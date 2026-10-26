# Phase 3A 实际验证记录（2026-10-24至2026-10-26）

阅读说明：第1–8节保留首次开发与233项历史回归；最终离线审查、241项复跑及本地提交边界见第9节。历史“未提交”是当时状态，不表示当前分支从未形成提交。

最新结论：2026-10-26已离线核验用户执行的真实v4/1024维报告，6次尝试、945输入Token，两份缓存逐题结果可复现；Dense在本次困难集上优于Hybrid。详情见第10节及[收尾报告](PHASE3A_REAL_ACCEPTANCE_20261026.md)。前9节“尚未运行真实Embedding”等表述仅描述2026-10-24历史，不作为当前状态。

## 1. 范围、分支和未做事项

目标为现有ServiceFlow enterprise-support-agent，不是相邻企业内部RAG项目。开始时main工作区干净，本地包含第二阶段最终提交ae0ed9070e4fe596069a34a16ea60d355ad2afcf；新建feature/phase3a-hybrid-rag，没有覆盖已有分支。

只实施Phase 3A：可选Embedding、NumPy Dense、安全缓存、RRF、回退和三模式对照。未开发Phase 3B、未改真实订单接口、未删TF-IDF/SQLite、未改人工审批或让模型直接建单、未部署公网。

**本轮没有真实Embedding/聊天模型请求，没有Git add、commit、push，没有修改真实.env。代码仅在本地开发分支未提交。**既有真实千问两份报告与历史默认评测保留，新增报告使用新的忽略目录。这里不是新的GitHub版本或CI通过声明；本轮没有触发云端CI。

## 2. 基线与最终测试

| 检查 | 实际执行结果 |
|---|---|
| 开发前后端基线 | 158 passed，43.16秒 |
| 新测试首轮 | 67 passed、1 failed；离线构建器保存Mock索引后重复mkdir |
| 修复后完整回归 | 228 passed，104.50秒；没有放宽断言 |
| 隔离增强前完整Pytest | 233 passed，0 failed，111.53秒 |
| 隔离增强首次检查 | 91 passed、142 setup errors；新Hybrid测试嵌套补丁恢复顺序污染policy_index，已修复 |
| 最终完整Pytest（进程开启远程配置） | **233 passed，0 failed，97.70秒**；公共夹具强制离线，原断言保留 |
| pip check | **No broken requirements found** |
| 本机已有依赖dry-run | pip install --dry-run --no-index -r requirements.txt成功，无安装/联网 |
| 前端完整Vitest | **23 passed，0 failed，4个文件** |
| vue-tsc -b + vite build | **成功，37模块，构建901ms** |
| 原完整Agent离线评测 | 工作流10/10、回复6/6、故障6/6、签收14/14；真实模型尝试0 |
| 独立离线三轮 | **1/1，实际模型调用0** |
| 新离线构建器 | 19片段、请求缓存36题，mock_dense，实际Embedding尝试0 |
| 新三模式离线对照 | 历史20题+困难16题全部保留；各模式回退数0；真实Embedding尝试0 |

原158项后端、19项前端测试及断言保留。新增75个后端执行用例（含参数化），4个前端分数标签用例。原测试断言未修改；conftest仅增加向量环境隔离和policy_index缓存清理，防止用户开启远程模式后Pytest意外消费。最终源码上重新运行全部后端、原完整评测和三轮入口；前端标签代码验证后未再修改。

