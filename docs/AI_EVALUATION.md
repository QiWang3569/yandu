# AI 流水线评测报告

本报告回答课程第 8 次汇报第 1 项要求：对每个 AI 模块，综合考虑质量属性与约束，通过细化测试选择模型。所有末尾数字均来自真实模型调用，fixture 结果不作为结论。

## 1. 预注册规则

在跑基线之前固定以下规则，之后不改：

- 数据集：人工标注集 `2026-11-23-v2`（SHA-256 清单见 `backend/eval/datasets/manifest.json`），按 40% `dev` / 60% `sealed_test` 分层划分。
- 阈值：`backend/eval/thresholds.json`，硬约束在基线前冻结。
- 流程：先在 `dev` 上迭代提示词与护栏；代码冻结后，`sealed_test` 只跑基线与最终适配各一次。适配后不再根据 sealed 结果调参。
- 真实运行必须显式 `--real`；缺少凭据的候选记录为 `UNAVAILABLE`，不用均值掩盖。
- 只比较预注册指标；补充分析（如排除有缺陷样本的敏感性）单独标注，不能替换主结果。

## 2. 数据集与标注

| 节点 | 样本数 | dev / sealed | 分层 |
|---|---:|---|---|
| 1.1 文案提取 | 20 | 8 / 12 | normal、boundary、contradictory、injection、missing |
| 1.2 视觉识图 | 15 | 6 / 9 | 书籍、数码、运动、家居、多件、空白、遮挡 |
| 2.1 意图解析 | 30 | 12 / 18 | normal、boundary、contradictory、injection、missing |
| 2.3 词面检索 | 30 查询 + 60 商品池 | 12 / 18 | normal、boundary、contradictory、injection |
| 2.4 候选精筛 | 30 对（15 需求 × 候选） | 12 / 18 | hard_match、exclusion、preference、insufficient |

- 标注方式：主标注者 A 全量标注；20% 由第二人独立复核；2.1 的角色/引文与 2.4 的判定全量双标，分歧由仲裁者 B 裁定（见每行的 `annotator`/`adjudicator` 字段）。
- 2.3 复用 2.1 的 30 条查询与 60 条公开测试商品池，按相关/近似/排除分层。
- 1.2 图片为 ImageGen 生成的私有素材，去除 EXIF、缩小尺寸，不含真实用户上传、手机号或邮箱；许可标注为 `ai-generated, no real user data`。
- 冻结：`manifest.json` 记录每个文件与图片的 SHA-256、样本数、标注版本与冻结时间 `2026-11-23T02:40:00Z`。sealed 集在基线后未改动；`verify` 每次运行前校验，`mismatches` 为空。

## 3. 候选模型与配置

候选由 `backend/eval/models.json` 通过环境变量解析；仓库不保存密钥，凭据从本地未提交的 `backend/.env` 注入。实际探测结果（`eval.cli check-models`）：

| 用途 | 候选 | 状态 | 模型 |
|---|---|---|---|
| text | text-primary | OK | `deepseek/deepseek-v4.1-flash` |
| text | text-alt | UNAVAILABLE | 缺 `EVAL_TEXT_MODEL_B / _BASE_URL_B / _API_KEY_B` |
| vision | vision-primary | OK | `qwen/qwen3.7-flash` |
| vision | vision-alt | UNAVAILABLE | 缺 `EVAL_VISION_MODEL_B / _BASE_URL_B / _API_KEY_B` |
| embedding | embedding-primary/alt | UNAVAILABLE | 缺 `EMBEDDING_*` |

模型选择的证据边界（必须如实说明）：

- 每个用途只有一个通过探测的真实候选。报告**不宣称**在主候选与备用候选之间做过 Pareto 比较，因为备用候选在此环境没有凭据、无法产生真实结果。
- 可比较的是同一主候选在“基线提示词”与“适配后提示词”下的真实指标，以及该候选是否满足硬约束。选择理由见第 8 节。
- `price_per_1k_input/output` 未配置，因此不能在本报告中给出货币成本；只记录调用数、token 数与延迟。成本字段保留为后续接入真实价格的位置，不以估算值代替。

