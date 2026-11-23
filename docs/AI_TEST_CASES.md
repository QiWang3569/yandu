# AI 流水线单元测试与测试用例报告

本文档对应课程第 8 次汇报第 3 项要求：对每条 AI 流水线的每个子模块设计并执行单元测试，覆盖正确与错误情况。

## 1. 测试方法

- 测试驱动：`pytest` + FastAPI `TestClient`，与课件中的 test driver 做法一致。
- 模型桩：`httpx.MockTransport` + `monkeypatch` 替换供应商 HTTP 客户端；单元测试不访问真实网络，不使用真实密钥。
- 数据隔离：每个用例使用临时 SQLite 数据库与临时 `data_dir`，不触碰开发数据。
- 断言层次：协议合法性（strict JSON/Schema）、护栏（引文逐字、排除项、偏好不拒绝）、状态机（草稿→发布、任务暂停/恢复/重试）、权限与脱敏。
- 真实模型输出质量不在此处断言，而由 `backend/eval` 的人工标注数据集与指标评测衡量（见 `docs/AI_EVALUATION.md`）。

运行方式（仓库根目录）：

```bash
./.venv/Scripts/python.exe -m pytest backend/tests -q
```

## 2. 八节点覆盖矩阵

| 节点 | 类型 | 正常路径 | 边界 | 错误/异常 | 主要测试文件 |
|---|---|---|---|---|---|
| 1.1 文案提取护栏 | AI | 有 | 有 | 有 | `test_item_drafts.py`、`test_draft_batches.py`、`test_config_services_admin_cli.py` |
| 1.2 视觉识图出稿 | AI | 有 | 有 | 有 | `test_vision.py` |
| 1.3 草稿审核与批量发布 | 程序 | 有 | 有 | 有 | `test_draft_batches.py`、`test_item_drafts.py` |
| 1.4 概念族学习 | AI + 程序护栏 | 有 | 有 | 有 | `test_concepts.py` |
| 2.1 意图解析 | AI | 有 | 有 | 有 | `test_structured_intent.py`、`test_buyer_agent.py`、`test_wanted_nlp.py`、`test_smart_search_and_admin.py` |
| 2.2 词面检索与排序 | 程序 | 有 | 有 | 有 | `test_wanted_search.py`、`test_smart_search_and_admin.py`、`test_reviews_similar_delete.py`、`test_workflows.py`、`test_concepts.py` |
| 2.3 异步代蹲与向量化 | 程序 + Embedding | 有 | 有 | 有 | `test_buyer_agent.py`、`test_workflows.py`、`test_config_services_admin_cli.py`、`test_concepts.py` |
| 2.4 候选精筛与引文护栏 | AI | 有 | 有 | 有 | `test_buyer_agent.py`、`test_workflows.py` |

## 3. 节点 1.1：卖家文案提取护栏（AI）

生产入口：`POST /api/v1/item-drafts/import`（`services.parse_item`，远程失败时回退本地规则）。

| 类型 | 输入/触发 | 预期结果 | 用例 |
|---|---|---|---|
| 正常 | 两行“出罗技静音鼠标 50 元，万柳面交 / 出九成新高数教材 20 元，燕园面交” | 生成 2 条草稿，价格解析正确，未进入公开搜索 | `test_item_drafts.py::test_imported_items_remain_private_until_owner_reviews_and_publishes` |
| 正常 | 远程模型返回合法字段 | 使用远程结果；不可用时回退本地解析且不报 500 | `test_config_services_admin_cli.py::test_parse_item_remote_success_and_local_fallback` |
| 边界 | 10 行上限、过短行“坏” | 422，错误定位到“第 2 件”，不产生半成品草稿 | `test_item_drafts.py::test_import_checks_line_limit_and_preserves_existing_drafts_on_error` |
| 边界 | 空列表、11 件、负价、非法分类/校区/成色、超长标签、缺图片字段、缺原文 | 全部 422，草稿表保持为空 | `test_draft_batches.py::test_import_validates_all_fields[items0..8]` |
| 错误 | 草稿容量已满（50 条） | 409，整批拒绝，不部分写入 | `test_draft_batches.py::test_import_capacity_atomic` |
| 错误 | 未登录、伪造 Origin、引用他人图片 | 401/403/422，草稿不落库 | `test_draft_batches.py::test_import_auth_origin_and_foreign_photos` |
| 错误 | 买家读取/修改卖家草稿 | 列表为空、修改返回 404 | `test_item_drafts.py::test_imported_items_remain_private_until_owner_reviews_and_publishes` |

## 4. 节点 1.2：卖家视觉识图出稿（AI）

生产入口：`POST /api/v1/vision/draft`（`VisionService`，结构化 `VisionDraft`，缓存键含提示词版本）。

