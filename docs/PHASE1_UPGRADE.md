# ServiceFlow 第一阶段升级：从单次运行到连续会话

> 本文是第一阶段的历史说明。第二阶段已新增配置预检、显式回复评测、调用预算与三轮验证入口；最新行为见 [第二阶段说明](PHASE2_QWEN_VALIDATION.md)。第一阶段的测试数字和当时live限制不代表第二阶段当前能力或真实模型已经验收。

## 先读结论与学习顺序

本次在原项目上增量实现会话持久化、有界上下文、连续聊天和可复现评测。默认后端仍是真实 LangGraph StateGraph，不是字符串路由演示；本次没有引入向量数据库，也没有替换 SQLite。

建议依次阅读：本文运行与演示 → MULTI_TURN_ARCHITECTURE.md → 源码 chat_schemas.py / conversations.py / chat_context.py → runtime.py / workflow.py → Vue composable 与组件 → EVALUATION_GUIDE.md。

数据与能力的边界：业务数据是模拟数据；评测集由 AI 辅助编写并依据仓库政策核对，尚未经独立人工复核。不能说“80 条人工标注已验收”，不能说“真实企业客服准确率 91.25%”。当前仍适合单实例低并发试点，不是已完成生产验收。

## 一、如何运行（不重装环境）

在 VS Code 打开本文件所在项目的根目录“企业客服多Agent系统”，不是另一个 RAG 项目。已有 .venv 和 node_modules 时，无需重新创建环境。

终端一（项目根目录）：

~~~powershell
cd "C:\Users\yymmxr\Documents\ChatGPT\企业客服多Agent系统"
.\.venv\Scripts\python.exe -m uvicorn support_agent.app:app --reload --host 127.0.0.1 --port 8000
~~~

终端二：

~~~powershell
cd "C:\Users\yymmxr\Documents\ChatGPT\企业客服多Agent系统\frontend"
pnpm.cmd dev
~~~

访问 http://127.0.0.1:5173；后端 API 文档 http://127.0.0.1:8000/docs。两个终端都要保持运行。

只有缺依赖时才执行以下命令，沿用原环境：

~~~powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
pnpm.cmd install --frozen-lockfile
~~~

本次没有新增 Python 或 npm 第三方依赖。Node/pnpm 的既有锁文件不变。后端不开模型也可以跑规则分类、检索、审核与幂等测试。当前 .env 的模型、私有凭证没有被本轮修改。

公开本机开发凭证：客户 dev-customer-u1001；客服 dev-support-reviewer。若 .env 设置了 SUPPORT_AUTH_TOKENS，以自己的配置为准。生产模式不会自动开放这些凭证。不要将真实模型 Key 放进前端或 Git。

## 二、三轮对话与验收

1. 验证客户身份，点“新建会话”。
2. 输入“我的订单 ORD1001 到哪了？”：返回本人的订单、物流与运行详情。
3. 输入“那它可以退款吗？”：本轮新建 run，继承的是服务端已确认的订单编号，重新查订单，并检索退款政策。
4. 输入“那帮我申请售后吧。”：进入 awaiting_review；此时还没有建单。客户看不到批准按钮。
5. “访问身份设置”换成客服凭证并验证，重新选中该会话，点最后一条回复的“查看运行详情”，通过或确认拒绝。
6. 通过后同一 run 继续，生成工单；拒绝则不建单。工单不代表退款已批准。
7. 刷新页面：凭证不持久化；本机开发会回到默认客户。再次验证同一身份、选中会话，可读到最新结果。生产前端刷新后需重新输入凭证。
8. 新建另一个会话，输入“那它可以退款吗？”：不能沿用上一会话订单；输入“帮我查一下订单”再补充 ORD1001，应继续原 awaiting_input 的 run。
9. 原会话改问 ORD1002：U1001 得不到 U1002 的商品与物流。
10. “最近运行与恢复 / 最近运行与客服审核”进入原兼容工作台；原请求、历史与审核入口保留。

Enter 发送，Shift+Enter 换行；输入法组词时 Enter 不发送。失败时使用“安全重试原消息”，不要换新请求编号。加载历史不会重放工作流。无流式 SSE，本轮是同步 HTTP 完成后刷新消息。

## 三、改前与改后

改前：Vue 单次表单 → POST /agent/run → WorkflowService → LangGraph → 单条运行结果。

改后：

