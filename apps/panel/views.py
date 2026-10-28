"""Teacher panel. Every queryset is scoped to the signed-in teacher's own courses."""
import csv
import io
import json
import re
from functools import wraps

import jdatetime
import qrcode
import qrcode.image.svg
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Func, IntegerField, Max, OuterRef, Subquery
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.audio import services as audio_service
from apps.audio import stt
from apps.audio import strings as AS
from apps.audio.models import Transcript
from apps.audit.models import AuditLog, record
from apps.courses.models import (Concept, Course, Enrollment, Option, Question, QuestionConcept, Response, Session,
                                 SessionQuestion)
from apps.insights import services
from apps.insights.models import Suggestion
from apps.live import services as live_service
from apps.live import strings as LS
from lib.analytics import Stat, confidence, stat, wilson
from lib.analytics.fmt import fa, js_round, pct

from . import dashboard as dashboard_view
from . import strings as S
from .charts import line_chart

FA_TO_EN = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


# ---------------------------------------------------------------- plumbing
def teacher_required(view):
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.user.role != User.Role.TEACHER:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapper


def my_courses(request):
    return Course.objects.filter(teacher=request.user)


def active_course(request):
    courses = my_courses(request)
    course = courses.filter(pk=request.session.get('course_id')).first() or courses.first()
    if course and request.session.get('course_id') != course.pk:
        request.session['course_id'] = course.pk  # only on change: writing would re-save the session every request
    return course


def panel_context(request, view, data=None, **extra):
    course = data.course if data else active_course(request)
    pending = Suggestion.objects.filter(course=course, status=Suggestion.Status.PENDING).count() if course else 0
    sessions = data.sessions if data else (list(course.sessions.all()) if course else [])
    ctx = {
        'view': view, 'courses': my_courses(request), 'course': course, 'data': data,
        'th': data.th if data else services.thresholds(services.course_settings(course)) if course else None,
        'cfg': data.settings if data else (services.course_settings(course) if course else services.DEFAULTS),
        'nav': [(k, v) for k, v in S.NAV.items()], 'pending_count': pending,
        'cur_session': sessions[-1] if sessions else None, 'T': S,
        'page_title': S.NAV.get(view, ''), 'page_sub': S.SUB.get(view, ''),
        'initial': request.user.full_name.replace('دکتر', '').strip()[:1],
        'live_now': Session.objects.filter(course=course, status=Session.Status.LIVE).first() if course else None,
    }
    ctx.update(extra)
    return ctx


def with_course(view):
    """Load the active course's data; without any course, send the teacher to create one."""
    @teacher_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        course = active_course(request)
        if course is None:
            return render(request, 'panel/no_course.html', panel_context(request, 'courses'))
        return view(request, services.CourseData(course), *args, **kwargs)
    return wrapper


def back(request, default='panel:dashboard'):
    nxt = request.POST.get('next') or request.GET.get('next')
    if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}, require_https=request.is_secure()):
        return redirect(nxt)
    return redirect(default)


def point(st, minimum):
    return {'v': st.ok / st.n, 'n': st.n, 'ok': st.n >= minimum} if st.n else None


def stat_of(cell):
    return Stat(cell['ok'], cell['n'])


def session_stat(data, number):
    return stat(data.a.in_session(number))


def participation_series(data):
    ps = data.a.participation_by_session()
    return [None if p is None else {'v': p, 'n': len(data.a.in_session(i + 1)), 'ok': True}
            for i, p in enumerate(ps)]


# ---------------------------------------------------------------- dashboard
@with_course
def dashboard(request, data):
    if not data.responses:
        return render(request, 'panel/empty_course.html', panel_context(request, 'dashboard', data, **greeting(request, data)))
    services.sync_suggestions(data)
    ctx = panel_context(request, 'dashboard', data, **greeting(request, data), d=dashboard_view.build(data))
    return render(request, 'panel/dashboard.html', ctx)


def concept_trend(data):
    """Cumulative mastery per concept up to the last session, with the change since the session before."""
    a = data.a
    last = a.last_session()
    out = []
    for c in a.d.concepts:
        cur, before = a.up_to(c.id, last), a.up_to(c.id, last - 1)
        if cur.n:
            m = cur.ok / cur.n
            d = js_round((m - before.ok / before.n) * 100) if before.n else 0
            out.append({'c': c, 'm': m, 'n': cur.n, 'd': d, 'abs_d': abs(d)})
    return out


