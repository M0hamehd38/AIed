"""The overview page's data, ready for display. No HTML here; templates/panel/dashboard.html only shows it.

Each number appears once: the stat cards hold the headline figures, the term summary holds what they do not
(sessions, responses, response rate, concepts to review, direction of travel), and the chart holds the series.
"""
from apps.audio import services as audio_service
from apps.audio import stt
from apps.audio.models import Transcript, TranscriptSignal
from apps.courses.models import Session
from apps.insights.models import Suggestion
from apps.live import services as live_service
from lib.analytics import Stat, stat
from lib.analytics.fmt import fa, js_round, pct

from .charts import line_chart

LEVEL_SYMBOL = {'g': '✓', 'o': '!', 'r': '✕'}
LEVEL_WORD = {'g': 'تسلط مناسب', 'o': 'نیازمند تمرین', 'r': 'دشوار'}


def _delta(now, before, good_when_up=True, unit=''):
    """A small change badge, or None when there is nothing valid to compare with or no change."""
    if before is None:
        return None
    d = now - before
    if d == 0:
        return None
    return {'text': ('▲ ' if d > 0 else '▼ ') + fa(abs(d)) + unit, 'good': (d > 0) == good_when_up,
            'title': 'نسبت به جلسه‌ی قبل'}


def stats(data, pending_count):
    a = data.a
    last = a.last_session()
    prev = last - 1 if a.in_session(last - 1) else None  # compare only with a session that has answers

    def active(s):
        return len({r.sid for r in a.in_session(s)})

    def avg_mastery(s):
        xs = [x for x in (a.up_to(c.id, s) for c in a.d.concepts) if x.n]
        return sum(x.ok / x.n for x in xs) / len(xs) if xs else 0

    def attention(s):
        return sum(1 for st in data.students if a.student(st.index, s)['attention'])

    m_now = avg_mastery(last)
    return [
        {'key': 'active', 'label': 'دانشجویان فعال', 'value': fa(active(last)), 'icon': 'students', 'tone': 'blue',
         'foot': f'از {fa(len(data.students))} دانشجو، جلسه‌ی {fa(last)}', 'href': 'panel:students',
         'delta': _delta(active(last), active(prev) if prev else None)},
        {'key': 'mastery', 'label': 'میانگین تسلط مفهومی', 'value': pct(m_now), 'icon': 'target', 'tone': 'green',
         'foot': 'تجمعی، همه‌ی مفاهیم', 'href': 'panel:analytics',
         'delta': _delta(js_round(m_now * 100), js_round(avg_mastery(prev) * 100) if prev else None, unit='٪')},
        {'key': 'attention', 'label': 'نیازمند توجه', 'value': fa(attention(last)), 'icon': 'alert', 'tone': 'orange',
         'foot': 'بر پایه‌ی آستانه‌های درس', 'href': 'panel:students', 'query': '?f=attention',
         'delta': _delta(attention(last), attention(prev) if prev else None, good_when_up=False)},
        {'key': 'pending', 'label': 'پیشنهادهای در انتظار', 'value': fa(pending_count), 'icon': 'ai', 'tone': 'purple',
         'foot': 'منتظر تصمیم شما' if pending_count else 'همه بررسی شده‌اند', 'href': 'panel:suggestions', 'delta': None},
    ]


def heatmap(data):
    a, th = data.a, data.th
    rows = []
    for c in a.d.concepts:
        cells = []
        for s in data.sessions:
            cl = a.cell(c.id, s.number)
            ev = {'type': 'cell', 'c': c.id, 's': s.number}
            if not cl['n']:
                cells.append({'kind': 'na', 'label': f'{c.title}، جلسه‌ی {fa(s.number)}: بدون سؤال'})
            elif cl['n'] < th.min_class:
                cells.append({'kind': 'low', 'n': cl['n'], 'ev': ev,
                              'label': f'{c.title}، جلسه‌ی {fa(s.number)}: داده کافی نیست، {fa(cl["n"])} پاسخ'})
            else:
                m = cl['ok'] / cl['n']
                lv = a.level(m)
                cells.append({'kind': lv, 'm': m, 'n': cl['n'], 'ev': ev, 'sym': LEVEL_SYMBOL[lv],
                              'label': f'{c.title}، جلسه‌ی {fa(s.number)}: {pct(m)}، {LEVEL_WORD[lv]}، {fa(cl["n"])} پاسخ'})
        rows.append({'c': c, 'cells': cells})
    # below this width the map scrolls sideways instead of squeezing the cells
    return {'rows': rows, 'cols': len(data.sessions), 'orange_top': th.green - 0.01, 'min_w': 110 + 64 * len(data.sessions)}


def suggestion_view(s):
    return {'pk': s.pk, 'title': s.title, 'reason': s.evidence, 'action': s.action, 'limits': s.limitations,
            'confidence': s.confidence, 'ev': s.evidence_ref}


def assistant(course):
    pending = list(Suggestion.objects.filter(course=course, status=Suggestion.Status.PENDING))
    decided = Suggestion.objects.filter(course=course).exclude(status=Suggestion.Status.PENDING).count()
    return {'primary': suggestion_view(pending[0]) if pending else None,
            'others': [suggestion_view(s) for s in pending[1:]], 'pending': len(pending), 'decided': decided}


