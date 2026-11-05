"""Phase 4: the language-model layer. A stand-in provider records exactly what would be sent."""
import io
import json
from types import SimpleNamespace

import pytest

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.courses.models import Enrollment, Question
from apps.insights import assistant, llm, services
from apps.insights.models import Suggestion


class StandIn(llm.Provider):
    name, model = 'stand-in', 'stand-in-model'

    def __init__(self, answer=None, fail=False):
        self.answer, self.fail, self.calls = answer, fail, []

    def generate(self, system, prompt, schema):
        self.calls.append({'system': system, 'prompt': prompt, 'schema': schema})
        if self.fail:
            raise llm.LLMUnavailable('connection')
        return schema.model_validate(self.answer(schema) if callable(self.answer) else self.answer)


def draft(evidence_id, title='مرور هدفمند', **kw):
    return {'evidence_id': evidence_id, 'kind': 'reteach', 'title': title, 'rationale': 'چون تسلط پایین است',
            'action': 'ده دقیقه مرور با یک مثال', 'limitations': 'غیبت از پاسخ‌ندادن جدا نمی‌شود', **kw}


@pytest.fixture
def use(monkeypatch):
    def _use(p):
        monkeypatch.setattr(llm, 'provider', lambda: p)
        monkeypatch.setattr(llm, 'describe', lambda: {'on': True, 'label': p.model, 'where': 'آزمون'})
        return p
    return _use


@pytest.fixture
def data(cs101):
    return services.CourseData(cs101)


def test_nothing_about_any_student_is_sent(teacher_client, cs101, use):
    # distinctive codes and student numbers, so any leak is unmistakable
    for e in Enrollment.objects.filter(course=cs101).select_related('student'):
        e.code = f'9871{e.pk:04d}'
        e.save(update_fields=['code'])
        User.objects.filter(pk=e.student_id).update(student_no=f'4012{e.pk:05d}')
    p = use(StandIn({'drafts': []}))
    assistant.request_drafts(services.CourseData(cs101), cs101.teacher)
    sent = p.calls[0]['system'] + p.calls[0]['prompt']
    people = Enrollment.objects.filter(course=cs101).select_related('student')
    assert people.count() == 30
    for e in people:
        assert e.student.full_name not in sent
        assert e.code not in sent and e.student.student_no not in sent and e.student.email not in sent
    assert cs101.teacher.full_name not in sent and cs101.teacher.email not in sent
    payload = json.loads(p.calls[0]['prompt'].split('\n', 1)[1])
    assert set(payload) == {'course', 'thresholds', 'concepts', 'questions', 'response_rate_by_session', 'evidence_catalogue'}
    # the page shows the very same figures to the teacher
    body = teacher_client.get('/t/suggestions/').content.decode()
    assert 'داده‌ای که فرستاده می‌شود' in body and '&quot;evidence_catalogue&quot;' in body


def test_only_drafts_with_real_sufficient_evidence_are_kept(cs101, data, use):
    _, catalogue = assistant.brief(data)
    thin = next(k for k, v in catalogue.items() if not v['enough'])
    use(StandIn({'drafts': [draft('concept:2'), draft('concept:99'), draft(thin), draft('concept:2', 'تکراری'),
                            draft('participation', 'پیگیری مشارکت')]}))
    kept, offered = assistant.request_drafts(data, cs101.teacher)
    assert (kept, offered) == (2, 5)
    ai = list(Suggestion.objects.filter(course=cs101, source='ai').order_by('id'))
    assert [s.evidence_ref for s in ai] == [{'type': 'concept', 'c': 2}, {'type': 'participation'}]
    s = ai[0]
    # evidence text and confidence come from our figures, not from the model
    assert s.evidence == catalogue['concept:2']['fact'] and s.confidence in ('high', 'medium', 'low')
    assert s.status == 'pending' and s.model_name == 'stand-in-model' and 'مدل زبانی نوشته' in s.limitations
    assert AuditLog.objects.filter(action='ai_request', course=cs101).exists()


