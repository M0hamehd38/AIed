"""Mastery analytics. Pure Python: no Django, no I/O, so it is easy to test and reuse.

Everything is computed from responses to concept-tagged questions. Numbers always travel
with their n, and below the minimum n the result is reported as insufficient data.
"""
from dataclasses import dataclass, field
from math import sqrt

from . import texts_fa as T
from .fmt import fa, js_round, pct


@dataclass
class Thresholds:
    green: float = 0.75
    orange: float = 0.50
    min_class: int = 10
    min_student: int = 8
    drop_alert: int = 10  # percentage points


@dataclass
class Concept:
    id: int  # position in the course, 0-based
    title: str
    intro_session: int = 1


@dataclass
class Session:
    number: int


@dataclass
class Question:
    id: int  # question number in the course
    session: int
    concepts: list
    options: list
    correct: int
    late: bool = False  # asked at the very end of class: left out of participation
    asked: bool = True


@dataclass
class Response:
    sid: int  # student position in the course, 0-based
    qid: int
    session: int
    opt: int
    ok: bool


@dataclass
class Stat:
    ok: int
    n: int

    @property
    def rate(self):
        return self.ok / self.n if self.n else 0.0


@dataclass
class Dataset:
    concepts: list
    sessions: list
    questions: list
    students: list  # student ids (positions)
    responses: list = field(default_factory=list)


def wilson(ok, n, z=1.96):
    if not n:
        return 0.0, 1.0
    p = ok / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - m) / d), min(1.0, (c + m) / d)


def confidence(ok, n, minimum):
    if n < minimum:
        return 'insufficient'
    lo, hi = wilson(ok, n)
    w = hi - lo
    return 'high' if w < 0.15 else 'medium' if w < 0.3 else 'low'


def stat(rs):
    return Stat(sum(1 for r in rs if r.ok), len(rs))


class Analytics:
    def __init__(self, data: Dataset, th: Thresholds = None):
        self.d = data
        self.th = th or Thresholds()
        self.q = {q.id: q for q in data.questions}
        self._qconcepts = {q.id: set(q.concepts) for q in data.questions}

    # --- building blocks -------------------------------------------------
    def level(self, m):
        return 'g' if m >= self.th.green else 'o' if m >= self.th.orange else 'r'

    def level_name(self, m):
        return T.LEVEL_NAMES[self.level(m)]

    def for_concept(self, c, rs=None):
        rs = self.d.responses if rs is None else rs
        return [r for r in rs if c in self._qconcepts[r.qid]]

    def cell(self, c, s):
        rs = [r for r in self.for_concept(c) if r.session == s]
        st = stat(rs)
        return {'ok': st.ok, 'n': st.n, 'qs': list(dict.fromkeys(r.qid for r in rs))}

    def up_to(self, c, s, rs=None):
        return stat([r for r in self.for_concept(c, rs) if r.session <= s])

    def asked_questions(self, up_to):
        return [q for q in self.d.questions if q.asked and q.session <= up_to and not q.late]

    def last_session(self):
        return max((r.session for r in self.d.responses), default=0)

    # --- per student -----------------------------------------------------
    def student(self, sid, up_to=99):
        th = self.th
        rs = [r for r in self.d.responses if r.sid == sid and r.session <= up_to]
        per = [{'c': c, **vars(stat(self.for_concept(c.id, rs)))} for c in self.d.concepts]
        asked = self.asked_questions(up_to)
        answered = {r.qid for r in rs}
        recent_s = [s.number for s in self.d.sessions if s.number <= up_to][-3:]
        recent_q = [q for q in asked if q.session in recent_s]
        recent_part = sum(1 for q in recent_q if q.id in answered) / len(recent_q) if recent_q else 1
        part = sum(1 for q in asked if q.id in answered) / len(asked) if asked else 0
        total = stat(rs)
        enough = sorted((p for p in per if p['n'] >= th.min_student), key=lambda p: p['ok'] / p['n'])
        hard = enough[0] if enough else None
        reasons = []
        for p in per:
            if p['n'] >= th.min_student and p['ok'] / p['n'] < th.orange:
                reasons.append(T.REASON_CONCEPT.format(concept=p['c'].title, pct=pct(p['ok'] / p['n']), n=fa(p['n'])))
        if len(recent_q) >= 3 and recent_part < 0.6:
            reasons.append(T.REASON_PARTICIPATION.format(pct=pct(recent_part)))
        return {'rs': rs, 'per': per, 'part': part, 'recent_part': recent_part, 'total': total,
                'hard': hard, 'reasons': reasons, 'attention': bool(reasons)}

    # --- per question ----------------------------------------------------
    def items(self):
        scores = {}
        for sid in self.d.students:
            st = stat([r for r in self.d.responses if r.sid == sid])
            scores[sid] = st.ok / st.n if st.n else 0
        out = []
        for q in self.d.questions:
            if not q.asked:
                continue
            rs = [r for r in self.d.responses if r.qid == q.id]
            n = len(rs)
            p = sum(1 for r in rs if r.ok) / n if n else 0
            ordered = sorted(rs, key=lambda r: -scores.get(r.sid, 0))
            k = max(1, js_round(n * 0.27))
            upper, lower = ordered[:k], ordered[-k:]
            disc = (sum(r.ok for r in upper) / k - sum(r.ok for r in lower) / k) if n >= 4 else None
            counts = [sum(1 for r in rs if r.opt == i) for i in range(len(q.options))]
            wrong = sorted(((i, c) for i, c in enumerate(counts) if i != q.correct), key=lambda x: -x[1])
            distractor = {'i': wrong[0][0], 'share': wrong[0][1] / n} if wrong and wrong[0][1] else None
            out.append({'q': q, 'n': n, 'p': p, 'D': disc, 'counts': counts, 'distractor': distractor})
        return out

    # --- class level -----------------------------------------------------
    def participation_by_session(self):
        out = []
        for s in self.d.sessions:
            qs = [q for q in self.d.questions if q.session == s.number and q.asked and not q.late]
            if not qs or not self.d.students:
                out.append(None)
                continue
            ids = {q.id for q in qs}
            answered = sum(1 for r in self.d.responses if r.qid in ids)
            out.append(answered / (len(qs) * len(self.d.students)))
        return out

    def alerts(self):
        th, out = self.th, []
        for c in self.d.concepts:
            pts = [(s.number, self.cell(c.id, s.number)) for s in self.d.sessions]
            pts = [(s, x) for s, x in pts if x['n'] >= th.min_class]
            if len(pts) < 2:
                continue
            (sa, a), (sb, b) = pts[-2], pts[-1]
            diff = js_round((b['ok'] / b['n'] - a['ok'] / a['n']) * 100)
            text = T.ALERT_TREND_TEXT.format(a=pct(a['ok'] / a['n']), sa=fa(sa), b=pct(b['ok'] / b['n']), sb=fa(sb), n=fa(b['n']))
            ev = {'type': 'cell', 'c': c.id, 's': sb}
            if diff <= -th.drop_alert:
                out.append({'kind': 'red', 'title': T.ALERT_DROP.format(concept=c.title), 'text': text, 'ev': ev})
            elif diff >= th.drop_alert:
                out.append({'kind': 'green', 'title': T.ALERT_RISE.format(concept=c.title), 'text': text, 'ev': ev})
        ps = [(p, i + 1) for i, p in enumerate(self.participation_by_session()) if p is not None]
        if len(ps) >= 4:
            (lp, ls), prev = ps[-1], ps[-4:-1]
            avg = sum(p for p, _ in prev) / len(prev)
            if js_round((lp - avg) * 100) <= -th.drop_alert / 2:
                out.append({'kind': 'orange', 'title': T.ALERT_PART,
                            'text': T.ALERT_PART_TEXT.format(s=fa(ls), p=pct(lp), avg=pct(avg)), 'ev': {'type': 'participation'}})
        return out

    def concept_mastery(self, up_to=None):
        up_to = self.last_session() if up_to is None else up_to
        return [{'c': c, **vars(self.up_to(c.id, up_to))} for c in self.d.concepts]