实际命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.\.pytest_tmp_phase3a_baseline_20261024 --tb=short
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.\.pytest_tmp_phase3a_final --tb=short
# 专门检查用户开启远程配置时，测试仍保持离线；这些是当次进程覆盖
$env:RAG_MODE = "hybrid"
$env:EMBEDDING_ENABLED = "true"
$env:RAG_REMOTE_QUERY_ENABLED = "true"
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.\.pytest_tmp_phase3a_isolated_verified --tb=short --maxfail=1
# 离线CLI内部仍显式固定TF-IDF，不会使用上述远程配置
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip install --dry-run --no-index -r requirements.txt
.\.venv\Scripts\python.exe -m evaluation.compare_rag --mode offline --output .\evaluation\reports-rag-phase3a-final-20261024
.\.venv\Scripts\python.exe -m evaluation.build_policy_index --mode offline --include-eval-queries --output .\evaluation\reports-rag-phase3a-build-20261024
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --mode offline --output .\evaluation\reports-phase3a-final-20261024
.\.venv\Scripts\python.exe -m evaluation.verify_qwen --mode offline --output .\evaluation\reports-phase3a-e2e-final-20261024
cd frontend
pnpm.cmd test
pnpm.cmd build
```

目录均为本轮新目录；不要将这些已存在的basetemp当作业务目录，复现时建议换新名字。原错误报告/测试临时目录不为制造成功而删除。

## 3. 原评测与业务安全没有退化

原rag_cases.jsonl保持原样，正式4份政策、原切分规则、原Query Expansion、TF-IDF阈值和分数保留。

- 80条意图：Accuracy=0.9125、Macro-F1=0.9208089669；7条错例保留。
- 20题历史TF-IDF：文档Recall@1/3/5=0.95/0.95/1.0，MRR=0.9625；rag-19仍为Top-3未命中。
- 原工作流：10/10符合预期，8个完成、2个按预期待审核；HTTP21/22次2xx、工具15/16次ok，保留预期越权拒绝和404。
- 原回复6/6、故障6/6（27次本地模拟、0真实供应商调用）、签收14/14和离线三轮1/1均通过。
- 另有新测试把Mock Hybrid接到原PolicyAgent：同一ORD1001追问、三态签收未知、真实来源、第三轮审核前零工单、客户审批403、原run批准与重复批准仅一单。
- 原测试继续覆盖服务重建后的SQLite恢复、会话隔离、request_id幂等、人工审核与订单归属。workflow.py、runtime.py、conversations.py、agents.py、order_facts.py、业务DB与OpenAPI没有修改。

## 4. 新三模式实际对照

同样语料/切分/问题/gold；困难集在预测前写好并检查证据，不按Hybrid输出改标注。Dense使用**128维字符哈希Mock**，不是text-embedding-v4或其他真实模型。不得把本节数字作为真实语义模型改进或简历模型提升百分比。

### 历史20题：文档命中与片段证据分开

| 模式 | 来源 | R@1 | R@3 | R@5 | MRR | 证据Hit@3 |
|---|---|---:|---:|---:|---:|---:|
| TF-IDF | tfidf_baseline | 0.9500 | 0.9500 | 1.0000 | 0.9625 | 0.9500 |
| Dense | mock_dense | 0.9500 | 1.0000 | 1.0000 | 0.9750 | 1.0000 |
| Hybrid | mock_dense（RRF） | 0.9500 | 1.0000 | 1.0000 | 0.9667 | 1.0000 |

### 困难16题：13正例，3无依据问题

| 模式 | R@1 | R@3 | R@5 | MRR | 证据Hit@3 | 负例正确空召回 |
|---|---:|---:|---:|---:|---:|---:|
| TF-IDF | 0.6923 | 0.9231 | 0.9231 | 0.8077 | 0.6154 | 0/3 |
| Mock Dense | 0.3077 | 0.3846 | 0.6923 | 0.4064 | 0.1538 | 0/3 |
| Mock Hybrid | 0.4615 | 0.6923 | 0.9231 | 0.6013 | 0.4615 | 0/3 |

正例Recall/MRR的分母为13，不把3个无答案问题当“没命中gold文件”的普通正例。负例单独记negative_return_rate=1.0、no_support_correct=0，三模式都返回了政策片段，不能宣传支持正确拒答。证据Hit要求实际片段包含标注证据，不只是命中文档；未评测最终答案事实正确性。

**本次Mock Hybrid没有超过TF-IDF，困难集反而退化。**原因只可解释为当前字符哈希Mock、无语义模型、词法扩展和候选名次之间存在差异，弱排名经RRF也会拖累结果；不能据此判断真实v4一定退化或一定提升。短语省略、退款/售后相似政策、较低排名证据和无依据问题仍是后续重点。小语料Recall@5天花板高，也掩盖片段定位不足。

### 实际耗时（本机，毫秒）

| 集合 / 模式 | mean | P50 | P95 |
|---|---:|---:|---:|
| 历史 / TF-IDF | 1.5647 | 1.5167 | 2.1008 |
| 历史 / Mock Dense | 1.0427 | 0.9494 | 1.6108 |
| 历史 / Mock Hybrid | 1.7485 | 1.6649 | 1.9562 |
| 困难 / TF-IDF | 1.2955 | 1.2850 | 1.4458 |
| 困难 / Mock Dense | 0.9105 | 0.8964 | 1.0696 |
| 困难 / Mock Hybrid | 1.6041 | 1.5712 | 1.8767 |

timing包括集合全部查询及负例，P50/P95采用nearest-rank。预建索引时间不包含在内，Dense/Hybrid复用查询向量且顺序运行；本轮同时执行其他测试，不能据此宣称真实模型速度提升或生产SLA。报告完整保留每题命中文档、片段、排名、实际模式、回退原因和耗时。

失败案例：历史TF-IDF为rag-19；困难TF-IDF为hard-02/03/06/09/10/14/15/16；Mock Dense为hard-02/04/05/06/07/08/09/10/11/12/13/14/15/16；Mock Hybrid为hard-03/06/07/08/09/10/11/14/15/16。通过标准含文档Top-3及证据Top-3，负例需要空召回；不只看Recall总数。明细保留，不删除或回填虚假人工评分。

## 5. 缓存、异常与预算验证

自动测试覆盖：稳定chunk_id和标题、原切分、版本manifest、相同索引复用、模型/维度/端点/语料/分块版本不匹配、损坏JSON、拒绝把Mock索引当真实、原子写失败保留旧文件、向量范数/维度/NaN/Inf/非数值/零向量、NumPy排序与同分顺序、RRF按名次不按score、Top-K去重。

超时、401/403、429、5xx、维度不匹配、缺索引、旧索引、非法向量、相似度错误、预算耗尽，在Dense/Hybrid两模式均测试明确TF-IDF回退，保留来源/配置模式/实际模式/原因。缺索引即使开启remote_query也没有自动构建；关闭远程时查询缓存未命中不外发。

真实OpenAI SDK接httpx.MockTransport，验证embeddings请求payload/维度/结果index重排、usage真实映射、底层隐藏重试关闭。超时允许有限重试、401不重试、预算2不会多出第三个HTTP请求；EmbeddingLedger与Chat CallLedger相互独立。usage缺失为null，部分缺失标为不完整，费用null。所有HTTP均Mock，不是供应商实测。

查询最小化测试包含紧邻中文的ORD1001、手机号、邮箱和SF单号，外发给Mock的内容已替换；相同问题复用内存向量。另测有效查询缓存可无Key、无远程执行offline cache比较；该用例的缓存为测试专用合成替身，不当作本轮真实Embedding证据。

模拟构建器失败写入明确failed/error_type报告，不创建伪成功索引；有效索引复用测试实际请求0。最终默认离线评测在RAG_MODE=hybrid、两个向量开关开启的测试环境下仍没有调用EmbeddingClient.embed，证明旧命令没有隐式网络消费。

## 6. 修改文件清单

| 分组 | 文件 |
|---|---|
| 原兼容检索入口 | support_agent/rag.py |
| 新向量配置与客户端 | support_agent/rag_config.py、embedding_client.py |
| 新索引、Dense、RRF | support_agent/rag_index.py、dense_retriever.py、hybrid_retriever.py |
| 工具与不可信证据边界 | support_agent/scoped_tools.py、tools.py、llm_client.py |
| 新离线/在线构建和对照 | evaluation/build_policy_index.py、compare_rag.py、rag_comparison.py、mock_embedding.py |
| 独立困难开发集 | evaluation/datasets/rag_hard_cases.jsonl |
| 原离线入口防外发 | evaluation/evaluators/rag_eval.py、workflow_eval.py、evaluation/sandbox.py |
| 前端兼容标签/类型 | frontend/src/components/ResultPanel.vue、frontend/src/types.ts |
| 新测试 | tests/test_hybrid_rag.py、frontend/src/RetrievalScores.test.ts |
| 测试隔离 | tests/conftest.py仅增加RAG离线配置与缓存清理，不改断言 |
| 配置与依赖 | .env.example、.gitignore、requirements.txt、constraints.txt |
| 文档 | README.md、docs/EVALUATION_GUIDE.md、docs/MULTI_TURN_ARCHITECTURE.md、docs/PHASE3A_HYBRID_RAG.md、本文 |

共31个文件。NumPy/OpenAI原先已安装，本次显式声明和约束实测版本，不强制引入向量数据库或额外模型下载。前端只补可选字段并更正分数语义标签，按UI/UX通用清晰原则避免把RRF叫相似度，未做风格重设计。

## 7. 安全与未完成验证

Git差异核对：原rag_cases.jsonl、政策文件、原测试断言、workflow/runtime/订单事实/审批/幂等实现无变化。公共conftest只增加RAG隔离，不改变业务断言。真实.env只比较SHA256，不读取或打印Key；两份既有真实千问latest.json哈希保持不变。默认.rag_cache、所有evaluation/reports-*、测试临时文件、DB和前端dist继续忽略；没有暂存索引或原始报告。

待独立人工复核、真实Embedding账户授权/地域、真实缓存/联网向量质量与费用、数据合规和多平台兼容未完成。本次无真实usage，cost=null；不声称Qwen整体模型准确率或线上SLA。字符哈希Mock不是语义替代品，有限文本最小化不是完备脱敏，RRF不保证提升，检索结果不构成事实支持或审批授权。业务仍是单worker SQLite受控工作流。

如何手动配置、按预算构建真实索引、缓存评测查询、离线复用和显式live比较，见[3A手册第7节](PHASE3A_HYBRID_RAG.md)。本次没有代执行这些付费命令。

## 8. 后续建议（未实施）

先人工复核困难集及负例，冻结评测分母；在数据外发和费用授权后补真实Embedding对照，重点看证据位置和无依据问题，不只看小库文档Recall@5。再根据错误决定候选深度、拒识策略、切分或RRF参数，不能基于当前开发集临时改gold宣传提升。

Phase 3B未来若开展，应先定义工具schema白名单、服务端参数/身份验证、只读和有副作用工具分离、审批前置、幂等审计与独立回归；模型只能建议受限工具选择，不能授予自己权限。本阶段没有实现新Tool Calling或动态自主执行。

## 9. 最终离线审查与本地提交验收（2026-10-24）

开始审查时，feature/phase3a-hybrid-rag的HEAD仍为ae0ed9070e4fe596069a34a16ea60d355ad2afcf，31个变更文件与首次开发清单一致，暂存区为空，没有无关修改。全部31文件的职责、差异/新文件、现有测试与历史报告均已核对。

### 审查发现与最小修复

1. 自建Embedding SDK原先长期持有但未显式关闭：改为每次embed操作用上下文管理器，成功和失败均关闭；外部注入SDK保持调用方所有权。未更改模型配置、预算或重试语义。
2. 查询缓存容器未验证：异常JSON中的非字典、非法哈希键或错误向量可能抛未归类异常。现在验证字典结构、最多256项、64位十六进制哈希键及原向量规范；坏缓存明确记录index_invalid/invalid_vector并回退。不是新增检索功能或Phase 3B。
3. 新增8个执行用例（SDK成功/失败关闭、注入SDK不被擅自关闭、5种坏缓存），全部通过。总测试数由233变为241，不是删测试或放宽断言。

### 本次实际重新执行

| 检查 | 新执行结果 |
|---|---|
| Python环境 | sys.executable与sys.prefix均为本项目.venv，不是Conda base |
| Hybrid专项 | 83 passed，0 failed，8.70秒 |
| 完整后端 | **241 passed，0 failed，32.22秒**；另生成本地JUnit XML |
| pip check | **No broken requirements found** |
| 完整前端 | **23 passed，0 failed，4个文件** |
| vue-tsc + Vite生产构建 | **成功，37模块，720ms** |
| compare_rag --mode offline | 完成；mock_dense；真实Embedding尝试0，usage=null，cost=null |
| 原完整Agent离线评测 | 工作流10/10、回复6/6、故障6/6、签收14/14；真实模型尝试0 |
| 离线三轮与恢复 | 1/1；真实模型尝试0 |

命令与新证据位置（报告均在忽略目录，不提交）：

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.\.pytest_tmp_phase3a_commit_final --tb=short --junitxml=evaluation/reports-phase3a-commit-review-20261024/pytest.xml
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m evaluation.compare_rag --mode offline
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --mode offline --output .\evaluation\reports-phase3a-commit-agent-20261024
.\.venv\Scripts\python.exe -m evaluation.verify_qwen --mode offline --output .\evaluation\reports-phase3a-commit-e2e-20261024
# frontend目录
pnpm.cmd test
pnpm.cmd build
```

