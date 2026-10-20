# Dify / Coze 接入边界（v0.2）

本项目默认使用 Vue 工作台和后端 LangGraph；Dify/Coze 是可选适配目标，本说明不表示已完成这些平台的实测验收。

## 1. 后端与网络

按 [README](../README.md) 启动 `support_agent.app:app`，API 文档在 `http://127.0.0.1:8000/docs`。平台所在容器或云端的 localhost 不是本机后端；应使用受控网络连接，不要为演示直接把公开开发凭证和服务暴露到公网。

## 2. 导入契约与凭证

`api/openapi_tool_for_dify.yaml` 是完整 API 契约（JSON 也是合法 YAML），包括运行、恢复、审核和业务读接口。平台的 OpenAPI 3.1 支持程度需实际验证；导入后应精简为该集成真正需要的操作，而不是全部交给模型。

业务请求必须携带服务端管理的 `Authorization: Bearer ...`。按客户授权选择凭证；平台用户不能自行提交角色或覆盖服务器身份。

## 3. 正确的写操作链路

```text
提交业务请求 → POST /agent/run
  ├─ completed：展示后端结果
  ├─ awaiting_input：收集订单号，POST /agent/runs/{run_id}/resume
  └─ awaiting_review：交由可信客服工作台审核，不能由模型自行批准
```

新请求必须带 UUID request_id；相同操作重试沿用原编号，不同输入换新编号。保存返回的 run_id，用于查看和继续同一次运行。

当前没有可绕过审核的 `POST /tickets` 建单接口。`/agent/runs/{run_id}/review` 只供可信客服身份使用，不要把审核员密钥或该工具提供给自主 Agent。审核通过后，由服务端的 ticket 节点执行幂等建单。

## 4. 回复与知识库

优先展示后端 final_response、status 和检索依据。若平台另设一个模型改写答案，要避免把“待审核”“被拒绝”“未建单”改写成成功承诺，也不能把检索不到的政策补成事实。

`data/policies/` 为模拟政策。另行上传平台知识库会形成独立检索链路，需要单独测量并明确文档版本；不能将其评测结果当作当前本地 TF-IDF 的结果。

## 5. 上线前验证

至少验证：客户隔离、未授权失败、重复请求、补充订单号、审核通过/拒绝、工单去重、网络中断恢复，以及平台不会向最终用户暴露密钥或内部敏感响应。接口细节见 [api/README](../api/README.md)。