def greeting(request, data):
    cur = data.sessions[-1] if data.sessions else None
    sub = f'{data.course.title} · {data.course.term} · ' + (f'آخرین جلسه {jdate_label(cur.date)}' if cur else 'بدون جلسه')
    return {'page_title': None, 'page_sub': sub + ' — نگاهی به وضعیت کلاس شما'}


def jdate_label(d):
    if not d:
        return ''
    j = jdatetime.date.fromgregorian(date=d)
    return f'{fa(j.day)} {jdatetime.date.j_months_fa[j.month - 1]}'


# ---------------------------------------------------------------- students
STUDENT_SORTS = [('mastery:1', 'کمترین تسلط'), ('mastery:-1', 'بیشترین تسلط'), ('part:1', 'کمترین مشارکت'), ('name:1', 'نام (الفبایی)')]


@with_course
def students(request, data):
    a, th = data.a, data.th
    rows = []
    for s in data.students:
        x = a.student(s.index)
        rows.append({'s': s, 'a': x, 'name': data.student_name(s),
                     'mastery': x['total'].ok / x['total'].n if x['total'].n else 0,
                     'enough': x['total'].n >= th.min_student})
    q = request.GET.get('q', '').strip()
    f = request.GET.get('f', 'all')
    sort = request.GET.get('sort', 'mastery:1')
    shown = rows
    if q:
        qn = q.translate(FA_TO_EN)
        shown = [r for r in shown if q in r['name'] or qn in r['s'].code]
    if f == 'attention':
        shown = [r for r in shown if r['a']['attention']]
    elif f == 'stable':
        shown = [r for r in shown if not r['a']['attention']]
    concept = None
    try:
        ci = int(request.GET.get('c', ''))
    except ValueError:
        ci = None
    if ci is not None and 0 <= ci < len(data.concepts):
        # students with enough answers on this concept and mastery below green, weakest first
        concept = data.concepts[ci]

        def on_concept(r):
            p = r['a']['per'][ci]
            return p['n'] >= th.min_student and p['ok'] / p['n'] < th.green
        shown = [dict(r, cm=r['a']['per'][ci]['ok'] / r['a']['per'][ci]['n']) for r in shown if on_concept(r)]
    key, _, direction = sort.partition(':')
    keyf = {'name': lambda r: r['name'], 'mastery': lambda r: r['mastery'], 'part': lambda r: r['a']['part']}.get(key, lambda r: r['mastery'])
    shown = sorted(shown, key=keyf, reverse=direction == '-1')
    if concept:
        shown.sort(key=lambda r: r['cm'])

    ctx = panel_context(request, 'students', data, rows=shown, total=len(rows), q=q, f=f, sort=sort, sorts=STUDENT_SORTS,
                        concept=concept, ci=ci if concept else None)
    if data.responses and rows:
        n = len(rows)
        lvl = {'g': 0, 'o': 0, 'r': 0, 'na': 0}
        for r in rows:
            lvl['na' if r['a']['total'].n < th.min_student else a.level(r['mastery'])] += 1
        bands = [('۹۰٪ و بیشتر', lambda p: p >= .9), ('۷۵ تا ۸۹٪', lambda p: .75 <= p < .9),
                 ('۶۰ تا ۷۴٪', lambda p: .6 <= p < .75), ('کمتر از ۶۰٪', lambda p: p < .6)]
        part_colors = ['var(--blue)', '#6f8ff7', '#a3b6fb', 'var(--orange)']
        need = [r for r in rows if r['a']['attention']]
        cm = sorted((x for x in a.concept_mastery() if x['n']), key=lambda x: x['ok'] / x['n'])
        stable_series = []
        for se in data.sessions:
            if a.in_session(se.number):
                stable = sum(1 for s in data.students if not a.student(s.index, se.number)['attention'])
                stable_series.append({'v': stable / n, 'n': n, 'ok': True})
            else:
                stable_series.append(None)
        ctx.update(
            chart=line_chart([
                {'name': 'تسلط کلاس', 'color': '#8c62db', 'points': [point(session_stat(data, s.number), th.min_class) for s in data.sessions]},
                {'name': 'نرخ پاسخ', 'color': '#4169f5', 'points': participation_series(data)},
                {'name': 'دانشجویان پایدار', 'color': '#13a67b', 'points': stable_series},
            ], data.sessions, th, h=240, area=True, threshold=False, label='وضعیت کلاس در طول ترم'),
            mastery_bars=[(f'تسلط مناسب (≥ {pct(th.green)})', lvl['g'], 'var(--green)'), ('نیازمند تمرین', lvl['o'], 'var(--orange)'),
                          (f'دشوار (< {pct(th.orange)})', lvl['r'], 'var(--red)'), ('داده کافی نیست', lvl['na'], '#b8c1d6')],
            part_bars=[(label, sum(1 for r in rows if test(r['a']['part'])), part_colors[i]) for i, (label, test) in enumerate(bands)],
            need_count=len(need),
            need_reason='افت مشارکت' if sum(1 for r in need if any(x.startswith('مشارکت') for x in r['a']['reasons'])) > len(need) / 2 else 'دشواری مفهوم',
            weakest=cm[0] if cm else None, class_size=n,
        )
    return render(request, 'panel/students.html', ctx)


