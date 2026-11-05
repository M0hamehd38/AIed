"""The language-model part of the assistant (phase 4).

1. `brief(data)` turns a course into aggregated, anonymous figures plus a catalogue of evidence items.
   No student appears in it: no names, codes, ids or per-student rows — only class-level counts.
2. The model answers with structured drafts (`DraftSet`) that must each cite one catalogue item.
3. `accept()` keeps only drafts whose cited evidence exists and has enough answers behind it; the evidence
   text and the confidence shown to the teacher come from our own figures, never from the model.
Nothing is carried out: drafts join the same queue as the rule-based ones and wait for the teacher.
"""
import json
import uuid
from typing import Literal

from django.core.cache import cache
from django.db import transaction
from pydantic import BaseModel

from apps.audit.models import record
from lib.analytics import confidence
from lib.analytics.fmt import fa, pct

from . import llm
from .models import Suggestion

MAX_DRAFTS = 3
COOLDOWN = 60  # seconds between two requests for the same course


# ---------------------------------------------------------------- what the model must return
class Draft(BaseModel):
    evidence_id: str                 # one id from the catalogue, e.g. "concept:2"
    kind: Literal['reteach', 'practice', 'misconception', 'participation', 'extend']
    title: str                       # Persian, one line
    rationale: str                   # Persian: how the cited figures lead to this
    action: str                      # Persian: one concrete step for the next session
    limitations: str                 # Persian: what the data cannot tell


class DraftSet(BaseModel):
    drafts: list[Draft]


class QuestionDraft(BaseModel):
    text: str                        # Persian stem; code in plain text
    options: list[str]               # exactly four
    correct: int                     # index 0–3
    targets: str                     # Persian: which misconception the wrong options probe


SYSTEM = """You assist a university teacher who runs short in-class quizzes. You receive class-level, anonymous
figures for one course and a catalogue of evidence items. Propose at most three teaching actions for the next
session, in Persian, each grounded in exactly one catalogue item (cite its id in evidence_id).

Rules:
- Use only the figures given. Never invent numbers, students, sessions or questions.
- Talk about concepts and questions, never about individuals; there is no data about individuals.
- Prefer items marked enough=true. Do not draw conclusions from items with enough=false.
- Keep each action small and concrete (what to do in class, for how long, how to check it worked).
- In limitations, say plainly what these figures cannot show (e.g. absence vs. not answering, guessing).
- If nothing in the data justifies an action, return an empty list."""

QUESTION_SYSTEM = """You help a university teacher write one new multiple-choice question, in Persian, for the same
concept as an existing question many students answered wrongly. Write a different question, not a paraphrase:
new context or numbers, same idea. Exactly four options, one correct; make the wrong options reflect the
misconception shown by the most-chosen wrong answer. Do not copy the original stem or options."""


# ---------------------------------------------------------------- what is sent
def brief(data):
    """Aggregated, anonymous course figures and the evidence catalogue they can be cited by."""
    a, th = data.a, data.th
    last = a.last_session()
    catalogue = {}
    concepts = []
    for c in a.d.concepts:
        cur = a.up_to(c.id, last)
        per = []
        for s in data.sessions:
            cell = a.cell(c.id, s.number)
            if cell['n']:
                per.append({'session': s.number, 'correct_rate': round(cell['ok'] / cell['n'], 2), 'answers': cell['n']})
        concepts.append({'id': f'concept:{c.id}', 'title': c.title, 'answers': cur.n,
                         'correct_rate': round(cur.ok / cur.n, 2) if cur.n else None, 'by_session': per})
        if cur.n:
            catalogue[f'concept:{c.id}'] = {
                'ok': cur.ok, 'n': cur.n, 'ref': {'type': 'concept', 'c': c.id},
                'fact': f'تسلط تجمعی کلاس در «{c.title}» {pct(cur.ok / cur.n)} از {fa(cur.n)} پاسخ'}
    questions = []
    for it in a.items():
        q = it['q']
        if not it['n']:
            continue
        dq = data.question_by_number.get(q.id)
        wrong = it['distractor']
        questions.append({'id': f'question:{q.id}', 'text': dq.text if dq else '', 'options': q.options, 'correct_option': q.correct,
                          'concepts': [a.d.concepts[i].title for i in q.concepts], 'answers': it['n'],
                          'correct_rate': round(it['p'], 2), 'choice_counts': it['counts']})
        if wrong:
            catalogue[f'question:{q.id}'] = {
                'ok': it['counts'][wrong['i']], 'n': it['n'], 'ref': {'type': 'question', 'q': q.id},
                'fact': f'{pct(wrong["share"])} پاسخ‌های سؤال {fa(q.id)} گزینه‌ی «{q.options[wrong["i"]]}» را انتخاب کرده‌اند (n={fa(it["n"])})'}
    part = [{'session': i + 1, 'response_rate': round(p, 2)} for i, p in enumerate(a.participation_by_session()) if p is not None]
    if part:
        catalogue['participation'] = {'ok': None, 'n': None, 'ref': {'type': 'participation'},
                                      'fact': 'نرخ پاسخ کلاس در هر جلسه: ' + '، '.join(f'ج{fa(p["session"])} {pct(p["response_rate"])}' for p in part)}
    for k, v in catalogue.items():
        v['enough'] = v['n'] is None or v['n'] >= th.min_class
    payload = {
        'course': {'title': data.course.title, 'class_size': len(data.students), 'sessions_held': last,
                   'sessions_planned': len(data.sessions)},
        'thresholds': {'good_mastery': th.green, 'needs_practice_below': th.green, 'difficult_below': th.orange,
                       'minimum_answers_for_a_conclusion': th.min_class},
        'concepts': concepts, 'questions': questions, 'response_rate_by_session': part,
        'evidence_catalogue': [{'id': k, 'fact': v['fact'], 'enough': v['enough']} for k, v in catalogue.items()],
    }
    return payload, catalogue


