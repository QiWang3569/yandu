# AI 流水线评测报告

本报告回答课程第 8 次汇报第 1 项要求：对每个 AI 模块，综合考虑质量属性与约束，通过细化测试选择模型。所有末尾数字均来自真实模型调用，fixture 结果不作为结论。

## 1. 预注册规则

在跑基线之前固定以下规则，之后不改：

- 数据集：人工标注集 `2026-11-23-v3`（前 6 个文件沿用 v2 的 SHA；新增 `concepts_1_4.jsonl`，SHA-256 清单见 `backend/eval/datasets/manifest.json`），按 40% `dev` / 60% `sealed_test` 分层划分。
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
| 2.4 候选精筛 | 30 对（6 需求 × 5 候选） | 12 / 18 | hard_match、exclusion、preference、insufficient |
| 1.4 概念族学习 | 16 | 6 / 10 | normal、boundary、no_family、alias_conflict、forbidden_alias、invalid_name |

- 标注方式（1.1/1.2/2.1/2.3/2.4）：主标注者 A 全量标注；20% 由第二人独立复核；2.1 的角色/引文与 2.4 的判定为部分双标（以每行 `adjudicator` 非空为准，2.1 为 16/30、2.4 为 12/30），分歧由仲裁者 B 裁定。1.4 是 AI 起草、未经人工确认，见下一条。
- 2.3 复用 2.1 的 30 条查询与 60 条公开测试商品池，按相关/近似/排除分层。
- 1.2 图片为 ImageGen 生成的私有素材，去除 EXIF、缩小尺寸，不含真实用户上传、手机号或邮箱；许可标注为 `ai-generated, no real user data`。
- 冻结：`manifest.json` 记录每个文件与图片的 SHA-256、样本数、标注版本与冻结时间 `2026-11-23T02:40:00Z`。sealed 集在基线后未改动；`verify` 每次运行前校验，`mismatches` 为空。
- 1.4 数据集为本轮新建（`concepts_1_4.jsonl`，16 行），随 `2026-11-23-v3` 冻结。每行 `annotator` 均如实写为 `AI-drafted, pending review`，manifest 的 `files["concepts_1_4.jsonl"].annotators` 也记录为同一值，未声称人工标注。1.4 的真实指标为**临时结果**，待逐行人工确认金标；若确认时有修改，将以 v4 重新冻结并只重跑 1.4。原有 6 个文件的 SHA-256 保持不变。

## 3. 候选模型与配置

候选由 `backend/eval/models.json` 解析：模型 ID 直接写在配置里（`model`），也可用同名环境变量覆盖；仓库不保存密钥，凭据从本地未提交的仓库根 `.env` 注入。所有候选共用同一网关与同一把 key（文本用 `DEEPSEEK_BASE_URL/DEEPSEEK_API_KEY`，视觉用 `VISION_BASE_URL/VISION_API_KEY`），本轮无需新增任何 `EVAL_*` 变量。

候选配置（模型 ID 已写死，可用性以本轮 `eval.cli check-models` 的真实探测为准）：

| 用途 | 候选 | 配置来源 | 模型 | 探测状态 |
|---|---|---|---|---|
| text | text-primary | `.env` 的 `DEEPSEEK_MODEL` | `deepseek/deepseek-v4.1-flash` | OK |
| text | text-alt | `models.json` 字面量 | `deepseek/deepseek-v4-pro-0813` | OK |
| text | text-alt-2 | `models.json` 字面量 | `z-ai/glm-5.3-flash` | OK |
| vision | vision-primary | `.env` 的 `VISION_MODEL` | `qwen/qwen3.7-flash` | OK |
| vision | vision-alt | `models.json` 字面量 | `deepseek/deepseek-v4-flash-vision-exp` | OK |
| embedding | embedding-primary/alt | `EMBEDDING_*` | 未配置，本轮不参与选型 | UNAVAILABLE |

