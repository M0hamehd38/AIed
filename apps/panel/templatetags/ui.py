"""Small UI components shared by the panel templates (ported from the prototype's C.* helpers)."""
import json
from math import pi

from django import template
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

from apps.panel import strings as S
from lib.analytics.fmt import fa as _fa, pct as _pct

register = template.Library()

ICONS = {
    'alert': '<path d="M12 3l10 18H2zM12 10v5M12 18v.5"/>',
    'target': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    'doc': '<path d="M6 3h9l4 4v14H6z"/><path d="M9 12h7M9 16h5"/>',
    'spark': '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6"/>',
    'grid': '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    'dashboard': '<path d="M3 3h7v7H3zM14 3h7v4h-7zM14 10h7v11h-7zM3 13h7v8H3z"/>',
    'live': '<circle cx="12" cy="12" r="3"/><path d="M5 5a10 10 0 0 0 0 14M19 5a10 10 0 0 1 0 14"/>',
    'audio': '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
    'students': '<circle cx="9" cy="8" r="3.5"/><path d="M2 20c1-4 4-6 7-6s6 2 7 6M16 4a3.5 3.5 0 0 1 0 7M18 14c2 1 3.5 3 4 6"/>',
    'analytics': '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    'suggestions': '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0 0 12 3z"/>',
    'courses': '<path d="M4 4h12a4 4 0 0 1 4 4v12H8a4 4 0 0 1-4-4z"/><path d="M8 9h8M8 13h5"/>',
    'settings': '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"/>',
    # top bar, assistant and status icons: same 24px grid and 1.8 stroke as the menu
    'bell': '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10 21h4"/>',
    'logout': '<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l-4-4 4-4M6 12h10"/>',
    'menu': '<path d="M4 7h16M4 12h16M4 17h16"/>',
    'ai': '<path d="M12 3l1.8 4.6L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.9z"/><path d="M18.5 15.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/>',
    'chevron': '<path d="M6 9l6 6 6-6"/>',
    'eye': '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    'check': '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    'x': '<path d="M6 6l12 12M18 6L6 18"/>',
    'calendar': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    'trend': '<path d="M3 17l6-6 4 4 8-8M15 7h6v6"/>',
}


@register.filter
def fa(v):
    return _fa(v)


@register.filter
def pct(v):
    return '—' if v is None else _pct(v)


@register.filter
def evjson(ev):
    return json.dumps(ev, separators=(',', ':'))


@register.filter
def jdate(d):
    """Gregorian date → '۱۹ مهر' (Jalali day and month)."""
    if not d:
        return ''
    import jdatetime
    j = jdatetime.date.fromgregorian(date=d)
    return f'{_fa(j.day)} {jdatetime.date.j_months_fa[j.month - 1]}'


@register.simple_tag
def icon(k):
    return mark_safe(f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
                     f'stroke-linejoin="round" aria-hidden="true">{ICONS[k]}</svg>')


@register.simple_tag
def h2(icon_key, color, title):
    return format_html('<h2><span class="hic {}">{}</span>{}</h2>', color, icon(icon_key), title)


@register.simple_tag
def tag(text, cls=''):
    return format_html('<span class="tag {}">{}</span>', cls, text)


@register.simple_tag
def conf_tag(c):
    return tag(S.CONF[c], S.CONF_CLASS[c])


def _level(th, m):
    return 'g' if m >= th.green else 'o' if m >= th.orange else 'r'


@register.simple_tag(takes_context=True)
def level_tag(context, m):
    th = context['th']
    names = {'g': 'تسلط مناسب', 'o': 'نیازمند تمرین', 'r': 'دشوار'}
    lv = _level(th, m)
    return tag(names[lv], S.LEVEL_CLASS[lv])


@register.simple_tag(takes_context=True)
def level_class(context, m):
    return {'g': 't-green', 'o': 't-orange', 'r': 't-red'}[_level(context['th'], m)]


@register.simple_tag(takes_context=True)
def progress(context, v, color=''):
    v = max(0.0, min(1.0, v or 0))
    color = color or S.LEVEL_COLOR[_level(context['th'], v)]
    return format_html('<div class="progress" role="img" aria-label="{}"><i style="width:{}%;background:{}"></i></div>',
                       _pct(v), round(v * 100), color)


