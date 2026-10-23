# ServiceFlow AI 第二阶段最终收尾记录（2026-10-23）

## 1. 结论与证据范围

本次在现有 enterprise-support-agent 仓库增量收尾，没有创建新项目或开发第三阶段。开始时分支为 main、上游 origin/main；fetch 后双方均为 19c7f97b2a78757f1a954dc1b1a54f86455ca23d，ahead=0、behind=0。14个未提交文件均属于此前签收事实修复，本次保留并审查，没有混入相邻RAG项目。

本次重新执行后端、前端、依赖检查、离线Agent评测和独立三轮验证，均符合对应预期。用户已有两次真实千问报告均存在；一次失败、一次单场景通过，原始文件保持不变。本次未额外调用真实模型、未修改真实.env，未删除业务数据库或历史报告。

本文记录提交前核验的事实，不预先把云端CI写成通过。发布提交以包含本文件的Git提交为准；提交SHA、远程一致性和该SHA的最终GitHub Actions结果由最终交付记录明确列出。历史103项和签收开发37.12秒记录保留，不冒充本次复跑。

## 2. 当前架构与边界

| 层 | 当前职责 |
|---|---|
| Vue 3 + TypeScript | 会话列表、连续消息、运行详情、政策来源、客服审核和只读评测页面 |
| FastAPI | 身份、会话owner与参数校验；会话/消息、运行、review/resume API |
| ConversationService | conversation_id分组、消息落盘、request_id幂等、有界上下文、确认订单关联 |
| WorkflowService + LangGraph | Intent / Order / Policy / Ticket / Response显式工作流；run_id始终为thread_id |
| SQLite | workflow_runs.db保存运行/会话/消息，workflow_checkpoints.db保存图检查点，business.db保存模拟订单/工单 |
| ScopedTools | 每次订单访问按服务对象重新校验归属；未授权不返回订单data或facts |
| TF-IDF RAG | 中文char 1–4 gram、Query Expansion、Top-K片段与来源文件；未引入Embedding或向量库 |
| Qwen辅助层 | 受限意图分类与回复生成；高风险审核路由保留规则保护；预算、有界重试、usage与安全回退 |
| 人工审核与幂等 | 原interrupt / Command(resume)；客服专属审批，批准前不建单，run级工单唯一键 |
| Agent评测 | 意图/检索/工作流/回复/故障/签收回归；独立三轮工具；JSON、CSV、摘要与pending人工表 |

受控工作流不是无限自主规划系统。模型不执行权限判断、退款审批或直接建单；会话历史不是授权依据。三个SQLite存储不构成跨库分布式事务，进程内RLock仅面向单实例/单worker。

## 3. 签收事实修复审查

### 已知事实、未知状态、政策条件分开

build_order_facts只从本轮成功且授权的订单data派生事实：

| 工具证据 | 签收事实 |
|---|---|
| 已发货，received_days=null | unknown；没有肯定或否定签收证据 |
| 明确已签收/已收货，天数null | received；天数仍未知 |
| 非负整数签收天数，包括0 | received；0表示当天签收，不是空值 |
| 明确未签收/未收货，无相反证据 | not_received |
| 明确未签收与合法签收天数冲突 | unknown且conflicting_evidence=true，要求核实 |
| 缺物流、预计送达、历史或用户自述 | 不作为签收结论的替代证据 |

不改原始data、数据库结构、种子或HTTP请求契约。负数、bool、字符串和小数不被当成合法签收天数。refund_eligibility保持not_determined：签收日期不是“商品完好、材料齐全、退款审核通过”的替代判定。

### 约束链路

1. ScopedTools先做订单归属校验，再附加facts；兼容SupportTools共用构造器。
2. llm_client从本轮data重建OrderFacts，Prompt明确事实、unknown_fields和政策条件；历史/预计送达不能补齐未知字段。
3. reply_safety将有限文本断言与同一三态/天数事实对比，不是一律禁止“未签收”一句话。明确未签收时允许；条件、询问和不确定表述单独处理。
4. 无依据签收断言/天数产生unsafe_reply及fact_violations，不额外重试，LLMResponseAgent保留原安全模板和来源。
5. ResponseAgent的政策模板也使用相同receipt_summary，避免模型失败后又用模板误判。
6. 评测从实际query_order.data取事实，不相信历史或外部注入的facts字段；14条固定文本回归单独标为offline_fact_regression。

