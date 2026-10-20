"""The Python analytics must give exactly the numbers of the prototype (reference produced by its JS)."""
import json
from pathlib import Path

import pytest

from lib.analytics import Analytics, Concept, Dataset, Question, Response, Session, build_suggestions, confidence, wilson
from lib.analytics.fmt import pct

ROOT = Path(__file__).resolve().parent.parent
SEED = json.loads((ROOT / 'seed' / 'prototype_data.json').read_text(encoding='utf-8'))
REF = json.loads((ROOT / 'tests' / 'fixtures' / 'prototype_reference.json').read_text(encoding='utf-8'))


def dataset(d):
    qs = [Question(q['number'], q['session'], q['concepts'], q['options'], q['correct'], q['late'], q['asked']) for q in d['questions']]
    by_id = {q.id: q for q in qs}
    return Dataset([Concept(i, c['title'], c['from_session']) for i, c in enumerate(d['concepts'])],
                   [Session(s['number']) for s in d['sessions']], qs, [s['index'] for s in d['students']],
                   [Response(s, q, se, o, o == by_id[q].correct) for s, q, se, o in d['responses']])


@pytest.fixture(params=[0, 1], ids=['CS101', 'CS201'])
def case(request):
    return Analytics(dataset(SEED[request.param])), REF[request.param]


def r6(x):
    return None if x is None else round(x, 6)


def test_attention_matches_prototype(case):
    a, ref = case
    assert [s for s in a.d.students if a.student(s)['attention']] == ref['attention']
    assert [len(a.student(s)['reasons']) for s in a.d.students] == ref['reasons']


def test_cs101_has_twelve_students_needing_attention():
    a = Analytics(dataset(SEED[0]))
    assert sum(a.student(s)['attention'] for s in a.d.students) == 12


def test_alerts_and_suggestions_match_prototype(case):
    a, ref = case
    assert [[x['kind'], x['title']] for x in a.alerts()] == ref['alerts']
    assert [[s['key'], s['title'], s['confidence']] for s in build_suggestions(a)] == ref['suggestions']


def test_items_participation_and_cells_match_prototype(case):
    a, ref = case
    items = [[it['q'].id, it['n'], r6(it['p']), r6(it['D']), it['distractor'] and [it['distractor']['i'], r6(it['distractor']['share'])]]
             for it in a.items()]
    assert items == ref['items']
    assert [r6(p) for p in a.participation_by_session()] == ref['participation']
    assert [[[a.cell(c.id, s.number)['ok'], a.cell(c.id, s.number)['n']] for s in a.d.sessions] for c in a.d.concepts] == ref['cells']


def test_late_questions_are_left_out_of_participation():
    a = Analytics(dataset(SEED[0]))
    late = [q for q in a.d.questions if q.late]
    assert late and all(q not in a.asked_questions(99) for q in late)


def test_confidence_and_insufficient_data():
    assert confidence(3, 5, 10) == 'insufficient'
    assert confidence(80, 100, 10) == 'medium'
    assert confidence(800, 1000, 10) == 'high'
    lo, hi = wilson(0, 0)
    assert (lo, hi) == (0.0, 1.0)


def test_pct_rounds_like_javascript():
    assert pct(0.125) == '۱۳٪'
    assert pct(0.5) == '۵۰٪'
