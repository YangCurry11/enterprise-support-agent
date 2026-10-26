<script setup lang="ts">
import type { AgentResult } from "../types";
import { formatNumber, intentLabels, statusLabels } from "../presentation";
import AppIcon from "./AppIcon.vue";
defineProps<{ result: AgentResult }>();

function formatScore(score?: number): string { return typeof score === "number" ? score.toFixed(3) : "未记录"; }
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
    <details class="card raw-card"><summary>查看工具执行数据<AppIcon name="down" /></summary><pre>{{ JSON.stringify(result.tool_results, null, 2) }}</pre></details>
  </div>
</template>
