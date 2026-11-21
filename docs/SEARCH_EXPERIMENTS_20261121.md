# 搜索实验报告与复现记录（2026-11-21）

| 问题 | 实验报告 |
| --- | --- |
| 搜索规则怎样影响误匹配、漏匹配与偏好排序？ | [机制核查](SEARCH_AUDIT_20261121.md)、[第一轮回归](SMART_SEARCH_REGRESSION_20261121.md)、[第二轮回归](SMART_SEARCH_ROUND2_20261121.md) |
| 模型能否按整句话判断条件并引用用户原话？ | [条件角色回归](SMART_SEARCH_ROLE_REGRESSION_20261121.md)、[逐条解析及结果](../evals/experiments/2026-11-21-search-roles/) |
| 哪个向量模型能找回同义商品？ | [本地三模型对照](../evals/experiments/2026-11-21-local-embeddings/README.md) |
| 服务器能否运行 M3E？大模型排序需要多久？ | [量化、服务器开销、新题命中率和排序耗时](../evals/experiments/2026-11-21-server-embeddings/README.md) |

在服务器实验的 24 条有货新查询中，单独使用 M3E-small INT8 有 18 条首位正确，全部 24 条的前三名包含正确商品。对向量召回的五件商品再调用大模型排序，同轮比较中 DeepSeek Flash 的客户端调用耗时中位数为 3.38 秒，完整清单正确 28/28；GPT-4.1 nano 为 1.60 秒、24/28。调整 nano 提示词后单独复测为 1.29 秒、27/28。28 条查询包含 4 条无货查询，这组开发集成绩不能直接推算线上命中率。[同轮逐条结果](../evals/experiments/2026-11-21-server-embeddings/m3e-latency-trial.json) · [nano 提示词复测](../evals/experiments/2026-11-21-server-embeddings/m3e-nano-check.json)

## 复现

报告中的“当前规则”指实验工作区的版本。相关源文件按仓库相对路径保存在[复现快照](../evals/experiments/2026-11-21-reproduction/source/)。在此 PR 的独立检出目录中，将该目录的内容覆盖到仓库根目录，即可按各报告的命令复现相应工作区。日常应用的源码和部署配置不随本次归档更改。向量权重需按模型报告中的版本另行准备。历史运行的[回放及比较记录](../evals/experiments/2026-11-21-reproduction/records/)可直接查阅。远程排序记录保留返回商品、耗时、错误和 token 计数，省略服务商账户配额等元数据。
