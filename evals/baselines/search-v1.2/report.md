# 燕渡模型评测报告

运行：20261115T105148Z-80c171dd；时间：2026-11-15 18:51:48 北京时间。
代码：`1bbf607f99f7378e57e13b390dea8d02e86bbe12`；工作区未提交修改：True；运行完整：True。
测试集：`b4be954b29ccd73e2e1f9486f94f2222e1dc37e882203317524fe86144a72ce3`；评分器：`1.2.0`；每例重复 3 次。

每次运行均保留失败结果。通过率以全部计划内已执行结果为分母；完整性另列，未完成运行不产生选型建议。费用未知时保留未知，已知费用小计不等同于总费用。

| 模型配置 | 任务 | 集合 | 用例／执行次数 | 完整 | 通过率 | 平均评分 | 错误率 | P95 毫秒 | 平均费用 元 |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| local-rules | smart_search | dev | 80／240 | True | 26.2% | 0.820 | 1.2% | 1.1 | 0.000000 |
| oracle | smart_search | dev | 80／240 | True | 75.0% | 0.976 | 0.0% | 0.7 | 0.000000 |

## 选型结论

**smart_search**：尚未确定优选模型。
选型规则仍为草案；团队须在保留集评测前确认并设为 confirmed 或 locked。 当前为开发集或本地基线诊断，尚无保留集对照。 保留集 0 例，少于预设的 20 例。 同一任务至少需要两个远程候选模型的完整对照。 固定商品库尚未人工复核。

## 评分与运行说明

规则状态：draft。按评测方法提出的搜索质量、交互耗时和稳定性门槛草案；团队须在人工复核保留集运行前确认。Oracle仅诊断后续检索损失，不作为候选模型。

整例通过率要求所有已声明断言通过；平均评分为每例断言得分的均值，不等同于按字段总数加权的准确率。匹配精筛的 macro-F1 固定平均 MATCH、NO_MATCH、UNCERTAIN 三类；某类没有样本时该类 F1 为 0，因此报告同时保留各类样本量。错误推荐率以标准答案非 MATCH 的候选数为分母。逐字引用校验不能替代人工核查证据是否支持结论。

P50／P95 对包含重试的整次调用耗时做线性插值；本地规则耗时不用于与远程模型的网络耗时选型比较。原始模型输出、应用校验后的结果和回退状态保存在 records.jsonl。

- `local-rules`／smart_search／dev：原始结果通过率 未知，应用结果通过率 26.2%，macro-F1 未知，错误推荐率 未知，回退 0 次。
- `oracle`／smart_search／dev：原始结果通过率 未知，应用结果通过率 75.0%，macro-F1 未知，错误推荐率 未知，回退 0 次。

## 失败用例

完整结果与输出见 records.jsonl；下表列出最多 100 条失败记录。

