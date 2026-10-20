from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Who decided what, and when. Summaries never hold students' personal data."""
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    course = models.ForeignKey('courses.Course', null=True, blank=True, on_delete=models.CASCADE, related_name='audit_entries')
    action = models.CharField(max_length=40)
    object_type = models.CharField(max_length=40)
    object_id = models.CharField(max_length=40, blank=True)
    summary = models.CharField(max_length=300)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-at', '-id']


def record(actor, action, obj, summary, course=None):
    return AuditLog.objects.create(actor=actor, course=course, action=action, object_type=type(obj).__name__,
                                   object_id=str(getattr(obj, 'pk', '') or ''), summary=summary[:300])
