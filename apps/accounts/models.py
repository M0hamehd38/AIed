from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError('email is required')
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, role=User.Role.ADMIN)
        return self.create_user(email, password, **extra)


class User(AbstractUser):
    """Sign-in is by email. The role decides which part of the product a user sees."""

    class Role(models.TextChoices):
        TEACHER = 'teacher', 'استاد'
        STUDENT = 'student', 'دانشجو'
        ADMIN = 'admin', 'مدیر آموزش'

    username = None
    email = models.EmailField('ایمیل', unique=True)
    full_name = models.CharField('نام کامل', max_length=120)
    role = models.CharField('نقش', max_length=10, choices=Role.choices, default=Role.TEACHER)
    student_no = models.CharField('شماره‌ی دانشجویی', max_length=20, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']
    objects = UserManager()

    class Meta:
        verbose_name = 'کاربر'
        verbose_name_plural = 'کاربران'

    def __str__(self):
        return self.full_name or self.email

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_superuser
