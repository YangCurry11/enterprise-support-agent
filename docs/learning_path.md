# 基于本项目的快速学习路线

你有 AI 基础，建议按“先跑通，再替换，再优化”的方式学。

## 第 1 天：跑通项目

- 启动 FastAPI
- 运行 CLI 示例
- 运行 Streamlit 页面
- 看懂 `mock_api.py` 和 `main_cli.py`

## 第 2 天：理解工具调用

重点看：

- `api_client.py`
- `tools.py`
- `agents.py` 里的 `OrderAgent` 和 `TicketAgent`

目标：知道 Agent 为什么要调用 API，而不是直接回答。

## 第 3 天：理解 RAG

重点看：

- `data/policies/`
- `rag.py`
- `PolicyAgent`

目标：知道知识库问答的流程：文档 → 切分 → 检索 → 依据 → 回复。

## 第 4 天：接入 Dify / Coze

- 导入 `api/openapi_tool_for_dify.yaml`
- 上传政策文档作为知识库
- 配置一个客服 Agent 原型

目标：满足实习岗位里的“平台配置、工具调用基础设置”。

## 第 5-7 天：升级为 LLM 版

你可以把：

- `intent.py` 的规则分类替换为 LLM JSON 输出
- `ResponseAgent` 的规则回复替换为 LLM 回复生成
- `rag.py` 替换成 LangChain + Chroma

## 第 2 周：LangChain / LangGraph 重构

- 用 LangChain 实现 RAG
- 用 LangGraph 实现状态流转
- 增加失败重试、人工审核节点、日志记录

## 第 3 周：数据清洗标注

运行：

```bash
python scripts/prepare_sft_data.py
```

然后扩展到 300 条客服问法，字段包括：

- user_input
- intent
- required_tool
- slots
- response_type
- standard_answer

这对应岗位中的 SFT/LoRA 数据清洗和标注辅助工作。
