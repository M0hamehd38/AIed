from django.shortcuts import render


def landing(request):
    auth = request.GET.get('auth', '')
    return render(request, 'site/landing.html', {'auth_open': auth if auth in ('login', 'signup') else ''})
