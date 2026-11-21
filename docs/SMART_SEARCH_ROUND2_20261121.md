# 智能搜索第二轮回归（2026-11-21）

本文记录第二轮实验当时的规则。后续按用户确认的口径，“两百多”改为 200–300 元（含两端），“200 元左右”继续按约价处理。历史统计保留当时的标注，当前价位段见[预算用例](../evals/search_benchmark/cases/search-price-01.json)。

七组 OpenLux 配置沿用第一轮成功解析的 1,284 条记录，误匹配从 26 次降至 0，漏匹配从 9 次降至 0。共移除 142 个无关商品件次、找回 9 个相关商品件次，原本命中的商品全部保留。发生商品集合变化的 35 条记录来自 8 个不同查询。每次改动的原始解析、实际采用的条件、移除和找回的商品名均已保存。[逐次明细及实验汇总](../evals/experiments/2026-11-21-smart-search/round2-summary.json)

## 同一批查询的前后对照

商品库固定为 52 件，开发集包含 80 条查询。74 条带有完整检索标注，各执行三次，另外 6 条只评价解析。按“模型配置 × 查询 × 重复”计数，多返回至少一件无关商品计一次误匹配，少返回至少一件相关商品计一次漏匹配。远程共 1,554 条应评检索记录，沿用第一轮分母，历史调用失败或输出无效的 270 条单列。本轮远程 API 调用数为零。标注、评分器及选型规则沿用第一轮。[第一轮报告](SMART_SEARCH_REGRESSION_20261121.md)

| 解析来源 | 有效检索记录 | 误匹配，第一轮 → 第二轮 | 漏匹配，第一轮 → 第二轮 | 完全匹配，第一轮 → 第二轮 |
| --- | ---: | ---: | ---: | ---: |
| DeepSeek Flash，关闭思考 | 218 | 6 → 0 | 0 → 0 | 212 → 218 |
| DeepSeek Flash，开启思考 | 218 | 6 → 0 | 2 → 0 | 210 → 218 |
| Qwen Max | 193 | 6 → 0 | 2 → 0 | 185 → 193 |
| 豆包 Pro | 214 | 3 → 0 | 1 → 0 | 210 → 214 |
| Kimi Pro | 171 | 1 → 0 | 0 → 0 | 170 → 171 |
| MiniMax Flash | 152 | 2 → 0 | 3 → 0 | 147 → 152 |
| GLM | 118 | 2 → 0 | 1 → 0 | 115 → 118 |
| **远程合计** | **1,284** | **26 → 0** | **9 → 0** | **1,249 → 1,284** |
| 本地规则，重新解析并检索 | 222 | 12 → 0 | 18 → 0 | 192 → 222 |
| Oracle，输入标注意图后走同一搜索入口 | 222 | 0 → 0 | 3 → 0 | 219 → 222 |

回放前用第一轮代码重新生成检索明细，与保存的第一轮文件逐字节相同。第二轮向智能搜索入口注入相同的模型解析，并传入原查询。入口根据买家的原话核对条件，再进入检索。基线配对会校验历史运行 ID、已变更记录的原排名，以及各配置的记录数、误返和漏返总数。[回放脚本](../evals/experiments/2026-11-21-reproduction/source/scripts/replay_search_regression.py) · [本机完整回放](../evals/experiments/2026-11-21-reproduction/records/search-round2-final-replay.json)

## 修复发生在哪里

| 查询及第一轮行为 | 第二轮行为 | 改善的远程记录 |
| --- | --- | ---: |
| “两百多买鼠标”被解释成 299、300 元或无限预算，也可能被截在 200 元 | 原有标注采用 200 元目标价。允许上浮 15%，即最多 230 元，保留更便宜的候选，找回 220 元的无线静音鼠标 | 15 次误返、1 次漏返 |
| “400以内静音鼠标”只提取了“鼠标” | 从原话补回必须属性“静音”，移除游戏鼠标等缺乏静音证据的商品 | 10 次误返 |
| 一条网球拍查询的模型解析丢失商品主体，导致返回整个商品库 | 从原话恢复“网球拍”，移除 51 件无关商品 | 1 次误返 |
| “优先车锁”“优先 LED”进入必须项 | 普通通勤自行车和普通台灯保留，带锁或 LED 商品优先展示 | 3 次漏返 |
| “键盘接收器”被增加“无线接收器”条件 | 移除原话没有要求的“无线”，找回 USB 键盘接收器 | 1 次漏返 |
| 笔记本支架和绿色积木玩具巴士被推断为“宿舍生活与家电” | 推断分类下没有结果时，仅撤销推断分类重查；成功后响应返回实际采用的筛选条件。用户指定的分类、校区、预算和属性继续生效 | 4 次漏返 |

明确的“200 元以内”仍以 200 元为上限。“万柳附近”的“近”不会触发价格浮动。预算识别与型号、成色分开，保留 G20、SER8 等型号中的数字。接口测试另外验证了 230.00 元和 230.01 元的边界，以及撤销推断分类后仍能排除其他校区的商品。[解析校正](../evals/experiments/2026-11-21-reproduction/source/backend/app/search_intent.py) · [搜索入口](../evals/experiments/2026-11-21-reproduction/source/backend/app/search.py) · [边界与接口测试](../evals/experiments/2026-11-21-reproduction/source/backend/tests/test_search_intent_grounding.py)

## 完整解析与排序

按原评分器同时检查字段、澄清和检索，本地规则从 141/240 提高到 171/240，Oracle 从 237/240 提高到 240/240。共 33 条从失败转为通过，原先通过的全部保留。排名指标与查询改写关系均无退化。另跑 40 条常规解析用例，评分保持不变。[搜索比较](../evals/experiments/2026-11-21-reproduction/records/search-round2-final-comparison/comparison.md) · [解析比较](../evals/experiments/2026-11-21-reproduction/records/parse-round2-20261121-comparison/comparison.md)

用第一轮人工核对过的 6 条偏好查询检验顺序，要求候选集合完整且所有满足偏好的商品排在其他合格商品之前。七个远程配置有 107 条有效记录，通过数从 104 提高到 107；Oracle 按不同查询核对，两轮均为 6/6。[逐用例排序结果](../evals/experiments/2026-11-21-smart-search/round2-summary.json)

这批结果衡量固定开发集上的检索。模型原始解析仍会出错，这次修复生效在检索前的条件校正环节。远程接口可用性和线上真实用户的搜索效果需要另行实测。

运行 `python -m pytest -q backend/tests evals/tests`，455 项测试全部通过，其中包含本轮新增的 19 项金额、条件归属与接口回归测试。

## 复现

在仓库根目录运行，第一条使用本机保存的 OpenLux 原始记录和第一轮回放。后两条重跑本地规则与 Oracle，并和第一轮端到端结果对照。

```powershell
python scripts/replay_search_regression.py --run test-results/selection-openlux-full --baseline-replay test-results/search-replay-20261121.json --output test-results/search-round2-replay-check.json
python scripts/run_model_eval.py run --cases evals/search_benchmark/cases --model-config evals/models.search.json --models local-rules,oracle --relations evals/search_benchmark/relations.json --policy evals/selection_policy.search.json --repeats 3 --output test-results/search-round2-check-new
python scripts/run_model_eval.py compare --baseline test-results/search-regression-20261121 --current test-results/search-round2-check-new --output test-results/search-round2-check-diff --fail-on-regression
```
