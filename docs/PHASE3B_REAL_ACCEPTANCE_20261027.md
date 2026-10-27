# Phase 3B 真实Qwen验收与最终本地交付（2026-10-27）

## 1. 交付结论和范围

在feature/phase3b-safe-tool-calling分支、基准ea8cdd994c92af0dd43a818a0d04dc699345509b上，
完成既有修复的最终安全审查、全量离线复跑和文档收尾。本轮没有重新开发Phase 3B、进入后续阶段或请求真实模型。
本地提交使用fix(agent): harden safe tool calling and validate live Qwen flow；
实际提交SHA以本报告所属Git记录及最终交付回复为准，不在提交文件中嵌入自身SHA。

用户第三次真实验收的**一组固定模拟业务三轮场景**符合工程预期。真实的是Qwen模型通信；
订单、身份、政策和数据库仍是隔离的模拟环境。不是全36题真实准确率、人工语言质量通过或生产上线证明。

## 2. 精确真实报告与安全摘要

通过实际目录枚举确认唯一匹配：

~~~text
evaluation/reports-tool-live-third-20261027-165002-913/latest.json
SHA256: 1ed2ee0c5830e023971c5ba729a0bc26a23623cd31ad012cab9bf65711216921
~~~

原始JSON、CSV和诊断保留本地并由Git忽略；本文只保留汇总和必要的模拟/脱敏证据。
验收报告的50个源码指纹及全部数据集指纹与本轮交付源码一致。没有为结果修改gold或供应商用量。

| 指标 | 真实报告记录 |
|---|---|
| 模型 / 端点主机 | qwen3.7-flash-2026-07-15 / dashscope.aliyuncs.com |
| 共享模型请求预算 / 实际尝试 | 8 / 5 |
| 确定性校验成功 / 失败 | 5 / 0；不是五个独立业务场景 |
| 额外重试 / 超时设置 | 0 / 90秒；5个调用记录均attempt=1 |
| 供应商返回Token | input=5476，output=364，total=5840；usage_complete=true |
| 金额 | 未核对实际账单，不编造人民币费用 |
| 三轮场景 | 1/1符合工程预期，24个自动检查均true |
| 人工复核 | pending；manual_review.csv的3行均未填写reviewer |

| 轮次 | 模型/工具证据 | 最终状态 |
|---|---|---|
| 订单查询 | 2次模型尝试；query_order授权执行1次；订单号、原状态、脱敏单号检查通过；签收仍unknown | completed / model_generated / violations=[] |
| 退款政策 | 3次模型尝试；query_order与search_policy各执行1次；3片段来自refund_policy.md、shipping_policy.md；回答含【来源：refund_policy.md】 | completed / model_generated / violations=[]；policy_source_present=true；receipt_state=unknown |
| 售后申请 | 新模型尝试0；guarded_workflow；转入原approval interrupt；原工作流可以进行确定性只读查询 | awaiting_review，未建单 |

第一轮没有政策来源，policy_source_present=null符合预期。第二轮只需引用实际来源集合中至少一个完整标识，
并非必须引用所有片段；任何可识别的未知来源仍拒绝。模型路径只读执行共3次，不把第三轮原工作流的读取混入模型自主调用次数。

在线检查还包括同会话独立run、订单上下文、普通客户审批403、另一客户无法读会话、SQLite待审核状态恢复、
重复request_id返回原run、重放和权限复验无额外模型请求、始终无工单。
在线流程**没有实际批准售后**；批准后的幂等建单等正向写入行为由本轮完整离线回归覆盖。

## 3. Tool Calling到安全回复的完整链路

~~~mermaid
flowchart TD
  A[认证身份与服务端订单上下文] --> B{规则识别是否敏感业务}
  B -->|售后/投诉/人工| R[原LangGraph审核interrupt]
  B -->|低风险| C[bind_tools固定两个只读schema]
  C --> D[Qwen返回标准AIMessage.tool_calls]
  D --> E[整批名称/参数/ID/轮数/预算校验]
  E --> F[ScopedTools校验绑定客户和订单归属]
  F --> G[裁剪脱敏结果/签收三态/真实来源合同]
  G --> H[ToolMessage按tool_call_id对应]
  H -->|预算内继续| C
  H --> I[模型最终候选]
  I --> J[validate_final事实与来源校验]
  J -->|通过| K[model_generated]
  E -->|失败| L[受控拒绝或原模板回退]
  J -->|unsafe_reply| L
  R -->|仅客服接口审核通过| T[原TicketAgent幂等建单]
~~~

