"""Search, slice, stability and parse diagnostics shared by report formats."""
from .diagnostics import aggregate_fields, consistency


def group_diagnostics(rows, manifest):
    from .reporting import _mean, _percentile
    result = {'parse_diagnostics': aggregate_fields(rows), **consistency(rows, manifest)}
    profile = next((p for p in manifest.get('models', []) if p['id'] == rows[0]['model']), {})
    result['first_schema_valid_rate'] = (sum(len(r.get('attempts', [])) == 1
        and r['attempts'][0].get('status') == 'ok' and r.get('status') == 'ok'
        and (r.get('raw_score') or {}).get('metrics', {}).get('schema_valid') is True for r in rows) / len(rows)
        if profile.get('mode') == 'remote' else None)
    for phase in ('parse', 'search'):
        timings = [r[phase + '_latency_ms'] for r in rows if isinstance(r.get(phase + '_latency_ms'), (int, float))]
        result['mean_' + phase + '_latency_ms'] = _mean(timings)
        result['p95_' + phase + '_latency_ms'] = _percentile(timings, .95)
    metrics = [(r.get('score') or {}).get('metrics', {}) for r in rows]
    for metric, name in [('mrr', 'mrr'), ('ap_at_5', 'map_at_5'), ('recall_at_10', 'recall_at_10')]:
        values = [m[metric] for m in metrics if m.get(metric) is not None]
        result[name] = _mean(values)
    result['retrieval_positive_count'] = sum(m.get('retrieval_eligible') is True for m in metrics)
    zeros = [m['zero_result_error'] for m in metrics if m.get('zero_result_error') is not None]
    result['zero_result_evaluated_count'] = len(zeros)
    result['zero_result_error_rate'] = _mean(zeros)
    return result