## 4. 质量属性与硬约束

| 节点 | 硬约束（基线前冻结） | 软指标 |
|---|---|---|
| 全部 | JSON/Schema 合法率 ≥ 0.98；不泄露密钥；不静默降级 | — |
| 1.1 | 字段 macro-F1 ≥ 0.85；p95 ≤ 20 s | clarification 判定准确率 ≥ 0.80 |
| 1.2 | 状态准确率、分类准确率 ≥ 0.80；无依据属性率 ≤ 5%；p95 ≤ 30 s | — |
| 2.1 | 字段 macro-F1 ≥ 0.85；预算/校区/成色精确匹配 ≥ 0.90；逐字引文命中率 ≥ 0.95；注入结构保持率 100%；p95 ≤ 20 s | — |
| 2.3 | Recall@10 ≥ 0.80 | p95 ≤ 5 s |
| 2.4 | MATCH 召回 ≥ 0.85；引文接地率 100%；排除项错误接受 0；偏好单独拒绝 0；p95 ≤ 20 s | 判定准确率 ≥ 0.80 |

## 5. 基线（sealed_test，未适配）

报告目录：`reports/eval/2026-11-23-baseline/`；git SHA `54df454`；提示词版本 `item-2 / vision-publish-2 / intent-2 / lexical-alias-1 / review-1`。

| 节点 | 指标 | 值 | 门槛 | 结论 |
|---|---|---:|---|---|
| 1.1 | valid_rate | 1.000 | ≥0.98 | 通过 |
| 1.1 | field_macro_f1 | 0.865 | ≥0.85 | 通过 |
| 2.1 | valid_rate | 0.944 | ≥0.98 | **未通过** |
| 2.1 | field_macro_f1 | 0.821 | ≥0.85 | **未通过** |
| 2.1 | hard_field_exact | 0.931 | ≥0.90 | 通过 |
| 2.1 | quote_recall | 0.000 | ≥0.95 | **未通过** |
| 2.1 | injection_structure_rate | 1.000 | =1.0 | 通过 |
| 2.4 | verdict_accuracy | 0.556 | ≥0.80（软） | 未通过 |
| 2.4 | match_recall | 0.615 | ≥0.85 | **未通过** |
| 2.4 | grounding_rate | 1.000 | =1.0 | 通过 |
| 1.2 | status_accuracy | 0.667 | ≥0.80 | **未通过** |
| 1.2 | category_accuracy | 0.667 | ≥0.80 | **未通过** |
| 1.2 | unsupported_attribute_rate | 0.222 | ≤0.05 | **未通过** |
| 2.3 | recall_at_10 | 0.960 | ≥0.80 | 通过 |

失败样例：`2.1-014` 返回 HTTPException —— 模型对“九成新以上”一类比较级成色输出无法通过枚举校验。

## 6. 触发的适配

按“只改被基线触发的部分”执行，`dev` 集用于迭代：

### P1 结构化意图（触发 2.1）

- 提示词 `intent-2` → `intent-3`：输出内部 `StructuredIntent`（role/term/逐字 quote、预算/校区/成色引文、clarification 与 `clarification_quotes`），再由 `flatten_intent` 转为公开 `ParsedIntent`。
- 成色比较级（“九成新以上”“八成新以上”“全新或九五新都行”）归一化到最宽松枚举；非法枚举、负价格、重复词被清洗；非逐字引文丢弃。
- 公开 API、数据库列、前端类型与匹配逻辑不变；评测 adapter 调用同一生产函数，不复制提示词。

### 2.4 证据护栏修正（触发 match_recall）

