import pytest
from django.core.management import call_command
from django.test import Client

from apps.accounts.models import User
from apps.courses.models import Course

PASSWORD = 'demo-pass-9876'


@pytest.fixture
def seeded(db, monkeypatch):
    monkeypatch.setenv('DEMO_TEACHER_PASSWORD', PASSWORD)
    call_command('seed_demo', verbosity=0)
    return User.objects.get(email='golzari@classyar.ir')


@pytest.fixture
def teacher_client(seeded):
    c = Client(HTTP_HOST='localhost')
    c.force_login(seeded)
    return c


@pytest.fixture
def cs101(seeded):
    return Course.objects.get(code='CS101')


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.core.cache import cache
    cache.clear()
