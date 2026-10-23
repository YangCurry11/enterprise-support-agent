# 第二阶段缺陷修复：空签收记录不能推出未签收

本文保留缺陷开发时的历史测试与“未调用/未推送”范围。后续用户已完成两次真实测试，本次发布又重新执行158项后端测试；最新证据和Git发布范围以[第二阶段最终收尾记录](PHASE2_RELEASE_20261023.md)为准，不将历史耗时冒充本次复跑结果。

## 问题与根因

用户反馈真实千问将ORD1001的status=已发货、received_days=null解释成“您的订单目前尚未签收”。这是把发货状态和缺失字段当作签收的否定证据，不是工具已知事实。

修复前，新增的单条回归用例确实失败：reply_violations对这句话返回空列表。旧Prompt只笼统要求不要编造，校验主要检查订单号、状态、物流和来源，未表示签收三态。

本次只修复第二阶段的事实约束，不更换模型协议、不重构Agent，不做第三阶段功能；没有执行真实千问调用、修改私有.env、提交或推送Git。

## 统一的结构化事实

order_facts.build_order_facts从本轮已授权订单工具的原始记录计算OrderFacts。原始data、订单表和业务接口均不改写，仅在工具结果外层补充facts；ScopedTools仍先校验订单归属，越权结果不返回data或facts。兼容SupportTools使用相同规范。

| 本轮工具记录 | receipt.state | 可说什么 |
|---|---|---|
| 已发货，received_days=null | unknown | 已发货；无法确认是否签收及签收时间 |
| 已签收，received_days=null | received | 已签收；签收天数未知，不能编造3天等数值 |
| 合法received_days=0 | received | 当天签收，不等同于null |
| 合法received_days=10 | received | 已签收10天；不能因此认定其他退款条件满足 |
| 原始状态明确未签收/未收货，无相反证据 | not_received | 可按工具证据说明未签收 |
| 明确未签收但又有合法签收天数 | unknown，conflicting_evidence=true | 记录冲突，需核实，不选一个当真 |
| 缺失物流公司/单号/预计送达 | 不改变签收三态 | 缺字段是未知，不是未发货或未签收 |

签收天数只接受非负整数；负数、bool、字符串或小数不冒充合法天数。预计送达文本、历史会话、用户说法、已有facts对象均不能覆盖本轮工具证据。

ORD1001派生事实的关键部分为：

```json
{
  "order_status": "已发货",
  "receipt": {
    "state": "unknown",
    "received_days": null,
    "evidence": [],
    "conflicting_evidence": false
  },
  "refund_eligibility": "not_determined"
}
```

refund_eligibility始终未确定：这个项目没有完整的商品完好、材料、退款审核判定工具，不能用签收状态或7天时间条件替代全部业务判断。

## Prompt、校验与回退如何配合

1. Prompt提供结构化OrderFacts与unknown_fields，明确区分已知事实、未知字段、政策适用条件。received_days=null不是未签收；已签收但天数缺失也不能否认已经签收。
2. 政策中的期限、材料和例外只可来自本轮检索片段；条款必须按条件表述，不能当成当前订单已满足的事实，更不能自行认定退款批准。
3. reply_safety用有限的签收极性/天数断言识别，再与统一三态事实比较，而不是将某一句中文一律禁掉。明确未签收时允许同样的表述；“如果/若”“是否/无法确认”等条件、询问和未知表达单独处理。
4. 未获证据支持的签收断言记unsupported_receipt_state，编造天数记unsupported_received_days；生成入口仍抛unsafe_reply，不做额外模型重试。
5. 原LLMResponseAgent保留模板回退，新增fact_violations解释拒绝原因，不落盘供应商原始异常或被拒绝的模型正文。政策模板也根据同一OrderFacts明确签收未知/天数未知，保留真实来源。

期望表达示例（说明用，不是本轮真实千问输出）：

