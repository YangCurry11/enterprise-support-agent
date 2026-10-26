# Agent 评测：如何运行、怎么看、面试怎么讲

Phase 3A新增独立三模式对照入口，原命令仍固定为离线TF-IDF基线，不因服务端开启Embedding而偷偷外发查询。2026-10-26本轮后端299项、前端23项与用户既有真实v4报告的离线核验见[收尾报告](PHASE3A_REAL_ACCEPTANCE_20261026.md)；历史233/241/277项及本文后面的第二阶段158/19数据不冒充本次执行。全部36题的独立人工复核仍待完成，自动安全拒答未验收。

## Phase 3A：新增的公平检索比较

```powershell
.\.venv\Scripts\python.exe -m evaluation.compare_rag --mode offline
```

默认在全新evaluation/reports-rag-compare-offline-mock-*目录写latest.json、details.csv、summary.md。显式--output也必须是未存在的新目录，避免覆盖失败记录。保留原rag_cases.jsonl的20题，不改正式政策；单独rag_hard_cases.jsonl有16题（13正例、3无依据），gold_evidence先核验确实在原文片段中，再做预测。gold_chunk_id为空时，按gold_source+原始证据确定所有合法片段ID，不从检索输出倒推gold。所有新标注仍pending human review，不是独立人工冻结测试集。

对同样语料、切分和问题分别测tfidf / dense / hybrid，报告来源为tfidf_baseline、mock_dense、real_cached_dense或live_dense。默认Mock使用128维字符哈希，不是语义Embedding模型；其优劣只说明该Mock设定下的融合结果，不能宣传真实模型收益。

文档Recall@K/MRR仍按返回的前K个片段source命中文档计算；证据Hit@K/evidence_mrr按包含gold_evidence的准确chunk_id计算。两者均不等于最终答案正确性。负例不进入正例Recall分母，另记negative_count、negative_return_rate和no_support_correct；本轮三种模式对3个负例均有召回，这些失败保留。

timing对所有查询（包括负例）统计mean、nearest-rank P50/P95；Dense/Hybrid共用查询向量缓存且顺序执行，预建索引时间不含在检索时间内，不能据此宣称公平速度提升或线上SLA。实际配置模式、实际模式、fallback_reason、命中文档与片段逐条保留；只要出现Dense/Hybrid回退，命令退出1，不能把TF-IDF结果当Dense成功。检索未命中属于测量结果，不通过篡改gold让命令凑100%。

离线--source cache需要有效的真实来源政策索引和已缓存的查询向量；不会调用远程补查询。缺查询向量时记录回退并退出1。默认原Agent评测、故障注入、三轮验证均显式隔离为TF-IDF，即使进程环境配置了远程Embedding也不会外发。真实构建与live对照还必须加--allow-remote和独立--max-embedding-calls；完整操作见[3A手册](PHASE3A_HYBRID_RAG.md)。

## 一、先运行默认离线评测

在项目根目录，沿用原虚拟环境：

~~~powershell
.\.venv\Scripts\python.exe -m evaluation.run_evaluation
# 等价于 --mode offline；可另存报告
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --mode offline --output .\evaluation\reports
~~~

生成 latest.json（机器可读）、details.csv（逐条明细，UTF-8 BOM）、summary.md（中文总结）、manual_review.csv（待人工复核）。latest.json 先写同目录临时文件再原子替换，API 不会读到一半 JSON。第二阶段新增6个回复/业务安全场景和6个离线故障注入场景；完整操作与代码走读见 [PHASE2_QWEN_VALIDATION.md](PHASE2_QWEN_VALIDATION.md)。

默认不会调用真实模型。工作流通过 TestClient 调用真实 FastAPI、LangGraph、SQLite 与业务工具；模型超时场景用 Mock；独立 TemporaryDirectory 中初始化模拟业务，退出清理，不写 data/business.db。单元测试还封锁 socket.create_connection，验证默认评测不依赖模型网络。

页面的“Agent 评测”只允许客服查看最近一次报告，不触发模型调用。默认读取 evaluation/reports/latest.json；可通过后端 EVALUATION_REPORT_DIR 指向其他目录。无文件显示“暂无评测数据”，错误文件返回 503。目录只能由管理员配置，不能由浏览器任意传文件路径。

## 二、真实千问评测：显式开启，有费用边界

先在后端私有环境配置 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL，填控制台真实可用的模型 code 与地域对应地址；本文不假定某个快照模型、价格或免费额度仍有效。先执行 --check-config，仅本地校验，不联网。缺失模型或地址不会使用默认值。LLM_INTENT_ENABLED 由 live 意图命令作用域临时启用；回复评测则固定使用规则意图以隔离测量。

~~~powershell
# 只预检格式，不创建客户端、不联网
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --check-config

# 以下会消耗额度，由使用者决定是否执行：最多5次尝试，只在线分类
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --mode live --live-limit 5 --output .\evaluation\reports-live

