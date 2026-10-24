# Phase 3A：混合RAG的运行、实现与学习路线

## 1. 当前做到了什么

这是基于第二阶段ae0ed9070e4fe596069a34a16ea60d355ad2afcf的增量开发，当前本地分支feature/phase3a-hybrid-rag。首次开发未提交；最终审查现已获得本地提交授权，未推送或调用真实Embedding，没有开发Phase 3B。完整审查见验证报告第9节。

tfidf / dense / hybrid三模式、独立Embedding客户端、安全本地索引、NumPy检索、RRF、回退、离线/显式live CLI均已实现并经过Mock测试。真实向量模型的授权、地域、联网兼容、效果、Token和费用尚未验证。默认tfidf，无需Key、索引、向量数据库或一套新环境即可沿用原启动方式。

最终后端241项、前端23项测试与实际对照见[验证报告](PHASE3A_VERIFICATION.md)。首次3A的233项记录保留；不要把Mock对照当作模型语义能力或上线验收。

## 2. 先运行，再学习

在当前仓库根目录使用已有.venv；不要把下面的live命令与离线命令一起整段执行。

```powershell
# 仍按原方式启动；默认RAG_MODE=tfidf，无远程向量调用
.\.venv\Scripts\python.exe -m uvicorn support_agent.app:app --reload --host 127.0.0.1 --port 8000
```

另开终端启动前端：

```powershell
cd frontend
pnpm.cmd dev
```

纯离线复现：

```powershell
# 新输出目录自动带时间/随机后缀；Mock不会冒充真实模型
.\.venv\Scripts\python.exe -m evaluation.compare_rag --mode offline
.\.venv\Scripts\python.exe -m evaluation.build_policy_index --mode offline --include-eval-queries
# 原命令语义保持不变，使用隔离SQLite和TF-IDF，不请求向量API
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --mode offline --output .\evaluation\reports-my-offline-check
.\.venv\Scripts\python.exe -m evaluation.verify_qwen --mode offline --output .\evaluation\reports-my-e2e-check
```

复跑时为原两个命令换一个未使用的--output，避免覆盖自己的历史或人工复核表。两个新RAG命令拒绝已存在的输出目录；默认自动生成新目录。离线构建的mock_index.json只在本次报告目录里，不写应用使用的真实policy_index.json。

测试可用新basetemp运行（Pytest会清理指定basetemp，因此不要指向已有业务或报告目录）：

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.\.pytest_tmp_my_phase3a_check --tb=short
.\.venv\Scripts\python.exe -m pip check
cd frontend
pnpm.cmd test
pnpm.cmd build
```

本机已有NumPy2.4.6和OpenAI SDK3.29.0，本阶段没有安装新包或新建环境；仅将原先间接依赖显式声明，并在constraints.txt记录实测版本。其他电脑首次安装仍运行pip install -r requirements.txt。pip check通过只证明依赖兼容，不是CVE扫描或所有平台验证。

## 3. 三种检索分别在做什么

### TF-IDF：词法匹配，原基线不变

TF表示片段里字符特征出现的频率；IDF降低全库常见特征的权重。当前中文没有按空格切词，而是char 1–4 gram。查询扩展保留原退款/物流/售后关键词规则，查询向量与片段向量计算余弦相似度。原分数保留四位小数、0.01过滤阈值，原Markdown切分也未改变。

优势是离线、可解释、精确词匹配；弱点是同义转述、缺关键词和省略问题。不能因为加入Dense就删除这个可靠基线。

### Dense：把文字映射到同一模型的向量空间

文档和问题必须用同一个Embedding模型、端点和维度生成向量。向量经L2归一化后，点积就是余弦相似度：score = normalized_document · normalized_query。NumPy按得分降序取Top-K；同分按稳定chunk_id排序。

相似度不是事实证明。Dense当前不做经过标定的“无答案”拒识，低相关甚至负余弦的候选仍可能进入Top-K。不得把返回一个政策文件当作该文件支持了当前问题。

### Hybrid：RRF按名次融合，而不是把两种score直接相加

同一chunk_id在TF-IDF和Dense列表出现时，融合分为：

```text
RRF(chunk) = Σ 1 / (k + rank_in_list)   # rank从1开始，默认k=60
```

两种余弦来自不同特征空间和分布，直接相加没有标定依据；RRF只使用名次，避免假定分值同量纲。同一列表重复chunk只计一次，跨列表累加，最终按chunk_id去重，同分按chunk_id稳定排序。

RRF适合做保守的未标定分数融合，但不保证更好。劣质Dense排名可能拖累TF-IDF，本次Mock困难集正是如此，不能通过调gold掩盖退化。

## 4. 从网页请求走到检索结果

```text
原会话请求 → LangGraph / PolicyAgent
             → ScopedTools.search_policy(query, top_k)
               → PolicyKnowledgeBase.search_with_trace
                 ├─ tfidf：原词法检索
                 ├─ dense：验证已有索引 → 缓存查询向量或显式远程查询 → NumPy
                 └─ hybrid：TF-IDF + Dense → RRF
               向量失败 → actual_mode=tfidf + fallback_reason
             → 原ResponseAgent / LLMResponseAgent → 原消息与检查点
