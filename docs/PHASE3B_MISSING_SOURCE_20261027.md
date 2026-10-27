# Phase 3B missing_source 精准修复（2026-10-27）

## 1. 真实报告核验

原始目录：evaluation/reports-tool-live-unsafe-review-20261027-135759-933/。
只读取报告的结构化字段，没有输出被拒绝的原始候选；原始报告和本地诊断均不修改。
报告中的源码指纹在本轮修改前与本地代码一致，不是运行了未修复的其他目录。

| 已存在的真实结果 | 核验值 |
|---|---|
| 模型 / 重试 / 请求预算 | qwen3.7-flash-2026-07-15 / 0 / 8 |
| 模型请求 / 校验成功 / 失败 | 5 / 4 / 1；第五次 unsafe_reply |
| 供应商 usage | input=4880，output=410，total=5290，usage_complete=true；非本轮调用 |
| 第一轮 | model_generated，violations=[]，policy_source_present=null |
| 第二轮工具 | query_order、search_policy 均已授权并执行成功 |
| 第二轮政策数据 | 3 个片段；去重后的 source 仅 refund_policy.md |
| 第二轮候选校验 | violations=["missing_source"]；policy_source_present=false；receipt_state=unknown |
| 停止位置 | turn_2；stopped_after_turn=2；第三轮没有执行 |

policy_source=true 检查的是 retrieved_docs 包含 refund_policy.md，不是模型是否引用它。
turn_2_facts 检查的是最终返回的回退文本，也不能当成被拒绝候选的完整语义正确证明。
reply_validation 才是候选在拒绝前保存的有限规则校验结果。

## 2. missing_source 的准确规则

shared reply_safety.reply_violations 当前实现为：

1. sources 是本轮 retrieved_docs 中 source 字段的集合。
2. cited 是从候选原始文本用正则 [A-Za-z0-9_-]+\.md 提取的标识集合，区分大小写。
3. cited 中出现不在 sources 的标识，报 unsupported_source。
4. sources 非空且 sources 与 cited 交集为空，报 missing_source。

需要至少出现一个当前检索返回的完整文件标识，不要求把每个片段都引用一遍，也不要求 JSON 结构化输出。
没有强制标签外壳；裸文件名、【来源：文件名】、反引号及 Markdown 链接均可，只要完整 source 原样存在。
例如本次 sources 只有 refund_policy.md，所以必须出现该完整标识；不是代码对所有问题硬编码这个文件。
其他场景若实际返回 membership_policy.md，就应引用后者；shipping_policy.md 即使在仓库存在，
没有被本轮检索返回也不能引用。真实来源加一个虚构来源仍然会拒绝。

原来的 policy_source_present 由 any(source in candidate) 计算；本次为 false，
说明候选没有任何完整的本轮 source 子串。因此没有证据表明上述合法外壳被误判。
没有原始候选可安全回看，不能声称模型实际用了哪个中文标题、解释句或其他别名。

## 3. 根因判断与本轮修改

直接原因是候选未提供系统要求的可识别来源标识。旧 Prompt 已要求“政策回复保留本轮source”，
ToolMessage 也包含每个片段的 source 和 reply_contract.policy_sources；不是检索工具没提供来源。
但 Prompt 没有明确“完整原文件名、后缀、大小写、至少一个标识”的规范，也没有动态引用示例。
因此本轮加强 Prompt/输出合同的明确性，不把它描述为完全没有旧引用要求，亦不把失败归为校验误判。

生产代码仅调整 support_agent/tool_calling.py 两处：

- reply_contract：从现有真实来源集合生成 policy_citation.required、format 和 examples；
  格式推荐【来源：<source>】，示例为本轮 source 动态构造，来源为空则 examples=[]。
- ToolCallingAgent.run 的系统 Prompt：使用最新工具结果的合同，至少原样保留一个 source，
  不允许仅用中文标题代替，所有引用必须来自本轮来源集合，无政策证据不得下确定性结论。