def enrollment_ref(data, pk):
    ref = next((s for s in data.students if s.pk == pk), None)
    if ref is None:
        raise Http404
    return ref


@with_course
def student_profile(request, data, pk):
    a, th = data.a, data.th
    s = enrollment_ref(data, pk)
    x = a.student(s.index)
    m = x['total'].ok / x['total'].n if x['total'].n else 0
    series = [{'name': p['c'].title, 'color': data.concepts[p['c'].id].color,
               'points': [point(stat([r for r in a.for_concept(p['c'].id, x['rs']) if r.session <= se.number]), th.min_student)
                          for se in data.sessions]} for p in x['per']]
    dates = {se.number: jdate_label(se.date) for se in data.sessions}
    history = [{'r': r, 'q_text': data.question_by_number[r.qid].text, 'date': dates.get(r.session, ''),
                'answer': data.qrefs[r.qid].options[r.opt]}
               for r in reversed(x['rs'])]
    per = [{**p, 'm': p['ok'] / p['n'] if p['n'] else 0, 'enough': p['n'] >= th.min_student} for p in x['per']]
    ctx = panel_context(request, 'students', data, page_title='نمایه‌ی دانشجو', s=s, name=data.student_name(s), x=x, m=m,
                        per=per, history=history, enough=x['total'].n >= th.min_student,
                        conf=confidence(x['total'].ok, x['total'].n, th.min_student),
                        chart=line_chart(series, data.sessions, th, h=220))
    return render(request, 'panel/student_profile.html', ctx)


@with_course
def student_export(request, data, pk):
    s = enrollment_ref(data, pk)
    rs = [{'session': r.session, 'question': data.question_by_number[r.qid].text,
           'answer': data.qrefs[r.qid].options[r.opt], 'correct': r.ok}
          for r in data.a.of_student(s.index)]
    record(request.user, 'export_student', data.course, f'خروجی داده‌های دانشجو {s.code}', course=data.course)
    resp = JsonResponse({'code': s.code, 'name': s.name, 'course': data.course.title, 'responses': rs},
                        json_dumps_params={'ensure_ascii': False, 'indent': 2})
    resp['Content-Disposition'] = f'attachment; filename="student-{s.code}.json"'
    return resp


# ---------------------------------------------------------------- analytics
@with_course
def analytics(request, data):
    a, th = data.a, data.th
    if not data.responses:
        return render(request, 'panel/empty_course.html', panel_context(request, 'analytics', data))
    last = a.last_session()
    cm = []
    for x in a.concept_mastery():
        if not x['n']:
            continue
        lo, hi = wilson(x['ok'], x['n'])
        cm.append({**x, 'm': x['ok'] / x['n'], 'lo': lo * 100, 'w': (hi - lo) * 100,
                   'conf': confidence(x['ok'], x['n'], th.min_class)})
    ordered = sorted(cm, key=lambda x: x['m'])
    items = a.items()
    for it in items:
        it['concept_titles'] = [data.concepts[i].title for i in it['q'].concepts]
        it['diff'] = ('آسان', 'green') if it['p'] >= .8 else ('متوسط', 'blue') if it['p'] >= .4 else ('دشوار', 'red')
        d = it['D']
        it['disc'] = None if d is None else (('خوب', 'green') if d >= .3 else ('قابل قبول', 'blue') if d >= .2 else ('ضعیف', 'orange'))
        it['D_txt'] = None if d is None else fa(f'{d:.2f}')
        it['distractor_text'] = it['q'].options[it['distractor']['i']] if it['distractor'] else ''
        it['enough'] = it['n'] >= th.min_class
    series = [{'name': c.title, 'color': c.color,
               'points': [point(stat_of(a.cell(i, s.number)), th.min_class) for s in data.sessions]}
              for i, c in enumerate(data.concepts)]
    services.sync_suggestions(data)
    ctx = panel_context(
        request, 'analytics', data, cm=cm, trend=concept_trend(data), alerts=a.alerts(),
        pending=list(Suggestion.objects.filter(course=data.course, status=Suggestion.Status.PENDING)), last=last, weakest=ordered[0] if ordered else None, best=ordered[-1] if ordered else None,
        items=items, chart=line_chart(series, data.sessions, th),
        mis_items=[it for it in items if it['enough'] and it['distractor'] and it['distractor']['share'] >= 0.25],
        weak_items=[it for it in items if it['enough'] and it['D'] is not None and it['D'] < 0.2],
    )
    return render(request, 'panel/analytics.html', ctx)


