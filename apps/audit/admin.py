from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['at', 'actor', 'action', 'summary', 'course']
    list_filter = ['action', 'course']

    def has_change_permission(self, request, obj=None):
        return False  # the audit trail is append-only
