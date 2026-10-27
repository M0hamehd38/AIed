from django.urls import path

from . import views

app_name = 'live'
urlpatterns = [
    path('', views.join, name='join'),
    path('live/', views.student, name='student'),
    path('state/', views.state, name='state'),
    path('answer/', views.answer, name='answer'),
    path('leave/', views.leave, name='leave'),
]
