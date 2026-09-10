# 企业客服工单多 Agent 系统

这是一个面向 **AI Agent 实习 / 大模型应用开发 / RAG 工程** 的练习项目。

项目模拟电商售后客服场景，实现：

- 订单查询 API
- 用户信息 API
- 工单创建 API
- 退款/物流/售后政策知识库
- 本地轻量 RAG 检索
- 多 Agent 流程：意图识别 → 工具调用/RAG → 工单处理 → 回复生成
- Vue 3 + TypeScript + Vite 可视化工作台
- Dify / Coze 可用的 OpenAPI 工具配置示例
- 客服数据清洗与标注 JSONL 示例

> 默认不需要大模型 API Key 也能运行。这样你可以先快速理解 Agent 工程结构，再逐步替换为真实 LLM、LangChain、LangGraph、Dify/Coze。

---

## 1. 项目结构

```text
enterprise_support_agent_project/
├── support_agent/
│   ├── mock_api.py          # FastAPI 模拟企业内部订单/用户/工单 API
│   ├── api_client.py        # Python 调用业务 API
│   ├── intent.py            # 规则版意图识别，可替换为 LLM
│   ├── rag.py               # 本地轻量 RAG 检索
│   ├── tools.py             # Agent 可调用工具集合
│   └── agents.py            # 多 Agent 编排逻辑
├── data/
│   ├── orders.json          # 模拟订单数据
│   ├── users.json           # 模拟用户数据
│   ├── tickets.json         # 工单数据
│   ├── policies/            # 知识库文档
│   └── training/            # 数据清洗/标注样例
├── api/
│   └── openapi_tool_for_dify.yaml  # Dify/Coze HTTP 工具配置示例
├── frontend/
│   ├── src/App.vue          # Vue 页面状态与请求编排
│   ├── src/api.ts           # 类型化 FastAPI 客户端
│   └── src/components/      # 回复、链路与历史组件
├── docs/
│   ├── architecture.md
│   ├── dify_coze_setup.md
│   ├── learning_path.md
│   └── interview_notes.md
├── main_cli.py              # 命令行 Demo
└── requirements.txt
```

---

## 2. 快速启动

### 2.1 创建环境

```bash
cd enterprise_support_agent_project
python -m venv venv
```

Windows：

```bash
venv\Scripts\activate
```

Mac / Linux：

```bash
source venv/bin/activate
```

安装依赖：

```bash
pip install -r requirements.txt
```

---

### 2.2 启动模拟企业 API

打开第一个终端：

```bash
uvicorn support_agent.mock_api:app --reload --port 8000
```

浏览器访问：

```text
http://127.0.0.1:8000/docs
```

你会看到 FastAPI 自动生成的接口文档。

---

### 2.3 运行命令行 Agent

打开第二个终端：

```bash
python main_cli.py "我的订单 ORD1001 到哪了？"
```

试试这些问题：

```bash
python main_cli.py "ORD1002 怎么还没发货？"
python main_cli.py "我买了10天的耳机还能退吗？"
python main_cli.py "商品坏了，无法使用，帮我处理一下"
python main_cli.py "我要投诉，你们服务太差了"
python main_cli.py "我要人工客服"
```

如果想看完整状态：

```bash
python main_cli.py "我的订单 ORD1001 到哪了？" --json
```

---

### 2.4 运行 Vue 3 前端

```bash
cd frontend
pnpm install
pnpm dev
```

访问 `http://127.0.0.1:5173`。前端通过 `/agent/run` 调用完整 Agent 工作流，并从 `/agent/runs` 读取 SQLite 运行历史。
如果 `pnpm` 不存在，请先安装 Node.js 20+，再执行 `npm install -g pnpm`。

---

## 3. 这个项目对应哪些岗位能力

| 岗位要求 | 项目对应模块 |
|---|---|
| Python 基础编程 | `api_client.py`, `tools.py`, `agents.py` |
| API 调用 | `mock_api.py`, `api_client.py` |
| Dify/Coze 工具配置 | `api/openapi_tool_for_dify.yaml` |
| Agent 角色配置 | `IntentAgent`, `OrderAgent`, `PolicyAgent`, `TicketAgent`, `ResponseAgent` |
| RAG 知识库 | `rag.py`, `data/policies/` |
| 数据清洗标注 | `scripts/prepare_sft_data.py`, `data/training/` |
| 工单流程 | `TicketAgent`, `/tickets` API |
| 前后端分离应用 | `frontend/`, `/agent/run`, `/agent/runs` |

---

## 4. 建议学习顺序

1. 先运行 `mock_api.py`，理解 API 是什么。
2. 看 `api_client.py`，理解 Python 如何调用 API。
3. 看 `tools.py`，理解 Agent 的工具函数怎么封装。
4. 看 `intent.py`，理解意图识别和槽位抽取。
5. 看 `rag.py`，理解知识库检索流程。
6. 看 `agents.py`，理解多 Agent 如何协作。
7. 看 `frontend/src/api.ts`，理解 Vue 如何通过 HTTP 调用 Python Agent。
8. 看 `api/openapi_tool_for_dify.yaml`，把 API 导入 Dify/Coze。
9. 后续把规则版意图识别和回复生成替换为真实 LLM。

---

## 5. 下一步升级方向

- 用 LangChain 替换 `rag.py` 的轻量检索
- 用 Chroma / FAISS 替换 TF-IDF
- 用真实 LLM 做意图识别和回复生成
- 用 OpenAI / DeepSeek / 通义千问的 Tool Calling 替换规则分支
- 用 LangGraph 重写 `CustomerSupportAgent` 工作流
- 增加日志、评估集、失败重试和人工审核
- 将数据存储从 JSON 文件升级到 SQLite / PostgreSQL

---

## 6. 简历写法

项目名称：**基于 RAG 与 Tool Calling 的企业客服多 Agent 系统**

项目描述：

> 设计并实现一个面向电商售后场景的智能客服 Agent 系统，支持订单查询、退款政策问答、售后工单创建和人工转接。项目结合 FastAPI 业务接口、RAG 知识库、工具调用和多 Agent 工作流，实现从用户问题理解、知识检索、业务工具调用到最终回复生成的自动化流程。

项目亮点：

1. 使用 FastAPI 模拟订单查询、用户信息、工单创建等企业内部接口。
2. 基于本地政策文档构建 RAG 知识库，实现退款、物流、售后政策检索。
3. 设计 `query_order`、`search_policy`、`create_ticket` 等 Agent 工具函数。
4. 实现意图识别 Agent、订单查询 Agent、政策问答 Agent、工单 Agent 和回复生成 Agent。
5. 提供 Dify/Coze 可导入的 OpenAPI 工具配置文件。
6. 使用 Vue 3、TypeScript 与 Vite 构建前端工作台，展示意图、工具结果、RAG 证据、执行链路和 SQLite 历史记录。
7. 整理客服意图识别和工具调用标注数据，便于后续 SFT/LoRA 数据准备。

---

## 7. 测试与构建

后端测试：

```bash
python -m pytest -q
```

前端测试和生产构建：

```bash
cd frontend
pnpm test
pnpm build
```

`frontend/node_modules`、`frontend/dist`、本机 `.env` 和 SQLite 运行数据均不会提交到 Git。
