# Phase 3A：真实 Embedding 核验与收尾报告

日期：2026-10-26。项目：ServiceFlow / 企业客服多Agent系统。
开发分支：`feature/phase3a-hybrid-rag`；本轮起点：`40b95632bf3c4c0be78a812ca181cc3318137ee8`；PR目标：`main`，不自动合并。

## 1. 验收结论

**用户既有真实Embedding记录、缓存检索工程及原开发集正例指标核验通过；独立人工证据复核、自动安全拒答与生产验收未通过/未完成。**不使用“全部验收通过”概括本次结果。

用户此前执行text-embedding-v4/1024维，北京地域：6次尝试、供应商945输入Token、usage_complete=true。945×0.5/1000000=**¥0.0004725**，依据准备时记录的公开同步价格估算，不是实际账单、不扣除未核实免费额度，也不是当前价格重新报价。

本轮只读取和核验这些记录，**真实Embedding请求0、真实聊天模型请求0，没有构建真实向量索引**。没有修改`.env`、4份政策、36题问题/gold或已有原始报告。默认TF-IDF、LangGraph、多轮会话、订单权限、人工审核、幂等与SQLite保持原样，没有Phase 3B开发。

## 2. 原始记录与完整性

以下文件保留在本地忽略目录，只有本报告中的摘要/指纹进入版本控制，不上传原始JSON/CSV、真实向量或私有配置。

| 记录 | 本地目录（evaluation/下） | latest.json SHA256 |
|---|---|---|
| 构建 | reports-rag-real-build-20261026-105251-706 | 7a551fa3a2e5978f75d4d72a7115e20c811f5a0b468e1e8730a87f6f4034efb2 |
| 第一次真实缓存对照 | reports-rag-real-cache-first-20261026-105251-706 | 222f495d551f7b7e340b81846919e3f56d90418775243ad1fc8901c7f4d667ff |
| 第二次真实缓存对照 | reports-rag-real-cache-repeat-20261026-105251-706 | 1a0b247973e8ff61600c9854d9cd300b669e68def1b9a8a78cb4c553b45d9aa3 |
| 原接受准备工具汇总 | reports-rag-real-acceptance-summary-20261026-105251-706 | 3b2a4f90914a6f6b6bf375eeb9d31d2f658cf29fd2e299d97f551f2f6488d056 |

核对方法不是相信文件夹名：

1. 构建、first、repeat的configuration完全一致；model=v4、dimensions=1024、端点地域北京。schema、split_version、端点哈希、corpus_hash及19个有序chunk_id与当前manifest相符。未请求API验证权限，也不输出Key或业务空间ID。
2. 两份对照记录的全部6个数据集文件指纹与4份政策文件指纹均匹配仓库。正式评测范围只使用原20题和困难16题，不添加/删除/重标样例。
3. 修改本轮源码前，报告中全部source_hashes与40b9563干净工作区源码一致；两份原报告的source_hashes也完全相同。本轮修正文案和审计工具不冒充生成原结果的旧源码。
4. 构建报告本身没有dataset指纹字段；它记录query_count_requested=36。问题集身份与完整覆盖由两份带指纹的逐题缓存报告补充验证，不编造构建器未记录的字段。
5. 原汇总recorded_results与从构建+first重新计算的结果一致，inventory与当前政策、数据集一致。它的`ready_to_call=false`是准备工具“不授权未来调用”的设计，不否认用户此前已经运行模型。

固定语料与RAG数据集指纹：

```text
split_version = markdown-v1-unchanged-600-500
corpus_hash = 4b278ac391adc7540f2953a4ac32ccf7ed9083915cd7c33287df9075daba293b
rag_cases.jsonl = 71459735681cabd5c315e1bba7cb3c5a2a91963d9f621889e40219f42f687d84
rag_hard_cases.jsonl = e1f185e8d9e2e499d148b9d357c1a4dbae36966d8455cc088b4c8261419ddabf
```

这些校验确认本地记录内部一致、可追溯；不是供应商签名凭证或账单独立审计，不能证明所有账户调用都包含在这6次里。