~~~text
连续聊天 → 会话 API → ConversationService
                         ├─ 原子登记用户/助手消息与请求
                         ├─ 解析有界上下文
                         └─ WorkflowService（仍以 run_id 为 thread_id）
                               → 原 Intent / Order / Policy / Review / Ticket / Response 图
                         ← 同步消息状态，附运行轨迹和政策来源
~~~

为什么不直接将 thread_id 改成 conversation_id？人工审核、订单号澄清、重试都依赖某一次 run 的检查点。一个会话中可能同时有已完成查询和待审核售后；共用 thread 会覆盖或混淆恢复位置。

为什么单独建 conversation_requests？HTTP 响应丢失不代表后端没完成。先登记稳定的用户/助手消息 ID、原文和调度上下文，再执行工作流，重试可以找到同一消息对与同一 run。

## 四、核心源码，分别学什么

| 文件 | 本轮职责 | 学习重点 |
|---|---|---|
| support_agent/app.py | 五个会话接口、客服只读评测接口 | HTTP 边界、依赖注入、身份和 Pydantic |
| chat_schemas.py | 会话、消息请求和响应契约 | 长度限制、拒绝未知字段、UUID、保留原文 |
| conversations.py | ConversationStore / ConversationService | SQLite 事务、请求去重、分页、消息同步 |
| chat_context.py | 配置与指代解析 | 滑动窗口、字符上限、显式订单优先 |
| runtime.py | 保存 conversation_id 和冻结上下文 | 旧指纹兼容、run/thread 不变、恢复 |
| agents.py | 带上下文的意图/订单关联，政策前复核订单 | 记忆不是授权；工具输出才是业务依据 |
| workflow.py | 保留原审核条件路由 | 拒绝订单访问后不走建单审核 |
| llm_client.py | 给模型有限历史并声明不可信 | 模型不掌握身份、审核决策与工具写权限 |
| intent.py | 中文相邻订单号解析 | 不用 Unicode 单词边界阻断中文订单号 |
| frontend/src/composables/useConversation.ts | 页面会话状态与异步请求 | 身份 epoch 丢弃旧响应，固定请求键 |
| ChatSidebar / ChatWindow / ChatMessage / ChatComposer | 导航、滚动、消息、输入 | 组件只负责显示或发事件 |
| AgentTracePanel.vue | 复用原 ResultPanel / AgentTimeline | 审核、补充、恢复仍调原 API |
| EvaluationPanel.vue | 客服查看真实本地报告 | 没有报告就显示空状态，不伪造图表 |
| LegacyWorkbench.vue | 原 App 原逻辑的兼容入口 | 不删旧业务与测试 |
| evaluation/ | 数据集、指标、评测执行、报告输出 | 测试通过率不等于 AI 效果 |
| tests/test_conversations.py、test_evaluation.py | 新增回归测试 | 隔离数据、失响应、越权、迁移与指标 |

后端一条消息的逐步走读及数据库设计见 MULTI_TURN_ARCHITECTURE.md。

## 五、实际验证与结果

开发前重新运行基线：后端 24 passed；前端 8 passed；构建成功。

开发后测试、联调与评测的最终记录见 VERIFICATION_PHASE1_20261022.md。构建和 pytest 不是模型在线效果证明。

2026-10-22 本机默认离线评测：80 条意图样例 Accuracy 91.25%，Macro-F1 0.9208；20 条政策检索 Recall@1/3/5 为 95%/95%/100%，MRR 0.9625；10/10 工作流场景符合预期。保留 7 条分类错误和 1 条 Top-3 检索未命中，不改标签凑分。

22 次集成请求中 21 次 2xx、1 次预期的跨用户 404；16 次工具调用有 1 次预期越权拒绝。不能把“非 2xx / 工具拒绝”全部当成缺陷，也不能把场景通过率当作全流程已经完成：10 个场景中 8 个末态完成，另外两个按预期等待审核。

报告 latest.json / details.csv / summary.md 保存在 evaluation/reports，默认被 Git 忽略。性能耗时随本机运行变化，以每次报告为准，禁止当作压测或线上 SLA。

## 六、主要难点与面试回答

问：多轮对话是把 history 拼进 prompt 吗？
答：不止。消息存 SQLite，会话 owner 绑定服务端身份；结构化 confirmed order 加有界历史提供上下文，每次用订单工具重新校验归属。历史只提供线索，不授权业务操作。