| 用例 | 模型 | 重复 | 原因 |
| --- | --- | ---: | --- |
| search-confusable-08 | local-rules | 1 | keywords.concept[0]; keywords.extra[0]; retrieval_exact |
| search-price-04 | local-rules | 1 | category; max_price; keywords.concept[0]; keywords.extra[0]; clarification; retrieval_exact |
| search-ambiguity-02 | local-rules | 1 | keywords.extra[0] |
| search-ood-01 | local-rules | 1 | category; keywords.concept[0]; keywords.extra[0]; clarification |
| search-confusable-06 | local-rules | 1 | keywords.concept[0]; keywords.extra[0]; retrieval_exact |
| search-core-04 | local-rules | 1 | max_price; retrieval_exact |
| search-negation-02 | oracle | 1 | retrieval_exact |
| search-negation-02 | local-rules | 1 | retrieval_exact |
| search-confusable-05 | local-rules | 1 | keywords.concept[0]; keywords.extra[0]; retrieval_exact |
| search-price-02 | local-rules | 1 | max_price; keywords.concept[0]; keywords.extra[0]; retrieval_exact |
| search-negation-07 | local-rules | 1 | category; keywords.concept[0]; clarification; retrieval_exact |
| search-preference-09 | oracle | 1 | retrieval_exact |
| search-preference-09 | local-rules | 1 | category; clarification; retrieval_exact |
| search-negation-01 | oracle | 1 | retrieval_exact |
| search-negation-01 | local-rules | 1 | retrieval_exact |
| search-price-08 | local-rules | 1 | retrieval_exact |
| search-price-08 | oracle | 1 | retrieval_exact |
| search-ambiguity-10 | local-rules | 1 | category; max_price; keywords.concept[0]; keywords.extra[0]; excluded_keywords.extra[0]; clarification; retrieval_exact |
| search-preference-06 | local-rules | 1 | keywords.concept[1]; retrieval_exact |
| search-preference-06 | oracle | 1 | retrieval_exact |
| search-ambiguity-08 | local-rules | 1 | keywords.concept[0]; keywords.extra[0]; keywords.extra[1]; retrieval_exact |
| search-core-06 | local-rules | 1 | max_price; keywords.concept[0]; keywords.extra[0] |
| search-confusable-07 | oracle | 1 | retrieval_exact |
| search-confusable-07 | local-rules | 1 | retrieval_exact |
| search-ood-02 | local-rules | 1 | category; clarification |
| search-negation-08 | oracle | 1 | retrieval_exact |
| search-negation-08 | local-rules | 1 | retrieval_exact |
| search-ood-05 | local-rules | 1 | category; keywords.concept[0]; keywords.extra[0]; clarification |
| search-confusable-04 | oracle | 1 | retrieval_exact |
| search-confusable-04 | local-rules | 1 | keywords.concept[0]; retrieval_exact |
| search-ood-03 | local-rules | 1 | category; clarification |
| search-price-06 | local-rules | 1 | keywords.concept[0]; keywords.extra[0]; retrieval_exact |
| search-ambiguity-07 | local-rules | 1 | retrieval_exact |
| search-ambiguity-07 | oracle | 1 | retrieval_exact |
| search-confusable-03 | local-rules | 1 | keywords.concept[0]; keywords.extra[0]; retrieval_exact |
| search-price-03 | local-rules | 1 | max_price |
| search-price-05 | local-rules | 1 | keywords.concept[0]; keywords.extra[0] |
| search-price-07 | local-rules | 1 | max_price; retrieval_exact |
| search-preference-08 | local-rules | 1 | keywords.concept[1]; retrieval_exact |
| search-preference-08 | oracle | 1 | retrieval_exact |
| search-price-02-rewrite | local-rules | 1 | keywords.concept[0]; keywords.extra[0]; retrieval_exact |
| search-negation-01-rewrite | oracle | 1 | retrieval_exact |
| search-negation-01-rewrite | local-rules | 1 | retrieval_exact |
| search-ood-08 | local-rules | 1 | keywords.concept[0]; keywords.extra[0] |
| search-ambiguity-01 | local-rules | 1 | keywords.extra[0] |
| search-core-05 | local-rules | 1 | max_price; retrieval_exact |
| search-ambiguity-03 | local-rules | 1 | output_validation_error |
| search-ood-06 | local-rules | 1 | keywords.concept[0]; keywords.extra[0]; retrieval_exact |
| search-core-07 | local-rules | 1 | category; max_price; keywords.concept[0]; keywords.extra[0]; clarification; retrieval_exact |
| search-price-01 | oracle | 1 | around_price; retrieval_exact |
| search-price-01 | local-rules | 1 | max_price; around_price; retrieval_exact |
| search-ood-09 | local-rules | 1 | category; keywords.concept[0]; keywords.extra[0]; clarification |
| search-core-01-rewrite | local-rules | 1 | retrieval_exact |
| search-core-01-rewrite | oracle | 1 | retrieval_exact |
| search-preference-02 | local-rules | 1 | keywords.concept[1]; retrieval_exact |
| search-preference-02 | oracle | 1 | retrieval_exact |
| search-price-08-budget | oracle | 1 | retrieval_exact |
| search-price-08-budget | local-rules | 1 | retrieval_exact |
| search-ood-04 | local-rules | 1 | category; clarification |
| search-ood-07 | local-rules | 1 | category; clarification |
| search-core-09 | local-rules | 1 | max_price; keywords.concept[0]; keywords.extra[0]; retrieval_exact |
| search-ood-10 | local-rules | 1 | category; clarification |
| search-price-08-rewrite | oracle | 1 | retrieval_exact |
| search-price-08-rewrite | local-rules | 1 | retrieval_exact |
| search-core-02 | local-rules | 1 | keywords.concept[0]; keywords.extra[0]; keywords.extra[1]; retrieval_exact |
| search-preference-10 | local-rules | 1 | category; keywords.concept[0]; keywords.concept[1]; keywords.extra[0]; clarification; retrieval_exact |
| search-ambiguity-06 | local-rules | 1 | keywords.extra[0] |
| search-confusable-03-rewrite | local-rules | 1 | keywords.concept[0]; keywords.extra[0]; retrieval_exact |
| search-core-03 | local-rules | 1 | keywords.concept[0]; keywords.extra[0] |
| search-core-01 | oracle | 1 | retrieval_exact |
| search-core-01 | local-rules | 1 | retrieval_exact |
| search-negation-10 | local-rules | 1 | category; clarification; retrieval_exact |
| search-negation-10 | oracle | 1 | retrieval_exact |
| search-confusable-10 | local-rules | 1 | category; clarification |
| search-preference-04 | local-rules | 1 | retrieval_exact |
| search-preference-04 | oracle | 1 | retrieval_exact |
| search-ambiguity-04 | local-rules | 1 | max_price; clarification |
| search-negation-03 | local-rules | 1 | retrieval_exact |
| search-negation-03 | oracle | 1 | retrieval_exact |
| search-ood-04 | local-rules | 2 | category; clarification |
| search-ambiguity-01 | local-rules | 2 | keywords.extra[0] |
| search-ood-10 | local-rules | 2 | category; clarification |
| search-preference-10 | local-rules | 2 | category; keywords.concept[0]; keywords.concept[1]; keywords.extra[0]; clarification; retrieval_exact |
| search-ood-07 | local-rules | 2 | category; clarification |
| search-core-03 | local-rules | 2 | keywords.concept[0]; keywords.extra[0] |
| search-confusable-03-rewrite | local-rules | 2 | keywords.concept[0]; keywords.extra[0]; retrieval_exact |
| search-price-06 | local-rules | 2 | keywords.concept[0]; keywords.extra[0]; retrieval_exact |
| search-confusable-03 | local-rules | 2 | keywords.concept[0]; keywords.extra[0]; retrieval_exact |
| search-confusable-06 | local-rules | 2 | keywords.concept[0]; keywords.extra[0]; retrieval_exact |
| search-price-05 | local-rules | 2 | keywords.concept[0]; keywords.extra[0] |
| search-ambiguity-10 | local-rules | 2 | category; max_price; keywords.concept[0]; keywords.extra[0]; excluded_keywords.extra[0]; clarification; retrieval_exact |
| search-preference-06 | local-rules | 2 | keywords.concept[1]; retrieval_exact |
| search-preference-06 | oracle | 2 | retrieval_exact |
| search-ambiguity-04 | local-rules | 2 | max_price; clarification |
| search-confusable-07 | oracle | 2 | retrieval_exact |
| search-confusable-07 | local-rules | 2 | retrieval_exact |
| search-negation-02 | oracle | 2 | retrieval_exact |
| search-negation-02 | local-rules | 2 | retrieval_exact |
| search-confusable-04 | local-rules | 2 | keywords.concept[0]; retrieval_exact |
| search-confusable-04 | oracle | 2 | retrieval_exact |

