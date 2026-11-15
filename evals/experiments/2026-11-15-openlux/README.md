# 2026-11-15 OpenLux 全候选实验

运行 `20261115T111828Z-e16d7659`：136 条用例，六款模型、七个远程配置，各重复三次；2,856 次远程请求，加本地规则和 Oracle 共 3,480 条记录。

结论与方法见[模型选型报告](../../../docs/MODEL_SELECTION_REPORT.md)，复现命令见[执行说明](../../../docs/SEARCH_EVALUATION.md)。

- `summary.json`：任务、场景、字段、排名、关系及自动选型状态。
- `analysis.json`：公开文案独立分组、分轮错误、思考元数据、格式诊断、门槛和配对区间。
- `provenance.json`：模型参数、数据／代码／原始记录哈希、环境版本及本机原始记录位置。
- `policy.json`：运行前冻结的搜索草案门槛。
- `verification.json`：完整矩阵、请求数、模型 ID 和 600 条离线对照的核验结果。
- `cost_observation.json`：窗口级计量增量，不包含其他历史账目或密钥。

原始文案、模型回答与图片保留在本机数据／运行目录；此目录只发布汇总和复查所需的指纹。标签仍为 `draft/dev`。

- [漏匹配清单](missed_matches.md)及[逐例明细](missed_matches.json)：预期／实际商品、缺失 ID、商品信息、解析差异与重复轮次。

- [漏匹配原因分析](missed_match_causes.md)：按商品名解释解析、检索、接口及排序问题，附离线字段干预证据。
