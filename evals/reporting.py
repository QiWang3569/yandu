"""Versioned evaluation reports and comparable-case regression analysis.

The runner supplies sanitized provider configurations. Unknown provider costs remain
unknown; local rule timing is never compared with a network model for selection.
"""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict
from pathlib import Path


VERDICTS = ("MATCH", "NO_MATCH", "UNCERTAIN")
TASKS = {"intent_parse", "wanted_parse", "item_parse", "candidate_review"}
RATE_METRICS = {"pass_rate", "mean_score", "error_rate", "schema_valid_rate", "macro_f1", "false_match_rate",
                "raw_pass_rate", "raw_mean_score", "application_pass_rate"}


def validate_policy(policy):
    """Reject misspelled or ineffective gates before any report is generated."""
    allowed = {"version", "status", "description", "minimum_reviewed_cases", "minimum_remote_models", "quality_tolerance", "tasks"}
    if not isinstance(policy, dict) or set(policy) - allowed:
        raise ValueError("选型规则必须是对象，且不能包含未知字段")
    if not isinstance(policy.get("version"), str) or not policy["version"].strip():
        raise ValueError("选型规则 version 必须是非空字符串")
    if policy.get("status") not in {"draft", "confirmed", "locked"}:
        raise ValueError("选型规则 status 必须为 draft、confirmed 或 locked")
    for name, minimum in (("minimum_reviewed_cases", 1), ("minimum_remote_models", 2)):
        value = policy.get(name, minimum)
        if type(value) is not int or value < minimum:
            raise ValueError(f"{name} 必须是至少 {minimum} 的整数")
    tolerance = policy.get("quality_tolerance", 0.0)
    if not _number(tolerance) or not 0 <= tolerance <= 1:
        raise ValueError("quality_tolerance 必须是 0 到 1 之间的有限数值")
    task_rules = policy.get("tasks")
    if not isinstance(task_rules, dict) or not task_rules or set(task_rules) - TASKS:
        raise ValueError("tasks 必须包含已支持任务的选型规则")
    for task, rules in task_rules.items():
        if not isinstance(rules, dict) or not rules:
            raise ValueError(f"{task} 的选型门槛不能为空")
        for name, value in rules.items():
            if not name.startswith(("min_", "max_")) or name[4:] not in RATE_METRICS:
                raise ValueError(f"未知选型指标：{task}.{name}")
            if not _number(value) or not 0 <= value <= 1:
                raise ValueError(f"{task}.{name} 必须是 0 到 1 之间的有限数值")
    return policy


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _mean(values):
    return sum(values) / len(values) if values else None


def _percentile(values, percentile):
    """Linear interpolation; retain the sample count alongside percentiles."""
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * percentile
    lo, hi = math.floor(position), math.ceil(position)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


def _passed(record, key="score"):
    value = record.get(key) or {}
    return value.get("passed") is True


def _quality(record, key="score"):
    value = (record.get(key) or {}).get("score", 0)
    return float(value) if _number(value) and 0 <= value <= 1 else 0.0


def _classification(rows, score_key):
    pairs = [p for row in rows for p in (row.get(score_key) or {}).get("metrics", {}).get("verdict_pairs", [])]
    if not pairs:
        return {"macro_f1": None, "false_match_rate": None, "verdict_count": 0, "confusion_matrix": {}}
    matrix = Counter((p["expected"], p.get("actual") if p.get("actual") in VERDICTS else "INVALID") for p in pairs)
    f1s = []
    per_class = {}
    for label in VERDICTS:
        tp = matrix[label, label]
        fp = sum(count for (gold, prediction), count in matrix.items() if prediction == label and gold != label)
        fn = sum(count for (gold, prediction), count in matrix.items() if gold == label and prediction != label)
        f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0
        per_class[label] = {"precision": tp / (tp + fp) if tp + fp else 0.0,
                            "recall": tp / (tp + fn) if tp + fn else 0.0,
                            "f1": f1, "support": tp + fn}
        f1s.append(f1)
    negatives = sum(p["expected"] != "MATCH" for p in pairs)
    false_matches = sum(p["expected"] != "MATCH" and p.get("actual") == "MATCH" for p in pairs)
    return {"macro_f1": _mean(f1s), "false_match_rate": false_matches / negatives if negatives else None,
            "verdict_count": len(pairs), "per_class": per_class,
            "confusion_matrix": {gold: {prediction: matrix[gold, prediction] for prediction in (*VERDICTS, "INVALID")}
                                 for gold in VERDICTS}}