问：四个 ID 怎么解释？
答：conversation_id 归组完整聊天，run_id 绑定一次可恢复业务执行与 Checkpointer thread，request_id 去重一次提交，message_id 标识消息。补充订单会产生新消息但恢复旧 run；已完成后的新业务请求创建新 run。HTTP X-Request-ID 则是每次网络请求的诊断追踪号，不是业务幂等键。

问：刷新怎么避免重复建工单？
答：GET 历史只读检查点并同步结果，不执行 invoke。重发 POST 用同一业务 request_id；消息层与运行层去重，建单再以 run_id:ticket 唯一键兜底。不是笼统承诺分布式 exactly-once。

问：中途断电，消息和检查点不是同一个事务怎么办？
答：消息对先用事务登记 pending，调度信息被冻结；LangGraph 及工单有各自持久化/幂等保障。未确认结果沿用请求键重试，再对齐消息。跨数据库不是一个大事务，仍需要故障注入测试和人工运维策略。

问：下一轮会覆盖正在审核的流程吗？
答：不会。每个 run 都有独立检查点，普通消息不能写 approved。新业务产生新 run，等待审核的 run 仍在原检查点；只有客服权限的审核接口能用 Command 恢复它。

问：模型挂了会怎样？
答：分类失败保留规则基线，回复失败保留模板，轨迹明确显示 disabled / fallback_template / llm_generated；真实写操作不由模型授权。离线评测用模拟超时验证回退，没假装真实千问端到端已全测。

问：为什么用 SQLite，不直接上 Redis / PostgreSQL？
答：这阶段是本机单实例验证，SQLite 事务和 checkpointer 已够用，复杂度低；进程 RLock 只保护一个 worker，不支持多进程一致调度。将来多实例必须改分布式租约/队列及可共享检查点，不能只加 workers。

问：你的评测数据可信吗？
答：它是 80+20+10 条 AI 辅助模拟开发数据，标记待独立人工复核；RAG 还保存了源文件与确切证据。指标脚本可复现，报告有数据/源码哈希，但这不是人工复核后的独立测试集，更不是生产日志。

问：怎么讲项目成果？
答：讲清楚已实现的闭环与保护机制、开发集实测数字和局限。不要编造企业实习、真实客户量、线上吞吐量或真实模型调用成功率。

## 七、文件变更清单

修改：.env.example、.gitignore、README.md、api/openapi_tool_for_dify.yaml；support_agent 的 app.py / agents.py / intent.py / llm_client.py / runtime.py / workflow.py；frontend/src 的 App.vue / api.ts / types.ts / main.ts / App.test.ts。原 App 测试只调整被测组件导入以保留兼容工作台，断言未删减。

新增：support_agent/chat_schemas.py / chat_context.py / conversations.py；frontend/src/LegacyWorkbench.vue / chat.css / ChatApp.test.ts / composables/useConversation.ts；components/ChatSidebar.vue / ChatWindow.vue / ChatMessage.vue / ChatComposer.vue / AgentTracePanel.vue / EvaluationPanel.vue；tests/test_conversations.py / test_evaluation.py；evaluation/__init__.py / run_evaluation.py / README.md / datasets/*.jsonl / evaluators/{__init__,metrics,intent_eval,rag_eval,workflow_eval}.py / reports/.gitkeep；本文及配套三份说明；.impeccable/surfaces/conversation.md 仅为开发设计记录。

未改：真实 .env、原业务数据、原 RAG 项目、依赖锁文件。升级验证完成时尚未提交或推送；后续 GitHub 同步以仓库提交和 Actions 记录为准。

## 八、当前风险和下一阶段

- 需要独立人工复核标注并冻结新测试集，补充边界与歧义问题，避免开发集调参过拟合。
- live 评测目前仅实际启用“意图分类”；完整千问三轮对话、额度、延迟、Token 与成本尚未验收。
- 静态开发凭证、单 worker、无数据保留/删除治理；公网前要接企业身份、密钥管理、PII 脱敏与审计策略。
- 模糊多订单指代保守处理，显式多订单拒绝；不是通用长期记忆或任意指代推理器。
- 同步请求期间会话串行，未实现分布式锁、后台任务、SSE。并发压测和故障恢复演练还需单独做。
- 后续优先真实业务适配与基于错误分析的改进，不能仅通过堆技术名词宣称企业级。
