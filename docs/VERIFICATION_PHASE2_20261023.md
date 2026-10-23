# 第二阶段实际验证记录（2026-10-23）

## 结论与范围

在原“企业客服多Agent系统”ServiceFlow仓库上增量开发，基线HEAD为8ab114aa85609647e346510536ea0afce6481503（main，开发前工作区干净）。没有创建新项目，没有改相邻RAG业务代码，没有替换第一阶段LangGraph/会话/SQLite架构。

**本记录全部为离线与Mock验证，没有调用真实千问API、没有消费模型额度，没有修改真实.env。**开发阶段未自动提交或推送；用户随后明确授权将代码与测试结果同步GitHub。本次发布保留这些离线边界；云端CI以对应提交的GitHub Actions为准，本文不预先宣称云端通过。真实模型质量、延迟、额度、授权仍待用户另行授权运行live。

附件在第七节第二轮说明处截断，范围说明见[第二阶段手册](PHASE2_QWEN_VALIDATION.md)。没有补造不可见需求的验收结论。

## 实际执行结果

| 检查 | 开发前基线 | 最终实际结果 |
|---|---|---|
| 后端Pytest | 41 passed | **103 passed，0 failed**，发布前复跑22.55秒 |
| 前端Vitest | 19 passed / 3个文件 | **19 passed / 3个文件，0 failed** |
| vue-tsc + Vite生产构建 | 成功，37模块 | **成功，37模块** |
| pip check | 本阶段未安装依赖 | No broken requirements found |
| 原OpenAPI契约测试 | 已有 | 通过；无HTTP契约变更，无须重导出API文件 |
| 默认offline语义/网络封锁测试 | 已有 | 通过；Key存在时仍不能意外联网 |
| 原有测试文件与断言 | 保留 | Git diff核验原测试与conftest未修改 |
| 真实.env | 私有文件 | 前后SHA256一致，只报告是否一致，不公开内容 |
| Git diff --check | 干净基线 | 无空白错误；Git有既有CRLF转换提示，不是测试失败 |

前端本阶段没有业务/视觉改动，仍验证现有Vue多轮会话、旧工作台、权限切换与API封装。没有新增UI测试来冒充已有功能重做；本次新增62个后端测试执行用例（含参数化），总数103。

### 离线效果与业务场景

| 组件 | 本次实际结果 | 必须保留的解释 |
|---|---|---|
| 规则意图80条 | Accuracy 0.9125，Macro-F1 0.9208089669 | 与原基线一致，7个错例保留，不是模型提升 |
| 政策检索20条 | Recall@1/3/5=0.95/0.95/1.0，MRR=0.9625 | 文档命中，不是最终答案正确率；1个Top-3未命中保留 |
| 原工作流A-J | 10/10符合预期 | 8个完成、2个按预期等待审核 |
| 原工作流请求/工具 | HTTP21/22为2xx；工具15/16为ok | 1个预期跨用户404、1个预期工具越权拒绝 |
| 新回复/业务安全A-D | 6/6符合预期 | 此次使用规则/模板，真实生成数0，人工复核数0 |
| 故障注入E | 6/6符合预期，27次本地模拟调用 | 真实供应商请求0，不能当真实模型故障率 |
| 独立三轮+审批恢复 | 1/1通过 | 原API/图/工具/临时SQLite；真实模型请求0 |
| 脱敏配置预检 | 通过，network_calls=0 | 仅本地格式与范围，不证明实际授权/地域/免费额度可用 |

数据仍为AI辅助模拟开发集，待独立人工复核，非真实客户数据。没有伪造人工标注、线上指标、Token或费用。

## 关键新增测试覆盖

- 必填Key/base URL/model缺失；HTTPS与敏感URL拒绝；NaN/无穷/非法超时、重试、温度、布尔值；配置变更后客户端更新与安全repr。
- 实际LangChain/OpenAI客户端接httpx.MockTransport：验证同步/异步SDK隐式重试确已关闭；429后成功、503触发有限重试且预算不能超限；真实SDK序列化与结构化解析。
- 线程并发预算预占不能超过上限；配置失败不计请求；无效结构化结果、空输出、危险财务承诺只回退，不冒充生成成功。
- 同一case的rule/model/final分别记录；投诉/人工/售后审核保护不请求模型；原始模型统计只包含成功解析子集。
- 三轮真实SDK+Mock HTTP链路依次观测intent/reply/intent/reply四次，usage取Mock供应商返回值且明确模拟；未冒称真实千问实测。
- 真实图/SQLite三轮关联同订单但新run、复核归属、原interrupt、客户审批403、他人历史404、服务重建恢复、原审核接口、重复请求不重放模型或重复建单。
- 原live-limit 5仍只意图；显式reply不启用在线意图；intent+reply共享总预算，耗尽后的失败样例仍写报告并返回失败码；三轮live无显式预算拒绝执行。
- 工具错误、缺失物流、订单/来源/工单号、他人订单、超时/401/429/503等故障；模板保留事实与来源，异常正文不进入轨迹。
- 人工复核表pending、CSV公式防护、JSON原始文本保留；默认离线与三轮命令封锁网络，运行后原目录、环境和原文件哈希不变。