| 类型 | 输入/触发 | 预期结果 | 用例 |
|---|---|---|---|
| 正常 | 卖家上传本人图片 | 返回草稿，不自动发布；相同图命中缓存 | `test_vision.py::test_owner_only_no_publish_and_cache` |
| 正常 | 备注变化、缓存过期、限流窗口 | 重新生成或按限流返回，不返回旧备注结果 | `test_vision.py::test_rate_limit_cache_and_changed_note` |
| 边界 | 模型返回 `unclear` / `multiple_items` | 不得填充可发布草稿 | `test_vision.py::test_unclear_results_cannot_fill[unclear/multiple_items]` |
| 边界 | 并发相同请求 | in-flight 去重，只调用一次模型 | `test_vision.py::test_inflight_deduplication_and_concurrency` |
| 错误 | 空图、URL、路径穿越、超量、非法格式（7 组） | 422/400，拒绝读取越权文件 | `test_vision.py::test_reject_invalid_input[images0..6]` |
| 错误 | 损坏图片 | 4xx，不写缓存 | `test_vision.py::test_corrupt_photo` |
| 错误 | 供应商返回非 JSON、截断、非法分类、超长标签、错误类型 | 拒绝并脱敏，不落缓存 | `test_vision.py::test_bad_provider_output[...]` |
| 错误 | 429/503 | 有限次退避重试后成功或明确失败 | `test_vision.py::test_transient_retry[429/503]` |
| 错误 | 供应商错误体包含凭据 | 响应与日志不含密钥，错误不缓存 | `test_vision.py::test_error_sanitized_not_cached` |
| 错误 | 非法 envelope（空 choices、非对象等） | 502/503 类失败，不静默降级 | `test_vision.py::test_invalid_provider_envelope[body0..3]` |
| 错误 | 调用超时 | 释放并发槽，可再次重试 | `test_vision.py::test_timeout_frees_slot_and_retry_possible` |
| 错误 | 配置缺模型/URL/key、复用文本 key | 启动校验失败，禁止跨用途复用凭据 | `test_vision.py::test_vision_config_validation`、`test_vision_does_not_reuse_text_key` |

## 5. 节点 1.3：草稿审核与批量发布（程序）

| 类型 | 输入/触发 | 预期结果 | 用例 |
|---|---|---|---|
| 正常 | 视觉导入→人工核对→批量发布 | 只有 ACTIVE 商品；重放幂等，不自动设封面 | `test_draft_batches.py::test_reviewed_import_private_idempotent_and_no_automatic_cover` |
| 正常 | 单条草稿编辑后发布（含图片） | 201 发布，草稿消失，重复发布 404 | `test_item_drafts.py::test_imported_items_remain_private_until_owner_reviews_and_publishes` |
| 正常 | 无图发布 | 允许发布，`images` 为空 | `test_item_drafts.py::test_draft_can_be_published_without_photos` |
| 边界 | 两件中第二件缺价格 | 整批 422，定位“第 2 件”，不发布第一件 | `test_draft_batches.py::test_missing_price_prevents_entire_batch` |
| 边界 | 编辑与嵌入并发 | 发布前复核 `updated_at`，旧版本拒绝且不覆盖 | `test_draft_batches.py::test_edit_during_embedding_rechecked_and_preserved`、`test_stale_draft_rejected_before_publication` |
| 错误 | 批量发布重复/重试、部分失败 | 原子成功或全部回滚；重试不产生重复商品 | `test_draft_batches.py::test_batch_publish_atomic_and_retries_never_duplicate` |
| 错误 | 未登录、伪造 Origin、他人草稿、重复 ID | 401/403/409/422，商品数不变 | `test_draft_batches.py::test_publish_auth_duplicates_and_owner` |
| 错误 | 入队失败 | 全部商品回滚，不留半发布状态 | `test_draft_batches.py::test_enqueue_failure_rolls_back_all_items` |
| 错误 | 批量模型输出字段非法/数量不符 | 整批拒绝，草稿保留可修正 | `test_draft_batches.py::test_batch_model_invalid_fields_rejected[change0..3]`、`test_batch_model_excess_or_empty_results` |

## 6. 节点 1.4：概念族学习（AI + 程序护栏）

生产入口：`POST /api/v1/items/` 或 `/api/v1/item-drafts/publish-batch` 提交后，`ConceptRunner` 异步调用 `concept_learning.propose`；提议经 `validate`/`apply_proposal` 校验后写入 `concepts`、`concept_aliases`、`item_concepts` 与 `concept_proposals`。