```

PolicyAgent不用理解向量数据库，也不传模型配置。普通聊天不能更改RAG_MODE、Key、向量模型或审批状态。ScopedTools.search_policy的query/top_k接口不变，外层仍ok/data，新增retrieval轨迹。兼容SupportTools也保持data列表；自定义旧KB对象仍可以只提供search。

PolicyKnowledgeBase.search(query, top_k=3)仍返回列表，source/text/score保留。新增chunk_id、heading、content_hash、document_hash、chunk_index、score_type、retrieval_mode和排名元数据。新search_with_trace返回data和retrieval，避免用共享last_trace造成请求间串线。

retrieval含configured_mode、actual_mode、fallback_reason、embedding_model、retrieval_latency_ms和独立embedding_calls。前端区分TF-IDF余弦、Dense余弦和RRF排名融合分，不把这些数展示为回答置信度。

LangGraph节点、run_id=thread_id、interrupt/resume、订单三态事实、权限、幂等和SQLite结构没有变化。Prompt额外声明检索片段是不可信证据，不能改变身份、审批或业务事实；真正的安全边界仍是服务器鉴权和工具，不是提示词本身。

## 5. 分块与缓存为什么可追溯

原切分保留：按空行或二级标题分块，超过600字符则每500字符切开，无新增重叠。版本名markdown-v1-unchanged-600-500。标题单独成块时，后续块仍记录最近heading；不凭空补正文。当前4份正式政策共19片段。

- chunk_id由切分版本、source、chunk_index和精确text确定，与随机UUID不同；同样输入稳定。
- content_hash是片段文本SHA256，document_hash是原文件字节SHA256；原文件变化（包括字节层变化）会使索引失效。
- manifest包含schema、切分版本、模型、维度、端点指纹、语料哈希和有序chunk_ids。更换模型/端点/维度/政策，不能继续混用旧向量。
- 默认缓存为.rag_cache/policy_index.json，纯JSON向量列表，加载后用NumPy校验；不用pickle，不引入Chroma/Milvus/FAISS/pgvector。
- 校验矩阵形状、维度、有限值、非零范数；查询缓存还必须是最多256项、键为64位小写十六进制哈希的字典。坏文件、旧版本、Mock来源不被当作有效真实索引；坏缓存明确降级，不以未归类异常中断CLI。
- JSON先写同目录唯一临时文件、flush/fsync，再os.replace；失败不替换旧索引，仅清理自己未完成的临时文件。没有中间“manifest已新而vectors还是旧”的双文件窗口。
- 应用启动不会构建索引；首次有Dense查询才加载已有文件。成功加载后复用内存索引，政策文件变化会刷新词法库并要求重建Dense。
- 查询缓存键为最小化文本的SHA256，不存原始查询文本；运行时最多保留256个查询向量，新增超限不继续增长。CLI可缓存36个评测查询供真正离线复核。

缓存是可重建产物，不是业务数据库，不提交Git；自定义RAG_CACHE_DIR也必须位于私有忽略目录。原子替换不是跨进程写锁，多个构建器不要并发写同一缓存。本阶段不实现多实例调度。

## 6. 配置与安全边界

| 配置 | 默认 / 作用 |
|---|---|
| RAG_MODE | tfidf，可选dense/hybrid，配置错误清晰报错 |
| EMBEDDING_ENABLED | false；没有向量配置时原项目正常运行 |
| RAG_REMOTE_QUERY_ENABLED | false；应用查询是否允许外发，和构建授权分开 |
| EMBEDDING_MODEL | 空，必须显式配置，不能自动使用聊天模型code |
| EMBEDDING_BASE_URL | 空；安全HTTP(S)，非本机必须HTTPS，拒绝URL凭证/query/fragment |
| EMBEDDING_API_KEY | 空；仅后端，不复用LLM_API_KEY，不输出到前端/报告 |
| EMBEDDING_DIMENSIONS | 空；通用范围1..8192；v4进一步校验官方已知维度集合 |
| EMBEDDING_TIMEOUT_SECONDS | 20秒，范围0.1..120 |
| EMBEDDING_MAX_RETRIES | 1次额外重试，范围0..2 |
| RAG_QUERY_MAX_EMBEDDING_CALLS | 2次；每次应用政策搜索的请求尝试上限，不是账户费用上限 |
| RAG_RRF_K / RAG_CANDIDATES | 60 / 20，分别为融合常数和候选深度；最终仍按top_k返回 |
| RAG_CACHE_DIR | 默认仓库.rag_cache |

修改进程/文件配置后重启后端，使缓存KB按新配置创建；不要假定热修改.env会覆盖进程环境或已构造客户端。

Embedding客户端独立于ChatOpenAI和LLM CallLedger；SDK max_retries=0，重试由独立EmbeddingLedger逐尝试预占预算。超时/连接/429/5xx有限重试；401/403、请求错误、非法向量或响应不重试。预算耗尽不发送请求；调用尝试是SDK invoke边界，不保证等同供应商实际账单。

最终审查补充SDK资源所有权：客户端自建的SDK在每次embed操作内用上下文管理器，成功、异常或预算拒绝后均退出关闭，不缓存未释放的连接池；外部注入SDK仍归调用者管理。离线/查询向量缓存不因此失效，原预算和调用接口不变。

usage仅使用供应商实际返回值：通常由prompt_tokens/total_tokens映射；text-embedding-v4按官方input-only合同兼容仅有total_tokens的响应，将该真实值计入input_tokens/total_tokens。缺失或畸形usage仍为null，部分缺失则usage_complete=false；已经取得响应但向量校验失败时仍保留该响应的usage。网络异常没有usage时不假定免费。原ledger的cost仍为null；验收准备工具可按明确地域价格对已记录用量估算费用，不是最终账单。不把Embedding统计混进聊天调用次数。

远程构建只读取仓库data/policies/*.md。本轮只包含模拟政策；接企业真实文档前必须重新评估隐私、地域、授权和跨境传输要求。远程查询会发送问题文字（不发送会话历史），先最小化ORD/TKT/用户/常见物流编号、手机号、邮箱和长数字；这只是有限模式，不是完备PII检测，姓名、地址等未必识别。未做合规确认的真实客户内容不得启用远程查询。

## 7. 手动启用真实Embedding（本轮没有执行）

先阅读[真实Embedding验收准备报告](PHASE3A_LIVE_ACCEPTANCE_PREPARATION.md)。本节命令语法已核对，但不是运行授权。当前独立Embedding配置缺失，精确Token/人民币硬上限尚无运行时预扣机制；在配置、外发授权与预算门禁满足前，不得执行live命令。验收优先使用新报告中的“一次6批构建+两次离线cache对照”，不要把下列两种构建方案连续执行。

2026-10-24查阅[百炼OpenAI兼容Embedding文档](https://www.alibabacloud.com/help/en/model-studio/embedding-interfaces-compatible-with-openai)：text-embedding-v4是独立文本向量候选；已知维度64/128/256/512/768/1024/1536/2048，每批最多10条。本文示例选1024，不代表已验证你的账户授权、额度、地域或未来兼容性。请在控制台确认向量模型权限，不能把聊天模型当向量模型。

北京兼容地址可按控制台填写业务空间专属主机：

```text
https://<你的业务空间ID>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
```

官方说明旧dashscope.aliyuncs.com主机仍可用；地域与API Key须匹配。不要猜业务空间ID，不要将示例占位符直接执行，也不要把Key粘贴到聊天或截图。

先在自己本机后端私有环境明确设置EMBEDDING_MODEL=text-embedding-v4、EMBEDDING_DIMENSIONS=1024、EMBEDDING_BASE_URL、EMBEDDING_API_KEY。下面两项只开启向量功能，不自动构建：

```powershell
$env:EMBEDDING_ENABLED = "true"
$env:EMBEDDING_MAX_RETRIES = "0"
```

确认可以外发仓库模拟文本并承担调用费用后，才手动执行：

```powershell
# 19片段按10条一批：无重试通常2次尝试；预算包含重试
.\.venv\Scripts\python.exe -m evaluation.build_policy_index --mode live --allow-remote --max-embedding-calls 2