def term_summary(data):
    a, th = data.a, data.th
    held = [s for s in data.sessions if a.in_session(s.number)]
    ps = [p for p in a.participation_by_session() if p is not None]
    review = sorted((x for x in a.concept_mastery() if x['n'] and x['ok'] / x['n'] < th.green), key=lambda x: x['ok'] / x['n'])
    # direction of travel: correct answers in the last three sessions vs the three before
    rates = [stat(a.in_session(s.number)) for s in held]
    trend = None
    def total(xs):
        return Stat(sum(x.ok for x in xs), sum(x.n for x in xs))
    recent, before = (total(rates[-3:]), total(rates[-6:-3])) if len(rates) >= 6 else (None, None)
    if recent and recent.n and before.n:
        d = js_round((recent.ok / recent.n - before.ok / before.n) * 100)
        trend = {'d': d, 'text': ('▲ ' if d > 0 else '▼ ' if d < 0 else '') + (fa(abs(d)) + ' واحد' if d else 'بدون تغییر'),
                 'good': d >= 0, 'detail': 'درست‌پاسخیِ سه جلسه‌ی اخیر نسبت به سه جلسه‌ی پیش از آن'}
    return {'held': len(held), 'planned': len(data.sessions), 'responses': len(data.responses),
            'response_rate': sum(ps) / len(ps) if ps else None,
            'review': [{'title': x['c'].title, 'm': x['ok'] / x['n']} for x in review], 'trend': trend}


def learning_chart(data):
    th = data.th
    if len(data.sessions) < 2:
        return None
    from .views import participation_series, point, session_stat  # shared helpers
    first, last = data.sessions[0].number, data.sessions[-1].number
    return {'svg': line_chart([
        {'name': 'درست‌پاسخی کلاس', 'color': 'var(--green)', 'points': [point(session_stat(data, s.number), th.min_class) for s in data.sessions]},
        {'name': 'نرخ پاسخ', 'color': 'var(--blue)', 'points': participation_series(data)},
    ], data.sessions, th, h=230, w=640, area=False, threshold=True, label='روند درست‌پاسخی و نرخ پاسخ در هر جلسه',
        table=True), 'range': f'جلسه‌ی {fa(first)} تا {fa(last)}'}


def attention_list(data, limit=5):
    a = data.a
    need = [(s, a.student(s.index)) for s in data.students]
    need = [(s, x) for s, x in need if x['attention']]
    rows = [{'s': s, 'name': data.student_name(s),
             'why': f'مفهوم دشوار: {x["hard"]["c"].title}' if x['hard'] else x['reasons'][0]} for s, x in need[:limit]]
    return {'rows': rows, 'count': len(need)}


def live_and_listening(data):
    course = data.course
    live = live_service.live_session(course)
    live_info = None
    if live:
        view = live_service.teacher_view(live)
        q = view['question']
        live_info = {'session': live, 'code': live.join_code, 'answered': view['answered_total'],
                     'question': q and {'number': q['number'], 'state': q['state'], 'n': q.get('n', 0)}}
    session = audio_service.target_session(course)
    lines = Transcript.objects.filter(session=session) if session else Transcript.objects.none()
    last_line = lines.order_by('-created_at').first()
    if not stt.configured():
        listen = {'state': 'err', 'label': 'تنظیم نشده', 'text': 'سرویس تبدیل گفتار روی سرور راه‌اندازی نشده است؛ شنود در دسترس نیست.'}
    elif not audio_service.consent_given(course):
        listen = {'state': 'warn', 'label': 'نیازمند رضایت‌نامه', 'text': 'پیش از اولین شنود، رضایت‌نامه را برای کلاس بخوانید و ثبت کنید.'}
    else:
        listen = {'state': 'off', 'label': 'غیرفعال', 'text': 'شنود فقط با زدن «شروع شنود» در صفحه‌ی شنود آغاز می‌شود.'}
    if last_line:
        listen['last'] = {'session': session.number, 'lines': lines.count(),
                          'confusion': TranscriptSignal.objects.filter(transcript__in=lines, kind='confusion').count()}
    return {'live': live_info, 'listen': listen}


def class_status(data):
    """One line under the greeting: course, group, latest session and whether class is on."""
    course = data.course
    live = Session.objects.filter(course=course, status=Session.Status.LIVE).first()
    held = [s for s in data.sessions if s.status == Session.Status.CLOSED]
    latest = live or (held[-1] if held else None)
    if live:
        state = {'label': 'در حال برگزاری', 'cls': 'on'}
    elif latest:
        state = {'label': 'جلسه‌ای در جریان نیست', 'cls': ''}
    else:
        state = {'label': 'هنوز جلسه‌ای برگزار نشده', 'cls': ''}
    return {'course': course, 'session': latest, 'state': state, 'demo': course.is_demo}


def build(data):
    a = assistant(data.course)
    return {'status': class_status(data), 'stats': stats(data, a['pending']), 'heat': heatmap(data), 'assistant': a,
            'summary': term_summary(data), 'chart': learning_chart(data), 'attention': attention_list(data),
            'ops': live_and_listening(data)}
