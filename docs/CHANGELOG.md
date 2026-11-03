# 修改日志（边改边记录）

> 记录本项目在本地开发调试期间的代码与文档变更，便于回溯。最后更新：2026-11-03。
> 说明：`software_architecture.html` / `software_architecture_simple.html` 是既有本地文件，不在此次修改范围内。

## 2026-11-03：按 open issue 评估并补齐评价、相似推荐与删除

- 交易评价：新增 `trade_reviews` 表与三个接口，成交确认后买卖双方可互评（1–5 星、标签、文字），商品详情与个人主页展示评分。详见 [Issue 评估记录](ISSUE_TRIAGE_20261103.md)。
- 相似推荐：新增 `GET /api/v1/items/{id}/similar`，按分类、共同标签、校区、成色和价格接近度排序，商品详情展示「相似好物」。
- 删除会话：`DELETE /api/v1/conversations/{id}` 支持从自己的列表移除会话，对方新消息会自动恢复；交易进行中禁止移除。
- 管理员面板：新增 `GET /api/v1/admin/summary` 待办统计与审核页签角标；公告支持删除；商品举报默认只看待处理，可切换回看历史。
- 聊天窗口：去掉 650px 高度上限，按可视高度铺满；手机端与深色布局同步验证。
- 已核对 #62 监控埋点与 #57 识图发布均已实现；#55 微信通知、#48/#15/#14/#10 等非代码 issue 未改动，理由见评估记录。
- 验证：后端 295 项测试通过，前端 TypeScript 与 Vite 构建通过；Chrome 无头浏览器覆盖桌面/手机聊天、评价弹窗、相似好物与管理员角标。

## 2026-10-23：发布求购支持自然语言

- 发布求购新增“智能识别并填充”：一句话描述即可自动补全标题、分类、预算和校区，识别结果可编辑，确认后发布；发布后仍自动关联代蹲。
- 后端新增 `POST /api/v1/wanted/parse`，复用需求解析（本地规则或远程模型），解析失败时回退本地规则；新增 `ParsedWanted` 校验与 4 项测试。
- 前端 `WantedForm` 改为受控表单并接入解析入口；TypeScript 检查与 Vite 构建通过，完整后端 287 项测试通过（覆盖率 94%）。

## 2026-10-23：识图发布（待部署，默认关闭）

- 批量导入页新增合照识图，每次 1–3 张合照拆成最多 10 张候选卡片，支持人工编辑、删除及合并套装后保存私人草稿；保留原文字导入。
- 待发布列表增加勾选和确认后批量发布，校验全部商品信息与草稿版本，事务保证整批提交，操作回执避免重试重复创建。合照不自动裁切或关联封面，可在草稿中补充单件照片。
- 新增 25 项批量测试，完整后端 283 项测试及前端构建通过；浏览器完成编辑、合并、补图和两件商品实际批量发布，七牛完成三本书合照、重复照片及空白图的小样验证。
- 发布、编辑及草稿上传区新增“识图发布”，从最多 9 张照片中选择 1–3 张，支持补充说明、编辑建议和逐项应用；保留手动输入，换图废弃旧结果。
- 新增独立视觉接口与七牛配置，验证图片归属，限制请求频率和并发，支持短时缓存、超时及一次临时错误重试；不自动填写价格、成色或校区。
- 后端回归、41 项识图测试及前端构建通过；浏览器验证九图上传、三图识别、编辑保护、换图取消、失败恢复、发布及手机/深色布局。修复九图上传栏撑宽发布窗口的问题。
- 真实七牛接口完成服务模块的小样复测，仍有无依据属性与虚构封面误拒识，需要人工核对。详见[实现与验证说明](VISION_ASSISTED_PUBLISHING.md)。
- 本地 `.env` 补上 `VISION_*` 配置并开启识图（沿用七牛密钥）；完整后端 283 项测试通过、整体行覆盖率 94%，前端类型检查与生产构建通过，README 徽章与「测试与覆盖率」同步为 283 通过 / 94%。

## 2026-10-23：通知已读与商品图片查看（待部署）

