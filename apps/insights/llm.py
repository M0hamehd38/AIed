"""Language-model providers for the assistant (phase 4).

One small interface, `Provider.generate(system, prompt, schema)`, returns an instance of a Pydantic model.
Which provider runs is a deployment setting (LLM_PROVIDER):
  ''                   — none: only the rule-based drafts s1–s4
  'anthropic'          — Claude through the official `anthropic` SDK
  'openai_compatible'  — a model the university runs itself behind an OpenAI-style /chat/completions endpoint
  'openrouter'         — a model on OpenRouter; by default the free DeepSeek V4 Flash (deepseek/deepseek-v4-flash:free)
Callers only ever pass aggregated, anonymous course figures (see assistant.brief); nothing here sees people.
"""
import ipaddress
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from pydantic import BaseModel, ValidationError


class LLMUnavailable(Exception):
    """The model could not give a usable answer: not configured, unreachable, refused or malformed."""


class Provider:
    name = ''
    model = ''

    def generate(self, system: str, prompt: str, schema: type[BaseModel]) -> BaseModel:
        raise NotImplementedError


class AnthropicProvider(Provider):
    name = 'anthropic'

    def __init__(self, model, api_key='', timeout=120):
        import anthropic
        self.model = model
        self._anthropic = anthropic
        # without an explicit key the SDK uses ANTHROPIC_API_KEY (or a signed-in profile) from the environment
        self.client = anthropic.Anthropic(**({'api_key': api_key} if api_key else {}), timeout=timeout, max_retries=2)

    def generate(self, system, prompt, schema):
        a = self._anthropic
        try:
            response = self.client.beta.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{'role': 'user', 'content': prompt}],
                output_format=schema,
                output_config={'effort': settings.LLM_EFFORT},
                # if a safety classifier declines, the API retries on a suitable model inside the same call
                betas=['server-side-fallback-2026-07-01'],
                fallbacks='default',
            )
        except a.APIConnectionError as e:   # includes timeouts
            raise LLMUnavailable('connection') from e
        except a.RateLimitError as e:
            raise LLMUnavailable('rate_limited') from e
        except a.AuthenticationError as e:
            raise LLMUnavailable('auth') from e
        except a.APIStatusError as e:
            raise LLMUnavailable(f'status {e.status_code}') from e
        if response.stop_reason == 'refusal':
            raise LLMUnavailable('refusal')
        if response.stop_reason == 'max_tokens' or response.parsed_output is None:
            raise LLMUnavailable('incomplete')
        return response.parsed_output


def _internal(url):
    """True for addresses on the university's own network, which must not go through an outbound proxy."""
    host = urllib.parse.urlsplit(url).hostname or ''
    if host == 'localhost' or '.' not in host or host.endswith(('.local', '.internal', '.lan')):
        return True
    try:
        return ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _json_text(text):
    """The JSON object in a reply, also when a model wraps it in a ```json fence or adds a sentence around it."""
    text = (text or '').strip()
    fenced = re.search(r'```(?:json)?\s*(\{.*\})\s*```', text, re.S)
    if fenced:
        return fenced.group(1)
    start, end = text.find('{'), text.rfind('}')
    return text[start:end + 1] if start != -1 and end > start else text