def build_suggestions(a: Analytics):
    """Rule-based drafts s1–s4. Nothing here is executed: each one waits for the teacher's decision."""
    th, out = a.th, []
    cm = sorted((x for x in a.concept_mastery() if x['n']), key=lambda x: x['ok'] / x['n'])
    weakest = cm[0] if cm else None
    if weakest and weakest['ok'] / weakest['n'] < th.green:
        qs = list(dict.fromkeys(r.qid for r in a.for_concept(weakest['c'].id)))
        out.append({'key': 's1', 'title': T.S1_TITLE.format(concept=weakest['c'].title),
                    'evidence': T.S1_EVIDENCE.format(pct=pct(weakest['ok'] / weakest['n']), q=fa(len(qs)), n=fa(weakest['n'])),
                    'evidence_ref': {'type': 'concept', 'c': weakest['c'].id},
                    'confidence': confidence(weakest['ok'], weakest['n'], th.min_class),
                    'limitations': T.S1_LIMITS, 'action': T.S1_ACTION, 'output': ''})
    items = sorted((it for it in a.items() if it['n'] >= th.min_class and it['distractor'] and it['distractor']['share'] >= 0.25),
                   key=lambda it: -it['distractor']['share'])
    if items:
        it = items[0]
        share = it['distractor']['share']
        out.append({'key': 's2', 'title': T.S2_TITLE.format(q=fa(it['q'].id)),
                    'evidence': T.S2_EVIDENCE.format(pct=pct(share), option=it['q'].options[it['distractor']['i']], n=fa(it['n'])),
                    'evidence_ref': {'type': 'question', 'q': it['q'].id},
                    'confidence': confidence(js_round(share * it['n']), it['n'], th.min_class),
                    'limitations': T.S2_LIMITS, 'action': T.S2_ACTION, 'output': 'question'})
    if any(x['kind'] == 'orange' for x in a.alerts()):
        out.append({'key': 's3', 'title': T.S3_TITLE, 'evidence': T.S3_EVIDENCE, 'evidence_ref': {'type': 'participation'},
                    'confidence': 'medium', 'limitations': T.S3_LIMITS, 'action': T.S3_ACTION, 'output': ''})
    best = cm[-1] if cm else None
    if best and best['ok'] / best['n'] >= th.green:
        out.append({'key': 's4', 'title': T.S4_TITLE.format(concept=best['c'].title),
                    'evidence': T.S4_EVIDENCE.format(pct=pct(best['ok'] / best['n']), n=fa(best['n'])),
                    'evidence_ref': {'type': 'concept', 'c': best['c'].id},
                    'confidence': confidence(best['ok'], best['n'], th.min_class),
                    'limitations': T.S4_LIMITS, 'action': T.S4_ACTION, 'output': ''})
    return out