审查与回归确认：已发货不推出未签收、null不等于0、“签收后7天”等政策条件不被当成订单已满足事实；未知签收回复正常；缺物流不触发否定签收推断。错误回复仍回退；客户审批403、跨客户历史404、检查点恢复与单工单约束保留。

没有修改workflow.py、runtime.py、conversations.py、business_db.py、model_runtime.py、OpenAPI导出、依赖/锁文件或原测试断言。本次审查没有发现需要进一步重构或追加第三阶段功能的依据。文本规则仍不完备，不能宣称消除了所有自然语言幻觉。

## 4. 本次重新执行的离线验证

2026-10-23约19:57（UTC+8）执行，沿用已有.venv与前端依赖。以下是本次结果，不是历史复制。

| 检查 | 结果 |
|---|---|
| 完整Pytest | **158 passed，0 failed，34.83秒** |
| pip check | **No broken requirements found** |
| Vitest | **19 passed，0 failed，3个测试文件** |
| vue-tsc -b + vite build | **成功，37模块** |
| 80条规则意图 | 73正确/7错误；Accuracy=0.9125，Macro-F1=0.9208089669 |
| 20条TF-IDF检索 | Recall@1/3/5=0.95/0.95/1.0；MRR=0.9625；保留1条Top-3未命中 |
| 工作流A–J | **10/10**；8个完成、2个按预期待审核 |
| 原工作流HTTP/工具 | 21/22次2xx、15/16次工具ok；另有预期404与越权拒绝，不能删除它们凑100% |
| 回复/业务安全 | **6/6**；本次规则/模板，真实生成数0、人工复核数0 |
| 故障注入 | **6/6**；27次本地模拟调用，真实供应商调用0 |
| 签收固定文本回归 | **14/14**；包含危险断言被正确拒绝，非模型回答准确率 |
| 独立离线三轮 | **1/1**；原API/图/工具/审核恢复，实际模型调用0 |

原103项后端测试和断言保留；签收修复新增55个参数化执行用例，总数158。默认离线过程明确关闭模型；测试用临时数据库，故障由Mock注入，现有网络封锁用例通过。

实际执行命令：

```powershell
# 当前仓库根目录；专用basetemp首次使用，不删除旧测试目录
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.\.pytest_tmp_phase2_release --tb=short
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --mode offline
.\.venv\Scripts\python.exe -m evaluation.verify_qwen --mode offline
cd frontend
pnpm.cmd test
pnpm.cmd build
```

重跑默认报告前，已将evaluation/reports和evaluation/reports-e2e复制到本地忽略目录evaluation/reports-pre-release-20261023-archive；未删除原有实验。新默认Agent报告generated_at=2026-10-23T11:57:15.605863+00:00。复跑时请使用新的basetemp和新的--output，或先备份已有人工复核表。

## 5. 既有真实千问证据：保留失败与成功

### 来源与可追溯性

两目录的latest.json、summary.md、manual_review.csv均存在：

- evaluation/reports-e2e-facts-live：生成于2026-10-23T09:24:27.368857+00:00。
- evaluation/reports-e2e-facts-retest：生成于2026-10-23T09:32:24.874162+00:00。

两份均为mode=live，模型qwen3.7-flash-2026-07-15，endpoint_host=dashscope.aliyuncs.com，key_configured=true。只读取脱敏配置与业务结果，不读取或复制真实Key。两次报告记录的34个核心源码指纹均与本次审查工作区一致；人工表各4行pending，reviewer、reviewed_at未填。用户反馈的回复验收不是带签字的独立人工质量评分，本次未代填。

原始JSON的SHA256（只用于本地证据对应，不代表人工质量通过）：

```text
首次: 0b04f3e34485df4c3ac747565ea4407d3f64480b157ddc60aefd23964129f6f1
复测: a872e2e8fbaa646a991255f89ffb023f4001eec20e3427517bd2e72886171b20
```

原始报告继续本地忽略，不随公开提交上传；公开文档只保留此审查后的汇总，不发布会话ID、工单ID或整份运行轨迹。

