# AI 模块选型与测试报告

本文件汇总第 8 次汇报的两项交付：① 5 个 AI 模块的候选模型选型指标与具体通过/不通过样例；② 各子模块单元测试的每模块 5 正确 + 5 错误样例（共 50 条）与全量结果。逐节点细节见 [AI_EVALUATION.md](AI_EVALUATION.md) 与 [AI_TEST_CASES.md](AI_TEST_CASES.md)。

- 数据集：`backend/eval/datasets/manifest.json` 冻结版本 `2026-11-23-v3`；1.1=20、1.2=15、2.1=30、2.4=30、1.4=16 条，`dev`/`sealed_test` 分离。
- 代码快照：git `d5b5bb6`（工作区有未提交改动，`git_dirty=true`）；提示词 `item-2 / vision-publish-3 / intent-3 / review-1 / concept-1`。
- 真实调用：`eval.cli run --real`；三份 sealed 报告 `verify` 均为 `report_ok=true`、`dataset_verified=true`、`fixture=false`。
- 选型规则在真实调用前预注册（[AI_EVALUATION.md §3.1](AI_EVALUATION.md)）：可用性硬过滤 → 逐节点硬门禁 → 主指标最高 → p95/token 决胜 → 无候选通过则保留现模型。`dev` 只用于选型，`sealed_test` 只给胜者各跑一次，不回头调参。

## 1. 候选与胜者

| 节点 | 参与比较的候选 | 胜者 | 部署建议 |
|---|---|---|---|
| 1.1 文案提取 | text-primary / text-alt / text-alt-2 | text-alt `deepseek/deepseek-v4-pro-0813` | 需按节点拆分配置；差距小，保留现模型也可接受 |
| 1.2 视觉识图 | vision-primary / vision-alt | vision-primary `qwen/qwen3.7-flash` | 保持现配置 |
| 2.1 意图解析 | text-primary / text-alt / text-alt-2 | text-alt `deepseek/deepseek-v4-pro-0813` | 需按节点拆分配置 |
| 2.4 候选精筛 | text-primary / text-alt / text-alt-2 | text-primary `deepseek/deepseek-v4.1-flash` | 保持现配置 |
| 1.4 概念族学习 | text-primary / text-alt / text-alt-2 | 无（保留 text-primary） | 保持现配置，别名提取列为待改进 |

Embedding 候选因 `EMBEDDING_*` 未配置为 `UNAVAILABLE`，未参与比较，2.3 仍按词面召回运行并如实标注。

## 2. dev 选型指标表

报告目录：`reports/eval/2026-11-23-model-selection-dev/`。“门禁”指该节点预注册硬约束是否全部通过。

### 2.1 文案提取（n=8）

| 候选 | field_macro_f1 | valid_rate | clarification | p95 | tokens in/out | 硬门禁 | 结论 |
|---|---:|---:|---:|---:|---|---|---|
| text-primary | 0.867 | 1.000 | 1.000 | 1 570 ms | 4 668 / 863 | 通过 | 质量次优 |
| text-alt | 0.873 | 1.000 | 1.000 | 3 542 ms | 5 420 / 884 | 通过 | **胜出**（主指标最高） |
| text-alt-2 | 0.848 | 1.000 | 0.875 | 31 140 ms | 4 379 / 4 299 | 未通过（F1<0.85，p95>20 s） | 淘汰 |

### 2.2 视觉识图（n=6）

| 候选 | status_accuracy | category_accuracy | unsupported_rate | p95 | tokens in/out | 硬门禁 | 结论 |
|---|---:|---:|---:|---:|---|---|---|
| vision-primary | 1.000 | 1.000 | 0.000 | 3 941 ms | 8 688 / 656 | 通过 | **胜出**（status 最高） |
| vision-alt | 0.833 | 1.000 | 0.000 | 2 375 ms | 7 566 / 472 | 通过 | 质量次优，延迟更低 |

### 2.3 意图解析（n=12）

| 候选 | field_macro_f1 | quote_recall | hard_field_exact | injection | p95 | tokens in/out | 硬门禁 | 结论 |
|---|---:|---:|---:|---:|---:|---|---|---|
| text-primary | 0.860 | 1.000 | 1.000 | 1.000 | 6 189 ms | 13 628 / 1 166 | 通过 | 质量次优 |
| text-alt | 0.880 | 1.000 | 1.000 | 1.000 | 3 919 ms | 14 756 / 1 548 | 通过 | **胜出**（F1 最高且延迟更低） |
| text-alt-2 | 0.870 | 0.972 | 0.979 | 1.000 | 54 672 ms | 12 825 / 10 325 | 未通过（p95>20 s） | 淘汰 |

### 2.4 候选精筛（n=12）

