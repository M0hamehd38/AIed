from django.shortcuts import redirect, render

from apps.accounts.views import home_for


def landing(request):
    # already signed in: the home page is the user's own panel
    if request.user.is_authenticated and 'auth' not in request.GET:
        return redirect(home_for(request.user))
    auth = request.GET.get('auth', '')
    return render(request, 'site/landing.html', {'auth_open': auth if auth in ('login', 'signup') else ''})
