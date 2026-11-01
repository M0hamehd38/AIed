import pytest
from django.test import Client

from apps.accounts.forms import normalize_mobile
from apps.accounts.models import User
from apps.audit.models import AuditLog

from .conftest import PASSWORD

URL = '/t/account/'


def test_account_page_and_topbar_link(teacher_client):
    assert teacher_client.get(URL).status_code == 200
    assert 'href="/t/account/"' in teacher_client.get('/t/').content.decode()


def test_account_needs_sign_in():
    assert Client(HTTP_HOST='localhost').get(URL).status_code == 302


@pytest.mark.parametrize('raw', ['09121234567', '۰۹۱۲ ۱۲۳ ۴۵۶۷', '+989121234567', '00989121234567', '9121234567', '0912-123-4567'])
def test_mobile_spellings(raw):
    assert normalize_mobile(raw) == '09121234567'


def test_edit_name_mobile_and_sms(teacher_client, seeded):
    r = teacher_client.post(URL, {'form': 'profile', 'full_name': '  دکتر   شهرام گلزاری ', 'mobile': '۰۹۱۲۱۲۳۴۵۶۷', 'sms_opt_in': 'on'})
    assert r.status_code == 302
    seeded.refresh_from_db()
    assert (seeded.full_name, seeded.mobile, seeded.sms_opt_in, seeded.mobile_verified) == ('دکتر شهرام گلزاری', '09121234567', True, False)
    log = AuditLog.objects.filter(action='account').latest('at')
    assert '09121234567' not in log.summary and 'شماره‌ی موبایل' in log.summary   # what changed, not the value


@pytest.mark.parametrize('data, field', [
    ({'full_name': 'دکتر گلزاری', 'mobile': '12345'}, 'شماره‌ی موبایل را مثل'),
    ({'full_name': 'دکتر گلزاری', 'mobile': '', 'sms_opt_in': 'on'}, 'برای دریافت پیامک'),
    ({'full_name': 'ab', 'mobile': ''}, 'نام خود را کامل'),
])
def test_profile_rejects_bad_input(teacher_client, seeded, data, field):
    r = teacher_client.post(URL, {'form': 'profile', **data})
    assert r.status_code == 400 and field in r.content.decode()
    seeded.refresh_from_db()
    assert seeded.full_name == 'دکتر شهرام گلزاری هرمزی'


def test_new_mobile_needs_verifying_again(teacher_client, seeded):
    User.objects.filter(pk=seeded.pk).update(mobile='09121234567', mobile_verified=True)
    teacher_client.post(URL, {'form': 'profile', 'full_name': seeded.full_name, 'mobile': '09351234567'})
    seeded.refresh_from_db()
    assert seeded.mobile == '09351234567' and not seeded.mobile_verified


def test_change_email_needs_current_password(teacher_client, seeded):
    r = teacher_client.post(URL, {'form': 'email', 'email': 'new@uni.ir', 'current_password': 'wrong-pass'})
    assert r.status_code == 400 and 'رمز عبور فعلی درست نیست' in r.content.decode()
    r = teacher_client.post(URL, {'form': 'email', 'email': 'New@Uni.ir', 'current_password': PASSWORD})
    assert r.status_code == 302
    seeded.refresh_from_db()
    assert seeded.email == 'new@uni.ir'
    assert Client(HTTP_HOST='localhost').post('/accounts/login/', {'email': 'new@uni.ir', 'password': PASSWORD}).status_code == 302


def test_email_taken_by_someone_else(teacher_client):
    User.objects.create_user('taken@uni.ir', 'pass-pass-123', full_name='دیگری')
    r = teacher_client.post(URL, {'form': 'email', 'email': 'taken@uni.ir', 'current_password': PASSWORD})
    assert r.status_code == 400 and 'حساب دیگری' in r.content.decode()


def test_change_password_keeps_this_session(teacher_client, seeded):
    r = teacher_client.post(URL, {'form': 'password', 'current_password': PASSWORD, 'new_password': 'Tazeh-Ramz-42', 'new_password2': 'Tazeh-Ramz-42'})
    assert r.status_code == 302
    assert teacher_client.get('/t/').status_code == 200   # still signed in here
    seeded.refresh_from_db()
    assert seeded.check_password('Tazeh-Ramz-42') and not seeded.check_password(PASSWORD)


@pytest.mark.parametrize('new, again, msg', [('Tazeh-Ramz-42', 'other-ramz-42', 'یکسان نیستند'), ('12345678', '12345678', 'new_password')])
def test_password_rules(teacher_client, seeded, new, again, msg):
    r = teacher_client.post(URL, {'form': 'password', 'current_password': PASSWORD, 'new_password': new, 'new_password2': again})
    body = r.content.decode()
    assert r.status_code == 400 and (msg in body if msg != 'new_password' else 'aWNewErr' in body)
    seeded.refresh_from_db()
    assert seeded.check_password(PASSWORD)


def test_wrong_current_password_is_throttled(teacher_client, seeded):
    for _ in range(5):
        teacher_client.post(URL, {'form': 'password', 'current_password': 'nope-nope', 'new_password': 'Tazeh-Ramz-42', 'new_password2': 'Tazeh-Ramz-42'})
    r = teacher_client.post(URL, {'form': 'password', 'current_password': PASSWORD, 'new_password': 'Tazeh-Ramz-42', 'new_password2': 'Tazeh-Ramz-42'})
    assert r.status_code == 429
    seeded.refresh_from_db()
    assert seeded.check_password(PASSWORD)