| 候选 | match_recall | verdict_accuracy | grounding | 排除误收 | 偏好单独拒绝 | p95 | tokens in/out | 硬门禁 | 结论 |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| text-primary | 1.000 | 0.833 | 1.000 | 0 | 0 | 1 653 ms | 5 736 / 584 | 通过 | **胜出（唯一全过）** |
| text-alt | 0.667 | 0.667 | 1.000 | 0 | 1 | 10 179 ms | 7 901 / 872 | 未通过（valid 0.917、偏好单独拒绝 1） | 淘汰 |
| text-alt-2 | 1.000 | 0.833 | 1.000 | 0 | 0 | 43 796 ms | 5 457 / 5 432 | 未通过（p95>20 s） | 淘汰 |

### 2.5 概念族学习（n=6，金标 AI 起草待复核）

| 候选 | accept_accuracy | family_f1 | alias_f1 | grounded_rate | schema_valid | p95 | tokens in/out | 硬门禁 | 结论 |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| text-primary | 1.000 | 1.000 | 0.389 | 1.000 | 1.000 | 5 250 ms | 2 961 / 392 | 未通过（alias_f1<0.70） | 保留现模型 |
| text-alt | 0.833 | 0.800 | 0.556 | 1.000 | 1.000 | 3 410 ms | 3 525 / 265 | 未通过（alias_f1<0.70） | 淘汰 |
| text-alt-2 | 0.833 | 0.800 | 0.433 | 0.833 | 0.833 | 88 399 ms | 3 703 / 5 416 | 未通过（valid/schema/grounded/p95） | 淘汰 |

## 3. sealed 胜者复核

sealed 只给各节点胜者跑一次，是描述性 holdout，不与 dev 合并计算。报告目录：

| 报告目录 | 节点 | 胜出候选 |
|---|---|---|
| `reports/eval/2026-11-23-selected-sealed-text-alt/` | 1.1、2.1 | text-alt `deepseek/deepseek-v4-pro-0813` |
| `reports/eval/2026-11-23-selected-sealed-text-primary/` | 2.4、1.4 | text-primary `deepseek/deepseek-v4.1-flash` |
| `reports/eval/2026-11-23-selected-sealed-vision-primary/` | 1.2 | vision-primary `qwen/qwen3.7-flash` |

| 节点 | 指标 | sealed | 门槛 | 结论 |
|---|---|---:|---|---|
| 1.1 | valid_rate | 1.000 | ≥0.98 | 通过 |
| 1.1 | field_macro_f1 | 0.881 | ≥0.85 | 通过 |
| 1.1 | clarification_accuracy | 1.000 | ≥0.80（软） | 通过 |
| 1.2 | status_accuracy | 1.000 | ≥0.80 | 通过 |
| 1.2 | category_accuracy | 0.889 | ≥0.80 | 通过 |
| 1.2 | unsupported_attribute_rate | 0.333 | ≤0.05 | **未通过** |
| 2.1 | valid_rate | 0.944 | ≥0.98 | **未通过**（1 条供应商失败） |
| 2.1 | field_macro_f1 | 0.864 | ≥0.85 | 通过 |
| 2.1 | hard_field_exact | 0.917 | ≥0.90 | 通过 |
| 2.1 | quote_recall | 0.931 | ≥0.95 | **未通过** |
| 2.1 | injection_structure_rate | 1.000 | =1.0 | 通过 |
| 2.4 | verdict_accuracy | 0.778 | ≥0.80（软） | 未通过 |
| 2.4 | match_recall | 0.923 | ≥0.85 | 通过 |
| 2.4 | grounding_rate | 1.000 | =1.0 | 通过 |
| 2.4 | exclusion_false_accept | 0 | =0 | 通过 |
| 2.4 | preference_only_reject | 0 | =0 | 通过 |
| 1.4 | accept_accuracy | 0.800 | ≥0.80 | 通过 |
| 1.4 | family_f1 | 0.750 | ≥0.70 | 通过 |
| 1.4 | alias_f1 | 0.367 | ≥0.70 | **未通过** |
| 1.4 | evidence_grounded_rate | 1.000 | =1.0 | 通过 |

调用与延迟：

| 节点 | 样本 | 调用 | 输入 token | 输出 token | 失败 | p95 延迟 |
|---|---:|---:|---:|---:|---:|---:|
| 1.1 | 12 | 12 | 8 096 | 1 182 | 0 | 3 335 ms |
| 1.2 | 9 | 9 | 13 032 | 1 210 | 0 | 2 247 ms |
| 2.1 | 18 | 20 | 24 557 | 2 125 | 1 | 5 076 ms |
| 2.4 | 18 | 18 | 8 163 | 952 | 0 | 3 077 ms |
| 1.4 | 10 | 10 | 4 905 | 737 | 0 | 1 458 ms |

sealed 暴露的选型风险如实保留：vision-primary 在 dev 上 `unsupported_attribute_rate=0`，sealed 为 0.333；2.1 出现 1 次供应商失败且引文召回 0.931；2.4 判定准确率 0.778；1.4 别名 F1 0.367。按预注册规则不据此改选型或提示词。

