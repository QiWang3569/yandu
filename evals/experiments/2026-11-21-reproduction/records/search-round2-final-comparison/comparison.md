# 燕渡模型评测回归比较

基线：20261121T111836Z-c37358bd；当前：20261121T113535Z-d9e0e9f3。
比较 80 个共有且未修改的用例、480 条结果；新增 0 例，删除 0 例，修改 0 例。
通过转失败 0 条；评分下降 0 条（可与前者重叠）；失败转通过 33 条。提示词变化 0 条；选型规则变化：False。

新增、删除和修改用例单列，不参与共有用例通过率比较。模型配置、评分器与重复次数一致后，才生成本报告。

| 模型 | 任务 | 集合 | 结果数 | 基线通过率 | 当前通过率 |
| --- | --- | --- | ---: | ---: | ---: |
| local-rules | smart_search | dev | 240 | 58.8% | 71.2% |
| oracle | smart_search | dev | 240 | 98.8% | 100.0% |

## 通过转失败

无。

## 评分下降

无。

## 失败转通过

- `search-ambiguity-03`／`local-rules`／第 1 次：0.000 → 1.000
- `search-ambiguity-03`／`local-rules`／第 2 次：0.000 → 1.000
- `search-ambiguity-03`／`local-rules`／第 3 次：0.000 → 1.000
- `search-core-04`／`local-rules`／第 1 次：0.800 → 1.000
- `search-core-04`／`local-rules`／第 2 次：0.800 → 1.000
- `search-core-04`／`local-rules`／第 3 次：0.800 → 1.000
- `search-core-05`／`local-rules`／第 1 次：0.800 → 1.000
- `search-core-05`／`local-rules`／第 2 次：0.800 → 1.000
- `search-core-05`／`local-rules`／第 3 次：0.800 → 1.000
- `search-core-06`／`local-rules`／第 1 次：0.727 → 1.000
- `search-core-06`／`local-rules`／第 2 次：0.727 → 1.000
- `search-core-06`／`local-rules`／第 3 次：0.727 → 1.000
- `search-core-09`／`local-rules`／第 1 次：0.636 → 1.000
- `search-core-09`／`local-rules`／第 2 次：0.636 → 1.000
- `search-core-09`／`local-rules`／第 3 次：0.636 → 1.000
- `search-price-01`／`local-rules`／第 1 次：0.700 → 1.000
- `search-price-01`／`local-rules`／第 2 次：0.700 → 1.000
- `search-price-01`／`local-rules`／第 3 次：0.700 → 1.000
- `search-price-01`／`oracle`／第 1 次：0.800 → 1.000
- `search-price-01`／`oracle`／第 2 次：0.800 → 1.000
- `search-price-01`／`oracle`／第 3 次：0.800 → 1.000
- `search-price-02`／`local-rules`／第 1 次：0.800 → 1.000
- `search-price-02`／`local-rules`／第 2 次：0.800 → 1.000
- `search-price-02`／`local-rules`／第 3 次：0.800 → 1.000
- `search-price-03`／`local-rules`／第 1 次：0.900 → 1.000
- `search-price-03`／`local-rules`／第 2 次：0.900 → 1.000
- `search-price-03`／`local-rules`／第 3 次：0.900 → 1.000
- `search-price-05`／`local-rules`／第 1 次：0.818 → 1.000
- `search-price-05`／`local-rules`／第 2 次：0.818 → 1.000
- `search-price-05`／`local-rules`／第 3 次：0.818 → 1.000
- `search-price-07`／`local-rules`／第 1 次：0.800 → 1.000
- `search-price-07`／`local-rules`／第 2 次：0.800 → 1.000
- `search-price-07`／`local-rules`／第 3 次：0.800 → 1.000

## 新增用例

无。

## 删除用例

无。

## 修改用例

无。

## 排名与关系回归

排名指标下降 0 条，蜕变关系退化 0 条；详细字段见 comparison.json。
