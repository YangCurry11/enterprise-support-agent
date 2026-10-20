# ServiceFlow 前端美化说明

这次应用四套技能：UI UX Pro Max、Anthropic frontend-design、Impeccable、Vercel web-design-guidelines。技能安装在用户的 Codex skills 目录，不属于应用运行依赖。

## 页面变化

- 保留深蓝侧栏和珊瑚色主操作的品牌识别，统一颜色、字号和间距。
- 缩小顶部展示区，优先呈现服务对象、请求输入、审核操作和真实记录。
- 客户与客服分别呈现适用的操作入口。拒绝审核先确认，通过后才建单。
- 请求历史显示中文问题类型、后端状态、格式化时间和执行耗时。
- 手机端收起侧栏，输入及操作区域自然换行；保留可见标签、键盘焦点和减少动态效果支持。
- 未增加新的 UI 框架、字体 CDN 或前端安装依赖。

## 实际验证

- TypeScript 类型检查和 Vite 生产构建。
- 前端 API 契约及页面交互测试。
- 独立测试数据库中查询 ORD1001、提交投诉、切换客服身份、审核通过并返回工单号。
- 浏览器实际 CSS 视口 375px 的窄屏布局，无横向溢出。
- 对比度检查：正常正文、次级正文、侧栏正文及状态文字达到 4.5:1；表单边界达到 3:1。主按钮颜色经过调整。

技能的自动建议经过人工判断：UI UX Pro Max 返回的营销页结构不适合客服操作界面，采用其密度、对比度和表单规则；Impeccable 的上下文引擎下载失败，按该技能备用流程读取现有代码并手工审查。

## 运行

如果前端已经执行 pnpm dev，源码更新后 Vite 会自动刷新；必要时手动刷新浏览器。

如果前端没有运行，在项目 frontend 目录执行 pnpm.cmd dev。后端仍按 README 的启动命令运行。

## 代码入口

- frontend/src/App.vue：布局、身份、请求与审核交互。
- frontend/src/styles.css：设计变量和响应式规则。
- frontend/src/components/AppIcon.vue：统一 SVG 图标。
- frontend/src/presentation.ts：中文状态和时间数字格式化。
- frontend/src/components/HistoryPanel.vue：历史与审核队列。
- frontend/src/components/ResultPanel.vue：回复、依据和执行数据。
- frontend/src/components/AgentTimeline.vue：真实节点记录。

后端接口、鉴权和数据库没有因本次美化修改。
