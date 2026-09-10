<script setup lang="ts">
import type { AgentResult } from "../types";

defineProps<{ result: AgentResult }>();

function formatScore(score?: number): string {
  return typeof score === "number" ? score.toFixed(3) : "—";
}
</script>

<template>
  <div class="result-stack" aria-live="polite">
    <section class="card response-card">
      <div class="section-head">
        <div><span class="eyebrow">FINAL RESPONSE</span><h2>客服回复</h2></div>
        <span :class="['route-badge', { human: result.need_human }]">
          {{ result.need_human ? "转人工处理" : "自动完成" }}
        </span>
      </div>
      <div class="response-copy">{{ result.final_response }}</div>
      <div class="metrics">
        <div><span>识别意图</span><b>{{ result.intent }}</b></div>
        <div><span>意图置信度</span><b>{{ Math.round(result.intent_confidence * 100) }}%</b></div>
        <div><span>订单号</span><b>{{ result.order_id || "—" }}</b></div>
        <div><span>执行耗时</span><b>{{ result.latency_ms }} ms</b></div>
      </div>
    </section>

    <section v-if="result.retrieved_docs.length" class="card evidence-card">
      <div class="section-head">
        <div><span class="eyebrow">RAG EVIDENCE</span><h2>政策检索依据</h2></div>
        <span class="count-pill">{{ result.retrieved_docs.length }} 条</span>
      </div>
      <div class="evidence-list">
        <div v-for="(document, index) in result.retrieved_docs" :key="`${document.source}-${index}`">
          <span>{{ index + 1 }}</span>
          <p><b>{{ document.source }}</b>{{ document.text }}</p>
          <small>{{ formatScore(document.score) }}</small>
        </div>
      </div>
    </section>

    <details class="card raw-card">
      <summary>查看工具结果与完整状态</summary>
      <pre>{{ JSON.stringify(result.tool_results, null, 2) }}</pre>
    </details>
  </div>
</template>