开发过程中修复了测试沙箱跨线程持有工作流RLock导致的等待，以及“不代表退款已批准”的错误事实拦截。修复后重新跑完整测试，没有删除原测试或降低原断言。

## 本轮文件清单

修改（11个）：

- .env.example：说明必要配置、有界超时/重试，只改示例，不改私有.env。
- support_agent/llm_client.py：明确配置、按配置缓存、关闭SDK重试、有界调用、原始结构化结果与回复校验。
- support_agent/intent.py：向后兼容的model_trace字段。
- support_agent/agents.py：轨迹来源/上下文覆盖、拒绝订单不调用模型润色、错误分类与模板回退。
- evaluation/evaluators/intent_eval.py：同批基线/原始模型/最终预测、保护/回退与调用指标。
- evaluation/run_evaluation.py：显式组件、共享硬预算、预检、schema2报告、人工CSV与可读摘要。
- evaluation/README.md、README.md：新入口、消费边界、文档链接，不宣称真实模型已验收。
- docs/EVALUATION_GUIDE.md、docs/PHASE1_UPGRADE.md、docs/MULTI_TURN_ARCHITECTURE.md：最新评测说明与历史行为边界。

新增（11个）：

- support_agent/model_runtime.py：ModelSettings、ModelConfigError/ServiceError、CallLedger、模型调用作用域。
- support_agent/reply_safety.py：已知订单/物流/来源/财务承诺/工单号最小事实防线。
- evaluation/sandbox.py：临时SQLite、模拟身份、真实API/工具观察、退出恢复。
- evaluation/evaluators/reply_eval.py：6个回复与业务安全场景，生成来源、检查与人工状态。
- evaluation/datasets/reply_cases.jsonl：6个可追溯模拟场景，明确待人工复核。
- evaluation/failure_checks.py：6类始终离线的错误注入与回退/幂等校验。
- evaluation/verify_qwen.py：独立三轮、审批与持久化恢复CLI。
- tests/test_model_runtime.py、tests/test_phase2_evaluation.py：新增单元、Mock传输和集成回归测试。
- docs/PHASE2_QWEN_VALIDATION.md、本文：完整运行、代码走读、指标口径与实际验收记录。

未修改：真实.env、原业务种子/数据库、前端业务源码、依赖/锁文件、原有测试文件及断言、API导出、原工作流/会话/持久化实现。提交与推送仅在用户明确要求同步GitHub后执行。

## 授权发布复核

2026-10-23用户明确要求“把代码改动、测试结果同步到GitHub”。发布前fetch确认本地main与origin/main无分叉，重新运行后端103项、前端19项、生产构建、pip check、离线评测与三轮工具，结果与上表一致。

同步范围为本文清单中的22个代码/测试/文档文件。真实.env、SQLite、前端构建产物及evaluation/reports-*仍排除在Git之外；公开的是脱敏验收记录，不强行上传私有原始报告。当前测试服务的独立临时数据库也不进入仓库。

此前打开网站只验证了前端HTTP200和后端ok；浏览器自动化因无法可靠确认当前URL而停止，没有完成页面点击验收。不能将这次网站基础检查写成真实模型或完整UI联调通过。

云端测试日志入口：[Verify support workflows](https://github.com/YangCurry11/enterprise-support-agent/actions/workflows/ci.yml)。GitHub Actions会独立运行后端测试、前端测试和生产构建，最终结论以本次提交的运行记录为准。

## 可复跑命令与报告位置

项目根目录执行；复跑pytest时换新的--basetemp名称，不删除或重置用户文件。

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.\.pytest_tmp_phase2_publish_20261023 --tb=short
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --mode offline --output .\evaluation\reports-phase2-offline
.\.venv\Scripts\python.exe -m evaluation.verify_qwen --mode offline --output .\evaluation\reports-phase2-e2e
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --check-config
cd frontend
pnpm.cmd test
pnpm.cmd build
```

本轮报告：evaluation/reports-phase2-offline与evaluation/reports-phase2-e2e，各含JSON/CSV/摘要/人工复核表；目录已被现有.gitignore忽略。本轮没有覆盖旧evaluation/reports默认报告。如需在现有评测页面读取本轮结果，可在后端进程环境设置EVALUATION_REPORT_DIR指向reports-phase2-offline，重启后端；页面仍只展示原核心指标，详细新增内容看报告文件。

真实千问验收的逐步命令与费用提示见[第二阶段手册第3节](PHASE2_QWEN_VALIDATION.md#3-真实调用仅在你决定消耗额度后手动执行)。当前尚未运行那些live命令，不能把103个自动化测试通过说成真实模型质量验收通过。
