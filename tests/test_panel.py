import json
from urllib.parse import quote

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.courses.models import Course, Enrollment, Question, Response
from apps.insights.models import Setting, Suggestion


def test_seed_counts(seeded):
    cs101, cs201 = Course.objects.get(code='CS101'), Course.objects.get(code='CS201')
    assert (cs101.concepts.count(), cs101.sessions.count(), cs101.enrollments.count()) == (4, 8, 30)
    assert Response.objects.filter(session_question__session__course=cs101).count() == 500
    assert Response.objects.filter(session_question__session__course=cs201).count() == 280
    assert list(Suggestion.objects.filter(course=cs101).values_list('key', flat=True)) == ['s1', 's2', 's4']


@pytest.mark.parametrize('url', ['/t/', '/t/students/', '/t/students/?f=attention&sort=name:1&q=۰۱', '/t/analytics/',
                                 '/t/suggestions/', '/t/live/', '/t/audio/', '/t/courses/', '/t/settings/'])
def test_pages_render(teacher_client, url):
    assert teacher_client.get(url).status_code == 200


def test_dashboard_shows_greeting_and_attention_count(teacher_client):
    body = teacher_client.get('/t/').content.decode()
    assert 'سلام دکتر شهرام گلزاری هرمزی' in body
    assert 'مشاهده‌ی همه (۱۲)' in body


@pytest.mark.parametrize('ev', [{'type': 'cell', 'c': 0, 's': 1}, {'type': 'concept', 'c': 2}, {'type': 'question', 'q': 12},
                                {'type': 'participation'}])
def test_evidence_partials(teacher_client, ev):
    r = teacher_client.get('/t/evidence/?ev=' + quote(json.dumps(ev)))
    assert r.status_code == 200 and 'data-title' in r.content.decode()


def test_low_n_cell_says_insufficient(teacher_client):
    # concept 3 (توابع) in session 6 has n=8 < 10
    body = teacher_client.get('/t/evidence/?ev=' + quote('{"type":"cell","c":3,"s":6}')).content.decode()
    assert 'داده کافی نیست' in body


def test_other_teachers_course_is_not_visible(teacher_client, cs101):
    other = User.objects.create_user('other@uni.ir', 'pass-pass-123', full_name='دکتر دیگر')
    c = Client(HTTP_HOST='localhost')
    c.force_login(other)
    assert c.post('/t/courses/switch/', {'course': cs101.pk}).status_code == 404
    e = Enrollment.objects.filter(course=cs101).first()
    assert c.get(f'/t/students/{e.pk}/').status_code == 200  # no course of their own: onboarding page, no data
    assert 'آرین کاظمی' not in c.get(f'/t/students/{e.pk}/').content.decode()
    s = Suggestion.objects.filter(course=cs101).first()
    assert c.post(f'/t/suggestions/{s.pk}/decide/', {'decision': 'approved'}).status_code == 404
    s.refresh_from_db()
    assert s.status == 'pending'


def test_student_profile_from_another_course_is_404(teacher_client, cs101):
    cs201_student = Enrollment.objects.exclude(course=cs101).first()
    teacher_client.post('/t/courses/switch/', {'course': cs101.pk})
    assert teacher_client.get(f'/t/students/{cs201_student.pk}/').status_code == 404


def test_decision_is_audited_and_kept_after_resync(teacher_client, seeded, cs101):
    s = Suggestion.objects.get(course=cs101, key='s1')
    r = teacher_client.post(f'/t/suggestions/{s.pk}/decide/', {'decision': 'approved'})
    assert r.status_code == 302
    entry = AuditLog.objects.filter(course=cs101).first()
    assert (entry.action, entry.actor, entry.summary) == ('approve', seeded, s.title)
    teacher_client.get('/t/suggestions/')  # re-runs the rules
    s.refresh_from_db()
    assert s.status == 'approved'


