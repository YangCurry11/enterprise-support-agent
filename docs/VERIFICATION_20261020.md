# v0.2 本地发布验证记录

日期：2026-10-20。对象：本次同步到仓库的持久化 LangGraph 工作流、Vue 工作台与当前说明文档。

## 本地实际执行结果

| 检查 | 结果 |
|---|---|
| Python 后端 pytest | 24 项通过 |
| Python pip check | No broken requirements found |
| Vue/Vitest | 2 个文件、8 项通过 |
| vue-tsc + Vite 生产构建 | 通过 |
| OpenAPI 契约 | 运行时 schema、操作与安全定义和导出文件一致；导出额外声明 localhost 开发服务器 |
| 本机密钥特征与 Git 历史扫描 | 发布前未发现匹配的供应商密钥、GitHub 凭证、云访问密钥或私钥特征；另做本地密钥精确匹配检查，不输出密钥内容 |

新增 5 项发布检查覆盖契约一致性、旧 HTTP 别名指向同一应用、模型客户端配置与缓存（替身客户端，无网络）、模型分类异常回退及意图白名单。

既有测试覆盖客户权限、订单归属、订单号补充、审核通过/拒绝、服务实例重建后的恢复、请求冲突、工单幂等、业务写成功后丢响应的恢复，以及模型回复失败保留模板。

## 安全与隔离

- 后端测试使用新的临时目录，模型开关/凭证由测试环境隔离，不调用真实供应商 API。
- 私有 .env、原业务数据库、检查点、node_modules、dist、缓存和个人面试准备资料不纳入公开提交。
- 密钥扫描不是完整安全审计，仍需人工管理凭证、权限和数据保留。
- 模型连通性脚本 llm_test.py 是手动付费调用入口，本次没有运行。

## 未包含的验收

本次没有验证真实 Qwen/DeepSeek 调用、模型效果、浏览器全流程、Dify/Coze、Docker 构建、真实业务系统、多 worker 并发或生产部署。GitHub Actions 的实际结果应查看该提交的 Actions 页面；本地通过不等于 CI/部署已经通过。

当前只支持单 API worker。不得将上述功能测试数量表述为真实业务准确率或线上效果。

## 复现

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
cd frontend
pnpm.cmd test
pnpm.cmd build
```

默认测试在临时目录写数据库。若要重复运行指定 --basetemp，应每次使用新的目录，避免 pytest 清理已有目录中的文件。