- 统一服务端未读计数；公告分页、展开全文后已读、铃铛移除已读公告并保留历史；已售反馈区分已读与待处理。
- 同步标签页阅读状态，丢弃过时计数响应；聊天提醒直接打开对应会话，仅确认取回的消息 ID。
- 商品图片支持放大、九图切换、缩放和手机手势，关闭查看器保留商品详情。
- 后端 217 项回归、前端构建及隔离浏览器验证通过，详见 [更新与验证说明](NOTIFICATIONS_AND_GALLERY.md)。
- 完成识图辅助发布调研；后续实现、模型实测与限制见[识图发布说明](VISION_ASSISTED_PUBLISHING.md)。

## 2026-10-21（合并 codex/market-usability-auth）

- 站内意见反馈：新增 `backend/app/feedback.py` 与 `frontend/src/Feedback.tsx`，支持提交问题与截图、我的反馈、管理员回复与状态流转，结果通过站内通知送达；新增 `feedbacks`、`feedback_replies`、`feedback_attachments`、`feedback_notices` 四张表与 `docs/FEEDBACK.md`。
- 商品发布、编辑与草稿的图片上限由 3 张提升到 9 张，并校验不重复；首页采用更紧凑的布局。
- 登录会话改为闲置 7 天过期、最长 30 天：新增 `POST /api/v1/auth/refresh` 供前台续期，后台轮询不续期，退出或重置密码撤销会话；登录页面过期后保留已填写表单。
- 公告已读改为「仅把实际展示的公告标为已读」：`POST /api/v1/announcements/mark-read` 现在接收 `ids` 列表。

## 2026-10-22

- 对话页支持卖家取消已确认的预订：卖家在 `RESERVED` 状态下点击「取消预订」，会话变为已取消、商品恢复在售并重新触发匹配。
- 修复访客统计：排除爬虫与健康检查请求，对浏览器首次请求去重，匿名访客按 15 分钟滚动窗口计数。
- 新增商业指标看板与 GMV / 动销率 / 停留时长指标：`frontend/src/AdminMetrics.tsx`；后端新增 `GET /api/v1/admin/analytics/user-growth`、`/visitor-funnel`、`/business-overview` 与 `POST /api/v1/analytics/dwell`，并新增 `PageDwellLog` 表。
- 商品卡片标签全部展示并自动换行（`frontend/src/App.tsx` / `styles.css`）。

## 2026-10-16

- 指标：新增 `yandu_active_users` 与 `yandu_active_sessions` 自定义业务指标，导出到 `/metrics`。

## 2026-10-15

- 监控与可观测性：接入 `prometheus-fastapi-instrumentator`，新增 `prometheus.yml` 与 `compose.preview.yaml`（Prometheus + Grafana），应用暴露 `/metrics`。
- 邮件提醒：新注册账号默认开启未读站内信提醒，并一次性开启现有 32 个注册用户；用户可自行关闭，应用重启与重复迁移不覆盖个人选择。
- 统一商品与求购的搜索栏，移除求购页重复输入框；搜索关键词标签移至「只看在售」之后。
- 部署：`compose.preview.yaml` 的环境变量与健康检查对齐服务器生产配置。

## 2026-10-14

- 整合本地交易保护、商品撤回、成交后复制草稿、统一搜索及注册邮箱未读提醒；以 zzx 的持续有效和共享需求规则为准。图片邮件仅显示提示，私有图片仍在站内查看；兼容迁移旧本地求购关联，细节见 [整合说明](FOLLOWUP_FEATURES.md)。

- 发布求购自动关联代蹲，新增从私密代蹲发布到求购看板、编辑代蹲条件与从“我的求购”查看匹配记录的入口。需求、暂停、恢复及完成状态互通，已有真实求购启动时补建关联。
- 取消商品、求购和代蹲的自动有效期及 5 个活跃代蹲限制；商品照片、求购描述/分类/预算改为可选，无图商品显示明确占位。
- 站内消息支持纯图片与图文消息、预览移除、点击查看、受权限保护的图片读取，以及图片消息举报和隐藏。
- 数据库加入需求关联和聊天附件，支持已有 SQLite/PostgreSQL 数据升级；前端保留上一轮深绿夜间配色。

## 2026-10-04

- 切到 `main` 分支，并重新构建前端、启动本地服务（http://127.0.0.1:8000）。
- 新增文档 `docs/TEST_CHECKLIST.md`（第一版功能测试清单）。