- MATCH 不再要求排除项出现在商品文本中：排除项只需**不存在**；若出现在 MATCH 文本中则显式拒绝。
- 关键词证据缺失时降级 UNCERTAIN 并只针对缺失关键词生成确认问题。
- 提示词版本仍为 `review-1`；修改的是确定性护栏代码。

### 1.2 视觉提示词（触发状态/分类/无依据属性）

- `vision-publish-2` → `vision-publish-3`：可识别但无文字的物品按 ready 出稿，型号/书名放入 uncertainties；背景细小物品不算多件；不得根据外观推断金属/塑料/皮革或全新。
- 缓存键仍包含提示词版本，旧缓存不串用。

### 未触发的项（保持原实现）

- P2 偏好次级排序：基线中偏好未导致 top-k 差异，且现有排序未违反语义，不改。
- P3 词面召回别名扩充：基线 Recall@10 = 0.960，已达门槛，不改。
- 1.3、2.2、2.3 为程序节点，基线通过，只记录测试证据，不做无依据重构。

### dev 集适配前后

| 节点 | 指标 | 基线 dev | 适配 dev | 门槛 |
|---|---|---:|---:|---|
| 1.1 | field_macro_f1 | 0.867 | 0.879 | ≥0.85 |
| 2.1 | valid_rate | 0.833 | 1.000 | ≥0.98 |
| 2.1 | field_macro_f1 | 0.846 | 0.874 | ≥0.85 |
| 2.1 | hard_field_exact | 0.812 | 0.979 | ≥0.90 |
| 2.1 | quote_recall | 0.000 | 1.000 | ≥0.95 |
| 2.4 | verdict_accuracy | 0.583 | 0.833 | ≥0.80 |
| 2.4 | match_recall | 0.500 | 1.000 | ≥0.85 |
| 1.2 | status_accuracy | 0.833 | 1.000 | ≥0.80 |
| 1.2 | category_accuracy | 0.667 | 1.000 | ≥0.80 |
| 1.2 | unsupported_attribute_rate | 0.000 | 0.000 | ≤0.05 |
| 2.3 | recall_at_10 | 0.944 | 0.944 | ≥0.80 |

报告目录：`reports/eval/2026-11-23-baseline-dev/`、`reports/eval/2026-11-23-adapted-dev/`。

## 7. 适配后 sealed_test 结果（只跑一次）

报告目录：`reports/eval/2026-11-23-adapted/`；`verify` 通过（`report_ok=true`，数据集合规）；提示词版本 `item-2 / vision-publish-3 / intent-3 / lexical-alias-1 / review-1`。

| 节点 | 指标 | 基线 sealed | 适配 sealed | 门槛 | 适配后结论 |
|---|---|---:|---:|---|---|
| 1.1 | valid_rate | 1.000 | 1.000 | ≥0.98 | 通过 |
| 1.1 | field_macro_f1 | 0.865 | 0.842 | ≥0.85 | **未通过** |
| 1.1 | clarification_accuracy | 0.917 | 1.000 | ≥0.80（软） | 通过 |
| 2.1 | valid_rate | 0.944 | 1.000 | ≥0.98 | 通过 |
| 2.1 | field_macro_f1 | 0.821 | 0.864 | ≥0.85 | 通过 |
| 2.1 | hard_field_exact | 0.931 | 0.972 | ≥0.90 | 通过 |
| 2.1 | quote_recall | 0.000 | 0.986 | ≥0.95 | 通过 |
| 2.1 | injection_structure_rate | 1.000 | 1.000 | =1.0 | 通过 |
| 2.4 | verdict_accuracy | 0.556 | 0.667 | ≥0.80（软） | 未通过 |
| 2.4 | match_recall | 0.615 | 0.769 | ≥0.85 | **未通过** |
| 2.4 | grounding_rate | 1.000 | 1.000 | =1.0 | 通过 |
| 2.4 | exclusion_false_accept | 0 | 0 | =0 | 通过 |
| 2.4 | preference_only_reject | 0 | 0 | =0 | 通过 |
| 1.2 | status_accuracy | 0.667 | 0.889 | ≥0.80 | 通过 |
| 1.2 | category_accuracy | 0.667 | 0.889 | ≥0.80 | 通过 |
| 1.2 | unsupported_attribute_rate | 0.222 | 0.222 | ≤0.05 | **未通过** |
| 2.3 | recall_at_10 | 0.960 | 0.960 | ≥0.80 | 通过 |

