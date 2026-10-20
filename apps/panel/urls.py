from django.urls import path

from . import views

app_name = 'panel'
urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('live/', views.live, name='live'),
    path('audio/', views.audio, name='audio'),
    path('students/', views.students, name='students'),
    path('students/<int:pk>/', views.student_profile, name='student'),
    path('students/<int:pk>/export/', views.student_export, name='student_export'),
    path('students/import/', views.students_import, name='students_import'),
    path('analytics/', views.analytics, name='analytics'),
    path('suggestions/', views.suggestions, name='suggestions'),
    path('suggestions/<int:pk>/decide/', views.suggestion_decide, name='suggestion_decide'),
    path('suggestions/<int:pk>/edit/', views.suggestion_edit, name='suggestion_edit'),
    path('suggestions/<int:pk>/draft-question/', views.suggestion_draft_question, name='suggestion_draft_question'),
    path('evidence/', views.evidence, name='evidence'),
    path('courses/', views.courses, name='courses'),
    path('courses/new/', views.course_create, name='course_create'),
    path('courses/switch/', views.course_switch, name='course_switch'),
    path('concepts/add/', views.concept_add, name='concept_add'),
    path('sessions/add/', views.session_add, name='session_add'),
    path('questions/add/', views.question_add, name='question_add'),
    path('questions/<int:pk>/approve/', views.question_approve, name='question_approve'),
    path('settings/', views.settings_view, name='settings'),
]