def test_rules_keep_working_and_do_not_remove_model_drafts(cs101, data, use):
    use(StandIn({'drafts': [draft('concept:2')]}))
    assistant.request_drafts(data, cs101.teacher)
    services.sync_suggestions(services.CourseData(cs101))
    assert Suggestion.objects.filter(course=cs101, source='ai', status='pending').count() == 1
    assert Suggestion.objects.filter(course=cs101, source='rules').count() == 3


def test_new_request_replaces_undecided_model_drafts_only(cs101, data, use, settings):
    from django.core.cache import cache
    use(StandIn({'drafts': [draft('concept:2'), draft('participation')]}))
    assistant.request_drafts(data, cs101.teacher)
    first = Suggestion.objects.filter(course=cs101, source='ai').first()
    services.decide(first, 'approved', cs101.teacher)
    cache.clear()
    assistant.request_drafts(data, cs101.teacher)
    assert Suggestion.objects.filter(pk=first.pk, status='approved').exists()
    assert Suggestion.objects.filter(course=cs101, source='ai', status='pending').count() == 2


def test_button_flow_messages(teacher_client, cs101, use):
    r = teacher_client.post('/t/suggestions/ai/', follow=True)
    assert 'مدل زبانی تنظیم نشده' in r.content.decode()
    use(StandIn({'drafts': [draft('concept:2')]}))
    r = teacher_client.post('/t/suggestions/ai/', follow=True).content.decode()
    assert '۱ پیشنهاد تازه' in r and 'نوشته‌ی مدل زبانی' in r
    r = teacher_client.post('/t/suggestions/ai/', follow=True).content.decode()
    assert 'یک دقیقه‌ی دیگر' in r


def test_model_failure_leaves_rule_drafts(teacher_client, cs101, use):
    use(StandIn(fail=True))
    teacher_client.get('/t/suggestions/')
    r = teacher_client.post('/t/suggestions/ai/', follow=True).content.decode()
    assert 'پاسخ قابل‌استفاده‌ای از مدل زبانی نرسید' in r
    assert Suggestion.objects.filter(course=cs101, source='rules', status='pending').count() == 3


def test_page_without_a_model_says_so(teacher_client):
    body = teacher_client.get('/t/suggestions/').content.decode()
    assert 'تنظیم نشده' in body and 'داده‌ای که فرستاده می‌شود' not in body
    assert 'تنظیم نشده؛ فقط پیشنهادهای قاعده‌محور' in teacher_client.get('/t/settings/').content.decode()


def _approved_question_suggestion(teacher_client, cs101):
    teacher_client.get('/t/suggestions/')
    s = Suggestion.objects.get(course=cs101, key='s2')
    services.decide(s, 'approved', cs101.teacher)
    return s


def test_draft_question_written_by_the_model(teacher_client, cs101, use):
    s = _approved_question_suggestion(teacher_client, cs101)
    p = use(StandIn({'text': 'خروجی 9 // 4 در پایتون چیست؟', 'options': ['2', '2.25', '3', '1'], 'correct': 0,
                     'targets': 'تقسیم صحیح با تقسیم اعشاری اشتباه گرفته می‌شود'}))
    r = teacher_client.post(f'/t/suggestions/{s.pk}/draft-question/', follow=True).content.decode()
    q = Question.objects.filter(course=cs101).latest('number')
    assert q.text == 'خروجی 9 // 4 در پایتون چیست؟' and q.status == 'draft'
    assert [o.text for o in q.options.order_by('order')] == ['2', '2.25', '3', '1'] and q.options.get(is_correct=True).text == '2'
    assert 'مدل زبانی نوشت' in r
    sent = p.calls[0]['prompt']
    assert all(e.student.full_name not in sent for e in Enrollment.objects.filter(course=cs101).select_related('student'))


