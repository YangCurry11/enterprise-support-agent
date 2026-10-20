# 系统架构说明（v0.2）

LangGraph 已在默认链路中使用，不是下一步的重构计划。前端为 Vue 3 + TypeScript，后端为 FastAPI；当前业务数据是本地测试数据，运行范围为单 API worker。

## 1. 从页面到执行器

```text
Vue App.vue → api.ts → POST /agent/run
  → app.py：参数校验、Bearer 身份与客户范围检查
  → runtime.py / WorkflowService：请求去重、run 登记、访问授权
  → workflow.py / build_graph：LangGraph StateGraph
  → ScopedTools：受限订单查询、政策检索、幂等建单
  → 状态整理为 JSON → Vue 展示答案、待补充或待审核状态
```

`CustomerSupportAgent.run()` 仍保留，但只是调用同一 WorkflowService 的 CLI 兼容入口，不是另一套手写工作流。`support_agent.mock_api:app` 也是新 FastAPI 应用的兼容名称。

## 2. 图节点与实际路径

| 节点 | 作用 |
|---|---|
| intent | 规则识别意图；按配置可使用带输出校验的模型分类 |
| clarify | 缺少订单号时 interrupt，补充后恢复同一个 run |
| order | 通过 ScopedTools 查询当前业务客户的订单 |
| policy | 字符级 TF-IDF、查询扩展、Top-K 政策检索 |
| review | 检查订单归属并 interrupt，等待有权限的客服审核 |
| ticket | 审核通过后创建带业务幂等键的工单 |
| response | 生成模板或可选模型回复；确定性拒绝不交由模型改写 |

当前路径以 `workflow.py` 的条件边为准：

```text
订单查询：intent → clarify → order → response
退款/发货政策及 unknown：intent → policy → response
售后：intent → policy → review → ticket（仅通过时）→ response
投诉/人工请求：intent → review → ticket（仅通过时）→ response
寒暄：intent → response
审核拒绝或订单访问被阻止：review → response，不创建工单
```

不是每个节点都调用模型，也不是模型自主决定数据库写入。身份、订单归属、审核权限、参数校验由服务端执行。

## 3. 三类持久化

| 存储 | 内容 | 负责模块 |
|---|---|---|
| business.db | 用户、订单、工单、建单幂等键 | business_db.py |
| workflow_runs.db | run 登记、输入指纹、结果缓存、审计事件 | runtime.py |
| workflow_checkpoints.db | 图状态、待执行节点与中断 | SqliteSaver |

恢复使用服务器生成的 run_id 作为 thread_id。检查点不会自动保证业务写入恰好一次；工单另用 `run_id:ticket`、数据库事务与唯一约束避免重放时重复建单。三个数据库之间没有统一跨库事务。

## 4. 当前与旧代码的边界

默认图注入 `ScopedTools`，直接调用本地业务数据库。`tools.py`、`api_client.py` 是保留的旧 HTTP 适配层；`storage.py` 是旧日志层，均不能代表 v0.2 主链路。旧 agent_logs.db 不自动变成可恢复的检查点。

政策检索目前不是 Dense、混合检索或 reranker。模型接口可选接入，但实际供应商成功联调和效果必须另行验证，不能仅凭配置或页面答案判断。

## 5. 尚未实现的生产能力

- 多实例执行、分布式锁、PostgreSQL 检查点和后台任务调度。
- 企业 SSO/OIDC、真实订单/工单服务适配与完整安全运营。
- 业务标注评测、并发压测、完整 SLO 与成本监控。

更详细的 API、升级边界与学习顺序见 [UPGRADE_V02.md](UPGRADE_V02.md)。