# ---------------------------------------------------------------- suggestions
@with_course
def suggestions(request, data):
    if data.responses:
        services.sync_suggestions(data)
    qs = Suggestion.objects.filter(course=data.course)
    audit = [{'e': e, 'label': S.AUDIT_ACTIONS.get(e.action, (e.action, 'gray'))}
             for e in AuditLog.objects.filter(course=data.course).select_related('actor')[:50]]
    ctx = panel_context(request, 'suggestions', data, pending=qs.filter(status=Suggestion.Status.PENDING),
                        done=qs.exclude(status=Suggestion.Status.PENDING), audit=audit)
    return render(request, 'panel/suggestions.html', ctx)


def my_suggestion(request, pk):
    return get_object_or_404(Suggestion, pk=pk, course__teacher=request.user)


@teacher_required
@require_POST
def suggestion_decide(request, pk):
    s = my_suggestion(request, pk)
    decision = request.POST.get('decision')
    if decision not in (Suggestion.Status.APPROVED, Suggestion.Status.REJECTED) or s.status != Suggestion.Status.PENDING:
        return HttpResponseBadRequest()
    services.decide(s, decision, request.user)
    messages.success(request, S.MSG[decision])
    return back(request, 'panel:suggestions')


@teacher_required
@require_POST
def suggestion_edit(request, pk):
    s = my_suggestion(request, pk)
    title = request.POST.get('title', '').strip()[:200] or s.title
    action = request.POST.get('action', '').strip() or s.action
    services.edit(s, title, action, request.user)
    messages.success(request, S.MSG['edited'])
    return redirect('panel:suggestions')


@teacher_required
@require_POST
def suggestion_draft_question(request, pk):
    s = my_suggestion(request, pk)
    if s.status != Suggestion.Status.APPROVED or s.output != 'question' or s.drafted:
        return HttpResponseBadRequest()
    course = s.course
    src = get_object_or_404(Question, course=course, number=s.evidence_ref.get('q'))
    with transaction.atomic():
        number = (course.questions.aggregate(m=Max('number'))['m'] or 0) + 1
        q = Question.objects.create(course=course, number=number, text=f'(پیش‌نویس، مشابه سؤال {fa(src.number)}) {src.text}',
                                    planned_session=course.sessions.last(), status=Question.Status.DRAFT,
                                    source=Question.Source.AI_DRAFT)
        QuestionConcept.objects.bulk_create([QuestionConcept(question=q, concept=c) for c in src.concepts.all()])
        Option.objects.bulk_create([Option(question=q, order=o.order, text=o.text, is_correct=o.is_correct) for o in src.options.all()])
        s.drafted = True
        s.save(update_fields=['drafted'])
        record(request.user, 'draft_question', q, f'سؤال {fa(number)} برای بازبینی', course=course)
    messages.success(request, S.MSG['drafted'])
    return redirect('panel:suggestions')