# 显式回复组件与共享预算（含重试）；没有此预算参数会拒绝执行
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --mode live --components reply --reply-limit 1 --max-model-calls 1 --output .\evaluation\reports-live-reply

# 三轮+原审核/恢复接口，隔离临时SQLite；前两轮要求真实模型生成
.\.venv\Scripts\python.exe -m evaluation.verify_qwen --mode live --max-model-calls 8 --output .\evaluation\reports-e2e-live
~~~

早期第二阶段开发只做离线验证；用户随后实际执行了两次live三轮验证。本次收尾只读取已有证据，没有新消费。首次失败、复测单场景通过，见[收尾报告](PHASE2_RELEASE_20261023.md)。旧命令默认仍仅intent，绝不隐式扩大到回复；新增 --components intent,reply 必须显式选择并提供 --max-model-calls。RAG、工作流A–J、6个故障注入和14个签收固定文本回归始终离线，按组件execution_mode标明；三轮是独立入口，不由默认命令自动调用。

模型分类实际保留受限意图集合、原规则高风险约束和失败回退；售后申请也保持确定性审核路由。live Accuracy 是“模型分类加规则约束/回退”的效果，不是纯模型原始能力。每条明细保留 rule_prediction / model_prediction / final_prediction、model_used / fallback_used / guard_applied / error_type / actual_model_calls；同批纯规则基线和原始模型成功子集指标分别记录，失败没有被删除或伪装成模型输出。

第二阶段 model_calls 逐次记录尝试、错误和供应商实际返回的usage；无usage为null，usage_complete=false说明不完整，不把缺失当零，不估造费用。重试也计入请求硬预算，SDK隐藏重试关闭。客户端尝试计数是保守上界，不等于供应商账单。已有真实报告：首次usage合计4436 Token，仅3/4次返回usage，统计不完整；复测8658 Token，4/4次返回usage。两次cost均null，不能据此声称费用或免费额度。离线报告仍无真实Token测量。

## 三、数据集与标注责任

| 文件 | 数量 | 标注依据 |
|---|---|---|
| intent_cases.jsonl | 80 | 与实际 8 类意图一致，每类10条；含口语、模糊、缺失订单、复杂表达 |
| rag_cases.jsonl | 20 | 当前政策文件名 + gold_doc_id + expected_topic + 原文 gold_evidence |
| workflow_cases.jsonl | 10 | A–J 明确预期状态、预期 Agent 和安全检查 |
| reply_cases.jsonl | 6 | 订单/缺失信息/工具错误/政策追问/售后/越权的事实与状态检查 |
| receipt_cases.jsonl | 14 | 签收三态、0天、未知天数、物流缺失与条件句的固定文本回归，不调用模型 |

**它们是 AI 辅助编写的模拟开发标注，待独立人工复核。不是已完成的人类独立标注，不是真实客户数据，不是冻结测试集。**人工标注部分需要你或其他复核人逐条确认；可以在分支保存 reviewed_by / reviewed_at 和分歧决议后再称“人工复核集”。发现歧义先记录，不要为提高准确率直接改 gold。

签收事实修复见 [RECEIPT_FACTS_FIX_20261023.md](RECEIPT_FACTS_FIX_20261023.md)。新receipt组件复用原回复事实检查，错误断言被按预期拒绝也计为场景通过；它始终离线，不扩大任何live组件或调用预算，不应解读为模型回答正确率。原始订单status=已发货且received_days=null时，派生签收状态必须为unknown。

RAG 评测会核验 gold_evidence 确实存在于 gold_source，否则直接报错。报告记录数据文件与核心源码 SHA256；相同版本能追溯，但运行耗时不保证位级一致。单独训练/调参集和独立测试集本阶段尚未划分完成。

## 四、指标公式与容易混淆的地方

意图 Accuracy = 正确分类数 / 样例数。对每类：
Precision=TP/(TP+FP)，Recall=TP/(TP+FN)，F1=2PR/(P+R)；分母为0时设0。Macro-F1 为固定8类 F1 算术均值，不按类别样本数加权。混淆矩阵行是真值，列是预测。

当前标签：order_query、refund_policy、shipping_policy、after_sales、complaint、human_escalation、chit_chat、unknown。没有另造项目不支持的意图。

RAG 当前每题一个 gold 来源文件。KB 返回 Top-K **片段**，用这些片段的 source 检查 gold 文档是否出现；Recall@K 是命中的正确文档数/该题 gold 文档数，单 gold 时等价于文档命中率。重复 source 不增加召回，但占片段位置；不是去重文档排序的 Recall，也不是片段语义完整性/答案事实正确率。

MRR 是首个命中 gold source 的片段排名倒数的均值。gold_evidence 可追溯，但本轮不逐句裁判检索片段与最终答案，不能将 100% Recall@5 宣称为100%回答正确。