## 4. 逐例判定统计

判定由 `eval.cli cases` 生成，规则比字段指标更严格：1.1 要求 category/price/campus/condition 四项全等；1.2 要求 status、category 全等且描述不含禁用词；2.1 要求四个硬字段全等**且** `gold_quotes` 全部命中；2.4 要求 verdict 全等、引文接地率 1、无排除误收；1.4 要求决策/原因类别一致、金标家族名 ⊆ 预测家族名、别名逐字接地。

| 模块 | sealed 样本 | 正确 | 错误 | 裁决级准确率 | 错误 ID |
|---|---:|---:|---:|---:|---|
| 1.1 文案提取 | 12 | 11 | 1 | 0.917 | `1.1-020` |
| 1.2 视觉识图 | 9 | 6 | 3 | 0.667 | `1.2-004` `1.2-007` `1.2-012` |
| 2.1 意图解析 | 18 | 14 | 4 | 0.778 | `2.1-004` `2.1-007` `2.1-009` `2.1-014` |
| 2.4 候选精筛 | 18 | 14 | 4 | 0.778 | `2.4-015` `2.4-024` `2.4-025` `2.4-030` |
| 1.4 概念族学习 | 10 | 6 | 4 | 0.600 | `1.4-008` `1.4-011` `1.4-015` `1.4-016` |

裁决级准确率低于字段指标是正常的：它要求一条样本的所有硬字段同时正确，字段 macro-F1 允许逐字段部分得分。

## 5. 每模块 1 条正确 + 1 条错误（完整样例）

以下 10 条均为 sealed，模型为各节点胜者。原始逐例输出可用 `eval.cli cases --report <报告目录> --node <节点>` 重新生成。

### 5.1 文案提取（text-alt）

正确 11 条：`1.1-005, 1.1-006, 1.1-007, 1.1-008, 1.1-009, 1.1-010, 1.1-013, 1.1-014, 1.1-016, 1.1-018, 1.1-019`；错误 1 条：`1.1-020`。

正确样例 `1.1-005`：

```json
输入: {"raw": "Dell 24 英寸显示器，1080P，320元，燕园校本部，九成新，无坏点，附 HDMI 线。"}
金标: {"category": "数码与影音", "price": 320, "campus": "燕园校本部", "condition_grade": "9成新", "tags": ["显示器"], "clarification_required": false}
实际: {"title": "Dell 24英寸显示器", "category": "数码与影音", "price": 320.0, "campus": "燕园校本部", "condition_grade": "9成新", "tags": ["Dell", "24英寸", "1080P", "显示器", "无坏点", "HDMI线"], "clarification": null}
判定: 正确（category/price/campus/condition 四项全等；tags 多出品牌与规格词，tags 按集合 F1 单列，不参与本条裁决）
```

错误样例 `1.1-020`：

```json
输入: {"raw": "东西很新，价格好商量，燕园校本部自取。"}
金标: {"category": null, "price": null, "campus": "燕园校本部", "condition_grade": null, "tags": [], "clarification_required": true}
实际: {"title": null, "category": null, "price": null, "campus": "燕园校本部", "condition_grade": "95新", "tags": [], "clarification": "未说明具体商品信息，无法确定分类、标题和成色。"}
判定: 错误（差异字段 condition_grade：金标留空，模型在信息不足时臆造“95新”）
```

### 5.2 视觉识图（vision-primary）

正确 6 条：`1.2-005, 1.2-006, 1.2-008, 1.2-013, 1.2-014, 1.2-015`；错误 3 条：`1.2-004, 1.2-007, 1.2-012`。

正确样例 `1.2-005`：

```json
输入: {"images": [{"file": "images/1.2-005.jpg"}], "note": ""}
金标: {"status": "ready", "category": "数码与影音", "title_keywords": ["Monitor"], "tags": [], "forbidden_terms": ["4K", "全新", "曲面"], "uncertainties_required": false}
实际: {"status": "ready", "title": "黑色显示器", "category": "数码与影音", "description": "黑色长方形电脑显示器，正面屏幕处于关闭状态，下边框中央有一个圆形电源按钮或传感器，配有黑色方形底座，后方连接有线缆。", "tags": ["显示器", "黑色", "电脑配件"], "uncertainties": ["图片未显示品牌、型号及具体尺寸参数", "无法确认屏幕分辨率及接口类型"]}
判定: 正确（status、category 与金标一致；描述未出现 4K/全新/曲面等禁用词）
```

错误样例 `1.2-004`：