- 探测细节：`check-models` 用生产同款 `chat_json` 探测；`z-ai/glm-5.3-flash` 是思考模型，32 token 的探测预算会被推理占满而误判，因此文本探测预算设为 256 token，与真实调用量级一致。
- 模型 ID 以轮询网关 `/v1/models` 返回的列表为准，而非猜测；`glm-5.3-flash` 在网关上的真实 ID 是 `z-ai/glm-5.3-flash`。

模型选择的证据边界（必须如实说明）：

- 本轮 5 个文本/视觉候选全部通过 `check-models`，并在 dev 上真实跑通；Embedding 候选因缺 `EMBEDDING_*` 标记为 `UNAVAILABLE`，不进入比较。
- 只有同一节点上至少两个候选都真实跑通时，才写“在该 dev 集上占优/无差异证据”；n=6–12，不宣称 Pareto 前沿或统计显著。
- 1.2 的视觉备用候选没有只凭合成灯图判定：`vision-alt` 已用 `--node 1.2 --split dev --real` 实跑通过，才记为可用。
- `price_per_1k_input/output` 未配置，因此不能在本报告中给出货币成本；只记录调用数、token 数与延迟。成本字段保留为后续接入真实价格的位置，不以估算值代替。

### 3.1 选型规则（预注册，先于本轮真实调用）

以下规则在本轮任何新增真实调用之前固定，之后不改：

- 候选池：`text-primary`（现用 flash）、`text-alt`（强质量档）、`text-alt-2`（第三方 flash 档）；视觉为 `vision-primary`（现用）、`vision-alt`（备用视觉模型）。模型 ID 写在 `backend/eval/models.json`，与主候选共用现有 key；如需临时替换，可用 `EVAL_TEXT_MODEL_B/C`、`EVAL_VISION_MODEL_B` 覆盖。
- 划分：只用 `dev` 集做候选比较；`sealed_test` 只给最终选中的候选跑一次，之后不再据此调参。1.4 使用本轮新建的 `concepts_1_4` 数据集，规则相同。
- 决策顺序：① 可用性硬过滤（凭据齐全、视觉实跑能接受图片、返回 JSON）；② 该节点预注册硬门禁全部通过；③ 主质量指标更高者胜；④ 平局依次比较 p95 延迟、输出 token 数；⑤ 无候选通过则保留现模型并如实报告失败。
- 主质量指标：1.1 `field_macro_f1`；1.2 `status_accuracy`（且 `unsupported_attribute_rate=0`）；2.1 `field_macro_f1` 与 `quote_recall`；2.4 `match_recall` 与 `verdict_accuracy`；1.4 `accept_accuracy` 与 `family_f1`。
- 记录：每个候选的逐节点指标、失败样本、尝试次数、token、p95 全部入报告；`dev` 每节点 n=6–12，不写统计显著或 Pareto 前沿，只写“占优/无差异证据”。
- 部署边界：生产端当前只有一个文本模型服务 1.1/2.1/2.4/1.4；若各模块胜者不同，报告按模块给建议并注明“按节点拆分配置需另行改造”，本轮不改生产配置。

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

报告目录：`reports/eval/2026-11-23-baseline/`（中间报告未入库；数字保留用于对照，可在 git 历史 `54df454` 上重新生成）；git SHA `54df454`；提示词版本 `item-2 / vision-publish-2 / intent-2 / lexical-alias-1 / review-1`。

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
- P3 词面召回别名扩充：冻结集基线 Recall@10 = 0.960，未触发。后续按人类提出的“概念知识库”设计单独实现，并用独立 dev 切片验证（见 §11），不把该切片混入 sealed 结果。
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

报告目录：`reports/eval/2026-11-23-baseline-dev/`、`reports/eval/2026-11-23-adapted-dev/`（中间报告未入库）。

## 7. 适配后 sealed_test 结果（只跑一次）