新对照目录为evaluation/reports-rag-compare-offline-mock-20261024T082924Z-a91605，包含逐题数据、实际模式、回退、失败明细和完整新计时。召回、MRR、证据命中及失败样例与第4节一致；历史耗时表不冒充本次计时。

| 集合 / 模式 | R@1 | R@3 | R@5 | MRR | 回退 |
|---|---:|---:|---:|---:|---:|
| 历史20 / TF-IDF | 0.9500 | 0.9500 | 1.0000 | 0.9625 | 0 |
| 历史20 / Mock Dense | 0.9500 | 1.0000 | 1.0000 | 0.9750 | 0 |
| 历史20 / Mock Hybrid | 0.9500 | 1.0000 | 1.0000 | 0.9667 | 0 |
| 困难13正例 / TF-IDF | 0.6923 | 0.9231 | 0.9231 | 0.8077 | 0 |
| 困难13正例 / Mock Dense | 0.3077 | 0.3846 | 0.6923 | 0.4064 | 0 |
| 困难13正例 / Mock Hybrid | 0.4615 | 0.6923 | 0.9231 | 0.6013 | 0 |

### 安全、剩余风险与验收边界

缺索引、失效索引、坏向量、API失败、预算耗尽均有明确回退用例。原PolicyAgent业务、LangGraph节点、订单权限、人工审核、幂等、SQLite恢复与原测试断言保留。检索内容只是候选证据，不能更改服务端权限或业务事实。

