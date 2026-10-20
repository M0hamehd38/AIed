from django.contrib import admin

from .models import Concept, Course, Enrollment, Option, Question, Session


class ConceptInline(admin.TabularInline):
    model = Concept
    extra = 0


class SessionInline(admin.TabularInline):
    model = Session
    extra = 0


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['title', 'code', 'group', 'term', 'teacher']
    list_filter = ['term']
    search_fields = ['title', 'code']
    inlines = [ConceptInline, SessionInline]


class OptionInline(admin.TabularInline):
    model = Option
    extra = 0


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['number', 'course', 'status', 'source']
    list_filter = ['status', 'source', 'course']
    inlines = [OptionInline]


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ['course', 'code', 'student']
    list_filter = ['course']
