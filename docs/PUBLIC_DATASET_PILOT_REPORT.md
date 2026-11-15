# 公开商品数据抽样测评

2026-11-15，商品文案与 Products-10K 各完成 8 例真实接口调用。文本分类、价格断言通过 8/8；图片整例通过 6/8，两条失败均来自业务分类。16 次请求全部返回有效结构，无重试、无回退。

| 数据／任务 | 模型与服务 | 通过 | 结构有效 | P50 | P95 |
| --- | --- | ---: | ---: | ---: | ---: |
| TaoDescribe 商品文案／`item_parse` | `deepseek-chat`，DeepSeek 官方接口 | 8/8 | 8/8 | 1.64 秒 | 1.97 秒 |
| Products-10K／`vision_draft` | `qwen3-vl-plus`，OpenLux 转发接口 | 6/8 | 8/8 | 8.53 秒 | 18.22 秒 |

本轮使用现有可用接口验证接入链路，每个任务只运行一个模型。上述通过率来自预标注开发集，不能据此确定优选模型；费用未配置，报告保留 usage，费用显示未知。

## 样本与评分

商品文案来自 [KOBE 作者发布包](https://github.com/THUDM/KOBE)的 TaoDescribe 测试部分：`saved/raw/test.title` 与 `test.desc`。作者 Google Drive 包 ID 为 `1NOhv8pvC8IGwt8oRoIZ-A0EojJBZcolr`。逐行对齐后按规范化标题分组，以 seed `20261115` 的 SHA256 排序，从 1462 个标题分组抽出 8 例；它们恰好都是服饰、鞋或手表。标准答案只断言 `category=美妆服饰与周边`、`price=null`，不评价校区、成色默认值或生成文案的事实完整性。这轮的 8/8 说明这两个字段跑通，尚未检验跨类别解析能力。

图片使用 [nyris/products10k-v1](https://huggingface.co/datasets/nyris/products10k-v1) 的重打包版本，revision 为 `c3a10717605bab88bc195deb987d3d3ffd072698`。先用固定 seed 从 train 的 141931 行抽出 8 行，再建立保留原文件名与 SKU 的本地索引；8 张图片属于 8 个 SKU。包括外套、空调、电视、电饭煲、药油、玩具巴士、粉底液和牙刷。该版本的划分与原竞赛不同，本轮只将其作为图像素材。

图片任务沿用线上预处理、提示词和 `VisionDraft` 结构，断言状态、六类业务分类及可见物品名称／颜色等词组，并检查指定的无依据成色、校区、价格用语。8 张图片的预标注状态均为 `ready`；状态准确率为 8/8，类别准确率为 6/8，可见事实词组检查全部通过。`unclear`、`multiple_items` 和多图输入仍需补充真实样本。

所有标准答案由 Codex 在模型调用前依据原文或图片预标注，保留 `draft/dev`，待团队复核。词组匹配无法判断全部描述是否准确，也可能受同义词和否定表达影响。平均断言得分 97.7% 包含多项“禁用词未出现”检查，因此本报告用整例通过率 75% 表示图片试跑结果。

## 两条图片失败

| 图片／用例 | 预标注类别 | 模型类别 | 判定依据 |
| --- | --- | --- | --- |
| `78863.jpg`／`products10k-3e0c072d347985719aaf` | `null` | 宿舍生活与家电 | 图中为活络油，当前六类没有明确对应类，应保留未知；模型识别出了药油，但强行归类。 |
| `92175.jpg`／`products10k-7607f257dadd06ef4e22` | 美妆服饰与周边 | 校园出行与运动 | 主体为积木玩具巴士，预标注按“周边”归类；模型描述已识别为积木模型，却按真实交通工具归类。团队需确认玩具的类别约定。 |

先复核这两条业务分类约定，再扩展类别覆盖、模糊图片、多件物品和多图输入。人工复核后的独立保留集、至少两个候选模型的同题对照及预先确认的视觉门槛，才用于正式选型。

## 重跑与记录

抽样清单、源文件哈希、图像哈希、标准答案及运行摘要见 [public-pilot-manifest.json](../evals/samples/public-pilot-manifest.json)。原始文案与图片保存在本地 `data/public-eval/`，不随代码分发；从干净检出开始时，先按[接入说明](PUBLIC_DATASET_INTEGRATION.md)获取数据、抽样和生成用例。

复用本机已生成的两个样本包，可在设置相应密钥环境变量后运行下列命令；输出目录须为空。配置文件中的 `YUNWU_GEMINI_API_KEY` 沿用本机密钥变量名，视觉请求实际使用的是 `qwen3-vl-plus`。

```powershell
python scripts/run_model_eval.py run --cases data/public-eval/taodescribe-pilot/cases --model-config evals/models.public-pilot.json --models deepseek-pilot --max-requests 8 --allow-remote --output test-results/public-pilot-text-v2
python scripts/run_model_eval.py run --cases data/public-eval/products10k-pilot/cases --assets-root data/public-eval/products10k-pilot --model-config evals/models.public-pilot.json --models qwen-vl-pilot --max-requests 8 --allow-remote --output test-results/public-pilot-vision-v2
```

当前评分器已升级为 1.2.0，上述 `v2` 运行作为新基线；首次 1.1.0 结果继续保留，不能跨评分版本比较。将图片运行命令的输出改为 `test-results/public-pilot-vision-v3` 再次执行后，可比较：

```powershell
python scripts/run_model_eval.py compare --baseline test-results/public-pilot-vision-v2 --current test-results/public-pilot-vision-v3 --output test-results/public-pilot-vision-comparison --fail-on-regression
```

首次文本运行 ID：`20261115T093543Z-d01f8aaf`；图片运行 ID：`20261115T093544Z-146de110`。评分器为 `1.1.0`，每例一次，temperature 为 `0.1`。完整记录分别位于 [文本报告](../test-results/public-pilot-text/report.md)和[图片报告](../test-results/public-pilot-vision/report.md)所在目录，含逐例输入快照、原始／应用输出、耗时、usage 和评分。

首次运行记录的实现哈希为 `c3a9d8021f1bfd7afa94dd6ab1c87e82c0a72fd5a777e611aa8c1bf6f2cb5dff`。试跑后补充了视觉响应结束状态校验和 TSV 列数校验，新增行为通过自动化测试验证；上述真实调用结果保留首次运行版本，未覆盖重写。

验证结果：后端 297 项、评测框架 109 项测试通过；默认 48 例及两个公开样本包校验通过；40 例本地规则回归无通过率或评分退化。评分器升级后 CI 使用 `evals/baselines/local-rules-v1.1`，旧基线保留。