def _expected_keys(manifest, model, task, split):
    profiles = {p["id"]: p for p in manifest.get("models", [])}
    profile = profiles.get(model, {})
    if profile.get("tasks") is not None and task not in profile["tasks"]:
        return set()
    return {(case["id"], repeat) for case in manifest.get("cases", [])
            if case["task"] == task and case["split"] == split
            for repeat in range(1, manifest.get("repeats", 1) + 1)}


def _group_summary(rows, manifest):
    first = rows[0]
    model, task, split = first["model"], first["task"], first["split"]
    n = len(rows)
    # Failed attempts are included in the row's total latency and cost by the runner.
    costs = [r.get("cost_cny") for r in rows]
    known_costs = [v for v in costs if _number(v)]
    latencies = [r["latency_ms"] for r in rows if _number(r.get("latency_ms"))]
    expected = _expected_keys(manifest, model, task, split)
    actual = [(r["case_id"], r["repeat"]) for r in rows]
    valid_hashes = {c["id"]: c["hash"] for c in manifest.get("cases", [])}
    complete = (manifest.get("complete") is True and set(actual) == expected and len(actual) == len(expected)
                and all(r.get("case_hash") == valid_hashes.get(r["case_id"]) for r in rows))
    raw_available = any(r.get("raw_score") is not None for r in rows)
    application_available = any(r.get("application_score") is not None for r in rows)
    schema_known = any("schema_valid" in (r.get("score") or {}).get("metrics", {}) for r in rows)
    summary = {
        "model": model, "task": task, "split": split, "count": n,
        "case_count": len({r["case_id"] for r in rows}), "expected_count": len(expected), "complete": complete,
        "passed_count": sum(_passed(r) and r.get("status") == "ok" for r in rows),
        "pass_rate": sum(_passed(r) and r.get("status") == "ok" for r in rows) / n,
        "mean_score": sum(_quality(r) if r.get("status") == "ok" else 0.0 for r in rows) / n,
        "error_count": sum(r.get("status") != "ok" for r in rows),
        "error_rate": sum(r.get("status") != "ok" for r in rows) / n,
        "fallback_count": sum(r.get("fallback_used") is True for r in rows),
        "raw_pass_rate": sum(_passed(r, "raw_score") for r in rows) / n if raw_available else None,
        "raw_mean_score": sum(_quality(r, "raw_score") for r in rows) / n if raw_available else None,
        "application_pass_rate": sum(_passed(r, "application_score") for r in rows) / n if application_available else None,
        "schema_valid_rate": sum((r.get("score") or {}).get("metrics", {}).get("schema_valid") is True
                                 and r.get("status") == "ok" for r in rows) / n if schema_known else None,
        "latency_samples": len(latencies), "mean_latency_ms": _mean(latencies),
        "p50_latency_ms": _percentile(latencies, 0.5), "p95_latency_ms": _percentile(latencies, 0.95),
        "attempt_count": sum(len(r.get("attempts", [])) for r in rows),
        "unknown_cost_count": n - len(known_costs), "known_cost_subtotal_cny": sum(known_costs),
        "total_cost_cny": sum(known_costs) if len(known_costs) == n else None,
        "mean_cost_cny": _mean(known_costs) if len(known_costs) == n else None,
        "errors": dict(Counter(r.get("error") or "unknown_error" for r in rows if r.get("status") != "ok")),
        "prompt_hashes": sorted({r["prompt_hash"] for r in rows if r.get("prompt_hash")}),
    }
    summary["cost_per_pass_cny"] = (summary["total_cost_cny"] / summary["passed_count"]
                                    if summary["total_cost_cny"] is not None and summary["passed_count"] else None)
    summary.update(_classification(rows, "score"))
    summary["raw_classification"] = _classification(rows, "raw_score")
    return summary