# ---------------------------------------------------------------- evidence (partial for the dialog)
@with_course
def evidence(request, data):
    a, th = data.a, data.th
    try:
        ev = json.loads(request.GET.get('ev', ''))
        kind = ev['type']
    except (ValueError, KeyError, TypeError):
        return HttpResponseBadRequest()
    n_concepts = len(data.concepts)
    ctx = panel_context(request, 'evidence', data)

    def question_block(qnum, session=None):
        q = data.qrefs.get(qnum)
        if q is None:
            raise Http404
        rs = [r for r in a.of_question(qnum) if session is None or r.session == session]
        n = len(rs)
        ok = sum(1 for r in rs if r.ok)
        opts = [{'text': o, 'correct': i == q.correct, 'c': sum(1 for r in rs if r.opt == i)} for i, o in enumerate(q.options)]
        for o in opts:
            o['share'] = o['c'] / n if n else 0
        return {'q': q, 'text': data.question_by_number[qnum].text, 'n': n, 'n_label': f'n={fa(n)}', 'opts': opts,
                'conf': confidence(ok, n, th.min_class) if n else None,
                'concept_titles': [data.concepts[i].title for i in q.concepts]}

    if kind == 'cell':
        c, s = int(ev.get('c', -1)), int(ev.get('s', -1))
        if not 0 <= c < n_concepts:
            raise Http404
        cl = a.cell(c, s)
        lo, hi = wilson(cl['ok'], cl['n'])
        # the same concept across every session, so one cell is read in context
        trend = [point(stat_of(a.cell(c, x.number)), th.min_class) for x in data.sessions]
        ctx.update(title=f'شواهد: {data.concepts[c].title} · جلسه‌ی {fa(s)}', cell=cl, enough=cl['n'] >= th.min_class,
                   m=cl['ok'] / cl['n'] if cl['n'] else 0, lo=lo, hi=hi, blocks=[question_block(q, s) for q in cl['qs']],
                   ci=c, concept=data.concepts[c],
                   trend=line_chart([{'name': f'تسلط کلاس در «{data.concepts[c].title}»', 'color': 'var(--green)', 'points': trend}],
                                    data.sessions, th, h=170, w=560, area=False, threshold=True,
                                    label=f'روند تسلط کلاس در مفهوم {data.concepts[c].title} در جلسات', table=True)
                   if sum(1 for t in trend if t) >= 2 else None)
    elif kind == 'concept':
        c = int(ev.get('c', -1))
        if not 0 <= c < n_concepts:
            raise Http404
        qs = list(dict.fromkeys(r.qid for r in a.for_concept(c)))
        ctx.update(title=f'شواهد: {data.concepts[c].title}', blocks=[question_block(q) for q in qs])
    elif kind == 'question':
        q = int(ev.get('q', -1))
        ctx.update(title=f'شواهد سؤال {fa(q)}', blocks=[question_block(q)])
    elif kind == 'participation':
        ps = a.participation_by_session()
        ctx.update(title='شواهد: نرخ پاسخ در هر جلسه', participation=[(s, ps[i]) for i, s in enumerate(data.sessions)],
                   class_size=len(data.students))
    else:
        return HttpResponseBadRequest()
    ctx['kind'] = kind
    return render(request, 'panel/_evidence.html', ctx)


# ---------------------------------------------------------------- live & audio (phase 2 and 3)
def question_bank(request, data, approved_only=False):
    """The bank by topic: one entry per concept with its counts, and the questions of the chosen concept only."""
    questions = [q for q in data.questions if not approved_only or q.status == Question.Status.APPROVED]
    topics = []
    for i, c in enumerate(data.concepts):
        qs = [q for q in questions if i in data.qrefs[q.number].concepts]
        topics.append({'c': c, 'index': i, 'qs': qs, 'count': len(qs),
                       'unasked': sum(1 for q in qs if not data.qrefs[q.number].asked),
                       'drafts': sum(1 for q in qs if q.status == Question.Status.DRAFT)})
    chosen = next((t for t in topics if str(t['c'].pk) == request.GET.get('topic')), None)
    rows = []
    if chosen:
        for q in chosen['qs']:
            ref = data.qrefs[q.number]
            rows.append({'q': q, 'ref': ref, 'asked_label': f'پرسیده‌شده ج{fa(ref.session)}',
                         'concepts': [data.concepts[i].title for i in ref.concepts]})
    return {'topics': topics, 'topic': chosen, 'rows': rows, 'total': len(questions)}


@with_course
def live(request, data):
    bank = question_bank(request, data, True)
    session = live_service.live_session(data.course)
    ctx = panel_context(request, 'live', data, bank=bank, live=session,
                        state=live_service.teacher_view(session) if session else None,
                        join_url=request.build_absolute_uri(reverse('live:join')))
    return render(request, 'panel/live.html', ctx)


def my_live_session(request):
    course = active_course(request)
    session = live_service.live_session(course) if course else None
    if session is None:
        raise Http404
    return session


@with_course
@require_POST
def live_start(request, data):
    try:
        session = live_service.start(data.course, request.user)
    except live_service.LiveError as e:
        messages.error(request, str(e))
        return redirect('panel:live')
    messages.success(request, LS.MSG['started'].format(n=fa(session.number), code=session.join_code))
    return redirect('panel:live')


