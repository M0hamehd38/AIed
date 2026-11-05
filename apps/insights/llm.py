"""Language-model providers for the assistant (phase 4).

One small interface, `Provider.generate(system, prompt, schema)`, returns an instance of a Pydantic model.
Which provider runs is a deployment setting (LLM_PROVIDER):
  ''                   — none: only the rule-based drafts s1–s4
  'anthropic'          — Claude through the official `anthropic` SDK
  'openai_compatible'  — a model the university runs itself behind an OpenAI-style /chat/completions endpoint
Callers only ever pass aggregated, anonymous course figures (see assistant.brief); nothing here sees people.
"""
import json
import urllib.error
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


class OpenAICompatibleProvider(Provider):
    """For a model served inside the university (vLLM, Ollama, TGI, …) with an OpenAI-style chat endpoint."""
    name = 'openai_compatible'
    # the service is on the internal network: never route it through an HTTP proxy from the environment
    _direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def __init__(self, model, base_url, api_key='', timeout=120):
        self.model, self.base_url, self.api_key, self.timeout = model, base_url.rstrip('/'), api_key, timeout

    def generate(self, system, prompt, schema):
        body = {'model': self.model,
                'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}],
                'response_format': {'type': 'json_schema',
                                    'json_schema': {'name': schema.__name__, 'schema': schema.model_json_schema(), 'strict': True}}}
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        req = urllib.request.Request(self.base_url + '/chat/completions', data=json.dumps(body).encode(), headers=headers, method='POST')
        try:
            with self._direct.open(req, timeout=self.timeout) as r:
                text = json.loads(r.read().decode('utf-8'))['choices'][0]['message']['content']
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError) as e:
            raise LLMUnavailable('connection') from e
        try:
            return schema.model_validate_json(text)
        except ValidationError as e:
            raise LLMUnavailable('malformed') from e


def provider():
    """The configured provider, or None when the assistant runs on rules only."""
    kind = settings.LLM_PROVIDER
    if kind == 'anthropic':
        return AnthropicProvider(settings.LLM_MODEL or 'claude-opus-5-5', settings.LLM_API_KEY, settings.LLM_TIMEOUT)
    if kind == 'openai_compatible' and settings.LLM_BASE_URL and settings.LLM_MODEL:
        return OpenAICompatibleProvider(settings.LLM_MODEL, settings.LLM_BASE_URL, settings.LLM_API_KEY, settings.LLM_TIMEOUT)
    return None


def describe():
    """For the panel: which model would answer, in words a teacher can read."""
    kind = settings.LLM_PROVIDER
    if kind == 'anthropic':
        return {'on': True, 'label': f'Claude ({settings.LLM_MODEL or "claude-opus-5-5"})', 'where': 'سرویس ابری Anthropic'}
    if kind == 'openai_compatible' and settings.LLM_BASE_URL and settings.LLM_MODEL:
        return {'on': True, 'label': settings.LLM_MODEL, 'where': 'سرور داخلی دانشگاه'}
    return {'on': False, 'label': '', 'where': ''}