| 类型 | 输入/触发 | 预期结果 | 用例 |
|---|---|---|---|
| 正常 | 模型提议“笔记本，父类电脑，别名笔记本/macbook” | 两个概念与父子关系落库；商品链接到笔记本；审计状态 APPLIED | `test_concepts.py::test_model_learning_persists_family_hierarchy_and_links` |
| 正常 | 第二件商品复用已有 concept_id 并补充 thinkpad 别名 | 不重复建族；两件商品都链接到同一概念；别名可查 | `test_concepts.py::test_existing_family_is_reused_across_items` |
| 正常 | 查询“电脑” | 经数据库目录向下展开到笔记本；查询期不调用模型 | `test_concepts.py::test_model_learning_persists_family_hierarchy_and_links`、`test_query_time_never_calls_the_model` |
| 边界 | 鼠标与鼠标垫分别学习 | 鼠标垫不并入鼠标族；列表与智能搜索都不把垫子算作鼠标 | `test_concepts.py::test_learned_accessory_does_not_join_product_family` |
| 边界 | 远程队列 | 仅远程模式入队；重复入队不产生重复任务 | `test_concepts.py::test_enqueue_only_in_remote_mode` |
| 边界 | 本地模式 | 不运行学习；旧字面别名表只在 `AI_MODE=local` 生效 | `test_concepts.py::test_legacy_table_is_used_only_for_local_mode` |
| 错误 | 证据不是商品原文 | 拒绝整份提议，审计记录 fabricated_evidence，概念表不变 | `test_concepts.py::test_fabricated_evidence_is_rejected_and_audited` |
| 错误 | 别名已被其他概念占用 / 未知 concept_id | 分别以 alias_conflict、unknown_concept 拒绝并审计 | `test_concepts.py::test_alias_conflict_and_unknown_concept_are_rejected` |
| 错误 | 把“静音”等属性词当作别名 | 拒绝，属性不能成为概念族 | `test_concepts.py::test_attribute_and_forbidden_alias_are_rejected` |
| 错误 | 目录被写坏形成父类环 | 校验发现 cycle，阻止继续学习 | `test_concepts.py::test_catalog_cycle_blocks_further_learning` |
| 错误 | 父类层级超过上限 | 校验发现 depth，拒绝继续加深目录 | `test_concepts.py::test_catalog_depth_limit_blocks_runaway_hierarchy` |
| 错误 | 模型不可用或供应商失败 | 任务回到 PENDING 并退避，3 次后 FAILED；商品保持 ACTIVE | `test_concepts.py::test_learning_failure_keeps_item_published_and_retries` |
| 正常 | 桩模型返回合法提议经完整队列 | 任务 DONE；商品-概念链接写入 | `test_concepts.py::test_runner_applies_stubbed_proposal` |
| 回归 | 2.3 本地逐条审查 | 使用学习得到的别名；“笔记本”需求命中 MacBook | `test_concepts.py::test_async_matching_uses_learned_aliases` |

## 7. 节点 2.1：买家意图解析（AI）

生产入口：`POST /api/v1/intents/parse`（`services.parse_intent_with_quotes`，内部 `StructuredIntent` 扁平化为公开 `ParsedIntent`）。

| 类型 | 输入/触发 | 预期结果 | 用例 |
|---|---|---|---|
| 正常 | “万柳附近 300 内静音鼠标”等 4 组 | 预算/校区/成色正确，不臆造约束 | `test_workflows.py::test_parser_extracts_budget_campus_condition_without_inventing_constraints` |
| 正常 | required/preferred/excluded 与逐字 quote | 正确扁平化为 keywords/preferences/excluded_keywords | `test_structured_intent.py::test_structured_roles_flatten_to_public_intent` |
| 正常 | 本地模式 | 否定/偏好/约束分离；不产生引文 | `test_buyer_agent.py::test_local_parser_separates_negation_preferences_and_constraints`、`test_structured_intent.py::test_local_mode_returns_no_quotes` |
| 边界 | 引文非原文（改写/拼接） | 丢弃该引文，字段仍可用 | `test_structured_intent.py::test_non_verbatim_quotes_are_dropped` |
| 边界 | “九成新以上”“全新或九五新都行” | 归一化为 9成新 / 95新，引文保留原文 | `test_structured_intent.py::test_condition_phrases_are_normalized` |
| 边界 | 非法枚举、负价格 | 分类/校区回到默认，价格置空 | `test_structured_intent.py::test_invalid_enums_and_negative_price_are_sanitized` |
| 边界 | 同一词出现在 required 与 excluded/preferred | 去重后只保留 required，公共校验不报错 | `test_structured_intent.py::test_duplicate_terms_never_break_public_validation` |
| 边界 | 矛盾需求，进入 clarification | 冲突片段通过 `clarification_quotes` 逐字保留 | `test_structured_intent.py::test_clarification_quotes_keep_conflicting_spans_verbatim` |
| 边界 | 输入过短、未登录 | 422 / 401 | `test_wanted_nlp.py::test_wanted_parse_rejects_short_input`、`test_wanted_parse_requires_login` |
| 错误 | 模型返回坏 JSON / 非法结构 / 空 choices | 502，响应不含密钥 | `test_structured_intent.py::test_invalid_provider_shape_is_sanitized_502`、`test_buyer_agent.py::test_invalid_provider_responses_are_sanitized_502[None..4]` |
| 错误 | 远程不可用 | 即时搜索回退本地解析而非 500 | `test_smart_search_and_admin.py::test_smart_search_falls_back_to_local_parser_when_remote_unavailable` |
| 错误 | 用户确认后创建意图 | 只使用确认字段，不重新解析原句 | `test_buyer_agent.py::test_remote_parser_and_worker_use_single_chat_key_and_confirmed_fields` |
| 回归 | 公开 API 形状 | 仍为 `ParsedIntent` 字段集合，无新增列 | `test_structured_intent.py::test_parse_api_shape_is_unchanged` |

## 8. 节点 2.2：词面检索与排序（程序）