## 2026-10-05

- 清理本地构建缓存：`__pycache__`、`*.pyc`、`frontend/dist`、`tsconfig.tsbuildinfo`、日志/pid；保留 `data/` 与 `.env`。
- 修复前端入口缓存问题：`backend/app/main.py` 的 SPA 兜底路由为 `index.html` 增加 `Cache-Control: no-store` 响应头。
- 重写 `docs/TEST_CHECKLIST.md`：改为 A 功能回归 / B 体验 / C 待改进三部分，并确立 `[√]`=通过、`[x]`=未通过、`[ ]`=未测试 的标记约定。
- 记录 UI 问题 C6（对比区域宽度）、C13（搜索框黑框）到清单。

## 2026-10-06

- 新增自动化测试脚本 `scripts/api_test.py`（接口回归，74 条）。
- 新增补充边角用例脚本 `scripts/api_test2.py`（22 条）。
- 新增结果报告 `docs/api_test_results.md`（累计 95 通过 / 0 失败 / 1 环境受限）。
- 修复对比托盘随商品数变宽的问题：`frontend/src/styles.css` 中 `.compare-tray` 由 `max-width` 改为固定 `width`，移动端改为 `left/right:12px + width:auto`。
- 实现「铃铛聚合所有新消息 + 反馈已售通知卖家」：
  - `backend/app/main.py`：新增 `GET /api/v1/sale-feedback/my`，返回卖家名下待处理的“反馈已售”列表。
  - `frontend/src/api.ts`：新增 `SaleFeedbackNotice` 类型。
  - `frontend/src/App.tsx`：铃铛未读数聚合“匹配未读 + 聊天未读 + 反馈已售数”；通知弹窗分区展示站内新消息 / 买家反馈已售 / 代蹲匹配；抽取 `renderNotice` 复用通知卡片。
  - `frontend/src/styles.css`：新增 `.notice-center`、`.notice-group`、`.notice-group-title` 样式。
- 修复站内消息输入框被顶下去的问题：`frontend/src/styles.css` 中 `.chat-thread` 增加 `min-height:0`，头部/交易栏/举报栏/输入框设为 `flex-shrink:0`，消息区独立滚动，输入框固定可见。
- 已售商品排到最后：`backend/app/main.py` 的 `/api/v1/items/` 排序前置 `(Item.status == 'SOLD')`，非售出商品在前、`SOLD` 商品始终排在末尾。

## 2026-10-07

- 已售商品支持恢复售卖：
  - `backend/app/main.py`：`/api/v1/items/{id}/status` 允许 `SOLD → ACTIVE`（仅 `BANNED` 仍禁止卖家操作），并刷新 14 天有效期、重新触发匹配。
  - `frontend/src/App.tsx`：卖家商品详情中，`SOLD` 商品显示“恢复售卖”按钮；`SOLD` 状态下隐藏“标记已售出”。
- 交易动作（申请预订/确认预订/拒绝/取消/售出/确认收货）会生成一条站内消息，通知到对方：
  - `backend/app/main.py`：`change_deal` 在状态流转成功后写入一条 `ChatMessage`（如“我已申请预订，请确认”），并更新会话的 `last_message_at`，使对方在站内消息与铃铛（聊天未读）中都能看到。
- 优化咨询草稿操作（对应 C3）：
  - `frontend/src/App.tsx`：删除“复制草稿”按钮；“去站内消息”改为“复制并去站内消息”（复制 + 预填草稿并跳转站内消息）；“关闭草稿”移到最右。
- 商品详情操作按钮调整：
  - `frontend/src/App.tsx`：非卖家详情页按钮顺序调整为「反馈已售 → 收藏 → 生成咨询草稿 → 联系卖家」；“关闭草稿”改为 `button secondary`；草稿说明文字 `flex:1` 使两按钮靠拢。
- 咨询草稿改为只在站内消息生成：
  - `frontend/src/App.tsx`：删除商品详情里的“咨询草稿”按钮与草稿弹层（`draft`/`draftOpen`/`draftRef` 及相关 JSX 一并移除）。
  - `frontend/src/AccountAndChat.tsx`：站内消息在“新会话”（`newItem`）时于输入框上方显示“咨询草稿”按钮，调用 `/items/{id}/message-draft` 生成并预填到输入框。
  - `frontend/src/styles.css`：新增 `.chat-draft-tool` 样式。
