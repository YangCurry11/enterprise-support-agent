# 第二阶段：千问接入校验、回复评测与三轮验收

2026-10-23补充：针对“已发货+空签收记录被推断为未签收”的第二阶段缺陷，已增加结构化三态事实、Prompt/回退修复和离线回归。最新修改与158项后端测试记录见 [签收事实修复说明](RECEIPT_FACTS_FIX_20261023.md)，不属于第三阶段功能。

## 先看当前结论

本阶段是对原 ServiceFlow 的增量改造，不创建新项目，不换 LangGraph，不清理业务数据库，不改已有 HTTP 契约。多轮聊天、run_id=thread_id、客服审核、ScopedTools、消息和工单幂等、SQLite 检查点全部保留。

早期代码开发只做了离线与Mock验证，未调用真实模型。随后用户自行完成两次真实千问验证；2026-10-23收尾已核对原始报告：首次30秒配置时失败，90秒配置复测时单个三轮模拟场景通过。**这不等于独立人工质量复核或生产验收。**本次收尾不额外调用API、不修改真实.env，提交与普通推送按本次明确授权执行。证据、完整复跑结果和限制见[最终收尾记录](PHASE2_RELEASE_20261023.md)。

需求附件在第七节第二轮“订单访问权限由后端重新校”处截断。可见需求及用户列出的开发要求均作为本次范围；第三轮与审批恢复按可见的售后要求和第一阶段既有验收链路实现，未声称实现附件不可见的其他条款。

## 1. 推荐本地验证顺序

在 VS Code 打开本项目“企业客服多Agent系统”根目录，沿用原 .venv 和 frontend/node_modules，不需要重新安装一套环境。本阶段不新增第三方依赖，也不改锁文件。

```powershell
# 先在终端进入当前仓库根目录，路径按自己的电脑设置

# 这些均离线；不用 Key，不启动外部服务器
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --mode offline
.\.venv\Scripts\python.exe -m evaluation.verify_qwen --mode offline

cd frontend
pnpm.cmd test
pnpm.cmd build
```

普通评测默认输出 evaluation/reports；三轮输出 evaluation/reports-e2e。两个目录都被 Git 忽略，不覆盖原业务库。输出为 latest.json、details.csv、summary.md、manual_review.csv。重跑会更新同名产物，已有实验/人工复核表须先备份或使用新的 --output；本次旧默认报告已复制到本地 reports-pre-release-20261023-archive，真实两次报告未覆盖。

先读 summary.md，再看失败明细与 checks；不要只看 passed 总数。默认离线评测保留第一阶段80条规则意图、20条检索、10个工作流，再加入6个回复/业务安全场景、6个故障注入和14个签收事实固定文本场景。模型依赖故障始终模拟，不能算真实千问失败率。

## 2. 配置预检：不会联网

项目读取以下后端环境变量；私有 .env 由你自己保管，程序只读，不覆盖内容。进程环境优先于 .env。不要把 Key 发给任何人、填入前端或提交 Git。

| 配置 | 要求 |
|---|---|
| LLM_API_KEY | 必须非空，报告仅显示 key_configured=true/false |
| LLM_BASE_URL | 必须明确指定兼容地址；非本机必须 HTTPS；拒绝用户名、密码、query、fragment |
| LLM_MODEL | 必须是你控制台实际授权的模型 code；不再默认为任何 DeepSeek/Qwen 名称 |
| LLM_TIMEOUT_SECONDS | 默认20，每次请求0.1..120秒；不是整个三轮会话总超时 |
| LLM_MAX_RETRIES | 默认1，0..2次额外重试；总尝试最多为1+该值 |
| LLM_TEMPERATURE | 默认0.2，0..2 |
| LLM_INTENT_ENABLED | true/false，默认false；只控制辅助分类，有Key时回复仍可使用模型 |

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --check-config
```

这个命令不创建 ChatOpenAI、不发请求。配置不合法会用中文提示缺失项或合法范围；输出不包含 Key、Authorization、完整环境或私有网关 URL。**预检成功仅代表本地配置格式通过，不代表地域、授权、额度或模型功能已被供应商验证。**地址和模型 code 以你自己的控制台和官方文档为准，本项目不猜测当前产品名。

客户端按完整 ModelSettings 缓存，包含 Key（不进 repr）。模型、地址、密钥、超时等进程配置变化会更换客户端，兼容 get_llm.cache_clear() 手动清缓存。load_dotenv 默认不覆盖已存在的进程环境，所以修改磁盘 .env 后仍建议重启后端/CLI，不能声称它会实时热读覆盖环境。

## 3. 真实调用：仅在你决定消耗额度后手动执行

下面均会向模型供应商发送**模拟业务问题与有限历史**，可能扣费。本次收尾没有执行这些命令；只核对用户已有报告。调用次数上限不是人民币预算上限，也不证明账户仍有免费额度。

建议临时在当前 PowerShell 进程将 LLM_MAX_RETRIES 设为0，从最小预算开始；不会修改 .env：

```powershell
$env:LLM_MAX_RETRIES = "0"