| 类型 | 输入/触发 | 预期结果 | 用例 |
|---|---|---|---|
| 正常 | 预算+分类即时搜索 | 返回符合商品 | `test_smart_search_and_admin.py::test_smart_search_parses_budget_category_and_returns_matching_item` |
| 正常 | 四种排序、输入校验 | 推荐/最新/价格升降序均有效；非法参数 422 | `test_smart_search_and_admin.py::test_smart_search_validates_input_and_supports_all_sorts` |
| 正常 | “300 左右” | 解析为区间而非硬上限 | `test_smart_search_and_admin.py::test_smart_search_detects_around_price` |
| 边界 | 标题/描述命中、大小写、`%`/`_` 字面量 | 通配符不被解释为模式 | `test_wanted_search.py::test_search_title_description_case_and_literal_wildcards` |
| 边界 | 多个空格分隔词跨标题与描述 | 全部词命中才返回 | `test_wanted_search.py::test_search_uses_all_whitespace_separated_terms_across_title_and_description` |
| 边界 | 超量结果 | 先过滤下架/他人，再截断数量 | `test_wanted_search.py::test_search_filters_before_result_limit_and_hides_inactive` |
| 边界 | 相似推荐 | 按同分类/标签/价格排序 | `test_reviews_similar_delete.py::test_similar_items_rank_shared_category_tags_and_price` |
| 错误 | 访问他人收藏/私密数据 | 按所有权规则隐藏 | `test_wanted_search.py::test_search_preserves_my_wanted_access_rules` |
| 错误 | 未知商品相似推荐 | 404 | `test_reviews_similar_delete.py::test_similar_items_rejects_unknown_item` |
| 错误 | 预算/校区/成色/自我排除硬过滤 | 不匹配项不进入候选，预算外商品不因偏好放行 | `test_workflows.py::test_hard_filters_budget_campus_condition_and_self_exclusion` |
| 正常 | 概念层级展开 | “电脑”命中学习到父类为电脑的笔记本；“笔记本”不反向命中父类 | `test_concepts.py::test_model_learning_persists_family_hierarchy_and_links` |
| 正常 | 发布后物化商品-概念链接 | `item_concepts` 写入学习到的概念，查询走链接表 | `test_concepts.py::test_model_learning_persists_family_hierarchy_and_links`、`test_runner_applies_stubbed_proposal` |
| 边界 | 产品与配件隔离 | 鼠标不召回鼠标垫；列表与智能搜索同样生效 | `test_concepts.py::test_learned_accessory_does_not_join_product_family` |
| 边界 | 整词匹配 | 规范化后按词序列匹配，子串不误命中 | `test_concepts.py::test_learned_accessory_does_not_join_product_family`、`test_legacy_table_is_used_only_for_local_mode` |
| 回归 | 查询期零模型调用 | 学习完成后，列表与智能搜索只读目录快照 | `test_concepts.py::test_query_time_never_calls_the_model` |

## 9. 节点 2.3：异步代蹲与向量化（程序 + Embedding）

| 类型 | 输入/触发 | 预期结果 | 用例 |
|---|---|---|---|
| 正常 | 新商品触发匹配，重复通知去重 | 每个 intent×item 只通知一次 | `test_workflows.py::test_intent_first_search_and_new_item_match_with_dedup` |
| 正常 | 超过 5 个代蹲任务 | 全部可运行；暂停/恢复/结束有效 | `test_workflows.py::test_more_than_five_tasks_can_run_and_pause_resume_end_still_work` |
| 边界 | 商品保留/售出/暂停/完成任务 | 保留仍可匹配；售出/暂停/完成不通知 | `test_workflows.py::test_old_items_stay_available_but_reserved_and_sold_do_not_match`、`test_buyer_agent.py::test_provider_work_holds_no_write_lock_and_revalidates_before_notify[sold/pause/completed]` |
| 边界 | 暂停中的 intent | 暂停不匹配，旧 ACTIVE intent 继续匹配 | `test_workflows.py::test_paused_intents_stop_matching_while_old_active_intents_keep_matching` |
| 边界 | 服务重启 | 未完成任务自动恢复，不丢通知 | `test_buyer_agent.py::test_unfinished_job_resumes_on_restart`、`test_existing_database_is_upgraded_without_losing_notifications` |
| 错误 | 模型调用 5xx/429 | 最多重试后标记失败，任务可重试且按所有者隔离 | `test_buyer_agent.py::test_transient_provider_failure_retries_automatically_and_new_item_triggers_job`、`test_failed_jobs_remain_saved_can_retry_and_are_owner_scoped` |
| 错误 | 嵌入返回 null/2 维/布尔向量 | 拒绝保存，不产生半成品 intent 或任务 | `test_buyer_agent.py::test_invalid_embeddings_do_not_save_half_finished_intent[None/2维/bool]` |
| 错误 | 远程 embedding 坏载荷 | 校验维度与有限值并脱敏 | `test_config_services_admin_cli.py::test_embed_remote_returns_vector_and_sanitizes_bad_payload` |
| 错误 | 管理员隐藏/恢复商品 | 恢复后补触发匹配 | `test_buyer_agent.py::test_admin_restore_triggers_matching_for_task_created_while_hidden` |
| 正常 | 本地逐条审查使用学习得到的别名 | “笔记本”需求对 MacBook 命中并给出原文证据 | `test_concepts.py::test_async_matching_uses_learned_aliases` |

## 10. 节点 2.4：候选精筛与逐字引文护栏（AI）

