# Phase 3B 首轮 unsafe_reply 排查与离线回归（2026-10-27）

后续第二次真实验收已定位到missing_source，最新修复与427项后端/27项前端结果见
[missing_source精准修复记录](PHASE3B_MISSING_SOURCE_20261027.md)。第5节的最多8次、0重试命令继续适用；
以下首轮“原候选未知”等结论只描述第一次报告，不覆盖第二次已有的具体违规代码。

## 1. 结论与证据边界

基准分支 `feature/phase3b-safe-tool-calling`，基准提交 `ea8cdd994c92af0dd43a818a0d04dc699345509b`。
本轮不提交、不推送、不调用真实模型；下述真实调用数据来自用户此前运行。

检查了 `evaluation/reports-phase3b-acceptance-20261027-094657-554-live/` 下的 latest.json、details.csv、
manual_review.csv、summary.md。这些文件保留最终回退结果，没有被拒绝的模型原文或具体违规代码。
因此**无法证明原模型具体说错什么，也无法证明某条规则误判**，不能声称模型确实说了“尚未签收”。
原始报告没有修改。

确定的失败位置：第二次模型调用返回最终候选 → `validate_final` → 事实/必含字段校验失败 →
`ModelServiceError("unsafe_reply")` → 原确定性 Agent 回退。usage 在校验前已记录，
successful_calls=1 表示第一次工具提议被接受，不表示最终回答成功。

| 历史真实证据 | 核验结果 |
|---|---|
| 模型 | qwen3.7-flash-2026-07-15 |
| 请求尝试 / 校验成功 / 失败 | 2 / 1 / 1；第二次 unsafe_reply |
| 供应商 usage | input=1391，output=63，total=1454，usage_complete=true |
| 工具协议 | query_order 实际执行 1 次；原生 tool_calls、ToolMessage、ID 对应检查通过 |
| 会话/权限 | 第一轮 history=[]，显式 ORD1001，服务端用户 U1001；未发现旧历史或错误权限上下文证据 |
| 业务事实 | 已发货；received_days=null；receipt.state=unknown；退款资格 not_determined |
| 物流 | 顺丰，脱敏 SF***6789，预计 2 天内送达；预计时间不是送达事实 |
| 回退 | status=fallback；额外工具执行 0 次；同 run 已授权结果复用；没有工单 |
| 场景 | accept-1 generated=false，其他七项检查通过 |

## 2. 可复现问题与修复

旧校验要求保留已知订单号、原状态，以及无政策片段时的脱敏单号，旧 Prompt 却没有明确这些必含要求。
例如“订单ORD1001已发货，预计2天内送达。”不含虚构签收，但仍触发 missing_tracking_number。
这是**已复现的 Prompt/校验约定不一致**；没有原候选，不能证明它就是该次真实失败的具体原因。
修复让模型生成前拿到同一份合同，仍拒绝缺字段回答，没有放宽旧规则。

| 函数/文件 | 调整 |
|---|---|
| `tool_calling.reply_contract` | 从本 run 已授权脱敏数据生成必含字段、签收三态、未知字段、政策来源和未经证明的业务动作 |
| `ToolCallingAgent.run` | 强化最终回复 Prompt；ToolMessage 附加合同；不修改原工具数据、facts 或缓存 |
| `validate_tool_messages` | 下次请求前检查缺失/重复/孤立消息及工具名/ID 对应；失败不发送下一次请求 |
| `tool_reply_violations` | 继续原 reply_violations 和退款资格规则；补充只读工具无法证明的支付/审批成功断言检查 |
| `validate_final` | 保留 unsafe_reply；trace 增加 violations、签收态、必含字段/来源存在性；没有候选原文 |
| `reply_diagnostics.record_rejection` | 默认关闭、固定目录、元数据白名单和固定词汇有损投影；诊断失败不影响安全回退 |
| 测试/评测隔离 | 测试和 offline 关闭诊断；专用 live 工具入口保留显式进程环境 opt-in |

reply_safety.py、order_facts.py、模型客户端重试/计费逻辑、授权工具、LangGraph、人工审核、工单幂等与数据库结构未改。
已发货+null 仍为签收未知；没有按某一句实测回复添加例外。
补充支付/审批检查区分条件、询问、否定和不确定表达，仍是有限规则，不能证明任意中文语义安全。

## 3. 新增测试与实际结果

新增 `tests/test_tool_reply_safety.py` 共 **36 项**，通过真实 ChatOpenAI SDK + MockTransport 构造标准响应，
实际解析 AIMessage.tool_calls，并检查服务端 ToolMessage 与授权事实一致。覆盖：

