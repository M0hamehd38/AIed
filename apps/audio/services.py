"""Listening: consent, transcript lines with their speech cues, and the retention clean-up.

Only text is kept. Every line expires after the course's retention period and is then deleted.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.audit.models import record
from apps.courses.models import Session

from . import signals
from . import strings as S
from .models import ConsentRecord, Transcript, TranscriptSignal


def consent_given(course):
    return ConsentRecord.objects.filter(course=course, kind='audio', announced_to_class=True).exists()


def give_consent(course, teacher):
    c = ConsentRecord.objects.create(course=course, teacher=teacher, kind='audio', text_version=S.CONSENT_VERSION,
                                     announced_to_class=True)
    record(teacher, 'audio_consent', c, 'ثبت رضایت‌نامه‌ی شنود (اعلام‌شده به کلاس)', course=course)
    return c


def target_session(course):
    """Lines go to the live session if there is one, otherwise to the course's latest session."""
    return (Session.objects.filter(course=course, status=Session.Status.LIVE).first()
            or Session.objects.filter(course=course).order_by('-number').first())


@transaction.atomic
def add_line(session, text, retention_days):
    now = timezone.now()
    line = Transcript.objects.create(session=session, text=text[:4000], expires_at=now + timedelta(days=retention_days))
    found = signals.detect(text)
    TranscriptSignal.objects.bulk_create([TranscriptSignal(transcript=line, kind=k, span=span[:300]) for k, span in found])
    return line, [k for k, _ in found]


def counts(session):
    got = dict(TranscriptSignal.objects.filter(transcript__session=session).values_list('kind').annotate(n=Count('id')))
    return {k: got.get(k, 0) for k, _, _ in S.SIGNALS}


def purge_expired():
    n, _ = Transcript.objects.filter(expires_at__lte=timezone.now()).delete()
    return n


def line_json(line, kinds):
    local = timezone.localtime(line.created_at)
    return {'id': line.pk, 'time': local.strftime('%H:%M'), 'text': line.text, 'signals': kinds}