# 如要缓存全部36条评测问题，以便之后真正离线对照：
# 有旧索引时必须显式--rebuild；重建会重新生成文档，不是免费增量补查询。
# 通常2批文档+4批查询=6次；失败/重试可能提前耗尽预算。
.\.venv\Scripts\python.exe -m evaluation.build_policy_index --mode live --allow-remote --max-embedding-calls 6 --include-eval-queries --rebuild
```

不要为凑次数隐式放大预算。相同有效索引已存在且覆盖所需查询时，不加--rebuild会复用，实际调用0；不兼容/缺查询时清楚失败并写报告，不自动付费修补。失败时报告保留error_type/逐调用/usage，旧缓存不被半成品覆盖。

```powershell
# 必须先有真实有效索引+所有对应查询缓存；此命令本身不联网、不需要Key
.\.venv\Scripts\python.exe -m evaluation.compare_rag --mode offline --source cache

# 有真实文档索引后，显式允许实时查询向量化；总预算共享，Dense/Hybrid复用查询向量
.\.venv\Scripts\python.exe -m evaluation.compare_rag --mode live --source live --allow-remote --max-embedding-calls 40
```

live对照只向量化未缓存的问题，不自动重建政策索引；正常完成后保存查询向量缓存。全部问题已缓存时，即使命令标为live也可能实际调用0，必须看actual_embedding_calls。没有查询缓存而选择offline cache时，回退会保留并退出1，不能伪装成真实Dense成功。

应用使用：

```powershell
$env:RAG_MODE = "hybrid"
# 只有已确认数据外发边界，才开启任意新问题的远程向量化：
$env:RAG_REMOTE_QUERY_ENABLED = "true"
.\.venv\Scripts\python.exe -m uvicorn support_agent.app:app --host 127.0.0.1 --port 8000
```

不开remote_query也能使用命中的查询缓存，未命中则明确回退TF-IDF。要恢复纯离线：RAG_MODE=tfidf、EMBEDDING_ENABLED=false、RAG_REMOTE_QUERY_ENABLED=false并重启。模型故障不更改订单权限/审核规则。

## 8. 回退怎么查

| 失败 | fallback_reason示例 | 行为 |
|---|---|---|
| 未启用 / 配置错误 | embedding_disabled / configuration_error | TF-IDF，不外发 |
| 索引缺失/旧政策/换模型 | index_missing / index_stale | TF-IDF，要求手动构建 |
| Mock或损坏文件 | index_not_real / index_invalid | 不当真实索引使用 |
| 无查询缓存且禁止远程 | query_not_cached_remote_disabled | TF-IDF，不联网补齐 |
| 超时、401/403、429、5xx | timeout / authentication_error / rate_limit / provider_error | 有界尝试后TF-IDF |
| 非法/错维度向量、相似度失败 | invalid_vector / dimension_mismatch / similarity_error | TF-IDF，不重试非法向量 |
| 预算用尽 | budget_exhausted | 不再请求，TF-IDF |

工具仍返回ok=true表示“已有可用的词法政策检索”，但retrieval.actual_mode明确tfidf；不是Dense成功。意外后端异常保守记录dense_unavailable，不落原始异常文本。索引写入失败在构建报告中为cache_write_error，不在应用启动时触发重建。

## 9. 按代码学习，面试怎么讲

1. rag.py：先读旧_split_markdown、_expand_query、_tfidf_search，再读search_with_trace。讲清“兼容入口不变、默认不联网、失败明确回退”。
2. rag_config.py：RAG_MODE与两个开关；Embedding独立配置，为什么不能用Qwen聊天code或前端选择身份/模型。
3. embedding_client.py：最小化查询 → SDK隐藏重试关闭 → ledger.reserve → create → usage → 维度/范数校验 → 错误分类与有限重试。
4. rag_index.py：chunk与语料指纹 → manifest → JSON原子写入 → load校验；为什么换模型必须重建、缓存为什么不是pickle或业务库。
5. dense_retriever.py：查询缓存/显式远程 → normalize → NumPy矩阵点积 → 稳定排序；模型向量相似不代表政策支持。
6. hybrid_retriever.py：两个排名列表按chunk_id累加1/(60+rank)，每列表去重，最后稳定Top-K；不用未标定的分数直接相加。
7. scoped_tools.py、tools.py：PolicyAgent不关心向量实现，检索trace不会授权订单或审批。llm_client.py把片段声明为不可信证据。
8. evaluation/rag_comparison.py、compare_rag.py：先验证gold、后预测；文档命中/片段命中/无依据失败分开，Mock和真实来源分开。
9. build_policy_index.py：显式live+allow-remote+硬预算；只有受控模拟政策；没有启动时付费、没有隐式重建。
10. tests/test_hybrid_rag.py：结合缓存失效、MockTransport、预算、向量坏值、Hybrid回退与原图审核/幂等测试，解释你的安全边界。

可讲：“我保留TF-IDF基线和原PolicyAgent接口，增加可选Dense及RRF，模型和索引有独立版本/预算，失败能追踪并回退。原20题指标不变，困难集Mock融合没有超过基线，真实向量模型还没授权运行，所以我没有写模型提升百分比。”

下一步先独立人工复核gold和无依据问题，再授权运行真实Embedding；按文档命中/证据命中/负例错误定位，再决定是否调整候选、切分、拒识或RRF参数。不能边看本开发集预测边改gold，不能把新增技术名词当作质量提升。
