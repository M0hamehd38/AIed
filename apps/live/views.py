"""Student phone pages: join with the session code and student number, then answer."""
from django.core.cache import cache
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.courses.models import Enrollment, Session

from . import services
from . import strings as S

FA_TO_EN = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
# per IP address: a whole class often shares one IP on university Wi-Fi, so the limit must allow
# for many typos, while still making a 6-digit code impossible to find by guessing
JOIN_TRIES, JOIN_WINDOW = 60, 10 * 60


def _ip(request):
    return request.META.get('REMOTE_ADDR', '')


def joined(request):
    """(session, enrollment) for this browser, or (None, None)."""
    live = request.session.get('live') or {}
    session = Session.objects.select_related('course').filter(pk=live.get('session')).first()
    if session is None:
        return None, None
    enrollment = Enrollment.objects.select_related('student').filter(pk=live.get('enrollment'), course=session.course).first()
    return (session, enrollment) if enrollment else (None, None)


def find_enrollment(course, number):
    number = number.translate(FA_TO_EN).strip()
    if not number:
        return None
    qs = Enrollment.objects.filter(course=course).select_related('student')
    return qs.filter(code=number).first() or qs.filter(student__student_no=number).first()


def join(request):
    ctx = {'code': request.GET.get('c', '')[:6]}
    if request.method == 'POST':
        key = f'live-join:{_ip(request)}'
        code = request.POST.get('code', '').translate(FA_TO_EN).strip()
        number = request.POST.get('number', '')
        ctx.update(code=code, number=number)
        if cache.get(key, 0) >= JOIN_TRIES:  # a 6-digit code must not be guessable by trying
            ctx['error'] = S.MSG['join_throttled']
            return render(request, 'live/join.html', ctx, status=429)
        session = Session.objects.select_related('course').filter(join_code=code, status=Session.Status.LIVE).first() if code else None
        enrollment = find_enrollment(session.course, number) if session else None
        if session is None or enrollment is None:
            cache.set(key, cache.get(key, 0) + 1, JOIN_WINDOW)
            ctx['error'] = S.MSG['join_bad_code'] if session is None else S.MSG['join_bad_student']
            return render(request, 'live/join.html', ctx, status=400)
        request.session.cycle_key()
        request.session['live'] = {'session': session.pk, 'enrollment': enrollment.pk}
        return redirect('live:student')
    session, _ = joined(request)
    if session and session.status == Session.Status.LIVE and not ctx['code']:
        return redirect('live:student')
    return render(request, 'live/join.html', ctx)


def student(request):
    session, enrollment = joined(request)
    if session is None:
        return redirect('live:join')
    return render(request, 'live/student.html', {'session': session, 'enrollment': enrollment,
                                                 'initial': services.student_view(session, enrollment)})


def state(request):
    session, enrollment = joined(request)
    if session is None:
        return JsonResponse({'live': False, 'question': None}, status=403)
    return JsonResponse(services.student_view(session, enrollment))


@require_POST
def answer(request):
    session, enrollment = joined(request)
    if session is None:
        return JsonResponse({'error': S.MSG['join_bad_code']}, status=403)
    try:
        option = int(request.POST.get('option', ''))
        services.answer(session, enrollment, option)
    except ValueError:
        return HttpResponseBadRequest()
    except services.LiveError as e:
        return JsonResponse({'error': str(e)}, status=409)
    services.answered(session)
    return JsonResponse(services.student_view(session, enrollment))


@require_POST
def leave(request):
    request.session.pop('live', None)
    return redirect('live:join')
