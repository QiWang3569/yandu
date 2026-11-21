# 智能搜索第一轮回归（2026-11-21）

七组远程模型配置固定解析后回放，1,284 条可比记录中，多返回无关商品从 315 次降到 26 次，减少 91.7%。漏掉相关商品从 66 次降到 9 次，减少 86.4%。商品集合与标注完全相同的记录从 903 次增至 1,249 次（70.3% → 97.3%）。这些数字描述固定开发集上的检索结果。[实验汇总及逐件漏匹配](../evals/experiments/2026-11-21-smart-search/summary.json)

## 比较方法

沿用 52 件商品和 80 条原有开发查询的草案标注。74 条查询有检索标注，各执行三次，另外 6 条仅评价解析。七个远程配置共有 1,554 条应评检索的记录，其中 270 条历史调用失败或输出无效，剩余 1,284 条用同一份解析、相同商品库和相同标注逐条比较。改动前已用旧检索重现历史返回顺序。本次回放的远程调用数为零。[历史实验来源](../evals/experiments/2026-11-15-openlux/provenance.json) · [回放脚本](../evals/experiments/2026-11-21-reproduction/source/scripts/replay_search_regression.py)

一次查询多返回至少一件无关商品，计一次误匹配。少返回至少一件相关商品，计一次漏匹配。商品件次按“模型配置 × 查询 × 重复 × 商品”计数。按商品件次，远程误返从 708 减到 142，漏返从 139 减到 9。旧结果中漏掉的 134 件次得到恢复，另有 4 件次从命中变为漏返。三次重复使用同一批查询。

## 分配置结果

| 解析来源 | 可比记录 | 误匹配次数，前 → 后 | 漏匹配次数，前 → 后 | 集合完全正确，前 → 后 |
| --- | ---: | ---: | ---: | ---: |
| DeepSeek Flash，关闭思考 | 218 | 53 → 6 | 6 → 0 | 159 → 212 |
| DeepSeek Flash，开启思考 | 218 | 53 → 6 | 7 → 2 | 158 → 210 |
| Qwen Max | 193 | 48 → 6 | 14 → 2 | 131 → 185 |
| 豆包 Pro | 214 | 59 → 3 | 8 → 1 | 147 → 210 |
| Kimi Pro | 171 | 47 → 1 | 6 → 0 | 118 → 170 |
| MiniMax Flash | 152 | 24 → 2 | 20 → 3 | 108 → 147 |
| GLM | 118 | 31 → 2 | 5 → 1 | 82 → 115 |
| **七组远程合计** | **1,284** | **315 → 26** | **66 → 9** | **903 → 1,249** |
| Oracle，直接给定人工标注的意图 | 222 | 51 → 0 | 9 → 3 | 162 → 219 |
| 本地规则，重新解析并检索 | 222 | 93 → 12 | 27 → 18 | 102 → 192 |

本地规则同时改了复合商品名和条件提取。若复用旧本地解析，只替换检索，漏匹配会从 27 增至 36。旧规则会把“键盘接收器”提取成“键盘”，新检索按主体过滤时会丢掉接收器。更新本地解析后，这条查询保留“键盘接收器”，端到端的漏匹配降至 18 次。[本地与 Oracle 端到端比较](../evals/experiments/2026-11-21-reproduction/records/search-comparison-20261121/comparison.md)

## 搜索行为

- **主体和配件**。按标题识别实际出售的物品，区分主体、适配设备和随附配件。Oracle 搜“MacBook电脑”，原来会返回笔记本支架、MacBook 充电器、联想笔记本和 MacBook Air。现在只返回 MacBook Air 笔记本电脑。
- **必须条件**。逐项检查主体和属性，允许证据分布在标题、描述及标签里。“免费”和成色可直接用标价及成色字段核对。搜“万柳150以内无线鼠标”，仍返回两款符合条件的鼠标，移除了只匹配“无线”的无线路由器。
- **排除词**。检查商品是否明确具备被排除的属性。文案里的“不支持静音”“不带车锁”按否定处理。“不要山地”保留通勤自行车。明确要求蓝牙时保留蓝牙的具体含义，搜无线时可用蓝牙作为证据。
- **偏好排序**。“最好”“优先”参与推荐顺序，先比较命中的偏好数，同分时再按目标价接近度（约价查询）、发布时间和商品 ID 排序。用户手动选择价格或最新排序时按选定字段排序。“200以内耳机，最好降噪”前后都保留两副耳机，降噪耳机从第二位升至第一位。

