"""Explicit model profiles and a bounded, observable chat-completions client.

No .env is read. Only the environment variables named by the selected profiles
are used. The profile returned to reports never contains credentials.
"""
import json
import os
import time
from typing import Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from .common import read_json

TASKS = {'intent_parse', 'item_parse', 'wanted_parse', 'candidate_review', 'vision_draft', 'smart_search'}


class Pricing(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    input_per_million_cny: float = Field(ge=0)
    output_per_million_cny: float = Field(ge=0)
    cached_input_per_million_cny: float | None = Field(default=None, ge=0)
    source: str = Field(min_length=1)
    checked_at: str = Field(min_length=1)


class Profile(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
    mode: Literal['local', 'remote', 'oracle']
    tasks: list[str] = Field(min_length=1)
    model: str | None = None
    model_env: str | None = None
    base_url: str | None = None
    base_url_env: str | None = None
    api_key_env: str | None = None
    thinking: Literal['enabled', 'disabled'] | None = None
    temperature: float = Field(default=0.1, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=32000)
    timeout: float = Field(default=30, ge=1, le=120)
    retries: int = Field(default=0, ge=0, le=3)
    pricing: Pricing | None = None

    @model_validator(mode='after')
    def validate_profile(self):
        if len(set(self.tasks)) != len(self.tasks) or not set(self.tasks) <= TASKS:
            raise ValueError('Tasks must be unique supported task names')
        if self.mode in {'local', 'oracle'}:
            if {'candidate_review', 'vision_draft'} & set(self.tasks):
                raise ValueError('The local rules do not implement candidate review or vision')
            if any((self.model, self.model_env, self.base_url, self.base_url_env, self.api_key_env, self.pricing)):
                raise ValueError('Local rules cannot have provider settings')
            if self.mode == 'oracle' and self.tasks != ['smart_search']:
                raise ValueError('Oracle only supports smart_search')
        else:
            if bool(self.model) == bool(self.model_env) or bool(self.base_url) == bool(self.base_url_env):
                raise ValueError('Choose exactly one model/model_env and base_url/base_url_env')
            if not self.api_key_env:
                raise ValueError('Remote profiles require api_key_env, never an inline key')
        return self


def load_profiles(path):
    value = read_json(path)
    if not isinstance(value, dict) or set(value) != {'version', 'models'} or type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Model configuration requires version=1 and models')
    if not isinstance(value['models'], list) or not value['models']:
        raise ValueError('At least one model profile is required')
    profiles = [Profile.model_validate(item) for item in value['models']]
    if len({p.id for p in profiles}) != len(profiles):
        raise ValueError('Duplicate model profile ID')
    return profiles


def resolve_profile(profile):
    public = profile.model_dump(exclude={'model_env', 'base_url_env', 'api_key_env'})
    if profile.mode in {'local', 'oracle'}:
        public['model'] = 'gold-intent-injection' if profile.mode == 'oracle' else 'local-keyword-rules'
        return public, SecretStr('')
    model = profile.model or os.getenv(profile.model_env or '')
    base_url = profile.base_url or os.getenv(profile.base_url_env or '')
    key = os.getenv(profile.api_key_env or '')
    if not model or not model.strip() or not base_url or not key or not key.strip():
        raise ValueError(f'{profile.id}: configure model, base URL and API key environment variables')
    url = urlparse(base_url)
    try:
        port = url.port
    except ValueError:
        raise ValueError(f'{profile.id}: invalid API port') from None
    if url.scheme != 'https' or not url.hostname or port == 0 or url.username or url.password or url.query or url.fragment:
        raise ValueError(f'{profile.id}: base URL must be HTTPS without credentials/query/fragment')
    public.update(model=model.strip(), base_url=base_url.rstrip('/'))
    return public, SecretStr(key)


def usage_cost(usage, pricing):
    """Unknown usage/pricing stays unknown, including potentially billed failures."""
    if not isinstance(usage, dict) or not pricing:
        return None
    prompt = usage.get('prompt_tokens')
    completion = usage.get('completion_tokens')
    if any(type(v) is not int or v < 0 for v in (prompt, completion)):
        return None
    details = usage.get('prompt_tokens_details') or {}
    if not isinstance(details, dict):
        return None
    cached = details.get('cached_tokens', usage.get('prompt_cache_hit_tokens', 0))
    if type(cached) is not int or not 0 <= cached <= prompt:
        return None
    if cached and pricing.get('cached_input_per_million_cny') is None:
        return None
    cached_rate = pricing.get('cached_input_per_million_cny') or 0
    return ((prompt - cached) * pricing['input_per_million_cny'] + cached * cached_rate
            + completion * pricing['output_per_million_cny']) / 1_000_000


def usage_metadata(value):
    """Preserve documented token counters, never arbitrary provider metadata."""
    if not isinstance(value, dict):
        return None
    result = {}
    for key in ('prompt_tokens', 'completion_tokens', 'total_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens'):
        if key in value:
            if type(value[key]) is not int or value[key] < 0:
                return None
            result[key] = value[key]
    for key in ('prompt_tokens_details', 'completion_tokens_details'):
        if key in value and value[key] is not None:
            if not isinstance(value[key], dict):
                return None
            details = {name: number for name, number in value[key].items()
                       if name in {'cached_tokens', 'reasoning_tokens', 'audio_tokens', 'accepted_prediction_tokens', 'rejected_prediction_tokens'}}
            if any(type(number) is not int or number < 0 for number in details.values()):
                return None
            result[key] = details
    return result or None


class CallFailure(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class RemoteClient:
    def __init__(self, profile, key, *, client=None, sleep=time.sleep):
        self.profile = profile
        self.key = key
        self.client = client
        self.sleep = sleep
        self.attempts = []
        self.raw_output = None
        self.raw_content = None
        self.error = None

    def __call__(self, system, payload, settings=None, max_tokens=2500, *, multimodal=False):
        request = {
            'model': self.profile['model'], 'temperature': self.profile['temperature'],
            'max_tokens': self.profile.get('max_tokens') or max_tokens,
            'response_format': {'type': 'json_object'},
            'messages': [{'role': 'system', 'content': system},
                         {'role': 'user', 'content': payload if multimodal else json.dumps(payload, ensure_ascii=False)}],
        }
        if self.profile.get('thinking'):
            request['thinking'] = {'type': self.profile['thinking']}
        owned_client = self.client is None
        client = self.client or httpx.Client(timeout=self.profile['timeout'], follow_redirects=False)
        try:
            for index in range(self.profile['retries'] + 1):
                started = time.perf_counter()
                attempt = {'status': 'error', 'error': None, 'usage': None, 'cost_cny': None,
                           'returned_model': None, 'elapsed_ms': 0.0}
                retryable = False
                try:
                    response = client.post(self.profile['base_url'] + '/chat/completions', json=request,
                        headers={'Authorization': f'Bearer {self.key.get_secret_value()}'},
                        timeout=self.profile['timeout'])
                    if response.status_code >= 400:
                        retryable = response.status_code == 429 or response.status_code >= 500
                        raise CallFailure(f'http_{response.status_code}')
                    if response.status_code >= 300:
                        raise CallFailure('unexpected_redirect')
                    try:
                        body = response.json()
                        if not isinstance(body, dict):
                            raise ValueError()
                        attempt['usage'] = usage_metadata(body.get('usage'))
                        attempt['returned_model'] = body.get('model') if isinstance(body.get('model'), str) else None
                        attempt['cost_cny'] = usage_cost(attempt['usage'], self.profile.get('pricing'))
                        choice = body['choices'][0]
                        reasoning = choice['message'].get('reasoning_content')
                        attempt['reasoning_char_count'] = len(reasoning) if isinstance(reasoning, str) else None
                        content = choice['message']['content']
                        if not isinstance(content, str):
                            raise ValueError()
                        self.raw_content = content
                        if choice.get('finish_reason') == 'length':
                            raise CallFailure('truncated_output')
                        if multimodal and choice.get('finish_reason') != 'stop':
                            raise CallFailure('incomplete_output')
                        parsed = json.loads(content, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                        # 1e999 is legal JSON syntax but overflows Python's float;
                        # reject it before an unserializable value reaches records.
                        json.dumps(parsed, allow_nan=False)
                        if not isinstance(parsed, dict):
                            raise ValueError()
                        self.raw_output = parsed
                    except (ValueError, TypeError, KeyError, IndexError):
                        raise CallFailure('invalid_json_response') from None
                    attempt['status'] = 'ok'
                except httpx.TimeoutException:
                    attempt['error'], retryable = 'timeout', True
                except httpx.RequestError:
                    attempt['error'], retryable = 'network_error', True
                except CallFailure as exc:
                    attempt['error'] = exc.code
                finally:
                    attempt['elapsed_ms'] = round((time.perf_counter() - started) * 1000, 3)
                    self.attempts.append(attempt)
                if attempt['status'] == 'ok':
                    return self.raw_output
                if not retryable or index == self.profile['retries']:
                    self.error = attempt['error']
                    raise CallFailure(self.error)
                self.sleep(min(2 ** index, 4))
        finally:
            if owned_client:
                client.close()