### 首次：失败，不能归咎于安全误判

timeout_seconds=30、max_retries=0、预算8次。报告passed=0/1，实际4次尝试（intent/reply/intent/reply），3次输出通过校验、1次失败。第一轮llm_generated；第二轮fallback_template，error=provider_error，失败调用耗时**30031.8593ms**，turn_2_really_generated=false。

原审核、权限、恢复与幂等检查仍通过；端到端未通过的明确检查是第二轮没有真实模型生成。轨迹不是unsafe_reply，因此不能说签收安全校验误拦。耗时接近30秒设置，仅能怀疑超时关联；没有明确底层异常证据，根因尚未完全确认，不改写成已证实timeout。

### 复测：单个模拟三轮核心链路通过

timeout_seconds=90、max_retries=0、预算8次。报告passed=1/1，实际4次尝试，4次输出通过校验，失败0。

- 第一轮llm_generated：订单/状态/模拟物流正确，明确“目前无法确认是否签收及签收时间”，询问实际情况。
- 第二轮llm_generated：关联同一ORD1001，分开已知事实、未知字段和政策条件，引用refund_policy.md，没有声称已签收或尚未签收，也未批准退款。
- 第三轮为原approval interrupt的确定性提示；批准前零工单，客户审核403、其他客户读会话404。
- 重建WorkflowService后从SQLite检查点恢复原run；批准结果为确定性pass_through文本，恰好一张工单，重复批准和同键重发没有增加工单或重放模型，历史保存六条消息并对齐最终回复。
- 工单明确不代表退款或赔偿已获批准。

第三轮尚未执行LLMResponseAgent；批准后原步骤记录mode=pass_through。这两条按response_mode辅助函数归类为deterministic，不是两次模型调用。

配置快照intent_enabled=false取自进入沙箱前的进程，verify(live=True)会在隔离作用域临时启用意图模型；逐调用记录确有两次intent和两次reply。不能把配置快照误读为整次未使用模型分类。

**90秒是用户那次PowerShell进程覆盖，不是永久改动。代码默认仍为20秒超时、1次额外重试。本次没有修改.env或任何默认值。**

### 实际usage、耗时与费用边界

| 项目 | 首次 | 复测 |
|---|---:|---:|
| 有usage的尝试 / 全尝试 | 3/4，不完整 | 4/4，完整 |
| input_tokens | 1735 | 3178 |
| output_tokens | 2701 | 5480 |
| total_tokens | 4436，仅已返回部分 | 8658 |
| intent第1/第2次耗时ms | 3355.4050 / 3676.6688 | 3302.4007 / 3142.0205 |
| reply第1/第2次耗时ms | 21432.4296 / 30031.8593 | 18111.7735 / 27761.3171 |
| cost | null | null |

以上均为原报告记录，不补算失败调用Token、不估人民币费用。客户端尝试数是保守边界，不是供应商账单确认；usage字段只按SDK实际返回统计，不自行推断计费Token类别或免费额度。两次样本不足以给出生产P95、SLA或模型整体准确率。

## 6. 文件清单

| 文件 | 本次发布内容 |
|---|---|
| support_agent/order_facts.py（新增） | 签收三态、证据、未知字段、冲突和确定性说明 |
| support_agent/scoped_tools.py、tools.py | 原data外增加facts，不更改权限/业务写入 |
| support_agent/llm_client.py | 结构化事实Prompt和拒绝原因，保留调用接口与回退 |
| support_agent/reply_safety.py | 有限断言与统一事实比较，条件句不按单句黑名单处理 |
| support_agent/agents.py | 政策模板使用相同签收事实，不改图路由 |
| evaluation/evaluators/reply_eval.py | 原评测增加签收一致性与模型违规原因 |
| evaluation/evaluators/receipt_eval.py（新增） | 固定文本回归，0真实调用 |
| evaluation/datasets/receipt_cases.jsonl（新增） | 14个合成签收边界场景，仍待独立复核 |
| evaluation/run_evaluation.py | 报告和退出检查加入receipt，不扩大live预算 |
| tests/test_receipt_facts.py（新增） | 55个执行用例，含Prompt、网络封锁、真实图回退/审核/幂等 |
| README.md | 最新架构、158项回归、真实失败/成功证据与诚实限制 |
| docs/PHASE2_QWEN_VALIDATION.md | 当前验证结论、操作、签收边界与超时默认值说明 |
| docs/EVALUATION_GUIDE.md | 当前实测、usage分母、人工复核与面试表述 |
| docs/MULTI_TURN_ARCHITECTURE.md | 当前订单事实边界，不重写原架构 |
| docs/RECEIPT_FACTS_FIX_20261023.md（新增） | 保留修复开发过程与历史测试，增加最新记录入口 |
| docs/VERIFICATION_PHASE2_20261023.md | 历史103项记录增加当前版本指引，原结果保留 |
| docs/PHASE2_RELEASE_20261023.md（新增） | 本收尾记录 |