## 分场景与重复执行

切片使用 `slice:` 标签。同一用例可出现在多个标签中；切片行不能相加作为总样本数。重复一致率以用例为单位，要求计划内各次执行全部成功且输出 JSON 完全一致（对象键顺序忽略，数组顺序保留）。

| 模型 | 任务 | 集合 | 重复一致率／用例数 | 首次 Schema 通过率 |
| --- | --- | --- | --- | ---: |
| local-rules | smart_search | dev | 98.8%／80 | 未知 |
| oracle | smart_search | dev | 100.0%／80 | 未知 |

| 模型 | 场景 | 集合 | 用例数 | 通过率 | MRR | MAP@5 | Recall@10 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| local-rules | ambiguity | dev | 10 | 20.0% | 0.750 | 0.750 | 0.750 |
| local-rules | confusable | dev | 11 | 27.3% | 0.742 | 0.750 | 1.000 |
| local-rules | core | dev | 14 | 35.7% | 0.714 | 0.714 | 0.714 |
| local-rules | negation | dev | 11 | 36.4% | 0.781 | 0.773 | 0.818 |
| local-rules | ood | dev | 10 | 0.0% | 0.929 | 0.929 | 1.000 |
| local-rules | preference | dev | 11 | 45.5% | 0.773 | 0.773 | 0.818 |
| local-rules | price | dev | 13 | 15.4% | 0.674 | 0.638 | 0.917 |
| oracle | ambiguity | dev | 10 | 90.0% | 1.000 | 1.000 | 1.000 |
| oracle | confusable | dev | 11 | 81.8% | 0.909 | 0.917 | 1.000 |
| oracle | core | dev | 14 | 85.7% | 1.000 | 1.000 | 1.000 |
| oracle | negation | dev | 11 | 45.5% | 0.864 | 0.864 | 0.909 |
| oracle | ood | dev | 10 | 100.0% | 1.000 | 1.000 | 1.000 |
| oracle | preference | dev | 11 | 54.5% | 0.864 | 0.864 | 0.909 |
| oracle | price | dev | 13 | 69.2% | 1.000 | 0.983 | 0.983 |

## 解析指标：local-rules／smart_search／dev