- 正确订单/物流、签收未知、条件表达；缺订单号/状态/已知单号仍拒绝。
- 无依据已签收/尚未签收拒绝；明确已签收（含 0 天/天数未知）、未签收正常通过；物流缺失保持未知。
- 虚构退款、支付成功、审批通过拒绝；否定/条件/不确定表达通过。
- ID 不匹配、孤立/缺失/重复/工具名错误拒绝；越权不泄露；预算耗尽无额外请求；回退不冒充生成。
- 诊断默认/错误配置关闭、敏感值投影、白名单、写入失败、链接路径拒绝、50 文件上限及评测隔离。

Mock usage 仅测试计数逻辑，不是供应商 Token/账单。全部原测试断言与评测 gold 保留。

| 本轮执行 | 实际结果 |
|---|---|
| 初次定向回归 | 140 passed（新增测试早期版本 + 原工具/签收测试） |
| 最终新增测试文件 | 36 passed |
| 全部后端 .venv Pytest | **399 passed，71.77 秒** |
| pip check | No broken requirements found |
| 全部 Vitest | **27 passed，5 文件** |
| vue-tsc + Vite build | 成功，39 模块 |
| 原 Agent offline | 工作流10/10、回复6/6、故障6/6、签收14/14；意图Accuracy=0.9125 |
| 3A compare_rag offline | 完成原20+16题三模式；source=mock_dense，真实Embedding请求0 |
| 固定3B工具场景 | 36/36符合工程预期；原始选择29/36，参数23/32，实际读取17/20，阻断11/11，回退24/36 |
| 原 verify_qwen offline | 1/1，原审核、恢复、幂等保留 |
| 新 verify_tool_calling offline | 1/1，4次脚本尝试，第3轮仍停人工审核，未建单 |

新报告位于 `evaluation/reports-{agent,rag,tools,legacy-e2e,tool-e2e}-unsafe-reply-20261027-review-v1/`。
均为新建本地忽略目录，不覆盖历史报告。真实聊天/Embedding 调用均为 **0**。
3A Mock Dense 仅作工程回归，不能当真实向量效果；困难集3条无依据问题仍返回候选，自动安全拒答尚未验证。

安全复核：真实 .env 的 SHA256 与排查前一致；排查前记录的 **198 个既有缓存、业务 SQLite 和历史报告文件**
逐文件摘要全部一致。12个本轮源码/测试/必要文档变更经已配置密钥比对及常见凭证格式扫描，无匹配；
Git 未跟踪 .env、缓存、数据库、临时测试目录、运行报告或本地诊断，暂存区仍为空，HEAD 未变。
git diff --check 通过。初次对 llm_client.py/scoped_tools.py 的 blob 字节比对因 checkout 的 CRLF 不同而失败，
随后分别验证 Git diff 为空、统一换行后内容一致；未为此改写文件。五份新报告的源码/数据集指纹与最终源码一致。

## 4. 受控本地诊断

未来另行授权真实验收时，可在同一个 PowerShell 设置 `$env:LLM_REPLY_DIAGNOSTICS_ENABLED = 'true'`。
拒绝时公共 trace 只有代码/布尔摘要及 local_diagnostic 保存状态；本地目录是 `.local_diagnostics/reply_safety/*.json`，
已被 Git 和 Docker 忽略。设置为 `'false'` 可关闭，不修改 .env。

文件只保留固定非身份词汇（如“已签收”“未知”“审批”）的有损顺序投影，其余内容替换为“〈隐藏〉”，
不保存原文、订单号、物流号、姓名、电话、地址或 Key；另存候选SHA256、长度及run哈希。
最多50文件，满额停止新增，不删除旧文件；不接受自定义外部路径，拒绝符号链接/目录联接。
Windows权限继承本地用户目录ACL，不宣称跨用户/管理员不可读。投影不能恢复完整语句，也不能补回历史候选。
不要为排查而开启SDK/HTTP原文debug日志；不要把本地报告/诊断提交GitHub。

## 5. 后续最多8次、0重试的真实验收（本轮未执行）

建议另行授权一次小规模三轮验收，保留拦截并检查具体 violations；不自动扩大36题、不放宽规则或加预算。
以下参数已核对现有 parser 和 `--help`，live 命令收费，本轮只准备：

