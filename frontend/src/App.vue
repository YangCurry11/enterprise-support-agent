<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ApiError, supportApi } from "./api";
import AgentTimeline from "./components/AgentTimeline.vue";
import HistoryPanel from "./components/HistoryPanel.vue";
import ResultPanel from "./components/ResultPanel.vue";
import type { AgentHistoryItem, AgentResult, Health } from "./types";

const examples = [
  { label: "订单查询", value: "我的订单 ORD1001 到哪了？" },
  { label: "延迟发货", value: "ORD1002 怎么还没发货？" },
  { label: "退款政策", value: "我买了10天的耳机还能退吗？" },
  { label: "售后处理", value: "商品坏了，无法使用，帮我处理一下" },
  { label: "投诉转人工", value: "我要投诉，你们服务太差了" },
];

const userId = ref("U1001");
const question = ref(examples[0].value);
const health = ref<Health | null>(null);
const result = ref<AgentResult | null>(null);
const history = ref<AgentHistoryItem[]>([]);
const running = ref(false);
const historyLoading = ref(false);
const error = ref("");

const ready = computed(() => health.value?.status === "ok");

function messageFor(errorValue: unknown): string {
  if (errorValue instanceof ApiError) return errorValue.message;
  return "请求未完成，请稍后重试。";
}

async function loadHistory() {
  historyLoading.value = true;
  try {
    history.value = await supportApi.history(10);
  } catch {
    history.value = [];
  } finally {
    historyLoading.value = false;
  }
}

async function runAgent() {
  const input = question.value.trim();
  const customer = userId.value.trim();
  if (!input || !customer || running.value) return;
  running.value = true;
  error.value = "";
  result.value = null;
  try {
    result.value = await supportApi.run(input, customer);
    await loadHistory();
  } catch (errorValue) {
    error.value = messageFor(errorValue);
  } finally {
    running.value = false;
  }
}

onMounted(async () => {
  try {
    health.value = await supportApi.health();
  } catch (errorValue) {
    error.value = messageFor(errorValue);
  }
  await loadHistory();
});
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark">A</span>
        <div><b>ServiceFlow</b><small>企业客服智能中台</small></div>
      </div>

      <div class="environment-card">
        <span :class="['health-dot', { offline: !ready }]" aria-hidden="true"></span>
        <div><b>{{ ready ? "业务服务在线" : "等待后端连接" }}</b><small>FastAPI · SQLite · Tool Calling</small></div>
      </div>

      <section class="side-section">
        <span class="side-label">CUSTOMER CONTEXT</span>
        <label for="user-id">模拟用户编号</label>
        <input id="user-id" v-model.trim="userId" maxlength="50" autocomplete="off" />
        <p>用户编号会随问题传入 Agent，用于订单查询和工单归属。</p>
      </section>

      <section class="side-section">
        <span class="side-label">QUICK SCENARIOS</span>
        <button
          v-for="example in examples"
          :key="example.label"
          type="button"
          :class="['scenario-button', { active: question === example.value }]"
          @click="question = example.value"
        >
          <span>{{ example.label }}</span><small>{{ example.value }}</small>
        </button>
      </section>

      <div class="demo-note">
        <b>演示边界</b>
        <p>订单、用户、政策和工单均为本机模拟数据。投诉与售后场景会创建模拟工单。</p>
      </div>
    </aside>

    <main class="main-content">
      <header class="hero">
        <div>
          <span class="eyebrow">MULTI-AGENT SERVICE DESK</span>
          <h1>让每一次服务请求<br /><em>自动流转</em></h1>
          <p>从意图识别到工具调用、政策检索、工单创建与回复生成，完整呈现企业客服 Agent 的决策链路。</p>
        </div>
        <div class="hero-stats">
          <div><b>5</b><span>Agent 节点</span></div>
          <div><b>3</b><span>业务工具</span></div>
          <div><b>RAG</b><span>政策依据</span></div>
        </div>
      </header>

      <section class="composer card">
        <div class="composer-top">
          <div><span class="eyebrow">NEW REQUEST</span><h2>创建客服请求</h2></div>
          <span class="customer-pill">{{ userId || "未设置用户" }}</span>
        </div>
        <textarea
          v-model="question"
          maxlength="1000"
          rows="4"
          placeholder="输入订单、退款、物流、售后或投诉问题…"
          :disabled="running"
          @keydown.ctrl.enter.prevent="runAgent"
        ></textarea>
        <div class="composer-bottom">
          <p><span>提示</span>投诉和人工客服请求会进入高优先级工单路径。</p>
          <button type="button" :disabled="running || !question.trim() || !userId.trim()" @click="runAgent">
            {{ running ? "Agent 执行中…" : "运行 Agent" }} <span>→</span>
          </button>
        </div>
      </section>

      <p v-if="error" class="error-banner" role="alert">{{ error }}</p>

      <div class="content-grid">
        <div class="primary-column">
          <template v-if="result">
            <ResultPanel :result="result" />
            <AgentTimeline :steps="result.steps" />
          </template>
          <section v-else class="card workflow-placeholder">
            <div class="section-head"><div><span class="eyebrow">ORCHESTRATION</span><h2>一次请求如何流转</h2></div></div>
            <div class="flow-line">
              <div><span>01</span><b>Intent</b><small>识别意图与订单号</small></div>
              <i>→</i>
              <div><span>02</span><b>Tool / RAG</b><small>查询业务或政策</small></div>
              <i>→</i>
              <div><span>03</span><b>Ticket</b><small>按需创建工单</small></div>
              <i>→</i>
              <div><span>04</span><b>Response</b><small>生成或降级回复</small></div>
            </div>
            <p class="placeholder-copy">选择左侧场景并运行，页面会展示本次执行经过的节点，而不是虚构所有 Agent 都被调用。</p>
          </section>
        </div>

        <aside class="secondary-column">
          <HistoryPanel :runs="history" :loading="historyLoading" @refresh="loadHistory" />
          <section class="card capability-card">
            <span class="eyebrow">CAPABILITIES</span>
            <h2>已连接能力</h2>
            <ul>
              <li><span>API</span><div><b>订单与用户查询</b><small>FastAPI + SQLite</small></div></li>
              <li><span>KB</span><div><b>售后政策检索</b><small>TF-IDF 本地 RAG</small></div></li>
              <li><span>TK</span><div><b>工单创建</b><small>优先级与人工转接</small></div></li>
              <li><span>LLM</span><div><b>回复生成</b><small>未配置时模板降级</small></div></li>
            </ul>
          </section>
        </aside>
      </div>
    </main>
  </div>
</template>