报告目录：`reports/eval/2026-11-23-adapted/`（中间报告未入库）；`verify` 通过（`report_ok=true`，数据集合规）；提示词版本 `item-2 / vision-publish-3 / intent-3 / lexical-alias-1 / review-1`。

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

说明：2.3 的 sealed 数值产生于概念知识库上线之前。按“sealed 集只跑一次”的预注册规则，概念库上线后没有重跑 sealed；因此 0.960 不能当作概念库之后的 sealed 检索指标。概念学习本身的质量改由 §11 的 1.4 数据集单独评测。

调用与延迟（sealed）：

| 节点 | 样本 | 调用 | 输入 token | 输出 token | 失败 | p95 延迟 |
|---|---:|---:|---:|---:|---:|---:|
| 1.1 | 12 | 12 | 6692 | 1132 | 0 | 5 592 ms |
| 2.1 | 18 | 18 | 20405 | 2360 | 0 | 5 379 ms |
| 2.4 | 18 | 18 | 8122 | 969 | 0 | 5 799 ms |
| 1.2 | 9 | 9 | 13032 | 1201 | 0 | 8 009 ms |
| 2.3 | 18 | 0 | 0 | 0 | 0 | 16 ms |

延迟为单次运行观测值，受网络与代理波动影响；12–18 个样本的 p95 只能作为量级参考，不构成 SLA。

### 7.1 本轮选型后的 sealed 复核（按节点胜者，各跑一次）

预注册规则见 §3.1：`dev` 选型，`sealed_test` 只给每个节点的胜者跑一次。胜者不同，因此拆成三个报告目录（同一份 v3 数据、同一提交）：

| 报告目录 | 节点 | 胜出候选 |
|---|---|---|
| `reports/eval/2026-11-23-selected-sealed-text-alt/` | 1.1、2.1 | text-alt `deepseek/deepseek-v4-pro-0813` |
| `reports/eval/2026-11-23-selected-sealed-text-primary/` | 2.4、1.4 | text-primary `deepseek/deepseek-v4.1-flash` |
| `reports/eval/2026-11-23-selected-sealed-vision-primary/` | 1.2 | vision-primary `qwen/qwen3.7-flash` |

运行信息：git SHA `d5b5bb6`（工作区有未提交改动，`git_dirty=true`，如实记录）；提示词版本 `item-2 / vision-publish-3 / intent-3 / review-1 / concept-1`；三份报告 `verify` 均为 `report_ok=true`、`dataset_verified=true`、`fixture=false`、`mismatches=[]`。

| 节点 | 指标 | 胜者 sealed | 门槛 | 结论 |
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

sealed 结果与 dev 选型的关系（必须如实说明）：

- sealed 只用于描述性 holdout，**不**据此改选型、改提示词或改金标。text-alt 在 dev 上以 `field_macro_f1` 胜出（1.1、2.1），但 2.1 的 sealed 暴露出 1 次供应商失败与引文召回 0.931，低于预注册门槛；这是选型风险，已记录，不通过回头重选掩盖。
- vision-primary 在 dev 上 `unsupported_attribute_rate=0`，sealed 上为 0.333（`1.2-004`、`1.2-012` 描述里写了“金属”）与 `1.2-007` 分类错误；该指标未达标。
- 2.4 的 `verdict_accuracy` 为软指标，sealed 0.778 略低于 0.80；MATCH 召回 0.923 达硬门槛。
- 1.4 的 `alias_f1` 未达标是三个候选在 dev 上的共同问题（0.389/0.556/0.433），sealed 0.367；该门槛由预注册固定，不因结果不理想而删除。

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

### 8.1 dev 候选对比（选型依据）

报告目录：`reports/eval/2026-11-23-model-selection-dev/`；同一 v3 数据、git SHA `d5b5bb6`（dirty）、提示词同 §7.1；5 个候选全部由 `check-models` 判定可用。下表是预注册指标在 `dev` 上的全部结果；“门禁”指该节点预注册硬约束是否全部通过。

