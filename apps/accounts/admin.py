from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ['email']
    list_display = ['email', 'full_name', 'role', 'is_active']
    list_filter = ['role', 'is_active', 'is_staff']
    search_fields = ['email', 'full_name', 'student_no']
    fieldsets = [
        (None, {'fields': ['email', 'password']}),
        ('مشخصات', {'fields': ['full_name', 'role', 'student_no']}),
        ('دسترسی‌ها', {'fields': ['is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions']}),
        ('تاریخ‌ها', {'fields': ['last_login', 'date_joined']}),
    ]
    add_fieldsets = [(None, {'classes': ['wide'], 'fields': ['email', 'full_name', 'role', 'password1', 'password2']})]
