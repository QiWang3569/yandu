# 测试用例管理与模型自动评测

这套机制将测试数据、模型配置、执行过程和评分规则分开保存，用同一批输入比较模型，并在代码或提示词变化后检查回归。现有业务测试继续验证权限、交易、重试等程序行为；新增评测记录真实模型输出和任务质量。

首版支持需求解析、商品信息提取、求购解析、候选匹配精筛。48条合成开发用例位于 `evals/cases/`，逐例标注规则见 [用例库说明](../evals/DATASET.md)。识图需要单独的图片与人工标注集，未纳入本轮文本评测。

## 文件与职责

| 位置 | 职责 |
| --- | --- |
| `evals/cases/<任务>/<ID>.json` | 输入、预期、标签、启用状态、数据划分和判定理由 |
| `evals/schema.py` | 校验输入、业务枚举、ID、同义词及跨集合测试族 |
| `evals/models.json` | 模型配置；密钥只保存环境变量名 |
| `evals/adapters.py` | 复用业务函数、当前提示词、输出校验和回退行为 |
| `evals/providers.py` | 真实接口调用、重试、原始响应、耗时与usage记录 |
| `evals/scoring.py` | 确定性的字段、集合、候选结论和引用来源评分 |
| `evals/selection_policy.json` | 选型门槛、规则状态与最少样本量 |
| `evals/reporting.py` | 汇总、选型理由、失败清单、回归比较 |
| `scripts/run_model_eval.py` | `validate`、`list`、`run`、`compare` 命令 |
| `evals/baselines/local-rules/` | 已核查的本地规则回归基线 |

## 本地执行

在项目根目录，使用安装了 `backend/requirements.lock.txt` 的 Python 3.12 环境：

```powershell
python scripts/run_model_eval.py validate
python scripts/run_model_eval.py list --tasks intent_parse
python scripts/run_model_eval.py run --models local-rules --output test-results/model-eval
python scripts/run_model_eval.py compare --baseline evals/baselines/local-rules --current test-results/model-eval --output test-results/model-regression --fail-on-regression
```

Windows也可将 `python` 替换为 `.\.venv\Scripts\python.exe`。每次运行使用新的空目录；省略 `--output` 时自动生成 `evals/results/<UTC时间及随机ID>/`，该目录不进入Git。

支持 `--tasks`、`--tags`、`--case-ids`，多个值用逗号分隔；多个标签按“任意标签命中”筛选。默认运行启用的开发集，使用 `--split holdout` 单独执行保留集。`--repeats` 设置每例重复次数；`--seed` 固定调度顺序，按用例交错运行各模型。

```powershell
python scripts/run_model_eval.py run --models local-rules --case-ids intent-014,intent-021 --output test-results/negation-check
```

`run` 正常完成诊断时退出0，即使有未通过用例；`--require-pass` 会在任何用例未通过时退出1。配置错误、空筛选结果或不可比较的回归退出2，中断退出130。自动回归通过 `compare --fail-on-regression` 检查新增退化，保留基线中已知的失败场景。

## 增删用例

新增时复制同任务JSON，分配唯一ID，修改输入、预期与理由，然后运行 `validate`。停用时设 `enabled: false` 并在 `rationale` 写明原因；删除由Git历史追溯。用例的标准答案独立于某个模型的输出。

`expected.fields` 中省略字段表示不评价，`null` 表示明确期望为空。`expected.sets` 的每个内层列表是一个概念的合法同义表达，完整词项匹配，缺项和额外项都会扣分。修改评分逻辑时递增 `evals/__init__.py` 中的 `SCORER_VERSION`，原结果不再作为同口径回归基线。

同一测试族及同源素材整组划分到dev或holdout。开发集用于修改提示词，保留集应独立构造、人工复核。当前48例全部为 `dev/draft`，需团队复核后再作为正式评测资料；已经用于调试的样例不能仅修改split就当作独立保留集。

## 真实模型比较

`text-a`、`text-b` 是待配置的候选槽位。由执行环境注入以下变量：

| 配置 | 候选A | 候选B |
| --- | --- | --- |
| 服务商精确模型ID | `EVAL_MODEL_A` | `EVAL_MODEL_B` |
| API基础地址，包含服务商要求的版本路径 | `EVAL_BASE_URL_A` | `EVAL_BASE_URL_B` |
| API密钥 | `EVAL_API_KEY_A` | `EVAL_API_KEY_B` |

客户端在基础地址后追加 `/chat/completions`，要求HTTPS和JSON对象输出。评测不读取应用 `.env`，不构造生产数据库、邮件或图片服务配置。它复用 `services.parse_intent/parse_item/parse_wanted` 与 `buyer_agent.review_candidates`，在独立顺序执行进程中替换模型调用边界，获取当前提示词并观测响应；没有复制另一套业务prompt。

