from django.conf import settings
from django.db import models


class Setting(models.Model):
    """Key/value settings; course=None means the global default."""
    course = models.ForeignKey('courses.Course', null=True, blank=True, on_delete=models.CASCADE, related_name='settings')
    key = models.CharField(max_length=60)
    value = models.JSONField()

    class Meta:
        unique_together = [('course', 'key')]


class Suggestion(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'در انتظار تصمیم'
        APPROVED = 'approved', 'تأییدشده'
        REJECTED = 'rejected', 'ردشده'

    class Confidence(models.TextChoices):
        HIGH = 'high', 'اطمینان بالا'
        MEDIUM = 'medium', 'اطمینان متوسط'
        LOW = 'low', 'اطمینان پایین'
        INSUFFICIENT = 'insufficient', 'داده کافی نیست'

    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='suggestions')
    key = models.CharField(max_length=60)  # stable id of the rule that produced it
    title = models.CharField(max_length=200)
    action = models.TextField()
    evidence = models.TextField()
    evidence_ref = models.JSONField(default=dict)  # what the "evidence" link opens
    limitations = models.TextField(blank=True)
    confidence = models.CharField(max_length=14, choices=Confidence.choices)
    output = models.CharField(max_length=20, blank=True)  # e.g. 'question': can draft a similar question
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    edited = models.BooleanField(default=False)
    drafted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        unique_together = [('course', 'key')]


class SuggestionDecision(models.Model):
    suggestion = models.ForeignKey(Suggestion, on_delete=models.CASCADE, related_name='decisions')
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    decision = models.CharField(max_length=10)  # approved / rejected / edited
    title = models.CharField(max_length=200, blank=True)
    action = models.TextField(blank=True)
    at = models.DateTimeField(auto_now_add=True)