@teacher_required
@require_POST
def live_end(request):
    session = my_live_session(request)
    n = live_service.end(session, request.user)
    messages.success(request, LS.MSG['ended'].format(n=fa(n)))
    return redirect('panel:live')


@teacher_required
@require_POST
def live_ask(request):
    session = my_live_session(request)
    question = get_object_or_404(Question, pk=request.POST.get('question'), course=session.course, status=Question.Status.APPROVED)
    live_service.ask(session, question, late=request.POST.get('late') == '1')
    live_service.broadcast(session)
    return JsonResponse(live_service.teacher_view(session))


@teacher_required
@require_POST
def live_control(request):
    session = my_live_session(request)
    state = request.POST.get('state')
    if state not in (SessionQuestion.State.OPEN, SessionQuestion.State.PAUSED, SessionQuestion.State.CLOSED):
        return HttpResponseBadRequest()
    try:
        live_service.set_state(session, state)
    except live_service.LiveError as e:
        return JsonResponse({'error': str(e)}, status=409)
    live_service.broadcast(session)
    return JsonResponse(live_service.teacher_view(session))


@teacher_required
def live_state(request):
    """Polling fallback for when the WebSocket is down."""
    return JsonResponse(live_service.teacher_view(my_live_session(request)))


@teacher_required
def live_qr(request):
    session = my_live_session(request)
    url = request.build_absolute_uri(reverse('live:join')) + f'?c={session.join_code}'
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    resp = HttpResponse(buf.getvalue(), content_type='image/svg+xml')
    resp['Cache-Control'] = 'no-store'
    return resp


@with_course
def audio(request, data):
    audio_service.purge_expired()  # retention is enforced on every visit too, not only by the hourly job
    course = data.course
    session = audio_service.target_session(course)
    lines = []
    if session:
        rows = Transcript.objects.filter(session=session).prefetch_related('signals').order_by('-created_at')[:200]
        lines = [audio_service.line_json(t, [x.kind for x in t.signals.all()]) for t in reversed(rows)]
    ctx = panel_context(request, 'audio', data, consent=audio_service.consent_given(course), target=session,
                        lines=lines, counts=audio_service.counts(session) if session else {},
                        signals=AS.SIGNALS, stt_ready=stt.configured(),
                        signals_json=json.dumps({k: [label, cls] for k, label, cls in AS.SIGNALS}, ensure_ascii=False),
                        consent_text=AS.CONSENT_TEXT.format(days=fa(data.settings['retention_days'])))
    return render(request, 'panel/audio.html', ctx)


@with_course
@require_POST
def audio_consent(request, data):
    if request.POST.get('announced') != 'on':
        messages.error(request, AS.MSG['consent_announce'])
    else:
        audio_service.give_consent(data.course, request.user)
        messages.success(request, AS.MSG['consent_saved'])
    return redirect('panel:audio')


AUDIO_TYPES = ('audio/webm', 'audio/ogg', 'audio/mp4', 'audio/mpeg', 'audio/wav', 'audio/x-wav')
MAX_CHUNK = 2 * 1024 * 1024


@with_course
@require_POST
def audio_chunk(request, data):
    """One short recording from the teacher's browser. It is read into memory, sent to the speech-to-text
    service and dropped: no audio is ever written to disk or the database."""
    course = data.course
    if not audio_service.consent_given(course):
        return JsonResponse({'error': AS.MSG['consent_needed']}, status=403)
    session = audio_service.target_session(course)
    if session is None:
        return JsonResponse({'error': AS.MSG['no_session']}, status=409)
    content_type = request.content_type or ''
    if not content_type.startswith(AUDIO_TYPES):
        return JsonResponse({'error': AS.MSG['bad_audio']}, status=415)
    if int(request.META.get('CONTENT_LENGTH') or 0) > MAX_CHUNK:
        return JsonResponse({'error': AS.MSG['bad_audio']}, status=413)
    audio_bytes = request.body
    try:
        text = stt.transcribe(audio_bytes, content_type)
    except stt.STTUnavailable:
        return JsonResponse({'error': AS.MSG['stt_down']}, status=503)
    finally:
        del audio_bytes
    if not text:
        return JsonResponse({'line': None, 'counts': audio_service.counts(session)})
    line, kinds = audio_service.add_line(session, text, data.settings['retention_days'])
    return JsonResponse({'line': audio_service.line_json(line, kinds), 'counts': audio_service.counts(session)})