| 类型 | 输入/触发 | 预期结果 | 用例 |
|---|---|---|---|
| 正常 | 偏好不满足但硬条件满足 | 判 MATCH，偏好不单独拒绝 | `test_buyer_agent.py::test_preferences_do_not_filter_and_exclusions_are_not_positive_requirements` |
| 正常 | 网球拍 vs 羽毛球拍 | 类别不同判 NO_MATCH；撤销后通知隐藏 | `test_buyer_agent.py::test_tennis_wish_does_not_match_badminton_and_revoked_match_is_hidden` |
| 正常 | 通知归属 | 只能看到自己代蹲的通知 | `test_buyer_agent.py::test_notifications_are_scoped_to_owned_wish` |
| 边界 | 关键词缺证据 | MATCH 降级为 UNCERTAIN 并生成向卖家确认的问题 | `test_buyer_agent.py::test_missing_hard_evidence_becomes_uncertain` |
| 边界 | 排除项未出现在商品文本 | 不影响 MATCH | `test_buyer_agent.py::test_absent_exclusion_does_not_block_match` |
| 错误 | 排除词出现在 MATCH 商品文本 | 拒绝该 MATCH | `test_buyer_agent.py::test_exclusion_present_in_text_cannot_be_match` |
| 错误 | 未知 ID、重复、缺失、编造引文、偏好拒绝、截断 | 整批拒绝，不保存半成品 | `test_buyer_agent.py::test_semantic_review_rejects_ungrounded_or_incomplete_batches[unknown_id/duplicate/missing/fabricated_quote/preference_rejection/truncated]` |
| 错误 | 硬特征被用户明确否定 | 本地规则也不会生成 MATCH | `test_buyer_agent.py::test_explicit_negative_required_feature_never_creates_local_match` |

## 11. 横切：评测 harness 与可观测性

| 类型 | 触发 | 预期结果 | 用例 |
|---|---|---|---|
| 正常 | 指标公式 | F1、Recall@k、分位数、引文接地、成本按已知输入输出正确 | `test_eval_metrics.py`（9 条） |
| 边界 | 数据集结构缺字段、缺图片 | 校验报错并指出行/ID | `test_eval_cli.py::test_validate_rows_reports_structural_errors`、`test_validate_rows_requires_vision_files` |
| 错误 | 数据集被篡改 | SHA 校验失败，真实运行拒绝执行 | `test_eval_cli.py::test_manifest_freeze_detects_tampering`、`test_real_run_refuses_when_manifest_does_not_match` |
| 错误 | 未传 `--real` | 拒绝调用供应商 | `test_eval_cli.py::test_real_run_requires_explicit_flag` |
| 错误 | 缺少凭据 | 标记 `UNAVAILABLE`，不伪造结果 | `test_eval_cli.py::test_check_models_marks_missing_credentials_unavailable` |
| 错误 | 配置写入字面密钥 | 测试失败 | `test_eval_cli.py::test_models_config_contains_no_literal_secrets` |
| 错误 | fixture 或未校验报告冒充最终结果 | `verify` 拒绝 | `test_eval_cli.py::test_fixture_report_cannot_be_verified_as_final`、`test_unverified_report_rejected` |
| 回归 | 观测回调可选 | 不传回调时返回结果不变；传入时收到 usage/耗时；失败事件不含密钥 | `test_buyer_agent.py::test_observability_callback_is_optional_and_reports_usage` |

## 12. 实际运行结果

### 12.1 每模块 5 正确 + 5 错误样例

判定约定：`判定=正确` 表示实际行为与预期一致；“错误样例”的预期本身是拒绝、回退或降级，只要按预期被处理即为正确，不代表模型判对。所有用例均在桩模型/临时数据库下执行，不访问真实网络。

每模块 5 条正确 + 5 条错误，共 50 条。T11-C3~C5、T11-W3~W5、T21-W4~W5 为本轮新增用例。

**1.1 文案提取**