```json
输入: {"images": [{"file": "images/1.2-004.jpg"}], "note": ""}
金标: {"status": "ready", "category": "宿舍生活与家电", "title_keywords": ["Lamp"], "tags": [], "forbidden_terms": ["无线", "金属", "全新"], "uncertainties_required": false}
实际: {"status": "ready", "title": "黄色台灯", "category": "宿舍生活与家电", "description": "黄色金属台灯，带有可调节的双关节支架和圆形底座，灯罩内部为白色，连接有一根黄色电源线。", "tags": ["黄色台灯", "台灯", "宿舍灯具"], "uncertainties": ["未看到品牌或型号标识，请补充具体品牌型号", "无法确认是否包含开关及插头类型"]}
判定: 错误（差异字段 forbidden:金属：描述写“黄色金属台灯”，属于无依据材质推断）
```

### 5.3 意图解析（text-alt）

正确 14 条：`2.1-005, 2.1-006, 2.1-008, 2.1-010, 2.1-015, 2.1-016, 2.1-017, 2.1-018, 2.1-019, 2.1-020, 2.1-023, 2.1-026, 2.1-029, 2.1-030`；错误 4 条：`2.1-004, 2.1-007, 2.1-009, 2.1-014`。

正确样例 `2.1-005`：

```json
输入: {"query": "收个 24 寸显示器，350 以内，燕园，最好无坏点"}
金标: {"category": "数码与影音", "max_price": 350, "campus": "燕园校本部", "condition_grade": null, "keywords": ["显示器"], "excluded_keywords": [], "preferences": ["无坏点"], "clarification_required": false, "gold_quotes": ["显示器", "350", "燕园", "无坏点"]}
实际: {"category": "数码与影音", "max_price": 350.0, "campus": "燕园校本部", "keywords": ["显示器", "24 寸"], "excluded_keywords": [], "preferences": ["无坏点"], "condition_grade": null, "clarification": null, "quotes": ["350", "燕园", "显示器", "24 寸", "无坏点"]}
判定: 正确（category/max_price/campus/condition 全等；4 段 gold_quotes 全部逐字命中）
```

错误样例 `2.1-007`：

```json
输入: {"query": "想要索尼降噪耳机，600 左右，最好无线"}
金标: {"category": "数码与影音", "max_price": 600, "campus": "不限校区", "condition_grade": null, "keywords": ["耳机", "降噪"], "excluded_keywords": [], "preferences": ["无线"], "clarification_required": false, "gold_quotes": ["耳机", "600", "降噪", "无线"]}
实际: {"category": "数码与影音", "max_price": null, "campus": "不限校区", "keywords": ["索尼", "降噪耳机"], "excluded_keywords": [], "preferences": ["无线"], "condition_grade": null, "clarification": null, "quotes": ["索尼", "降噪耳机", "无线"]}
判定: 错误（差异字段 max_price、quotes：600 左右的预算没有落地为 max_price=600，引文缺“600”）
```

### 5.4 候选精筛（text-primary）

正确 14 条：`2.4-004, 2.4-005, 2.4-007, 2.4-009, 2.4-010, 2.4-011, 2.4-013, 2.4-017, 2.4-019, 2.4-020, 2.4-021, 2.4-026, 2.4-028, 2.4-029`；错误 4 条：`2.4-015, 2.4-024, 2.4-025, 2.4-030`。

正确样例 `2.4-005`：

```json
输入: {"intent": {"keywords": ["静音", "鼠标"], "excluded_keywords": ["游戏鼠标"], "preferences": ["无线"], "category": "数码与影音", "max_price": 300, "campus": "万柳学区", "condition_grade": null}, "item": {"id": "A5", "title": "静音鼠标", "description": "静音鼠标，底部轻微磨损", "tags": ["鼠标", "静音"], "price": 99, "campus": "万柳学区", "condition_grade": "8成新"}}
金标: {"verdict": "MATCH", "preference_missing": true}
实际: {"item_id": "A5", "verdict": "MATCH", "evidence": [{"criterion": "静音", "quote": "静音鼠标"}, {"criterion": "鼠标", "quote": "静音鼠标"}], "questions": ["是否支持无线连接？"]}
判定: 正确（硬条件齐备判 MATCH；无线偏好缺失只生成向卖家确认的问题，没有单独拒绝）
```

错误样例 `2.4-024`：

```json
输入: {"intent": {"keywords": ["耳机"], "excluded_keywords": ["入耳式"], "preferences": ["降噪"], "category": "数码与影音", "max_price": 700, "campus": "不限校区", "condition_grade": null}, "item": {"id": "E4", "title": "耳机", "description": "耳机，型号不明", "tags": ["耳机"], "price": 30, "campus": "昌平新校区", "condition_grade": "8成新"}}
金标: {"verdict": "MATCH", "preference_missing": true}
实际: {"item_id": "E4", "verdict": "UNCERTAIN", "evidence": [{"criterion": "耳机", "quote": "耳机"}], "questions": ["这款耳机是入耳式还是非入耳式？", "这款耳机是否支持降噪？"]}
判定: 错误（差异字段 verdict：降噪只是偏好，硬条件“耳机”已满足，应判 MATCH；模型把偏好当成硬条件降级为 UNCERTAIN）
```

