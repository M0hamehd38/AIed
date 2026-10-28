from django.conf import settings
from django.db import models

CONCEPT_COLORS = ['#4169f5', '#8c62db', '#0e9fb5', '#c2477f', '#e08a17', '#13a67b']


class Course(models.Model):
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='courses_taught', verbose_name='استاد')
    title = models.CharField('نام درس', max_length=120)
    code = models.CharField('کد درس', max_length=20, blank=True)
    group = models.CharField('گروه', max_length=40, blank=True)
    term = models.CharField('ترم', max_length=40, default='پاییز ۱۴۰۵')
    schedule = models.CharField('زمان کلاس', max_length=80, blank=True)
    # loaded by seed_demo: the panel labels its numbers as sample data, never as real statistics
    is_demo = models.BooleanField('داده‌ی نمایشی', default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        verbose_name = 'درس'
        verbose_name_plural = 'درس‌ها'

    def __str__(self):
        return self.title


class Concept(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='concepts')
    title = models.CharField('مفهوم', max_length=120)
    order = models.PositiveSmallIntegerField(default=0)
    intro_session = models.PositiveSmallIntegerField('معرفی از جلسه', default=1)

    class Meta:
        ordering = ['order', 'id']
        unique_together = [('course', 'title')]

    def __str__(self):
        return self.title

    @property
    def color(self):
        return CONCEPT_COLORS[self.order % len(CONCEPT_COLORS)]


class Session(models.Model):
    class Status(models.TextChoices):
        PLANNED = 'planned', 'برنامه‌ریزی‌شده'
        LIVE = 'live', 'در حال برگزاری'
        CLOSED = 'closed', 'برگزارشده'

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sessions')
    number = models.PositiveSmallIntegerField('شماره‌ی جلسه')
    date = models.DateField('تاریخ', null=True, blank=True)
    topic = models.CharField('موضوع', max_length=160)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CLOSED)
    # live sessions only: students join with this code; it is cleared when the session ends
    join_code = models.CharField('کد ورود', max_length=6, null=True, blank=True, unique=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['number']
        unique_together = [('course', 'number')]

    def __str__(self):
        return f'{self.course} · جلسه {self.number}'


class Enrollment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='enrollments')
    code = models.CharField('کد در درس', max_length=12)

    class Meta:
        ordering = ['id']
        unique_together = [('course', 'student')]


class Question(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'پیش‌نویس'
        APPROVED = 'approved', 'تأییدشده'

    class Source(models.TextChoices):
        MANUAL = 'manual', 'استاد'
        AI_DRAFT = 'ai_draft', 'پیش‌نویس دستیار'

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='questions')
    number = models.PositiveIntegerField()
    text = models.TextField('متن سؤال')
    concepts = models.ManyToManyField(Concept, through='QuestionConcept', related_name='questions')
    planned_session = models.ForeignKey(Session, null=True, blank=True, on_delete=models.SET_NULL, related_name='planned_questions')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.APPROVED)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)

    class Meta:
        ordering = ['number']
        unique_together = [('course', 'number')]

    def __str__(self):
        return self.text[:60]


class QuestionConcept(models.Model):
    """Every question is tagged with one or more concepts; all mastery analytics rest on this."""
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE)

    class Meta:
        unique_together = [('question', 'concept')]


class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    order = models.PositiveSmallIntegerField()
    text = models.CharField(max_length=300)
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ['order']
        unique_together = [('question', 'order')]


class SessionQuestion(models.Model):
    """A question asked in a live session."""

    class State(models.TextChoices):
        PENDING = 'pending', 'در انتظار'
        OPEN = 'open', 'باز'
        PAUSED = 'paused', 'متوقف'
        CLOSED = 'closed', 'بسته'

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='asked')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='asked_in')
    state = models.CharField(max_length=10, choices=State.choices, default=State.CLOSED)
    # asked at the very end of class: kept out of participation rates
    late = models.BooleanField(default=False)
    opened_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('session', 'question')]


class Response(models.Model):
    session_question = models.ForeignKey(SessionQuestion, on_delete=models.CASCADE, related_name='responses')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='responses')
    option = models.ForeignKey(Option, on_delete=models.CASCADE)
    answered_at = models.DateTimeField(auto_now=True)  # a student may change the answer until the question closes

    class Meta:
        unique_together = [('session_question', 'student')]