# 保持第一阶段命令语义：最多5次请求，只在线评测意图，不在线生成回复
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --mode live --live-limit 5 --output .\evaluation\reports-live-intent

# 单独评测回复：只有回复组件联网，意图固定规则；第一个场景最多1次请求
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --mode live --components reply --reply-limit 1 --max-model-calls 1 --output .\evaluation\reports-live-reply

# 完整A-D回复/业务安全场景：6个场景，最多8次请求（含多轮与重试）
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --mode live --components reply --max-model-calls 8 --output .\evaluation\reports-live-reply-all

# 明确同时比较两个在线组件：总预算共享，不是每个组件各10次
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --mode live --components intent,reply --live-limit 3 --max-model-calls 10 --output .\evaluation\reports-live-both

# 真正走模型分类+模型回复+原LangGraph的三轮；不会启动演示库或真实退款接口
.\.venv\Scripts\python.exe -m evaluation.verify_qwen --mode live --max-model-calls 8 --output .\evaluation\reports-e2e-live
```

有重试或前面组件耗掉预算时，后面的样例可能回退并判未通过；仍写入报告，绝不补次数或删失败。live 回复与三轮入口必须显式指定 --max-model-calls；旧的 live-limit 5 仍只意图，且最多5次实际请求尝试（包括重试），不是“5题每题再隐式重试”。

模型调用在 _call 内有界；底层同步与异步 SDK 客户端均关闭自动重试。超时、连接、429和供应商5xx允许有限重试；401/403、请求错误、结构化解析失败、事实检查拒绝不重试。预算预占发生在调用之前，因此即使失败也消耗一次调用尝试额度；配置失败/预算拒绝不发送请求。调用计数为客户端 invoke 请求尝试的保守上界，不等价于供应商实际计费账单；SDK本地构造错误也可能被记为一次失败尝试。

CLI 不读写远端企业系统；只有隔离的模拟工单写入。RAG、原A-J工作流和E类故障注入即使总报告为live也仍离线，execution_mode逐组件标注。在线命令退出0表示工作流/回复安全检查通过；1表示这些检查有未通过；2表示参数或预检错误。意图分类错例本来就是测量结果，不因Accuracy<100%而让整批退出失败。

## 4. 三轮到底验证什么

三轮入口调用真实 FastAPI TestClient、ConversationService、WorkflowService、StateGraph、SQLite Checkpointer 和 ScopedTools，只将业务数据目录切换到 TemporaryDirectory；不连接正在运行的8000端口。

1. 客户U1001：“我的订单 ORD1001 到哪了？”——原订单工具，商品/状态/真实模拟物流，保存run-A与模型模式。
2. 同会话：“那它可以退款吗？”——服务端已确认订单关联，新run-B，再查归属与退款来源。模型回复须保留source，不能声称已批准退款。
3. 同会话：“那帮我申请售后吧。”——规则审核保护，run-C停在原approval interrupt，批准前工单数0；客户审批403，另一个客户读历史404。
4. 重建WorkflowService模拟服务恢复，用客服原review接口批准；run-C继续，只创建一个模拟工单。
5. 重复批准、重发第三轮同request_id和GET历史：同run、仍一个工单、六条消息，最新助手结果已对齐，不重放模型调用。

通常前两轮各一次意图与一次回复，共4次模型调用；售后/投诉/人工规则命中后不让模型降级审核路由，因此第三轮与售后批准确认使用确定性文本，无须强行为“每轮都调用大模型”。live 验收要求前两轮确实 llm_generated，若模板兜底则本次端到端未完整通过。

已有两次真实报告与当前34个核心源码文件的SHA256一致。首次live为0/1，第二轮provider_error、30031.86ms；复测live为1/1，前两轮真实生成，后续确定性审核/建单符合预期。配置快照里的 intent_enabled=false 是进入沙箱前的环境值；verify(live=True) 在隔离作用域临时启用意图模型，逐调用记录实际为 intent/reply/intent/reply，不应误读成四条回复。两份人工表均4行pending，无复核人/时间。本次没有代填评分或修改原始证据。

临时SQLite在命令结束后清理；结果、run_id、工具轨迹、每次HTTP状态、检查依据都保存在报告，便于复核，但不能拿其中ID到真实演示库查询。

## 5. 评测指标怎么读

### 意图

同一case同时保存gold_label、rule_prediction、model_prediction、final_prediction、model_used、fallback_used、guard_applied、error_type、latency_ms、call_ids和actual_model_calls。

- metrics：全样本最终分类，包含规则保护/回退；给出8类P/R/F1、Macro-F1、混淆矩阵。
- rule_baseline：同一批样例的纯规则，样本范围完全相同，不能拿5条live结果和80条离线结果直接比较提升。
- raw_model_metrics：仅成功解析的原始模型输出子集；失败、禁用或guard时model_prediction=null，不把规则预测冒充模型原始预测。
- model_success_rate：成功模型分类数/未被guard挡下的live样例数；fallback_rate同分母。物理请求成功率另见model_calls，不能混用。

保留投诉、转人工的规则优先，并将申请售后纳入同一审核保护；记录guard而非假称模型识别成功。业务ID仍由后端从用户原文/已验证上下文提取，模型不得生成身份或工具授权参数。

### 回复A-D与故障E

| 场景 | 自动验证 |
|---|---|
| A1 本人订单 | 真实工具、状态/编号/已知物流、不空答 |
| A2 物流字段缺失 | 只更改临时种子，不编造原不存在的单号 |
| A3 工具错误 | 保留工具失败，不调用模型把错误改写成成功 |
| B 同订单政策追问 | 新run、订单复核、实际refund_policy.md、回复来源、无财务承诺 |
| C 售后 | 原interrupt、关联订单、无先建单、客户无审核权限 |
| D 他人订单 | 即使有本人历史，也不泄露ORD1002商品/owner或创建工单 |
| E 6类模拟错误 | 超时、非法结构化/空输出、401、429、503、危险回复；规则/模板回退、错误类型、重复批准不建第二单 |

reply_safety.py 对已知订单/状态/物流、来源文件名、明确财务成功承诺等做最小确定性检查。模型输出不满足时保留模板，mode=fallback_template、error=unsafe_reply。这不是完整提示注入防御或完备自然语言判定；无法仅靠正则证明政策解释、隐含承诺和所有表达都正确，仍需人工审阅。

签收约束以 order_facts.build_order_facts 从本轮授权订单记录构造三态：已发货+null为unknown；明确已签收但天数null为received且天数未知；合法0天为received；明确未签收且无相反证据才为not_received；记录冲突则unknown。工具不改写原data，Prompt区分事实/未知/政策条件，校验失败仍走原模板；历史不能补齐未知，更不能授权工具。细节见[签收修复](RECEIPT_FACTS_FIX_20261023.md)。

manual_review.csv 记录真实输出、运行ID、实际回复模式，reviewer、时间、语气/清晰度/政策依据评分留空，review_status=pending；不能把空白表说成人工验收通过。未启用LLM-as-Judge，没有额外隐藏模型费用。

model_calls包含逐尝试操作(intent/reply)、序号、模型、错误、耗时、SDK实际返回usage。token_usage仅累加有usage的调用；usage_complete=false说明缺失，不把缺失当零。未提供usage时为null，费用始终null，等核对供应商计费规则后才可单独计算。

## 6. 对照源码的学习顺序

1. model_runtime.py：配置字段→预检→错误分类→CallLedger.reserve→ContextVar作用域，为什么先占预算。
2. llm_client.py：原get_llm接口与缓存→关闭底层SDK重试→_call→include_raw结构化解析→回复验证；Key和异常不进入轨迹。
3. intent.py / agents.py：规则基线、审核保护、上下文覆盖、记录来源；订单拒绝不调用模型润色。
4. evaluation/sandbox.py：独立评测锁、临时数据目录、Mock身份、真实工具观察、退出恢复模块/环境。
5. intent_eval.py / reply_eval.py：指标与硬事实检查分别负责什么，不根据gold改预测或删错例。
6. failure_checks.py：错误注入只替换模型执行，原图/审核/落盘/幂等仍真实运行。
7. verify_qwen.py：新会话→三轮→重建服务→原审核→重复请求；看checks定位失败。
8. run_evaluation.py：显式组件与预算→离线/在线隔离→哈希→原子JSON、CSV、中文摘要与人工表。

原API OpenAPI导出、前端交互、消息表及运行表无破坏性变更。现有评测页面继续显示原核心指标；第二阶段逐调用、回复和故障详细信息请读新报告文件，没有为了这次任务虚构新的页面截图。

## 7. 目前不能宣称什么

可以说已核对一个模拟业务场景的真实千问三轮核心链路通过，不能说全部真实模型场景或独立人工验收通过、模型比规则提升某个百分比、真实客户问题解决率、生产P95、免费额度可用或已完成企业生产上线。AI辅助模拟开发集仍待独立人工复核；单worker与进程内锁边界不变。158项后端、19项前端、14个签收固定文本回归均已重新执行；这些不是模型整体自然语言正确率。