## 3. 请求、用量与缓存复现

| 构建尝试 | 供应商输入/total Token | 结果 |
|---|---:|---|
| 1 | 258 | success |
| 2 | 315 | success |
| 3 | 111 | success |
| 4 | 99 | success |
| 5 | 105 | success |
| 6 | 57 | success |
| 合计 | **945** | 全部成功，attempt均1，无重试 |

构建max_embedding_calls=6，6条usage均为非负整数、input=total，汇总与供应商记录相符。两份cache报告的顶层ledger及每题trace均0次尝试；零调用ledger没有供应商usage，不把其`usage_complete=false`误认作构建缺失用量。合并实际6条调用后的usage_complete=true；不对每题的累积ledger再次相加。

逐题核验原20+困难16题、每题三模式，共**108组、540条Top5候选**。对照不是仅看退出码，严格比较有序chunk_id、score、score_type、tfidf_rank、dense_rank、fusion_rank，全部一致；候选全文、source、内容/文件哈希与仓库chunk逐字段相符。问题、gold、expected_chunk_ids不变；指标从逐题结果重新计算后与原报告相符。

每次cache报告中，Dense和Hybrid各36/36查询向量命中，回退0、网络请求0。这里复现的是真实缓存下的检索排名，不是重新联网生成向量的一致性，也不是同进程缓存/生产并发性能证明。

另只读加载现有真实索引：provenance=live、矩阵19×1024，manifest与构建记录一致，36个查询哈希全部覆盖，向量/查询缓存通过现有维度、有限值及范数校验；不输出向量，不创建Embedding客户端或保存索引。

## 4. 真实三模式效果

保留原切分、原TF-IDF扩展、候选深度20、RRF k=60和最终Top5。同一文档/问题/标签/真实向量缓存用于三种模式，没有为了Hybrid改标签或调参数。

| 集合 / 模式 | 文档R@1 | 文档R@3 | 文档R@5 | 文档MRR | 证据Hit@3 | 证据MRR |
|---|---:|---:|---:|---:|---:|---:|
| Historical20 / TF-IDF | 0.9500 | 0.9500 | 1.0000 | 0.9625 | 0.9500 | 0.8208 |
| Historical20 / Real Dense | 0.9500 | 1.0000 | 1.0000 | 0.9750 | 1.0000 | 0.9750 |
| Historical20 / Real Hybrid | 0.9500 | 1.0000 | 1.0000 | 0.9750 | 1.0000 | 0.9750 |
| Hard16的13正例 / TF-IDF | 0.6923 | 0.9231 | 0.9231 | 0.8077 | 0.6154 | 0.4808 |
| Hard16的13正例 / Real Dense | 0.8462 | 1.0000 | 1.0000 | 0.9231 | 1.0000 | 0.8846 |
| Hard16的13正例 / Real Hybrid | 0.7692 | 0.9231 | 1.0000 | 0.8654 | 0.8462 | 0.7115 |

指标为正例的宏平均，Hard16分母为13，不包括3个无依据问题。每题只有一个gold文件时，文档Recall实际上是该文件在前K个候选来源中的Hit@K；重复文件仍占候选位置，保持历史口径。MRR为Top5内首个正确文件的倒数排名，证据指标使用原gold定位的chunk；命中文档不等于命中证据或答案正确。

**本次困难集Dense优于Hybrid，而不是Hybrid最优。**证据Hit@3分别为13/13与11/13，文档MRR为0.9231与0.8654。RRF按两路名次融合，不保证融合后超过较好的一路；本次错误的词法高排名可将正确Dense证据挤出Top3。

| 例子 | 原gold证据主题 | Dense证据排名 | Hybrid证据排名 | 状态 |
|---|---|---:|---:|---|
| hard-06：不是加急的服务单，要等一整天吗？ | 普通售后24小时响应 | 1 | 未入Top5 | 词法排名把标题/物流等候选推到前列；不改gold掩盖失败 |
| hard-10：付费高级客户能否不受退货规定限制？ | VIP仍需遵守退款退货政策 | 2 | 4 | Hybrid前三为退款文档片段，会员条件证据被挤至第4 |

