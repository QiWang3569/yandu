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

## 2. 七节点覆盖矩阵

| 节点 | 类型 | 正常路径 | 边界 | 错误/异常 | 主要测试文件 |
|---|---|---|---|---|---|
| 1.1 文案提取护栏 | AI | 有 | 有 | 有 | `test_item_drafts.py`、`test_draft_batches.py`、`test_config_services_admin_cli.py` |
| 1.2 视觉识图出稿 | AI | 有 | 有 | 有 | `test_vision.py` |
| 1.3 草稿审核与批量发布 | 程序 | 有 | 有 | 有 | `test_draft_batches.py`、`test_item_drafts.py` |
| 2.1 意图解析 | AI | 有 | 有 | 有 | `test_structured_intent.py`、`test_buyer_agent.py`、`test_wanted_nlp.py`、`test_smart_search_and_admin.py` |
| 2.2 词面检索与排序 | 程序 | 有 | 有 | 有 | `test_wanted_search.py`、`test_smart_search_and_admin.py`、`test_reviews_similar_delete.py`、`test_workflows.py` |
| 2.3 异步代蹲与向量化 | 程序 + Embedding | 有 | 有 | 有 | `test_buyer_agent.py`、`test_workflows.py`、`test_config_services_admin_cli.py` |
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

## 6. 节点 2.1：买家意图解析（AI）

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

## 7. 节点 2.2：词面检索与排序（程序）

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

## 8. 节点 2.3：异步代蹲与向量化（程序 + Embedding）

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

## 9. 节点 2.4：候选精筛与逐字引文护栏（AI）

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

## 10. 横切：评测 harness 与可观测性

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

## 11. 实际运行结果

在冻结代码上执行全量测试（2026-11-23）：

```text
337 passed, 3 warnings in 277.03s
```

- 覆盖：认证、聊天、交易、通知、草稿、视觉、检索、意图解析、异步匹配、评测 harness 与可观测性等全部后端测试；其中 AI 节点的对应用例见第 3–9 节。
- 告警：FastAPI/Starlette 的 `httpx` 弃用提示与 SQLite datetime 适配器弃用提示，均不影响用例结果。
- 测试使用桩与临时数据库，不调用真实模型；真实模型质量结论见 `docs/AI_EVALUATION.md`。

## 12. 覆盖边界与不可声称事项

- 单元测试使用桩替代真实模型，能证明协议、护栏、状态机和降级行为，不能证明真实模型的语义质量；后者由 `docs/AI_EVALUATION.md` 中的标注集指标覆盖。
- `TestClient` 测试属于模块级测试驱动，不等于浏览器端到端测试，也不覆盖真实 SMTP 投递与供应商网络故障的全链路时序。
- 未对真实支付、真实用户数据和第三方邮件服务做测试；这些属于课程外生产集成风险。
