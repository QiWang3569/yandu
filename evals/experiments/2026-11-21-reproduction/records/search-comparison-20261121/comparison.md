# 燕渡模型评测回归比较

基线：20261115T105148Z-80c171dd；当前：20261121T111836Z-c37358bd。
比较 80 个共有且未修改的用例、480 条结果；新增 0 例，删除 0 例，修改 0 例。
通过转失败 0 条；评分下降 0 条（可与前者重叠）；失败转通过 135 条。提示词变化 0 条；选型规则变化：False。

新增、删除和修改用例单列，不参与共有用例通过率比较。模型配置、评分器与重复次数一致后，才生成本报告。

| 模型 | 任务 | 集合 | 结果数 | 基线通过率 | 当前通过率 |
| --- | --- | --- | ---: | ---: | ---: |
| local-rules | smart_search | dev | 240 | 26.2% | 58.8% |
| oracle | smart_search | dev | 240 | 75.0% | 98.8% |

## 通过转失败

无。

## 评分下降

无。

## 失败转通过

- `search-ambiguity-07`／`local-rules`／第 1 次：0.909 → 1.000
- `search-ambiguity-07`／`local-rules`／第 2 次：0.909 → 1.000
- `search-ambiguity-07`／`local-rules`／第 3 次：0.909 → 1.000
- `search-ambiguity-07`／`oracle`／第 1 次：0.909 → 1.000
- `search-ambiguity-07`／`oracle`／第 2 次：0.909 → 1.000
- `search-ambiguity-07`／`oracle`／第 3 次：0.909 → 1.000
- `search-confusable-03`／`local-rules`／第 1 次：0.727 → 1.000
- `search-confusable-03`／`local-rules`／第 2 次：0.727 → 1.000
- `search-confusable-03`／`local-rules`／第 3 次：0.727 → 1.000
- `search-confusable-03-rewrite`／`local-rules`／第 1 次：0.727 → 1.000
- `search-confusable-03-rewrite`／`local-rules`／第 2 次：0.727 → 1.000
- `search-confusable-03-rewrite`／`local-rules`／第 3 次：0.727 → 1.000
- `search-confusable-04`／`local-rules`／第 1 次：0.818 → 1.000
- `search-confusable-04`／`local-rules`／第 2 次：0.818 → 1.000
- `search-confusable-04`／`local-rules`／第 3 次：0.818 → 1.000
- `search-confusable-04`／`oracle`／第 1 次：0.909 → 1.000
- `search-confusable-04`／`oracle`／第 2 次：0.909 → 1.000
- `search-confusable-04`／`oracle`／第 3 次：0.909 → 1.000
- `search-confusable-05`／`local-rules`／第 1 次：0.727 → 1.000
- `search-confusable-05`／`local-rules`／第 2 次：0.727 → 1.000
- `search-confusable-05`／`local-rules`／第 3 次：0.727 → 1.000
- `search-confusable-06`／`local-rules`／第 1 次：0.727 → 1.000
- `search-confusable-06`／`local-rules`／第 2 次：0.727 → 1.000
- `search-confusable-06`／`local-rules`／第 3 次：0.727 → 1.000
- `search-confusable-07`／`local-rules`／第 1 次：0.900 → 1.000
- `search-confusable-07`／`local-rules`／第 2 次：0.900 → 1.000
- `search-confusable-07`／`local-rules`／第 3 次：0.900 → 1.000
- `search-confusable-07`／`oracle`／第 1 次：0.900 → 1.000
- `search-confusable-07`／`oracle`／第 2 次：0.900 → 1.000
- `search-confusable-07`／`oracle`／第 3 次：0.900 → 1.000
- `search-confusable-08`／`local-rules`／第 1 次：0.727 → 1.000
- `search-confusable-08`／`local-rules`／第 2 次：0.727 → 1.000
- `search-confusable-08`／`local-rules`／第 3 次：0.727 → 1.000
- `search-core-01`／`local-rules`／第 1 次：0.909 → 1.000
- `search-core-01`／`local-rules`／第 2 次：0.909 → 1.000
- `search-core-01`／`local-rules`／第 3 次：0.909 → 1.000
- `search-core-01`／`oracle`／第 1 次：0.909 → 1.000
- `search-core-01`／`oracle`／第 2 次：0.909 → 1.000
- `search-core-01`／`oracle`／第 3 次：0.909 → 1.000
- `search-core-01-rewrite`／`local-rules`／第 1 次：0.909 → 1.000
- `search-core-01-rewrite`／`local-rules`／第 2 次：0.909 → 1.000
- `search-core-01-rewrite`／`local-rules`／第 3 次：0.909 → 1.000
- `search-core-01-rewrite`／`oracle`／第 1 次：0.909 → 1.000
- `search-core-01-rewrite`／`oracle`／第 2 次：0.909 → 1.000
- `search-core-01-rewrite`／`oracle`／第 3 次：0.909 → 1.000
- `search-negation-01`／`local-rules`／第 1 次：0.909 → 1.000
- `search-negation-01`／`local-rules`／第 2 次：0.909 → 1.000
- `search-negation-01`／`local-rules`／第 3 次：0.909 → 1.000
- `search-negation-01`／`oracle`／第 1 次：0.909 → 1.000
- `search-negation-01`／`oracle`／第 2 次：0.909 → 1.000
- `search-negation-01`／`oracle`／第 3 次：0.909 → 1.000
- `search-negation-01-rewrite`／`local-rules`／第 1 次：0.909 → 1.000
- `search-negation-01-rewrite`／`local-rules`／第 2 次：0.909 → 1.000
- `search-negation-01-rewrite`／`local-rules`／第 3 次：0.909 → 1.000
- `search-negation-01-rewrite`／`oracle`／第 1 次：0.909 → 1.000
- `search-negation-01-rewrite`／`oracle`／第 2 次：0.909 → 1.000
- `search-negation-01-rewrite`／`oracle`／第 3 次：0.909 → 1.000
- `search-negation-02`／`local-rules`／第 1 次：0.909 → 1.000
- `search-negation-02`／`local-rules`／第 2 次：0.909 → 1.000
- `search-negation-02`／`local-rules`／第 3 次：0.909 → 1.000
- `search-negation-02`／`oracle`／第 1 次：0.909 → 1.000
- `search-negation-02`／`oracle`／第 2 次：0.909 → 1.000
- `search-negation-02`／`oracle`／第 3 次：0.909 → 1.000
- `search-negation-03`／`local-rules`／第 1 次：0.917 → 1.000
- `search-negation-03`／`local-rules`／第 2 次：0.917 → 1.000
- `search-negation-03`／`local-rules`／第 3 次：0.917 → 1.000
- `search-negation-03`／`oracle`／第 1 次：0.917 → 1.000
- `search-negation-03`／`oracle`／第 2 次：0.917 → 1.000
- `search-negation-03`／`oracle`／第 3 次：0.917 → 1.000
- `search-negation-08`／`local-rules`／第 1 次：0.900 → 1.000
- `search-negation-08`／`local-rules`／第 2 次：0.900 → 1.000
- `search-negation-08`／`local-rules`／第 3 次：0.900 → 1.000
- `search-negation-08`／`oracle`／第 1 次：0.900 → 1.000
- `search-negation-08`／`oracle`／第 2 次：0.900 → 1.000
- `search-negation-08`／`oracle`／第 3 次：0.900 → 1.000
- `search-negation-10`／`oracle`／第 1 次：0.900 → 1.000
- `search-negation-10`／`oracle`／第 2 次：0.900 → 1.000
- `search-negation-10`／`oracle`／第 3 次：0.900 → 1.000
- `search-ood-06`／`local-rules`／第 1 次：0.727 → 1.000
- `search-ood-06`／`local-rules`／第 2 次：0.727 → 1.000
- `search-ood-06`／`local-rules`／第 3 次：0.727 → 1.000
- `search-ood-08`／`local-rules`／第 1 次：0.818 → 1.000
- `search-ood-08`／`local-rules`／第 2 次：0.818 → 1.000
- `search-ood-08`／`local-rules`／第 3 次：0.818 → 1.000
- `search-preference-02`／`local-rules`／第 1 次：0.818 → 1.000
- `search-preference-02`／`local-rules`／第 2 次：0.818 → 1.000
- `search-preference-02`／`local-rules`／第 3 次：0.818 → 1.000
- `search-preference-02`／`oracle`／第 1 次：0.909 → 1.000
- `search-preference-02`／`oracle`／第 2 次：0.909 → 1.000
- `search-preference-02`／`oracle`／第 3 次：0.909 → 1.000
- `search-preference-04`／`local-rules`／第 1 次：0.909 → 1.000
- `search-preference-04`／`local-rules`／第 2 次：0.909 → 1.000
- `search-preference-04`／`local-rules`／第 3 次：0.909 → 1.000
- `search-preference-04`／`oracle`／第 1 次：0.909 → 1.000
- `search-preference-04`／`oracle`／第 2 次：0.909 → 1.000
- `search-preference-04`／`oracle`／第 3 次：0.909 → 1.000
- `search-preference-06`／`local-rules`／第 1 次：0.818 → 1.000
- `search-preference-06`／`local-rules`／第 2 次：0.818 → 1.000
- `search-preference-06`／`local-rules`／第 3 次：0.818 → 1.000
- `search-preference-06`／`oracle`／第 1 次：0.909 → 1.000
- `search-preference-06`／`oracle`／第 2 次：0.909 → 1.000
- `search-preference-06`／`oracle`／第 3 次：0.909 → 1.000
- `search-preference-08`／`local-rules`／第 1 次：0.818 → 1.000
- `search-preference-08`／`local-rules`／第 2 次：0.818 → 1.000
- `search-preference-08`／`local-rules`／第 3 次：0.818 → 1.000
- `search-preference-08`／`oracle`／第 1 次：0.909 → 1.000
- `search-preference-08`／`oracle`／第 2 次：0.909 → 1.000
- `search-preference-08`／`oracle`／第 3 次：0.909 → 1.000
- `search-preference-09`／`oracle`／第 1 次：0.900 → 1.000
- `search-preference-09`／`oracle`／第 2 次：0.900 → 1.000
- `search-preference-09`／`oracle`／第 3 次：0.900 → 1.000
- `search-price-02-rewrite`／`local-rules`／第 1 次：0.727 → 1.000
- `search-price-02-rewrite`／`local-rules`／第 2 次：0.727 → 1.000
- `search-price-02-rewrite`／`local-rules`／第 3 次：0.727 → 1.000
- `search-price-06`／`local-rules`／第 1 次：0.727 → 1.000
- `search-price-06`／`local-rules`／第 2 次：0.727 → 1.000
- `search-price-06`／`local-rules`／第 3 次：0.727 → 1.000
- `search-price-08`／`local-rules`／第 1 次：0.909 → 1.000
- `search-price-08`／`local-rules`／第 2 次：0.909 → 1.000
- `search-price-08`／`local-rules`／第 3 次：0.909 → 1.000
- `search-price-08`／`oracle`／第 1 次：0.909 → 1.000
- `search-price-08`／`oracle`／第 2 次：0.909 → 1.000
- `search-price-08`／`oracle`／第 3 次：0.909 → 1.000
- `search-price-08-budget`／`local-rules`／第 1 次：0.909 → 1.000
- `search-price-08-budget`／`local-rules`／第 2 次：0.909 → 1.000
- `search-price-08-budget`／`local-rules`／第 3 次：0.909 → 1.000
- `search-price-08-budget`／`oracle`／第 1 次：0.909 → 1.000
- `search-price-08-budget`／`oracle`／第 2 次：0.909 → 1.000
- `search-price-08-budget`／`oracle`／第 3 次：0.909 → 1.000
- `search-price-08-rewrite`／`local-rules`／第 1 次：0.909 → 1.000
- `search-price-08-rewrite`／`local-rules`／第 2 次：0.909 → 1.000
- `search-price-08-rewrite`／`local-rules`／第 3 次：0.909 → 1.000
- `search-price-08-rewrite`／`oracle`／第 1 次：0.909 → 1.000
- `search-price-08-rewrite`／`oracle`／第 2 次：0.909 → 1.000
- `search-price-08-rewrite`／`oracle`／第 3 次：0.909 → 1.000

## 新增用例

无。

## 删除用例

无。

## 修改用例

无。

## 排名与关系回归

排名指标下降 0 条，蜕变关系退化 0 条；详细字段见 comparison.json。
