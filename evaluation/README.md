# ServiceFlow Agent 效果评测

项目根目录运行：python -m evaluation.run_evaluation。默认offline，无真实模型调用；输出reports/latest.json、details.csv、summary.md、manual_review.csv。

- datasets/：80条意图、20条仓库政策检索、10条工作流。均AI辅助模拟标注，待独立人工复核，非生产数据。
- evaluators/：分类、TF-IDF检索、隔离数据库工作流与纯函数指标。
- --mode live --live-limit 5：显式启用真实意图分类API，会消耗额度。RAG/工作流仍是离线验证。
- --output PATH：指定报告目录，建议不同模式分开存放。
- 只有客服身份能通过GET /agent/evaluations/latest查看报告；无文件返回report=null。
- 默认reports/输出被Git忽略；没有真实usage时Token/成本不虚构。
- --check-config：仅校验必要配置，不创建客户端、不联网，不打印Key。
- --components reply --mode live --max-model-calls 8：显式启用回复评测，意图固定规则；预算包含重试，不隐式扩大旧命令消费。
- python -m evaluation.verify_qwen：默认离线三轮验证；live 必须明确 --mode live --max-model-calls N，开发期间未执行真实调用。
- 新增6个回复/业务安全场景与6个离线故障注入。后者永不请求供应商，不纳入真实调用统计。
- 模型分类输出、规则兜底、审核保护、模板回复分别标明；人工复核表默认为pending，不伪造验收结果。

完整运行、指标定义、分母、安全与人工标注边界见[评测指南](../docs/EVALUATION_GUIDE.md)和[第二阶段验证手册](../docs/PHASE2_QWEN_VALIDATION.md)。架构说明见[第一阶段升级](../docs/PHASE1_UPGRADE.md)。
