# Dify / Coze 接入说明

## 1. 先启动业务 API

```bash
uvicorn support_agent.mock_api:app --reload --port 8000
```

确认接口可访问：

```text
http://127.0.0.1:8000/docs
```

## 2. 导入 HTTP 工具

项目提供了 OpenAPI 文件：

```text
api/openapi_tool_for_dify.yaml
```

你可以在 Dify / Coze 中创建 HTTP 工具，导入这个 OpenAPI 文件。

工具包括：

- `queryOrder`：查询订单
- `queryUser`：查询用户
- `createTicket`：创建工单

## 3. 建议 Agent 提示词

```text
你是企业售后智能客服 Agent。
你的职责是帮助用户查询订单、解释退款政策、处理物流和售后问题。

规则：
1. 用户提供订单号时，优先调用 queryOrder 查询订单。
2. 用户咨询退款、退货、物流、售后政策时，优先检索知识库。
3. 用户投诉、要求人工、涉及赔偿或情绪强烈时，调用 createTicket 创建高优先级工单。
4. 不要编造订单状态、物流单号、退款政策。
5. 如果信息不足，先向用户追问必要信息。
```

## 4. 建议知识库文档

将以下文件上传到 Dify / Coze 知识库：

```text
data/policies/refund_policy.md
data/policies/shipping_policy.md
data/policies/after_sales_policy.md
data/policies/membership_policy.md
```

## 5. 工作流建议

```text
开始
  ↓
LLM 节点：识别用户意图和订单号
  ↓
条件分支：
  ├─ 订单查询 → HTTP 工具 queryOrder
  ├─ 政策咨询 → 知识库检索
  ├─ 投诉/人工 → HTTP 工具 createTicket
  ↓
LLM 节点：生成最终回复
```