# ---------------------------------------------------------------- courses
def course_cards(request, active):
    """All of the teacher's courses with their counts, in one query (each count is a subquery, so joins don't multiply)."""
    def count(model, **filters):
        q = model.objects.filter(**filters).order_by().values('pk')
        return Subquery(q.annotate(n=Func(F('pk'), function='COUNT')).values('n')[:1], output_field=IntegerField())
    courses = my_courses(request).annotate(
        n_students=count(Enrollment, course=OuterRef('pk')), n_sessions=count(Session, course=OuterRef('pk')),
        n_questions=count(Question, course=OuterRef('pk')),
        n_responses=count(Response, session_question__session__course=OuterRef('pk')),
        n_correct=count(Response, session_question__session__course=OuterRef('pk'), option__is_correct=True))
    return [{'c': c, 'active': active and c.pk == active.pk, 'students': c.n_students, 'sessions': c.n_sessions,
             'questions': c.n_questions, 'mastery': c.n_correct / c.n_responses if c.n_responses else None} for c in courses]


@with_course
def courses(request, data):
    a = data.a
    sessions = []
    for se in data.sessions:
        sessions.append({'s': se, 'date': jdate_label(se.date), 'year': fa(jdatetime.date.fromgregorian(date=se.date).year) if se.date else '',
                         'questions': sum(1 for q in a.d.questions if q.asked and q.session == se.number),
                         'responses': len(a.in_session(se.number))})
    ctx = panel_context(request, 'courses', data, cards=course_cards(request, data.course), sessions=sessions,
                        bank=question_bank(request, data), colors=['#4169f5', '#8c62db', '#0e9fb5', '#c2477f', '#e08a17', '#13a67b'])
    return render(request, 'panel/courses.html', ctx)


@teacher_required
@require_POST
def course_switch(request):
    course = get_object_or_404(my_courses(request), pk=request.POST.get('course'))
    request.session['course_id'] = course.pk
    messages.info(request, S.MSG['course_active'].format(title=course.title))
    return back(request)


@teacher_required
@require_POST
def course_create(request):
    title = request.POST.get('title', '').strip()[:120]
    concepts = [x.strip() for x in re.split(r'[\n،,]', request.POST.get('concepts', '')) if x.strip()]
    if not title or not concepts:
        messages.error(request, S.MSG['course_bad'])
        return redirect('panel:courses')
    with transaction.atomic():
        course = Course.objects.create(teacher=request.user, title=title, code=request.POST.get('code', '').strip()[:20],
                                       group=request.POST.get('group', '').strip()[:40],
                                       term=request.POST.get('term', '').strip()[:40] or 'پاییز ۱۴۰۵',
                                       schedule=request.POST.get('schedule', '').strip()[:80])
        for i, t in enumerate(dict.fromkeys(concepts)):
            Concept.objects.create(course=course, title=t[:120], order=i, intro_session=1)
        record(request.user, 'create_course', course, f'ایجاد درس «{title}»', course=course)
    request.session['course_id'] = course.pk
    messages.success(request, S.MSG['course_created'].format(title=title))
    return redirect('panel:courses')


@with_course
@require_POST
def concept_add(request, data):
    title = request.POST.get('title', '').strip()[:120]
    course = data.course
    if title and not course.concepts.filter(title=title).exists():
        last = data.sessions[-1].number if data.sessions else 0
        Concept.objects.create(course=course, title=title, order=len(data.concepts), intro_session=last + 1)
        messages.success(request, S.MSG['concept_added'])
    return redirect('panel:courses')


def parse_jalali(text):
    m = re.fullmatch(r'\s*(\d{4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*', text.translate(FA_TO_EN))
    if not m:
        return None
    try:
        return jdatetime.date(*map(int, m.groups())).togregorian()
    except ValueError:
        return None


@with_course
@require_POST
def session_add(request, data):
    date = parse_jalali(request.POST.get('date', ''))
    topic = request.POST.get('topic', '').strip()[:160]
    if not date or not topic:
        messages.error(request, S.MSG['session_bad'])
        return redirect('panel:courses')
    n = (data.sessions[-1].number if data.sessions else 0) + 1
    Session.objects.create(course=data.course, number=n, date=date, topic=topic, status=Session.Status.PLANNED)
    messages.success(request, S.MSG['session_added'].format(n=fa(n)))
    return redirect('panel:courses')


