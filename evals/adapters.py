"""Exercise the production parsers/prompts in an isolated sequential evaluator.

The patch is local to this CLI process and never runs inside the web server.
It makes the existing chat_json boundary observable without duplicating prompts
or changing production fallback/validation behavior.
"""
import copy
import time
from types import SimpleNamespace
from unittest.mock import patch

from .common import digest
from .providers import CallFailure, RemoteClient

# Do not load the application's .env while importing the pure business functions.
with patch('dotenv.load_dotenv', return_value=False):
    from app import buyer_agent, services
    from app.schemas import ParsedIntent, ParsedItem


def _invoke(case, settings):
    task, data = case['task'], case['input']
    if task == 'candidate_review':
        values = buyer_agent.review_candidates(data['intent'], data['items'], settings)
        return {'assessments': [value.model_dump(mode='json') for value in values]}
    entry = {'intent_parse': services.parse_intent, 'item_parse': services.parse_item,
             'wanted_parse': services.parse_wanted}[task]
    return entry(data['text'], settings).model_dump(mode='json')


def evaluate(case, profile, key, *, client=None, sleep=time.sleep, vision_images=None, search_context=None):
    if case['task'] == 'smart_search':
        from .search_eval import evaluate_search
        return evaluate_search(case, profile, key, search_context, client=client, sleep=sleep)
    started = time.perf_counter()
    settings = SimpleNamespace(ai_mode=profile['mode'])
    result = {'status': 'ok', 'error': None, 'output': None, 'raw_output': None,
              'raw_score_output': None, 'raw_content': None, 'fallback_used': False,
              'attempts': [], 'usage': None, 'cost_cny': 0.0 if profile['mode'] == 'local' else None,
              'prompt_hash': None}
    remote = RemoteClient(profile, key, client=client, sleep=sleep) if profile['mode'] == 'remote' else None

    def observed_chat(system, payload, ignored_settings, max_tokens=2500):
        result['prompt_hash'] = digest({'system': system, 'max_tokens': profile.get('max_tokens') or max_tokens,
                                       'response_format': 'json_object'})
        try:
            raw = remote(system, payload, max_tokens=max_tokens)
            # A deep copy keeps Pydantic guards from changing the preserved raw response.
            result['raw_output'] = copy.deepcopy(raw)
            if case['task'] in {'intent_parse', 'wanted_parse'}:
                parsed = ParsedIntent.model_validate(raw)
                if case['task'] == 'wanted_parse':
                    projected = services.parse_wanted(case['input']['text'], settings, parser=lambda *_: parsed)
                    result['raw_score_output'] = projected.model_dump(mode='json')
                else:
                    result['raw_score_output'] = copy.deepcopy(raw)
            elif case['task'] == 'item_parse':
                ParsedItem.model_validate(raw)
                result['raw_score_output'] = copy.deepcopy(raw)
            else:
                result['raw_score_output'] = copy.deepcopy(raw)
            return copy.deepcopy(raw)
        except CallFailure as exc:
            result['error'] = exc.code
            raise buyer_agent.ModelUnavailable(exc.code) from None
        except (ValueError, TypeError):
            result['error'] = 'schema_error'
            raise buyer_agent.ModelUnavailable('schema_error') from None

    try:
        if case['task'] == 'vision_draft':
            from backend.app.vision import SYSTEM_PROMPT, VisionDraft, vision_content
            if remote is None or not vision_images:
                raise ValueError('vision requires a remote model and verified images')
            result['prompt_hash'] = digest({'system': SYSTEM_PROMPT,
                'max_tokens': profile.get('max_tokens') or 1200, 'response_format': 'json_object'})
            try:
                raw = remote(SYSTEM_PROMPT, vision_content(vision_images, case['input'].get('note', '')),
                             max_tokens=1200, multimodal=True)
                result['raw_output'] = copy.deepcopy(raw)
                result['raw_score_output'] = copy.deepcopy(raw)
                result['output'] = VisionDraft.model_validate(raw, strict=True).model_dump(mode='json')
            except CallFailure as exc:
                result['error'] = exc.code
            except (ValueError, TypeError):
                result['error'] = 'schema_error'
        elif remote:
            with patch.object(services, 'chat_json', observed_chat), patch.object(buyer_agent, 'chat_json', observed_chat):
                result['output'] = _invoke(case, settings)
        else:
            result['output'] = _invoke(case, settings)
    except Exception as exc:
        # The result records a stable category, never provider error bodies/credentials.
        from fastapi import HTTPException
        if isinstance(exc, (buyer_agent.ModelUnavailable, HTTPException, ValueError, TypeError)):
            result['error'] = result['error'] or 'output_validation_error'
        else:
            raise
    result['latency_ms'] = round((time.perf_counter() - started) * 1000, 3)
    if result['error']:
        result['status'] = 'error'
        result['fallback_used'] = result['output'] is not None
    if remote:
        result['attempts'] = remote.attempts
        result['raw_content'] = remote.raw_content
        if result['raw_output'] is None:
            result['raw_output'] = remote.raw_output
        if remote.attempts and all(a['cost_cny'] is not None for a in remote.attempts):
            result['cost_cny'] = sum(a['cost_cny'] for a in remote.attempts)
        if remote.attempts and all(isinstance(a['usage'], dict) for a in remote.attempts):
            keys = ('prompt_tokens', 'completion_tokens', 'total_tokens')
            if all(type(a['usage'].get(k)) is int and a['usage'][k] >= 0 for a in remote.attempts for k in keys):
                result['usage'] = {k: sum(a['usage'][k] for a in remote.attempts) for k in keys}
    return result