模型白名单只有query_order/search_policy，使用真实bind_tools与ToolMessage协议，没有把Prompt里的普通JSON当执行器。
参数由strict Pydantic schema验证，身份/run绑定由服务器复核，订单号必须等于本轮确认上下文，
ScopedTools再校验真实归属；模型不能通过历史或额外字段传入user_id/approved。
create_ticket、approve_refund、SQL、代码、任意URL均不在白名单；仅授权客服接口能恢复原审核图。

ScopedCallLedger引用CLI共享父账本，发送前预占；所有节点累计不超过8，单节点最多4次，工具轮数最多2。
SDK同步/异步隐式重试关闭，验收入口额外重试0；模型提议、实际读取、缓存复用和回退读取分开计数。
订单无权访问时直接拒绝，不再交给模型回答。模型失败仍保留真实失败代码/usage，模板不冒充model_generated。

## 4. 两次失败如何修复

1. 首轮query_order原生协议已成功，但最终unsafe_reply。报告没有被拒绝原文或细分代码，
   无法断言是具体哪句话违规或安全校验误判。复现了必含订单字段与原Prompt不够明确的问题，
   新增结构化reply_contract、明确签收三态和必含字段，并记录违规代码/布尔摘要。
2. 验收CLI原先三轮发完才检查，改为每轮立刻判定；失败保留部分报告并停止后续场景，预算不加码。
3. 第二轮真实验收在turn_2失败，唯一missing_source，policy_source_present=false。
   工具已返回refund_policy.md；原Prompt虽要求保留source，但缺少完整文件标识和引用示例。
   根据本轮实际来源动态生成policy_citation，并明确推荐格式，不修改校验器、不在任意回答尾部追加固定文件。
4. 第三次真实验收来源与订单事实检查通过。首轮未知原文的证据限制依然保留，不事后编造首轮原因。

详细历史见[unsafe_reply排查](PHASE3B_UNSAFE_REPLY_20261027.md)和[missing_source修复](PHASE3B_MISSING_SOURCE_20261027.md)。

reply_safety.py及missing_source/unsupported_source/unsafe_reply门禁未被删除或放宽。
诊断默认关闭，只能显式开启本地固定词汇有损投影；不保存拒绝原文，公共trace只有代码、枚举、布尔和保存状态。
本地最多50文件，失败不阻止安全回退；Git和Docker均排除该目录。它不是完整可恢复的原文脱敏器。

## 5. 本轮重新执行的离线验证

运行环境：项目.venv Python 3.11.7；Node 24.21.0；pnpm 11.19.0。
CI/Docker配置为Python 3.12，本次没有触发云端CI，不能把本地3.11测试冒称为本分支CI结果。

| 本轮命令/检查 | 实际结果 |
|---|---|
| 全部Pytest | 427 passed，54.66秒 |
| pip check | No broken requirements found |
| 全部Vitest | 27 passed，5文件 |
| vue-tsc + Vite build | 成功，39模块 |
| evaluate_tool_calling offline | 36/36符合工程预期；原始选择29/36、参数23/32、实际读取17/20、安全阻断11/11、回退24/36 |
| verify_tool_calling offline | 1/1；4次脚本尝试；第3轮待审核 |
| verify_qwen offline | 1/1；旧审核、恢复和幂等保留 |
| compare_rag offline | 原20+16题三模式回归完成；source=mock_dense，真实Embedding调用0 |
| 原Agent offline | 工作流10/10、回复6/6、故障6/6、签收14/14；意图Accuracy=0.9125 |

工具评测的故意错误模型提议没有通过回退修正成“模型选对”；36/36是工程预期符合率，不是Qwen准确率。
脚本模型尝试及SDK Mock usage不算供应商真实请求/费用，3A Mock Dense不算真实语义向量效果。
新报告目录为evaluation/reports-{tools,tool-e2e,legacy-e2e,rag,agent}-phase3b-delivery-20261027-final/，
均为独立忽略目录，不覆盖历史文件。本轮新增真实聊天/Embedding请求均为0。

## 6. Windows本地运行和演示

在VS Code打开现有ServiceFlow仓库，根目录新PowerShell终端运行；无需重新安装环境，不修改.env：

~~~powershell
$env:LLM_TOOL_CALLING_ENABLED = 'false'
$env:LLM_API_KEY = ''
$env:LLM_INTENT_ENABLED = 'false'
$env:RAG_MODE = 'tfidf'
$env:EMBEDDING_ENABLED = 'false'
$env:RAG_REMOTE_QUERY_ENABLED = 'false'
.\.venv\Scripts\python.exe -m uvicorn support_agent.app:app --reload --host 127.0.0.1 --port 8000
~~~

另一仓库根目录终端运行：

~~~powershell
Set-Location frontend
pnpm.cmd dev
~~~