class OpenAICompatibleProvider(Provider):
    """Any OpenAI-style /chat/completions endpoint: a model inside the university (vLLM, Ollama, TGI, …) or OpenRouter.

    Not every endpoint supports a JSON schema in `response_format`, so it asks in three steps, each only if the
    one before is refused: strict JSON schema, then plain JSON mode, then the schema spelled out in the prompt.
    Whatever comes back is validated against the same Pydantic model."""
    name = 'openai_compatible'
    # internal hosts are reached directly; public ones (OpenRouter) through the environment's proxy settings
    _direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    _public = urllib.request.build_opener()
    MODES = ('json_schema', 'json_object', 'prompt')

    def __init__(self, model, base_url, api_key='', timeout=120, headers=None):
        self.model, self.base_url, self.api_key, self.timeout = model, base_url.rstrip('/'), api_key, timeout
        self.extra_headers = headers or {}
        self._opener = self._direct if _internal(self.base_url) else self._public

    def _body(self, system, prompt, schema, mode):
        js = schema.model_json_schema()
        if mode != 'json_schema':
            system = (f'{system}\n\nReply with one JSON object only, no other text, matching this JSON schema:\n'
                      + json.dumps(js, ensure_ascii=False))
        body = {'model': self.model, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}]}
        if mode == 'json_schema':
            body['response_format'] = {'type': 'json_schema', 'json_schema': {'name': schema.__name__, 'schema': js, 'strict': True}}
        elif mode == 'json_object':
            body['response_format'] = {'type': 'json_object'}
        return body

    def generate(self, system, prompt, schema):
        headers = {'Content-Type': 'application/json', **self.extra_headers}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        for mode in self.MODES:
            req = urllib.request.Request(self.base_url + '/chat/completions', headers=headers, method='POST',
                                         data=json.dumps(self._body(system, prompt, schema, mode)).encode())
            try:
                with self._opener.open(req, timeout=self.timeout) as r:
                    text = json.loads(r.read().decode('utf-8'))['choices'][0]['message']['content']
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    raise LLMUnavailable('rate_limited') from e
                if e.code in (401, 403):
                    raise LLMUnavailable('auth') from e
                if e.code in (400, 404, 415, 422) and mode != self.MODES[-1]:
                    continue   # this endpoint does not take that response_format: ask more simply
                raise LLMUnavailable(f'status {e.code}') from e
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError) as e:
                raise LLMUnavailable('connection') from e
            try:
                return schema.model_validate_json(_json_text(text))
            except ValidationError as e:
                raise LLMUnavailable('malformed') from e
        raise LLMUnavailable('malformed')


def provider():
    """The configured provider, or None when the assistant runs on rules only."""
    kind = settings.LLM_PROVIDER
    if kind == 'anthropic':
        return AnthropicProvider(settings.LLM_MODEL or 'claude-opus-5-5', settings.LLM_API_KEY, settings.LLM_TIMEOUT)
    if kind == 'openai_compatible' and settings.LLM_BASE_URL and settings.LLM_MODEL:
        return OpenAICompatibleProvider(settings.LLM_MODEL, settings.LLM_BASE_URL, settings.LLM_API_KEY, settings.LLM_TIMEOUT)
    if kind == 'openrouter' and settings.LLM_API_KEY:
        p = OpenAICompatibleProvider(settings.LLM_MODEL or OPENROUTER_MODEL, settings.LLM_BASE_URL or OPENROUTER_URL,
                                     settings.LLM_API_KEY, settings.LLM_TIMEOUT, headers={'X-Title': 'Classyar'})
        p.name = 'openrouter'
        return p
    return None


OPENROUTER_URL = 'https://openrouter.ai/api/v1'
OPENROUTER_MODEL = 'deepseek/deepseek-v4-flash:free'   # DeepSeek V4 Flash, free tier (daily request cap)


def describe():
    """For the panel: which model would answer, in words a teacher can read."""
    kind = settings.LLM_PROVIDER
    if kind == 'anthropic':
        return {'on': True, 'label': f'Claude ({settings.LLM_MODEL or "claude-opus-5-5"})', 'where': 'سرویس ابری Anthropic'}
    if kind == 'openai_compatible' and settings.LLM_BASE_URL and settings.LLM_MODEL:
        return {'on': True, 'label': settings.LLM_MODEL, 'where': 'سرور داخلی دانشگاه'}
    if kind == 'openrouter' and settings.LLM_API_KEY:
        model = settings.LLM_MODEL or OPENROUTER_MODEL
        free = model.endswith(':free')
        return {'on': True, 'label': 'DeepSeek V4 Flash (رایگان)' if model == OPENROUTER_MODEL else model,
                'where': 'سرویس ابری OpenRouter' + ('؛ نسخه‌ی رایگان با سقف درخواست روزانه' if free else '')}
    return {'on': False, 'label': '', 'where': ''}