3个无依据问题仍全部返回候选，三模式空召回正确数均0/3。这是已知质量风险：检索相关不代表政策支持，当前没有已验证的拒识阈值或完整答案语义守卫。因此仅满足**离线工程版本**的可追溯/可复现验收，不满足生产问答质量或真实Embedding上线验收。没有基于gold临时调阈值掩盖失败。

本轮扫描候选源码、测试、文档和新增评测产物，不发现真实Key样式；.env只比较哈希且保持不变，不输出密钥。缓存、DB、日志、测试临时文件、dist和原始报告不进入提交；只显式暂存审查过的31个文件。git diff --check及暂存差异检查通过后，按授权创建本地提交：

```text
feat(rag): implement phase 3a hybrid retrieval with safe fallback
```

本次不push、merge、rebase或删除分支，不触发新的GitHub CI；本地成功不等于云端成功。提交SHA以包含本文件的本地Git提交和最终交付消息为准，避免将提交前的父提交当作本次结果。

真实Embedding验收尚缺：账户/地域权限、真实索引、独立人工复核、真实向量质量与无依据问题、实际usage/费用和供应商延迟。后续先冻结并复核gold，确认只外发允许的模拟文本及预算，再依手册第7节显式执行live构建/对照，复用缓存离线核验；记录退化与错误，再决定能否扩大使用范围。本轮没有执行任何真实付费API或进入Phase 3B。