```powershell
python scripts/run_model_eval.py run --models text-a,text-b --tasks intent_parse --repeats 3 --max-requests 300 --allow-remote --output test-results/text-comparison
```

当前24条需求例、两个模型、三次重复、每次最多一次重试，最坏为288次请求。执行前检查最坏请求数，超过上限整轮拒绝启动。请求上限控制次数，不等于人民币预算；实际费用由模型计价和token用量决定。

默认温度0.1，解析输出上限2500 tokens，精筛5000 tokens；配置可覆盖 `max_tokens`、`thinking`、`timeout`、`retries`。只对网络错误、超时、429和5xx重试；无效JSON、截断和schema错误直接记失败。报告保留每次尝试，最终延迟包含退避与重试。

可在配置中增加 `pricing`：`input_per_million_cny`、`output_per_million_cny`、可选 `cached_input_per_million_cny`，并填写价格来源 `source` 与核对日期 `checked_at`。仅在计价及usage齐全时计算费用。重试中任一请求计费未知，整次总费用仍为未知；已知部分可查看逐次记录。

## 评分与失败归属

| 任务 | 自动指标 | 仍需人工复核 |
| --- | --- | --- |
| 需求／求购解析 | 整例通过率、字段与条件集合断言、格式合法率、澄清触发 | 澄清是否准确指出问题、合法同义词是否完整 |
| 商品提取 | 分类、价格、校区、成色、标签的声明断言 | 标题与描述的事实保留；未给字段是否被臆测 |
| 候选精筛 | 三分类macro-F1、错误推荐率、候选完整性、引用来源 | 引用是否逻辑上支持结论 |

整例通过要求该例全部已声明断言通过；平均评分是每例断言得分的平均，不能写成课程要求的“字段准确率”。macro-F1固定平均三类，缺样本的类别记0；错误推荐率分母为预期非MATCH的候选。

报告同时保存 `raw_output`、`output`、`raw_score`、`score`、`application_score` 和 `fallback_used`。商品／求购接口在模型失败后可能返回本地规则结果：模型评分仍为0，应用结果另列。精筛将缺少证据的MATCH降为UNCERTAIN时，保留修改前后的判断。求购模型原始输出是ParsedIntent，`raw_score`先按生产映射转为求购字段，再和求购答案比较；原始对象仍保留。

失败请求留在分母。精筛失败时所有预期候选保留为INVALID预测，不能把失败批次从macro-F1中删除。本地规则的运行耗时不参与远程模型网络延迟的比较。

## 输出与回归

每轮输出包含：

- `manifest.json`：代码SHA、未提交状态、实现哈希、测试集哈希、评分器版本、模型配置、重复次数、运行完整性。
- `cases.json`、`policy.json`：当次输入和评分目标、选型规则快照。
- `records.jsonl`：逐例输入对应ID、原始输出、校验后结果、错误、token、费用和各次尝试。
- `summary.json`、`summary.csv`、`report.md`：分任务汇总、失败清单和选型结论。

Ctrl+C保留已完成结果，并将运行标记为不完整。回归要求模型配置、评分器版本、重复次数一致，只比较共有且未修改的用例；新增、删除和修改单列。通过转失败或已有失败的评分下降都会使回归命令退出1。没有共有用例、缺失记录或不完整运行时拒绝比较。

替换基线前先检查失败变化、标签修改和评分器版本。基线不因当前结果变差而自动更新。`cases.json`快照、逐例记录和manifest应一并保留。

## 选型规则

`selection_policy.json` 默认 `status: draft`。团队在实测前确定门槛后改为 `confirmed` 或 `locked`。正式建议要求：人工复核的保留集、每任务至少20例、完整重复运行、至少两个不同远程候选、相同用例与可核对的结果。

先检查任务质量和错误率门槛，再按整例通过率形成质量候选组；`quality_tolerance` 默认为0，只有通过率相同才进入同档。质量同档且费用都已知时比较费用，否则使用P95延迟并注明费用未参与。解析与精筛分别选型。候选全部未达标时报告具体原因；本地或开发集诊断保留“尚未确定优选模型”。首版规则中的20例、精筛F1和错误率门槛均为项目拟定值，可在实验前调整并冻结。

## CI执行

现有 `Application checks` 在Windows和Linux上运行业务测试、评测框架测试、用例校验、本地规则评测与基线比较，并上传报告。离线CI不需要密钥。

新增 `Model evaluation` 使用 `workflow_dispatch` 手动触发。仓库Variables配置 `EVAL_MODEL_A/B`、`EVAL_BASE_URL_A/B`，Secrets配置 `EVAL_API_KEY_A/B`；可选择模型、集合、重复次数及请求上限。所有输入先传入环境变量再作为带引号的命令参数，结果作为Actions artifact保留30天。

首轮诊断与选型依据见 [模型选型报告](MODEL_SELECTION_REPORT.md)。
