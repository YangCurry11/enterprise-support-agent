<script setup lang="ts">
import type { AgentResult, ToolAttempt } from "../types";
import { formatNumber, intentLabels, statusLabels } from "../presentation";
import AppIcon from "./AppIcon.vue";
defineProps<{ result: AgentResult }>();

function formatScore(score?: number): string { return typeof score === "number" ? score.toFixed(3) : "未记录"; }
const toolStatuses: Record<string, string> = {
  ready: "等待只读工具规划", running: "执行中", model_generated: "模型已基于工具结果回复",
  no_tool_needed: "普通问候，无需工具", blocked: "已拦截", fallback: "已回退确定性流程",
  guarded_workflow: "交由原人工审核流程", disabled: "未启用",
};
function toolOutcome(tool: ToolAttempt): string {
  if (tool.permission_blocked) return "权限拦截";
  if (tool.cached) return tool.success ? "复用本轮已授权结果" : "复用拒绝结果";
  if (tool.executed) return tool.success ? "执行成功" : "执行失败";
  return "未执行";
}
function retrieval(result: AgentResult): Record<string, unknown> | undefined {
  const value = result.tool_results.search_policy as { retrieval?: Record<string, unknown> } | undefined;
  return value?.retrieval;
}
</script>

<template>
  <div class="result-stack" aria-live="polite">
    <section class="card response-card">
      <div class="section-head"><h2>客服回复</h2><span :class="['status-badge', result.status]"><AppIcon :name="result.status === 'completed' ? 'check' : result.status === 'failed' ? 'alert' : 'clock'" />{{ result.status === "completed" && result.need_human ? "需人工跟进" : statusLabels[result.status] }}</span></div>
      <div class="response-copy">{{ result.final_response || (result.status === "failed" ? "本次处理暂未完成，请使用上方恢复操作继续。" : "正在处理这条请求…") }}</div>
      <dl class="metrics"><div><dt>问题类型</dt><dd>{{ intentLabels[result.intent] || result.intent || "待识别" }}</dd></div><div><dt>订单号</dt><dd translate="no">{{ result.order_id || "未关联订单" }}</dd></div><div><dt>本次执行耗时</dt><dd>{{ formatNumber(result.latency_ms) }} ms</dd></div></dl>
      <details v-if="result.intent_reason" class="classification-note"><summary><AppIcon name="down" />查看意图识别依据</summary><p>{{ result.intent_reason }}</p></details>
    </section>
    <section v-if="result.retrieved_docs.length" class="card evidence-card">
      <div class="section-head"><h2>政策检索依据</h2><span class="panel-count">{{ result.retrieved_docs.length }} 条片段</span></div>
      <ol class="evidence-list"><li v-for="(document, index) in result.retrieved_docs" :key="`${document.source}-${index}`"><h3>{{ document.source }}</h3><p>{{ document.text }}</p><div class="evidence-meta">{{ document.score_type === 'rrf' ? 'RRF 排名融合分' : document.score_type === 'dense_cosine' ? 'Dense 余弦相似度' : 'TF-IDF 检索相似度' }} {{ formatScore(document.score) }} · 分数不代表答案置信度</div></li></ol>
    </section>
    <details v-if="result.tool_calling_trace?.enabled" class="card raw-card tool-trace">
      <summary>只读工具调用轨迹<AppIcon name="down" /></summary>
      <div class="tool-trace-content">
        <p>{{ toolStatuses[result.tool_calling_trace.status || ''] || '状态未记录' }}</p>
        <p v-if="result.tool_calling_trace.fallback_used">模型路径未完成，已使用原有规则与模板。可先查看下方错误类型；需要业务处理时请联系人工客服。</p>
        <p v-if="result.tool_calling_trace.error_type">错误类型：<code>{{ result.tool_calling_trace.error_type }}</code></p>
        <p v-if="result.tool_calling_trace.fallback_error_type">回退读取未完成：<code>{{ result.tool_calling_trace.fallback_error_type }}</code></p>
        <dl v-if="result.tool_calling_trace.model_calls" class="metrics">
          <div><dt>模型请求尝试（含重试）</dt><dd>{{ result.tool_calling_trace.model_calls.actual_model_calls }} / {{ result.tool_calling_trace.model_calls.max_model_calls }}<span v-if="result.tool_calling_trace.model_calls.simulated"> · 模拟</span></dd></div>
          <div><dt>工具提议 / 实际执行</dt><dd>{{ result.tool_calling_trace.tool_call_count ?? '未记录' }} / {{ result.tool_calling_trace.tool_execution_count ?? '未记录' }}</dd></div>
          <div><dt>回退工具读取次数</dt><dd>{{ result.tool_calling_trace.fallback_tool_execution_count ?? '未记录' }}</dd></div>
        </dl>
        <p v-else>本记录未包含模型请求统计；不据此推断模型已调用。</p>
        <p v-if="retrieval(result)">政策检索：{{ retrieval(result)?.configured_mode || '未记录' }} → {{ retrieval(result)?.actual_mode || '未记录' }}<span v-if="retrieval(result)?.fallback_reason">；检索回退：{{ retrieval(result)?.fallback_reason }}</span></p>
        <ol v-if="result.tool_calling_trace.tools?.length" class="evidence-list">
          <li v-for="(tool, index) in result.tool_calling_trace.tools" :key="`${tool.tool_call_id}-${index}`">
            <h3>{{ tool.tool }} · {{ toolOutcome(tool) }}</h3>
            <p>参数{{ !tool.parameters_checked ? '未校验' : tool.parameters_valid ? '校验通过' : '校验失败' }}；{{ tool.allowed ? '允许尝试执行' : '执行未获许可' }}</p>
            <p class="evidence-meta">call_id：{{ tool.tool_call_id }} · {{ formatNumber(tool.latency_ms) }} ms<span v-if="tool.error_type"> · {{ tool.error_type }}</span></p>
          </li>
        </ol>
        <p v-else>本记录没有模型工具提议。</p>
      </div>
    </details>
    <details class="card raw-card"><summary>查看工具执行数据<AppIcon name="down" /></summary><pre>{{ JSON.stringify(result.tool_results, null, 2) }}</pre></details>
  </div>
</template>

<style scoped>
.tool-trace-content { padding: 0 24px 20px; overflow-wrap: anywhere; }
.tool-trace-content .evidence-list { margin-top: 16px; }
.tool-trace-content .metrics { margin-bottom: 16px; }
@media (max-width: 640px) { .tool-trace-content { padding-inline: 20px; } }
</style>