### 5.5 概念族学习（text-primary，金标待人工复核）

正确 6 条：`1.4-007, 1.4-009, 1.4-010, 1.4-012, 1.4-013, 1.4-014`；错误 4 条：`1.4-008, 1.4-011, 1.4-015, 1.4-016`。

正确样例 `1.4-007`：

```json
输入: {"item": {"title": "《概率论与数理统计》浙大第五版", "description": "少量荧光笔标记 九成新", "tags": ["教材"], "category": "课程资料与书籍"}, "catalog": [{"name": "教材", "definition": "课程学习用书", "category": "课程资料与书籍", "parent": null, "aliases": ["课本"]}]}
金标: {"decision": "apply", "reason": "learned", "families": [{"name": "教材", "parent": null, "aliases": []}]}
实际: {"decision": "apply", "reason": "learned", "families": [{"name": "教材", "parent": null, "aliases": []}], "aliases": [], "evidence_grounded": true, "schema_valid": true}
判定: 正确（复用已有“教材”族，决策、家族名与原因类别一致）
```

错误样例 `1.4-008`：

```json
输入: {"item": {"title": "露营折叠椅 克米特椅", "description": "铝合金 承重120kg 九成新", "tags": ["椅子"], "category": "校园出行与运动"}, "catalog": [{"name": "户外装备", "definition": "户外活动用品", "category": "校园出行与运动", "parent": null, "aliases": ["露营"]}]}
金标: {"decision": "apply", "reason": "learned", "families": [{"name": "折叠椅", "parent": "户外装备", "aliases": ["克米特椅"]}]}
实际: {"decision": "apply", "reason": "learned", "families": [{"name": "户外装备", "parent": null, "aliases": ["露营折叠椅", "克米特椅"]}], "aliases": ["露营折叠椅", "克米特椅"], "evidence_grounded": true, "schema_valid": true}
判定: 错误（差异字段 missing:折叠椅：模型把商品直接挂到父类“户外装备”，没有建立更具体的“折叠椅”子族，家族粒度过粗）
```

1.4 金标由 AI 起草、尚待逐行人工复核，有两处条件性问题需说明：

- `1.4-015`（帆布鞋 + 全新）金标要求 `reject/forbidden_alias`；模型没有把“全新”写成别名（行为更安全），按金标仍记为错误。金标无法表达“两种都可接受”。
- `1.4-016`（“壶”）金标为 `reject/invalid_name`，模型确实拒绝但原因记为 `invalid_alias`，原因类别不同。
- 因此 1.4 的 `accept_accuracy`/`family_f1` 可参考，`alias_f1` 与拒绝原因类别只作诊断；待人工复核金标后再决定是否保留这些分层。

## 6. 单元测试：每模块 5 正确 + 5 错误（共 50 条）

判定约定：`判定=正确` 表示实际行为与预期一致；“错误样例”的预期本身是拒绝、回退或降级，按预期被处理即为正确，不代表模型判对。所有用例在桩模型/临时数据库下执行，不访问真实网络。T11-C3~C5、T11-W3~W5、T21-W4~W5 为本轮新增；其余复用既有用例。

### 6.1 文案提取（1.1）

