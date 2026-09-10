<script setup lang="ts">
import type { AgentHistoryItem } from "../types";

defineProps<{ runs: AgentHistoryItem[]; loading: boolean }>();
defineEmits<{ refresh: [] }>();
</script>

<template>
  <section class="card history-card">
    <div class="section-head compact">
      <div><span class="eyebrow">RECENT RUNS</span><h2>最近运行</h2></div>
      <button class="text-button" type="button" :disabled="loading" @click="$emit('refresh')">刷新</button>
    </div>
    <div v-if="loading" class="history-loading"><span></span><span></span><span></span></div>
    <div v-else-if="runs.length" class="history-list">
      <details v-for="run in runs" :key="run.run_id" class="history-item">
        <summary>
          <span :class="['intent-dot', { human: run.need_human }]" aria-hidden="true"></span>
          <span><b>{{ run.intent }}</b><small>{{ run.user_input }}</small></span>
          <time>{{ run.latency_ms }}ms</time>
        </summary>
        <p>{{ run.final_response }}</p>
        <small>{{ run.created_at }} · {{ run.user_id }}</small>
      </details>
    </div>
    <p v-else class="empty-state">运行 Agent 后，这里会显示保存在 SQLite 中的最近记录。</p>
  </section>
</template>
