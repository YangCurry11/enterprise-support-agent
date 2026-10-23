# Agent 评测：如何运行、怎么看、面试怎么讲

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

第二阶段开发没有执行真实live，没有消费API额度。旧命令默认仍仅intent，绝不隐式扩大到回复；新增 --components intent,reply 必须显式选择并提供 --max-model-calls。RAG、工作流A–J和6个故障注入始终离线，按组件 execution_mode / live_components 标明，不因顶层live就声称全部真实模型端到端通过。三轮是独立入口，不会由默认命令自动调用。

模型分类实际保留受限意图集合、原规则高风险约束和失败回退；售后申请也保持确定性审核路由。live Accuracy 是“模型分类加规则约束/回退”的效果，不是纯模型原始能力。每条明细保留 rule_prediction / model_prediction / final_prediction、model_used / fallback_used / guard_applied / error_type / actual_model_calls；同批纯规则基线和原始模型成功子集指标分别记录，失败没有被删除或伪装成模型输出。

第二阶段 model_calls 逐次记录尝试、错误和供应商实际返回的usage；无usage为null，usage_complete=false说明不完整，不把缺失当零，不估造费用。重试也计入请求硬预算，SDK隐藏重试关闭。客户端尝试计数是保守上界，不等于供应商账单。供应商API失败不能据此声称免费额度正常；当前尚无真实千问usage实测记录。

## 三、数据集与标注责任

| 文件 | 数量 | 标注依据 |
|---|---|---|
| intent_cases.jsonl | 80 | 与实际 8 类意图一致，每类10条；含口语、模糊、缺失订单、复杂表达 |
| rag_cases.jsonl | 20 | 当前政策文件名 + gold_doc_id + expected_topic + 原文 gold_evidence |
| workflow_cases.jsonl | 10 | A–J 明确预期状态、预期 Agent 和安全检查 |
| reply_cases.jsonl | 6 | 订单/缺失信息/工具错误/政策追问/售后/越权的事实与状态检查 |

**它们是 AI 辅助编写的模拟开发标注，待独立人工复核。不是已完成的人类独立标注，不是真实客户数据，不是冻结测试集。**人工标注部分需要你或其他复核人逐条确认；可以在分支保存 reviewed_by / reviewed_at 和分歧决议后再称“人工复核集”。发现歧义先记录，不要为提高准确率直接改 gold。

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

## 六、本次实际结果（2026-10-22，离线）

80条意图：73正确/7错误，Accuracy=0.9125，Macro-F1=0.9208089669。
20条检索：Recall@1=0.95，@3=0.95，@5=1.0，MRR=0.9625。
10条业务场景：10通过；8个结果completed，2个按预期待审核。
请求22次：21次2xx、1次预期404；工具16次、15次ok、1次越权拒绝。
模拟模型超时1次，回退1次；无实际Token统计。

耗时以 evaluation/reports/latest.json 本机最新报告为准，不能放进简历当作线上P95。summary.md 会列出7条意图错误和1条Top-3检索未命中；不删失败样例。

## 七、文件职责与扩展方法

run_evaluation.py 管CLI、模式、数据/源码指纹与报告；intent_eval.py 管分类执行；rag_eval.py 管证据核验与真实检索；workflow_eval.py 管隔离业务链路；metrics.py 纯函数计算指标，方便单元测试。

添加案例：生成唯一id → 写明确gold/依据 → 加标注来源与复核状态 → 不看模型输出定gold → 跑默认offline → 看错误而非只看总分。使用 --output 留下不同版本报告，避免覆盖实验对照。默认报告不入Git，公开发布前仍要审查敏感信息。

## 八、面试可用表述

“我把传统功能测试和Agent效果评测分开：前者验证权限、幂等与恢复；后者在模拟开发集评估8类意图、TF-IDF文档命中与业务场景。评测有失败明细、哈希与明确分母。目前是AI辅助标注、待人工复核，千问端到端和线上SLA还没验收。”

后续先建立独立复核/冻结集，按真实错误补充边界场景，再经授权运行真实千问及人工复核。manual_review.csv仅生成pending表，不自动把语言质量打满分；复核结果请另存，不要下一次运行覆盖已填写文件。是否升级检索应由错误分析决定，不先写未经运行的Dense对比提升数字。