**1.1 文案提取（n=8）**

| 候选 | field_macro_f1 | valid_rate | clarification | p95 | tokens in/out | 硬门禁 | 结论 |
|---|---:|---:|---:|---:|---|---|---|
| text-primary | 0.867 | 1.000 | 1.000 | 1 570 ms | 4 668 / 863 | 通过 | 质量次优 |
| text-alt | 0.873 | 1.000 | 1.000 | 3 542 ms | 5 420 / 884 | 通过 | **胜出**（主指标最高） |
| text-alt-2 | 0.848 | 1.000 | 0.875 | 31 140 ms | 4 379 / 4 299 | **未通过**（F1<0.85，p95>20 s） | 淘汰 |

**1.2 视觉识图（n=6）**

| 候选 | status_accuracy | category_accuracy | unsupported_rate | p95 | tokens in/out | 硬门禁 | 结论 |
|---|---:|---:|---:|---:|---|---|---|
| vision-primary | 1.000 | 1.000 | 0.000 | 3 941 ms | 8 688 / 656 | 通过 | **胜出**（status 最高） |
| vision-alt | 0.833 | 1.000 | 0.000 | 2 375 ms | 7 566 / 472 | 通过 | 质量次优，延迟更低 |

**2.1 意图解析（n=12）**

| 候选 | field_macro_f1 | quote_recall | hard_field_exact | injection | p95 | tokens in/out | 硬门禁 | 结论 |
|---|---:|---:|---:|---:|---:|---|---|---|
| text-primary | 0.860 | 1.000 | 1.000 | 1.000 | 6 189 ms | 13 628 / 1 166 | 通过 | 质量次优 |
| text-alt | 0.880 | 1.000 | 1.000 | 1.000 | 3 919 ms | 14 756 / 1 548 | 通过 | **胜出**（F1 最高且延迟更低） |
| text-alt-2 | 0.870 | 0.972 | 0.979 | 1.000 | 54 672 ms | 12 825 / 10 325 | **未通过**（p95>20 s） | 淘汰 |

**2.4 候选精筛（n=12）**

| 候选 | match_recall | verdict_accuracy | grounding | 排除误收 | 偏好单独拒绝 | p95 | tokens in/out | 硬门禁 | 结论 |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| text-primary | 1.000 | 0.833 | 1.000 | 0 | 0 | 1 653 ms | 5 736 / 584 | 通过 | **胜出**（唯一全过） |
| text-alt | 0.667 | 0.667 | 1.000 | 0 | 1 | 10 179 ms | 7 901 / 872 | **未通过**（valid 0.917、偏好单独拒绝 1） | 淘汰 |
| text-alt-2 | 1.000 | 0.833 | 1.000 | 0 | 0 | 43 796 ms | 5 457 / 5 432 | **未通过**（p95>20 s） | 淘汰 |

**1.4 概念族学习（n=6，金标为 AI 起草待复核）**

| 候选 | accept_accuracy | family_f1 | alias_f1 | grounded_rate | schema_valid | p95 | tokens in/out | 硬门禁 | 结论 |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| text-primary | 1.000 | 1.000 | 0.389 | 1.000 | 1.000 | 5 250 ms | 2 961 / 392 | **未通过**（alias_f1<0.70） | 保留现模型 |
| text-alt | 0.833 | 0.800 | 0.556 | 1.000 | 1.000 | 3 410 ms | 3 525 / 265 | **未通过**（alias_f1<0.70） | 淘汰 |
| text-alt-2 | 0.833 | 0.800 | 0.433 | 0.833 | 0.833 | 88 399 ms | 3 703 / 5 416 | **未通过**（valid/schema/grounded/p95） | 淘汰 |

候选对比的边界：