**不改** reply_safety.py、tool_reply_violations、validate_final、retrieval 数据、校验通过条件或评测标签。
服务端没有给回复追加固定文件名，model_generated 的正文仍是模型候选本身（仅原有 strip）。
missing_source、unsupported_source、缺政策证据门禁、签收三态、订单归属、人工审核、幂等和失败即停全部保留。
示例用于指导生成，不能保证真实模型每次都遵守；仍需第三次独立在线验收。

## 4. 新增回归与执行过程

新增 tests/test_tool_policy_citations.py 共17项：

- 3项动态合同：单一来源、不同真实来源名集合和空来源；无固定退款文件依赖。
- 4种引用形式通过：来源标签、裸文件名、反引号、Markdown链接。
- 仅中文标题/漏引触发 missing_source；虚构文件、未检索文件、大小写不一致拒绝。
- 有真实来源仍附加虚构来源也拒绝；签收未知时断言已签收或尚未签收仍拒绝。
- 空检索结果触发 missing_required_evidence，不能靠自己写文件名生成政策结论。
- 顺序调用真实 SDK 格式的 query_order → search_policy → 最终回复；按 tool_call_id 对应消息，
  检查实际 ToolMessage 中的 source、动态示例及正文未被服务端追加引用。

所有SDK响应均由MockTransport提供，业务读取使用隔离模拟库与现有TF-IDF检索；只有空证据测试显式模拟空工具结果。
模拟Token仅用于工程计数，不是供应商用量。没有修改任何旧测试断言或gold。

执行过程中如实记录：

- 修复前3个新合同测试失败，因原合同没有policy_citation；这证明缺少明确格式字段，不证明模型一定会服从新增字段。
- 第一版SDK测试14 failed / 114 passed：模拟器错误依赖HTTP ToolMessage的可选name字段。
  改为标准tool_call_id关联，没有改引用或安全期望。
- 第二次17项新测试8 failed / 9 passed：模拟器检索query与已有回退query不同，分数/片段结果不能直接等同。
  改为发送本轮真实问题作为query，保留原数据一致性断言；未修改生产回退流程。
- 最终新增文件17 passed；下列全量结果来自修正后的最终源码。

## 5. 本轮全量结果

| 检查 | 实际结果 |
|---|---|
| 项目.venv全部后端Pytest | **427 passed，55.61秒** |
| pip check | No broken requirements found |
| 全部前端Vitest | **27 passed，5文件** |
| vue-tsc + Vite生产构建 | 成功，39模块 |
| Phase 3B固定工具场景 | **36/36符合预期**；原始选择29/36、参数23/32、实际读取17/20、阻断11/11、回退24/36 |
| 新三轮verify_tool_calling offline | **1/1**，4次脚本尝试，第3轮仍停在原人工审核，没有建单 |
| 原Agent offline | 工作流10/10、回复6/6、故障6/6、签收14/14；意图Accuracy=0.9125 |
| 原verify_qwen offline | **1/1**，原审核、恢复、幂等流程保留 |

新报告位于 evaluation/reports-{tools,tool-e2e,agent,legacy-e2e}-missing-source-20261027-review-v1/，
使用全新Git忽略目录，没有覆盖历史结果。脚本评测不是千问真实效果，本轮真实聊天及Embedding调用均为0。

## 6. 第三次真实验收条件

具备再次小预算验收的离线工程条件；尚不能声称真实missing_source已经消失。
沿用[已核对的最多8次、0重试命令](PHASE3B_UNSAFE_REPLY_20261027.md#5-后续最多8次0重试的真实验收本轮未执行)，
使用新时间戳输出目录。该CLI在新进程读取当前未提交源码，所有模型节点共享CallLedger；
只读工具、临时模拟SQLite、固定合成语料、TF-IDF、Embedding关闭、首个失败即停均不改变。

第三次重点检查第二轮：reply_validation.violations=[]、policy_source_present=true、
status=model_generated；若继续漏引，保留拦截/报告，不自动追加来源、放宽规则或重试。
线上生成质量与独立人工政策复核仍未完成。此处仅准备条件，本轮没有执行live、修改.env或执行Git提交/推送。
