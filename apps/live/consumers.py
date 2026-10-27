"""WebSocket channels. They only push updates; every change goes through ordinary HTTP views."""
import asyncio

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.accounts.models import User
from apps.courses.models import Enrollment, Session

from . import services

BATCH_SECONDS = 0.15


class TeacherConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.session = await self._own_session(self.scope['user'], self.scope['url_route']['kwargs']['session_id'])
        if self.session is None:
            await self.close(code=4403)
            return
        self.group = services.teacher_group(self.session)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self.send_json(await database_sync_to_async(services.teacher_view)(self.session))

    @database_sync_to_async
    def _own_session(self, user, session_id):
        if not user.is_authenticated or user.role != User.Role.TEACHER:
            return None
        return Session.objects.select_related('course').filter(pk=session_id, course__teacher=user).first()

    async def disconnect(self, code):
        if getattr(self, 'group', None):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def live_update(self, event):
        await self.send_json(event['data'])

    async def live_answered(self, event):
        # a class answers in a burst: recount once per burst, not once per answer
        if getattr(self, '_pending', False):
            return
        self._pending = True
        await asyncio.sleep(BATCH_SECONDS)
        self._pending = False
        await self.send_json(await database_sync_to_async(services.teacher_view)(self.session))


class StudentConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        found = await self._joined(self.scope.get('session'))
        if found is None:
            await self.close(code=4403)
            return
        self.session, self.enrollment = found
        self.group = services.student_group(self.session)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self.send_json(await database_sync_to_async(services.student_view)(self.session, self.enrollment))

    @database_sync_to_async
    def _joined(self, http_session):
        live = (http_session or {}).get('live') or {}
        session = Session.objects.select_related('course').filter(pk=live.get('session'), status=Session.Status.LIVE).first()
        enrollment = Enrollment.objects.select_related('student').filter(pk=live.get('enrollment'), course_id=getattr(session, 'course_id', None)).first()
        return (session, enrollment) if session and enrollment else None

    async def disconnect(self, code):
        if getattr(self, 'group', None):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def live_update(self, event):
        # the broadcast never carries anyone's own answer; the page keeps its own selection
        await self.send_json(event['data'])
