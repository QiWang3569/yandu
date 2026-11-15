# 固定商品库与智能搜索评测

本次按《评测方法(1).pdf》扩展已有执行器，新增 `smart_search` 任务。数据、模型配置、评分、回归继续使用同一套管理机制。商品文案和 Products-10K 图片任务继续独立运行。

## 数据与执行边界

`evals/search_benchmark/catalog.json` 固定 52 件合成商品，覆盖六个业务类别、五个校区、五档成色及价格边界。ID、描述、价格、状态和发布时间均固定。运行时创建独立内存 SQLite 数据库，复用线上 `execute_smart_search`、解析、硬过滤与关键词排序，不读写应用数据库。

`cases/` 包含 70 条基础查询，七类场景各 10 条：`core` 高频需求、`ood` 本地词典盲区、`negation` 否定排除、`preference` 软偏好与硬条件、`price` 价格边界、`confusable` 易混淆品类／配件、`ambiguity` 歧义／冲突／注入。另有 10 条改写或收紧预算的查询，共 80 条。`relations.json` 声明 8 组不变关系和 4 组方向关系；其中两组复用基础用例。

商品事实、标准解析和相关商品 ID 在模型执行前独立编写，没有调用被测搜索程序生成答案。源码生成器为 `scripts/build_search_benchmark.py`，只用于生成新的空版本目录；日常维护直接编辑 JSON。全部标签为 `draft/dev`，商品库也标为 `draft`，待团队复核。`family` 将基础查询与改写绑定，禁止跨 dev/holdout；它们不能拆成独立保留样本。

本轮评测覆盖搜索服务函数的完整解析、过滤与排序流程，取回固定库中的全部结果后计算指标。耗时不含建库，也不含 HTTP 鉴权、客户端网络和传输；不能把本地服务函数 P95 当成线上 HTTP 接口 P95。

## 用例维护

搜索用例保留原有 11 个根字段。`input.text` 为查询；`expected` 增加：

| 字段 | 含义 |
| --- | --- |
| `parse` | 原有解析断言：`fields`、`sets` 同义词组和 `clarification` |
| `oracle_intent` | 显式填写全部八个解析字段；必须符合业务结构且通过 `parse` 断言 |
| `relevant_item_ids` | 满足查询的全部商品 ID；当前由助手预标注，正式评测须经人工复核，不从模型结果反推 |
| `retrieval_applicable` | 歧义、冲突可设为 false，只评价解析；同时相关 ID 必须为空 |
| `around_price` | 预期是否触发约数处理；与模型解析字段分开评价 |

普通无匹配查询保持 `retrieval_applicable=true`、相关 ID 为空，整例要求返回空集。不能用“不适用检索”隐藏漏召回。当前 80 例中，70 例有相关商品、4 例应无结果、6 例只评价歧义／冲突解析。整例通过要求全部解析断言、约数断言及适用时完整结果集合相等；排名得分另列，避免正确首条掩盖多余召回。

新增用例使用新 ID；停用设 `enabled=false`；删除或修改保留 Git 历史。按 `tags` 过滤运行，场景标签使用 `slice:名称`。关系文件引用两个用例 ID，必须同 family、同 split；筛选只运行其中一端时关系不执行，跳过数量写入 manifest。

## 指标口径