以上是机械证据定位与错误分析，不冒充独立人工语义评审。样本少、语料仅4文档19片段，存在开发集天花板与标注局限，不声称统计显著、真实企业准确率或ROI；不因此自动修改默认业务检索模式。

### 已记录延迟，不是线上SLA

第一次cache报告的mean / P50 / P95（ms）：

| 集合 / 模式 | mean | P50 | P95 |
|---|---:|---:|---:|
| 历史 / TF-IDF | 1.3887 | 1.2890 | 1.4714 |
| 历史 / Dense | 0.6454 | 0.5077 | 1.4112 |
| 历史 / Hybrid | 1.6075 | 1.6084 | 1.7160 |
| 困难 / TF-IDF | 1.2379 | 1.2312 | 1.4217 |
| 困难 / Dense | 0.5047 | 0.5002 | 0.5756 |
| 困难 / Hybrid | 1.5578 | 1.5329 | 1.7355 |

包含集合全部问题（困难含负例），nearest-rank分位数。两次计时自然不同，不要求相同；没有远程向量化耗时，三模式顺序执行并共享查询向量，不能拿它宣传公平的冷网络性能或生产延迟。nDCG@3保持N/A：没有完整、独立人工复核的相关性qrels，不把未标注片段自动标为0。

## 5. 全部36题的待人工证据表

本轮已逐题检查数据身份、原gold可溯源、候选全文和排名，生成：

```text
evaluation/reports-rag-final-audit-20261026-01/latest.json
evaluation/reports-rag-final-audit-20261026-01/evidence_review.md
```

表内36个问题均含原gold、三模式Top5完整片段、source、完整chunk_id、分数类型、各路排名、机械gold命中及独立支持判定/理由位置。**36题的独立人工结论、复核人、时间全部待填写。**证据表是派生的本地工作表，和原始报告/向量一起保持私有忽略状态，不提交540条运行明细到GitHub。

3个无依据问题单独列入每模式审查，不以返回候选或空召回判“有/无证据”：

| ID | 问题 | 原gold | 三模式候选数 | 独立政策证据判断 |
|---|---|---|---|---|
| hard-14 | 跨国出差机票是否公司报销 | 无支持 | 各5 | 待人工确认；候选相关词不能构成报销制度 |
| hard-15 | 本月股票一定会涨多少 | 无支持 | 各5 | 待人工确认；没有预测保证的政策依据 |
| hard-16 | 员工年假天数和申请流程 | 无支持 | 各5 | 待人工确认；会员/售后政策不等于人事制度 |

这不是替用户签署人工复核，也不自动确认原gold一定正确。审查人需要先通读4份政策、独立确认是否存在支持，再检查每个候选与理由。所有模式的旧`no_support_correct=0/3`只代表“负例空召回数”，不代表语义证据判断准确率。没有运行答案生成或安全拒答实验，**automatic_safe_refusal_verified=false**。

### 可复跑的纯本地审计

在仓库根目录使用已有`.venv`，无需Key，不联网、不构建索引：

```powershell
$sfTag = '20261026-105251-706'
$sfBase = '.\evaluation'
& .\.venv\Scripts\python.exe -m evaluation.audit_rag_acceptance --build "$sfBase\reports-rag-real-build-$sfTag\latest.json" --first "$sfBase\reports-rag-real-cache-first-$sfTag\latest.json" --repeat "$sfBase\reports-rag-real-cache-repeat-$sfTag\latest.json" --summary "$sfBase\reports-rag-real-acceptance-summary-$sfTag\latest.json"
if ($LASTEXITCODE -ne 0) { throw '原始记录核验失败，停止发布；不得自动付费修补' }
```

默认输出唯一新忽略目录，显式输出目录若存在则拒绝覆盖。原始报告本轮只读，SHA256复核用于确认没有回写。其他机器没有这些私有输入时只能复跑Mock/单元测试，不能假装本机有真实缓存或重跑供应商。