> 订单ORD1001当前记录为已发货。目前无法确认是否签收及签收时间，请补充实际情况。退款政策的签收期限、商品完好等条件是否满足仍需核实，依据见refund_policy.md。

这不是完整自然语言语义证明或通用幻觉防御。有限断言识别可能对少见表达保守回退；提示词和规则不能替代独立人工质量复核。没有引入额外LLM裁判、价格模型或新Agent。

## 修改文件

- 新增support_agent/order_facts.py：三态、证据、未知字段与确定性签收说明。
- 修改support_agent/scoped_tools.py、tools.py：订单工具补facts，不改原data或权限逻辑。
- 修改support_agent/llm_client.py：注入事实约束、细化Prompt、记录事实违规代码，保持现有调用接口和预算。
- 修改support_agent/reply_safety.py：基于事实三态检查签收断言与天数，不按单句黑名单拦截。
- 修改support_agent/agents.py：政策模板明确未知签收、未知天数或记录冲突，不改变路由/审核/写入。
- 修改evaluation/evaluators/reply_eval.py：原事实检查增加receipt_facts_consistent，保留模型拒绝原因。
- 新增evaluation/evaluators/receipt_eval.py、datasets/receipt_cases.jsonl：14个固定文本回归，复用原评测事实检查，不调用模型。
- 修改evaluation/run_evaluation.py：报告增加receipt组件与失败码判断，原live组件/数量/预算不扩大。
- 新增tests/test_receipt_facts.py：55个测试执行用例（含参数化），原103项测试文件和断言未改。
- 文档：本文，及第二阶段手册/评测指南的入口说明。

未修改数据库结构或种子、真实.env、依赖/锁文件、OpenAPI导出、前端业务代码、workflow.py、runtime.py、conversations.py、人工审批与工单幂等实现。

## 实际验证（2026-10-23）

| 检查 | 实际结果 |
|---|---|
| 修复前后端基线 | 103 passed |
| 原错误回归修复前 | 1 failed，确认旧校验放过错误 |
| 修复后完整Pytest | 158 passed，0 failed，最终37.12秒 |
| 前端Vitest | 19 passed，3个文件 |
| vue-tsc + Vite生产构建 | 成功，37模块 |
| pip check | No broken requirements found |
| 原工作流/回复/故障注入 | 10/10、6/6、6/6符合离线预期 |
| 新签收事实回归 | 14/14符合预期；包括错误文本被正确拒绝 |
| 原独立三轮离线工具 | 1/1通过 |
| 真实模型调用 | 0；不伪称真实千问质量验收 |

Mock模型错误回复还实走了原FastAPI/LangGraph多轮：第二轮回退为明确未知的政策模板，第三轮仍在同订单新run上等待人工；客户审批403、服务重建后客服恢复同run、重复批准与同request_id重发仍仅一张工单。

原80条规则意图和20条RAG开发集指标未变化：Accuracy=0.9125，Macro-F1=0.9208；Recall@1/3/5=0.95/0.95/1.0，MRR=0.9625。保留7条分类错例与1条Top-3检索未命中，不改标签凑分。

## 复跑与生效

沿用原.venv和前端依赖，不需要重新安装环境。下面均离线，报告写入本轮专用忽略目录，不覆盖旧结果：

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.\.pytest_tmp_receipt_final_20261023 --tb=short
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --mode offline --output .\evaluation\reports-receipt-fix-20261023
.\.venv\Scripts\python.exe -m evaluation.verify_qwen --mode offline --output .\evaluation\reports-receipt-e2e-20261023
cd frontend
pnpm.cmd test
pnpm.cmd build
```

报告仍是JSON/CSV/中文摘要/待人工复核表。receipt组件是固定合成文本回归，即使顶层命令是live也不会额外调用模型，不代表真实千问回复准确率。

已有后端进程需重启或确认reload已经生效，随后再由使用者明确授权执行原小预算live验证。本轮没有启动真实模型测试、改写旧聊天消息或向GitHub同步；现有错误历史不能成为新一轮签收事实的证据。
