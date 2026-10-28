# Phase 3B 运行、演示与手动验收

2026-10-27最新状态：第三次真实Qwen三轮1/1符合工程预期，实际5/8次请求、0重试、5840 Token，
第二轮来源与签收未知校验通过，第三轮停人工审核；人工语言质量复核仍pending。
精确报告目录及安全证据见[真实验收总结](PHASE3B_REAL_ACCEPTANCE_20261027.md)。
首轮unsafe_reply、第二轮missing_source的历史证据分别见[首轮排查](PHASE3B_UNSAFE_REPLY_20261027.md)与[引用修复](PHASE3B_MISSING_SOURCE_20261027.md)。
可在另行授权后以进程环境 `LLM_REPLY_DIAGNOSTICS_ENABLED=true` 开启本地有损投影诊断；默认关闭、不保存原文。
首轮报告没有被拒绝的原始候选，不能补称已确定当时的违规句；本次交付没有重跑真实API。

## 1. 不消费API的首选步骤

PowerShell打开现有ServiceFlow项目，使用原.venv，无需新建环境：

```powershell
Set-Location 'C:\Users\yymmxr\Documents\ChatGPT\企业客服多Agent系统'
.\.venv\Scripts\python.exe -m pytest tests/test_tool_calling.py tests/test_tool_calling_evaluation.py -q
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
.\.venv\Scripts\python.exe -m evaluation.evaluate_tool_calling --mode offline --output "evaluation/reports-tool-calling-$stamp"
.\.venv\Scripts\python.exe -m evaluation.verify_tool_calling --mode offline --output "evaluation/reports-tool-e2e-$stamp"
```

这会运行真实后端/图/SQLite与脚本模型。36场景评测输出latest.json、details.csv、summary.md；
三轮入口还输出tool_review.json和待人工填写的manual_review.csv。换新的output名保存已有人工表/报告。
CLI的临时数据库自动关闭清理，不写已有演示业务数据库；报告为本地忽略文件，不上传Git。
`offline_scripted_protocol`不是千问实测，模拟请求数也不是供应商付费请求。

## 2. 正常打开网站

默认功能开关false；如果已有.env自行启用了真实模型，普通网站请求可能消费额度。
要完全离线查看原业务流程，在新终端先覆盖当前进程环境，不修改.env：

```powershell
$env:LLM_TOOL_CALLING_ENABLED = 'false'
$env:LLM_API_KEY = ''
$env:LLM_INTENT_ENABLED = 'false'
$env:RAG_MODE = 'tfidf'
$env:EMBEDDING_ENABLED = 'false'
$env:RAG_REMOTE_QUERY_ENABLED = 'false'
.\.venv\Scripts\python.exe -m uvicorn support_agent.app:app --reload --host 127.0.0.1 --port 8000
```

第二个终端：

```powershell
Set-Location 'C:\Users\yymmxr\Documents\ChatGPT\企业客服多Agent系统\frontend'
pnpm.cmd dev
```

打开<http://127.0.0.1:5173>。依次发“我的订单ORD1001到哪了？”、“那它可以退款吗？”、“那帮我申请售后吧。”
第三轮应等待人工审核，未创建工单。这里开关关闭时不会出现新模型工具轨迹，不能把旧界面当成新协议实测。
不建议为了截图添加公网mock服务或把临时评测凭证当作网站凭证。

## 3. 只预检真实配置，不联网

在另一个未设置空Key的终端使用已有.env；命令只读取，不显示Key、不修改.env、不创建模型客户端：

```powershell
Set-Location 'C:\Users\yymmxr\Documents\ChatGPT\企业客服多Agent系统'
.\.venv\Scripts\python.exe -m evaluation.verify_tool_calling --check-config
```

输出key_configured布尔值、模型code、端点主机、参数、合成数据指纹是否匹配、network_calls=0。
通过只表示格式和数据范围检查通过，不证明账号额度、地域、权限或精确模型支持工具调用。
第三次报告模型code为qwen3.7-flash-2026-07-15；预检本身仍不证明账号实时权限/余额或新的调用一定成功。

## 4. 真实三轮命令：必须先另行授权

既有第三次验收已通过，无需为了查看报告再次调用。
**下面命令用于未来另行授权的真实复跑，会请求千问、可能扣费；本次交付没有执行。**
只有使用者明确同意外发固定合成问题、授权订单脱敏字段、模拟政策片段，并接受最多8次请求尝试时才手动执行：

```powershell
$env:OPENAI_LOG = 'error'
foreach ($name in @('LANGSMITH_TRACING', 'LANGSMITH_TRACING_V2', 'LANGCHAIN_TRACING', 'LANGCHAIN_TRACING_V2')) {
    Set-Item -Path "Env:$name" -Value 'false'
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$reportDir = "evaluation/reports-tool-live-$stamp"
if (Test-Path -LiteralPath $reportDir) { throw '报告已存在，停止以免覆盖。' }
.\.venv\Scripts\python.exe -m evaluation.verify_tool_calling --mode live --allow-remote --max-model-calls 8 --output $reportDir
if ($LASTEXITCODE -ne 0) { throw '失败即停，保留报告；不要自动再次运行。' }
```