- 头像下拉菜单：
  - `frontend/src/App.tsx`：点击右侧头像弹出菜单（查看个人主页 / 编辑资料 / 账号设置），支持点击外部关闭。
  - `frontend/src/Profile.tsx`：新增 `autoEdit`/`onAutoEditConsumed`，支持从菜单直接打开“编辑个人资料”弹窗。
  - `frontend/src/styles.css`：新增 `.avatar-menu-wrap`、`.avatar-menu`、`.avatar-menu-item` 样式。
- 隐形滚动条：`frontend/src/styles.css` 对 `.chat-list`、`.chat-history`、`.modal` 隐藏滚动条（`scrollbar-width:none` + `::-webkit-scrollbar{display:none}`），保留滚动能力。
- 侧边栏底部：去掉“本地演示 · 校园邮箱认证”文案，改为“联系我们”邮件链接（`mailto:pkuyandu@163.com`）。
  - `frontend/src/App.tsx`：侧边栏底部改为 `Mail` 图标 + “联系我们：pkuyandu@163.com”链接。
  - `frontend/src/styles.css`：`.sidebar-caption` 增加 `text-decoration:none`。
- 优化“联系我们”排版并去掉底部演示文案：
  - `frontend/src/App.tsx`：侧边栏“联系我们”改为图标 + 两行（“联系我们”标题 + 邮箱小字）；主页面 `footer` 删除“演示环境 · 数据仅保存在本地”。
  - `frontend/src/styles.css`：用 `.sidebar-contact` 替换 `.sidebar-caption`，新增图标/标题/邮箱/悬停样式。
- 对比弹窗宽度自适应（对应 C6）：
  - `frontend/src/components.tsx`：`Modal` 增加 `style` 透传。
  - `frontend/src/App.tsx`：对比弹窗改为 `min(860px, 对比数*280+60px)`，2 件更窄、3 件稍宽。
- 对比托盘恢复自适应并右对齐操作按钮（对应 C6）：
  - `frontend/src/styles.css`：`.compare-tray` 由固定 `width` 改回 `max-width`（随商品数增长），移动端改为 `max-width:none`。
  - `frontend/src/App.tsx`：“比较一下”按钮加 `margin-left:auto`，与“清空对比（×）”一起靠右。
- 对比托盘按钮组紧凑化：
  - `frontend/src/App.tsx`：把“比较一下”和“清空对比（×）”包进 `.compare-actions`。
  - `frontend/src/styles.css`：`.compare-actions` 用 `gap:8px`，去掉 `margin-left:auto`，让“已选几件好物”与“比较一下/×”保持紧凑相邻，托盘初始宽度收缩到内容宽度。
- 对比托盘改为纵向布局，收缩到最短宽度：
  - `frontend/src/App.tsx`：托盘拆成 `.compare-tray-top`（标签 + 操作按钮）与 `.compare-selection`（商品标签）两行。
  - `frontend/src/styles.css`：`.compare-tray` 改 `flex-direction:column`；`.compare-actions` 加 `margin-left:auto` 靠右；`.compare-selection` 去掉 `flex:1 1 100%`（不再撑宽托盘）。
- 对比托盘版式微调（最终状态）：
  - “已选几件好物”与“比较一下”间距为 `22px`；“比较一下”与“×”保持 `8px` 并一起靠右；托盘右侧内边距缩到 `10px`（“×”更贴近右缘）。
- 修复搜索回车后的大黑框（对应 C13）：
  - `frontend/src/styles.css`：给 `.market-section:focus / :focus-visible` 加 `outline:none`，去掉回车后聚焦商品结果区时浏览器默认的黑框轮廓。