## 10. 用户真实Embedding结果核验与本轮收尾（2026-10-26）

本次从`40b95632bf3c4c0be78a812ca181cc3318137ee8`的干净工作区开始。用户已执行一次真实构建，本轮只读取原始记录，不请求聊天/Embedding、不修改.env、原政策或评测标签，不构建真实索引。

- 4份报告的模型/配置一致：text-embedding-v4、1024维、北京；构建manifest与当前19片段、切分版本、有序chunk_id和端点指纹一致。
- 两份对照的6个数据集文件指纹与4份政策指纹均与仓库一致；修改源码前，原报告全部源码指纹与本地40b9563源码一致。构建报告本身不含问题集指纹，查询覆盖结合两份带指纹的逐题缓存报告验证，不虚构该字段。
- 逐调用汇总为6次、945输入Token、usage_complete=true；估算¥0.0004725，不是实际账单。两份cache报告各0次新增请求，不能对逐题累计ledger重复求和。
- 36题×3模式共108组、540条Top5候选，chunk_id、顺序、分数类型、TF-IDF/Dense/RRF排名及分数严格一致；不是仅检查退出码。

| 集合 / 模式 | R@1 | R@3 | R@5 | 文档MRR | 证据Hit@3 |
|---|---:|---:|---:|---:|---:|
| Historical20 / TF-IDF | 0.9500 | 0.9500 | 1.0000 | 0.9625 | 0.9500 |
| Historical20 / Real Dense | 0.9500 | 1.0000 | 1.0000 | 0.9750 | 1.0000 |
| Historical20 / Real Hybrid | 0.9500 | 1.0000 | 1.0000 | 0.9750 | 1.0000 |
| 困难13正例 / TF-IDF | 0.6923 | 0.9231 | 0.9231 | 0.8077 | 0.6154 |
| 困难13正例 / Real Dense | 0.8462 | 1.0000 | 1.0000 | 0.9231 | 1.0000 |
| 困难13正例 / Real Hybrid | 0.7692 | 0.9231 | 1.0000 | 0.8654 | 0.8462 |

