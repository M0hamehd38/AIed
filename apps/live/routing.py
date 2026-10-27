from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path('ws/live/teacher/<int:session_id>/', consumers.TeacherConsumer.as_asgi()),
    path('ws/live/student/', consumers.StudentConsumer.as_asgi()),
]