@register.simple_tag(takes_context=True)
def ring(context, v, size=76):
    r = size / 2 - 7
    length = 2 * pi * r
    col = S.LEVEL_COLOR[_level(context['th'], v)]
    c = size / 2
    return mark_safe(
        f'<div class="ring" style="width:{size}px;height:{size}px"><svg width="{size}" height="{size}" aria-hidden="true">'
        f'<circle cx="{c}" cy="{c}" r="{r}" stroke="var(--line)" stroke-width="7" fill="none"/>'
        f'<circle cx="{c}" cy="{c}" r="{r}" stroke="{col}" stroke-width="7" fill="none" stroke-linecap="round" '
        f'stroke-dasharray="{length * v:.2f} {length:.2f}" transform="rotate(-90 {c} {c})"/></svg><span>{_pct(v)}</span></div>')


def _rng(seed):
    """mulberry32, as in the prototype, so the placeholder portraits look the same."""
    state = [seed & 0xFFFFFFFF]

    def imul(a, b):
        return (a * b) & 0xFFFFFFFF

    def nxt():
        state[0] = (state[0] + 0x6D2B79F5) & 0xFFFFFFFF
        s = state[0]
        t = imul(s ^ (s >> 15), 1 | s)
        t = ((t + imul(t ^ (t >> 7), 61 | t)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return nxt


@register.simple_tag(takes_context=True)
def photo(context, s, size=64):
    """Illustrated placeholder portrait; the product would show the photo from the university's system."""
    if not context['cfg']['show_names']:
        return format_html('<span class="avatar photo" style="width:{}px;height:{}px;background:#77839b;font-size:{}px" '
                           'aria-hidden="true">{}</span>', size, size, size // 3, _fa(s.code))
    r = _rng(s.index * 97 + 13)

    def pick(a):
        return a[int(r() * len(a))]
    skin = pick(['#f1c7a5', '#e5b48f', '#c98f68', '#f6d6bd', '#d9a07a'])
    hair = pick(['#2b1d16', '#4a2f22', '#1c1c1c', '#6b4a2e', '#3a2a20', '#7a5230'])
    shirt = pick(['#4169f5', '#8c62db', '#13a67b', '#e08a17', '#0e9fb5', '#c2477f', '#2e3f6e'])
    bg = pick(['#e8eeff', '#f1ebfb', '#e3f5ee', '#fff1df', '#e2f4f7', '#fbe8f0'])
    style = s.index % 4
    back = f'<path d="M17 30Q16 11 32 11Q48 11 47 30L50 52L14 52Z" fill="{hair}"/>' if style == 1 else ''
    if style == 3:
        top = ''.join(f'<circle cx="{x}" cy="{y}" r="5.5" fill="{hair}"/>'
                      for x, y in [(22, 22), (26, 17), (32, 15), (38, 17), (42, 22), (24, 27), (40, 27)])
    elif style == 2:
        top = f'<path d="M20 30Q18 13 33 13Q46 14 45 28Q37 18 22 25Z" fill="{hair}"/>'
    else:
        top = f'<path d="M20 29Q19 13 32 13Q45 13 44 29Q41 20 32 20Q23 20 20 29Z" fill="{hair}"/>'
    return mark_safe(
        f'<svg class="photo" width="{size}" height="{size}" viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" fill="{bg}"/>'
        f'{back}<path d="M8 66Q10 46 32 46Q54 46 56 66Z" fill="{shirt}"/><rect x="27" y="37" width="10" height="11" rx="4" fill="{skin}"/>'
        f'<ellipse cx="32" cy="30" rx="11" ry="12.5" fill="{skin}"/>{top}<circle cx="28" cy="31" r="1.3" fill="#2b2b2b"/>'
        f'<circle cx="36" cy="31" r="1.3" fill="#2b2b2b"/><path d="M28.5 35.8Q32 38.4 35.5 35.8" stroke="#8a4b3a" stroke-width="1.3" '
        f'fill="none" stroke-linecap="round"/></svg>')


@register.simple_tag
def delta(d, unit='', good_up=True):
    if d == 0:
        return 'بدون تغییر نسبت به جلسه‌ی قبل'
    up = d > 0
    return format_html('<span class="{}">{} {}{}</span> نسبت به جلسه‌ی قبل', 'up' if up == good_up else 'down',
                       '▲' if up else '▼', _fa(abs(d)), unit)


@register.simple_tag
def alert_ic(kind):
    return {'red': '!', 'orange': '!', 'green': '↑', 'blue': 'i'}[kind]


@register.filter
def attr(obj, name):
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


@register.filter
def esc(v):
    return escape(v)


@register.filter
def div(a, b):
    return a / b if b else 0


@register.filter
def rate(x):
    """{'ok', 'n'} (or a Stat) → ok / n"""
    ok, n = (x['ok'], x['n']) if isinstance(x, dict) else (x.ok, x.n)
    return ok / n if n else 0