调用与延迟（sealed）：

| 节点 | 样本 | 调用 | 输入 token | 输出 token | 失败 | p95 延迟 |
|---|---:|---:|---:|---:|---:|---:|
| 1.1 | 12 | 12 | 6692 | 1132 | 0 | 5 592 ms |
| 2.1 | 18 | 18 | 20405 | 2360 | 0 | 5 379 ms |
| 2.4 | 18 | 18 | 8122 | 969 | 0 | 5 799 ms |
| 1.2 | 9 | 9 | 13032 | 1201 | 0 | 8 009 ms |
| 2.3 | 18 | 0 | 0 | 0 | 0 | 16 ms |

延迟为单次运行观测值，受网络与代理波动影响；12–18 个样本的 p95 只能作为量级参考，不构成 SLA。

## 8. 失败样例分析

### 1.1：0.842 未达 0.85（代码与提示词未改）

- 同一 `item-2` 提示词、同一模型，基线 sealed 0.865、适配 sealed 0.842；差异完全来自 tag 集合 F1（0.492 → 0.375），其余字段两轮相同：分类/校区 1.0，价格/成色 0.917。
- 金标 tag 是“规范集合”，模型有时输出品牌、颜色、成色等合理但未被金标列出的词（如 `Dell`、`24英寸`、`降噪`），按集合 F1 被记为错误。价格唯一错误样本 `1.1-016` 是“预算矛盾”句，金标要求价格留空，模型取了 450；成色错误样本 `1.1-020` 在用户未提成色时填了 95新。
- 结论：这是小样本下的措辞波动与金标粒度问题，不是回归。按预注册规则，1.1 仍记为未达硬门槛；没有为了过线在 sealed 之后改金标或阈值。

### 2.4：判定准确率 0.667、MATCH 召回 0.769

18 对中 6 对与金标不一致，集中在两种判定口径：

1. 金标 MATCH、模型 UNCERTAIN（3 对）：`2.4-010` 高等数学教材（版本未标明）、`2.4-024` 耳机（型号不明）、`2.4-029` 显示器（屏幕有坏点）。金标认为关键词齐备即 MATCH；模型要求版本/型号/瑕疵信息，选择了向卖家提问。
2. 金标 UNCERTAIN、模型 NO_MATCH（3 对）：`2.4-015` 自行车需求 vs 滑板车、`2.4-025` 耳机需求 vs 蓝牙音箱、`2.4-030` 显示器需求 vs 电视。模型按“具体品类必须一致”判否；金标把相邻品类视为“待确认”。

这两种分歧说明护栏“不能过度自信”和“不能过度保守”之间存在标注口径差异。当前实现更严格：宁可 UNCERTAIN 或按品类判否，也不在信息不足时判 MATCH。该行为符合生产安全方向，但按预注册口径仍未达标，保留如实记录。

### 1.2：状态/分类 0.889 通过；无依据属性 0.222 未通过

- 状态唯一错误 `1.2-007`：图片实际是**无字样的牛皮纸笔记本 + 一支铅笔**，金标却要求出稿为可发布书籍（`title_keywords: ["Linear Algebra"]`）。模型判 `multiple_items` 是合理行为。该行在数据集冻结后被确认为受控缺陷（生成图与金标不一致），sealed 集不允许事后修改。
- 敏感性（补充分析，非预注册指标）：若排除该缺陷行，状态与分类准确率为 8/8 = 1.000。
- 无依据属性仍为 2/9（`1.2-004`、`1.2-012`）：模型在描述中写了“黄色金属台灯”“银色金属多节支架”。提示词已禁止根据外观推断金属/塑料/皮革，但视觉模型仍推断材质。这是真实的提示词遵从缺口，未在 sealed 后修正。
- `1.2-014`（显示器 + 鼠标 + 键盘场景）在适配后正确判为 ready，说明“背景细小物品不算多件”的修正生效。