| 类型 | 样例 ID | pytest nodeid | 输入/触发 | 预期结果 | 实际结果 | 判定 |
|---|---|---|---|---|---|---|
| 正确 1 | T11-C1 | `test_config_services_admin_cli.py::test_parse_item_local_extracts_every_field` | `静音无线鼠标，¥280，万柳学区，九五新` | 六个字段全部正确 | title=静音无线鼠标、category=数码与影音、price=280、campus=万柳学区、condition=95新、tags=[鼠标,静音,无线] | 正确 |
| 正确 2 | T11-C2 | `test_config_services_admin_cli.py::test_parse_item_remote_success_and_local_fallback` | 远程合法 JSON；供应商 down | 远程字段被采用；不可用回退本地 | 远程 price=100；provider down 时回退 price=300 | 正确 |
| 正确 3 | T11-C3 | `test_config_services_admin_cli.py::test_parse_item_local_reads_chinese_price_condition_and_campus` | `台灯，售价120元，昌平新校区，八成新` | 中文价格/校区/成色正确抽取 | price=120、campus=昌平新校区、condition=8成新 | 正确 |
| 正确 4 | T11-C4 | `test_config_services_admin_cli.py::test_parse_item_remote_accepts_numeric_price_and_eight_tags` | 远程 JSON：price=35（数字）、8 个 tags | 数字价格与满额标签被接受 | price=35、campus=医学部、condition=9成新、tags 8 项 | 正确 |
| 正确 5 | T11-C5 | `test_config_services_admin_cli.py::test_parse_item_remote_keeps_a_full_length_description` | description 3000 字、price="199.99" | 长度上限内完整保留 | len(description)=3000、price=199.99 | 正确 |
| 错误 1 | T11-W1 | `test_config_services_admin_cli.py::test_parse_item_invalid_remote_fields_fall_back_to_local` | 非法分类/负价/火星校区/十成新 | 整体回退本地 | 回退后 price=300、campus=燕园校本部 | 正确（按预期回退） |
| 错误 2 | T11-W2 | `test_config_services_admin_cli.py::test_parse_item_blank_or_punctuation_input_does_not_crash` | `，。！？ ` | 不崩溃，字段留空 | title=None、price=None、tags=[]，无异常 | 正确（按预期降级） |
| 错误 3 | T11-W3 | `test_config_services_admin_cli.py::test_parse_item_remote_non_object_payload_falls_back` | 远程返回 `["not","an","object"]` | 非对象载荷回退本地 | 回退后 price=300 | 正确（按预期回退） |
| 错误 4 | T11-W4 | `test_config_services_admin_cli.py::test_parse_item_remote_out_of_range_price_falls_back` | 远程 price=1000000 | 校验失败回退本地 | 回退后 price=250 | 正确（按预期回退） |
| 错误 5 | T11-W5 | `test_config_services_admin_cli.py::test_parse_item_remote_unknown_field_falls_back` | 多出 `seller_phone` 字段 | `extra='forbid'` 触发回退 | 回退后 price=280 | 正确（按预期回退） |

### 6.2 视觉识图（1.2）

| 类型 | 样例 ID | pytest nodeid | 输入/触发 | 预期结果 | 实际结果 | 判定 |
|---|---|---|---|---|---|---|
| 正确 1 | T12-C1 | `test_vision.py::test_owner_only_no_publish_and_cache` | 1 张本人图片 + note | 草稿不发布、缓存命中、他人 404 | 200；商品数不变；第二次 0 次调用；他人 404 | 正确 |
| 正确 2 | T12-C2 | `test_vision.py::test_two_photos_share_one_request` | 2 张图片 | 合并为一次请求 | 200、请求数 1、2 个 image_url | 正确 |
| 正确 3 | T12-C3 | `test_vision.py::test_transient_retry[429]` | 供应商先 429 后成功 | 重试一次并成功 | 200、请求数 2 | 正确 |
| 正确 4 | T12-C4 | `test_vision.py::test_rate_limit_cache_and_changed_note` | 限额 1；同 payload 两次后改 note | 缓存命中后超限 429 | 200、200、429；供应商 1 次调用 | 正确 |
| 正确 5 | T12-C5 | `test_vision.py::test_inflight_deduplication_and_concurrency` | 同键并发 + 第 5 个并发 | 去重、超限 429、释放槽位 | 共享结果；4 次调用；pending 清空 | 正确 |
| 错误 1 | T12-W1 | `test_vision.py::test_bad_provider_output[not json-stop]` | 供应商返回非 JSON | 502 且脱敏 | 502，无 test-secret | 正确（按预期拒绝） |
| 错误 2 | T12-W2 | `test_vision.py::test_invalid_provider_envelope[body1]` | `{"choices": []}` | 502 | 502 | 正确（按预期拒绝） |
| 错误 3 | T12-W3 | `test_vision.py::test_corrupt_photo` | 文件内容不是图片 | 422，不调供应商 | 422、0 次调用 | 正确（按预期拒绝） |
| 错误 4 | T12-W4 | `test_vision.py::test_ready_without_any_evidence_degrades_to_unclear` | ready 但全字段为空 | 降级 unclear 并补问题 | status=unclear、title=None、uncertainties 非空 | 正确（按预期降级） |
| 错误 5 | T12-W5 | `test_vision.py::test_error_sanitized_not_cached` | 401 且错误信息含密钥 | 502 脱敏、不缓存、可重试 | 502 无密钥；下一次 200；2 次调用 | 正确（按预期拒绝） |

### 6.3 意图解析（2.1）

