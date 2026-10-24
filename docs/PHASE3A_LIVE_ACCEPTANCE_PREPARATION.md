# Phase 3A：真实 Embedding 在线验收准备报告

日期：2026-10-24。项目：ServiceFlow / 企业客服多Agent系统。
分支：`feature/phase3a-hybrid-rag`；开始检查的 HEAD / 基准为 `228e7fcada1688f1c1bb157176e76432051e8502`，工作区原本干净。

阅读说明：第1–9节保留验收准备开发完成时的检查快照（当时未暂存/提交）；本次获授权后的最终代码审查、重新测试与独立本地提交边界见第10节。本文不代表真实Embedding已经验收通过或GitHub已经更新。

## 1. 结论与本轮边界

本轮只完成静态审查、官方文档核对、数据/请求/费用规划、最小用量兼容修复和离线验证。**真实 Embedding API 调用为 0；聊天模型 API 调用为 0；没有构建真实向量索引。**没有修改 `.env`、原政策、36题数据及其标注，没有改 LangGraph、PolicyAgent、权限、审批、幂等、SQLite，没有提交、推送、合并或进入 Phase 3B。

**目前不具备直接开始真实调用的条件。**原因是独立向量配置未完成、Key地域/账户权限无法离线验证、数据所有者尚未明确授权外发、人工标注复核未完成，以及现有硬预算是 SDK 请求尝试次数，不是精确Token/人民币预扣。不能把下面的估算当作已经获得授权或已经实测。

新增纯本地工具 `evaluation/prepare_embedding_acceptance.py`，无live选项、不构造SDK、不读取业务订单/会话数据库；即使本机开启远程RAG环境，也只实例化显式TF-IDF知识库。生成清单成功的退出码0只表示准备工具完成，输出始终保留 `ready_to_call=false` 和 `actual_calls_authorized=false`。

## 2. 配置检查与官方接口核对

本机 `.env` 加当前进程环境的有效检查结果（dotenv不覆盖已有进程配置）：

| 检查 | 结果 |
|---|---|
| `EMBEDDING_API_KEY` 已配置 | `false` |
| 独立模型 / Base URL / 维度已配置 | 均为 `false` |
| Embedding配置通过校验 | `false` |
| RAG模式 | `tfidf` |
| `EMBEDDING_ENABLED` | `false` |
| `RAG_REMOTE_QUERY_ENABLED` | `false` |
| Endpoint地域与Key所属地域一致 | 无法确认；端点未配置，Key地域须本人在控制台确认 |
| 模型权限、额度、免费额度是否有效 | 未验证；没有通过真实请求探测 |

这里只输出Key配置布尔值，不输出Key、前后缀、长度或散列。聊天用Key即使存在，也不会自动用于Embedding；需要本人私下配置独立 `EMBEDDING_API_KEY`，不要发到聊天、截图或GitHub。

候选固定为 `text-embedding-v4`，本次建议1024维，不擅自迁移到其他模型。官方支持64/128/256/512/768/1024/1536/2048维，每请求最多10条，每条最多8192 Token。兼容接口请求为 `model/input/dimensions/encoding_format=float`，响应为带index的data向量列表；v4可能仅有 `usage.total_tokens`。[官方同步接口](https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api)

