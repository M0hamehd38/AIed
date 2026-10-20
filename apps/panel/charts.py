"""Server-rendered SVG line charts (RTL: session 1 on the right)."""
from itertools import count

from django.utils.html import escape
from django.utils.safestring import mark_safe

from lib.analytics.fmt import fa, pct

_ids = count(1)


def line_chart(series, sessions, th, h=220, w=640, y_min=0.0, area=False, threshold=True,
               label='نمودار روند تسلط', hollow_note=True):
    """series: [{'name', 'color', 'points': [None | {'v', 'n', 'ok'}] per session}]"""
    n = len(sessions)
    if n < 2:
        return mark_safe('<div class="empty">برای رسم نمودار دست‌کم دو جلسه لازم است.</div>')
    gid = f'g{next(_ids)}'
    W, H, P = w, h, {'l': 36, 'r': 16, 't': 12, 'b': 28}

    def x(i):
        return round(W - P['r'] - (i * (W - P['l'] - P['r']) / (n - 1)), 2)

    def y(v):
        return round(P['t'] + (1 - (v - y_min) / (1 - y_min)) * (H - P['t'] - P['b']), 2)
    g, defs = [], []
    for t in (0, .25, .5, .75, 1):
        g.append(f'<line x1="{P["l"]}" x2="{W - P["r"]}" y1="{y(t)}" y2="{y(t)}" stroke="var(--line)"/>'
                 f'<text x="{P["l"] - 6}" y="{y(t) + 4}" font-size="10" fill="var(--muted)" text-anchor="end">{pct(t)}</text>')
    if threshold:
        g.append(f'<line x1="{P["l"]}" x2="{W - P["r"]}" y1="{y(th.green)}" y2="{y(th.green)}" stroke="var(--green)" '
                 f'stroke-dasharray="4 4" opacity=".6"/>')
    for i, s in enumerate(sessions):
        g.append(f'<text x="{x(i)}" y="{H - 8}" font-size="10" fill="var(--muted)" text-anchor="middle">ج{fa(s.number)}</text>')
    for si, sr in enumerate(series):
        pts = [{'x': x(i), 'y': y(p['v']), **p} for i, p in enumerate(sr['points']) if p]
        solid = [p for p in pts if p['ok']]
        color, name = sr['color'], escape(sr['name'])
        if area and len(solid) > 1:
            defs.append(f'<linearGradient id="{gid}{si}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{color}" '
                        f'stop-opacity=".26"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient>')
            poly = ' '.join(f'{p["x"]},{p["y"]}' for p in solid)
            g.append(f'<polygon fill="url(#{gid}{si})" points="{solid[0]["x"]},{y(y_min)} {poly} {solid[-1]["x"]},{y(y_min)}"/>')
        if len(solid) > 1:
            line = ' '.join(f'{p["x"]},{p["y"]}' for p in solid)
            g.append(f'<polyline fill="none" stroke-linejoin="round" stroke-linecap="round" stroke="{color}" stroke-width="2.6" '
                     f'points="{line}"/>')
        for p in pts:
            note = '' if p['ok'] else ' — داده کافی نیست'
            g.append(f'<circle cx="{p["x"]}" cy="{p["y"]}" r="4" fill="{color if p["ok"] else "var(--card)"}" stroke="{color}" '
                     f'stroke-width="2"><title>{name}: {pct(p["v"])} (n={fa(p["n"])}){note}</title></circle>')
    legend = ''.join(f'<span><i style="background:{s["color"]}"></i>{escape(s["name"])}</span>' for s in series)
    if hollow_note:
        legend += '<span><i style="background:var(--card);border:2px solid var(--muted)"></i>نقطه‌ی توخالی: داده کافی نیست</span>'
    return mark_safe(f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="{escape(label)}"><defs>{"".join(defs)}</defs>'
                     f'{"".join(g)}</svg><div class="legend">{legend}</div>')