| 类型 | 样例 ID | pytest nodeid | 输入/触发 | 预期结果 | 实际结果 | 判定 |
|---|---|---|---|---|---|---|
| 正确 1 | T21-C1 | `test_structured_intent.py::test_structured_roles_flatten_to_public_intent` | 三角色完整 JSON | 扁平化、逐字 quotes 保留 | keywords=[鼠标,无线]、excluded=[游戏鼠标]、preferences=[静音]；quotes 6 条 | 正确 |
| 正确 2 | T21-C2 | `test_structured_intent.py::test_conditions_are_deduplicated_and_capped_at_twelve` | 15 项条件含重复 | 去重并截断到 12 | keywords=前 12 项；quotes 14 条 | 正确 |
| 正确 3 | T21-C3 | `test_structured_intent.py::test_non_verbatim_quotes_are_dropped` | budget_quote=三百元 | 非逐字引文被丢弃 | max_price=300；quotes=万柳、无线鼠标 | 正确 |
| 正确 4 | T21-C4 | `test_structured_intent.py::test_condition_phrases_are_normalized` | 九成新以上；全新或九五新都行 | 归一为 9成新 / 95新 | condition=9成新、95新 | 正确 |
| 正确 5 | T21-C5 | `test_structured_intent.py::test_invalid_enums_and_negative_price_are_sanitized` | 非法分类/火星校区/-50 | 非法值与负价清空 | category=None、campus=不限校区、max_price=None | 正确 |
| 错误 1 | T21-W1 | `test_structured_intent.py::test_blank_query_local_parse_does_not_crash` | `，。！？ ` | 不崩溃 | keywords=[]、quotes=[]、clarification 非空 | 正确（按预期降级） |
| 错误 2 | T21-W2 | `test_structured_intent.py::test_model_unavailable_is_sanitized_502` | 供应商不可用 | 502 脱敏 | 502，detail 不含供应商信息 | 正确（按预期拒绝） |
| 错误 3 | T21-W3 | `test_structured_intent.py::test_invalid_provider_shape_is_sanitized_502` | conditions 为字符串 | 502 不含凭据 | 502，无 test-credential | 正确（按预期拒绝） |
| 错误 4 | T21-W4 | `test_structured_intent.py::test_non_object_payload_is_sanitized_502` | 返回 `["不是对象"]` | 502 | 502 | 正确（按预期拒绝） |
| 错误 5 | T21-W5 | `test_structured_intent.py::test_malformed_price_is_sanitized_502` | max_price="很贵" | 502 不泄露原文 | 502，detail 不含“很贵” | 正确（按预期拒绝） |

### 6.4 候选精筛（2.4）

| 类型 | 样例 ID | pytest nodeid | 输入/触发 | 预期结果 | 实际结果 | 判定 |
|---|---|---|---|---|---|---|
| 正确 1 | T24-C1 | `test_buyer_agent.py::test_absent_exclusion_does_not_block_match` | 排除项未出现在商品文本 | grounded MATCH | verdict=MATCH，criterion=鼠标 | 正确 |
| 正确 2 | T24-C2 | `test_buyer_agent.py::test_empty_candidates_skip_provider` | 空候选 | 返回 []，不调供应商 | []，无网络调用 | 正确 |
| 正确 3 | T24-C3 | `test_buyer_agent.py::test_preferences_do_not_filter_and_exclusions_are_not_positive_requirements` | 偏好静音；普通/游戏/非游戏鼠标 | 偏好不拒绝；排除不误收 | MATCH + 静音问题；游戏鼠标不通知、非游戏鼠标通知 | 正确 |
| 正确 4 | T24-C4 | `test_buyer_agent.py::test_missing_hard_evidence_becomes_uncertain` | required 含静音，候选缺证据 | 降级 UNCERTAIN 并提问 | verdict=UNCERTAIN，questions 含静音 | 正确（按预期降级） |
| 正确 5 | T24-C5 | `test_buyer_agent.py::test_notifications_are_scoped_to_owned_wish` | 卖家访问买家 intent | 归属隔离、越权 404 | 越权的空/404；本 intent 通知齐全 | 正确 |
| 错误 1 | T24-W1 | `test_buyer_agent.py::test_assessment_rejects_criterion_outside_intent_whitelist` | criterion=静音，不在白名单 | ValueError | ValueError（Ungrounded evidence） | 正确（按预期拒绝） |
| 错误 2 | T24-W2 | `test_buyer_agent.py::test_uncertain_assessment_requires_a_question` | UNCERTAIN 无问题 | ValueError | ValueError（requires a question） | 正确（按预期拒绝） |
| 错误 3 | T24-W3 | `test_buyer_agent.py::test_semantic_review_rejects_ungrounded_or_incomplete_batches[fabricated_quote]` | quote 编造 | 整批拒绝 ModelUnavailable | ModelUnavailable | 正确（按预期拒绝） |
| 错误 4 | T24-W4 | `test_buyer_agent.py::test_exclusion_present_in_text_cannot_be_match` | 排除词出现却判 MATCH | 拒绝该 MATCH | ModelUnavailable | 正确（按预期拒绝） |
| 错误 5 | T24-W5 | `test_buyer_agent.py::test_invalid_provider_responses_are_sanitized_502[None]` | 响应为 None | 502 脱敏 | 502，无 test-credential | 正确（按预期拒绝） |

### 6.5 概念族学习（1.4）

