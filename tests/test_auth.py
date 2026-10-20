import pytest
from django.test import Client

from apps.accounts.models import User

from .conftest import PASSWORD


def client():
    return Client(HTTP_HOST='localhost')


def test_landing_page_renders(db):
    r = client().get('/')
    assert r.status_code == 200
    assert 'کلاس‌یار' in r.content.decode()


def test_teacher_login_goes_to_panel(seeded):
    r = client().post('/accounts/login/', {'email': 'golzari@classyar.ir', 'password': PASSWORD})
    assert r.status_code == 302 and r['Location'] == '/t/'


def test_password_is_hashed_with_argon2(seeded):
    assert seeded.password.startswith('argon2')


def test_wrong_password_reopens_dialog_with_message(seeded):
    r = client().post('/accounts/login/', {'email': 'golzari@classyar.ir', 'password': 'wrong-one'})
    body = r.content.decode()
    assert r.status_code == 400
    assert 'data-open-auth="login"' in body and 'ایمیل یا رمز عبور درست نیست.' in body


def test_login_is_rate_limited(seeded):
    c = client()
    for _ in range(5):
        c.post('/accounts/login/', {'email': 'golzari@classyar.ir', 'password': 'wrong-one'})
    r = c.post('/accounts/login/', {'email': 'golzari@classyar.ir', 'password': PASSWORD})
    assert r.status_code == 429


def test_signup_creates_teacher_and_signs_in(db):
    c = client()
    r = c.post('/accounts/signup/', {'full_name': 'دکتر نمونه', 'email': 'New@Uni.ac.ir', 'password': 'a-strong-pass-1'})
    assert r.status_code == 302 and r['Location'] == '/t/'
    user = User.objects.get(email='new@uni.ac.ir')
    assert user.role == User.Role.TEACHER
    assert c.get('/t/').status_code == 200  # no course yet: onboarding page


@pytest.mark.parametrize('password', ['short', '12345678901'])
def test_signup_rejects_weak_passwords(db, password):
    r = client().post('/accounts/signup/', {'full_name': 'دکتر نمونه', 'email': 'a@b.ir', 'password': password})
    assert r.status_code == 400 and not User.objects.filter(email='a@b.ir').exists()


def test_panel_requires_login(db):
    r = client().get('/t/')
    assert r.status_code == 302 and r['Location'].startswith('/?auth=login')


def test_students_cannot_open_teacher_panel(seeded):
    c = client()
    c.force_login(User.objects.filter(role=User.Role.STUDENT).first())
    assert c.get('/t/').status_code == 403


def test_logout_needs_post(teacher_client):
    assert teacher_client.get('/accounts/logout/').status_code == 405
    assert teacher_client.post('/accounts/logout/').status_code == 302
