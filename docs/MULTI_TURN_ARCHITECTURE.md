# 多轮会话与 LangGraph：结合源码精讲

第二阶段保持本页会话/检查点架构不变，在模型边界与离线/在线评测上增量扩展，见 [千问验证说明](PHASE2_QWEN_VALIDATION.md)。

2026-10-23收尾已加入本轮订单结构化事实约束，不改变以下会话、路由、审核或持久化契约。重新执行的测试与既有真实模型证据见[第二阶段收尾报告](PHASE2_RELEASE_20261023.md)。

## 1. 四种业务 ID 和一条关键不变量

| ID | 谁生成/何时生成 | 保存在哪里 | 重试/澄清 |
|---|---|---|---|
| conversation_id | 后端创建会话 | conversations 主键及 run 关联 | 跨多轮不变 |
| run_id | WorkflowService 创建业务执行 | runs、消息、checkpointer | 同次澄清/审核恢复不变 |
| request_id | 前端 crypto.randomUUID，一次发送固定 | conversation_requests 与 runs 请求键 | 同次重试必须复用 |
| message_id | 后端登记消息对 | conversation_messages | 重试不重复新增 |

始终保持 run_id = LangGraph configurable.thread_id。会话不是工作流的检查点线程。

另外：每个 HTTP 响应的 X-Request-ID 是诊断追踪号，每次 HTTP 可以不同，不能拿它替代业务 request_id。

## 2. 一条请求逐步执行

从页面点击发送开始：

1. ChatComposer 处理 Enter / Shift+Enter / IME，向父组件发 send 事件。
2. App → useConversation.send；没有会话先创建；生成并保存一个 request_id。忙碌或有待重试消息时拒绝再发。
3. api.ts 将凭证放入 Authorization，POST 会话消息，只传 content 与 request_id；没有可修改角色、审核状态或记忆的入口。
4. app.py 的 current_principal 从服务器配置查真实 Principal；MessageCreate 验证 UUID、非空和最长 1000 字符。空白消息拒绝，但 API 原文不被改写。
5. ConversationService.send 先取会话并校验 owner，再在单进程 execution_lock 下查请求去重。
6. 同 actor+request_id 已存在：若内容/会话不同返回 409；相同则读已有运行或用冻结调度重试，不新建消息。
7. 新请求先读取未完成 run 的检查点以同步状态，再找是否有 awaiting_input。有未确认的 pending/failed 消息时要求先重试，避免顺序失控。
8. resolve_context 只读本会话最近窗口和 verified_order_id，显式订单优先。多订单返回 422；若正在等订单号，只允许本轮补充合法编号。
9. 一个 SQLite 事务写 conversation_requests 和 user / assistant 两条 pending 消息，更新会话标题与最后时间。
10. 新业务调用 WorkflowService.start；补充信息调用原 WorkflowService.resume，同 run，不改变 thread_id。
11. 原 StateGraph 按意图路由；ScopedTools 在服务端按服务对象查订单；售后/投诉需 interrupt 审核。
12. sync_run 将运行状态、回复、steps 和 sources 保存到最新助手消息 metadata.result。响应扩展原 AgentResult，附 conversation_id、用户 message_id、assistant_message_id。
13. 前端重新加载服务端消息与会话列表，显示真实状态。选择某条回复可 GET 其 run，查看原轨迹或恢复接口。

网络出错时不把本地气泡伪装成已完成。原 request_id 保存在内存；已登记但未完成的用户消息 metadata 还带 request_id，刷新后重新验证身份即可恢复安全重试。

## 3. 数据库表与迁移

不新增数据库服务：会话表与运行登记共用 data/workflow_runs.db；图检查点仍在 workflow_checkpoints.db；订单/工单仍在 business.db。SUPPORT_DATA_DIR 可以独立指定数据库目录，政策文档仍来自仓库 data/policies。

### conversations

conversation_id 主键，owner_user_id，title，created_at，updated_at，last_message_at，status；附 verified_order_id 和 verified_order_sequence。后者避免旧审核稍后完成时覆盖更新的订单上下文。

索引 conversation_owner_time(owner_user_id, updated_at)。

### conversation_messages

sequence 自增主键用于稳定分页；message_id UNIQUE；conversation_id 外键；run_id 可空；role CHECK(user/assistant/system)；content；status；created_at；metadata JSON 文本。

