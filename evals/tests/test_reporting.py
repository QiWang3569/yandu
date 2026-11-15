import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.reporting import compare_runs, summarize, validate_policy, write_reports


def policy():
    return {"version": "test", "status": "locked", "minimum_reviewed_cases": 1,
            "tasks": {"intent_parse": {"min_pass_rate": 0.9, "max_error_rate": 0.05}}}


def manifest(case_ids=("a",), models=("model-a", "model-b"), split="holdout"):
    return {"run_id": "run", "created_at": "2026-11-15T01:00:00+08:00", "git_sha": "abc", "dirty": False,
            "dataset_hash": "dataset", "scorer_version": "1", "repeats": 1, "complete": True,
            "policy_hash": "policy", "models": [{"id": model, "mode": "remote", "model": model,
                                                 "tasks": ["intent_parse"], "temperature": 0.1} for model in models],
            "cases": [{"id": cid, "hash": "hash-" + cid, "task": "intent_parse", "split": split,
                       "label_status": "reviewed"} for cid in case_ids]}


def row(cid="a", model="model-a", passed=True, cost=0.01, status="ok", split="holdout"):
    score = {"passed": passed, "score": float(passed), "checks": [{"field": "category", "passed": passed}],
             "metrics": {"schema_valid": status == "ok"}}
    return {"case_id": cid, "case_hash": "hash-" + cid, "task": "intent_parse", "split": split,
            "label_status": "reviewed", "model": model, "repeat": 1, "status": status,
            "error": "timeout" if status == "error" else None, "latency_ms": 100,
            "attempts": [{"elapsed_ms": 100, "status": status}], "cost_cny": cost,
            "raw_score": copy.deepcopy(score), "score": score, "fallback_used": False,
            "prompt_hash": "prompt-1"}


def test_unknown_cost_is_not_zero_and_failed_rows_stay_in_denominator():
    config = manifest(("a", "b"), ("model-a",))
    rows = [row(), row("b", passed=False, status="error", cost=None)]
    summary = summarize(rows, config, policy())
    group = summary["groups"][0]
    assert group["pass_rate"] == 0.5
    assert group["error_rate"] == 0.5
    assert group["total_cost_cny"] is None
    assert group["mean_cost_cny"] is None
    assert group["known_cost_subtotal_cny"] == 0.01
    assert group["unknown_cost_count"] == 1
    assert summary["selection"][0]["selected_model"] is None


def test_complete_reviewed_holdout_can_recommend_on_quality_then_cost():
    config = manifest()
    rows = [row(cost=0.03), row(model="model-b", cost=0.01)]
    result = summarize(rows, config, policy())["selection"][0]
    assert result["status"] == "recommended"
    assert result["selected_model"] == "model-b"


def test_unknown_cost_skips_cost_ranking_instead_of_rewarding_missing_usage():
    rows = [row(cost=0.03), row(model="model-b", cost=None)]
    rows[0]["latency_ms"] = 50
    rows[1]["latency_ms"] = 100
    result = summarize(rows, manifest(), policy())["selection"][0]
    assert result["selected_model"] == "model-a"
    assert any("费用存在未知值" in reason for reason in result["reasons"])


def test_draft_policy_never_produces_a_model_recommendation():
    draft = policy()
    draft["status"] = "draft"
    result = summarize([row(), row(model="model-b")], manifest(), draft)["selection"][0]
    assert result["selected_model"] is None
    assert any("规则仍为草案" in reason for reason in result["reasons"])


def test_aliases_of_the_same_provider_model_do_not_count_as_two_candidates():
    config = manifest()
    for profile in config["models"]:
        profile["model"] = "same-real-model"
        profile["base_url"] = "https://provider.example/v1/"
    result = summarize([row(), row(model="model-b")], config, policy())["selection"][0]
    assert result["selected_model"] is None
    assert any("相同模型" in reason for reason in result["reasons"])


