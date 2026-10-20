from django.contrib import admin

from .models import Setting, Suggestion, SuggestionDecision


@admin.register(Suggestion)
class SuggestionAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'status', 'confidence', 'edited']
    list_filter = ['status', 'course']


@admin.register(SuggestionDecision)
class SuggestionDecisionAdmin(admin.ModelAdmin):
    list_display = ['suggestion', 'decision', 'decided_by', 'at']


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ['key', 'course', 'value']
