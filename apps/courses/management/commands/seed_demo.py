"""Load the demo courses (the same numbers as the prototype) for the demo teacher.

The teacher's password is never stored in the code: pass it in DEMO_TEACHER_PASSWORD.
"""
import json
import os
from datetime import datetime, time
from pathlib import Path

import jdatetime
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.courses.models import (Concept, Course, Enrollment, Option, Question, QuestionConcept, Response, Session,
                                 SessionQuestion)
from apps.insights.services import CourseData, sync_suggestions

SEED_FILE = Path(settings.BASE_DIR) / 'seed' / 'prototype_data.json'
TEACHER_EMAIL = 'golzari@classyar.ir'
TEACHER_NAME = 'دکتر شهرام گلزاری هرمزی'
JALALI_MONTHS = {'فروردین': 1, 'اردیبهشت': 2, 'خرداد': 3, 'تیر': 4, 'مرداد': 5, 'شهریور': 6,
                 'مهر': 7, 'آبان': 8, 'آذر': 9, 'دی': 10, 'بهمن': 11, 'اسفند': 12}
FA_TO_EN = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
# decisions taken before the demo starts, as in the prototype
PAST_AUDIT = [('CS101', 'approve', 'مرور شرط‌های ترکیبی با جدول درستی', '۱۹ مهر', '10:42'),
              ('CS101', 'reject', 'افزودن تکلیف اضافه برای کل کلاس', '۱۲ مهر', '09:15')]


def jalali(label, year=1405):
    """'۱۹ مهر' → a Gregorian date."""
    day, month = label.split()
    return jdatetime.date(year, JALALI_MONTHS[month], int(day.translate(FA_TO_EN))).togregorian()


class Command(BaseCommand):
    help = 'Load the demo courses for the demo teacher (needs DEMO_TEACHER_PASSWORD).'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help="Delete the demo teacher's courses first.")

    def handle(self, *args, reset=False, **opts):
        password = os.environ.get('DEMO_TEACHER_PASSWORD')
        if not password:
            raise CommandError('DEMO_TEACHER_PASSWORD is not set.')
        data = json.loads(SEED_FILE.read_text(encoding='utf-8'))
        with transaction.atomic():
            teacher, created = User.objects.get_or_create(
                email=TEACHER_EMAIL, defaults={'full_name': TEACHER_NAME, 'role': User.Role.TEACHER})
            teacher.set_password(password)
            teacher.save()
            if Course.objects.filter(teacher=teacher).exists():
                if not reset:
                    self.stdout.write('Demo data already loaded (use --reset to reload).')
                    return
                Course.objects.filter(teacher=teacher).delete()
                User.objects.filter(email__endswith='@demo.classyar.ir', role=User.Role.STUDENT).delete()
            for c in data:
                self.load_course(teacher, c)
            tz = timezone.get_current_timezone()
            for code, action, summary, day, hm in PAST_AUDIT:
                course = Course.objects.get(teacher=teacher, code=code)
                entry = AuditLog.objects.create(actor=teacher, course=course, action=action, object_type='Suggestion', summary=summary)
                h, m = map(int, hm.split(':'))
                AuditLog.objects.filter(pk=entry.pk).update(at=timezone.make_aware(datetime.combine(jalali(day), time(h, m)), tz))
        for course in Course.objects.filter(teacher=teacher):
            sync_suggestions(CourseData(course))
        self.stdout.write(self.style.SUCCESS(
            f'Loaded {len(data)} courses for {TEACHER_EMAIL}: '
            + ', '.join(f"{c['code']} ({len(c['students'])} students, {len(c['responses'])} responses)" for c in data)))

    def load_course(self, teacher, c):
        course = Course.objects.create(teacher=teacher, title=c['title'], code=c['code'], group=c['group'],
                                       term=c['term'], schedule=c['schedule'], is_demo=True)
        concepts = [Concept.objects.create(course=course, title=x['title'], order=i, intro_session=x['from_session'])
                    for i, x in enumerate(c['concepts'])]
        sessions = {s['number']: Session.objects.create(course=course, number=s['number'], date=jalali(s['date']),
                                                        topic=s['topic'], status=Session.Status.CLOSED)
                    for s in c['sessions']}
        students = []
        for s in c['students']:
            code = f"{s['index'] + 1:02d}"
            user = User.objects.create_user(f"{c['code'].lower()}-{code}@demo.classyar.ir", None, full_name=s['name'],
                                            role=User.Role.STUDENT, student_no=f"1405{c['code'][-3:]}{code}")
            Enrollment.objects.create(course=course, student=user, code=code)
            students.append(user)
        asked, options = {}, {}
        for q in c['questions']:
            question = Question.objects.create(course=course, number=q['number'], text=q['text'],
                                               planned_session=sessions.get(q['session']))
            QuestionConcept.objects.bulk_create([QuestionConcept(question=question, concept=concepts[i]) for i in q['concepts']])
            options[q['number']] = Option.objects.bulk_create(
                [Option(question=question, order=i, text=t, is_correct=i == q['correct']) for i, t in enumerate(q['options'])])
            if q['asked']:
                asked[q['number']] = SessionQuestion.objects.create(session=sessions[q['session']], question=question,
                                                                    late=q['late'], state=SessionQuestion.State.CLOSED)
        Response.objects.bulk_create([Response(session_question=asked[qnum], student=students[sid], option=options[qnum][opt])
                                      for sid, qnum, _session, opt in c['responses']])
        return course