| 类型 | 样例 ID | pytest nodeid | 输入/触发 | 预期结果 | 实际结果 | 判定 |
|---|---|---|---|---|---|---|
| 正确 1 | T11-C1 | `test_config_services_admin_cli.py::test_parse_item_local_extracts_every_field` | `静音无线鼠标，¥280，万柳学区，九五新` | 本地解析六个字段全部正确 | title=静音无线鼠标、category=数码与影音、price=280、campus=万柳学区、condition=95新、tags=[鼠标,静音,无线] | 正确 |
| 正确 2 | T11-C2 | `test_config_services_admin_cli.py::test_parse_item_remote_success_and_local_fallback` | 远程合法 JSON；供应商 down | 远程字段被采用；不可用回退本地 | 远程 price=100；provider down 时回退 price=300 | 正确 |
| 正确 3 | T11-C3 | `test_config_services_admin_cli.py::test_parse_item_local_reads_chinese_price_condition_and_campus` | `台灯，售价120元，昌平新校区，八成新` | 中文价格/校区/成色正确抽取 | price=120、campus=昌平新校区、condition=8成新 | 正确 |
| 正确 4 | T11-C4 | `test_config_services_admin_cli.py::test_parse_item_remote_accepts_numeric_price_and_eight_tags` | 远程 JSON：price=35（数字）、campus=医学部、condition=9成新、8 个 tags | 数字价格与满额标签被接受 | price=35、campus=医学部、condition=9成新、tags 8 项 | 正确 |
| 正确 5 | T11-C5 | `test_config_services_admin_cli.py::test_parse_item_remote_keeps_a_full_length_description` | 远程 JSON：description 3000 字、price="199.99" | 长度上限内完整保留 | len(description)=3000、price=199.99 | 正确 |
| 错误 1 | T11-W1 | `test_config_services_admin_cli.py::test_parse_item_invalid_remote_fields_fall_back_to_local` | 远程返回非法分类/负价/火星校区/十成新 | 整体回退本地，不抛 500 | 回退后 price=300、campus=燕园校本部 | 正确（按预期回退） |
| 错误 2 | T11-W2 | `test_config_services_admin_cli.py::test_parse_item_blank_or_punctuation_input_does_not_crash` | `，。！？ ` | 不崩溃，字段留空 | title=None、price=None、tags=[]，无异常 | 正确（按预期降级） |
| 错误 3 | T11-W3 | `test_config_services_admin_cli.py::test_parse_item_remote_non_object_payload_falls_back` | 远程返回 `["not","an","object"]` | 非对象载荷回退本地 | 回退后 price=300 | 正确（按预期回退） |
| 错误 4 | T11-W4 | `test_config_services_admin_cli.py::test_parse_item_remote_out_of_range_price_falls_back` | 远程 price=1000000（超出 999999） | 校验失败回退本地 | 回退后 price=250 | 正确（按预期回退） |
| 错误 5 | T11-W5 | `test_config_services_admin_cli.py::test_parse_item_remote_unknown_field_falls_back` | 远程 JSON 多出 `seller_phone` 字段 | `extra='forbid'` 触发回退 | 回退后 price=280 | 正确（按预期回退） |

**1.2 视觉识图**

| 类型 | 样例 ID | pytest nodeid | 输入/触发 | 预期结果 | 实际结果 | 判定 |
|---|---|---|---|---|---|---|
| 正确 1 | T12-C1 | `test_vision.py::test_owner_only_no_publish_and_cache` | 1 张本人图片 + note | 返回草稿不发布、重复请求命中缓存、他人 404 | 200；商品数不变；第二次 0 次调用；他人 404 | 正确 |
| 正确 2 | T12-C2 | `test_vision.py::test_two_photos_share_one_request` | 2 张图片 | 合并为一次请求 | 200、请求数 1、消息含 2 个 image_url | 正确 |
| 正确 3 | T12-C3 | `test_vision.py::test_transient_retry[429]` | 供应商先 429 后成功 | 重试一次并成功 | 200、请求数 2 | 正确 |
| 正确 4 | T12-C4 | `test_vision.py::test_rate_limit_cache_and_changed_note` | 每小时限额 1，同一 payload 两次后改 note | 同 payload 命中缓存，改 note 触发 429 | 200、200、429；供应商仅 1 次调用 | 正确 |
| 正确 5 | T12-C5 | `test_vision.py::test_inflight_deduplication_and_concurrency` | 同用户同图并发 + 第 5 个并发 | 同键去重，超限 429，结束后释放 | 重复请求共享结果；4 次调用；pending 清空 | 正确 |
| 错误 1 | T12-W1 | `test_vision.py::test_bad_provider_output[not json-stop]` | 供应商返回非 JSON | 502 且脱敏 | 502，响应不含 test-secret | 正确（按预期拒绝） |
| 错误 2 | T12-W2 | `test_vision.py::test_invalid_provider_envelope[body1]` | 供应商返回 `{"choices": []}` | 502 | 502 | 正确（按预期拒绝） |
| 错误 3 | T12-W3 | `test_vision.py::test_corrupt_photo` | 上传文件内容不是图片 | 422，且不调用供应商 | 422、0 次调用 | 正确（按预期拒绝） |
| 错误 4 | T12-W4 | `test_vision.py::test_ready_without_any_evidence_degrades_to_unclear` | provider 返回 ready 但全字段为空 | 降级 unclear 并补问题 | status=unclear、title=None、uncertainties 非空 | 正确（按预期降级） |
| 错误 5 | T12-W5 | `test_vision.py::test_error_sanitized_not_cached` | 供应商 401 且错误信息含密钥 | 502 脱敏、失败不缓存、重试可成功 | 502 无密钥；下一次 200；共 2 次调用 | 正确（按预期拒绝） |

**2.1 意图解析**