def test_edit_keeps_teacher_wording(teacher_client, cs101):
    s = Suggestion.objects.get(course=cs101, key='s4')
    teacher_client.post(f'/t/suggestions/{s.pk}/edit/', {'title': 'عنوان من', 'action': 'اقدام من'})
    teacher_client.get('/t/suggestions/')
    s.refresh_from_db()
    assert (s.title, s.action, s.edited) == ('عنوان من', 'اقدام من', True)
    assert AuditLog.objects.filter(action='edit', course=cs101).exists()


def test_draft_question_only_after_approval(teacher_client, cs101):
    s = Suggestion.objects.get(course=cs101, key='s2')
    assert teacher_client.post(f'/t/suggestions/{s.pk}/draft-question/').status_code == 400
    teacher_client.post(f'/t/suggestions/{s.pk}/decide/', {'decision': 'approved'})
    teacher_client.post(f'/t/suggestions/{s.pk}/draft-question/')
    q = Question.objects.filter(course=cs101).order_by('-number').first()
    assert q.status == 'draft' and q.source == 'ai_draft' and q.options.count() == 4


def test_settings_are_saved_per_course_and_validated(teacher_client, cs101):
    teacher_client.post('/t/settings/', {'green': 50, 'orange': 60, 'min_class': 10, 'min_student': 8, 'drop_alert': 10, 'retention_days': 30})
    assert not Setting.objects.filter(course=cs101).exists()
    teacher_client.post('/t/settings/', {'green': 80, 'orange': 55, 'min_class': 12, 'min_student': 8, 'drop_alert': 10, 'retention_days': 30})
    values = dict(Setting.objects.filter(course=cs101).values_list('key', 'value'))
    assert values['green'] == 0.8 and values['min_class'] == 12 and values['show_names'] is False


def test_hiding_names_shows_codes_only(teacher_client, cs101):
    teacher_client.post('/t/settings/', {'green': 75, 'orange': 50, 'min_class': 10, 'min_student': 8, 'drop_alert': 10, 'retention_days': 30})
    body = teacher_client.get('/t/students/').content.decode()
    assert 'آرین کاظمی' not in body and 'دانشجو ۰۱' in body


def test_create_course_with_concepts_session_question_and_csv(teacher_client, seeded):
    teacher_client.post('/t/courses/new/', {'title': 'طراحی الگوریتم', 'code': 'CS301', 'concepts': 'بازگشت\nبرنامه‌ریزی پویا'})
    course = Course.objects.get(code='CS301', teacher=seeded)
    assert list(course.concepts.values_list('title', flat=True)) == ['بازگشت', 'برنامه‌ریزی پویا']
    teacher_client.post('/t/sessions/add/', {'date': '۱۴۰۵/۰۷/۳۰', 'topic': 'آشنایی'})
    assert course.sessions.get().date.isoformat() == '2026-10-22'
    concept = course.concepts.first()
    teacher_client.post('/t/questions/add/', {'text': 'سؤال نمونه', 'option0': 'a', 'option1': 'b', 'option2': 'c', 'option3': 'd',
                                              'correct': '2', 'concepts': [concept.pk]})
    q = course.questions.get()
    assert q.options.get(is_correct=True).text == 'c'
    csv = SimpleUploadedFile('s.csv', 'کد,نام\n9901,علی رضایی\n9902,سارا محمدی\n9902,تکراری\n'.encode('utf-8'))
    teacher_client.post('/t/students/import/', {'csv': csv})
    assert list(course.enrollments.values_list('code', flat=True)) == ['9901', '9902']
    assert teacher_client.get('/t/').status_code == 200  # empty course: checklist


def test_student_export_is_json(teacher_client, cs101):
    e = Enrollment.objects.filter(course=cs101).first()
    teacher_client.post('/t/courses/switch/', {'course': cs101.pk})
    data = json.loads(teacher_client.get(f'/t/students/{e.pk}/export/').content)
    assert data['code'] == e.code and data['responses']