额外核对了 6 条已有偏好查询，其中包含 1 条同义改写。根据固定商品文案人工列出满足偏好的商品，要求候选集合正确且所有偏好商品排在其余商品之前。Oracle 下按唯一用例，符合这两个条件的从 3/6 升至 6/6。逐例结果见[偏好顺序核对表](../evals/experiments/2026-11-21-smart-search/summary.json)。[生产检索实现](../evals/experiments/2026-11-21-reproduction/source/backend/app/search.py) · [主体与属性匹配规则](../evals/experiments/2026-11-21-reproduction/source/backend/app/smart_terms.py) · [入口回归测试](../evals/experiments/2026-11-21-reproduction/source/backend/tests/test_smart_terms.py)

## 余下的错误

| 远程配置仍漏掉的商品 | 件次 | 对照原查询与解析后的原因 |
| --- | ---: | --- |
| 通勤自行车 | 2 | “优先车锁”被写入必须关键词。一次解析同时把车锁写进必须项和偏好项，普通通勤车被过滤 |
| 普通台灯 | 1 | “优先LED”被解析成必须有 LED |
| USB键盘接收器 | 1 | GLM 为“键盘接收器”额外要求“无线接收器”，商品文案没有无线证据 |
| 绿色积木玩具巴士 | 2 | 模型给出“宿舍生活与家电”，商品登记在“美妆服饰与周边”，在分类过滤时丢失 |
| 笔记本支架 | 2 | 模型给出“宿舍生活与家电”，商品登记在“数码与影音” |
| 220 元的无线静音鼠标 | 1 | “两百多”落成 200 元硬上限，排除了标注相关的 220 元商品 |

前三行合计 4 件次是这轮新出现的漏返。Oracle 余下的 3 次漏返均来自“两百多买鼠标”这一查询的三次重复。剩余误返也有聚集现象。DeepSeek 关闭思考的 6 次误返全部出自“两百多买鼠标”和“400以内静音鼠标”，后者的解析遗漏了必须属性“静音”。GLM 有一次把网球拍查询解析为空条件，一次混入 51 件无关商品。下一轮可以据此分别验证偏好与必须项冲突、缺失主体和约价边界。[逐次解析与商品名](../evals/experiments/2026-11-21-reproduction/records/search-replay-20261121.json)

## 复现

在仓库根目录运行以下命令。第一条使用本机保存的 OpenLux 原始记录。后两条只需要仓库内的固定基线与用例。

```powershell
python scripts/replay_search_regression.py --run test-results/selection-openlux-full --output test-results/search-replay-20261121.json
python scripts/run_model_eval.py run --cases evals/search_benchmark/cases --model-config evals/models.search.json --models local-rules,oracle --relations evals/search_benchmark/relations.json --policy evals/selection_policy.search.json --repeats 3 --output test-results/search-verify-new
python scripts/run_model_eval.py compare --baseline evals/baselines/search-v1.2 --current test-results/search-verify-new --output test-results/search-verify-comparison --fail-on-regression
```

按原评分器同时检查解析与检索，本地规则及 Oracle 共 480 条记录中，135 条由失败变为通过，原先通过的全部保留，排名指标与查询改写关系均无退化。另外 40 条原有解析回归中，“非游戏鼠标”一例由失败变为通过，其余评分保持原值。[搜索回归](../evals/experiments/2026-11-21-reproduction/records/search-comparison-20261121/comparison.md) · [解析回归](../evals/experiments/2026-11-21-reproduction/records/parser-comparison-20261121/comparison.md)

运行 `python -m pytest -q backend/tests evals/tests`，436 项测试全部通过。