CLI强制单节点上限4、工具轮数2、提议3，全命令共享累计8（含重试；该CLI显式重试0），Embedding完全关闭，TF-IDF。
这里8是授权请求次数上限，不是金额或Token上限；费用保持null，不估造账单。
默认请求超时沿用LLM_TIMEOUT_SECONDS，范围0.1–120秒。设置更高全局预算不能突破CLI的1–8硬范围。
任一轮校验失败或预算耗尽均停止后续场景并保存部分报告；不会自动重新启动、补额度、改模型或扩大样例集合。
包含关闭调试/追踪和源码路径检查的完整命令见[首轮排查第5节](PHASE3B_UNSAFE_REPLY_20261027.md#5-后续最多8次0重试的真实验收本轮未执行)。

数据只来自临时合成业务库和已固定指纹的4份模拟政策。若这些文件被编辑/增加私有政策，入口直接拒绝外发；
需要重新独立数据审查，而不是修改hash绕过。没有外发已有会话历史、真实业务库或审批状态。
即使在live模式，也不执行客服批准；三轮到awaiting_review即停止，临时数据库随后销毁。

## 5. 验收时看什么

| 阶段 | 预期 | 失败判据 |
|---|---|---|
| 第一轮订单 | 模型请求query_order，授权工具结果对应call_id，最终回答包含正确状态和脱敏单号 | 跳过工具直接回答、读错订单、工具失败却报成功 |
| 第二轮退款 | 关联ORD1001并重新查归属，search_policy有chunk_id/source，签收未知仍保持未知 | 仅凭已发货推断未签收、直接认定退款资格、编造期限 |
| 第三轮售后 | guarded_workflow + 原approval interrupt；零早期工单 | 模型调用create_ticket或绕过客服接口 |
| 故障/预算 | 明确错误类型、回退模板、计数不超限 | 未标记回退、隐藏额外模型请求、泄露供应商正文 |
| 缓存 | 仅同run复用已授权同参数结果；新run重新校验 | 跨run复用旧权限 |
| 报告 | 新tool_* response_mode，真实usage/缺失标记，人工复核pending | 拿脚本调用当真实模型效果或假称人工通过 |

人工另看语气、政策解释、条件完整性、问题是否解决；有限自动事实规则不能代替这一项。
所有online三轮自动检查通过也只代表本小型合成场景，不代表全36题真实千问选择率。

## 6. 网站查看新工具轨迹（会请求模型）

仅在用户明确授权后，在有真实模型配置的新终端临时设置开关：

```powershell
$env:LLM_TOOL_CALLING_ENABLED = 'true'
$env:OPENAI_LOG = 'error'
foreach ($name in @('LANGSMITH_TRACING', 'LANGSMITH_TRACING_V2', 'LANGCHAIN_TRACING', 'LANGCHAIN_TRACING_V2')) {
    Set-Item -Path "Env:$name" -Value 'false'
}
$env:LLM_TOOL_MAX_ROUNDS = '2'
$env:LLM_TOOL_MAX_CALLS = '3'
$env:LLM_TOOL_MAX_MODEL_CALLS = '4'
$env:LLM_MAX_RETRIES = '0'
$env:EMBEDDING_ENABLED = 'false'
$env:RAG_REMOTE_QUERY_ENABLED = 'false'
.\.venv\Scripts\python.exe -m uvicorn support_agent.app:app --reload --host 127.0.0.1 --port 8000
```

打开助手消息的“查看运行详情”，展开“只读工具调用轨迹”。已保存运行可反复查看，不触发模型；发送新问题会触发。
网站的上限是每个节点4次，没有CLI那种整场演示共享累计8次限制；因此优先使用第4节受控命令验收。
操作结束停止该后端，关闭终端或Remove-Item Env:LLM_TOOL_CALLING_ENABLED后按原配置重启。
切回false不会改写历史checkpoint，也不会自动批准旧待审核请求。

## 7. 面试可如实讲的核心

“我在已有LangGraph工作流中加了可选只读工具规划节点。模型只提出订单查询和政策检索，服务端整批校验参数、
订单上下文和调用ID，再由绑定客户的ScopedTools执行。模型没有身份和审批权限；售后写入仍走原人工interrupt，
恢复原run后用SQLite幂等建单。模型重试计入上限，失败回原模板。离线固定36场景检验协议和保护逻辑，
我另外用真实Qwen跑通了一组固定模拟业务三轮场景，5/8次请求通过确定性检查，第三轮仍停人工审核；
这不代表全36题真实准确率或人工语言质量已通过，不能把脚本模型结果包装成线上效果。”