合计18个文件。现有前端代码、测试断言、依赖与锁文件没有变化，仍执行全套验证。

## 7. 安全发布方式

只允许显式暂存上述事实修复、测试和文档，不使用git add .。发布前检查未跟踪/暂存文件、diff、空白、敏感凭证样式和个人绝对路径；.env、数据库、缓存、dist、原始报告与报告备份继续被忽略。

真实.env只作SHA256前后比较，不读取Key正文。模型错误记录使用脱敏error_type，不发布供应商异常原文。没有新增依赖，pip check只证明现有依赖约束兼容，**不等于已执行CVE漏洞扫描**。

普通提交与推送，仅在上游明确且远程没有冲突时执行。不force、不reset、不clean、不覆盖他人提交。推送后以远程SHA及该SHA的backend/frontend CI确认发布；若远程变化、冲突或CI失败，必须在交付中明确说明，不能用历史成功结果替代。

## 8. 第二阶段项目成果与面试讲解

可使用的简历表述（个人工程项目，不虚构企业客户或实习）：

> 基于Vue 3、FastAPI、LangGraph与SQLite实现受控客服多Agent工作流，支持多轮订单/政策追问、ScopedTools权限、人工审核恢复和幂等建单；接入Qwen API，增加调用预算、usage记录及模型异常回退。针对“已发货+空签收”导致的错误推断建立结构化签收三态与回复约束，158项后端、19项前端测试通过，14个签收固定文本回归通过；真实千问单个模拟三轮场景复测通过，原始失败记录保留。

面试展开顺序：

1. 背景：客服不仅要回答，还必须重新验证订单归属、保留政策来源，并控制写操作。
2. 链路：前端带request_id → 会话服务去重/有界历史 → 新run或原run恢复 → LangGraph路由 → 授权订单工具与TF-IDF政策 → 模型回复校验 → 消息/检查点持久化。
3. 难点：不是加一句“别幻觉”，而是把缺失值建模为unknown；0天是事实，发货不是未签收证据，政策条件不是订单已满足条件。模型和模板共用结构化事实。
4. 写入：售后先interrupt，客服审批后原run继续，唯一键保证重复批准不重复建单；工单不是退款批准。
5. 结果：说清158/19是自动化测试数、14是固定文本回归、1/1是一个模拟live场景，不是生产准确率。首次provider_error保留，90秒复测成功不证明根因或解决全部超时。
6. 限制：模拟数据、待独立人工复核、单worker、有限语义规则；没有真实客户规模、生产SLA或已确认成本数字。

## 9. 尚未解决的问题与第三阶段建议（本次未开发）

- 首次provider_error的底层原因未确认；后续应在保护隐私的前提下增加可定位的错误证据与供应商问题跟踪。
- 独立人工复核和冻结测试集缺失；先复核标注与实际输出，再经授权扩大多场景live样本，建立真正可比较的基线。
- 文本事实检查不是完备语义防线；按新发现的真实错误补证据与边界，不堆句子黑名单或伪称零幻觉。
- SQLite和进程内锁主要适合单实例；后续只有在业务需求明确时再规划数据库、分布式并发控制、可观测性和恢复演练。
- 真实业务适配、企业身份生命周期、数据保留与脱敏、限流和正式生产验收尚未完成。
- 未实施向量数据库、Embedding、混合RAG、新Tool Calling流程或其他第三阶段功能；检索升级应由独立错误分析决定。

这是第二阶段受控工程链路的发布记录，不是“企业生产系统已全面验收”的证明。