索引 (conversation_id,sequence) 与 run_id。最新页倒序 LIMIT 后在返回前转回正序。before 是 sequence 游标，避免时间戳相同导致顺序不稳定。返回 next_before，可能多出一次空尾页，但不会重叠或漏历史。

### conversation_requests

PRIMARY KEY(actor_id,request_id)，conversation_id 外键；两条 message_id 各 UNIQUE；原 content；冻结 dispatch JSON；run_id；status。actor 是发起者，owner 是被服务客户：客服可以代客户，但客户不可以指定别人的 owner。

### runs 增量列

runtime.py 先 PRAGMA table_info，缺 conversation_id / context_json 时 ALTER TABLE ADD COLUMN；旧行默认空上下文，不更改旧 run/request 指纹。创建会话表使用 IF NOT EXISTS，并在 chat_schema_migrations 记录 version=1；重复初始化安全。

本次第一次启动后自动执行增量迁移。不会删除业务表或把旧 agent_logs.db 导入新表。后续再增加字段必须新增迁移版本，不能只改 CREATE TABLE 假设旧表自动跟着变。

### 启动前备份与回退

如有重要数据，先停止后端再备份整个实际 SUPPORT_DATA_DIR（默认 data）到项目外的私有目录，保证三个 SQLite 数据库和可能存在的 WAL/SHM 一致；不要边运行边单独复制某一个 db。备份包含聊天和用户数据，不要上传 Git。

这阶段新增字段/表不要求删除旧记录。应用退回旧版本前应先停止服务并使用完整一致的备份；旧版本未认识的新会话不会自动显示。迁移幂等不等于已经完成所有跨版本回滚演练。

## 4. 上下文到底记住什么

chat_context.ContextSettings.read 在后端启动与解析时真实读取：

| 配置 | 默认 | 合法范围 |
|---|---|---|
| CHAT_HISTORY_WINDOW | 10 | 1..50 条消息，不是 10 个双向回合 |
| CHAT_MAX_CONTEXT_CHARS | 12000 | 256..24000 个序列化 JSON 字符 |
| CHAT_CONTEXT_ENABLED | true | true / false |

先按窗口拿最近消息，再按字符预算截断，最后校验整个上下文 JSON 字符上限。字符不是 Token；模型的真实 Token 成本仍需供应商 usage 才能统计。当前最新问题另行单独传模型，长度由 API 1000 字符限制。

结构化字段：order_id、order_source、history，必要时 intent_hint。显式编号覆盖继承；业务追问或“那/它/这单”等指代可用已确认订单；多个明确不同订单拒绝。未知指代且已有确认订单时，确定性回退为订单查询。

只有工具 query_order 返回 ok 的结果能更新 verified_order_id。对明确但无权订单会清除确认值，不能“沿用之前的授权”访问新编号。每轮 PolicyAgent / OrderAgent / ReviewAgent / Ticket 工具仍做实际归属校验。

history 里的角色文本和模型输出不参与服务器身份判定。generate_customer_reply 的提示明确声明历史不可信；这是一层提示约束，不应冒充完备的提示注入防御，真正的边界在服务器鉴权与工具。

### 订单事实不是会话推测

ScopedTools.query_order先校验客户归属，再在原始data外附加OrderFacts；兼容SupportTools也使用同一构造器。订单数据库和原HTTP业务字段不变。模型入口与回复校验均从本轮data重新构造事实，不相信历史文本或外部传入的facts对象。

- status=已发货且received_days=null：receipt.state=unknown，不能推出未签收。
- 明确已签收但天数null：可以说已签收，不可编造天数；合法0天不能用真值判断误当未知。
- 明确未签收且无相反证据：not_received；负数、bool、字符串、小数不冒充合法签收天数；矛盾证据回到unknown并要求核实。
- 缺物流不改变签收三态。refund_eligibility始终not_determined，政策条件不等于订单已满足条件或审批结论。

OrderFacts → Prompt区分已知/未知/政策条件 → 有限断言检查 → 不安全输出回退原模板。该链路不改变LangGraph节点、thread_id、审批resume或工单唯一键，也不允许模型授权写入。规则不是完整自然语言语义判定，少见表达仍需独立复核。

## 5. 三轮与澄清的区别

