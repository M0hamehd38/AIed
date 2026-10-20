from django.conf import settings
from django.db import models


class ConsentRecord(models.Model):
    """Informed consent before the first listening session in a course."""
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='consents')
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    kind = models.CharField(max_length=20, default='audio')
    text_version = models.CharField(max_length=20, default='1')
    announced_to_class = models.BooleanField(default=False)
    at = models.DateTimeField(auto_now_add=True)


class Transcript(models.Model):
    """Text only: raw audio is never stored. Deleted automatically after the retention period."""
    session = models.ForeignKey('courses.Session', on_delete=models.CASCADE, related_name='transcripts')
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()


class TranscriptSignal(models.Model):
    class Kind(models.TextChoices):
        QUESTION = 'question', 'پرسش'
        CONFUSION = 'confusion', 'ابهام'
        REPEAT = 'repeat', 'درخواست تکرار'
        EXAMPLE = 'example', 'درخواست مثال'
        TOPIC = 'topic', 'تغییر موضوع'

    transcript = models.ForeignKey(Transcript, on_delete=models.CASCADE, related_name='signals')
    kind = models.CharField(max_length=10, choices=Kind.choices)
    span = models.CharField(max_length=300)
    detector = models.CharField(max_length=10, default='rules')
