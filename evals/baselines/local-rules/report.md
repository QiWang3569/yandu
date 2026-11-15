# 燕渡模型评测报告

运行：20261114T173052Z-86a9be5f；时间：2026-11-15 01:30:52 北京时间。
代码：`6951c5c3df449cba995b122f9d8401e76c617e70`；工作区未提交修改：True；运行完整：True。
测试集：`3ae891897e610690171ed8cf802bed259843dc6224a508f759401be03bede670`；评分器：`1.0.0`；每例重复 1 次。

每次运行均保留失败结果。通过率以全部计划内已执行结果为分母；完整性另列，未完成运行不产生选型建议。费用未知时保留未知，已知费用小计不等同于总费用。

| 模型配置 | 任务 | 集合 | 用例／执行次数 | 完整 | 通过率 | 平均评分 | 错误率 | P95 毫秒 | 平均费用 元 |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| local-rules | intent_parse | dev | 24／24 | True | 58.3% | 0.934 | 0.0% | 4.3 | 0.000000 |
| local-rules | item_parse | dev | 8／8 | True | 25.0% | 0.842 | 0.0% | 2.1 | 0.000000 |
| local-rules | wanted_parse | dev | 8／8 | True | 62.5% | 0.885 | 0.0% | 1.3 | 0.000000 |

## 选型结论

**intent_parse**：尚未确定优选模型。
选型规则仍为草案；团队须在保留集评测前确认并设为 confirmed 或 locked。 当前为开发集或本地基线诊断，尚无保留集对照。 保留集 0 例，少于预设的 20 例。 同一任务至少需要两个远程候选模型的完整对照。

**item_parse**：尚未确定优选模型。
选型规则仍为草案；团队须在保留集评测前确认并设为 confirmed 或 locked。 当前为开发集或本地基线诊断，尚无保留集对照。 保留集 0 例，少于预设的 20 例。 同一任务至少需要两个远程候选模型的完整对照。

**wanted_parse**：尚未确定优选模型。
选型规则仍为草案；团队须在保留集评测前确认并设为 confirmed 或 locked。 当前为开发集或本地基线诊断，尚无保留集对照。 保留集 0 例，少于预设的 20 例。 同一任务至少需要两个远程候选模型的完整对照。

## 评分与运行说明

规则状态：draft。预设实验规则。需求解析整例正确率目标沿用课程材料；文字提取使用平均断言评分，不等同于原目标中的字段总准确率。其余门槛为本次拟定，须由团队在保留集评测前确认，并将 status 改为 confirmed 或 locked。

整例通过率要求所有已声明断言通过；平均评分为每例断言得分的均值，不等同于按字段总数加权的准确率。匹配精筛的 macro-F1 固定平均 MATCH、NO_MATCH、UNCERTAIN 三类；某类没有样本时该类 F1 为 0，因此报告同时保留各类样本量。错误推荐率以标准答案非 MATCH 的候选数为分母。逐字引用校验不能替代人工核查证据是否支持结论。

P50／P95 对包含重试的整次调用耗时做线性插值；本地规则耗时不用于与远程模型的网络耗时选型比较。原始模型输出、应用校验后的结果和回退状态保存在 records.jsonl。

- `local-rules`／intent_parse／dev：原始结果通过率 未知，应用结果通过率 58.3%，macro-F1 未知，错误推荐率 未知，回退 0 次。
- `local-rules`／item_parse／dev：原始结果通过率 未知，应用结果通过率 25.0%，macro-F1 未知，错误推荐率 未知，回退 0 次。
- `local-rules`／wanted_parse／dev：原始结果通过率 未知，应用结果通过率 62.5%，macro-F1 未知，错误推荐率 未知，回退 0 次。

## 失败用例

完整结果与输出见 records.jsonl；下表列出最多 100 条失败记录。

| 用例 | 模型 | 重复 | 原因 |
| --- | --- | ---: | --- |
| intent-015 | local-rules | 1 | keywords.extra[1] |
| item-006 | local-rules | 1 | price |
| intent-014 | local-rules | 1 | max_price |
| item-008 | local-rules | 1 | price; clarification |
| intent-024 | local-rules | 1 | keywords.concept[1] |
| intent-021 | local-rules | 1 | campus |
| wanted-003 | local-rules | 1 | budget |
| item-001 | local-rules | 1 | price |
| wanted-005 | local-rules | 1 | budget |
| item-004 | local-rules | 1 | price |
| item-002 | local-rules | 1 | price |
| intent-018 | local-rules | 1 | keywords.extra[0] |
| intent-006 | local-rules | 1 | max_price |
| intent-022 | local-rules | 1 | keywords.concept[0]; keywords.extra[0] |
| intent-017 | local-rules | 1 | clarification |
| wanted-007 | local-rules | 1 | clarification |
| intent-007 | local-rules | 1 | max_price |
| item-005 | local-rules | 1 | price |
| intent-020 | local-rules | 1 | excluded_keywords.concept[0] |