Dense/Hybrid回退均0，两次各模式查询向量命中36/36。困难集Dense证据命中13/13高于Hybrid 11/13；hard-06证据Dense第1、Hybrid未入Top5，hard-10证据Dense第2、Hybrid第4，不能声称RRF必然更好。保持默认TF-IDF与现有业务流程，不为收尾调参数。

本轮最小修复为报告模板按mock_dense/real_cached_dense/live_dense显示不同来源说明，保留Mock警告。新增纯本地`evaluation.audit_rag_acceptance`复核原始记录、重算指标并生成全部36题/540条候选的`evidence_review.md`；每个独立人工结论均待填写，不把命中原gold视为独立复核。输出在忽略目录，不提交原始报告、向量或派生运行明细。

本次实际重新执行：**后端299 passed（37.27秒）、前端23 passed（4文件）、生产构建成功（37模块，986ms）、pip check通过**；原离线工作流10/10、回复6/6、故障6/6、签收14/14，离线三轮1/1，真实模型请求均0。22个新审计/模板回归用例未修改原断言。报告证据位于`evaluation/reports-phase3a-real-closeout-a7cb3e60af37423a86e4411a4224f728/`，不随Git提交。

工程与原开发集正例指标核验通过，但独立人工复核、3题无依据问题的自动安全拒答、完整相关性标注/nDCG、最终账单、精确Token/费用硬门禁和生产SLA仍未验收。三模式对3个无依据问题均返回候选，不能写成拒答成功。仅授权当前开发分支提交/推送并创建面向main的PR，不自动合并，不开发Phase 3B。最终提交、PR与CI状态以实际Git和GitHub记录为准。
