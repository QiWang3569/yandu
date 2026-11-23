"""Pure metric functions used by the evaluation runner and its unit tests."""
import math


def set_f1(gold, pred):
    gold, pred = set(gold), set(pred)
    if not gold and not pred:
        return 1.0
    if not gold or not pred:
        return 0.0
    tp = len(gold & pred)
    if not tp:
        return 0.0
    precision = tp / len(pred)
    recall = tp / len(gold)
    return 2 * precision * recall / (precision + recall)


def macro_f1(pairs):
    values = [set_f1(gold, pred) for gold, pred in pairs]
    return sum(values) / len(values) if values else None


def exact_rate(pairs):
    values = [1.0 if gold == pred else 0.0 for gold, pred in pairs]
    return sum(values) / len(values) if values else None


def rate(flags):
    flags = list(flags)
    return sum(1.0 for flag in flags if flag) / len(flags) if flags else None


def mean(values):
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def percentile(values, pct):
    values = sorted(value for value in values if value is not None)
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    position = (len(values) - 1) * pct / 100
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return float(values[low])
    return values[low] + (values[high] - values[low]) * (position - low)


def recall_at_k(relevant, ranked, k=10):
    relevant = set(relevant)
    if not relevant:
        return 1.0
    return len(relevant & set(ranked[:k])) / len(relevant)


def cosine(a, b):
    if not a or not b or len(a) != len(b):
        return None
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return None
    return max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b)) / (norm_a * norm_b)))


def quote_recall(gold_quotes, pred_quotes):
    gold = [quote for quote in gold_quotes if quote]
    if not gold:
        return 1.0
    pred = [quote for quote in pred_quotes if isinstance(quote, str) and quote]
    return sum(any(quote in candidate for candidate in pred) for quote in gold) / len(gold)


def grounding_rate(quotes, sources):
    quotes = [quote for quote in quotes if isinstance(quote, str) and quote]
    if not quotes:
        return 1.0
    joined = sources if isinstance(sources, str) else ' '.join(sources)
    return sum(quote in joined for quote in quotes) / len(quotes)


def passes(value, rule):
    """Return True/False/None (None when the metric is missing)."""
    if value is None:
        return None
    if 'min' in rule:
        return value >= rule['min']
    if 'max' in rule:
        return value <= rule['max']
    return None