- 单值字段：准确率；类别、校区、成色另算 Macro-F1，标签集合使用当前统计组标准答案实际出现的类别，包括显式 null，并保存支持数。价格按十进制数值比较。
- 集合字段：按预先声明的同义词组匹配，报告 Micro Precision/Recall/F1 与逐例 Macro-F1。双方为空计 1；结构／执行失败计 0，Micro 汇总保留一个无效预测错误项。
- 澄清触发：正类为“需要澄清”；空白文本不算澄清。无效输出使应澄清正例计入漏报，不把无效负例虚构成已触发的误报；无效数、准确率单列。没有正例且没有误报时 F1 留空，支持数单列。
- Schema 首次通过率：首次请求成功且模型原始结构有效。重试后成功不计首次通过；应用回退结果单独评分。
- MRR：首个相关结果排名的倒数，无命中为 0，使用完整排序。
- MAP@5：每个查询的 AP@5 分母为 `min(5, 相关商品数)`，再对查询取均值。
- Recall@10：前 10 条命中数除以全部相关商品数。
- 排名三项仅统计有相关商品且适用检索的查询；执行失败仍计 0。无相关商品和不适用检索的查询不混入排名均值。
- 零结果误杀率：有相关商品且结构有效、执行成功的查询中返回空集的比例；分母和执行错误另列，区分检索过严与接口失败。
- 重复一致率：以唯一用例为单位，要求全部计划内重复成功，输出 JSON 完全一致。只忽略对象键顺序，保留数组顺序与文字差异；重复不足两次留空。重复失败不会被误计为稳定。
- 错误率降低：以整例失败为错误，计算 `（模型通过率−本地通过率）/（1−本地通过率）`；本地全对时留空。MRR 等排名质量只报告绝对增量。

每次执行记录解析阶段、检索阶段及服务流程总耗时。P50/P95 使用线性插值；重试耗时与失败记录保留。模型 usage 按提供方返回计数，未核实单价时费用为未知。

## 蜕变关系与 Oracle

`invariant` 比较规范化解析与完整结果 ID 集合。词项忽略空白／大小写、集合顺序，并使用用例中预先声明的同义词组；澄清只比较是否触发。该关系不要求不影响语义的澄清措辞完全相同。

`subset` 要求变换后的完整结果集合是原集合的子集，并检查新增预算上限、不得出现的商品 ID。比较完整集合可以避免“删去前排商品后，原第 11 条补入前 10 条”的误报。基例为空时单列，不能把空集上的通过当作充足证据。两端任一失败或缺失，关系判失败。

`oracle` 模式将预标注 `oracle_intent` 注入同一个搜索函数，再执行真实过滤与排序；不会复制 `relevant_item_ids`。因此 Oracle 也可能失败，能显示解析之后的检索损失。当前答案未经人工复核，Oracle 是诊断对照，不是已验证的系统性能上限。

## 本地运行与回归

在项目根目录，使用安装了锁定依赖的 Python 环境。输出目录须为空：

```powershell
python scripts/run_model_eval.py validate --cases evals/search_benchmark/cases --model-config evals/models.search.json --relations evals/search_benchmark/relations.json
python scripts/run_model_eval.py run --cases evals/search_benchmark/cases --model-config evals/models.search.json --models local-rules,oracle --relations evals/search_benchmark/relations.json --policy evals/selection_policy.search.json --repeats 3 --output test-results/search-eval
python scripts/run_model_eval.py compare --baseline evals/baselines/search-v1.2 --current test-results/search-eval --output test-results/search-regression --fail-on-regression
```

默认 `--catalog` 为 `evals/search_benchmark/catalog.json`；新版本通过参数指定。生成器只接受空目录，例如 `python scripts/build_search_benchmark.py --output data/new-search-package`。修改商品库后须复核相关性标签并建立新基线；比较器拒绝商品库或关系定义哈希不同的两轮。

报告目录保存 cases/catalog/relations 的快照、模型配置、提示词与实现哈希、逐例原始／应用输出、评分与耗时。汇总包括 `report.md`、`summary.json/csv`、`parse_metrics.csv`、`slices.csv`、`metamorphic.json`。回归检查同时覆盖整例退化、评分降低、MRR/AP@5/Recall@10 降低和原先通过的关系转为失败。

评分器版本为 `1.2.0`。CI 在 Linux/Windows 上运行原有本地规则基线和这组搜索基线，不调用付费模型。历史基线目录不覆盖。

## 候选模型与选型