@with_course
@require_POST
def question_add(request, data):
    course = data.course
    text = request.POST.get('text', '').strip()
    options = [request.POST.get(f'option{i}', '').strip()[:300] for i in range(4)]
    try:
        correct = int(request.POST.get('correct', '0'))
    except ValueError:
        correct = -1
    concept_ids = request.POST.getlist('concepts')
    concepts = list(course.concepts.filter(pk__in=[c for c in concept_ids if c.isdigit()]))
    if not text or any(not o for o in options) or not 0 <= correct < 4 or not concepts:
        messages.error(request, S.MSG['question_bad'])
        return redirect('panel:courses')
    with transaction.atomic():
        number = (course.questions.aggregate(m=Max('number'))['m'] or 0) + 1
        q = Question.objects.create(course=course, number=number, text=text, planned_session=course.sessions.last())
        QuestionConcept.objects.bulk_create([QuestionConcept(question=q, concept=c) for c in concepts])
        Option.objects.bulk_create([Option(question=q, order=i, text=o, is_correct=i == correct) for i, o in enumerate(options)])
    messages.success(request, S.MSG['question_added'])
    return redirect('panel:courses')


@teacher_required
@require_POST
def question_approve(request, pk):
    q = get_object_or_404(Question, pk=pk, course__teacher=request.user)
    q.status = Question.Status.APPROVED
    q.save(update_fields=['status'])
    record(request.user, 'approve_question', q, f'تأیید سؤال {fa(q.number)}', course=q.course)
    messages.success(request, S.MSG['question_approved'])
    return redirect('panel:courses')


@with_course
@require_POST
def students_import(request, data):
    """CSV with «code, name» columns. Each row becomes (or reuses) a student account and an enrollment."""
    course = data.course
    upload = request.FILES.get('csv')
    try:
        text = upload.read(512 * 1024).decode('utf-8-sig') if upload else ''
    except UnicodeDecodeError:
        text = ''
    rows = []
    for row in csv.reader(io.StringIO(text.replace('،', ',').replace(';', ',').replace('\t', ','))):
        cells = [c.strip() for c in row]
        if len(cells) >= 2 and cells[1] and not re.search(r'نام|name', cells[1], re.I):
            rows.append((cells[0].translate(FA_TO_EN)[:12], cells[1][:120]))
    if not rows:
        messages.error(request, S.MSG['csv_bad'])
        return redirect('panel:courses')
    added = skipped = 0
    with transaction.atomic():
        taken = set(course.enrollments.values_list('code', flat=True))
        for code, name in rows:
            if not code or code in taken:
                skipped += 1
                continue
            user = User.objects.filter(role=User.Role.STUDENT, student_no=code).first()
            if user is None:
                user = User.objects.create_user(f's{course.pk}-{code}@students.classyar.local'.lower(), None, full_name=name,
                                                role=User.Role.STUDENT, student_no=code)
            if Enrollment.objects.filter(course=course, student=user).exists():
                skipped += 1
                continue
            Enrollment.objects.create(course=course, student=user, code=code)
            taken.add(code)
            added += 1
        record(request.user, 'import_students', course, f'ورود {added} دانشجو از CSV', course=course)
    messages.success(request, S.MSG['csv_done'].format(n=fa(added)))
    if skipped:
        messages.warning(request, S.MSG['csv_skipped'].format(n=fa(skipped)))
    return redirect('panel:courses')


# ---------------------------------------------------------------- settings
@with_course
def settings_view(request, data):
    if request.method == 'POST':
        def num(name, default, lo=1, hi=None):
            try:
                v = int(request.POST.get(name, default))
            except (TypeError, ValueError):
                v = default
            v = max(lo, v)
            return min(hi, v) if hi else v
        green, orange = num('green', 75, 1, 100) / 100, num('orange', 50, 1, 100) / 100
        if not (0 < orange < green <= 1):
            messages.error(request, S.MSG['thresholds_bad'])
            return redirect('panel:settings')
        services.save_course_settings(data.course, {
            'green': green, 'orange': orange, 'min_class': num('min_class', 10), 'min_student': num('min_student', 8),
            'drop_alert': num('drop_alert', 10), 'show_names': request.POST.get('show_names') == 'on',
            'retention_days': num('retention_days', 30, 1, 365)}, request.user)
        services.sync_suggestions(services.CourseData(data.course))
        messages.success(request, S.MSG['settings_saved'])
        return redirect('panel:settings')
    return render(request, 'panel/settings.html', panel_context(request, 'settings', data, consent=audio_service.consent_given(data.course)))
