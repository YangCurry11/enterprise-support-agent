# Phase 3B 验证与本地交付记录（2026-10-27）

最新状态：用户第三次真实Qwen三轮1/1符合工程预期，5/8次模型请求、5成功/0失败、5840 Token，
来源/签收未知/原人工审核等24项自动检查通过；人工表3行仍pending。
精确目录、安全汇总、完整链路和生产限制见[真实验收总结](PHASE3B_REAL_ACCEPTANCE_20261027.md)。
本轮交付重新执行**427项后端、27项前端**，生产构建、pip check、固定36场景、新旧三轮、3A离线检索与原Agent offline全部完成，
详见第11节；新增真实模型请求0，仅在审查通过后创建本地提交，不Push或Merge。
第1–10节保留2026-10-26历史开发/审查记录，363项和“真实未执行”仅描述当时。
首轮未知原文的证据边界和第二次missing_source记录分别保留在对应排查文档，不以最终成功覆盖历史失败。

## 1. 结论与Git边界（历史，最新见第11节）

本节记录首次离线开发轮：当时完成可选只读Tool Calling的工程实现与验证，尚未执行真实千问验收。
本轮**真实聊天模型调用0、真实Embedding调用0**，没有修改.env，没有构建真实向量索引，没有上传业务数据。

- 基准main：`0a4b8e433c57cda1cd7751d14d03b880d44adfc1`。
- [3A PR #1](https://github.com/YangCurry11/enterprise-support-agent/pull/1)已由用户合并。
- 开发前main工作区干净；项目.venv执行299 passed（39.22秒）。
- 已核对该main的[CI run 40279405334](https://github.com/YangCurry11/enterprise-support-agent/actions/runs/40279405334)为success。
- 本次分支：`feature/phase3b-safe-tool-calling`，从origin/main建立并取消自动上游，避免误推main。
- 首次开发轮未执行git add/commit/push，HEAD当时仍为基准SHA；本次用户另行授权最终审查与本地提交，见第10节。
- 本分支没有新的云端CI结果；不能将main历史CI或本地测试冒充本分支CI。

## 2. 改动文件

| 文件 | 变更 |
|---|---|
| `support_agent/tool_calling.py` | 新增固定只读schema、ScopedCallLedger、执行器、消息循环、脱敏结果与回退 |
| `support_agent/workflow.py` | 可选safe_tools节点、规则保护高风险、旧分支与确定性响应 |
| `support_agent/agents.py` | AgentState默认空轨迹、IntentAgent可选跳过模型分类 |
| `.env.example` | 4个默认关闭的配置示例；真实.env未改 |
| `evaluation/evaluate_tool_calling.py` | 独立36场景离线评测、真实图/工具、故障注入、显式指标分母 |
| `evaluation/tool_calling_fakes.py` | 可追踪协议模拟器；超时/429/格式/注入/循环等故障，不是Qwen |
| `evaluation/verify_tool_calling.py` | 新三轮原服务入口、live门槛、固定合成数据外发范围与请求预算 |
| `evaluation/datasets/tool_calling_cases.jsonl` / `TOOL_CALLING_README.md` | 固定预期与AI辅助/待独立人工复核声明 |
| `evaluation/sandbox.py` | 旧离线评测强制关闭新开关，保持原评测语义 |
| `evaluation/run_evaluation.py` | 人工表根据新轨迹标记tool_*，不误标成旧回复模式；旧模式不变 |
| `tests/test_tool_calling.py` / `test_tool_calling_evaluation.py` | 首次新增52项，最终审查再新增12项，共64个后端执行用例（含参数化） |
| `tests/conftest.py` | 公共夹具关闭新开关，防止用户本地启用后旧测试意外调用模型 |
| `frontend/src/types.ts` / `components/ResultPanel.vue` | 可选轨迹类型、折叠工具执行详情、旧字段缺失兼容 |
| `frontend/src/components/AgentTimeline.vue` | 新节点中文标签 |
| `frontend/src/ToolTrace.test.ts` | 4个DOM回归用例：旧记录、成功、拒绝/回退、字段缺失及转义 |
| `README.md` / `docs/PHASE3B_*.md` | 当前范围、完整实现、真实执行结果与手动演示步骤 |

原299项后端与23项前端断言保留；没有删除测试或放宽旧断言，没有修改原gold/政策/订单种子来提高指标。
原runtime、conversations、订单事实定义、reply_safety、业务DB、工单和人工审核授权函数均保持不变。

## 3. 首次开发轮执行结果（历史）

使用 `C:\Users\yymmxr\Documents\ChatGPT\企业客服多Agent系统\.venv\Scripts\python.exe`；sys.executable/sys.prefix已输出核对。
没有使用Conda base执行。完整后端验证进程故意将新工具及Embedding远程开关设为true，再由测试公共夹具隔离。

| 检查 | 本轮实际结果 |
|---|---|
| 预算收紧前全部后端Pytest | 350 passed / 0 failed，191.09秒（历史中间结果） |
| 最终全部后端Pytest | **351 passed / 0 failed，201.46秒**，含新增回退预算回归 |
| 预算收紧前新增测试单独回归 | 51 passed / 0 failed，13.87秒；最终新增52项均在完整回归中执行 |
| pip check | **No broken requirements found** |
| 最终全部前端Vitest | **27 passed / 0 failed，5个文件，2.33秒** |
| 最终vue-tsc -b + Vite生产构建 | **成功，39模块，698ms** |
| 旧Agent离线评测 | 工作流10/10、回复6/6、故障6/6、签收14/14；实际模型调用0 |
| 原独立三轮 | **1/1**，实际模型调用0，仍使用原审批接口 |
| 3A三模式离线检索 | **source=mock_dense**，历史20+困难16全部保留，Embedding调用0 |
| 新36场景工具评测 | **36/36符合工程预期**；脚本模型尝试50，供应商请求0 |
| 新三轮Tool Calling | **1/1**；脚本模型尝试4；原审核待处理，未批准、未建单 |
| Git diff --check | 通过；Git提示LF/CRLF转换是本机换行提示，不是检查失败 |

实际无网络预检也已执行：key_configured=true、模型qwen3.7-flash-2026-07-15、主机dashscope.aliyuncs.com、
配置超时30秒/重试0、合成数据指纹匹配、network_calls=0。只说明静态格式和数据范围通过；未请求模型权限或额度。

本轮自动化前端验收是Vitest/jsdom和生产构建，没有执行真实浏览器视觉走查，不能声称已完成所有分辨率视觉验收。
并行运行后端与离线评测会影响本机耗时，不能把本节时间当生产P95或作性能提升对比。

## 4. 工具评测分母与真实数字

36条为运行前固定的AI辅助合成开发场景，全部独立人工复核仍为pending。包含坏参数/禁止工具/故障注入，
`expected_behavior_pass_rate`衡量保护机制是否按预期工作，不是纯模型准确率。

| 指标 | 分子 / 分母 | 值 | 口径 |
|---|---:|---:|---|
| 工具名称集合选择 | 29/36 | 0.8056 | 看模型原始提议，不用回退修正；不考察参数和重复次数 |
| 参数合法率 | 23/32 | 0.7188 | 只统计实际完成schema检查的提议；名称未知/预算拒绝/坏JSON未检查者排除 |
| 工具执行成功率 | 17/20 | 0.8500 | 模型触发的实际读取；授权拒绝和工具异常算未成功；排除缓存/模板回退读取 |
| 固定安全样例拒绝 | 11/11 | 1.0000 | 本集指定错误被拦截且零写入；不能外推所有攻击 |
| 运行completed | 35/36 | 0.9722 | 缺订单按预期awaiting_input仍不算completed，安全拒绝可completed |
| 场景符合预期 | 36/36 | 1.0000 | 包括正确拦截错误模型输出，不代表千问100% |
| 确定性回退 | 24/36 | 0.6667 | 模型/参数/协议/事实故障等均计入 |

脚本模型尝试总数50、平均1.3889/场景、最大3；工具提议40，模型触发实际读取20，回退实际读取20。
本机36场景耗时mean=606.05ms、P50=471.22ms、P95=731.39ms，nearest-rank；含TestClient/SQLite/本地检索和模拟器，不含供应商推理。
模拟器没有提供usage，因此Token=null、usage_complete=false、费用=null；不虚构“消耗0Token”或人民币估价。
SDK协议单测使用MockTransport返回的usage验证累计，不是实际供应商账单或真实千问效果。

固定数据集SHA256：`242c123f50f714b103709b8e2646af1d0bd4e87d0743a72f0d3cfbee235a53ba`。
报告保留逐题提议轨迹、断言、错误类型、响应、模型尝试和指纹，可以人工核对，而不是只凭退出码。

## 5. 新三轮的实际观察

1. 客户在临时会话问ORD1001，真实应用/图调用ScopedTools，脚本规划query_order；模型结果有状态及脱敏单号。
2. 追问“那它可以退款吗”，服务端关联同一订单并重新查归属，query_order+search_policy都有对应ToolMessage，
   chunk_id/source保留，received_days=null仍为unknown，没有变成未签收或已批准退款。
3. 售后申请走guarded_workflow，原approval interrupt暂停；同request_id复发保持原run；重建WorkflowService后从SQLite恢复待审核。
4. 普通客户批准403、其他客户读取会话404；原三轮单独验证和集成单测继续覆盖客服批准、重复批准只建一张工单。

新live验收工具主动停在第3轮，不自动使用客服批准；没有为了真实模型验证制造模拟写操作。

## 6. 3A回归保持

此次只运行Mock向量离线对照，没有重新读取/重写真实向量缓存。

| 集合 / 指标 | TF-IDF | Mock Dense | Mock Hybrid |
|---|---:|---:|---:|
| Historical20 来源Recall@3 | 0.9500 | 1.0000 | 1.0000 |
| Historical20 来源MRR | 0.9625 | 0.9750 | 0.9667 |
| Hard16中13正例 来源Recall@3 | 0.9231 | 0.3846 | 0.6923 |
| Hard16中13正例 证据Hit@3 | 0.6154 | 0.1538 | 0.4615 |
| Hard16中13正例 来源MRR | 0.8077 | 0.4064 | 0.6013 |

这与3A的Mock基线一致，不是用户历史Real Dense/Hybrid结果；历史真实困难集Dense优于Hybrid的结论保留。
3个无依据问题三模式仍均返回候选，自动证据充分性与安全拒答仍未通过，不能宣传本次工具系统已解决。
旧80题规则Accuracy=0.9125，7条错例保留；本轮不修改标注来改善分数。

## 7. 调试中真实发生的失败

- 新测试第一次网络防线拦截了Windows asyncio的loopback socketpair，TestClient启动失败并引发Pytest内部异常。
  修正为允许本机loopback基础设施、拦截外部连接；离线评测另外禁止HTTPTransport外发。不曾调用真实模型。
- 36场景初跑35/36：ORD1004的脚本回复复用旧非已发货模板，漏掉已知物流号，原事实校验按预期拒绝。
  修改模拟器使正常脚本输出包括已知脱敏单号，并新增回归确认遗漏时仍报unsafe_reply；未改gold、未放宽事实规则。
- 最终审查收紧了总读取预算：模型读取与回退读取之和不得超过max_calls；不足时记录fallback_error_type，返回暂不可用，不额外读取。
  新增1项集成回归并更新前端错误展示，之后完整复跑**351项**、27项前端、生产构建和全部离线命令。
- 没有把失败前或预算修复前结果当最终通过。

## 8. 安全与仍未通过事项

已检查真实.env摘要与开发前一致，Git忽略.env、.rag_cache、DB、运行报告和临时测试目录；暂存区为空。
22个待审文件经过已配置密钥比对与常见凭证格式扫描，未发现匹配；Git跟踪的禁止产物数量为0。
新增工具只允许两个静态只读函数；订单拒绝不泄露外部客户产品/owner；异常输出为类型/错误代码。
真实缓存、3A原始报告和已有评测标签未被改动或加入Git。

仍未通过/未执行：

- 当前账号与精确Qwen模型code的真实工具协议、权限、响应质量、真实Token/费用、供应商延迟。
- 所有36题和生成回复的独立人工复核，不能冒称用户已完成。
- 3A无依据问题自动安全拒答、完整政策语义/任意中文事实改写防御。
- 跨进程崩溃的持久化模型配额、账户全局金额上限、分布式并发和生产SLA。
- 真实浏览器视觉走查及本分支云端CI。

模型预算是每节点客户端尝试上限，CLI再加全局上限；不是Token/人民币限额，进程崩溃在checkpoint前可能重放只读/模型请求。
规则保护意图召回有限，普通输入可能含个人信息，本次没有宣称全输入自动PII过滤。
本轮不进入后续阶段、不开放模型写工具、不重构多Agent架构。

## 9. 可复现命令与本地报告

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=".pytest_tmp_phase3b_$(Get-Date -Format yyyyMMddHHmmss)" --tb=short
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --mode offline --output evaluation/reports-phase3b-agent-my-run
.\.venv\Scripts\python.exe -m evaluation.compare_rag --mode offline --output evaluation/reports-rag-phase3b-my-run
.\.venv\Scripts\python.exe -m evaluation.verify_qwen --mode offline --output evaluation/reports-phase3b-legacy-e2e-my-run
.\.venv\Scripts\python.exe -m evaluation.evaluate_tool_calling --mode offline --output evaluation/reports-tool-calling-my-run
.\.venv\Scripts\python.exe -m evaluation.verify_tool_calling --mode offline --output evaluation/reports-tool-e2e-my-run
Set-Location frontend
pnpm.cmd test
pnpm.cmd build
```

首次开发轮报告位于本地忽略目录：

- `evaluation/reports-phase3b-agent-reviewed`
- `evaluation/reports-rag-phase3b-reviewed`
- `evaluation/reports-phase3b-legacy-e2e-reviewed`
- `evaluation/reports-tool-calling-reviewed`
- `evaluation/reports-tool-e2e-reviewed`

真实调用预检及显式预算命令见[PHASE3B_DEMO.md](PHASE3B_DEMO.md)。本轮没有执行该live命令，
需用户另行明确授权并接受合成数据外发及请求次数上限后再运行。

## 10. 最终代码审查与本地提交验收（2026-10-26）

### 10.1 范围与逐文件结论

本轮从`feature/phase3b-safe-tool-calling`、HEAD=`0a4b8e433c57cda1cd7751d14d03b880d44adfc1`开始，
暂存区为空，22个变更均属于Phase 3B。没有覆盖其他分支或丢弃已有修改。
本轮检查的是所有10个已跟踪文件的diff与12个未跟踪文件的完整内容；第2节列出文件用途。

| 文件组 | 最终审查结论 |
|---|---|
| `tool_calling.py` | 真正使用bind_tools → AIMessage.tool_calls → ToolMessage(tool_call_id)协议；没有解析Prompt里的自造工具JSON充当协议。固定白名单、整批预校验、静态分发、同run缓存、双层模型预算和总读取预算均保留 |
| `workflow.py` / `agents.py` | 开关默认关闭；开启后高风险先由规则保护，仍走原review/TicketAgent。新AgentState字段默认空字典，旧checkpoint可读；不增加无预算的旧模型回退 |
| `.env.example` | 仅新增4项非敏感默认配置，max_calls也限制回退实际读取；真实.env不变 |
| `evaluate_tool_calling.py` / `tool_calling_fakes.py` | 模拟器与真实模型明确区分，离线禁止HTTPTransport外发；选择/参数/执行/回退分开计数，费用和未知usage不补造 |
| `verify_tool_calling.py` | live要求allow-remote+1–8次预算；固定合成语料指纹、官方Qwen端点检查、临时SQLite、停在原审核处；本轮只执行help和check-config |
| 数据集JSONL / 数据说明 | 固定36条预期和SHA256不变；AI辅助标注，独立人工复核pending；未按预测修改gold |
| `sandbox.py` / `run_evaluation.py` | 旧离线评测强制关新开关，人工表区分tool_*与旧回复模式，不误标成真实模型效果 |
| 两个工具测试文件 / `conftest.py` | 真实FastAPI、ConversationService、LangGraph、SQLite与SDK MockTransport；本轮增加12项安全边界回归，全部旧断言保留 |
| 前端types / ResultPanel / AgentTimeline / ToolTrace测试 | 可选字段兼容旧记录；提议、门禁、实际执行、权限拒绝、缓存与回退分开展示；使用Vue插值而非v-html渲染不可信内容；4个新增DOM回归保留 |
| README / 本说明 / 实现手册 / 演示手册 | 最新数量和本地提交边界更新；真实调用命令与实际parser一致；不冒称在线效果、人工验收或云端CI |

### 10.2 发现与最小修复

先新增回归再运行：**8 failed、1 passed、47 deselected**，确实复现以下三类边界问题。
随后修改`tool_calling.py`，未改旧测试断言或任何评测gold；相关测试完整复跑**64 passed，14.77秒**。

1. **执行作用域一致性**：之前只检查isinstance(ScopedTools)，未复核其绑定身份/run是否等于当前AgentState/run。
   原WorkflowService工厂本就按服务端记录绑定，模型不能传入这些字段；现进一步防御错误工厂绑定或内部误用。
   mismatch在任何模型请求/业务读取前直接blocked；错误码tool_scope_mismatch，不向错误作用域回退。新增2项回归。
2. **短单号脱敏**：之前首2位+末4位在长度≤6时可能覆盖全部字符。
   现短单号整体替换为***，较长单号仍保留不重叠首尾，并从脱敏结果重建facts。新增4项边界回归。
3. **政策元数据类型**：score_type/retrieval_mode之前直接透传可选值。
   现仅接受已知字符串枚举，不接受嵌套对象/列表/未知类型。新增3项回归。

另外新增3项伪造工具名回归：approve_refund、delete_order、fetch_url，均在执行前拒绝；
create_ticket、SQL/Python、身份字段注入、重复ID、整批拒绝、超时、429、预算与政策注入等原断言继续保留。
没有增加模型写工具，没有新增退款批准功能，没有修改业务数据库结构或进入后续阶段。

### 10.3 本轮重新执行结果

| 检查 | 实际结果 |
|---|---|
| 项目.venv全部Pytest | **363 passed / 0 failed，71.70秒** |
| pip check | **No broken requirements found** |
| 全部Vitest | **27 passed / 0 failed，5文件，2.18秒** |
| vue-tsc -b + Vite build | **成功，39模块，724ms** |
| 原Agent offline | 意图Accuracy=0.9125；工作流10/10、回复6/6、故障6/6、签收14/14；真实模型请求0 |
| 3A compare_rag offline | source=mock_dense，全部36题三模式对照保留，真实Embedding请求0；不能当Real Dense效果 |
| 原verify_qwen offline | **1/1**，含原审核/恢复/幂等；真实模型请求0 |
| 3B evaluate_tool_calling offline | **36/36符合工程预期**；原始选择29/36，参数23/32，实际读取成功17/20，固定安全拒绝11/11，回退24/36；脚本模型尝试50，真实请求0 |
| 新verify_tool_calling offline | **1/1**，4次脚本模型尝试，第3轮停在原awaiting_review；不批准或创建工单 |
| CLI help与check-config | 参数核对完成；key_configured=true、合成语料匹配、network_calls=0；未执行live |

36题工具指标分母与第4节一致，没有通过回退修复错误模型提议的选择指标。
本次本机工具场景耗时mean=341.00ms、P50=231.57ms、P95=458.80ms；与历史开发轮环境负载不同，不能当性能优化证据。
脚本模型usage=null、费用=null，未把MockTransport里的模拟Token算作实际供应商用量。

本轮新报告路径（均Git忽略，不覆盖历史文件）：

- `evaluation/reports-agent-phase3b-git-review-20261026-e6faa762`
- `evaluation/reports-rag-phase3b-git-review-20261026-e6faa762`
- `evaluation/reports-legacy-e2e-phase3b-git-review-20261026-e6faa762`
- `evaluation/reports-tools-phase3b-git-review-20261026-e6faa762`
- `evaluation/reports-tool-e2e-phase3b-git-review-20261026-e6faa762`

### 10.4 安全边界与未完成事项

只有query_order/search_policy两个函数进入模型白名单；函数名/参数/ID/轮数全部由代码校验，Prompt不承担授权。
身份来自服务端，工具绑定必须与运行一致，订单仍在ScopedTools里检查归属；历史记忆和模型参数都不能覆盖身份。
模型提议次数和模型+回退实际读取总数分别受max_calls限制，所有模型重试还需逐次预占local/global ledger。
不解析执行SQL/Python/任意URL，也不将create_ticket或approve_refund接到模型执行器。
售后仍需原审核接口和客服角色，原工单幂等及SQLite恢复测试均通过。

Prompt injection可让模型提错工具或答错，但不能修改静态白名单、审批状态和服务器角色；测试验证了这类写权限边界。
现有有限事实规则不能证明完整语义安全；任意政策改写、资格判断及无依据问题仍需独立人工验收。
真实账号/精确Qwen模型的工具协议、效果、Token/费用和供应商延迟仍未执行。
预算不是账户级人民币或Token硬上限；节点checkpoint前进程崩溃仍可能重放只读/模型请求。
没有宣称已完成分布式部署、所有攻击覆盖、真实浏览器视觉走查或本分支云端CI。

### 10.5 后续小预算真实命令（仅准备，本轮未执行）

已根据实际`--help`及parser核对以下参数。未来须另行明确授权外发固定合成数据并接受请求预算后手动执行：

```powershell
Set-Location 'C:\Users\yymmxr\Documents\ChatGPT\企业客服多Agent系统'
.\.venv\Scripts\python.exe -m evaluation.verify_tool_calling --check-config
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
.\.venv\Scripts\python.exe -m evaluation.verify_tool_calling --mode live --allow-remote --max-model-calls 6 --output "evaluation/reports-tool-live-$stamp"
```

全三轮最多6次模型请求尝试，单节点最多4次；该CLI强制重试0、关闭Embedding和模型分类，只用临时合成业务库。
合成数据指纹不匹配会在外发前停止，预算耗尽停止模型请求并安全回退；第3轮到待审核即止。
这里的6不是金额或Token预算，也不保证全36题真实模型效果通过。

### 10.6 本地提交边界

最终安全扫描未发现已配置API Key或常见私钥/Token格式泄露；真实.env的SHA256与审查前一致。
旧核心流程、订单/政策种子、原评测gold及已有测试与基准一致，旧测试断言未删除。
审查前记录的**169个既有向量缓存、业务SQLite及历史报告文件**在复跑后逐文件SHA256一致，没有删除或覆盖；新报告使用独立目录。
`git diff --check`通过；agents.py原有7行尾部空白与main相同，不为本次审查清理历史代码。

本轮用户明确授权验收后创建本地提交：`feat(agent): implement safe Qwen tool calling`。
只包含第2节22个Phase 3B源码、测试、固定合成用例及必要文档；真实.env、密钥、向量缓存、DB、临时目录和运行报告全部排除。
本节随该本地提交保存；实际SHA以本节所属Git提交记录和最终回复为准，不将自身SHA硬编码进提交文件。
不Push、不创建PR、不Merge、不Rebase、不删分支；main仍保持基准SHA，不能声称触发了新CI。

## 11. 真实验收后的最终交付审查（2026-10-27）

### 11.1 实际报告与范围

通过目录查找确认evaluation/reports-tool-live-third-20261027-165002-913/。
用户既有live报告记录qwen3.7-flash-2026-07-15、5/8次请求、0重试、输入5476/输出364/合计5840 Token，
usage_complete=true，5次确定性校验成功、0失败；24项检查均true。
第一轮2次模型请求、第二轮3次，均model_generated且violations=[]；
第二轮policy_source_present=true、receipt_state=unknown，回答引用实际检索来源refund_policy.md；
第三轮模型请求0、guarded_workflow、awaiting_review，没有工单。
manual_review.csv三行均pending，不能声称已完成独立人工语言/政策质量复核。

审查开始HEAD=ea8cdd994c92af0dd43a818a0d04dc699345509b，暂存区为空，
16个既有未提交文件属于前述安全回复/验收修复；本轮补齐README和交付文档，没有覆盖无关用户修改。
最终交付清单共20文件，按运行时、评测、测试、配置保护和公开文档列在[总结第7节](PHASE3B_REAL_ACCEPTANCE_20261027.md#7-审查范围与交付文件)。

### 11.2 代码审查结论

- 标准bind_tools → AIMessage.tool_calls → ToolMessage(tool_call_id)协议，固定白名单仅query_order/search_policy。
- strict参数、整批预校验、ID对应、服务端user/run绑定、订单上下文及ScopedTools归属双重校验保留。
- create_ticket/approve_refund等名称拒绝；售后仍走原审核interrupt、客服角色、同run恢复与幂等建单。
- reply_contract从实际授权数据生成必含字段、签收三态与来源示例；没有固定文件名自动追加。
- reply_safety.py、missing_source/unsupported_source/unsafe_reply及原事实校验没有放宽；缺证据仍拒绝。
- ScopedCallLedger逐次预占同一CLI父账本；节点4次、全场8次，额外重试0，预算耗尽与任何轮次失败停止后续场景。
- 模板回退不标记model_generated，不额外调用旧回复模型；错误代码、usage、模型提议和工具实际读取分开审计。
- reply_diagnostics默认关闭；固定词汇有损投影/白名单元数据，不保存拒绝原文；异常不阻止安全回退。
- 新旧测试断言与固定gold保留；没有发现需要修改已通过生产代码的阻断性问题。

### 11.3 本轮重新执行结果

| 检查 | 实际结果 |
|---|---|
| .venv全量Pytest | **427 passed / 0 failed，54.66秒** |
| pip check | No broken requirements found |
| 全部Vitest | **27 passed / 0 failed，5文件** |
| vue-tsc + Vite | 成功，39模块 |
| 固定工具offline | **36/36符合工程预期**；原始选择29/36、参数23/32、实际读取17/20、阻断11/11、回退24/36 |
| 新三轮offline | **1/1**，4次脚本尝试，第三轮仍待审核 |
| 原三轮offline | **1/1**，审核/恢复/幂等保留 |
| 3A compare_rag offline | 原20+16题三模式完成，source=mock_dense，Embedding调用0 |
| 原Agent offline | 工作流10/10、回复6/6、故障6/6、签收14/14；意图Accuracy=0.9125 |

环境：Python3.11.7（项目.venv）、Node24.21.0、pnpm11.19.0。仓库CI/Docker配置Python3.12，本轮未触发新云端CI。
新报告均位于evaluation/reports-{tools,tool-e2e,legacy-e2e,rag,agent}-phase3b-delivery-20261027-final/，
没有覆盖旧目录；Mock结果不替代真实模型效果，本轮新增真实聊天/Embedding请求均为0。

### 11.4 本地提交与剩余门禁

只纳入Phase 3B修复、对应测试、配置保护和必要文档；真实.env、真实凭证、业务SQLite、向量缓存、诊断、临时目录及运行报告均不提交。
提交信息为fix(agent): harden safe tool calling and validate live Qwen flow，SHA以实际Git记录和最终回复为准。
不Push、建PR、Merge、Rebase或删分支。后续PR正文保存在PHASE3B_PR_BODY.md，供用户人工执行命令使用。

仍未完成：独立人工质量复核、多场景真实Qwen评测、3A无依据问题自动拒答、企业身份/真实业务适配、
跨进程持久化金额预算、并发/灾备/生产SLA及新提交云端CI。本次真实小场景通过不消除这些风险。
