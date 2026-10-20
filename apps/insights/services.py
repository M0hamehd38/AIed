"""Bridges the database and the pure analytics in lib/analytics."""
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Q
from django.utils.functional import cached_property

from apps.audit.models import record
from apps.courses.models import Course, Enrollment, Question, Response, SessionQuestion
from lib import analytics as A

from .models import Setting, Suggestion, SuggestionDecision

DEFAULTS = {'green': 0.75, 'orange': 0.50, 'min_class': 10, 'min_student': 8, 'drop_alert': 10,
            'show_names': True, 'retention_days': 30}


def course_settings(course):
    values = dict(DEFAULTS)
    # global defaults first, then this course's own values (one query)
    for st in sorted(Setting.objects.filter(Q(course__isnull=True) | Q(course=course)), key=lambda st: st.course_id is not None):
        values[st.key] = st.value
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
    """Everything the panel needs about one course, loaded once per request.
    The roster, the question bank and the responses load on first use, so light pages skip them."""

    def __init__(self, course: Course):
        self.course = course
        self.settings = course_settings(course)
        self.th = thresholds(self.settings)
        self.concepts = list(course.concepts.all())
        self.sessions = list(course.sessions.all())

    @cached_property
    def enrollments(self):
        return list(Enrollment.objects.filter(course=self.course).select_related('student').order_by('id'))

    @cached_property
    def students(self):
        return [StudentRef(i, e.pk, e.code, e.student.full_name) for i, e in enumerate(self.enrollments)]

    @cached_property
    def questions(self):
        return list(Question.objects.filter(course=self.course).prefetch_related('options', 'concepts')
                    .select_related('planned_session'))

    @cached_property
    def question_by_number(self):
        return {q.number: q for q in self.questions}

    @cached_property
    def asked(self):
        """question id → the session question it was first asked in"""
        asked = {}
        for sq in (SessionQuestion.objects.filter(session__course=self.course).select_related('session')
                   .order_by('session__number', 'id')):
            asked.setdefault(sq.question_id, sq)
        return asked

    @cached_property
    def qrefs(self):
        concept_index = {c.pk: i for i, c in enumerate(self.concepts)}
        refs = {}
        for q in self.questions:
            opts = list(q.options.all())
            correct = next((o.order for o in opts if o.is_correct), 0)
            sq = self.asked.get(q.pk)
            session = sq.session.number if sq else (q.planned_session.number if q.planned_session else 0)
            refs[q.number] = A.Question(id=q.number, session=session, concepts=sorted(concept_index[c.pk] for c in q.concepts.all()),
                                        options=[o.text for o in opts], correct=correct, late=bool(sq and sq.late), asked=bool(sq))
        return refs

    @cached_property
    def a(self):
        student_index = {e.student_id: i for i, e in enumerate(self.enrollments)}
        rows = (Response.objects.filter(session_question__session__course=self.course)
                .values_list('student_id', 'session_question__question__number', 'session_question__session__number',
                             'option__order', 'option__is_correct').order_by('id'))
        responses = [A.Response(student_index[sid], qnum, snum, opt, ok) for sid, qnum, snum, opt, ok in rows if sid in student_index]
        dataset = A.Dataset(
            concepts=[A.Concept(i, c.title, c.intro_session) for i, c in enumerate(self.concepts)],
            sessions=[A.Session(s.number) for s in self.sessions],
            questions=list(self.qrefs.values()), students=[s.index for s in self.students], responses=responses)
        return A.Analytics(dataset, self.th)

    @property
    def responses(self):
        return self.a.d.responses

    def student_name(self, s: StudentRef):
        return s.name if self.settings['show_names'] else f'دانشجو {A.fa(s.code)}'


@transaction.atomic
def sync_suggestions(data: CourseData):
    """Refresh the rule-based drafts. Decisions already taken, and teacher edits, are kept.
    Writes only what changed, so an ordinary page view costs one read."""
    course = data.course
    produced = A.build_suggestions(data.a)
    existing = {s.key: s for s in Suggestion.objects.filter(course=course)}
    for p in produced:
        s = existing.get(p['key'])
        if s is None:
            Suggestion.objects.create(course=course, **p)
            continue
        fields = ['evidence', 'evidence_ref', 'confidence', 'limitations', 'output'] + ([] if s.edited else ['title', 'action'])
        changed = [f for f in fields if getattr(s, f) != p[f]]
        for f in changed:
            setattr(s, f, p[f])
        if changed:
            s.save(update_fields=changed)
    stale = [s.pk for k, s in existing.items() if s.status == Suggestion.Status.PENDING and k not in {p['key'] for p in produced}]
    if stale:
        Suggestion.objects.filter(pk__in=stale).delete()


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