| 字段 | 样本数（含重复） | 准确率 | Macro-F1 |
| --- | ---: | ---: | ---: |
| category | 240 | 78.8% | 0.791 |
| max_price | 240 | 83.8% | 未知 |
| campus | 240 | 98.8% | 0.998 |
| condition_grade | 240 | 98.8% | 0.999 |
- `keywords`：Micro-P/R/F1=0.685/0.677/0.681；逐例 Macro-F1=0.633。
- `excluded_keywords`：Micro-P/R/F1=0.867/1.000/0.929；逐例 Macro-F1=0.975。
- `preferences`：Micro-P/R/F1=0.857/1.000/0.923；逐例 Macro-F1=0.988。
- 澄清触发 F1=0.308，应澄清 18/240 例。

## 解析指标：oracle／smart_search／dev

| 字段 | 样本数（含重复） | 准确率 | Macro-F1 |
| --- | ---: | ---: | ---: |
| category | 240 | 100.0% | 1.000 |
| max_price | 240 | 100.0% | 未知 |
| campus | 240 | 100.0% | 1.000 |
| condition_grade | 240 | 100.0% | 1.000 |
- `keywords`：Micro-P/R/F1=1.000/1.000/1.000；逐例 Macro-F1=1.000。
- `excluded_keywords`：Micro-P/R/F1=1.000/1.000/1.000；逐例 Macro-F1=1.000。
- `preferences`：Micro-P/R/F1=1.000/1.000/1.000；逐例 Macro-F1=1.000。
- 澄清触发 F1=1.000，应澄清 18/240 例。

## 固定商品库搜索

排名指标以有相关商品且适用检索的查询为分母；执行失败按 0 分计入。MRR 使用完整排序，AP@5 的分母为 min(5,相关商品数)，Recall@10 的分母为全部相关商品数。无相关商品查询不计入三项排名均值，但整例检查要求返回空集。歧义查询可声明仅评价解析。

零结果误杀率只统计有相关商品、结构有效且执行成功的查询，执行错误另计错误率。端到端耗时覆盖解析与实际检索，不包含固定库建库和 HTTP 鉴权／传输；解析与检索阶段另列。Oracle 只注入预标注解析，不注入相关商品答案。

| 模型 | 集合 | 排名样本数 | MRR | MAP@5 | Recall@10 | 零结果误杀率／分母 | 解析 P95 ms | 搜索端到端 P95 ms |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| local-rules | dev | 210 | 0.755 | 0.749 | 0.857 | 12.9%／210 | 0.1 | 1.1 |
| oracle | dev | 210 | 0.943 | 0.941 | 0.969 | 2.9%／210 | 0.0 | 0.7 |

## 相对本地规则

只比较相同用例和重复次数。错误率降低=(模型整例通过率−本地通过率)/(1−本地通过率)，本地已全对时留空；排名指标报告绝对增量。

| 模型 | 本地基线 | 任务／集合 | 通过率增量 | 整例错误率降低 | MRR 增量 | MAP@5 增量 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| oracle | local-rules | smart_search／dev | 48.8% | 66.1% | 0.188 | 0.192 |

## 蜕变关系

不变关系比较规范化解析和完整结果 ID 集合；方向关系比较完整集合的子集、价格及排除商品约束。错误或缺失执行计失败；空基例单列，避免把空集关系当作充分证据。

| 模型 | 关系执行数 | 通过 | 非空基例数 |
| --- | ---: | ---: | ---: |
| local-rules | 36 | 27 | 33 |
| oracle | 36 | 33 | 36 |
- `local-rules`／`inv-core-05`／第 1 次：intent_invariant, result_set_invariant
- `local-rules`／`inv-core-05`／第 2 次：intent_invariant, result_set_invariant
- `local-rules`／`inv-core-05`／第 3 次：intent_invariant, result_set_invariant
- `local-rules`／`inv-price-02`／第 1 次：intent_invariant, result_set_invariant
- `local-rules`／`inv-price-02`／第 2 次：intent_invariant, result_set_invariant
- `local-rules`／`inv-price-02`／第 3 次：intent_invariant, result_set_invariant
- `local-rules`／`dir-preference-03-preference-04`／第 1 次：excluded_items_absent
- `local-rules`／`dir-preference-03-preference-04`／第 2 次：excluded_items_absent
- `local-rules`／`dir-preference-03-preference-04`／第 3 次：excluded_items_absent
- `oracle`／`dir-preference-03-preference-04`／第 1 次：excluded_items_absent
- `oracle`／`dir-preference-03-preference-04`／第 2 次：excluded_items_absent
- `oracle`／`dir-preference-03-preference-04`／第 3 次：excluded_items_absent

分类 Macro-F1 的类别集合为本组标准答案中出现的类别，包含显式 null；支持数保存在 summary.json。集合字段的双方空集计 1，结构／执行失败计 0，Micro 汇总为无效预测保留一个错误项。无澄清正例且无误报时澄清 F1 留空。首次 Schema 通过率要求首次请求成功且原始结构有效，重试成功不算首次通过。