| 类型 | 样例 ID | pytest nodeid | 输入/触发 | 预期结果 | 实际结果 | 判定 |
|---|---|---|---|---|---|---|
| 正确 1 | T14-C1 | `test_concepts.py::test_existing_family_is_reused_across_items` | 第二件商品挂已有“笔记本” | 复用 concept_id | 概念仍为 2 个；thinkpad 别名写入；链接存在 | 正确 |
| 正确 2 | T14-C2 | `test_concepts.py::test_empty_assignments_are_applied_as_no_family` | assignments=[] | APPLIED/no_family | 概念数 0；审计 APPLIED + no_family | 正确 |
| 正确 3 | T14-C3 | `test_concepts.py::test_model_learning_persists_family_hierarchy_and_links` | MacBook，提议“笔记本”父类“电脑” | 建族、父子、别名、链接持久化 | 概念={笔记本,电脑}；搜索命中 | 正确 |
| 正确 4 | T14-C4 | `test_concepts.py::test_learned_accessory_does_not_join_product_family` | 鼠标与鼠标垫分别学族 | 配件不并入产品族 | 搜“鼠标”不含鼠标垫 | 正确 |
| 正确 5 | T14-C5 | `test_concepts.py::test_async_matching_uses_learned_aliases` | 学习“笔记本”别名后匹配 MacBook | MATCH 且给原文证据 | verdict=MATCH，quote=MacBook Air M1 | 正确 |
| 错误 1 | T14-W1 | `test_concepts.py::test_non_object_payload_is_rejected_as_invalid_schema` | payload 非对象 | REJECTED/invalid_schema | Rejected(invalid_schema)；审计同因 | 正确（按预期拒绝） |
| 错误 2 | T14-W2 | `test_concepts.py::test_alias_outside_item_text_is_rejected` | thinkpad 不在原文 | ungrounded_alias | Rejected(ungrounded_alias)；审计同因 | 正确（按预期拒绝） |
| 错误 3 | T14-W3 | `test_concepts.py::test_fabricated_evidence_is_rejected_and_audited` | evidence 编造 | fabricated_evidence，不落库 | Rejected；概念数为 0 | 正确（按预期拒绝） |
| 错误 4 | T14-W4 | `test_concepts.py::test_alias_conflict_and_unknown_concept_are_rejected` | 别名冲突；concept_id 缺失 | alias_conflict / unknown_concept | 两次原因正确；概念数 2 | 正确（按预期拒绝） |
| 错误 5 | T14-W5 | `test_concepts.py::test_attribute_and_forbidden_alias_are_rejected` | 属性词“静音”当别名 | forbidden_alias | Rejected(forbidden_alias) | 正确（按预期拒绝） |

每模块统计（50 个样例全部通过）：

| 模块 | 正确样例通过 | 错误样例按预期处理 | 未通过 |
|---|---:|---:|---|
| 1.1 文案提取 | 5/5 | 5/5 | 无 |
| 1.2 视觉识图 | 5/5 | 5/5 | 无 |
| 2.1 意图解析 | 5/5 | 5/5 | 无 |
| 2.4 候选精筛 | 5/5 | 5/5 | 无 |
| 1.4 概念族学习 | 5/5 | 5/5 | 无 |
| 合计 | 25/25 | 25/25 | 0 |

全量测试（2026-11-23，冻结代码）：

```text
377 tests collected
377 passed, 0 failed, 0 skipped, 3 warnings in 161.48s
```

告警为 FastAPI/Starlette 的 `httpx` 弃用提示与 SQLite datetime 适配器弃用提示，不影响结果。

## 7. 不能声称的事项

- dev 每节点 n=6–12，只能写“在该集上占优/无差异证据”，不能声称统计显著或 Pareto 前沿。
- sealed 每节点只跑一次，是描述性 holdout，不与 dev 合并算均值，不据此改选型或提示词。
- 1.4 数据集为首次构建、样本小且金标为 AI 起草，指标只用于本轮选型参考，不能与 1.1/2.1 的历史 sealed 数字横向比较。
- 生产仍由一个文本模型服务 1.1/2.1/2.4/1.4；各节点胜者不同时只给建议，本轮不改部署。
- `price_per_1k_*` 未配置，不给出货币成本。

## 8. 复现

```bash
# 仓库根目录
./.venv/Scripts/python.exe -m pytest backend/tests -q

# backend 目录
../.venv/Scripts/python.exe -m eval.cli check-models
../.venv/Scripts/python.exe -m eval.cli dry-run --node all --split dev
../.venv/Scripts/python.exe -m eval.cli run --node 1.1,1.2,2.1,2.4,1.4 --split dev --real --out ../reports/eval/<dev 目录>
../.venv/Scripts/python.exe -m eval.cli run --node 1.1,2.1 --split sealed_test --candidate text-alt --real --out ../reports/eval/<sealed 目录>
../.venv/Scripts/python.exe -m eval.cli verify ../reports/eval/<sealed 目录>
../.venv/Scripts/python.exe -m eval.cli cases --report ../reports/eval/<sealed 目录> --node 1.1
```