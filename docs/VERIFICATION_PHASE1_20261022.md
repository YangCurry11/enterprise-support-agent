# 第一阶段实际验证记录（2026-10-22）

范围：企业客服多Agent系统项目；不是相邻的企业内部RAG知识库。开发前 main 与 origin/main 同步、工作区干净，基线提交 b2a5670。升级验证完成时尚未 commit、push 或触发 GitHub CI；用户随后单独授权同步。以下为本地验证记录，云端结果以本次提交对应的 Actions 为准。

## 自动验证

| 检查 | 实际结果 |
|---|---|
| 开发前后端基线 | 24 passed |
| 开发前前端基线 | 8 passed |
| 开发前 pnpm build | 成功 |
| 最终 pytest | 41 passed，0 failed |
| 最终 Vitest | 19 passed，3个文件，0 failed |
| 最终 vue-tsc + Vite build | 成功；37个模块 |
| pip check | No broken requirements found |
| OpenAPI 导出一致性 | 完整运行时契约对比测试通过 |
| 重复迁移/旧API兼容 | 原测试保留；新增迁移、历史、原文与会话恢复测试通过 |

实际运行命令（项目根目录，复跑时换新的临时目录名）：

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.\.pytest_tmp_phase1_release --tb=short
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --mode offline
cd frontend
pnpm.cmd test
pnpm.cmd build
~~~

Pytest 与工作流评测使用隔离数据库；模型测试使用 Mock。不对原 data/business.db / workflow_runs.db / workflow_checkpoints.db 做测试写入。本轮未修改真实 .env 或真实模型密钥，没有执行真实模型调用。

开发过程中发现并修复：OpenAPI 导出中文编码不一致、评测用例来源字段不统一、旧CSS导入覆盖移动导航、未发送草稿跨会话保留。修复后重新执行测试，不删除失败断言。

## 默认离线评测

数据：80条意图、20条实际政策检索、10条A–J工作流，AI辅助模拟开发标注，待独立人工复核，非真实客户数据。

- 意图：73/80正确，Accuracy 91.25%，Macro-F1 0.9208089669。
- 检索：Recall@1/3/5 0.95/0.95/1.0，MRR 0.9625；gold是源文档，K为返回片段数量，非回答正确率。
- 工作流：10/10场景符合预期；8个末态completed，2个按预期等待审核。
- HTTP：22次，21个2xx、1个预期跨用户404。
- 工具：16次，15次ok、1次预期越权拒绝。
- 模型：1次模拟超时、1次模板回退，未测试真实模型成功率；Token为null。
- 7条意图错误、1条Top-3检索未命中保留在报告，不删除或改gold。

耗时、P50、P95以 evaluation/reports/latest.json 中每次本机实际结果为准；nearest-rank，不是公网压测或生产SLA。报告包含数据、源码、政策文件哈希。JSON/CSV/MD输出默认忽略，不进入Git。

## 浏览器真实前后端联调

单独启动后端127.0.0.1:18000与前端127.0.0.1:5174，SUPPORT_DATA_DIR指向系统TEMP中的serviceflow-phase1-browser-20261022。LLM_API_KEY置空、模型分类关闭；临时鉴权仅三种本机测试身份。没有使用原演示数据库或真实模型。

实际通过页面输入：

1. 客户查询ORD1001，返回本人无线耳机物流。
2. “那它可以退款吗？”保留订单关联并返回refund_policy.md来源。
3. “那帮我申请售后吧。”同订单新run停在awaiting_review，客户没有批准按钮。
4. 客服验证身份后，页面清除旧客户内容，重新从历史选会话；打开最后run，批准后才出现工单。
5. 刷新页面回到开发默认客户，历史6条消息可恢复，最新助手消息变为真实已建单结果；run_id不变。
6. 桌面CSS1440x960与手机约391x844布局检查，无横向溢出；浏览器缩放导致截图物理像素与CSS尺寸不同。
7. 客服进入“Agent评测”，实际读取最新offline报告，显示91.25%意图Accuracy、10/10工作流、分类F1和8条失败明细；不是写死的页面数字。

截图保存 .impeccable/review/desktop.png 与 mobile.png，仅开发本机证据且Git忽略。内部聊天/详情有滚动容器，截图不宣称显示全部消息。

账号隔离、两个会话不继承、澄清同run、重复请求、丢响应、拒绝审核、模型超时与报告权限另由自动化测试验证，不冒称每项都手工在浏览器执行。

## 界面复核

沿用Frontend Design、UI UX Pro Max与Impeccable的既有界面约定，保留深蓝/橙红品牌与原工作台，无新增UI依赖或图片资产。

Impeccable context/detect均因本机engine 0.1.14未安装及缓存不可写失败；不能声称自动检测通过。按备用流程读取既有DESIGN和源码。独立finish reviewer核验桌面/手机证据有效，发现P2草稿串会话问题；按conversation_id清空并补两路径测试后，verdict pass为resolved / ship。该结论仅关闭所列发现，不代表全系统无风险。

独立documenter只读比对了颜色变量、系统字体、248px侧栏、380px详情及1200/700px断点、表单/焦点/减少动态效果与权限入口。本次为普通扩展，保留原DESIGN.md，不新建sidecar或补造缺失的PRODUCT.md。文档与实现的既有字号差异及当前局部差异（旧工作台30px标题、11px键盘提示；聊天15px正文、25px标题、手机评测表格11px）仅记录，不借本次任务迁移整个设计规范。未增加图片或外部字体。

## 尚未验证 / 未完成的验收条件

- “80条独立人工标注”尚未完成，当前AI辅助模拟标注必须人工复核。
- 真实千问端到端、多模型对比、真实Token/费用、供应商限流与额度未验证。
- 多实例、并发压力、生产恢复演练、企业身份、真实订单/退款接口未验证。
- 浏览器完全退出进程再重新登录未手工执行；已实走页面刷新恢复，后端持久化重建和前端历史恢复由测试覆盖。
- 不具备正式生产上线结论；当前只支持单实例单worker本机/受控低并发试点。
