import pytest

from eval import metrics


def test_set_f1_known_values():
    assert metrics.set_f1([], []) == 1.0
    assert metrics.set_f1(['a'], []) == 0.0
    assert metrics.set_f1([], ['a']) == 0.0
    assert metrics.set_f1(['a', 'b'], ['a', 'b']) == 1.0
    assert metrics.set_f1(['a', 'b'], ['a']) == pytest.approx(2 / 3)
    assert metrics.set_f1(['a'], ['a', 'b']) == pytest.approx(2 / 3)


def test_macro_f1_averages_rows():
    assert metrics.macro_f1([(['a'], ['a']), (['b'], ['c'])]) == pytest.approx(0.5)
    assert metrics.macro_f1([]) is None


def test_exact_rate_and_rate():
    assert metrics.exact_rate([(1, 1), (1, 2)]) == 0.5
    assert metrics.rate([True, False, True]) == pytest.approx(2 / 3)
    assert metrics.rate([]) is None


def test_percentile_interpolates():
    assert metrics.percentile([10], 95) == 10.0
    assert metrics.percentile([1, 2, 3, 4], 50) == pytest.approx(2.5)
    assert metrics.percentile([1, 2, 3, 4, 5], 100) == 5.0
    assert metrics.percentile([], 95) is None


def test_recall_at_k():
    assert metrics.recall_at_k(['a', 'b'], ['a', 'c'], 10) == 0.5
    assert metrics.recall_at_k(['x'], ['a', 'b', 'c'], 2) == 0.0
    assert metrics.recall_at_k([], []) == 1.0


def test_cosine_rejects_mismatched_and_zero_vectors():
    assert metrics.cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert metrics.cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert metrics.cosine([0, 0], [1, 1]) is None
    assert metrics.cosine([1], [1, 1]) is None


def test_quote_recall_counts_verbatim_spans():
    assert metrics.quote_recall(['九成新'], ['成色九成新以上']) == 1.0
    assert metrics.quote_recall(['九成新', '燕园'], ['九成新']) == 0.5
    assert metrics.quote_recall([], ['任意']) == 1.0
    assert metrics.quote_recall(['x'], []) == 0.0


def test_grounding_rate_requires_verbatim_match():
    sources = ['静音鼠标', '附接收器']
    assert metrics.grounding_rate(['静音鼠标', '接收器'], sources) == 1.0
    assert metrics.grounding_rate(['静音鼠标', '无线'], sources) == 0.5
    assert metrics.grounding_rate([], sources) == 1.0


def test_passes_handles_min_max_and_missing():
    assert metrics.passes(0.9, {'min': 0.8}) is True
    assert metrics.passes(0.7, {'min': 0.8}) is False
    assert metrics.passes(10, {'max': 5}) is False
    assert metrics.passes(None, {'min': 0.8}) is None
    assert metrics.passes(1, {}) is None
