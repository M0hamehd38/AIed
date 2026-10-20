"""Bridges the database and the pure analytics in lib/analytics."""
from dataclasses import dataclass

from django.db import transaction

from apps.audit.models import record
from apps.courses.models import Course, Enrollment, Question, Response, SessionQuestion
from lib import analytics as A

from .models import Setting, Suggestion, SuggestionDecision

DEFAULTS = {'green': 0.75, 'orange': 0.50, 'min_class': 10, 'min_student': 8, 'drop_alert': 10,
            'show_names': True, 'retention_days': 30}


def course_settings(course):
    values = dict(DEFAULTS)
    for s in Setting.objects.filter(course__isnull=True):
        values[s.key] = s.value
    for s in Setting.objects.filter(course=course):
        values[s.key] = s.value
    return values


def save_course_settings(course, values, actor):
    with transaction.atomic():
        for k, v in values.items():
            if k in DEFAULTS:
                Setting.objects.update_or_create(course=course, key=k, defaults={'value': v})
        record(actor, 'settings', course, 'به‌روزرسانی آستانه‌ها و تنظیمات درس', course=course)


def thresholds(values):
    return A.Thresholds(green=values['green'], orange=values['orange'], min_class=values['min_class'],
                        min_student=values['min_student'], drop_alert=values['drop_alert'])


@dataclass
class StudentRef:
    index: int
    pk: int  # enrollment id
    code: str
    name: str


class CourseData:
    """Everything the panel needs about one course, loaded once per request."""

    def __init__(self, course: Course):
        self.course = course
        self.settings = course_settings(course)
        self.th = thresholds(self.settings)
        self.concepts = list(course.concepts.all())
        self.sessions = list(course.sessions.all())
        concept_index = {c.pk: i for i, c in enumerate(self.concepts)}
        self.enrollments = list(Enrollment.objects.filter(course=course).select_related('student').order_by('id'))
        student_index = {e.student_id: i for i, e in enumerate(self.enrollments)}
        self.students = [StudentRef(i, e.pk, e.code, e.student.full_name) for i, e in enumerate(self.enrollments)]

        self.questions = list(Question.objects.filter(course=course).prefetch_related('options', 'concepts')
                              .select_related('planned_session'))
        asked = {}
        for sq in SessionQuestion.objects.filter(session__course=course).select_related('session').order_by('session__number', 'id'):
            asked.setdefault(sq.question_id, sq)
        self.asked = asked
        self.qrefs = {}
        aq = []
        for q in self.questions:
            opts = list(q.options.all())
            correct = next((o.order for o in opts if o.is_correct), 0)
            sq = asked.get(q.pk)
            session = sq.session.number if sq else (q.planned_session.number if q.planned_session else 0)
            ref = A.Question(id=q.number, session=session, concepts=sorted(concept_index[c.pk] for c in q.concepts.all()),
                             options=[o.text for o in opts], correct=correct, late=bool(sq and sq.late), asked=bool(sq))
            self.qrefs[q.number] = ref
            aq.append(ref)
        self.question_by_number = {q.number: q for q in self.questions}

        responses = []
        rows = (Response.objects.filter(session_question__session__course=course)
                .values_list('student_id', 'session_question__question__number', 'session_question__session__number',
                             'option__order', 'option__is_correct').order_by('id'))
        for sid, qnum, snum, opt, ok in rows:
            if sid in student_index:
                responses.append(A.Response(student_index[sid], qnum, snum, opt, ok))
        dataset = A.Dataset(
            concepts=[A.Concept(i, c.title, c.intro_session) for i, c in enumerate(self.concepts)],
            sessions=[A.Session(s.number) for s in self.sessions],
            questions=aq, students=[s.index for s in self.students], responses=responses)
        self.a = A.Analytics(dataset, self.th)

    @property
    def responses(self):
        return self.a.d.responses

    def student_name(self, s: StudentRef):
        return s.name if self.settings['show_names'] else f'دانشجو {A.fa(s.code)}'


@transaction.atomic
def sync_suggestions(data: CourseData):
    """Refresh the rule-based drafts. Decisions already taken, and teacher edits, are kept."""
    course = data.course
    produced = A.build_suggestions(data.a)
    keys = [p['key'] for p in produced]
    for p in produced:
        s = Suggestion.objects.filter(course=course, key=p['key']).first()
        if s is None:
            Suggestion.objects.create(course=course, **p)
            continue
        for f in ('evidence', 'evidence_ref', 'confidence', 'limitations', 'output'):
            setattr(s, f, p[f])
        if not s.edited:
            s.title, s.action = p['title'], p['action']
        s.save()
    Suggestion.objects.filter(course=course, status=Suggestion.Status.PENDING).exclude(key__in=keys).delete()


def decide(suggestion, decision, actor):
    suggestion.status = decision
    suggestion.save(update_fields=['status'])
    SuggestionDecision.objects.create(suggestion=suggestion, decided_by=actor, decision=decision,
                                      title=suggestion.title, action=suggestion.action)
    record(actor, 'approve' if decision == Suggestion.Status.APPROVED else 'reject', suggestion, suggestion.title,
           course=suggestion.course)


def edit(suggestion, title, action, actor):
    suggestion.title, suggestion.action, suggestion.edited = title, action, True
    suggestion.save(update_fields=['title', 'action', 'edited'])
    SuggestionDecision.objects.create(suggestion=suggestion, decided_by=actor, decision='edited', title=title, action=action)
    record(actor, 'edit', suggestion, title, course=suggestion.course)


__all__ = ['CourseData', 'StudentRef', 'course_settings', 'save_course_settings', 'sync_suggestions', 'decide', 'edit']