@pytest.mark.parametrize('bad', [
    {'text': 'سؤال', 'options': ['1', '2', '3'], 'correct': 0, 'targets': ''},           # three options
    {'text': 'سؤال', 'options': ['1', '1', '2', '3'], 'correct': 0, 'targets': ''},      # repeated option
    {'text': 'سؤال', 'options': ['1', '2', '3', '4'], 'correct': 7, 'targets': ''},      # no such answer
])
def test_bad_model_question_falls_back_to_a_marked_copy(teacher_client, cs101, use, bad):
    s = _approved_question_suggestion(teacher_client, cs101)
    use(StandIn(bad))
    teacher_client.post(f'/t/suggestions/{s.pk}/draft-question/')
    q = Question.objects.filter(course=cs101).latest('number')
    assert 'پیش از استفاده بازنویسی کنید' in q.text and q.status == 'draft'


# ---------------------------------------------------------------- the providers themselves
class FakeParse:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.kwargs = response, error, None

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


def anthropic_with(monkeypatch, fake):
    p = llm.AnthropicProvider('claude-opus-5-5', api_key='test-key')
    monkeypatch.setattr(p.client.beta.messages, 'parse', fake)
    return p


def test_anthropic_request_shape(monkeypatch, settings):
    settings.LLM_EFFORT = 'medium'
    ok = assistant.DraftSet(drafts=[])
    fake = FakeParse(SimpleNamespace(stop_reason='end_turn', parsed_output=ok))
    assert anthropic_with(monkeypatch, fake).generate('sys', 'figures', assistant.DraftSet) is ok
    k = fake.kwargs
    assert k['model'] == 'claude-opus-5-5' and k['output_format'] is assistant.DraftSet and k['system'] == 'sys'
    assert k['fallbacks'] == 'default' and k['betas'] == ['server-side-fallback-2026-07-01']
    assert k['output_config'] == {'effort': 'medium'} and k['messages'] == [{'role': 'user', 'content': 'figures'}]


@pytest.mark.parametrize('resp', [SimpleNamespace(stop_reason='refusal', parsed_output=None),
                                  SimpleNamespace(stop_reason='max_tokens', parsed_output=None)])
def test_anthropic_unusable_answers(monkeypatch, resp):
    with pytest.raises(llm.LLMUnavailable):
        anthropic_with(monkeypatch, FakeParse(resp)).generate('s', 'p', assistant.DraftSet)


def test_anthropic_network_error(monkeypatch):
    import anthropic
    import httpx2
    err = anthropic.APIConnectionError(request=httpx2.Request('POST', 'https://api.anthropic.com/v1/messages'))
    with pytest.raises(llm.LLMUnavailable):
        anthropic_with(monkeypatch, FakeParse(error=err)).generate('s', 'p', assistant.DraftSet)


def test_openai_compatible_provider(monkeypatch):
    p = llm.OpenAICompatibleProvider('uni-model', 'http://llm.internal/v1', api_key='k')
    sent = {}

    def fake_open(req, timeout):
        sent['url'], sent['body'], sent['auth'] = req.full_url, json.loads(req.data), req.get_header('Authorization')
        return io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps({'drafts': [draft('concept:1')]})}}]}).encode())
    monkeypatch.setattr(p._direct, 'open', fake_open)
    out = p.generate('sys', 'figures', assistant.DraftSet)
    assert out.drafts[0].evidence_id == 'concept:1'
    assert sent['url'] == 'http://llm.internal/v1/chat/completions' and sent['auth'] == 'Bearer k'
    assert sent['body']['response_format']['type'] == 'json_schema' and sent['body']['model'] == 'uni-model'

    monkeypatch.setattr(p._direct, 'open', lambda req, timeout: io.BytesIO(b'{"choices":[{"message":{"content":"not json"}}]}'))
    with pytest.raises(llm.LLMUnavailable):
        p.generate('sys', 'figures', assistant.DraftSet)


def test_provider_choice(settings):
    settings.LLM_PROVIDER = ''
    assert llm.provider() is None and not llm.describe()['on']
    settings.LLM_PROVIDER, settings.LLM_MODEL, settings.LLM_API_KEY = 'anthropic', '', 'test-key'
    assert llm.provider().model == 'claude-opus-5-5'
    settings.LLM_PROVIDER, settings.LLM_BASE_URL, settings.LLM_MODEL = 'openai_compatible', '', 'x'
    assert llm.provider() is None   # no address, no provider