## 6. 最小代码修改与本轮实际测试

- `compare_rag.write_comparison`以前无条件写Mock说明，现在分别处理Mock、real_cached_dense和live_dense；未知来源拒绝生成，保留正确Mock警示和回退说明。原始报告不回写；以后生成的summary按真实来源措辞。
- 新增`evaluation.audit_rag_acceptance`，只读核验四份报告、重算已有指标、检查逐题复现并生成待人工证据表。它没有模型调用入口，不是新检索框架，不更改业务流程。
- 22个新增回归用例覆盖逐题score/顺序/rank/正文/gold/缺题、fallback、调用次数、指标/manifest/usage/汇总篡改、源码身份不一致、模式误标、离线CLI与人工表、HTML/Markdown安全转义、真实/Mock模板分支。测试合成数据只在临时目录，不冒充真实模型结果。

| 本次执行 | 实际结果 |
|---|---|
| 新审计+准备+Hybrid专项 | 141 passed，15.32秒 |
| 完整后端 `.venv` Pytest | **299 passed，37.27秒** |
| pip check | **No broken requirements found** |
| 前端Vitest | **23 passed，4文件，14.71秒** |
| vue-tsc + Vite生产构建 | **成功，37模块，986ms** |
| 原离线工作流 | **10/10**；回复6/6、故障6/6、签收14/14 |
| 原离线三轮/审核/恢复 | **1/1** |
| 默认Mock检索回归 | 成功，mock_dense，真实Embedding尝试0 |

离线工作流日志中的timeout/401/429等是预期的故障替身，不是本轮真实供应商请求。全部回归使用新的忽略输出目录`evaluation/reports-phase3a-real-closeout-a7cb3e60af37423a86e4411a4224f728/`；前端未改源码，但测试和构建确实本轮重新运行，不挪用历史结果。

## 7. Git与发布安全

起点工作区干净。只提交本次代码、回归测试和整理后的说明文档；不暂存`.env`、原始JSON/CSV、540条派生运行明细、`.rag_cache`、数据库、node_modules/dist或测试临时目录。正式数据集和政策与起点一致，不覆盖用户配置。

本轮对`.env`、4组原始报告及真实缓存共10个文件逐个比较SHA256，内容均未变化；PR涉及的37个源码/说明文件扫描未发现真实Key、私钥或本机已配置密钥值。真实配置/索引/原始及派生报告的忽略规则有效，`git diff --check`通过。两份相关手册共4段PowerShell只做语法解析，未执行其中的付费命令。

本轮获授权推送的仅`feature/phase3a-hybrid-rag`，向main创建PR供审查，不自动合并、强推、rebase或删除分支。GitHub网络读取曾被OpenSSL连接重置，使用仅本命令的Schannel/HTTP1.1恢复连接，未禁用证书验证或修改全局配置。提交与PR的准确SHA/URL、实际CI结果以Git/GitHub和最终交付消息为准，不能在CI完成前写“云端通过”。

## 8. 仍未通过或不在本轮完成的事项

| 项目 | 状态 / 边界 |
|---|---|
| 36题及负例独立人工证据复核 | 未完成，表格待填写；不冒充用户签字 |
| 3题无依据的自动安全拒答 | 未验收，所有模式仍有候选；不能生产安全上线 |
| 独立、完整相关性标签及nDCG | 未完成，N/A；不修改gold提升指标 |
| 供应商最终账单/全账户费用审计 | 未完成，¥0.0004725仅公开价格估算 |
| 精确Token/人民币调用前预扣与跨进程硬上限 | 未实现；本次既有6次成功不证明此机制存在 |
| 真实新问题在线延迟、并发、限流、生产SLA | 本轮不新增模型实验，不以缓存计时替代 |
| 未来新增真实业务数据外发授权 | 需单独确认；本轮仅核验既有模拟数据记录 |
| main合并 / Phase 3B | 不执行 |

结论：Phase 3A可以提交检索工程、真实缓存结果与审计证据供代码审查；不能据此宣称系统已具备自动拒答安全、生产级预算控制或企业上线质量。