打开http://127.0.0.1:5173，后端文档http://127.0.0.1:8000/docs。
使用现有开发凭证或自己配置的身份，依次查询ORD1001、追问退款、申请售后；
第三轮待审核，只有客服角色才能批准，批准后仍使用原run与幂等键。
以上是完全离线网站演示，没有Qwen工具规划；截图中的旧聊天/审核界面不能当真实Tool Calling证据。
临时验收数据库已销毁，第三次真实验收的run不会自动出现在网站历史；可直接用VS Code查看既有本地JSON/CSV，无需重新付费。

新工具链路的离线实操可用已有CLI（新时间戳保护历史报告）：

~~~powershell
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
.\.venv\Scripts\python.exe -m evaluation.evaluate_tool_calling --mode offline --output "evaluation/reports-tools-demo-$stamp"
.\.venv\Scripts\python.exe -m evaluation.verify_tool_calling --mode offline --output "evaluation/reports-tool-e2e-demo-$stamp"
~~~

将来若需要重新发起真实模型验收，必须另行明确授权；[演示手册](PHASE3B_DEMO.md)和
[已核实的8次/0重试命令](PHASE3B_UNSAFE_REPLY_20261027.md#5-后续最多8次0重试的真实验收本轮未执行)保留受控入口。
网站只有节点级上限，没有整场CLI共享总额，不用连续网站发问代替8次预算验收。

## 7. 审查范围与交付文件

本轮没有新增依赖、改动业务数据库schema、放宽旧断言或修改gold。对比真实报告的50个源码指纹均一致，
即交付审查无需再次修改已通过的生产代码。reply_safety、ScopedTools、LangGraph和原人工审核代码也复核通过。

本地提交覆盖此前待提交修复及本轮交付文档：

| 分组 | 文件 |
|---|---|
| 运行时 | support_agent/tool_calling.py、support_agent/reply_diagnostics.py |
| 评测 | evaluation/evaluate_tool_calling.py、evaluation/sandbox.py、evaluation/verify_tool_calling.py |
| 测试 | tests/conftest.py、tests/test_tool_reply_safety.py、tests/test_tool_acceptance_failfast.py、tests/test_tool_policy_citations.py |
| 配置保护 | .gitignore、.dockerignore、.env.example（默认关闭诊断，不是真实.env） |
| 公开文档 | README.md；docs/PHASE3B_DEMO.md、PHASE3B_VERIFICATION.md、PHASE3B_SAFE_TOOL_CALLING.md、PHASE3B_UNSAFE_REPLY_20261027.md、PHASE3B_MISSING_SOURCE_20261027.md、PHASE3B_REAL_ACCEPTANCE_20261027.md、PHASE3B_PR_BODY.md |

真实.env、API Key、运行时Authorization值、真实客户资料、SQLite、向量缓存、诊断和原始报告均不纳入提交。
代码中的鉴权字段名及显式模拟测试凭证不代表真实抓取的Authorization Header。
没有自动Push、建PR、Merge、Rebase或删除分支；PR正文另存为PHASE3B_PR_BODY.md供后续人工执行使用。

## 8. 仍未覆盖的生产风险

- 人工表3行pending；礼貌、清晰度、完整政策条件及用户问题是否解决仍需独立复核。
- 只有一组固定模拟业务真实三轮；没有证明36题真实Qwen选择率、独立留出集泛化或ROI。
- 有限文本规则不能证明全部中文改写/提示注入的语义正确性；3A三条无依据问题自动拒答仍未验收。
- 没有企业SSO、多租户政策权限、真实企业API接入、全输入PII治理或完整日志保留策略。
- 共享请求上限是单CLI进程的尝试数，不是账户人民币上限；重启/跨进程不共享配额，checkpoint前崩溃可能重放只读/模型请求。
- SQLite与进程锁适用于单实例；未验收多worker、并发压测、分布式事务、灾难恢复或生产SLA。
- 当前本地提交没有本分支新云端CI；main徽章和历史CI不能当作该提交已验证。

## 9. 提交前安全门禁实测

20个明确文件已逐项核对，最大约31KB；未发现已配置真实密钥或常见私钥/Token格式泄露。
真实.env摘要与审查前一致，251个既有业务SQLite、向量缓存、历史报告和本地诊断逐文件摘要一致，未清理或覆盖。
Git忽略规则覆盖.env、缓存、数据库、诊断、临时测试目录、运行报告和前端构建产物；禁止产物的跟踪数量为0。
真实报告及5份新离线报告的源码/数据集指纹与当前版本一致，原gold及旧安全/业务核心文件保持不变。
git diff --check通过，公开文档的本地链接有效。提交只使用显式20文件名单，不使用git add .或强制加入忽略文件。
本机当前PATH未检出gh；本地提交无需安装它，后续PR命令需先安装并登录GitHub CLI，或推送后在GitHub网页发起PR。