def _gate(group, rules):
    failures = []
    for key, threshold in rules.items():
        if not key.startswith(("min_", "max_")):
            continue
        metric = key[4:]
        value = group.get(metric)
        if value is None:
            failures.append(f"{metric} 无可用结果")
        elif (key.startswith("min_") and value < threshold) or (key.startswith("max_") and value > threshold):
            symbol = "≥" if key.startswith("min_") else "≤"
            failures.append(f"{metric}={value:.4f}，要求 {symbol}{threshold}")
    return failures


def _select(groups, records, manifest, policy):
    profiles = {p["id"]: p for p in manifest.get("models", [])}
    selected = []
    tasks = sorted({c["task"] for c in manifest.get("cases", [])} | {g["task"] for g in groups})
    for task in tasks:
        decision = {"task": task, "status": "insufficient_evidence", "selected_model": None, "reasons": [], "candidates": []}
        cases = [c for c in manifest.get("cases", []) if c["task"] == task and c["split"] == "holdout"]
        candidates = [g for g in groups if g["task"] == task and g["split"] == "holdout"
                      and profiles.get(g["model"], {}).get("mode") == "remote"]
        expected_models = {name for name, profile in profiles.items() if profile.get("mode") == "remote"
                           and (profile.get("tasks") is None or task in profile["tasks"])}
        if policy.get("status") not in {"confirmed", "locked"}:
            decision["reasons"].append("选型规则仍为草案；团队须在保留集评测前确认并设为 confirmed 或 locked。")
        if not cases:
            decision["reasons"].append("当前为开发集或本地基线诊断，尚无保留集对照。")
        elif any(c.get("label_status") != "reviewed" for c in cases):
            decision["reasons"].append("保留集标签尚未全部经过人工复核。")
        if len(cases) < policy.get("minimum_reviewed_cases", 1):
            decision["reasons"].append(f"保留集 {len(cases)} 例，少于预设的 {policy.get('minimum_reviewed_cases', 1)} 例。")
        if len(candidates) < max(2, policy.get("minimum_remote_models", 2)):
            decision["reasons"].append("同一任务至少需要两个远程候选模型的完整对照。")
        identities = {(str(profiles[g["model"]].get("base_url", "")).rstrip("/"), profiles[g["model"]].get("model"))
                      for g in candidates}
        if candidates and (len(identities) < max(2, policy.get("minimum_remote_models", 2))
                           or any(not identity[1] for identity in identities)):
            decision["reasons"].append("不同配置别名须对应不同的供应商与模型组合；相同模型的重复配置不算独立候选。")
        if any(not g["complete"] for g in candidates) or manifest.get("complete") is not True:
            decision["reasons"].append("运行未完成，或存在缺失、重复、用例版本不一致的结果。")
        if cases and {g["model"] for g in candidates} != expected_models:
            decision["reasons"].append("配置中的部分候选模型缺少该任务的完整结果。")
        task_rows = [r for r in records if r["task"] == task and r["split"] == "holdout"
                     and profiles.get(r["model"], {}).get("mode") == "remote"]
        if any(r.get("label_status") != "reviewed" for r in task_rows):
            decision["reasons"].append("逐例结果中仍有未复核标签。")
        if task not in policy.get("tasks", {}):
            decision["reasons"].append("未配置该任务的选型门槛。")
        for group in candidates:
            failures = _gate(group, policy.get("tasks", {}).get(task, {}))
            decision["candidates"].append({"model": group["model"], "meets_gates": not failures, "failures": failures})
        if decision["reasons"]:
            selected.append(decision)
            continue
        eligible = [g for g in candidates if not _gate(g, policy["tasks"][task])]
        if not eligible:
            decision.update(status="no_model_qualified", reasons=["本次候选均未达到预设门槛，保留现有配置并处理失败用例。"])
            selected.append(decision)
            continue
        best = max(g["pass_rate"] for g in eligible)
        finalists = [g for g in eligible if best - g["pass_rate"] <= policy.get("quality_tolerance", 0.0) + 1e-12]
        costs_available = all(g["mean_cost_cny"] is not None for g in finalists)
        if costs_available:
            chosen = min(finalists, key=lambda g: (g["mean_cost_cny"], g["p95_latency_ms"] if g["p95_latency_ms"] is not None else math.inf, g["model"]))
        else:
            chosen = min(finalists, key=lambda g: (g["p95_latency_ms"] if g["p95_latency_ms"] is not None else math.inf, g["model"]))
        decision.update(status="recommended", selected_model=chosen["model"], reasons=[
            f"通过预设门槛，整例通过率 {chosen['pass_rate']:.1%}；先比较质量，再在同等质量候选中比较成本与 P95。",
            "候选费用均已记录，使用费用作为次级选择依据。" if costs_available else "候选费用存在未知值，本次不按费用排序，使用 P95 作为次级依据。",
        ])
        selected.append(decision)
    return selected