def prompt_for(payload):
    return 'Course figures (JSON):\n' + json.dumps(payload, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- what is kept
def accept(drafts, catalogue, data):
    """Drafts that cite real, sufficient evidence, shaped as Suggestion fields. The rest are dropped."""
    th, kept, seen = data.th, [], set()
    for d in drafts[:MAX_DRAFTS * 2]:
        ev = catalogue.get(d.evidence_id)
        title, action = ' '.join(d.title.split())[:200], d.action.strip()
        if not ev or not ev['enough'] or not title or not action or d.evidence_id in seen:
            continue
        seen.add(d.evidence_id)
        conf = 'medium' if ev['n'] is None else confidence(ev['ok'], ev['n'], th.min_class)
        kept.append({'title': title, 'action': action, 'evidence': ev['fact'], 'evidence_ref': ev['ref'], 'confidence': conf,
                     'limitations': (d.limitations.strip() + ' ' if d.limitations.strip() else '') + 'این متن را مدل زبانی نوشته و ممکن است نادرست باشد.',
                     'rationale': d.rationale.strip(), 'output': 'question' if ev['ref']['type'] == 'question' else ''})
        if len(kept) == MAX_DRAFTS:
            break
    return kept


class TooSoon(Exception):
    pass


def request_drafts(data, actor):
    """Ask the model for drafts and queue the valid ones. Returns (kept, offered).
    Raises TooSoon, or llm.LLMUnavailable when there is no usable answer (the rule-based drafts stay)."""
    p = llm.provider()
    if p is None:
        raise llm.LLMUnavailable('not configured')
    key = f'assistant-cooldown:{data.course.pk}'
    if not cache.add(key, 1, COOLDOWN):
        raise TooSoon
    payload, catalogue = brief(data)
    try:
        answer = p.generate(SYSTEM, prompt_for(payload), DraftSet)
    except llm.LLMUnavailable:
        cache.delete(key)
        raise
    kept = accept(answer.drafts, catalogue, data)
    with transaction.atomic():
        # a new request replaces the model's earlier undecided drafts; decided ones stay in the record
        Suggestion.objects.filter(course=data.course, source=Suggestion.Source.AI, status=Suggestion.Status.PENDING).delete()
        for k in kept:
            rationale = k.pop('rationale')
            if rationale:
                k['action'] = f'{k["action"]}\n\nاستدلال: {rationale}'
            Suggestion.objects.create(course=data.course, key=f'ai-{uuid.uuid4().hex[:10]}', source=Suggestion.Source.AI,
                                      model_name=p.model, **k)
        record(actor, 'ai_request', data.course,
               f'درخواست از مدل زبانی ({p.model}): {fa(len(kept))} پیشنهاد پذیرفته از {fa(len(answer.drafts))}', course=data.course)
    return len(kept), len(answer.drafts)


def draft_question(data, source_q, item):
    """A new question for the same concept, written by the model; None when no usable answer came back."""
    p = llm.provider()
    if p is None:
        return None
    wrong = item['distractor']
    payload = {'concepts': [data.concepts[i].title for i in data.qrefs[source_q.number].concepts],
               'original_question': {'text': source_q.text, 'options': [o.text for o in source_q.options.all()],
                                     'correct_option': data.qrefs[source_q.number].correct,
                                     'choice_counts': item['counts'], 'answers': item['n'],
                                     'most_chosen_wrong_option': wrong['i'] if wrong else None}}
    try:
        q = p.generate(QUESTION_SYSTEM, prompt_for(payload), QuestionDraft)
    except llm.LLMUnavailable:
        return None
    opts = [' '.join(o.split()) for o in q.options]
    if (len(opts) != 4 or len(set(opts)) != 4 or not all(opts) or not 0 <= q.correct < 4 or not q.text.strip()
            or ' '.join(q.text.split()) == ' '.join(source_q.text.split())):
        return None
    return {'text': q.text.strip(), 'options': opts, 'correct': q.correct, 'targets': q.targets.strip(), 'model': p.model}
