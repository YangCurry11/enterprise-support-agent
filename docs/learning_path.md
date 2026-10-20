# 基于当前 v0.2 的学习路线

先跑通一条请求，再读代码、解释故障场景。当前页面是 Vue 3，不需要运行 Streamlit；LangGraph 已落地，不需要先重写 CustomerSupportAgent。

## 第 1 步：启动并区分三个入口

按 [README](../README.md) 启动 `support_agent.app:app` 和 Vue 工作台。使用本机开发身份查询 `ORD1001`，再尝试 `ORD1002`，观察客户权限边界。

- 网页入口：`frontend/src/App.vue` → `frontend/src/api.ts`。
- HTTP 入口：`support_agent/app.py` 的 `/agent/run`。
- CLI 入口：`main_cli.py` → `CustomerSupportAgent.run()`，同样调用 WorkflowService。

目标：能解释“按钮按下后，参数和身份怎样传到后端”。

## 第 2 步：理解身份与请求登记

读 `auth.py`、`app.py`、`runtime.py` 的 `start`。区分用户输入中的 user_id 与服务器身份；理解 request_id、输入指纹、run_id，以及 401/403/404/409 的意义。

目标：知道请求去重不等于工单幂等，也不能靠前端按钮实现权限控制。

## 第 3 步：理解已接入的 LangGraph

读 `workflow.py` 的 `build_graph` 和条件边，画出订单、政策、售后三条实际路径；再读 `runtime.py` 的 `graph`、`invoke`、`render`。

目标：解释 StateGraph、节点、条件边、状态、thread_id 和 SqliteSaver。不是每个节点都调用一个 LLM。

## 第 4 步：亲手做中断与恢复

输入“我的订单到哪了”，看到 awaiting_input 后补充 ORD1001；输入“我要投诉”，看到 awaiting_review 后切换客服身份审核。审核前可以重启后端，再打开相同 run，观察检查点仍可读取。

读 `clarify`、`review` 与 `runtime.resume`。目标：解释 interrupt 与 Command 恢复的是同一个业务 run，而不是任意聊天的长期记忆。

## 第 5 步：理解工具与防重复建单

读 `scoped_tools.py`、`business_db.py` 和 `tests/test_workflow.py`。重点解释客户归属校验、参数化 SQL、事务、幂等键，以及“写入成功但检查点未保存”的故障注入测试。

`tools.py` / `api_client.py` / `storage.py` 是旧适配器或旧日志层，不作为当前默认路径的学习入口。

## 第 6 步：再学检索与模型

读 `rag.py`、`data/policies/`、`PolicyAgent`，理解字符级 TF-IDF、查询扩展、Top-K 和证据来源。接着读 `LLMResponseAgent`、`llm_client.py` 和 `IntentDecision`，区分回复增强、规则分类、可选模型分类和异常回退。

密钥只放本地后端环境；先验证小规模真实调用，再测试分类，不能把模板答案误认为模型调用成功。真实调用会消耗供应商额度，不属于默认测试套件。

## 第 7 步：测试后练习面试

先跑后端 pytest、pip check，再跑前端 test/build。每个重要说法都对应函数和测试：权限、审核拒绝、服务重建恢复、工单幂等、模型失败保留模板。

面试按“业务问题 → 执行链路 → 风险 → 实现 → 验证 → 限制”来讲，不把未完成的生产接入或模型评测写成成果。

## 可选：外部平台与后续升级

Dify/Coze 是可选集成，先读 [安全接入说明](dify_coze_setup.md)，不要把审核权限交给自主模型。Embedding/rerank、多实例、SSO 和真实业务接入仍属于后续工作；SFT 数据示例不等于已经训练模型。