北京、新加坡的业务空间兼容地址分别为 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` 与 `https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1`；SDK自动追加 `/embeddings`。使用控制台提供的真实业务空间地址，不要把占位符或DashScope原生 `/api/v1` 路径填进去；各地域Key不可想当然混用。[官方向量化指南](https://help.aliyun.com/zh/model-studio/embedding)

本地预检只识别官方完整域名及兼容路径、拒绝凭证/query/fragment/非HTTPS/异常端口，不输出业务空间ID。它能判断“配置指向哪个地域”，不能判断“Key实际属于哪个地域”。旧dashscope兼容主机的识别仅为兼容现有配置，新配置优先以本人控制台为准。

### 现有能力与审查结论

| 能力 / 文件 | 结论与边界 |
|---|---|
| `rag_config.py` | Embedding配置独立，HTTPS和显式维度校验；无聊天Key回退 |
| `rag_index.py` | schema/split/model/维度/endpoint/语料/有序chunk_id共同校验；坏、旧、Mock索引拒绝；JSON原子替换，不用pickle |
| `dense_retriever.py` | 查询最小化后哈希缓存；语料/模型/端点/维度变化使索引失效；最多256个查询，未命中且远程关闭则明确回退；不是TTL或跨进程并发锁 |
| `embedding_client.py` | SDK隐藏重试关闭，ledger在每次尝试前预占，重试也计数；自建SDK在退出时关闭；不输出异常body/Key |
| `rag.py` | 请求失败、坏向量、缺/失效索引、预算耗尽回退原TF-IDF，记录实际模式和原因，不自动付费重建 |
| `hybrid_retriever.py` | 相同稳定chunk_id按RRF名次融合、去重与确定性排序，不直接相加原分数 |
| 构建/评测入口 | 默认offline Mock；live需显式参数和开关；`offline --source cache`只用真实缓存不联网；Mock结果不冒充真实效果 |
| Token与费用 | 记录实际usage；未实现调用前精确Token预扣、跨进程共享费用额度；不能以字符数或“余额够用”替代硬门禁 |

### 本轮必要的最小修复

原客户端要求usage同时具备prompt_tokens和total_tokens，会漏记v4的total-only用量。现在仅对明确的v4 input-only合同将供应商真实total计作输入用量；其他未知模型不推断，缺失、负数、布尔值、字符串或不一致usage不伪造。向量维度、index、范数校验保持原样，排序/模型回退不变。真实OpenAI SDK接MockTransport的测试已覆盖这种响应，没有向外发请求。

超时配置默认20秒，可设0.1–120秒；它是SDK网络超时配置，不是全任务20秒硬截止。超时/连接/429/5xx仅有限重试，401/403/400/404/422和非法向量不重试。现有短退避不是账户级RPM/TPM调度，不宣称生产限流治理。官方北京v4列示RPM1800、输入TPM120万，实际账户限额与其他并行任务仍须确认；本次首次验收选择串行、`EMBEDDING_MAX_RETRIES=0`，遇429直接停止构建，不扩大预算重试。[官方限流说明](https://help.aliyun.com/zh/model-studio/rate-limit)

## 3. 数据外发安全清单

允许候选范围严格限定为 `data/policies/*.md` 的4份模拟政策，加原20题和困难16题中的问题文本。构建器发送chunk.text，查询发送minimize_query后的文字，不发送文件路径、gold、业务DB、订单对象、会话历史、日志、用户身份或API Key以外的业务认证信息。

| 待发文本 | 条数 | 字符数 | UTF-8字节数 | 单条最大字符 / 字节 |
|---|---:|---:|---:|---:|
| 原切分政策chunk | 19 | 874 | 2446 | 88 / 252 |
| 最小化后去重评测问题 | 36 | 561 | 1667 | 26 / 78 |
| 合计 | 55 | 1435 | 4113 | — |

20题全部正例；困难集13正例+3无依据问题，全部保留。当前36个查询互不重复，最小化未改变其中任何一题。4份正文与全部问题已查看，内容为通用模拟政策与合成咨询，未发现真实个人、完整号码、真实订单详情、地址或商业机密；邮箱/手机号/身份证/订单物流编号/Key样式的规则扫描命中0。

这不等于法律或数据所有权证明。规则不能完备识别人名、地址、组织机密或伪装文本；“文件在仓库里”也不等于有外发授权。**需要本人确认这些文件确属自建模拟素材，可以发送至所选阿里云地域。**真实用户自由输入不在本次授权范围，保持 `RAG_REMOTE_QUERY_ENABLED=false`。后续修改任何政策、问题或分块规则都需要重做清单和授权。

冻结指纹：

```text
split_version: markdown-v1-unchanged-600-500
corpus_hash: 4b278ac391adc7540f2953a4ac32ccf7ed9083915cd7c33287df9075daba293b
rag_cases.jsonl: 71459735681cabd5c315e1bba7cb3c5a2a91963d9f621889e40219f42f687d84
rag_hard_cases.jsonl: e1f185e8d9e2e499d148b9d357c1a4dbae36966d8455cc088b4c8261419ddabf
```

逐文件政策哈希、分母、最小化统计、负例复核模板保存在本地新报告 `evaluation/reports-rag-preparation-20261024T111754Z-a974a3/latest.json`。原始评测报告与缓存均被Git忽略，不自动上传。

## 4. 请求、Token、冷/热缓存与费用预算

本轮实际请求0、外发计费Token为0，没有产生本轮模型费用。不存在本轮供应商usage；待真实测量的模型Token字段保持null。以下是未来单次授权任务的规划，不是实测Token或账单。

### 请求计划

- 政策19个chunk按10条批处理：2次请求。
- 36个唯一问题按10条批处理：4次请求。
- 新建“文档+全部评测查询”真实缓存：无重试计划 **6次SDK尝试**。一次构建后比较三种模式，不是每种模式再花6次。
- 文档索引已在而查询未缓存时，现有live比较逐问题调用：36次；Hybrid顺序共享Dense的查询向量。**本次不选择这条高请求数路径。**
- 完整热缓存复验/离线cache比较：0次远程请求。已有完整有效索引不加rebuild会复用0次；缺失/不匹配不能当作热命中。
- 默认额外重试1次、若每批都经历一次失败再成功，理论可能12次；允许2次额外重试则18次。这只有在放大总预算时才可能发生。总cap=6时无论重试配置如何，**绝不会发第7次**，但可能无法完成全部批次。

### Token与价格

暂未安装/验证与v4服务一致的离线tokenizer，不能精确预报计费Token。用“每字符1 Token”得到1435、用“每UTF-8字节1 Token”得到4113，均仅为两个规划情景；不是置信区间、实际用量或已经证明的Token上限。

中国站官方同步v4价格：北京0.5元/百万输入Token、新加坡0.514元/百万输入Token，向量输出不收费。不假定还有免费额度；国际站账户须另核价格/币种。普通同步API一次传10条不等于官方异步Batch API，**不套用Batch半价**。[官方价格](https://help.aliyun.com/zh/model-studio/model-pricing)

| 地域 | 1435 Token情景 | 4113 Token情景 | 6次请求的服务规格条件性粗上界 |
|---|---:|---:|---:|
| 北京 | ¥0.0007175 | ¥0.0020565 | ¥0.24576 |
| 新加坡 | ¥0.00073759 | ¥0.002114082 | ¥0.25264128 |

最后一列按 `6 × 每次最多10条 × 每条8192 Token = 491520 Token`，再乘公开单价计算，**依赖固定官方v4端点、模型/价格未变及服务规格成立**，不是应用精确Token硬上限或全账户扣费担保。若放任12/18次尝试，条件性最坏数分别为983040/1474560 Token，北京¥0.49152/¥0.73728。不能因为预计很便宜就增加调用。

失败/超时也占本地请求预算；不以缺失usage判免费，不能盲目重新跑整个构建。现有ledger记录到的usage费用是已报告用量估计；若有缺失调用，只是已知部分，实际账单须控制台核对。

### 门禁设计与立即停止

1. 只授权一次构建任务，共6次尝试，重试0；关闭应用远程查询，不并发运行其他构建/模型任务。请求cap为进程内硬限制，**不是多进程/跨命令共享账户预算**。
2. 构建器任一Embedding错误（含预算耗尽）立即结束构建、退出非0，保留失败报告且不覆盖旧索引。PowerShell检查退出码，阻止后续步骤；不得自动循环/重建/加额度。
3. 全部评测改用offline cache，不能调用原手册的live比较40次作为后续“补齐”。现有live compare会在逐题预算耗尽后继续离线回退，没有新增网络请求，但不是整批立即退出；本次绕开该入口，不改正常业务回退。
4. 若用户要求“精确Token数/人民币不可超过指定金额”，**当前运行时未实现这样的预扣门禁，禁止实际调用**。必须先明确采用供应商可验证硬额度，或经验证的本地tokenizer+每次请求前含重试的Token预留机制，并通过测试。控制台账单告警不等于硬停机。
5. 因此本报告只是可执行路径的准备稿；在预算保障未被确认前，下面付费命令不获准执行。即使本人后续同意，也必须先重新确认本节条件，不将一次同意视为无限重跑许可。

## 5. 公平评测设计与指标定义

文档、原切分、chunk_id、36题、gold证据、Top-K、RRF k=60、候选深度20均冻结，不看预测修改gold、不调参到本次数据后再冒充独立测试。基线20和困难13正例分别汇报，不混合稀释退化。使用同一个真实索引与36个查询向量分别运行TF-IDF、Real Dense、Real Hybrid，三者都最终取5条以报告@1/@3/@5。不要删原TF-IDF扩展。

| 指标 | 定义 / 统计范围 |
|---|---|
| Recall@1/3/5 | 正例按每题gold_source文档集合在前K个chunk候选来源中的覆盖率，再宏平均；当前每题1个gold文件，实际为文档Hit@K。重复来源仍占候选位置，不另改基线语义 |
| MRR | 正例首个gold文档出现名次的倒数平均；只检索到Top5，未出现记0，报告注明截断口径 |
| Evidence Hit@K / Evidence MRR | 使用预测前可追溯gold_evidence定位的chunk_id，不能以命中文档替代证据命中 |
| nDCG@3 | 当前null / pending。现有单条证据不是完整、独立复核的多级相关性qrels；不能默认未标注chunk为0。若未来先有有效标注，再按DCG=sum((2^rel-1)/log2(rank+1))、除IDCG，固定rel等级；不在本次编造 |
| 检索延迟 | 原报告all queries incl negatives的mean/P50/P95（nearest-rank）。缓存比较含刷新/排序，但不含远程向量化；单列构建各批API耗时，不把两者合并冒充端到端SLA |
| 缓存命中率 | 各Dense/Hybrid中“实际模式未回退且本次Embedding尝试=0”的查询数 / 该模式全部查询数；TF-IDF为N/A。只用于真实cache/live报告，不把Mock零请求当真命中 |
| API次数 | build与compare各自顶层ledger实际尝试数相加，含重试；不能对逐题累积ledger再次求和，否则重复计数 |
| 实际Token | 仅已返回合法usage的供应商值；v4 total-only按input-only映射。缺失保持未知，列usage_complete和缺失尝试数 |
| 费用估计 | 已报告输入Token/1000000×确认地域单价；不减未经确认的免费额度，不含其他任务；供应商账单最终为准 |

冷/热实验：冷构建记录2批文档+4批查询的真实向量化总耗时和逐请求耗时；第一次cache比较是新进程加载+热查询向量，第二次是同类新进程复验，不称“同进程全热”。三种质量结果可以公平比较，顺序计时仍受OS缓存影响，不能声称严格公平的冷启动速度提升。若以后需要“未缓存问题的逐题真实网络延迟”，须另外设计独立且同等冷缓存实验并另行授权；本轮不预支。

### 3个无依据问题的独立证据复核

`hard-14`（出差机票报销）、`hard-15`（股票涨幅）、`hard-16`（员工年假）保留原标注。独立复核人先通读全部4份政策确认“库内无可支持答案”，再逐模式查看Top5全文，记录支持与否、chunk_id、理由、姓名和时间；相同词或同文档不算直接支持。

预检JSON含3题×3模式的空复核表，`supports_question=null`，不预填通过。原字段 `no_support_correct` 为兼容保留，但只统计“候选为空”；新生成summary明确称“负例空召回数（候选诊断）”。它**不是无依据问题判定准确率**。当前库没有经过验证的语义证据充分性判别器/拒识阈值：即使人工确认所有候选不支持，也不表示系统会自动拒答。自动安全拒答能力仍未验收，不能写成生产可用。

## 6. PowerShell步骤（准备与付费步骤严格分开）

### 6.1 现在允许执行：本地配置/清单检查

```powershell
$sfRepo = Join-Path $env:USERPROFILE 'Documents\ChatGPT\企业客服多Agent系统'
Set-Location -LiteralPath $sfRepo
$sfPython = Join-Path (Get-Location).Path '.venv\Scripts\python.exe'
& $sfPython -c "import sys; print(sys.executable)"
& $sfPython -m evaluation.prepare_embedding_acceptance
if ($LASTEXITCODE -ne 0) { throw '本地预检查失败，停止' }
# 输出新报告路径；Key只显示配置true/false。检查人工授权、预算与指纹，不因退出0直接执行live。
```

不需要重新安装环境，不使用Conda base的python。新报告输出目录必须不存在，避免覆盖历史。第7节旧命令的参数语法有效；“先只建19片段，再rebuild含36题”的连续执行会额外付费，不推荐。下面复用现有builder/cache比较，无需另实现检索系统。

### 6.2 未来明确授权并解决门禁之后：仅一次真实构建（本轮未执行）

先由本人私下配置独立Key和控制台Base URL，不在文档命令、shell历史或聊天里写入真实Key。本轮没有修改现有.env。该步骤只描述未来进程设置；固定北京示例若不符合本人地域，应先重审价格/授权，不能直接照抄。

```powershell
# 禁止现在整段执行；完成第4/8节门禁并明确授权后才允许。
# 本机私有环境已配置 EMBEDDING_API_KEY / EMBEDDING_BASE_URL，绝不打印。
$env:EMBEDDING_MODEL = 'text-embedding-v4'
$env:EMBEDDING_DIMENSIONS = '1024'
$env:EMBEDDING_TIMEOUT_SECONDS = '20'
$env:EMBEDDING_MAX_RETRIES = '0'
$env:EMBEDDING_ENABLED = 'true'
$env:RAG_REMOTE_QUERY_ENABLED = 'false'
$env:RAG_MODE = 'tfidf'
$env:RAG_RRF_K = '60'
$env:RAG_CANDIDATES = '20'
$sfRun = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$env:RAG_CACHE_DIR = Join-Path (Get-Location).Path ".rag_cache\acceptance-$sfRun"
if (Test-Path -LiteralPath $env:RAG_CACHE_DIR) { throw '必须用新的私有缓存目录' }
$sfPlan = ".\evaluation\reports-rag-preflight-$sfRun"
& $sfPython -m evaluation.prepare_embedding_acceptance --output $sfPlan
if ($LASTEXITCODE -ne 0) { throw '预检失败' }
$sfCheck = Get-Content -Raw -Encoding UTF8 (Join-Path $sfPlan 'latest.json') | ConvertFrom-Json
if (-not $sfCheck.configuration.api_key_configured -or
    -not $sfCheck.configuration.embedding_configuration_valid -or
    -not $sfCheck.configuration.candidate_model_matches -or
    $sfCheck.configuration.endpoint_region -ne 'cn-beijing' -or
    $sfCheck.inventory.request_plan.cold_build_no_retries -ne 6 -or
    $sfCheck.inventory.corpus_hash -ne '4b278ac391adc7540f2953a4ac32ccf7ed9083915cd7c33287df9075daba293b' -or
    $sfCheck.inventory.dataset_hashes.'rag_cases.jsonl' -ne '71459735681cabd5c315e1bba7cb3c5a2a91963d9f621889e40219f42f687d84' -or
    $sfCheck.inventory.dataset_hashes.'rag_hard_cases.jsonl' -ne 'e1f185e8d9e2e499d148b9d357c1a4dbae36966d8455cc088b4c8261419ddabf') {
    throw '配置/地域/语料/问题集有变化，重新审查后再授权'
}
# 上述检查不能验证Key地域/额度，不能代替数据所有者和硬预算授权。
$sfApproval = Read-Host '仅在门禁已满足且本次已被明确授权时，输入 ALLOW-ONE-BUILD-6；否则回车停止'
if ($sfApproval -cne 'ALLOW-ONE-BUILD-6') { throw '没有授权，停止' }
$sfBuild = ".\evaluation\reports-rag-real-build-$sfRun"
& $sfPython -m evaluation.build_policy_index --mode live --allow-remote --max-embedding-calls 6 --include-eval-queries --output $sfBuild
if ($LASTEXITCODE -ne 0) { throw '真实构建失败；保留报告，禁止自动重跑或扩大预算' }
# 没有--rebuild：新私有缓存不覆盖既有索引。不要再运行一次doc-only构建或live比较。
```

口令只是防误粘贴的人机确认，不是费用控制或持久授权系统；现在不得运行。无论失败或成功，第二次付费命令都需要新的授权。任务期间不要改源码/政策/环境，不并发构建。

### 6.3 构建成功后：三模式对照、缓存复验、结果与费用导出（均离线）

```powershell
$sfCompare = ".\evaluation\reports-rag-real-cache-first-$sfRun"
& $sfPython -m evaluation.compare_rag --mode offline --source cache --output $sfCompare
if ($LASTEXITCODE -ne 0) { throw '真实缓存无效或发生回退；不能作为Dense验收通过' }
$sfWarm = ".\evaluation\reports-rag-real-cache-repeat-$sfRun"
& $sfPython -m evaluation.compare_rag --mode offline --source cache --output $sfWarm
if ($LASTEXITCODE -ne 0) { throw '缓存复验失败；停止，不联网补齐' }
$sfExport = ".\evaluation\reports-rag-real-acceptance-summary-$sfRun"
& $sfPython -m evaluation.prepare_embedding_acceptance --build-report (Join-Path $sfBuild 'latest.json') --comparison-report (Join-Path $sfCompare 'latest.json') --price-region cn-beijing --output $sfExport
if ($LASTEXITCODE -ne 0) { throw '报告来源/指纹/模型/地域不符或文件错误，停止' }
# compare输出 latest.json / details.csv / summary.md；导出JSON另含缓存命中、实际尝试、usage完整性与费用估计。
# 对第二份$sfWarm报告可同样生成一份新导出，再比每题source/chunk_id/score；耗时不要求完全相同。
```

`source=cache`使用真实向量，但模型此时不在线；结果应标 `real_cached_dense`，不是Mock也不是新一次网络测试。0网络是设计目标，不是缺少模型权限的证明。导出器拒绝Mock来源、不同语料/数据集、模型/维度/价格地域不匹配；它不是独立验收官，最终仍须人工核对36题齐全、三模式实际执行和证据表。

不要对逐题trace中的embedding_calls求和。费用导出只加build和compare的顶层独立ledger，actual费用不完整时明确未知部分。原始JSON/CSV为本地私有数据，不自动同步GitHub。完成后恢复 `EMBEDDING_ENABLED=false`、`RAG_REMOTE_QUERY_ENABLED=false`、`RAG_MODE=tfidf` 并重启业务服务；不要修改真实.env来执行本轮准备。

## 7. 拟定验收门槛（先确认，后测量）

以下是建议的预注册标准，不是本轮已通过结果，需本人同意后冻结。

1. 工程硬门槛：真实构建成功且总尝试≤6，重试0，三模式覆盖相同20+16题，Dense/Hybrid回退0；模型/维度/所有指纹一致，真实usage不能填Mock数；第二次cache复验远程请求0、Dense/Hybrid缓存命中36/36、逐题排名/分数可复现。任一不满足即真实工程验收失败。
2. 安全硬门槛：外发只有授权冻结文本，Key无输出，未读取真实订单/历史，未越预算；缺用量记录不得声称费用审计完整。费用超过已授权限额即停止并调查，不加预算重跑。
3. 质量对照：分别完整汇报Real Dense/Hybrid对原TF-IDF的R@1/3/5、MRR和证据Hit@K。暂建议Hybrid在历史20题Evidence Hit@3≥19/20且文档Recall@3≥19/20；困难13题Evidence Hit@3≥8/13（不低于当前TF-IDF），MRR≥当前TF-IDF的0.8076923。未满足则“已测量但不建议替换TF-IDF”，保留失败题，不通过调gold获得通过。Dense即使差也要如实记录，不删掉。
4. “效果提升”必须有正向数据（例如困难证据Hit@3至少9/13，同时未违反上述不退化门槛）；样本很小，1题变化不证明统计显著或真实客服ROI。不必为了工程验收虚构提升。
5. 无依据安全：3题×3模式均完成人工证据复核；不得把任何不支持的候选当作可回答依据。没有自动证据充分性/拒答验证时只能说“完成检索对照和人工风险评估”，不能宣称自动拒答安全或生产问答验收通过。
6. nDCG未具备有效qrels时合法报告N/A并说明原因，不伪造相关等级；没有预注册远程延迟SLA，不给毫秒阈值编“通过”。只比较所记录的本地延迟范围，不混入远程构建耗时。

工程验收、真实模型质量验收、生产上线验收是三个结论，不用一个“全部通过”掩盖剩余风险。

## 8. 待本人手动确认与授权

- 私下配置独立Key、官方Base URL、v4/1024，并在控制台确认Key和模型地域、权限、账户计价与额度；不要把Key发送给助手。
- 确认冻结的4份政策+36个合成问题有权发送至选定地域，不包括后续真实客户输入。
- 确认费用/Token上限的保障方式。现有精确Token/人民币预扣未实现；若这是硬要求，必须先补齐可验证门禁，本轮不会绕过。
- 复核并冻结gold；同意第7节门槛、总请求6次/重试0/只运行一次、失败不自动重试。需要不同方案时重新计算，不采用原40次live比较。
- 门禁全部满足后，再明确授权“对冻结模拟语料执行一次真实Embedding验收构建”。本轮到此停止，不因配置后来变为true自动执行。

## 9. 本轮离线验证记录

专项：`python -m pytest tests/test_embedding_acceptance_preparation.py tests/test_hybrid_rag.py -q`，**119 passed，27.11秒**，使用本项目`.venv`；新增测试36个，含官方域名识别、Secret不输出、原数据不变、远程配置下预检仍无客户端、请求计划、Mock报告拒绝、指纹/地域/维度校验、缺usage不当0、累计ledger不重复相加、负例人工表保持pending、v4 total-only SDK模拟兼容等。

本轮实际完整执行：

| 检查 | 结果 |
|---|---|
| 全部后端Pytest | **277 passed，0 failed，100.53秒**；比基准241项新增36项，未删除原测试或放宽断言 |
| pip check | **No broken requirements found** |
| compare_rag --mode offline | **完成，Mock，真实Embedding尝试0**，20+16题与原六组Recall/MRR/证据命中指标一致，各模式回退0 |
| PowerShell命令 | **3段语法解析通过，未执行付费命令** |
| 差异与敏感信息检查 | git diff --check通过；6个变更文件及4个新产物扫描无Key/私钥样式或本地已配置密钥值命中；此扫描不是完整DLP审计 |
| .env完整性 | 前后SHA256一致；未改动 |

后端命令使用 `.venv/Scripts/python.exe`，完整回归临时目录为`.pytest_tmp_phase3a_preparation_full_20261024`，离线结果目录为`evaluation/reports-rag-compare-offline-mock-20261024T112055Z-26c6ac`。复跑时不要用业务目录当Pytest的basetemp。

前端本轮没有代码变更，也未重新运行Vitest或生产构建；历史前端23项通过不冒充本轮重跑。真实Dense/Hybrid效果、在线API延迟、供应商usage及账单仍未测量。三负例仍在Mock三模式下均返回候选，旧空召回计数均0/3；这不是自动“有证据/无证据”的成功结论。

本轮生成的模型响应全部来自内存替身或httpx.MockTransport；不访问模型网络。本地真实`.env`前后SHA256一致。Git变更仅本准备工具、测试、用量兼容修复和相关文档/报告措辞；保持未暂存、未提交、未推送。

## 10. 最终审查与独立本地提交记录（2026-10-24）

本次开始时分支与基准一致：`feature/phase3a-hybrid-rag` / `228e7fcada1688f1c1bb157176e76432051e8502`。检查了status、完整未暂存diff、cached diff与全部非忽略未跟踪文件；暂存区为空，恰有以下6个相关变更，没有发现额外用户修改，也没有覆盖、丢弃、删除或重置文件。

| 文件 | 纳入本次提交的内容 |
|---|---|
| `evaluation/prepare_embedding_acceptance.py` | 无远程入口的配置预检、文本/请求/费用规划、真实报告本地汇总、负例人工证据复核模板 |
| `support_agent/embedding_client.py` | 仅v4的total-only usage兼容；未知模型不推断，非法/缺失用量保持未知 |
| `tests/test_embedding_acceptance_preparation.py` | 36项离线执行用例，包含SDK MockTransport；不改原测试断言 |
| `evaluation/compare_rag.py` | 将负例空召回标为候选诊断，不冒充政策证据判定；原指标字段兼容 |
| `docs/PHASE3A_HYBRID_RAG.md` | 用量映射说明和验收准备门禁链接 |
| `docs/PHASE3A_LIVE_ACCEPTANCE_PREPARATION.md` | 本准备报告、命令、预算边界、验收标准和本节审查记录 |

逐文件复核了纯本地边界、URL地域识别、缓存/数据集指纹、请求批数、费用单位、usage缺失、累计ledger避免重复相加以及Mock与真实数据来源隔离。没有发现阻断本离线准备提交的问题。预检的`ready_to_call=false`不是授权门禁实现，费用代理估计不充当真实Token或账户预算；报告不自动判定验收通过。

本次只做额外的文档隐私清理：运行示例改用`USERPROFILE`拼接项目路径，不提交本机用户名绝对路径。密钥/私钥样式、本机已配置密钥值及个人信息检查未发现真实泄露；邮箱样式的唯一匹配为测试中故意构造的URL凭证拒绝样例，并非真实邮箱。`.env`前后哈希一致；忽略规则覆盖`.env`、缓存、数据库、测试临时目录及运行报告，实际只允许暂存上表6个文件。没有活动Git提交钩子要求额外执行。

### 本次重新执行的结果（不是历史结果）

| 检查 | 结果 |
|---|---|
| Python | `sys.executable`、`sys.prefix`均指向本项目`.venv` |
| 全部后端Pytest | **277 passed，0 failed，106.13秒** |
| pip check | **No broken requirements found** |
| `evaluation.compare_rag --mode offline` | **退出0，mock_dense，真实Embedding尝试0** |
| 离线指标复核 | 20题基线+13困难正例+3无依据问题保留；六组Recall/MRR/证据命中与准备阶段报告一致，各模式回退0 |
| 文档PowerShell | **3段仅语法解析通过，未执行付费命令** |
| Git差异检查 | `git diff --check`通过；提交前另检查cached diff与明确的6文件暂存白名单 |
| 前端 | 未修改，不重跑Vitest/生产构建，不引用历史结果作为本轮执行结果 |

测试使用新的唯一临时/输出目录，避免清理已有目录。本次私有证据位于`evaluation/reports-rag-preflight-commit-6982c4dfd3ee4a98a313a2269b35c223/`：`pytest.xml`及`comparison/latest.json`、`details.csv`、`summary.md`。目录被忽略，不纳入提交。测试环境显式关闭聊天Key和远程RAG，模型响应均为替身或MockTransport，**真实Embedding与聊天模型API请求均为0，没有构建真实索引**。

### 提交范围与剩余风险

用户本次明确授权独立本地提交，提交信息为`feat(rag): add offline embedding acceptance preflight`。提交是否成功及具体SHA以本地Git记录和最终交付消息为准，避免在提交自身文件中写入错误的父SHA。禁止Push、Merge、Rebase或删除分支；本地提交不等于GitHub已更新。

仍未解决、但不阻断本准备代码提交的风险：独立Embedding配置/地域/账户权限尚未完成真实验证；精确Token/人民币预算预扣未实现；数据外发需所有者授权；独立相关性标注与3题无依据证据复核未完成，nDCG保持N/A；真实Dense/Hybrid效果、在线延迟、usage与供应商账单均未实测。当前Mock三模式对3个负例均返回候选，不能声称自动拒答安全。这些事项仍阻止开始真实付费验收或宣称生产上线通过。