- 每节点 n=6–12，上表只写“在该 dev 集上占优/无差异证据”，不写统计显著，也不构造 Pareto 前沿（维度与样本都不足）。
- text-alt 在 1.1 的领先幅度只有 0.006 F1，属于小样本下的量级差异；规则只看主指标高低，因此记为胜出，但不应解读为稳定优势。
- 2.4 的 text-alt 失败包含 1 次供应商失败（`valid_rate=0.917`）与 1 次“偏好单独拒绝”，不是单纯的判定风格差异。
- 1.4 三个候选都没过 `alias_f1` 门槛。按规则⑤保留现模型 `text-primary` 并如实报告失败；不因为“想选出一个胜者”而删除该门槛。

## 9. 模型选择结论（按预注册顺序）

1. **可用性硬过滤**：本轮 5 个文本/视觉候选（text-primary、text-alt、text-alt-2、vision-primary、vision-alt）全部通过 `check-models` 与真实 dev 运行；Embedding 候选因 `EMBEDDING_*` 未配置为 `UNAVAILABLE`，不参与比较，2.3 仍以词面召回运行并如实标注。
2. **逐节点硬门禁**：1.1、1.2、2.1 的候选在 dev 上均须全过；2.4 只有 text-primary 全过；1.4 三个候选都被 `alias_f1` 挡住。
3. **主指标排序与胜者**：

| 节点 | 胜者 | 依据 | 部署建议 |
|---|---|---|---|
| 1.1 | text-alt `deepseek/deepseek-v4-pro-0813` | dev `field_macro_f1` 0.873 > 0.867 | 若采用需按节点拆分配置；差距小，保留现模型也可接受 |
| 1.2 | vision-primary `qwen/qwen3.7-flash` | dev `status_accuracy` 1.000 > 0.833 | 保持现配置 |
| 2.1 | text-alt `deepseek/deepseek-v4-pro-0813` | dev F1 0.880 > 0.860，p95 也更低 | 若采用需按节点拆分配置 |
| 2.4 | text-primary `deepseek/deepseek-v4.1-flash` | 唯一全过全部硬门禁 | 保持现配置 |
| 1.4 | 无（保留 text-primary） | 全部候选 `alias_f1` < 0.70 | 保持现配置，别名提取列为待改进 |

4. **部署边界**：生产端当前只有一个文本模型服务 1.1/2.1/2.4/1.4。若 1.1/2.1 采用 text-alt，需要把文本模型配置按节点拆分（`DEEPSEEK_MODEL` 之外增加节点级覆盖），属于部署改造；本轮**不改**生产配置，只给建议。
5. **sealed 描述性复核**：1.1 text-alt 全部硬门禁通过；2.1 的引文召回 0.931 与 1 次供应商失败、2.4 的判定准确率 0.778、1.2 的无依据属性 0.333、1.4 的 alias_f1 0.367 未过线，均如实保留。按预注册规则，sealed 只用于描述，不回头改选型与提示词。
6. **成本**：`price_per_1k_*` 未配置，不给货币成本；调用数、token、p95 见 §7.1 与 §8.1。小样本下不宣称统计显著或 Pareto 前沿。

### 9.1 具体测试例子（每模块 1 条正确 + 1 条错误，完整样例）

逐例判定由 `eval.cli cases` 生成，规则比字段级指标更严格：1.1 要求 category/price/campus/condition 四项全等；1.2 要求 status、category 全等且描述不含禁用词；2.1 要求四个硬字段全等**且**该行 `gold_quotes` 全部命中；2.4 要求 verdict 全等、引文接地率 1、无排除误收；1.4 要求决策/原因类别一致、金标家族名 ⊆ 预测家族名、别名逐字接地。

| 模块 | sealed 样本 | 正确 | 错误 | 裁决级准确率 |
|---|---:|---:|---:|---:|
| 1.1 文案提取 | 12 | 11 | 1 | 0.917 |
| 1.2 视觉识图 | 9 | 6 | 3 | 0.667 |
| 2.1 意图解析 | 18 | 14 | 4 | 0.778 |
| 2.4 候选精筛 | 18 | 14 | 4 | 0.778 |
| 1.4 概念族学习 | 10 | 6 | 4 | 0.600 |