```powershell
$ErrorActionPreference = 'Stop'
$projectRoot = 'C:\Users\yymmxr\Documents\ChatGPT\企业客服多Agent系统'
Set-Location -LiteralPath $projectRoot
$python = (Resolve-Path -LiteralPath '.\.venv\Scripts\python.exe').Path
$env:PYTHONIOENCODING = 'utf-8'
$env:LLM_TIMEOUT_SECONDS = '90'
$env:LLM_MAX_RETRIES = '0'
$env:LLM_TOOL_CALLING_ENABLED = 'true'
$env:LLM_INTENT_ENABLED = 'false'
$env:RAG_MODE = 'tfidf'
$env:EMBEDDING_ENABLED = 'false'
$env:RAG_REMOTE_QUERY_ENABLED = 'false'
$env:LLM_REPLY_DIAGNOSTICS_ENABLED = 'true'
$env:OPENAI_LOG = 'error'
foreach ($name in @('LANGSMITH_TRACING', 'LANGSMITH_TRACING_V2', 'LANGCHAIN_TRACING', 'LANGCHAIN_TRACING_V2')) {
    Set-Item -Path "Env:$name" -Value 'false'
}
& $python -c "from pathlib import Path; import evaluation.verify_tool_calling as v; import support_agent.tool_calling as t; r=Path.cwd().resolve(); assert Path(v.__file__).resolve()==r/'evaluation'/'verify_tool_calling.py'; assert Path(t.__file__).resolve()==r/'support_agent'/'tool_calling.py'; assert callable(t.reply_contract); print('source_check=OK')"
if ($LASTEXITCODE -ne 0) { throw '修复代码路径核验失败，停止。' }
& $python -m evaluation.verify_tool_calling --check-config
if ($LASTEXITCODE -ne 0) { throw '配置或合成数据预检失败，停止。' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$reportDir = Join-Path $projectRoot "evaluation\reports-tool-live-unsafe-review-$stamp"
if (Test-Path -LiteralPath $reportDir) { throw '报告目录已存在，停止以免覆盖。' }
# 仅在另行授权后手动执行下面的付费命令：
& $python -m evaluation.verify_tool_calling --mode live --allow-remote --max-model-calls 8 --output $reportDir
$verifyExit = $LASTEXITCODE
Write-Host "本地验收报告：$reportDir"
if ($verifyExit -ne 0) { throw '验收失败，已停止后续场景并保存报告；不要自动重试。' }
```

该CLI强制重试0、Embedding关闭、TF-IDF；单节点最多4次，全场最多8次（不是金额/Token限额），
使用固定合成数据与隔离临时SQLite，第3轮停人工审核。
任一轮unsafe_reply、协议/权限异常、预算耗尽或检查失败，CLI立即停止后续场景并导出已有结果，
失败退出码为1；不需要等三轮结束后才检查。新 violations 位于
latest.json 的 e2e.cases[0].results[*].tool_calling_trace.reply_validation.violations，
details.csv 和 tool_review.json 也保留同一份trace；只包含代码/摘要，没有被拒绝的候选原文。
先审报告，不自动换模型/加额度；预检失败发生在外发前，无法保证磁盘损坏、强制终止等情况仍可写报告。
仅通过这一轮也不代表全36题真实效果或完整语义安全，人工语言/政策复核仍待完成。

## 6. 复测命令专项核对（2026-10-27，未调用真实API）

专项检查发现旧verify_tool_calling先发送完三轮再检查结果，PowerShell末尾的throw只能阻止再次运行，
不能阻止第一轮失败后继续第二轮。本次仅在已有入口补充逐轮检查，失败立即跳出并继续写入部分报告。
保留原有全部验收检查，没有降低通过条件；新增failure_stage和stopped_after_turn便于定位。
第三轮检查失败时也不会继续执行重放/权限复验。

新增tests/test_tool_acceptance_failfast.py共11项，验证首轮/次轮unsafe_reply和timeout停止，
共享预算1/3耗尽停止，事实检查/第三轮失败停止，支付与审批违规代码进入报告，
被拒绝的候选标记不进入任何报告/日志，Embedding调用被禁止。
定向97项通过；全量后端410项通过（52.70秒）；现有CLI的offline三轮1/1、4次脚本尝试通过。
新离线报告：evaluation/reports-tool-e2e-command-check-20261027/。本轮未改前端，也未重跑前端测试。

文档完整命令通过Windows PowerShell 5.1.26100.9444和PowerShell 7.6.5语法检查，
其中源码路径检查片段在两者均实际执行成功。项目Python为.venv中的3.11.7，导入的是本目录
evaluation/verify_tool_calling.py及修复后的support_agent/tool_calling.py，不依赖已提交或已推送版本。
实际执行的check-config仅显示key_configured=true、模型qwen3.7-flash-2026-07-15、
主机dashscope.aliyuncs.com、超时90、重试0、模拟指纹匹配和network_calls=0；不证明线上权限/额度。

每次_call先向共享CallLedger预占，节点ScopedCallLedger引用同一父账本；总上限8、节点上限4，
SDK同步/异步隐式重试为0，工具入口也强制额外重试0。回退不会调用旧回复模型，售后仍走原人工审核。
Sandbox使用TemporaryDirectory和模拟身份/订单，只把query_order与search_policy两个只读工具提供给模型，
强制TF-IDF且禁止Embedding和远程查询，不操作原业务库或向量缓存。

最终命令在导入SDK之前关闭OPENAI调试日志和两种前缀的LangSmith/LangChain自动追踪。
只有本地默认关闭的有损诊断可显式启用，拒绝原文不出现在公共trace或日志。
本次真实聊天/Embedding请求均为0，没有修改.env或执行Git暂存、提交、推送。
