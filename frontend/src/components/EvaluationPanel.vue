<script setup lang="ts">
import { onMounted, ref } from "vue";
import { supportApi } from "../api";
import type { EvaluationReport } from "../types";
const report = ref<EvaluationReport | null>(null), error = ref(""), loading = ref(false);
const percent = (value?: number) => typeof value === "number" ? `${(value * 100).toFixed(2)}%` : "未统计";
async function load() { loading.value = true; error.value = ""; try { report.value = await supportApi.evaluation(); } catch (cause) { error.value = cause instanceof Error ? cause.message : "报告读取失败"; } finally { loading.value = false; } }
onMounted(load);
</script>
<template>
  <section class="chat-evaluation" :aria-busy="loading"><header><div><h1>Agent 评测</h1><p>读取最近一次真实报告，不在页面触发模型调用。</p></div><button class="button button-secondary" :disabled="loading" @click="load">刷新报告</button></header>
    <p v-if="error" role="alert" class="error-banner">{{ error }}</p><p v-if="loading" role="status">正在读取报告…</p>
    <p v-else-if="!report">暂无评测数据。请先运行 python -m evaluation.run_evaluation。</p>
    <template v-else><p>{{ new Date(report.generated_at).toLocaleString() }} · {{ report.mode }}</p><p class="chat-evaluation-note">{{ report.data_provenance }}。模拟开发集，非生产数据；独立人工复核尚未完成。</p>
      <table><caption>核心指标</caption><tbody><tr><th>意图 Accuracy / Macro-F1</th><td>{{ percent(report.intent.metrics.accuracy) }} / {{ percent(report.intent.metrics.macro_f1) }}</td></tr><tr><th>RAG Recall@1 / @3 / @5</th><td>{{ percent(report.rag.metrics.recall_at_1) }} / {{ percent(report.rag.metrics.recall_at_3) }} / {{ percent(report.rag.metrics.recall_at_5) }}</td></tr><tr><th>RAG MRR（文档级）</th><td>{{ report.rag.metrics.mrr.toFixed(3) }}</td></tr><tr><th>工作流场景通过</th><td>{{ report.workflow.metrics.passed }} / {{ report.workflow.metrics.sample_count }}</td></tr><tr><th>请求均值 / P95</th><td>{{ report.workflow.metrics.timing.mean_ms.toFixed(1) }} / {{ report.workflow.metrics.timing.p95_ms.toFixed(1) }} ms</td></tr></tbody></table>
      <p>P95 使用 nearest-rank；耗时来自本机 TestClient，不代表公网负载测试。</p>
      <table><caption>各类意图 F1</caption><thead><tr><th>类别</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead><tbody><tr v-for="(metric, name) in report.intent.metrics.per_class" :key="name"><th>{{ name }}</th><td>{{ percent(metric.precision) }}</td><td>{{ percent(metric.recall) }}</td><td>{{ percent(metric.f1) }}</td></tr></tbody></table>
      <h2>错误样例</h2><p v-if="![...report.intent.cases, ...report.rag.cases, ...report.workflow.cases].some(c => !c.passed)">本报告的用例未出现失败，不表示不存在其他缺陷。</p><details v-for="item in [...report.intent.cases, ...report.rag.cases, ...report.workflow.cases].filter(c => !c.passed)" :key="item.id"><summary>{{ item.id }} · {{ item.input || item.query || item.scenario }}</summary><pre>{{ JSON.stringify(item, null, 2) }}</pre></details>
    </template>
  </section>
</template>