- 新增“人员招募”分类、只看在售筛选、搜索条变窄：
  - `backend/app/schemas.py`：`CATEGORIES` 增加“人员招募”。
  - `backend/app/services.py`：`CATEGORY_FEATURES` 增加“招募/招聘/兼职/实习/组队/志愿者/找人”。
  - `frontend/src/App.tsx`：分类标签增加“人员招募”（`Users` 图标）；筛选区“只看正在出售的好物”改为下拉“只看在售 / 所有好物”。
  - `backend/app/main.py`：`/api/v1/items/` 增加 `on_sale` 参数，`on_sale=false` 时展示全部状态（含已售/过期）。
  - `frontend/src/styles.css`：`.global-search` 宽度 380→300px。
- 顶栏与搜索宽度定稿：`.topbar` 高度 90→80px；`.global-search` 宽度恢复为 380px。
- 系统公告与更新通知：
  - `backend/app/models.py`：新增 `Announcement` 表（title/body/kind/active/created_at）。
  - `backend/app/schemas.py`：新增 `AnnouncementCreate` / `AnnouncementUpdate`。
  - `backend/app/main.py`：新增 `GET /api/v1/announcements`（公开）与 `POST/PATCH /api/v1/admin/announcements`（管理员后台发布/下线）。
  - `backend/app/services.py`：演示种子新增两条公告。
  - `frontend/src/api.ts`：新增 `Announcement` 类型。
  - `frontend/src/App.tsx`：侧边栏新增“公告”入口；新增公告弹窗；铃铛通知中心新增“公告与更新”分区。
  - `frontend/src/styles.css`：新增公告卡片样式。
- 公告入口改名“系统公告”，清空演示公告数据；新增发布说明文档 `docs/ANNOUNCEMENTS.md`。
- 发布商品支持智能识别填充（类似代蹲解析）：
  - `backend/app/schemas.py`：新增 `ItemParseRequest` / `ParsedItem`。
  - `backend/app/services.py`：新增 `parse_item` / `parse_item_local`（本地启发式 + 远程模型）。
  - `backend/app/main.py`：新增 `POST /api/v1/items/parse`。
  - `frontend/src/api.ts`：新增 `ParsedItem` 类型。
  - `frontend/src/forms.tsx`：发布表单增加“智能识别并填充”，并把表单字段改为受控状态。
- 商品识别在远程模型不可用时回退到本地启发式解析（不再返回 502）。
- 定位远程模型不可用原因：此前服务进程在沙箱内启动，外网被限制（Windows socket 10013）。改为非沙箱启动后，DeepSeek 远程解析/精筛恢复正常（`/intents/parse`、`/items/parse` 均返回 200）。
- 我的主页与编辑能力补全：
  - `backend/app/schemas.py`：新增 `ItemUpdate` / `WantedUpdate`。
  - `backend/app/main.py`：新增 `PATCH /api/v1/items/{id}`（卖家编辑在售商品）、`PATCH /api/v1/wanted/{id}`（编辑自己的求购）；`GET /api/v1/wanted/` 增加 `mine=true`；`/items/` 的 `on_sale` 对 mine/favorites 也生效；`/users/me/overview` 增加 `wanted` 计数。
  - `frontend/src/App.tsx`：卖家商品详情增加“编辑商品”；求购看板 owner 增加“编辑”；新增“我的求购”视图；筛选状态下拉统一用于逛逛校园/收藏/售卖；`navigate` 按视图重置售卖状态默认值。
  - `frontend/src/Profile.tsx`：“我发布的”改名“我的售卖”，新增“我的求购”卡片与计数。
  - `frontend/src/forms.tsx`：`PublishForm` / `WantedForm` 支持编辑模式（预填 + PATCH）。
- 个人中心导航与求购按钮微调：
  - `frontend/src/Profile.tsx`：个人中心子导航首项“主页”改名“我的主页”，并把“站内消息”提前到第二位。
  - `frontend/src/App.tsx`：商品详情弹窗宽度由 890 收窄到 760。
  - `frontend/src/App.tsx` / `styles.css`：求购卡片的“编辑 / 我已找到”按钮分组并靠右（`.wanted-actions`）。
- 求购续期：
  - `backend/app/main.py`：新增 `POST /api/v1/wanted/{id}/renew`，把已过期/已结束的求购恢复为 ACTIVE 并续期 7 天。
  - `frontend/src/App.tsx`：我的求购里“已过期”的求购显示“续期”按钮。
