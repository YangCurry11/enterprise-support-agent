为客服低风险请求增加标准Qwen只读Tool Calling，并将工具执行、回复证据校验与原人工审核连接起来。
模型只能提议query_order/search_policy，服务端校验参数、调用ID、客户作用域、订单归属和共享请求预算；
售后写入继续走原LangGraph审核及SQLite幂等流程。

本次收尾明确订单/签收/来源输出合同，保留missing_source、unsupported_source和unsafe_reply拦截；
新增默认关闭的本地有损诊断、ToolMessage对应校验，以及验收逐轮失败即停。
不自动补造引用，不把模板回退标成模型生成，不提交真实配置、原始报告或诊断。

验证：

- 本地.venv全量Pytest 427 passed；Vitest 27 passed；生产构建与pip check通过。
- 固定工具场景36/36符合工程预期；新旧三轮各1/1；3A离线检索回归完成，向量来源为Mock。
- 核验用户既有真实Qwen报告：qwen3.7-flash-2026-07-15，5/8次请求，0重试，确定性校验5成功/0失败，
  供应商返回5840 Token；三轮1/1符合工程预期，第三轮停在原人工审核，24项检查通过。
- 本次交付重新执行的全部模型评测均离线，新增真实聊天/Embedding调用0。

真实业务数据仍为固定合成环境；人工语言质量复核尚未完成，不能视为生产安全或全36题真实准确率证明。
本地Python为3.11.7，仓库CI配置为3.12；本分支新CI以推送后实际结果为准。
安全汇总、两次失败修复和Windows步骤见[Phase 3B真实验收总结](https://github.com/YangCurry11/enterprise-support-agent/blob/feature/phase3b-safe-tool-calling/docs/PHASE3B_REAL_ACCEPTANCE_20261027.md)。