| 类型 | 样例 ID | pytest nodeid | 输入/触发 | 预期结果 | 实际结果 | 判定 |
|---|---|---|---|---|---|---|
| 正确 1 | T21-C1 | `test_structured_intent.py::test_structured_roles_flatten_to_public_intent` | 含 required/preferred/excluded 的完整 JSON | 三角色扁平化、逐字 quotes 保留 | keywords=[鼠标,无线]、excluded=[游戏鼠标]、preferences=[静音]；quotes 6 条 | 正确 |
| 正确 2 | T21-C2 | `test_structured_intent.py::test_conditions_are_deduplicated_and_capped_at_twelve` | 15 项条件（含 1 条重复） | 去重并截断到 12 项 | keywords=前 12 项；quotes 14 条去重 | 正确 |
| 正确 3 | T21-C3 | `test_structured_intent.py::test_non_verbatim_quotes_are_dropped` | budget_quote=三百元（原文为 300） | 非逐字引文被丢弃 | max_price=300；quotes=万柳、无线鼠标 | 正确 |
| 正确 4 | T21-C4 | `test_structured_intent.py::test_condition_phrases_are_normalized` | 九成新以上；全新或九五新都行 | 归一为 9成新 / 95新 | condition=9成新、95新；quote=九成新 | 正确 |
| 正确 5 | T21-C5 | `test_structured_intent.py::test_invalid_enums_and_negative_price_are_sanitized` | category=不存在、campus=火星、max_price=-50 | 非法枚举与负价清空 | category=None、campus=不限校区、max_price=None | 正确 |
| 错误 1 | T21-W1 | `test_structured_intent.py::test_blank_query_local_parse_does_not_crash` | `，。！？ ` | 本地解析不崩溃 | keywords=[]、quotes=[]、clarification 非空 | 正确（按预期降级） |
| 错误 2 | T21-W2 | `test_structured_intent.py::test_model_unavailable_is_sanitized_502` | 供应商不可用 | 502 脱敏 | HTTPException 502，detail 不含供应商信息 | 正确（按预期拒绝） |
| 错误 3 | T21-W3 | `test_structured_intent.py::test_invalid_provider_shape_is_sanitized_502` | `{"conditions": "not-a-list"}` | 502 且不含凭据 | 502，响应不含 test-credential | 正确（按预期拒绝） |
| 错误 4 | T21-W4 | `test_structured_intent.py::test_non_object_payload_is_sanitized_502` | 供应商返回 `["不是对象"]` | 502 | 502 | 正确（按预期拒绝） |
| 错误 5 | T21-W5 | `test_structured_intent.py::test_malformed_price_is_sanitized_502` | max_price="很贵" | 502 且回显不泄露原文 | 502，detail 不含“很贵” | 正确（按预期拒绝） |

**2.4 候选精筛**

| 类型 | 样例 ID | pytest nodeid | 输入/触发 | 预期结果 | 实际结果 | 判定 |
|---|---|---|---|---|---|---|
| 正确 1 | T24-C1 | `test_buyer_agent.py::test_absent_exclusion_does_not_block_match` | 排除项“游戏鼠标”未出现在商品文本 | 仍判 grounded MATCH | verdict=MATCH，证据 criterion=鼠标 | 正确 |
| 正确 2 | T24-C2 | `test_buyer_agent.py::test_empty_candidates_skip_provider` | 空候选列表 | 直接返回 []，不调供应商 | 返回 []，无网络调用 | 正确 |
| 正确 3 | T24-C3 | `test_buyer_agent.py::test_preferences_do_not_filter_and_exclusions_are_not_positive_requirements` | 需求偏好静音；候选含普通鼠标/游戏鼠标/非游戏鼠标 | 偏好缺失仍 MATCH 并生成问题；排除项不误收 | MATCH + 静音问题；游戏鼠标不通知、非游戏鼠标通知 | 正确 |
| 正确 4 | T24-C4 | `test_buyer_agent.py::test_missing_hard_evidence_becomes_uncertain` | 需求 required 含静音，候选仅“无线鼠标” | 降级 UNCERTAIN 并生成静音问题 | verdict=UNCERTAIN，questions 含静音 | 正确（按预期降级） |
| 正确 5 | T24-C5 | `test_buyer_agent.py::test_notifications_are_scoped_to_owned_wish` | 买家两条代蹲；卖家访问买家 intent | 通知按 intent 归属隔离，越权 404 | 本 intent 通知齐全；其他 intent 为空；卖家 404 | 正确 |
| 错误 1 | T24-W1 | `test_buyer_agent.py::test_assessment_rejects_criterion_outside_intent_whitelist` | evidence.criterion=静音，不在 intent 白名单 | ValueError | 抛出 ValueError（Ungrounded evidence） | 正确（按预期拒绝） |
| 错误 2 | T24-W2 | `test_buyer_agent.py::test_uncertain_assessment_requires_a_question` | UNCERTAIN 且 questions 为空 | ValueError | 抛出 ValueError（requires a question） | 正确（按预期拒绝） |
| 错误 3 | T24-W3 | `test_buyer_agent.py::test_semantic_review_rejects_ungrounded_or_incomplete_batches[fabricated_quote]` | evidence.quote 编造“全新未拆，保修一年” | 整批拒绝 ModelUnavailable | 抛出 ModelUnavailable | 正确（按预期拒绝） |
| 错误 4 | T24-W4 | `test_buyer_agent.py::test_exclusion_present_in_text_cannot_be_match` | 排除词“游戏鼠标”出现在候选文本却判 MATCH | 拒绝该 MATCH | 抛出 ModelUnavailable | 正确（按预期拒绝） |
| 错误 5 | T24-W5 | `test_buyer_agent.py::test_invalid_provider_responses_are_sanitized_502[None]` | 供应商响应为 None | 502 脱敏 | 502，响应不含 test-credential | 正确（按预期拒绝） |