def summarize(records, manifest, policy):
    validate_policy(policy)
    records = list(records)
    grouped = defaultdict(list)
    for record in records:
        grouped[record["model"], record["task"], record["split"]].append(record)
    groups = [_group_summary(rows, manifest) for _, rows in sorted(grouped.items())]
    return {"run_id": manifest.get("run_id"), "complete": manifest.get("complete") is True,
            "record_count": len(records), "policy_version": policy.get("version"),
            "groups": groups, "selection": _select(groups, records, manifest, policy)}


def _cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _fmt(value, digits=3):
    return "未知" if value is None else f"{value:.{digits}f}"


def _pct(value):
    return "未知" if value is None else f"{value:.1%}"


def _report_markdown(summary, manifest, policy, records):
    display_time = manifest.get('created_at', '')
    try:
        display_time = datetime.fromisoformat(display_time.replace('Z', '+00:00')).astimezone(
            timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S 北京时间')
    except (ValueError, AttributeError):
        pass
    lines = ["# 燕渡模型评测报告", "", f"运行：{_cell(manifest.get('run_id', ''))}；时间：{_cell(display_time)}。",
             f"代码：`{_cell(manifest.get('git_sha', 'unknown'))}`；工作区未提交修改：{bool(manifest.get('dirty'))}；运行完整：{summary['complete']}。",
             f"测试集：`{_cell(manifest.get('dataset_hash', ''))}`；评分器：`{_cell(manifest.get('scorer_version', ''))}`；每例重复 {manifest.get('repeats', 1)} 次。", "",
             "每次运行均保留失败结果。通过率以全部计划内已执行结果为分母；完整性另列，未完成运行不产生选型建议。费用未知时保留未知，已知费用小计不等同于总费用。", "",
             "| 模型配置 | 任务 | 集合 | 用例／执行次数 | 完整 | 通过率 | 平均评分 | 错误率 | P95 毫秒 | 平均费用 元 |",
             "| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |"]
    for g in summary["groups"]:
        lines.append(f"| {_cell(g['model'])} | {g['task']} | {g['split']} | {g['case_count']}／{g['count']} | {g['complete']} | {_pct(g['pass_rate'])} | {_fmt(g['mean_score'])} | {_pct(g['error_rate'])} | {_fmt(g['p95_latency_ms'], 1)} | {_fmt(g['mean_cost_cny'], 6)} |")
    lines.extend(["", "## 选型结论", ""])
    for decision in summary["selection"]:
        lines.append(f"**{decision['task']}**：" + (f"建议使用 `{_cell(decision['selected_model'])}`。" if decision["selected_model"] else "尚未确定优选模型。"))
        lines.append(" ".join(decision["reasons"]))
        for candidate in decision["candidates"]:
            lines.append(f"- `{_cell(candidate['model'])}`：" + ("达到当前门槛。" if candidate["meets_gates"] else "；".join(candidate["failures"]) + "。"))
        lines.append("")
    lines.extend(["## 评分与运行说明", "", f"规则状态：{_cell(policy.get('status', 'unspecified'))}。{_cell(policy.get('description', ''))}", "",
                  "整例通过率要求所有已声明断言通过；平均评分为每例断言得分的均值，不等同于按字段总数加权的准确率。匹配精筛的 macro-F1 固定平均 MATCH、NO_MATCH、UNCERTAIN 三类；某类没有样本时该类 F1 为 0，因此报告同时保留各类样本量。错误推荐率以标准答案非 MATCH 的候选数为分母。逐字引用校验不能替代人工核查证据是否支持结论。", "",
                  "P50／P95 对包含重试的整次调用耗时做线性插值；本地规则耗时不用于与远程模型的网络耗时选型比较。原始模型输出、应用校验后的结果和回退状态保存在 records.jsonl。", ""])
    for g in summary["groups"]:
        if g["macro_f1"] is not None or g["raw_pass_rate"] is not None or g["application_pass_rate"] is not None:
            lines.append(f"- `{_cell(g['model'])}`／{g['task']}／{g['split']}：原始结果通过率 {_pct(g['raw_pass_rate'])}，应用结果通过率 {_pct(g['application_pass_rate'])}，macro-F1 {_fmt(g['macro_f1'])}，错误推荐率 {_pct(g['false_match_rate'])}，回退 {g['fallback_count']} 次。")
    failed = [r for r in records if not _passed(r) or r.get("status") != "ok"]
    lines.extend(["", "## 失败用例", "", "完整结果与输出见 records.jsonl；下表列出最多 100 条失败记录。", "",
                  "| 用例 | 模型 | 重复 | 原因 |", "| --- | --- | ---: | --- |"])
    for row in failed[:100]:
        reason = row.get("error") or "; ".join(str(c.get("field", "assertion")) for c in (row.get("score") or {}).get("checks", []) if c.get("passed") is not True)
        lines.append(f"| {_cell(row['case_id'])} | {_cell(row['model'])} | {row['repeat']} | {_cell(reason or '未通过评分')} |")
    if not failed:
        lines.append("| 无 | — | — | 本次已执行用例均通过 |")
    return "\n".join(lines) + "\n"


def write_reports(output_dir, records, manifest, policy):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = list(records)
    summary = summarize(records, manifest, policy)
    _write_json(output_dir / "manifest.json", manifest)
    _write_json(output_dir / "summary.json", summary)
    _write_json(output_dir / "selection_policy.json", policy)
    (output_dir / "records.jsonl").write_text("".join(_json(r) + "\n" for r in records), encoding="utf-8")
    fields = ["model", "task", "split", "case_count", "count", "expected_count", "complete", "pass_rate", "mean_score", "error_rate", "schema_valid_rate", "raw_pass_rate", "application_pass_rate", "macro_f1", "false_match_rate", "p50_latency_ms", "p95_latency_ms", "attempt_count", "total_cost_cny", "mean_cost_cny", "unknown_cost_count"]
    with (output_dir / "summary.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary["groups"])
    (output_dir / "report.md").write_text(_report_markdown(summary, manifest, policy, records), encoding="utf-8")
    return summary


def _read_run(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8-sig"))
    rows = [json.loads(line) for line in (directory / "records.jsonl").read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    return manifest, rows


def compare_runs(baseline_dir, current_dir, output_dir):
    baseline, before = _read_run(baseline_dir)
    current, after = _read_run(current_dir)
    errors = []
    for field in ("scorer_version", "repeats"):
        if baseline.get(field) != current.get(field) or baseline.get(field) is None:
            errors.append(f"{field} 不一致或缺失")
    old_models = {p["id"]: p for p in baseline.get("models", [])}
    new_models = {p["id"]: p for p in current.get("models", [])}
    if old_models != new_models or not old_models:
        errors.append("模型配置不一致或缺失；模型、供应商、解码参数、重试与计费配置须相同")
    if baseline.get("complete") is not True or current.get("complete") is not True:
        errors.append("至少一次运行未完成")
    if errors:
        raise ValueError("无法比较：" + "；".join(errors))
    old_cases = {c["id"]: c for c in baseline.get("cases", [])}
    new_cases = {c["id"]: c for c in current.get("cases", [])}
    common = set(old_cases) & set(new_cases)
    changed = sorted(cid for cid in common if old_cases[cid] != new_cases[cid])
    stable = common - set(changed)
    def index(rows, manifest_cases):
        result = {}
        for row in rows:
            key = (row["case_id"], row["model"], row["task"], row["split"], row["repeat"])
            if key in result:
                raise ValueError("无法比较：存在重复运行记录")
            case = manifest_cases.get(row["case_id"])
            if not case or row.get("case_hash") != case.get("hash") or row["task"] != case["task"] or row["split"] != case["split"]:
                raise ValueError("无法比较：记录与 manifest 的用例版本不一致")
            result[key] = row
        return result
    old = index(before, old_cases)
    new = index(after, new_cases)
    expected = set()
    for cid in stable:
        case = new_cases[cid]
        for model, profile in new_models.items():
            if profile.get("tasks") is not None and case["task"] not in profile["tasks"]:
                continue
            for repeat in range(1, current["repeats"] + 1):
                expected.add((cid, model, case["task"], case["split"], repeat))
    if not expected:
        raise ValueError("无法比较：没有共有且未修改、模型支持的用例")
    if any(key not in old or key not in new for key in expected):
        raise ValueError("无法比较：共有用例存在缺失记录，不能静默排除失败或未运行样本")
    regressions, score_regressions, improvements, prompt_changes = [], [], [], []
    grouped = defaultdict(list)
    for key in sorted(expected):
        a, b = old[key], new[key]
        detail = {"case_id": key[0], "model": key[1], "task": key[2], "split": key[3], "repeat": key[4],
                  "before_score": _quality(a), "after_score": _quality(b), "error": b.get("error")}
        a_pass, b_pass = _passed(a) and a.get("status") == "ok", _passed(b) and b.get("status") == "ok"
        if a_pass and not b_pass:
            regressions.append(detail)
        if detail["after_score"] < detail["before_score"] - 1e-9:
            score_regressions.append(detail)
        if not a_pass and b_pass:
            improvements.append(detail)
        if a.get("prompt_hash") != b.get("prompt_hash"):
            prompt_changes.append({"case_id": key[0], "model": key[1], "before": a.get("prompt_hash"), "after": b.get("prompt_hash")})
        grouped[key[1:4]].append((a_pass, b_pass))
    comparison = {"baseline_run": baseline.get("run_id"), "current_run": current.get("run_id"),
                  "comparable_record_count": len(expected), "unchanged_cases": sorted(stable),
                  "added_cases": sorted(set(new_cases) - set(old_cases)), "removed_cases": sorted(set(old_cases) - set(new_cases)),
                  "changed_cases": changed, "regressions": regressions, "improvements": improvements,
                  "score_regressions": score_regressions,
                  "has_regressions": bool(regressions or score_regressions), "prompt_changes": prompt_changes,
                  "policy_changed": baseline.get("policy_hash") != current.get("policy_hash"),
                  "groups": [{"model": key[0], "task": key[1], "split": key[2], "count": len(pairs),
                              "before_pass_rate": sum(a for a, _ in pairs) / len(pairs),
                              "after_pass_rate": sum(b for _, b in pairs) / len(pairs)} for key, pairs in sorted(grouped.items())]}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "comparison.json", comparison)
    lines = ["# 燕渡模型评测回归比较", "", f"基线：{_cell(comparison['baseline_run'])}；当前：{_cell(comparison['current_run'])}。",
             f"比较 {len(stable)} 个共有且未修改的用例、{len(expected)} 条结果；新增 {len(comparison['added_cases'])} 例，删除 {len(comparison['removed_cases'])} 例，修改 {len(changed)} 例。",
             f"通过转失败 {len(regressions)} 条；评分下降 {len(score_regressions)} 条（可与前者重叠）；失败转通过 {len(improvements)} 条。提示词变化 {len(prompt_changes)} 条；选型规则变化：{comparison['policy_changed']}。", "",
             "新增、删除和修改用例单列，不参与共有用例通过率比较。模型配置、评分器与重复次数一致后，才生成本报告。", "",
             "| 模型 | 任务 | 集合 | 结果数 | 基线通过率 | 当前通过率 |", "| --- | --- | --- | ---: | ---: | ---: |"]
    for g in comparison["groups"]:
        lines.append(f"| {_cell(g['model'])} | {g['task']} | {g['split']} | {g['count']} | {_pct(g['before_pass_rate'])} | {_pct(g['after_pass_rate'])} |")
    for title, entries in (("通过转失败", regressions), ("评分下降", score_regressions), ("失败转通过", improvements)):
        lines.extend(["", f"## {title}", ""])
        lines.extend(f"- `{_cell(r['case_id'])}`／`{_cell(r['model'])}`／第 {r['repeat']} 次：{_fmt(r['before_score'])} → {_fmt(r['after_score'])}" for r in entries)
        if not entries:
            lines.append("无。")
    for title, cases in (("新增用例", comparison["added_cases"]), ("删除用例", comparison["removed_cases"]), ("修改用例", comparison["changed_cases"])):
        lines.extend(["", f"## {title}", "", ", ".join(f"`{_cell(cid)}`" for cid in cases) or "无。"])
    (output_dir / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return comparison