~~~text
同一 conversation
  消息1：查 ORD1001           → run-A completed
  消息2：那它可以退款吗       → run-B completed，复核 ORD1001 + RAG
  消息3：帮我申请售后         → run-C awaiting_review
  客服 /run-C/review          → run-C completed，建单唯一键 run-C:ticket
~~~

没有订单的新会话：

~~~text
  消息1：帮我查订单           → run-D awaiting_input
  消息2：ORD1001              → resume run-D，不创建第二个 run
~~~

澄清前原始用户文本与助手询问内容保留；恢复后的最终答案更新最新助手消息。关联同一 run 的状态同步为最新业务状态。因此早先那条“请提供订单号”可以保留文字、状态却显示完成，含义是这次运行已继续完成，不是改写历史。

等待审核时下一条普通消息可以创建新业务 run，但绝不能把 approved 写到原 run。审核只允许原客服接口；恢复前后仍有审计事件与工具幂等校验。

## 6. 一致性与恢复边界

消息对登记是一个事务，但消息库、图检查点与业务工单不是分布式大事务。项目采取“先登记 + 可重入执行 + 幂等副作用 + 结果对齐”。

- 登记后、图执行前失败：同 request_id 用冻结 dispatch 执行。
- 图完成但消息写回失败：同请求定位原 run，不重复消息或建单，再同步状态。
- 审核后消息未刷新：GET messages 读取检查点同步，不 invoke。
- 完成的请求重发：返回原运行/消息 ID，不新建业务记录。
- 数据库/网络长期不可用：需要人工排查与备份恢复，不承诺自动修复一切故障。

execution_lock 是进程内 RLock，不是分布式锁；本配置只能一个 API worker。列表 offset 分页在并发更新时间变化时不是不可变快照；需要实时大列表时应升级游标策略。历史 reconcile 当前扫描会话关联 run，长会话成本会增长；未来可以建立终态快照与待同步索引，不能声称无限历史 O(1)。

## 7. 前端文件关系

App 组装页面与导航；useConversation 管状态与 API；ChatSidebar 管会话导航；ChatWindow 管历史与自动滚动；ChatMessage 管安全纯文本展示；ChatComposer 管输入；AgentTracePanel 复用原 ResultPanel 和 AgentTimeline；EvaluationPanel 只读报告；LegacyWorkbench 保留原运行与审核页面。

状态切换采用 epoch/selection 计数，异步返回前比较：用户已切换则旧响应不能覆盖新页面。清除消息、运行、重试请求、当前会话；token 仅内存；localStorage 仅按已验证用户保存选中的 conversation_id，服务端再验证该 ID 的归属。

刷新不会把真实 token 存浏览器以自动登录；本机开发默认凭证只是开发便利。两个账号不要共享一个正在发业务请求的浏览器会话，正式部署仍需要会话注销和企业身份生命周期治理。

## 8. 新增 API 速查

全部要求 Bearer，评测接口还要求 support。

| 方法/路径 | 含义 |
|---|---|
| POST /agent/conversations | 创建，客户 owner 只能本人，客服可填合法 owner_user_id |
| GET /agent/conversations?limit=30&offset=0 | 客户仅本人；客服全部 |
| GET /agent/conversations/{UUID} | 归属检查；无权统一 404 |
| GET /agent/conversations/{UUID}/messages?limit=50&before=序号 | 时间顺序历史，仅同步结果不执行图 |
| POST /agent/conversations/{UUID}/messages | content + UUID request_id；返回扩展 AgentResult |
| GET /agent/evaluations/latest | 客服只读报告；无文件 report=null |

原 /agent/run、/agent/runs、/resume、/review、/retry、/audit 均保留。api/openapi_tool_for_dify.yaml 是可作为 YAML 读取的 JSON OpenAPI 导出；测试对比运行时 schema，不能手改造成与代码不一致。

最小请求体示例：

~~~json
{"content":"那它可以退款吗？","request_id":"e4f2488e-4e88-4a20-9162-a62578167193"}
~~~

401 凭证无效；403 不具备客服权限/客户冒用 owner；404 不存在或无权；409 幂等冲突或上一消息未确认；422 参数/订单澄清问题；500/503 暂时执行或持久化失败。错误详情不输出供应商原始密钥异常。