裁决级准确率低于对应字段指标是正常的：它要求一条样本的所有硬字段同时正确；字段 macro-F1 允许逐字段部分得分。

#### 1.1 文案提取（text-alt，sealed）

sealed 全量：正确 11 条 `1.1-005, 1.1-006, 1.1-007, 1.1-008, 1.1-009, 1.1-010, 1.1-013, 1.1-014, 1.1-016, 1.1-018, 1.1-019`；错误 1 条 `1.1-020`。

正确样例 `1.1-005`：

```json
输入: {"raw": "Dell 24 英寸显示器，1080P，320元，燕园校本部，九成新，无坏点，附 HDMI 线。"}
金标: {"category": "数码与影音", "price": 320, "campus": "燕园校本部", "condition_grade": "9成新", "tags": ["显示器"], "clarification_required": false}
实际: {"title": "Dell 24英寸显示器", "category": "数码与影音", "price": 320.0, "campus": "燕园校本部", "condition_grade": "9成新", "tags": ["Dell", "24英寸", "1080P", "显示器", "无坏点", "HDMI线"], "clarification": null}
判定: 正确（category/price/campus/condition 四项全等；tags 多出品牌与规格词，按集合 F1 单列，不参与本条裁决）
```

错误样例 `1.1-020`：

```json
输入: {"raw": "东西很新，价格好商量，燕园校本部自取。"}
金标: {"category": null, "price": null, "campus": "燕园校本部", "condition_grade": null, "tags": [], "clarification_required": true}
实际: {"title": null, "category": null, "price": null, "campus": "燕园校本部", "condition_grade": "95新", "tags": [], "clarification": "未说明具体商品信息，无法确定分类、标题和成色。"}
判定: 错误（差异字段 condition_grade：金标留空，模型在信息不足时臆造“95新”）
```

#### 1.2 视觉识图（vision-primary，sealed）

sealed 全量：正确 6 条 `1.2-005, 1.2-006, 1.2-008, 1.2-013, 1.2-014, 1.2-015`；错误 3 条 `1.2-004, 1.2-007, 1.2-012`。

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

#### 2.1 意图解析（text-alt，sealed）

sealed 全量：正确 14 条 `2.1-005, 2.1-006, 2.1-008, 2.1-010, 2.1-015, 2.1-016, 2.1-017, 2.1-018, 2.1-019, 2.1-020, 2.1-023, 2.1-026, 2.1-029, 2.1-030`；错误 4 条 `2.1-004, 2.1-007, 2.1-009, 2.1-014`。

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

#### 2.4 候选精筛（text-primary，sealed）

sealed 全量：正确 14 条 `2.4-004, 2.4-005, 2.4-007, 2.4-009, 2.4-010, 2.4-011, 2.4-013, 2.4-017, 2.4-019, 2.4-020, 2.4-021, 2.4-026, 2.4-028, 2.4-029`；错误 4 条 `2.4-015, 2.4-024, 2.4-025, 2.4-030`。

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

#### 1.4 概念族学习（text-primary，sealed，金标待人工复核）

sealed 全量：正确 6 条 `1.4-007, 1.4-009, 1.4-010, 1.4-012, 1.4-013, 1.4-014`；错误 4 条 `1.4-008, 1.4-011, 1.4-015, 1.4-016`。

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

1.4 的判定口径需要额外说明（金标为 AI 起草）：

- `1.4-015`（帆布鞋 + 全新）金标要求 `reject/forbidden_alias`；模型没有把“全新”写成别名，直接复用“帆布鞋”族，按金标记为错误。这属于“金标期待模型犯错”的条件性样例：模型行为其实更安全，但金标无法表达“两种都可接受”。
- `1.4-016`（“壶”）金标为 `reject/invalid_name`，模型确实拒绝，但原因是 `invalid_alias`，原因类别不同。它说明拒绝是稳定的，细分原因不稳定。
- 因此 1.4 的 `accept_accuracy`/`family_f1` 可参考，`alias_f1` 与拒绝原因类别只作诊断；待人工复核金标后再决定是否保留这些分层。

