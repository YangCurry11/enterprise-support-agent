# ServiceFlow 会话工作台

扩展既有 Operate 表面，不重做品牌。方向依据 DESIGN.md 与本次用户的多轮对话要求。

## Direction contract

- THESIS：把多轮业务请求可追踪地接到现有审核流程，聊天状态以真实后端为准。
- OWN-WORLD：沿用深蓝 #122235、橙红 #C34F32、浅灰 #F4F3EF、纸白 #FFFEFA 与既有字体。
- STORY：创建或恢复会话 → 提问或补充 → 查看依据与运行 → 等待客服审核；客服另有评测入口。
- FIRST VIEWPORT：桌面 248px 会话栏，中间连续消息与底部输入，右侧可收起的运行详情；窄屏纵向排列。
- FORM：用户已明确连续聊天，不进行概念抽签；code-led，未使用随机种子。每条 AI 消息绑定真实运行是核心交互。
- FINISH：unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

无新图片、无新增 UI 框架。空、忙、失败、无权限状态都展示实际状态。保留原工作台作为兼容入口。
