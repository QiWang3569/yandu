# 公开商品数据与图片测评接入

`scripts/import_public_eval.py` 支持 TaoDescribe 商品文案和 Products-10K 图片索引，分为抽样、补标、生成用例三步。生成的用例直接进入原有 `validate/list/run/compare` 流程。数据与图片保存在被 Git 忽略的 `data/`，模型返回与报告保存在 `test-results/`，不随代码再分发原始数据。

## 商品文案

支持天池原始两列 TSV（标题、文案），或 [KOBE](https://github.com/THUDM/KOBE) 作者发布的逐行对齐 `.title` / `.desc`。不要将 `content_tag` 的用户分布当作商品属性。

```powershell
python scripts/import_public_eval.py taodescribe --tsv data/item_desc_dataset.txt --count 8 --seed 20261115 --source-url https://tianchi.aliyun.com/dataset/9717 --source-version downloaded-20261115 --output data/public-eval/text-v1
```

作者处理版用法：

```powershell
python scripts/import_public_eval.py taodescribe --titles data/public-eval/raw/taodescribe-test.title --descriptions data/public-eval/raw/taodescribe-test.desc --count 8 --seed 20261115 --source-url https://github.com/THUDM/KOBE --source-version KOBE-v2-saved.zip-test-20261115 --output data/public-eval/text-v1
```

导入器拒绝两文件行数不等；超出业务 3000 字上限或空内容会被排除并计数，不截断后冒充原文。按规范化标题分组，每组取一条，以固定 seed 的 SHA256 排序抽样。`samples.json` 记录源文件 SHA256、行号、样本内容哈希和抽样规则。

## Products-10K

输入 CSV 必须有 `name,class`，可带 `group`；`name` 是图片根目录下的相对路径，`class` 是 SKU。将已获取图片及其对应索引放入本地后执行：

```powershell
python scripts/import_public_eval.py products10k --csv data/public-eval/raw/products10k.csv --images-root data/public-eval/raw/products10k --count 8 --seed 20261115 --source-url https://huggingface.co/datasets/nyris/products10k-v1 --source-version YOUR_EXACT_REVISION --output data/public-eval/images-v1
```

每个 SKU 只抽一张；图片以内容哈希命名复制至样本包 `images/`。导入时拒绝缺失、无法解码和超过线上图片限制的文件，不用另一张图静默替换失败样本。SKU 只用于追溯和分组，不能自动转换为燕渡的六类答案。

原始数据入口与许可见[调研报告](PUBLIC_DATASET_REVIEW.md)。本轮使用 nyris 的 Products-10K v1 重打包版本，保留原图片路径和 SKU；具体 revision、行号与图像哈希见[样本清单](../evals/samples/public-pilot-manifest.json)。该发布版本与原竞赛划分有差别，报告不将其视为原排行榜复现。

## 补标与生成用例

抽样产生 `samples.json` 和 `annotations.json`，不会自动生成标准答案。在后者逐例填写：

- `expected`：适用于任务的标准答案。
- `rationale`、`annotator`：判定依据和标注者。
- `label_status`：预标注使用 `draft`；团队复核后才改为 `reviewed`。
- `split`、`enabled`：开发／保留集与是否执行。

原文没有价格时可断言 `price: null`；校区、成色的业务默认值不是来源事实，若不评判应从 `expected.fields` 省略。文本 title、description 的事实完整性仍需人工核对。

图片标准答案示例（用于说明格式，并非原数据标签）：

```json
{
  "fields": {"status": "ready", "category": "数码与影音"},
  "required_mentions": [["鼠标", "滑鼠"], ["黑色", "黑"]],
  "forbidden_mentions": ["功能正常", "全新", "售价"],
  "uncertainty_required": false
}
```

`status/category` 必须声明；类别未知可为 null。每组 `required_mentions` 是一个事实的可接受表述，在标题、描述、标签合并文本中做大小写与空白归一化后的包含匹配。`forbidden_mentions` 是指定词组检查，不是完整的幻觉检测器；否定表达和同义词可能影响匹配，必须人工复核。`uncertainty_required` 可省略。

```powershell
python scripts/import_public_eval.py build --package data/public-eval/images-v1
python scripts/run_model_eval.py validate --cases data/public-eval/images-v1/cases --assets-root data/public-eval/images-v1
```

`build` 拒绝未补标或样本被改动的输入，保存标注与样本哈希。输出目录须为空；修改已有样本或标注时创建新版本目录。停用已有用例可改 JSON 的 `enabled`；新增时使用新 ID，并保留同商品 `family`。同一 SKU 的不同图应保持相同 family，不能同时进入 dev/holdout；校验器另检查完全相同图片跨集合泄漏。

## 运行与回归

为 `vision-a` 设置环境变量 `EVAL_VISION_MODEL`、`EVAL_VISION_BASE_URL`、`EVAL_VISION_API_KEY`。基础地址须为 HTTPS，包含服务商要求的版本路径；程序追加 `/chat/completions`。密钥不写进 JSON、报告或 Git。文本模型继续使用 `text-a/text-b` 的现有变量。

```powershell
python scripts/run_model_eval.py run --cases data/public-eval/images-v1/cases --assets-root data/public-eval/images-v1 --models vision-a --repeats 1 --max-requests 16 --allow-remote --output test-results/images-v1
python scripts/run_model_eval.py run --cases data/public-eval/text-v1/cases --models text-a --max-requests 16 --allow-remote --output test-results/text-v1
```

图片任务复用 `backend/app/vision.py` 的预处理、提示词、用户消息构造和 `VisionDraft` 校验，以多模态 `image_url` 发送实际图片字节。评测直接调用模型边界，每次独立请求，不经过业务的五分钟缓存。图片文件须匹配用例声明的 SHA256，任一缺失／变更图片都会在整轮付费调用前被拒绝。文件路径相对 `--assets-root`，不接受 URL 或越界路径。

当前实现覆盖单件商品草稿，包括 1–3 张图片输入及 `ready/unclear/multiple_items` 状态；批量拆成多个草稿的 `VisionBatch` 另需任务和评分设计。自动报告含整例通过率、类别／状态准确率、原始／应用输出、错误、延迟、usage 和已知费用；失败也计入类别和状态指标的分母。未配置价格时费用保持未知。

回归使用相同样本包、模型配置和评分器版本，在新空目录重跑后执行：

```powershell
python scripts/run_model_eval.py compare --baseline test-results/images-v1 --current test-results/images-v2 --output test-results/images-regression --fail-on-regression
```

图片首轮使用评分器 1.1.0；加入搜索评测后，当前评分器为 1.2.0，CI 使用 `evals/baselines/local-rules-v1.2` 和 `evals/baselines/search-v1.2`，旧版结果保留。默认 CI 运行框架测试、48 条原有用例及 80 条搜索用例校验和离线回归；不下载公开大数据包，也不调用付费接口。不同评分器版本的结果不能直接做回归比较，重跑公开数据时应建立 1.2 基线。图片小样本目前均为 draft/dev，选型策略没有新增已确认的视觉门槛，因此报告不产生正式模型推荐。
