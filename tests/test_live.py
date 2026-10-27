"""Phase 2: live sessions. Students join with code + student number; answers go over HTTP; screens update over WebSocket."""
import pytest
from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import Client

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.courses.models import Course, Enrollment, Question, Response, Session
from apps.live import services
from config.asgi import application


@pytest.fixture
def live(teacher_client, cs101):
    teacher_client.post('/t/courses/switch/', {'course': cs101.pk})
    assert teacher_client.post('/t/live/start/').status_code == 302
    return Session.objects.get(course=cs101, status=Session.Status.LIVE)


def loops_question(course):
    return Question.objects.get(course=course, number=9)  # «for i in range(3)…», correct option order 1


def student(code, number):
    c = Client(HTTP_HOST='localhost')
    r = c.post('/j/', {'code': code, 'number': number})
    assert r.status_code == 302 and r['Location'] == '/j/live/', r.content.decode()[:300]
    return c


# ------------------------------------------------------------------ starting and ending
def test_start_creates_the_next_session_with_a_six_digit_code(live, cs101):
    assert live.number == 9 and len(live.join_code) == 6 and live.join_code.isdigit()
    assert AuditLog.objects.filter(course=cs101, action='live_start').exists()


def test_only_one_live_session_per_course(teacher_client, live):
    teacher_client.post('/t/live/start/')
    assert Session.objects.filter(course=live.course, status=Session.Status.LIVE).count() == 1


def test_end_invalidates_the_code_and_closes_the_question(teacher_client, live):
    teacher_client.post('/t/live/ask/', {'question': loops_question(live.course).pk})
    code = live.join_code
    teacher_client.post('/t/live/end/')
    live.refresh_from_db()
    assert live.status == Session.Status.CLOSED and live.join_code is None
    assert not live.asked.exclude(state='closed').exists()
    r = Client(HTTP_HOST='localhost').post('/j/', {'code': code, 'number': '01'})
    assert r.status_code == 400 and 'کد جلسه پیدا نشد' in r.content.decode()


# ------------------------------------------------------------------ joining
def test_join_by_course_code_or_student_number(live):
    student(live.join_code, '۰۱')                     # Persian digits are fine
    student(live.join_code, '1405101' + '02')        # the full student number works too


def test_join_rejects_students_outside_the_course(live):
    outsider = Enrollment.objects.exclude(course=live.course).first()
    r = Client(HTTP_HOST='localhost').post('/j/', {'code': live.join_code, 'number': outsider.student.student_no})
    assert r.status_code == 400 and 'در فهرست این درس نیست' in r.content.decode()


def test_join_attempts_are_throttled(live):
    c = Client(HTTP_HOST='localhost')
    from apps.live.views import JOIN_TRIES
    for _ in range(JOIN_TRIES):
        c.post('/j/', {'code': '000000', 'number': '01'})
    assert c.post('/j/', {'code': live.join_code, 'number': '01'}).status_code == 429


# ------------------------------------------------------------------ asking and answering
def test_answer_flow_and_privacy(teacher_client, live):
    q = loops_question(live.course)
    s1, s2 = student(live.join_code, '01'), student(live.join_code, '02')
    assert s1.post('/j/answer/', {'option': 1}).status_code == 409          # nothing asked yet
    teacher_client.post('/t/live/ask/', {'question': q.pk})
    assert s1.post('/j/answer/', {'option': 1}).json()['question']['mine'] == 1
    s2.post('/j/answer/', {'option': 2})
    s2.post('/j/answer/', {'option': 1})                                     # changing the answer is allowed
    teacher = teacher_client.get('/t/live/state/').json()['question']
    assert teacher['counts'] == [0, 2, 0, 0] and teacher['n'] == 2
    seen_by_student = s1.get('/j/state/').json()
    assert 'counts' not in seen_by_student['question'] and 'insight' not in seen_by_student['question']
    assert 'correct' not in seen_by_student['question']                     # the right answer is not revealed


def test_paused_and_closed_questions_take_no_answers(teacher_client, live):
    teacher_client.post('/t/live/ask/', {'question': loops_question(live.course).pk})
    s = student(live.join_code, '03')
    teacher_client.post('/t/live/control/', {'state': 'paused'})
    assert s.post('/j/answer/', {'option': 1}).status_code == 409
    teacher_client.post('/t/live/control/', {'state': 'open'})
    assert s.post('/j/answer/', {'option': 1}).status_code == 200
    teacher_client.post('/t/live/control/', {'state': 'closed'})
    assert s.post('/j/answer/', {'option': 0}).status_code == 409
    assert s.get('/j/state/').json()['question']['state'] == 'closed'      # students still see the closed question


