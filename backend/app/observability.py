"""Low-cardinality metrics for remote AI operations; never record inputs or user identifiers."""
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic

from prometheus_client import Counter, Histogram

MODEL_CALLS = Counter('yandu_model_calls_total', 'Remote model operations by outcome',
                      ['node', 'status'])
MODEL_LATENCY = Histogram('yandu_model_latency_seconds', 'Remote operation duration, including retries',
                          ['node'], buckets=(.25, .5, 1, 2, 5, 10, 20, 30, 60, 120))
MODEL_TOKENS = Counter('yandu_model_tokens_total', 'Tokens reported in the final provider response',
                       ['node', 'kind'])
MODEL_FALLBACKS = Counter('yandu_model_fallbacks_total', 'Operations falling back from remote AI to local rules',
                          ['node'])
_ACTIVE = ContextVar('yandu_model_usage', default=None)


@contextmanager
def model_operation(node):
    """Count one logical operation, after application validation, not one per retry."""
    started = monotonic()
    usage = {}
    reset = _ACTIVE.set(usage)
    status = 'error'
    try:
        yield
        status = 'ok'
    finally:
        _ACTIVE.reset(reset)
        MODEL_CALLS.labels(node=node, status=status).inc()
        MODEL_LATENCY.labels(node=node).observe(monotonic() - started)
        for kind, value in usage.items():
            MODEL_TOKENS.labels(node=node, kind=kind).inc(value)


def collect_provider_usage(body):
    current = _ACTIVE.get()
    usage = body.get('usage') if isinstance(body, dict) else None
    if current is None:
        return
    current.clear()
    if not isinstance(usage, dict):
        return
    for field, kind in (('prompt_tokens', 'input'), ('completion_tokens', 'output')):
        value = usage.get(field)
        if type(value) is int and 0 <= value <= 10**12:
            current[kind] = value