@pytest.mark.parametrize("gate,value", [("min_pass_rate", -0.01), ("min_pass_rate", 1.01),
                                      ("max_error_rate", float("nan")), ("max_error_rate", float("inf")),
                                      ("min_pass_rate", True), ("min_pass_rate", "0.9"),
                                      ("min_pass_rtae", 0.9), ("error_rate", 0.9)])
def test_invalid_or_misspelled_policy_gates_are_rejected(gate, value):
    config = policy()
    config["tasks"]["intent_parse"] = {gate: value}
    with pytest.raises(ValueError):
        validate_policy(config)


@pytest.mark.parametrize("condition", ["dev", "draft", "incomplete", "missing_model", "missing_repeat", "duplicate", "hash_mismatch", "local"])
def test_incomplete_or_unreviewed_runs_never_select(condition):
    config = manifest()
    rows = [row(), row(model="model-b")]
    if condition == "dev":
        for case in config["cases"]:
            case["split"] = "dev"
        for item in rows:
            item["split"] = "dev"
    elif condition == "draft":
        config["cases"][0]["label_status"] = "draft"
    elif condition == "incomplete":
        config["complete"] = False
    elif condition == "missing_model":
        config["models"].append({"id": "model-c", "mode": "remote", "model": "model-c", "tasks": ["intent_parse"]})
    elif condition == "missing_repeat":
        config["repeats"] = 2
    elif condition == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    elif condition == "hash_mismatch":
        rows[0]["case_hash"] = "wrong"
    elif condition == "local":
        config["models"][0]["mode"] = "local"
    selection = summarize(rows, config, policy())["selection"][0]
    assert selection["selected_model"] is None
    assert selection["status"] == "insufficient_evidence"


def test_all_failures_remain_visible_and_no_candidate_qualifies():
    rows = [row(passed=False, status="error", cost=None), row(model="model-b", passed=False, status="error", cost=None)]
    summary = summarize(rows, manifest(), policy())
    assert all(group["pass_rate"] == 0 and group["error_rate"] == 1 for group in summary["groups"])
    assert summary["selection"][0]["status"] == "no_model_qualified"


def test_raw_and_application_results_are_separate():
    rows = [row()]
    rows[0]["raw_score"]["passed"] = False
    rows[0]["raw_score"]["score"] = 0
    rows[0]["application_score"] = copy.deepcopy(rows[0]["score"])
    result = summarize(rows, manifest(models=("model-a",)), policy())["groups"][0]
    assert result["pass_rate"] == 1
    assert result["raw_pass_rate"] == 0
    assert result["application_pass_rate"] == 1


def test_review_metrics_include_invalid_prediction_and_all_three_classes():
    rows = [row()]
    rows[0]["score"]["metrics"]["verdict_pairs"] = [
        {"item_id": "one", "expected": "MATCH", "actual": "MATCH"},
        {"item_id": "two", "expected": "NO_MATCH", "actual": "MATCH"},
        {"item_id": "three", "expected": "UNCERTAIN", "actual": None},
    ]
    result = summarize(rows, manifest(models=("model-a",)), policy())["groups"][0]
    assert result["false_match_rate"] == 0.5
    assert result["confusion_matrix"]["UNCERTAIN"]["INVALID"] == 1
    assert result["macro_f1"] == pytest.approx((2 / 3) / 3)


def test_failed_review_requests_remain_in_classification_denominator():
    rows = [row(passed=False, status="error", cost=None)]
    rows[0]["score"]["metrics"]["verdict_pairs"] = [
        {"item_id": str(i), "expected": verdict, "actual": None}
        for i, verdict in enumerate(("MATCH", "NO_MATCH", "UNCERTAIN"))
    ]
    result = summarize(rows, manifest(models=("model-a",)), policy())["groups"][0]
    assert result["verdict_count"] == 3
    assert result["macro_f1"] == 0
    assert result["per_class"]["MATCH"]["support"] == 1
    assert result["confusion_matrix"]["MATCH"]["INVALID"] == 1


