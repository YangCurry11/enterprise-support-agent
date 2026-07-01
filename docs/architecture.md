# 系统架构说明

## 1. 总体流程

```text
用户输入
  ↓
IntentAgent：识别意图、抽取订单号
  ↓
根据意图路由：
  ├─ OrderAgent：调用订单查询 API
  ├─ PolicyAgent：检索政策知识库 RAG
  ├─ TicketAgent：创建售后/投诉/人工工单
  ↓
ResponseAgent：生成最终客服回复
```

## 2. Agent 分工

| Agent | 职责 |
|---|---|
| IntentAgent | 判断问题类型，如订单查询、退款咨询、投诉、人工转接 |
| OrderAgent | 调用订单 API 查询实时订单状态 |
| PolicyAgent | 基于退款、物流、售后政策做 RAG 检索 |
| TicketAgent | 创建售后、投诉、人工转接工单 |
| ResponseAgent | 汇总工具结果，生成用户可读回复 |

## 3. 为什么这样设计

企业里的 Agent 不能只靠模型“猜”。真实业务必须连接系统：

- 订单状态来自订单系统
- 退款规则来自知识库
- 投诉需要工单系统记录
- 高风险问题需要人工介入

所以本项目把 Agent 拆成“理解任务 + 调用工具 + 检索知识 + 创建工单 + 回复”的结构。

## 4. 后续可替换部分

当前实现是轻量可运行版，后续可以替换：

| 当前模块 | 可替换为 |
|---|---|
| 规则意图识别 | LLM JSON 结构化输出 |
| TF-IDF RAG | Embedding + Chroma/FAISS/Milvus |
| 手写工作流 | LangGraph StateGraph |
| JSON 文件 | SQLite / PostgreSQL |
| 规则回复 | LLM 回复生成 |