def report_extension(summary):
    from .reporting import _cell, _pct, _fmt
    groups = summary['groups']
    lines = ['', '## 分场景与重复执行', '',
        '切片使用 `slice:` 标签。同一用例可出现在多个标签中；切片行不能相加作为总样本数。重复一致率以用例为单位，要求计划内各次执行全部成功且输出 JSON 完全一致（对象键顺序忽略，数组顺序保留）。', '',
        '| 模型 | 任务 | 集合 | 重复一致率／用例数 | 首次 Schema 通过率 |',
        '| --- | --- | --- | --- | ---: |']
    for g in groups:
        lines.append(f"| {_cell(g['model'])} | {g['task']} | {g['split']} | {_pct(g.get('consistency_rate'))}／{g.get('consistency_case_count', 0)} | {_pct(g.get('first_schema_valid_rate'))} |")
    if summary.get('slices'):
        lines += ['', '| 模型 | 场景 | 集合 | 用例数 | 通过率 | MRR | MAP@5 | Recall@10 |',
                  '| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |']
        for g in summary['slices']:
            lines.append(f"| {_cell(g['model'])} | {_cell(g['slice'])} | {g['split']} | {g['case_count']} | {_pct(g['pass_rate'])} | {_fmt(g.get('mrr'))} | {_fmt(g.get('map_at_5'))} | {_fmt(g.get('recall_at_10'))} |")
    for g in groups:
        d = g.get('parse_diagnostics', {})
        if not d.get('fields') and not d.get('sets') and not d.get('clarification'):
            continue
        lines += ['', f"## 解析指标：{_cell(g['model'])}／{g['task']}／{g['split']}", '',
            '| 字段 | 样本数（含重复） | 准确率 | Macro-F1 |', '| --- | ---: | ---: | ---: |']
        for name, item in d.get('fields', {}).items():
            lines.append(f"| {_cell(name)} | {item['count']} | {_pct(item['accuracy'])} | {_fmt(item['macro_f1'])} |")
        for name, item in d.get('sets', {}).items():
            lines.append(f"- `{name}`：Micro-P/R/F1={_fmt(item['micro_precision'])}/{_fmt(item['micro_recall'])}/{_fmt(item['micro_f1'])}；逐例 Macro-F1={_fmt(item['macro_f1'])}。")
        if d.get('clarification'):
            item = d['clarification']
            lines.append(f"- 澄清触发 F1={_fmt(item['f1'])}，应澄清 {item['positive_count']}/{item['count']} 例。")
    if any(g['task'] == 'smart_search' for g in groups):
        lines += ['', '## 固定商品库搜索', '',
            '排名指标以有相关商品且适用检索的查询为分母；执行失败按 0 分计入。MRR 使用完整排序，AP@5 的分母为 min(5,相关商品数)，Recall@10 的分母为全部相关商品数。无相关商品查询不计入三项排名均值，但整例检查要求返回空集。歧义查询可声明仅评价解析。', '',
            '零结果误杀率只统计有相关商品、结构有效且执行成功的查询，执行错误另计错误率。端到端耗时覆盖解析与实际检索，不包含固定库建库和 HTTP 鉴权／传输；解析与检索阶段另列。Oracle 只注入预标注解析，不注入相关商品答案。', '',
            '| 模型 | 集合 | 排名样本数 | MRR | MAP@5 | Recall@10 | 零结果误杀率／分母 | 解析 P95 ms | 搜索端到端 P95 ms |',
            '| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |']
        for g in groups:
            if g['task'] == 'smart_search':
                lines.append(f"| {_cell(g['model'])} | {g['split']} | {g['retrieval_positive_count']} | {_fmt(g['mrr'])} | {_fmt(g['map_at_5'])} | {_fmt(g['recall_at_10'])} | {_pct(g['zero_result_error_rate'])}／{g['zero_result_evaluated_count']} | {_fmt(g['p95_parse_latency_ms'],1)} | {_fmt(g['p95_latency_ms'],1)} |")
    if summary.get('baseline_comparisons'):
        lines += ['', '## 相对本地规则', '',
            '只比较相同用例和重复次数。错误率降低=(模型整例通过率−本地通过率)/(1−本地通过率)，本地已全对时留空；排名指标报告绝对增量。', '',
            '| 模型 | 本地基线 | 任务／集合 | 通过率增量 | 整例错误率降低 | MRR 增量 | MAP@5 增量 |',
            '| --- | --- | --- | ---: | ---: | ---: | ---: |']
        for d in summary['baseline_comparisons']:
            lines.append(f"| {_cell(d['model'])} | {_cell(d['baseline'])} | {d['task']}／{d['split']} | {_pct(d['pass_rate_gain'])} | {_pct(d['error_rate_reduction'])} | {_fmt(d['mrr_gain'])} | {_fmt(d['ap_at_5_gain'])} |")
    if summary.get('metamorphic'):
        lines += ['', '## 蜕变关系', '',
            '不变关系比较规范化解析和完整结果 ID 集合；方向关系比较完整集合的子集、价格及排除商品约束。错误或缺失执行计失败；空基例单列，避免把空集关系当作充分证据。', '',
            '| 模型 | 关系执行数 | 通过 | 非空基例数 |', '| --- | ---: | ---: | ---: |']
        for model in sorted({r['model'] for r in summary['metamorphic']}):
            rows = [r for r in summary['metamorphic'] if r['model'] == model]
            lines.append(f"| {_cell(model)} | {len(rows)} | {sum(r['passed'] for r in rows)} | {sum(r['base_nonempty'] for r in rows)} |")
        for r in summary['metamorphic']:
            if not r['passed']:
                lines.append(f"- `{_cell(r['model'])}`／`{_cell(r['id'])}`／第 {r['repeat']} 次：" + ', '.join(k for k,v in r['checks'].items() if not v))
    lines += ['', '分类 Macro-F1 的类别集合为本组标准答案中出现的类别，包含显式 null；支持数保存在 summary.json。集合字段的双方空集计 1，结构／执行失败计 0，Micro 汇总为无效预测保留一个错误项。无澄清正例且无误报时澄清 F1 留空。首次 Schema 通过率要求首次请求成功且原始结构有效，重试成功不算首次通过。', '']
    return '\n'.join(lines)
