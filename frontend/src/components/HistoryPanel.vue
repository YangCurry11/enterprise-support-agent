<script setup lang="ts">
import type { AgentHistoryItem } from "../types";
import { formatDate, formatNumber, intentLabels, statusLabels } from "../presentation";
import AppIcon from "./AppIcon.vue";

defineProps<{ runs: AgentHistoryItem[]; loading: boolean; title?: string; queue?: boolean; error?: string; disabled?: boolean; selectedId?: string }>();
defineEmits<{ refresh: []; open: [runId: string] }>();
</script>

<template>
  <section class="card history-card" :aria-label="title || '最近记录'" :aria-busy="loading">
    <div class="section-head">
      <div><h2>{{ title || "最近记录" }}</h2><span class="panel-count">{{ queue ? "最多显示 50 条待审核请求" : "最近加载的 10 条请求" }}</span></div>
      <button class="text-button" type="button" :disabled="loading || disabled" :aria-label="`刷新${title || '最近记录'}`" @click="$emit('refresh')"><AppIcon name="refresh" />刷新</button>
    </div>
    <div v-if="loading" class="history-loading" role="status"><span class="visually-hidden">正在加载请求记录…</span><span aria-hidden="true"></span><span aria-hidden="true"></span></div>
    <p v-else-if="error" class="history-error" role="alert">{{ error }}</p>
    <ul v-else-if="runs.length" class="history-list">
      <li v-for="run in runs" :key="run.run_id" :class="['history-item', { selected: run.run_id === selectedId }]">
        <div class="history-item-head"><b>{{ intentLabels[run.intent] || run.intent }}</b><span :class="['status-badge', run.status]">{{ statusLabels[run.status] || run.status }}</span></div>
        <p class="history-question">{{ run.user_input }}</p>
        <div class="history-meta"><time :datetime="run.created_at">{{ formatDate(run.created_at) }}</time><span>{{ run.user_id }}</span><span>{{ formatNumber(run.latency_ms) }} ms</span></div>
        <button class="text-button" type="button" :disabled="disabled" :aria-label="`打开处理：${run.user_input}`" @click="$emit('open', run.run_id)">打开处理<AppIcon name="chevron" /></button>
      </li>
    </ul>
    <div v-else class="empty-state"><AppIcon :name="queue ? 'check' : 'inbox'" /><p>{{ queue ? "暂时没有待审核请求" : "还没有处理记录" }}</p><small>{{ queue ? "新的待审核请求会显示在这里。" : "提交一条问题，开始你的第一条服务请求。" }}</small></div>
  </section>
</template>