## 10. 复现

```bash
# 仓库根目录：单元测试
./.venv/Scripts/python.exe -m pytest backend/tests -q

# backend 目录：探测、干跑、真实运行、校验
../.venv/Scripts/python.exe -m eval.cli check-models --config eval/models.json
../.venv/Scripts/python.exe -m eval.cli dry-run --node 1.1,1.2,2.1,2.4,1.4 --split dev
../.venv/Scripts/python.exe -m eval.cli run --node 1.1,1.2,2.1,2.4,1.4 --split dev --real \
  --out ../reports/eval/2026-11-23-model-selection-dev
../.venv/Scripts/python.exe -m eval.cli run --node 1.1,2.1 --split sealed_test --candidate text-alt --real \
  --out ../reports/eval/2026-11-23-selected-sealed-text-alt
../.venv/Scripts/python.exe -m eval.cli run --node 2.4,1.4 --split sealed_test --candidate text-primary --real \
  --out ../reports/eval/2026-11-23-selected-sealed-text-primary
../.venv/Scripts/python.exe -m eval.cli run --node 1.2 --split sealed_test --candidate vision-primary --real \
  --out ../reports/eval/2026-11-23-selected-sealed-vision-primary
../.venv/Scripts/python.exe -m eval.cli cases --report ../reports/eval/2026-11-23-selected-sealed-text-alt --node 1.1
../.venv/Scripts/python.exe -m eval.cli verify ../reports/eval/2026-11-23-selected-sealed-text-alt
```

可追溯信息：

- 数据集：`2026-11-23-v3`，冻结于 `2026-11-23T12:00:00Z`；前 6 个文件 SHA 与 v2 相同，新增 `concepts_1_4.jsonl`（`annotators: ["AI-drafted, pending review"]`）。
- 基线 sealed：git SHA `54df454`，提示词 `item-2 / vision-publish-2 / intent-2 / lexical-alias-1 / review-1`。
- 适配 sealed：在 `54df454` 之上带未提交改动执行，随后以同一内容提交为 `fad5799`（`codex/ai-pipeline-evaluation` 分支）；提示词 `item-2 / vision-publish-3 / intent-3 / lexical-alias-1 / review-1`。
- 本轮 dev 与 selected-sealed：git SHA `d5b5bb6`，`git_dirty=true`（工作区含本轮未提交的 harness 与数据集改动，manifest 如实记录）；提示词 `item-2 / vision-publish-3 / intent-3 / review-1 / concept-1`。
- 逐例表：可由 `eval.cli cases --report <报告目录> --node <节点>` 重新生成；本轮逐例 Markdown 与运行日志作为中间产物未入库。

## 11. 概念学习节点（1.4）：数据集、指标与局限

本轮为 1.4 新建了同口径评测，但它的金标是 AI 起草、尚未逐行人工确认，因此结论只用于本轮选型参考。