工作流 pass_rate = 所有本场景检查满足的场景数/场景数。等待审核本来就是正确预期，不能把它算作失败；workflow_completed 另记运行是否真的 completed。

HTTP request_success 只计算2xx；预期跨用户404也在 request_failed 中。工具成功率按工具实际 ok 计算，越权拒绝计为非ok但可能是安全场景的预期成功。必须连同安全断言解释。

性能 timing 为每次本机 TestClient 请求（包括预期404）耗时；意图/检索另有计时；不要把场景总耗时、请求耗时、纯模型延迟混用。P50/P95 使用 nearest-rank：排序后取第 ceil(p*n) 个；n=0 则 null。不是插值法，n小时P95接近最大值；预热和本机负载会影响结果。

第一阶段workflow回退率分母仍为模拟超时场景数（1），不是所有请求数，更不是真实模型错误率。新faults组件单独记录6类离线注入，不混入真实调用成功率。意图模型成功率/回退率分母为live未被guard跳过的样例数；请求成功率在model_calls按尝试计算（含重试），这两个分母不同。回复pass_rate为确定性检查符合率，不是完整自然语言回答准确率。

## 五、A–J 实际断言

- A 合法订单：completed，真实 OrderAgent 与订单工具。
- B 越权订单：无其他客户商品泄露，订单工具 ok=false。
- C 政策：真实 TF-IDF，必须有来源。
- D 售后：awaiting_review，批准前零新增工单。
- E 同键重试与重复批准：同run，单工单。
- F 模型超时：轨迹 fallback_template，工作流继续。
- G 三轮同会话：订单关联、三个业务run、售后待审核。
- H 切换用户：他人读会话404。
- I 补充编号：同run恢复，不产生新业务run。
- J 拒绝审核：completed但无工单。

expected_agents 是响应里的 Agent/业务步骤名，不是底层 StateGraph 所有节点的完整 trace；observed_agents、checks、tool_calls 保留逐条依据。审批前 review 节点会 interrupt，直到恢复后才记录 ReviewAgent step。

## 六、本次收尾实际复跑（2026-10-23，离线）

80条意图：73正确/7错误，Accuracy=0.9125，Macro-F1=0.9208089669。
20条检索：Recall@1=0.95，@3=0.95，@5=1.0，MRR=0.9625。
10条业务场景：10通过；8个结果completed，2个按预期待审核。
请求22次：21次2xx、1次预期404；工具16次、15次ok、1次越权拒绝。
原工作流模拟模型超时1次，回退1次；另有回复6/6、故障注入6/6（27次本地模拟调用、0次供应商请求）、签收固定文本14/14、独立离线三轮1/1。整次离线模型请求为0，无实际Token统计。

完整Pytest为158 passed / 0 failed（34.83秒），原103项测试不改；Vitest为19 passed / 0 failed，生产构建与pip check通过。真实报告已核对：30秒配置0/1、90秒配置1/1，两次各4次模型尝试。首次第二轮provider_error并非事实守卫拒绝；耗时接近超时值但根因未确认。90秒为用户那次进程覆盖，不是代码默认值。两份人工复核CSV各4行pending，reviewer与reviewed_at未填，不视为独立验收。

耗时以 evaluation/reports/latest.json 本机最新报告为准，不能放进简历当作线上P95。summary.md 会列出7条意图错误和1条Top-3检索未命中；不删失败样例。

## 七、文件职责与扩展方法

run_evaluation.py 管CLI、模式、数据/源码指纹与报告；intent_eval.py 管分类执行；rag_eval.py 管证据核验与真实检索；workflow_eval.py 管隔离业务链路；metrics.py 纯函数计算指标，方便单元测试。

添加案例：生成唯一id → 写明确gold/依据 → 加标注来源与复核状态 → 不看模型输出定gold → 跑默认offline → 看错误而非只看总分。使用 --output 留下不同版本报告，避免覆盖实验对照。默认报告不入Git，公开发布前仍要审查敏感信息。

## 八、面试可用表述

“我把功能测试和Agent效果评测分开：前者验证权限、幂等与恢复；后者在模拟开发集评估8类意图、TF-IDF文档命中与业务场景。158项后端与19项前端回归通过；已用千问验证一个模拟三轮场景，保留首次provider_error与随后成功证据。对模型把‘已发货+空签收’推断成‘未签收’的问题，我统一了签收三态、Prompt约束和模板回退。数据集尚待独立人工复核，不把单场景通过说成生产准确率或SLA。”

后续先建立独立复核/冻结集，按真实错误补充边界场景，再经授权扩大真实千问覆盖并人工复核。manual_review.csv仅生成pending表，不自动把语言质量打满分；复核结果请另存，不要下一次运行覆盖已填写文件。本次默认报告重跑前已备份到本地evaluation/reports-pre-release-20261023-archive，已有两份live证据保持原样。是否升级检索应由错误分析决定，不先写未经运行的Dense对比提升数字。