### 2.1：基线 502 已修复，引文达标

- `2.1-014` 基线因比较级成色触发 HTTPException；适配后 18 条全部合法，无失败样本。
- 引文召回 0.986：18 条中仅 1 条缺少一个金标引文片段，其余字段与硬条件均满足。

## 9. 模型选择结论（按预注册顺序）

1. **硬约束过滤**：只有 `text-primary` 与 `vision-primary` 通过 `check-models`；备用与 embedding 候选因凭据缺失为 `UNAVAILABLE`，不能进入比较。没有可用候选的节点（Embedding）不以本地近似值冒充远程结果，2.3 以词面召回运行并如实标注。
2. **准确率/召回**：主候选在 2.1、2.3、1.2（状态/分类）上满足硬门槛；2.4 的 MATCH 召回、1.1 的字段 F1、1.2 的无依据属性仍未达标，按规则保留为未通过。
3. **延迟/成本**：所有节点 p95 远低于各自超时上限；货币成本因未配置价格无法计算，token 与调用数已记录。延迟差异在同类节点间不构成硬约束冲突。
4. **Pareto 选择**：本环境不存在两个都能产生真实结果的同类候选，因此**无法**给出跨模型的 Pareto 前沿。可以确认的是：主候选在适配后满足除已列缺口外的全部硬约束，且没有因适配引入新的失败样本。若后续配置第二候选，可用同一 `models.json` 与 `--candidate` 在 dev 集重复本流程。

## 10. 复现

```bash
# 仓库根目录：单元测试
./.venv/Scripts/python.exe -m pytest backend/tests -q

# backend 目录：探测、干跑、真实运行、校验
../.venv/Scripts/python.exe -m eval.cli check-models --config eval/models.json
../.venv/Scripts/python.exe -m eval.cli dry-run --node all --split sealed_test
../.venv/Scripts/python.exe -m eval.cli run --node all --split sealed_test --out ../reports/eval/2026-11-23-adapted --real
../.venv/Scripts/python.exe -m eval.cli verify ../reports/eval/2026-11-23-adapted
```

可追溯信息：

- 数据集：`2026-11-23-v2`，冻结于 `2026-11-23T02:40:00Z`，SHA 清单在 `backend/eval/datasets/manifest.json`。
- 基线 sealed：git SHA `54df454`，提示词 `item-2 / vision-publish-2 / intent-2 / lexical-alias-1 / review-1`。
- 适配 sealed：在 `54df454` 之上带未提交改动执行，随后以同一内容提交为 `fad5799`（`codex/ai-pipeline-evaluation` 分支）；提示词 `item-2 / vision-publish-3 / intent-3 / lexical-alias-1 / review-1`。
- 本次运行早于 `git_dirty` 字段的加入，因此其 manifest 只有 `git_sha`；`git_dirty` 已加入 harness，后续运行会显式记录工作区是否干净。

## 11. 不能声称的事项

- 30 条以内的标注集结果不等于线上准确率或 P95 SLA；失败率的分母很小，单条样本可改变 5–10 个百分点。
- 没有跨模型 Pareto 比较：备用候选与 Embedding 候选在本环境不可用，不能声称“选出了全局最优模型”。
- 2.4 的 MATCH 召回、1.1 的字段 F1、1.2 的无依据属性仍未达门槛，不能声称“全部 AI 节点已达标”。
- 未实现动态同义词库、即时向量检索、自动发布、在线学习或反思式自我修正；报告不为这些能力背书。
- 1.2-007 的受控数据缺陷只做敏感性说明，不修改 sealed 数据，也不据此重跑最终结果。