- 分类横向条优化：`frontend/src/App.tsx` / `styles.css` 给分类条隐藏滚动条，并支持鼠标拖拽左右滚动（grab 光标 + pointer 拖拽）。
- 注册/账号弹窗窄屏自适应修复：
  - `frontend/src/styles.css`：`.modal-backdrop` 增加 `overflow-y:auto`，`.modal` 用 `margin:auto` 居中，避免内容过高时顶部被截断；移动端 `.form-grid` 改为单列，避免两列挤压/截断。
- 窄屏体验与排序微调：
  - `frontend/src/Profile.tsx` / `styles.css`：个人中心顶部子导航支持鼠标拖拽左右滚动。
  - `frontend/src/styles.css`：`html/body` 增加 `overflow-x:hidden` 隐藏整页横向滚动条；移动端筛选行“不限价格/所有好物/为你挑选”变窄并保持一行。
  - `backend/app/main.py`：商品列表按状态排序改为「在售 → 已预订 → 已过期/其它 → 已售出」。
- 顶栏固定与窄屏底部导航优化：
  - `frontend/src/styles.css`：`html/body` 的 `overflow-x:hidden` 改为 `overflow-x:clip`，避免破坏 `position:sticky`，让顶部白条固定不随滚动消失。
  - `frontend/src/styles.css` / `App.tsx`：窄屏底部导航条隐藏横向滚动条并支持拖拽左右移动。
- 文档整理：把测试清单 C 中尚未改进的问题（C1/C2/C4/C5/C7/C8/C9/C10/C11/C12）移入 `docs/FUTURE_FEATURES.md` 待实现清单。

## 2026-10-11

- 新增自然语言智能搜索：
  - `backend/app/schemas.py`：新增 `SmartSearchIn` 请求模型。
  - `backend/app/main.py`：新增 `POST /api/v1/items/smart-search`，复用 `parse_intent` / `parse_local` 把自然语言拆成分类、预算、成色、关键词等条件，再按关键词覆盖率与价格贴近度排序；远程模型不可用时降级为本地解析。
  - `frontend/src/App.tsx`：顶栏与手机搜索框新增「智能」开关，市场页新增智能搜索理解标签与结果列表。
  - `frontend/src/styles.css`：新增智能搜索样式。
- 管理员工作台拆分与公告管理：
  - `backend/app/main.py`：新增 `GET /api/v1/admin/announcements` 管理员公告列表。
  - `frontend/src/App.tsx`：审核工作台拆成「公告管理 / 聊天举报 / 商品举报 / 操作记录」四个页签；新增公告发布表单与上线/下线操作。
  - `frontend/src/api.ts`：新增 `AdminAnnouncement` 类型。
- 公告未读提醒：
  - `backend/app/models.py`：新增 `AnnouncementRead` 表，记录每个用户已读公告。
  - `backend/app/main.py`：新增 `GET /api/v1/announcements/unread` 与 `POST /api/v1/announcements/mark-read`。
  - `frontend/src/App.tsx`：未读公告计入铃铛红点，打开铃铛或「系统公告」时自动标记已读；未读数 10 秒轮询。
- 公告正文保留换行并放大字号：`frontend/src/styles.css` 给公告与铃铛通知正文加 `white-space: pre-line`，并调大公告/铃铛字号。
- 演示种子新增「燕渡」上线通知：`backend/app/services.py`。

## 历史改动文件清单（2026-10-07 快照）

| 文件 | 状态 | 说明 |
| --- | --- | --- |
| `backend/app/main.py` | 已修改 | no-store 响应头；新增 `/api/v1/sale-feedback/my`；已售商品排最后 |
| `frontend/src/App.tsx` | 已修改 | 铃铛聚合 + 通知中心分区 |
| `frontend/src/api.ts` | 已修改 | 新增 `SaleFeedbackNotice` 类型 |
| `frontend/src/styles.css` | 已修改 | 对比托盘固定宽度；通知分区样式；聊天输入框固定 |
| `docs/TEST_CHECKLIST.md` | 新增 | 测试清单 |
| `docs/api_test_results.md` | 新增 | 自动测试结果 |
| `scripts/api_test.py` | 新增 | 接口回归脚本 |
| `scripts/api_test2.py` | 新增 | 边角用例脚本 |