**1.4 概念族学习**

| 类型 | 样例 ID | pytest nodeid | 输入/触发 | 预期结果 | 实际结果 | 判定 |
|---|---|---|---|---|---|---|
| 正确 1 | T14-C1 | `test_concepts.py::test_existing_family_is_reused_across_items` | 第二件商品挂到已有“笔记本” | 复用 concept_id，不重复建族 | 概念仍为 2 个；thinkpad 别名写入；链接存在 | 正确 |
| 正确 2 | T14-C2 | `test_concepts.py::test_empty_assignments_are_applied_as_no_family` | assignments=[] | APPLIED/no_family | 概念数 0；审计 APPLIED + no_family | 正确 |
| 正确 3 | T14-C3 | `test_concepts.py::test_model_learning_persists_family_hierarchy_and_links` | MacBook Air，提议“笔记本”父类“电脑” | 建族、父子关系、别名与链接持久化 | 概念={笔记本,电脑}；父子关系成立；搜索可命中 | 正确 |
| 正确 4 | T14-C4 | `test_concepts.py::test_learned_accessory_does_not_join_product_family` | 鼠标与鼠标垫分别学族 | 鼠标垫不并入“鼠标”族 | 搜“鼠标”不含鼠标垫；智能搜索同样排除 | 正确 |
| 正确 5 | T14-C5 | `test_concepts.py::test_async_matching_uses_learned_aliases` | 学习“笔记本”别名后匹配 MacBook | 使用别名判 MATCH 并给原文证据 | verdict=MATCH，quote=MacBook Air M1 | 正确 |
| 错误 1 | T14-W1 | `test_concepts.py::test_non_object_payload_is_rejected_as_invalid_schema` | payload 为 `["not","an","object"]` | REJECTED/invalid_schema 并审计 | Rejected(invalid_schema)；审计同因 | 正确（按预期拒绝） |
| 错误 2 | T14-W2 | `test_concepts.py::test_alias_outside_item_text_is_rejected` | 别名 thinkpad 不在商品原文 | ungrounded_alias | Rejected(ungrounded_alias)；审计同因 | 正确（按预期拒绝） |
| 错误 3 | T14-W3 | `test_concepts.py::test_fabricated_evidence_is_rejected_and_audited` | evidence=“这是一台游戏本”不在原文 | fabricated_evidence，且不落库 | Rejected(fabricated_evidence)；概念数为 0 | 正确（按预期拒绝） |
| 错误 4 | T14-W4 | `test_concepts.py::test_alias_conflict_and_unknown_concept_are_rejected` | 别名 macbook 已被占用；concept_id=missing | alias_conflict / unknown_concept | 两次拒绝原因正确；概念数仍为 2 | 正确（按预期拒绝） |
| 错误 5 | T14-W5 | `test_concepts.py::test_attribute_and_forbidden_alias_are_rejected` | 把属性词“静音”当别名 | forbidden_alias | Rejected(forbidden_alias) | 正确（按预期拒绝） |

每模块统计（50 个样例全部通过，无失败样例）：

| 模块 | 正确样例通过数 | 错误样例按预期处理数 | 未通过样例 |
|---|---:|---:|---|
| 1.1 文案提取 | 5/5 | 5/5 | 无 |
| 1.2 视觉识图 | 5/5 | 5/5 | 无 |
| 2.1 意图解析 | 5/5 | 5/5 | 无 |
| 2.4 候选精筛 | 5/5 | 5/5 | 无 |
| 1.4 概念族学习 | 5/5 | 5/5 | 无 |
| 合计 | 25/25 | 25/25 | 0 |

### 12.2 全量测试统计

在冻结代码上执行全量测试（2026-11-23）：

```text
377 tests collected
377 passed, 3 warnings in 161.48s
```

- 数据量：30 个测试文件、377 个用例，覆盖认证、聊天、交易、通知、草稿、视觉、概念学习、检索、意图解析、异步匹配、评测 harness 与可观测性；其中 AI 节点的对应用例见第 3–10 节，逐例选出的 50 个代表用例见 12.1。
- 结果：`passed=377`、`failed=0`、`skipped=0`；本轮新增用例覆盖 1.4 评测适配、多候选 checks、逐例判定，以及 12.1 中 1.1/2.1 补充的 8 条样例（其余模块直接复用既有用例）。
- 告警：FastAPI/Starlette 的 `httpx` 弃用提示与 SQLite datetime 适配器弃用提示，均不影响用例结果。
- 测试使用桩与临时数据库，不调用真实模型；真实模型质量结论见 `docs/AI_EVALUATION.md`。

## 13. 覆盖边界与不可声称事项

- 单元测试使用桩替代真实模型，能证明协议、护栏、状态机和降级行为，不能证明真实模型的语义质量；后者由 `docs/AI_EVALUATION.md` 中的标注集指标覆盖。
- `TestClient` 测试属于模块级测试驱动，不等于浏览器端到端测试，也不覆盖真实 SMTP 投递与供应商网络故障的全链路时序。
- 未对真实支付、真实用户数据和第三方邮件服务做测试；这些属于课程外生产集成风险。