def test_thirty_students_answer_and_the_analytics_count_them(teacher_client, live):
    q = loops_question(live.course)
    clients = [student(live.join_code, f'{i:02d}') for i in range(1, 31)]
    teacher_client.post('/t/live/ask/', {'question': q.pk, 'late': '0'})
    for i, c in enumerate(clients):
        assert c.post('/j/answer/', {'option': i % 4}).status_code == 200
    assert teacher_client.get('/t/live/state/').json()['question']['n'] == 30
    teacher_client.post('/t/live/end/')
    assert Response.objects.filter(session_question__session=live).count() == 30
    # the new session now shows in the mastery map of the overview
    assert 'ج۹' in teacher_client.get('/t/').content.decode()


def test_late_question_is_left_out_of_participation(teacher_client, live):
    teacher_client.post('/t/live/ask/', {'question': loops_question(live.course).pk, 'late': '1'})
    assert live.asked.get().late is True


def test_other_teachers_cannot_reach_the_session(live):
    other = User.objects.create_user('other@uni.ir', 'pass-pass-123', full_name='دکتر دیگر')
    Course.objects.create(teacher=other, title='درس دیگر')
    c = Client(HTTP_HOST='localhost')
    c.force_login(other)
    for url in ['/t/live/state/', '/t/live/qr.svg']:
        assert c.get(url).status_code == 404
    assert c.post('/t/live/ask/', {'question': loops_question(live.course).pk}).status_code == 404


def test_qr_code_points_at_the_join_page(teacher_client, live):
    r = teacher_client.get('/t/live/qr.svg')
    assert r.status_code == 200 and r['Content-Type'] == 'image/svg+xml' and b'<svg' in r.content


# ------------------------------------------------------------------ WebSocket
def _ws(path, client):
    cookie = f'sessionid={client.cookies["sessionid"].value}'.encode()
    return WebsocketCommunicator(application, path, headers=[(b'cookie', cookie), (b'origin', b'http://localhost'), (b'host', b'localhost')])


@pytest.mark.django_db(transaction=True)
def test_websockets_push_questions_to_students_and_counts_to_the_teacher(monkeypatch):
    from django.core.management import call_command
    monkeypatch.setenv('DEMO_TEACHER_PASSWORD', 'demo-pass-9876')
    call_command('seed_demo', verbosity=0)
    teacher = User.objects.get(email='golzari@classyar.ir')
    tc = Client(HTTP_HOST='localhost')
    tc.force_login(teacher)
    cs101 = Course.objects.get(code='CS101')
    tc.post('/t/courses/switch/', {'course': cs101.pk})
    tc.post('/t/live/start/')
    live = Session.objects.get(course=cs101, status=Session.Status.LIVE)
    sc = student(live.join_code, '01')

    async def scenario():
        t = _ws(f'/ws/live/teacher/{live.pk}/', tc)
        s = _ws('/ws/live/student/', sc)
        assert (await t.connect())[0] and (await s.connect())[0]
        assert (await t.receive_json_from())['code'] == live.join_code
        assert (await s.receive_json_from())['question'] is None
        # the teacher asks: the question reaches the phone, without the answer counts
        await sync_to_async(tc.post)('/t/live/ask/', {'question': await sync_to_async(lambda: loops_question(cs101).pk)()})
        got = await s.receive_json_from(timeout=3)
        assert got['question']['number'] == 9 and 'counts' not in got['question']
        await t.receive_json_from(timeout=3)
        # a student answers: only the teacher hears about it, once per burst
        await sync_to_async(sc.post)('/j/answer/', {'option': 1})
        got = await t.receive_json_from(timeout=3)
        assert got['question']['n'] == 1 and got['question']['counts'][1] == 1
        assert await s.receive_nothing(timeout=0.4)
        await t.disconnect()
        await s.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_websocket_refuses_strangers(monkeypatch):
    from django.core.management import call_command
    monkeypatch.setenv('DEMO_TEACHER_PASSWORD', 'demo-pass-9876')
    call_command('seed_demo', verbosity=0)

    async def scenario():
        anon = WebsocketCommunicator(application, '/ws/live/student/', headers=[(b'origin', b'http://localhost'), (b'host', b'localhost')])
        ok, _ = await anon.connect()
        assert not ok
        teacher_ws = WebsocketCommunicator(application, '/ws/live/teacher/1/', headers=[(b'origin', b'http://localhost'), (b'host', b'localhost')])
        ok, _ = await teacher_ws.connect()
        assert not ok
    async_to_sync(scenario)()


def test_a_class_on_one_network_is_not_locked_out_by_a_few_typos(live):
    for i in range(1, 21):  # 20 typos from the same address, then everyone still gets in
        Client(HTTP_HOST='localhost').post('/j/', {'code': '000000', 'number': '01'})
    student(live.join_code, '05')


def test_student_session_is_renewed_during_a_long_class(live):
    import time
    c = student(live.join_code, '06')
    s = c.session
    s['seen'] = int(time.time()) - 10 * 60
    s.save()
    c.get('/j/state/')
    assert c.session['seen'] > int(time.time()) - 60
