"""Phase 3: listening. Audio goes from the teacher's browser through the panel to the speech-to-text
service and is dropped; only text lines (with their expiry) and speech cues are kept."""
import builtins
import importlib.util
import socket
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from apps.audio import signals
from apps.audio.models import ConsentRecord, Transcript, TranscriptSignal
from apps.audit.models import AuditLog

ROOT = Path(__file__).resolve().parent.parent
FAKE_AUDIO = b'\x1aE\xdf\xa3' + b'\x00' * 2000  # webm magic + padding; content is irrelevant to the stand-in model


# ------------------------------------------------------------------ the real stt/app.py, with a stand-in model
class _Seg:
    def __init__(self, text):
        self.text = text


class _Info:
    duration = 8.0


class StandInModel:
    """Replaces Whisper only (it cannot be downloaded in CI). Returns whatever the test queues."""
    def __init__(self):
        self.replies, self.received = [], []

    def transcribe(self, audio, **kw):
        self.received.append((audio.read(), kw))
        return [_Seg(t) for t in self.replies.pop(0)], _Info()


@pytest.fixture(scope='module')
def stt_server():
    pytest.importorskip('fastapi')
    uvicorn = pytest.importorskip('uvicorn')
    import os
    os.environ['STT_TOKEN'] = 'test-token-123'
    spec = importlib.util.spec_from_file_location('stt_app', ROOT / 'stt' / 'app.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    model = StandInModel()
    mod._model = model
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(mod.app, host='127.0.0.1', port=port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f'http://127.0.0.1:{port}', model
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def stt_on(settings, stt_server):
    url, model = stt_server
    settings.STT_URL, settings.STT_TOKEN = url, 'test-token-123'
    model.replies.clear()
    model.received.clear()
    return model


@pytest.fixture
def consented(teacher_client, cs101):
    teacher_client.post('/t/courses/switch/', {'course': cs101.pk})
    teacher_client.post('/t/audio/consent/', {'announced': 'on'})
    return cs101


def send(client, data=FAKE_AUDIO, content_type='audio/webm;codecs=opus'):
    return client.post('/t/audio/chunk/', data=data, content_type=content_type)


# ------------------------------------------------------------------ speech cues
@pytest.mark.parametrize('text, kinds', [
    ('استاد، ببخشید، فرق return با print چیه؟', ['question']),
    ('من متوجه نشدم مقدار برگشتی کجا ذخیره می‌شه.', ['confusion']),
    ('میشه یه بار دیگه توضیح بدید؟', ['repeat']),
    ('میشه یه مثال بزنید؟', ['example']),
    ('خب، بریم سراغ موضوع بعدی.', ['topic']),
    ('این قسمت يكم گیج‌کننده‌ست.', ['confusion']),          # Arabic ی/ک in the text still match
    ('دقیقاً. تابع همون لحظه تموم می‌شه.', []),
])
def test_speech_cues(text, kinds):
    assert [k for k, _ in signals.detect(text)] == kinds


# ------------------------------------------------------------------ consent
def test_listening_needs_announced_consent(teacher_client, cs101, stt_on):
    teacher_client.post('/t/courses/switch/', {'course': cs101.pk})
    assert send(teacher_client).status_code == 403
    teacher_client.post('/t/audio/consent/', {})                       # box not ticked
    assert not ConsentRecord.objects.filter(course=cs101).exists()
    teacher_client.post('/t/audio/consent/', {'announced': 'on'})
    assert ConsentRecord.objects.get(course=cs101).announced_to_class
    assert AuditLog.objects.filter(course=cs101, action='audio_consent').exists()
    assert 'رونوشت زنده' in teacher_client.get('/t/audio/').content.decode()


# ------------------------------------------------------------------ the chain
def test_chunk_becomes_a_text_line_with_cues_and_an_expiry(teacher_client, consented, stt_on):
    stt_on.replies.append(['من متوجه نشدم', 'مقدار برگشتی کجا میره؟'])
    r = send(teacher_client)
    assert r.status_code == 200, r.content
    body = r.json()
    assert body['line']['text'] == 'من متوجه نشدم مقدار برگشتی کجا میره؟'
    assert body['line']['signals'] == ['confusion'] and body['counts']['confusion'] == 1
    received, kw = stt_on.received[0]
    assert received == FAKE_AUDIO and kw['language'] == 'fa'       # the exact bytes reached the service
    line = Transcript.objects.get()
    assert line.session.number == 8                                 # the course's latest session
    days = (line.expires_at - timezone.now()).days
    assert 29 <= days <= 30                                         # course retention: 30 days
    assert TranscriptSignal.objects.get().span == 'متوجه نشدم'


def test_no_audio_is_written_anywhere(teacher_client, consented, stt_on, monkeypatch):
    real_open = builtins.open

    def guarded_open(file, mode='r', *a, **kw):
        assert not any(m in mode for m in 'wax'), f'audio path tried to write {file}'
        return real_open(file, mode, *a, **kw)
    monkeypatch.setattr(builtins, 'open', guarded_open)
    stt_on.replies.append(['سلام'])
    assert send(teacher_client).status_code == 200
    field_types = {f.get_internal_type() for f in Transcript._meta.get_fields() if hasattr(f, 'get_internal_type')}
    assert not field_types & {'FileField', 'BinaryField'}


def test_silence_adds_no_line(teacher_client, consented, stt_on):
    stt_on.replies.append([])
    assert send(teacher_client).json()['line'] is None
    assert not Transcript.objects.exists()


def test_bad_or_oversized_audio_is_refused(teacher_client, consented, stt_on):
    assert send(teacher_client, content_type='text/plain').status_code == 415
    assert send(teacher_client, data=b'\x00' * (2 * 1024 * 1024 + 1)).status_code == 413


def test_service_rejects_a_wrong_token(teacher_client, consented, stt_on, settings):
    settings.STT_TOKEN = 'wrong'
    assert send(teacher_client).status_code == 503


def test_service_down_or_not_configured(teacher_client, consented, settings):
    settings.STT_URL, settings.STT_TOKEN = '', ''
    assert send(teacher_client).status_code == 503
    assert 'سرویس تبدیل گفتار تنظیم نشده است' in teacher_client.get('/t/audio/').content.decode()
    settings.STT_URL, settings.STT_TOKEN = 'http://127.0.0.1:9', 'x'   # nothing listens there
    assert send(teacher_client).status_code == 503


# ------------------------------------------------------------------ retention and display
def test_expired_lines_are_purged(teacher_client, consented, stt_on):
    from django.core.management import call_command
    stt_on.replies += [['یک'], ['دو']]
    send(teacher_client)
    send(teacher_client)
    old = Transcript.objects.order_by('id').first()
    Transcript.objects.filter(pk=old.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    call_command('purge_transcripts', verbosity=0)
    assert list(Transcript.objects.values_list('text', flat=True)) == ['دو']


def test_overview_counts_confusion_cues_of_the_last_session(teacher_client, consented, stt_on):
    stt_on.replies.append(['من گیج شدم'])
    send(teacher_client)
    body = teacher_client.get('/t/').content.decode()
    assert 'نشانه‌ی ابهام گفتاری' in body and 'از رونوشت جلسه‌ی ۸' in body