`evals/models.search.json` 配置六个候选，以及 DeepSeek 思考模式开／关两个配置，总计七个远程配置。使用七牛统一入口及 `EVAL_QINIU_API_KEY` 环境变量，密钥不写入文件。模型 ID 已对照 2026-11-15 的 [七牛模型列表](https://api.qnaigc.com/v1/models)；豆包使用 `bytedance/doubao-seed-2-1-pro`。模型列入接口目录不代表所有解码参数均已实测，先做小样本兼容性检查，失败如实入表。价格没有沿用 PDF 未核实的数字。

六模型、每类一例的接口检查最多 42 次请求，不含思考模式变体：

```powershell
python scripts/run_model_eval.py run --cases evals/search_benchmark/cases --model-config evals/models.search.json --models local-rules,oracle,deepseek-flash,qwen-max,glm,doubao-pro,kimi-pro,minimax-flash --case-ids search-core-01,search-ood-01,search-negation-01,search-preference-01,search-price-01,search-confusable-01,search-ambiguity-01 --policy evals/selection_policy.search.json --max-requests 42 --allow-remote --output test-results/search-remote-smoke
```

完整 80 例、每例三次、六个候选共 1440 次请求；加入 DeepSeek 思考模式变体为 1680 次（当前配置均不重试）。需按所选配置设置 `--max-requests`；执行器会在读取密钥及付费调用前检查上限。

本机另有 `evals/models.search.openlux.json`，使用 `YUNWU_GEMINI_API_KEY` 和 OpenLux 入口，保留七牛配置。该配置还支持原有文本任务；实际模型 ID 及 `returned_model` 随结果保存。OpenLux 对 DeepSeek 思考开关的支持需要从返回元数据核实，不能仅依据请求中写了 `thinking=enabled` 就断言思考模式已生效。

2026-11-15 全量实验将 48 条原有文本用例、80 条搜索用例和 8 条已导入商品文案合并为本地冻结包 `data/model-selection/full-v1/cases`。七个远程配置各运行 136 例 × 3 次，共 2,856 次请求；本地规则运行 128 例 × 3 次，Oracle 运行 80 例 × 3 次，共 3,480 条记录。8 条图片用例继续作为独立视觉任务，不把六款文本候选的结果当作图片测评。

```powershell
python scripts/build_selection_case_bundle.py --output data/model-selection/full-v1/cases
python scripts/run_model_eval.py run --cases data/model-selection/full-v1/cases --model-config evals/models.search.openlux.json --models local-rules,oracle,deepseek-flash,deepseek-flash-thinking,qwen-max,glm,doubao-pro,kimi-pro,minimax-flash --relations evals/search_benchmark/relations.json --policy evals/selection_policy.search.json --repeats 3 --concurrency 8 --max-requests 2856 --allow-remote --output test-results/selection-openlux-full
python scripts/summarize_selection_experiment.py --run test-results/selection-openlux-full --output evals/experiments/2026-11-15-openlux
```

汇总导出器校验用例哈希和完整的用例／模型／重复矩阵，再导出 `provenance.json`、`summary.json`、`analysis.json` 和冻结的 `policy.json`，不复制原始商品文案或模型回答。补充的配对 bootstrap 以 family 为抽样单位，将三次重复和改写留在同一簇中；其 95% 区间是开发集上的事后描述，未做多重比较校正，不代替保留集检验。

构建冻结包前，须按[公开数据接入指南](PUBLIC_DATASET_INTEGRATION.md)准备 TaoDescribe 的 8 条本地用例。构建器拒绝非空输出目录；已有 `full-v1` 时直接复用，下一轮新建版本目录。

正式选型使用独立编写并人工复核的 holdout，商品库也须 reviewed。`selection_policy.search.json` 为待确认草案，列出质量、错误率、首次 Schema、重复一致率、关系通过率和 2.5 秒 P95 门槛。至少需要两个不同实际远程模型的完整同题结果；同一模型的思考开关不算两个独立候选。缺少保留集、人工复核、指标或已确认规则时不自动推荐模型。通过门槛后按整例质量、已知费用与 P95 排序，并在报告说明理由。
