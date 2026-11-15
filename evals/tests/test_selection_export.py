import json

import pytest

from scripts.summarize_selection_experiment import export, paired_bootstrap


def test_bootstrap_keeps_paraphrases_and_repeats_in_their_family():
    cases = {str(i): {'family': 'shared' if i < 3 else 'independent'} for i in range(4)}
    a, b = [], []
    for cid in cases:
        for repeat in range(1, 4):
            for rows, value in ((a, 1.0 if cid != '3' else 0.0),
                                (b, 0.0 if cid != '3' else 1.0)):
                rows.append({'case_id': cid, 'repeat': repeat, 'score': {'metrics': {'mrr': value}}})
    result = paired_bootstrap(a, b, cases, 'mrr', iterations=2000, seed=11)
    # Four queries belong to two families, regardless of the twelve executions.
    # Resampling both families gives 0.5; taking only one family gives +1 or -1.
    assert result['cases'] == 4 and result['families'] == 2
    assert result['difference_a_minus_b'] == .5
    assert (result['ci95_low'], result['ci95_high']) == (-1.0, 1.0)
    with pytest.raises(ValueError, match='same eligible cases'):
        paired_bootstrap(a, [r for r in b if r['case_id'] != '3'], cases, 'mrr', 10, 11)


def test_incomplete_run_cannot_be_exported_as_experimental_evidence(tmp_path):
    run = tmp_path / 'run'
    run.mkdir()
    (run / 'manifest.json').write_text(json.dumps({'complete': False}), encoding='utf-8')
    destination = tmp_path / 'export'
    with pytest.raises(ValueError, match='completed run'):
        export(run, destination)
    assert not destination.exists()
