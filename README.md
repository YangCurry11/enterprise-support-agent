# 企业客服多 Agent 系统 v0.2

Vue 3 + TypeScript、FastAPI、LangGraph、SQLite 组成的客服工作流系统。支持订单查询、政策问答、补充信息、人工审核、幂等建单、故障恢复和运行审计。

当前业务数据为本机测试数据，架构支持单实例低并发试点。完整升级说明、学习顺序和面试表述见 [docs/UPGRADE_V02.md](docs/UPGRADE_V02.md)。

## 启动后端（Windows PowerShell）

LangGraph 已接入默认执行链路，不是待实现计划：`POST /agent/run → WorkflowService → build_graph → StateGraph`。保留的 `CustomerSupportAgent.run()` 也是调用该链路的 CLI 兼容入口。

在 VS Code 中打开整个“企业客服多Agent系统”文件夹，然后打开终端：

```powershell
# 仅首次创建；已有 .venv 时跳过这一行，不用重新安装环境
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn support_agent.app:app --reload --host 127.0.0.1 --port 8000
```

后端终端保持运行。API 文档：<http://127.0.0.1:8000/docs>。

项目包含 .env.example；如需自定义模型或凭证，复制成 .env 再修改。不开模型也能运行所有工作流测试。模型配置为 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL；LLM_INTENT_ENABLED=true 可启用结构化模型分类，供应商须支持相应工具调用协议。

已有 .env 时保留其他配置，仅修改对应项。密钥只放后端环境，不能放进 Vue 的 VITE_* 变量；不要提交 .env、实际凭证、运行数据库或模型检查点。配置供应商不等于已联调，页面可能返回模板兜底；真实调用应另外核对供应商记录和返回结果。

建议按 [当前学习路线](docs/learning_path.md) 阅读，再参考 [架构说明](docs/architecture.md) 和 [面试说明](docs/interview_notes.md)。[Dify/Coze 接入](docs/dify_coze_setup.md) 是可选适配，不能绕过人工审核。

## 启动前端

先安装 Node.js 24 LTS。在第二个终端执行：

```powershell
cd frontend
npm.cmd install -g pnpm@11.19.0
pnpm.cmd install --frozen-lockfile
pnpm.cmd dev
```

浏览器打开 <http://127.0.0.1:5173>。使用 `.cmd` 可以避免 PowerShell 对 npm.ps1 / pnpm.ps1 的执行策略限制。

## 验证升级功能

开发模式提供两种公开测试凭证，只用于本机测试：

| 凭证 | 身份 | 操作 |
|---|---|---|
| dev-customer-u1001 | U1001 / customer | 查询自己的订单、发起请求、补充订单号 |
| dev-support-reviewer | S1001 / support | 从运行历史打开请求、审核通过或拒绝 |

1. 客户身份查询“ORD1001 到哪了”，应返回本人的物流信息。
2. 查询“ORD1002 到哪了”，应拒绝透露其他用户的订单。
3. 输入“我的订单到哪了”，应进入待补充状态；提交 ORD1001 后继续。
4. 输入“我要投诉”，应进入待审核状态，此时没有创建工单。
5. 在访问凭证中换为客服凭证并验证身份，在历史记录打开该请求。
6. 选择通过后创建高优先级工单；选择拒绝则不创建工单。
7. 可以在审核前重启后端，再打开同一次请求，检查等待状态仍然保留。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
cd frontend
pnpm.cmd test
pnpm.cmd build
```

测试覆盖权限、订单归属、审核拒绝、检查点恢复、重复请求、重复建单、模型降级和前端审核交互。数据库测试使用临时目录，不修改业务数据库。

本次本地发布检查结果及未验证范围见 [验证记录](docs/VERIFICATION_20261020.md)。GitHub Actions 需以仓库中的实际运行结果为准。

## 数据与兼容性

已有 business.db 保留，并进行新增列的迁移。原 agent_logs.db 保留，但旧历史不自动导入新工作流。新记录保存在 workflow_runs.db，检查点保存在 workflow_checkpoints.db。

旧 `support_agent.mock_api:app` 名称仍指向新应用，原启动命令可继续使用。API 请求现在必须携带身份凭证和 request_id；旧 Dify/Coze 调用配置需要更新。

## 部署

已提供 Dockerfile 和 GitHub Actions。Docker 容器默认 SUPPORT_ENV=production，必须配置私有 SUPPORT_AUTH_TOKENS；不会启用公开开发凭证。数据目录需挂载持久卷。

```powershell
docker build -t enterprise-support-agent:0.2 .
docker run --env-file .env.production -p 127.0.0.1:8000:8000 -v support-data:/var/lib/support enterprise-support-agent:0.2
```

.env.production 至少设置 SUPPORT_ENV=production 和 SUPPORT_AUTH_TOKENS（格式见 .env.example）。不要提交实际凭证。

当前只能启动一个 API worker。多实例需配套实现 PostgreSQL 检查点和分布式调度；对外上线前需接入企业身份系统和真实业务适配器，并进行并发、恢复、业务评测与运维验收。
