"""Live session: start/end, asking questions, answers, and the updates pushed to screens.

Students only ever receive the question and their own answer; answer counts go to the teacher alone.
"""
import secrets

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import IntegrityError, transaction
from django.db.models import Count, Max
from django.utils import timezone

from apps.audit.models import record
from apps.courses.models import Enrollment, Option, Question, Response, Session, SessionQuestion
from apps.insights.services import course_settings
from lib.analytics.fmt import fa, pct

from . import strings as S


class LiveError(Exception):
    pass


def teacher_group(session):
    return f'live-{session.pk}-teacher'


def student_group(session):
    return f'live-{session.pk}-students'


def live_session(course):
    return Session.objects.filter(course=course, status=Session.Status.LIVE).first()


def _new_code():
    # 6 digits, never starting with 0 so it reads the same everywhere
    return str(100000 + secrets.randbelow(900000))


@transaction.atomic
def start(course, teacher):
    if live_session(course):
        raise LiveError(S.MSG['already_live'])
    if not course.questions.filter(status=Question.Status.APPROVED).exists():
        raise LiveError(S.MSG['no_questions'])
    session = course.sessions.filter(status=Session.Status.PLANNED).order_by('number').first()
    if session is None:
        number = (course.sessions.aggregate(m=Max('number'))['m'] or 0) + 1
        session = Session.objects.create(course=course, number=number, date=timezone.localdate(),
                                         topic='جلسه‌ی زنده', status=Session.Status.PLANNED)
    for _ in range(20):
        try:
            with transaction.atomic():
                Session.objects.filter(pk=session.pk).update(
                    status=Session.Status.LIVE, join_code=_new_code(), started_at=timezone.now(), ended_at=None,
                    date=session.date or timezone.localdate())
            break
        except IntegrityError:  # code already used by another live session
            continue
    else:
        raise LiveError('could not allocate a join code')
    session.refresh_from_db()
    record(teacher, 'live_start', session, f'شروع جلسه‌ی زنده‌ی {session.number}', course=course)
    return session


def current_question(session):
    return (SessionQuestion.objects.filter(session=session).exclude(state=SessionQuestion.State.CLOSED)
            .select_related('question').first())


@transaction.atomic
def end(session, teacher):
    close_open(session)
    n = Response.objects.filter(session_question__session=session).count()
    Session.objects.filter(pk=session.pk).update(status=Session.Status.CLOSED, join_code=None, ended_at=timezone.now())
    session.refresh_from_db()
    record(teacher, 'live_end', session, f'پایان جلسه‌ی {session.number} · {n} پاسخ', course=session.course)
    broadcast(session)
    return n


def close_open(session):
    SessionQuestion.objects.filter(session=session).exclude(state=SessionQuestion.State.CLOSED).update(
        state=SessionQuestion.State.CLOSED, closed_at=timezone.now())


@transaction.atomic
def ask(session, question, late=False):
    if session.status != Session.Status.LIVE:
        raise LiveError(S.MSG['not_live'])
    close_open(session)
    sq, _ = SessionQuestion.objects.get_or_create(session=session, question=question)
    sq.state, sq.late, sq.opened_at, sq.closed_at = SessionQuestion.State.OPEN, late, timezone.now(), None
    sq.save()
    return sq


def set_state(session, state):
    sq = current_question(session)
    if sq is None:
        raise LiveError(S.MSG['not_live'])
    sq.state = state
    if state == SessionQuestion.State.CLOSED:
        sq.closed_at = timezone.now()
    sq.save(update_fields=['state', 'closed_at'])
    return sq


def answer(session, enrollment, option_order):
    """Record (or change) a student's answer to the open question."""
    sq = current_question(session)
    if sq is None or sq.state != SessionQuestion.State.OPEN:
        raise LiveError(S.MSG['answer_closed'])
    option = Option.objects.filter(question=sq.question, order=option_order).first()
    if option is None:
        raise LiveError('bad option')
    Response.objects.update_or_create(session_question=sq, student=enrollment.student, defaults={'option': option})
    return sq


# ------------------------------------------------------------------ what each screen sees
def last_question(session):
    """The open question, else the one closed most recently (students keep seeing it until the next)."""
    return current_question(session) or (SessionQuestion.objects.filter(session=session).select_related('question')
                                         .order_by('-closed_at', '-pk').first())


def student_view(session, enrollment=None):
    sq = last_question(session) if session.status == Session.Status.LIVE else None
    data = {'live': session.status == Session.Status.LIVE, 'session': session.number, 'course': session.course.title,
            'question': None}
    if sq:
        q = sq.question
        mine = None
        if enrollment:
            mine = Response.objects.filter(session_question=sq, student=enrollment.student).values_list('option__order', flat=True).first()
        data['question'] = {'id': sq.pk, 'number': q.number, 'text': q.text, 'state': sq.state,
                            'options': [o.text for o in q.options.all()], 'mine': mine}
    return data


def teacher_view(session):
    data = student_view(session)
    course = session.course
    data['code'] = session.join_code
    data['class_size'] = Enrollment.objects.filter(course=course).count()
    data['joined'] = 0
    sq = last_question(session)
    if sq and data['question'] is None:  # the session has ended: still show its last question
        q = sq.question
        data['question'] = {'id': sq.pk, 'number': q.number, 'text': q.text, 'state': sq.state,
                            'options': [o.text for o in q.options.all()], 'mine': None}
    if sq:
        opts = list(sq.question.options.all())
        counts = dict(Response.objects.filter(session_question=sq).values_list('option__order').annotate(n=Count('id')))
        n = sum(counts.values())
        correct = next((o.order for o in opts if o.is_correct), 0)
        data['question'].update({
            'correct': correct, 'late': sq.late, 'n': n, 'counts': [counts.get(o.order, 0) for o in opts],
            'concepts': list(sq.question.concepts.values_list('title', flat=True)),
            'insight': insight(course, opts, counts, n, correct)})
    data['answered_total'] = Response.objects.filter(session_question__session=session).count()
    return data


def insight(course, opts, counts, n, correct):
    cfg = course_settings(course)
    if n < cfg['min_class']:
        t, b = S.INSIGHT_INSUFFICIENT
        return {'kind': 'gray', 'title': t, 'text': b.format(min=fa(cfg['min_class']), n=fa(n))}
    wrong = max(((c, i) for i, c in counts.items() if i != correct), default=(0, None))
    ok = counts.get(correct, 0) / n
    if wrong[1] is not None and wrong[0] / n >= 0.25:
        t, b = S.INSIGHT_MISCONCEPTION
        return {'kind': 'orange', 'title': t.format(option=opts[wrong[1]].text), 'text': b.format(pct=pct(wrong[0] / n), n=fa(n))}
    t, b = S.INSIGHT_GOOD if ok >= cfg['green'] else S.INSIGHT_SCATTERED
    return {'kind': 'green' if ok >= cfg['green'] else 'blue', 'title': t, 'text': b.format(pct=pct(ok), n=fa(n))}


def answered(session):
    """A student answered: only the teacher's counts change, so only the teacher's screen is told."""
    layer = get_channel_layer()
    if layer is not None:
        async_to_sync(layer.group_send)(teacher_group(session), {'type': 'live.answered'})


def broadcast(session):
    """Push the new state: the full picture to the teacher, the question only to students."""
    layer = get_channel_layer()
    if layer is None:
        return
    send = async_to_sync(layer.group_send)
    send(teacher_group(session), {'type': 'live.update', 'data': teacher_view(session)})
    send(student_group(session), {'type': 'live.update', 'data': student_view(session)})