- 数据集：`backend/eval/datasets/concepts_1_4.jsonl`，16 行（dev 6 / sealed 10）。每行给出商品文本（复用 1.1 风格）与该商品自带的 3–5 条目录快照；金标含 `decision`（apply/reject）、`reason`（`learned`/`no_family`/拒绝原因）与 `families`（名称、父类、别名）。分层覆盖 `normal`、`boundary`（一件商品多个族）、`no_family`、`alias_conflict`、`forbidden_alias`、`invalid_name`。
- 评测适配器（`backend/eval/adapters.py::run_concept`）：每条样本建独立内存 SQLite，按目录快照播种 `Concept/ConceptAlias`，调用生产 `concept_learning.propose`，再用 `concept_learning.validate` 跑全部护栏；**不调用** `apply_proposal`，因此不写业务库、不刷新全局目录，样本之间互不污染。输出记录 `decision`、`reason`、家族名（把内部 `c-<sha1>` 映射回名称）、别名与校验前的逐字接地率。
- 指标：`accept_accuracy`（决策是否一致）、`family_f1`（金标家族名 vs 预测家族名）、`alias_f1`（仅对金标给出别名的行计算，避免惩罚合理额外别名）、`evidence_grounded_rate`、`schema_valid_rate`、`p95`。门槛见 `thresholds.json`（`alias_f1≥0.70` 等），在运行前冻结。
- 真实结果：dev 上三个候选 `accept_accuracy` 0.833–1.000、`family_f1` 0.800–1.000，但 `alias_f1` 0.389/0.556/0.433 全部未达 0.70；sealed 上现模型 `accept_accuracy=0.800`、`family_f1=0.750`、`alias_f1=0.367`。因此按规则保留现模型并报告失败（§8.1、§7.1）。
- 失败形态：`1.4-008` 把折叠椅直接挂到“户外装备”而没有建子族（粒度过粗）；`1.4-011` 因自拟别名未逐字接地被 `ungrounded_alias` 拒绝；`1.4-015`/`1.4-016` 说明“拒绝类”金标依赖模型是否愿意冒险写别名（或拒绝原因类别不稳定），标注口径需要人工复核。
- 仍不能声称：别名抽取已达生产质量；1.4 指标可与 1.1/2.1 的历史 sealed 数字横向比较（n 与标注成熟度都不同）；学习在真实商品流上带来检索收益。护栏、状态机与查询期零模型调用仍由桩模型单元测试覆盖，见 [AI_TEST_CASES.md](AI_TEST_CASES.md) 第 6 节。
- 不进入证据：此前的手写同义词 dev 切片（`synonyms_*.jsonl`、`eval.cli synonyms`）针对的是已被移除的静态目录实现，相关文件已归档、CLI 入口已删除；其中的 Recall@10 与误召回数字不再适用于本实现，本报告不再引用。

## 12. 不能声称的事项

- 每节点 n=6–12（1.4 sealed n=10），结果不等于线上准确率或 P95 SLA；单条样本可改变 5–10 个百分点，不宣称统计显著。
- **不等于 Pareto 前沿**：本轮 5 个候选都在同一网关、同一把 key 下真实跑通，可以给出逐节点“占优/无差异证据”，但维度（质量、延迟、token）与样本量都不足以构造 Pareto 前沿。
- **不能用 sealed 反过来改选型**：sealed 只给 dev 胜者各跑一次；2.1 引文召回 0.931、1.2 无依据属性 0.333、2.4 判定准确率 0.778、1.4 alias_f1 0.367 均未过线，只如实记录，没有据此回改提示词或金标。
- **部署未拆分**：1.1/2.1 的 dev 胜者是 text-alt，但生产端仍只有一个文本模型服务全部文本节点；按节点拆分配置属于未实施的部署改造。
- **1.4 金标未人工确认**：每行 `annotator` 是 `AI-drafted, pending review`，`accept_accuracy`/`family_f1` 只作本轮选型参考；`alias_f1` 与拒绝原因类别只作诊断。若人工复核后修改金标，需要以 v4 重新冻结并重跑 1.4，当前数字不能当作最终结论。
- 1.4 的“拒绝类”样例是条件性的：模型可以选择不写危险别名而安全通过，此时按金标仍记为错误；报告如实列出，不把它包装成模型缺陷。
- 概念学习只扩充符号目录，不改提示词或模型权重；错误词条目前需要人工从数据库修正，没有在线回滚或审核界面。不声称即时向量检索、自动发布或反思式自我修正。
- 1.2-007 的受控数据缺陷只做敏感性说明，不修改 sealed 数据，也不据此重跑最终结果；1.2 的 sealed 分类准确率 0.889 已包含该行（其余 8 条全对）。