def save_run(path, rows, config):
    write_reports(path, rows, config, policy())


def test_report_outputs_preserve_results_and_escape_markdown(tmp_path):
    rows = [row(passed=False)]
    rows[0]["error"] = "field|value\nnext"
    summary = write_reports(tmp_path, rows, manifest(models=("model-a",)), policy())
    assert json.loads((tmp_path / "summary.json").read_text(encoding="utf-8")) == summary
    assert (tmp_path / "summary.csv").exists()
    assert len((tmp_path / "records.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    assert "field\\|value next" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_regression_compares_only_unchanged_cases_and_lists_dataset_changes(tmp_path):
    old_config = manifest(("stable", "removed", "changed"), ("model-a",))
    new_config = manifest(("stable", "added", "changed"), ("model-a",))
    new_config["cases"][2]["hash"] = "new-hash"
    old_rows = [row(cid) for cid in ("stable", "removed", "changed")]
    new_rows = [row("stable", passed=False), row("added"), row("changed")]
    new_rows[2]["case_hash"] = "new-hash"
    new_rows[0]["prompt_hash"] = "prompt-2"
    save_run(tmp_path / "old", old_rows, old_config)
    save_run(tmp_path / "new", new_rows, new_config)
    result = compare_runs(tmp_path / "old", tmp_path / "new", tmp_path / "comparison")
    assert result["has_regressions"] is True
    assert result["comparable_record_count"] == 1
    assert result["regressions"][0]["case_id"] == "stable"
    assert result["added_cases"] == ["added"]
    assert result["removed_cases"] == ["removed"]
    assert result["changed_cases"] == ["changed"]
    assert len(result["prompt_changes"]) == 1


@pytest.mark.parametrize("mutation", ["scorer", "model", "repeats", "missing", "duplicate", "incomplete"])
def test_incomparable_regression_runs_are_rejected(tmp_path, mutation):
    old_config = manifest(models=("model-a",))
    new_config = copy.deepcopy(old_config)
    new_rows = [row()]
    if mutation == "scorer":
        new_config["scorer_version"] = "2"
    elif mutation == "model":
        new_config["models"][0]["temperature"] = 0.9
    elif mutation == "repeats":
        new_config["repeats"] = 2
    elif mutation == "missing":
        new_rows = []
    elif mutation == "duplicate":
        new_rows.append(copy.deepcopy(new_rows[0]))
    elif mutation == "incomplete":
        new_config["complete"] = False
    save_run(tmp_path / "old", [row()], old_config)
    save_run(tmp_path / "new", new_rows, new_config)
    with pytest.raises(ValueError, match="无法比较"):
        compare_runs(tmp_path / "old", tmp_path / "new", tmp_path / "comparison")


def test_no_unchanged_cases_is_not_reported_as_a_successful_regression_check(tmp_path):
    save_run(tmp_path / "old", [row("old")], manifest(("old",), ("model-a",)))
    save_run(tmp_path / "new", [row("new")], manifest(("new",), ("model-a",)))
    with pytest.raises(ValueError, match="没有共有"):
        compare_runs(tmp_path / "old", tmp_path / "new", tmp_path / "comparison")


@pytest.mark.parametrize("after_score,expected_regression", [(0.2, True), (0.9 - 1e-12, False)])
def test_score_drop_on_already_failed_case_is_a_regression(tmp_path, after_score, expected_regression):
    old_row = row(passed=False)
    old_row["score"]["score"] = 0.9
    new_row = row(passed=False)
    new_row["score"]["score"] = after_score
    config = manifest(models=("model-a",))
    save_run(tmp_path / "old", [old_row], config)
    save_run(tmp_path / "new", [new_row], config)
    result = compare_runs(tmp_path / "old", tmp_path / "new", tmp_path / "comparison")
    assert result["regressions"] == []
    assert bool(result["score_regressions"]) is expected_regression
    assert result["has_regressions"] is expected_regression
