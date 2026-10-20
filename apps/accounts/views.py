from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .forms import LoginForm, SignupForm
from .models import User

MAX_ATTEMPTS = 5
WINDOW = 10 * 60  # seconds


def _client_ip(request):
    return request.META.get('REMOTE_ADDR', '')


def _landing(request, status=200, **ctx):
    return render(request, 'site/landing.html', ctx, status=status)


def home_for(user):
    if user.role == User.Role.TEACHER:
        return 'panel:dashboard'
    if user.is_admin_role:
        return 'admin:index'
    return 'accounts:student_home'


@login_required
def home(request):
    return redirect(home_for(request.user))


def login_view(request):
    if request.method != 'POST':
        return redirect('/?auth=login')
    key = f'login-fail:{_client_ip(request)}:{request.POST.get("email", "").lower()[:120]}'
    form = LoginForm(request.POST, request=request)
    if cache.get(key, 0) >= MAX_ATTEMPTS:
        form.is_valid()
        form.errors.clear()
        form.add_error(None, 'تلاش‌های ناموفق زیاد بود. چند دقیقه‌ی دیگر دوباره امتحان کنید.')
        return _landing(request, status=429, auth_open='login', login_form=form)
    if not form.is_valid():
        cache.set(key, cache.get(key, 0) + 1, WINDOW)
        return _landing(request, status=400, auth_open='login', login_form=form)
    cache.delete(key)
    login(request, form.user)
    return redirect(home_for(form.user))


def signup_view(request):
    if request.method != 'POST':
        return redirect('/?auth=signup')
    form = SignupForm(request.POST)
    if not form.is_valid():
        return _landing(request, status=400, auth_open='signup', signup_form=form)
    user = form.save()
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return redirect(home_for(user))


@require_POST
def logout_view(request):
    logout(request)
    return redirect('/')


@login_required
def student_home(request):
    return render(request, 'accounts/student_home.html')
