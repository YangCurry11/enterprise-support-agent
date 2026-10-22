<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import AppIcon from "./components/AppIcon.vue";
import { statusLabels } from "./presentation";
import { ApiError, setCredential, supportApi } from "./api";
import AgentTimeline from "./components/AgentTimeline.vue";
import HistoryPanel from "./components/HistoryPanel.vue";
import ResultPanel from "./components/ResultPanel.vue";
import type { AgentHistoryItem, AgentResult, Health, Identity } from "./types";

const examples = [
  { label: "订单查询", icon: "inbox", value: "我的订单 ORD1001 到哪了？" },
  { label: "订单访问校验", icon: "shield", value: "ORD1002 怎么还没发货？" },
  { label: "退款政策", icon: "book", value: "我买了10天的耳机还能退吗？" },
  { label: "售后处理", icon: "layers", value: "商品坏了，无法使用，帮我处理一下" },
  { label: "投诉转人工", icon: "user", value: "我要投诉，你们服务太差了" },
];

const props = defineProps<{ initialToken?: string }>();
const userId = ref("U1001");
const token = ref(props.initialToken ?? (import.meta.env.DEV ? "dev-customer-u1001" : ""));
const identity = ref<Identity | null>(null);
const orderId = ref("");
const reviewNote = ref("");
let retryRequest: { payload: string; key: string } | null = null;
const question = ref(examples[0].value);
const health = ref<Health | null>(null);
const result = ref<AgentResult | null>(null);
const history = ref<AgentHistoryItem[]>([]);
const reviewQueue = ref<AgentHistoryItem[]>([]);
const running = ref(false);
const historyLoading = ref(false);
const error = ref("");
const historyError = ref("");
const reviewError = ref("");
const authenticating = ref(false);
const revealToken = ref(false);
const mobileMenuOpen = ref(false);
const rejecting = ref(false);
const errorPanel = ref<HTMLElement | null>(null);
watch(error, async value => { if (value) { await nextTick(); errorPanel.value?.focus(); } });
watch(() => result.value?.run_id, () => { rejecting.value = false; reviewNote.value = ""; orderId.value = ""; });
async function showCredentials() {
  mobileMenuOpen.value = true;
  await nextTick();
  const details = document.querySelector<HTMLDetailsElement>(".credential-details");
  if (details) details.open = true;
  document.getElementById("token")?.focus();
}

const ready = computed(() => health.value?.status === "ok");

async function authenticate() {
  if (running.value || authenticating.value) return;
  authenticating.value = true;
  setCredential(token.value);
  identity.value = null;
  result.value = null;
  history.value = [];
  reviewQueue.value = [];
  error.value = "";
  try {
    identity.value = await supportApi.me();
    if (identity.value.role === "customer") userId.value = identity.value.user_id;
    await loadHistory();
  } catch (value) { error.value = messageFor(value); }
  finally { authenticating.value = false; }
}

async function openRun(runId: string) {
  if (running.value) return;
  running.value = true;
  error.value = "";
  try { result.value = await supportApi.get(runId); }
  catch (value) { error.value = messageFor(value); }
  finally { running.value = false; }
}

async function continueRun(approved?: boolean) {
  if (!result.value || running.value) return;
  running.value = true;
  error.value = "";
  try {
    result.value = approved === undefined
      ? await supportApi.resume(result.value.run_id, orderId.value.trim().toUpperCase())
      : await supportApi.review(result.value.run_id, approved, reviewNote.value);
    await loadHistory();
  } catch (value) { error.value = messageFor(value); }
  finally { running.value = false; }
}

async function recoverRun() {
  if (!result.value || running.value) return;
  running.value = true;
  error.value = "";
  try {
    result.value = await supportApi.retry(result.value.run_id);
    await loadHistory();
  } catch (value) { error.value = messageFor(value); }
  finally { running.value = false; }
}

function messageFor(errorValue: unknown): string {
  if (errorValue instanceof ApiError) return errorValue.message;
  return "请求未完成，请稍后重试。";
}

async function loadHistory() {
  if (historyLoading.value) return;
  historyLoading.value = true;
  historyError.value = "";
  reviewError.value = "";
  const settled = await Promise.allSettled([
    supportApi.history(10),
    identity.value?.role === "support" ? supportApi.reviews() : Promise.resolve([]),
  ]);
  const [recent, pending] = settled;
  if (recent.status === "fulfilled") history.value = recent.value;
  else { history.value = []; historyError.value = "记录加载失败，请刷新重试。"; }
  if (pending.status === "fulfilled") reviewQueue.value = pending.value;
  else { reviewQueue.value = []; reviewError.value = "审核队列加载失败，请刷新重试。"; }
  historyLoading.value = false;
}

async function runAgent() {
  const input = question.value.trim();
  const customer = userId.value.trim();
  if (running.value || authenticating.value) return;
  if (!identity.value) { error.value = "请先打开访问身份设置并验证凭证。"; return; }
  if (!input || !customer) { error.value = "请填写问题描述和服务对象编号。"; return; }
  running.value = true;
  error.value = "";
  result.value = null;
  try {
    const payload = JSON.stringify([input, customer]);
    if (!retryRequest || retryRequest.payload !== payload) retryRequest = { payload, key: crypto.randomUUID() };
    result.value = await supportApi.run(input, customer, retryRequest.key);
    retryRequest = null;
    await loadHistory();
  } catch (errorValue) {
    error.value = messageFor(errorValue);
    await loadHistory();
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
  if (token.value) await authenticate();
});
</script>

<template>
  <a class="skip-link" href="#main-content">跳到服务工作台</a>
  <div class="app-shell">
    <aside :class="['sidebar', { 'is-expanded': mobileMenuOpen }]" aria-label="工作台侧栏">
      <div class="brand-row">
        <a class="brand" href="#main-content" aria-label="ServiceFlow 服务工作台">
          <span class="brand-mark"><AppIcon name="layers" /></span>
          <span><b translate="no">ServiceFlow</b><small>企业客服工作台</small></span>
        </a>
        <button class="mobile-menu icon-button" type="button" :aria-expanded="mobileMenuOpen" aria-controls="sidebar-content" aria-label="展开或收起身份与快捷场景" @click="mobileMenuOpen = !mobileMenuOpen"><AppIcon :name="mobileMenuOpen ? 'close' : 'menu'" /></button>
      </div>
      <div id="sidebar-content" class="sidebar-body">
        <nav class="workspace-nav" aria-label="工作台导航">
          <a href="#request-composer"><AppIcon name="inbox" />创建请求</a>
          <a v-if="identity?.role === 'support'" href="#review-queue"><AppIcon name="shield" />待审核请求<span class="nav-count">{{ reviewQueue.length }}</span></a>
          <a href="#recent-runs"><AppIcon name="history" />最近记录</a>
        </nav>
        <section class="identity-section">
          <div class="identity-summary"><span class="avatar"><AppIcon name="user" /></span><div><b>{{ identity?.user_id || "尚未验证身份" }}</b><small>{{ identity?.role === "support" ? "客服审核员" : identity ? "客户账户" : "先验证身份，再发起请求" }}</small></div><AppIcon v-if="identity" name="check" class="identity-check" /></div>
          <details class="credential-details">
            <summary>访问身份设置<AppIcon name="down" /></summary>
            <form class="credential-form" @submit.prevent="authenticate">
              <label for="token">访问凭证</label>
              <div class="credential-field"><input id="token" v-model.trim="token" name="access-token" :type="revealToken ? 'text' : 'password'" autocomplete="off" :spellcheck="false" :disabled="running || authenticating" required /><button class="icon-button" type="button" :aria-label="revealToken ? '隐藏访问凭证' : '显示访问凭证'" :aria-pressed="revealToken" @click="revealToken = !revealToken"><AppIcon name="eye" /></button></div>
              <button class="button button-sidebar" type="submit" :disabled="running || authenticating">{{ authenticating ? "正在验证…" : "验证身份" }}</button>
            </form>
          </details>
          <div class="customer-field"><label for="user-id">服务对象编号</label><input id="user-id" v-model.trim="userId" name="customer-id" maxlength="50" autocomplete="off" :spellcheck="false" :disabled="identity?.role !== 'support' || running" aria-describedby="customer-help" /><p id="customer-help">{{ identity?.role === "support" ? "可为指定客户发起请求。" : "当前账户仅可访问自己的订单。" }}</p></div>
        </section>
        <section class="scenario-section"><h2>快捷场景</h2><div class="scenario-list"><button v-for="example in examples" :key="example.label" type="button" :class="['scenario-button', { active: question === example.value }]" :aria-pressed="question === example.value" :disabled="running" @click="question = example.value"><AppIcon :name="example.icon" /><span>{{ example.label }}</span><AppIcon name="chevron" class="scenario-chevron" /></button></div></section>
        <div class="sidebar-foot"><div class="service-state"><span :class="['health-dot', { offline: !ready }]" aria-hidden="true"></span>{{ ready ? "业务服务在线" : "等待后端连接" }}</div><p>当前使用测试订单与政策。工单须审核，不执行真实退款或赔偿。</p></div>
      </div>
    </aside>
    <main id="main-content" class="main-content" tabindex="-1">
      <header class="workspace-toolbar"><div class="workspace-location"><AppIcon name="inbox" /><span>服务工作空间</span></div><span class="environment-label">本机测试环境</span></header>
      <div class="workspace-content">
        <header class="workspace-heading"><div><h1>客服工作台</h1><p>提交问题、跟进审核，让每一次处理都有记录。</p></div><span :class="['workspace-status', { offline: !ready }]"><AppIcon :name="ready ? 'check' : 'clock'" />{{ ready ? "服务已就绪" : "后端未连接" }}</span></header>
        <dl class="workspace-summary" aria-label="当前工作台概览">
          <div><dt>当前服务对象</dt><dd>{{ userId || "未设置" }}<span>{{ identity?.role === "support" ? "客服代办" : "客户自助" }}</span></dd></div>
          <div><dt>最近加载记录</dt><dd>{{ historyLoading ? "…" : history.length }}<span>条 / 最多 10 条</span></dd></div>
          <div v-if="identity?.role === 'support'"><dt>已加载待审核</dt><dd>{{ historyLoading ? "…" : reviewQueue.length }}<span>条 / 最多 50 条</span></dd></div>
          <div v-else><dt>本次处理状态</dt><dd class="summary-state">{{ running ? "处理中" : result ? statusLabels[result.status] : "等待请求" }}</dd></div>
        </dl>
        <p v-if="error" id="request-error" ref="errorPanel" class="error-banner" role="alert" tabindex="-1"><AppIcon name="alert" /><span>{{ error }}</span></p>
        <div class="content-grid">
          <div class="primary-column">
            <form id="request-composer" class="composer-card" :aria-busy="running" @submit.prevent="runAgent">
              <div class="section-head"><div class="section-heading"><span class="heading-icon"><AppIcon name="message" /></span><div><h2>创建客服请求</h2><p>输入问题，系统将按需查询订单、检索政策或发起审核。</p></div></div><span class="customer-pill"><AppIcon name="user" />{{ userId || "未设置" }}</span></div>
              <label class="input-label" for="question">问题描述</label>
              <textarea id="question" v-model="question" name="question" maxlength="1000" rows="4" placeholder="例如：我的订单 ORD1001 到哪了…" :disabled="running" required aria-describedby="question-help" @keydown.ctrl.enter.prevent="runAgent"></textarea>
              <div class="input-caption"><span id="question-help">订单问题请尽量提供订单号。</span><span>{{ question.length }} / 1000</span></div>
              <div class="composer-bottom"><span class="shortcut-hint"><kbd>Ctrl</kbd> + <kbd>Enter</kbd> 发送</span><button class="button button-primary" type="submit" :disabled="running || authenticating"><AppIcon :name="running ? 'refresh' : 'send'" :class="{ spinning: running }" />{{ running ? "正在处理…" : "运行 Agent" }}</button></div>
              <p v-if="!identity" class="form-guidance">请先在左侧“访问身份设置”验证凭证。<button class="text-button" type="button" @click="showCredentials">打开身份设置</button></p>
            </form>
            <template v-if="result">
              <section v-if="result.status === 'failed' || result.status === 'running'" class="action-panel action-error" aria-labelledby="recovery-heading"><AppIcon name="refresh" class="action-icon" /><div class="action-content"><h2 id="recovery-heading">从已保存的位置继续</h2><p>流程暂未完成。恢复会沿用当前请求，已创建的工单不会重复写入。</p><button class="button button-secondary" type="button" :disabled="running" @click="recoverRun">重试并恢复</button></div></section>
              <form v-if="result.status === 'awaiting_input'" class="action-panel" @submit.prevent="continueRun()"><AppIcon name="search" class="action-icon" /><div class="action-content"><h2>补充订单号</h2><p>这条请求已保存。补充后会继续查询，无需重新提交问题。</p><label for="order-id">订单号</label><div class="inline-form"><input id="order-id" v-model="orderId" name="order-id" placeholder="例如 ORD1001…" maxlength="40" autocomplete="off" :spellcheck="false" pattern="[Oo][Rr][Dd][0-9]{4,}" required :disabled="running" /><button class="button button-primary" type="submit" :disabled="running">继续处理</button></div></div></form>
              <section v-if="result.status === 'awaiting_review'" class="action-panel action-review" aria-labelledby="review-heading"><AppIcon name="shield" class="action-icon" /><div class="action-content"><h2 id="review-heading">等待客服审核</h2><p>尚未创建工单。审核通过后才会执行建单。</p><div class="review-request"><span>{{ result.user_id }}</span><p>{{ result.user_input }}</p></div>
                <form v-if="identity?.role === 'support'" @submit.prevent="continueRun(true)"><label for="review-note">审核说明 <span class="optional-label">选填</span></label><textarea id="review-note" v-model="reviewNote" name="review-note" maxlength="500" rows="2" placeholder="填写核实情况或处理依据…" :disabled="running"></textarea><div v-if="rejecting" class="reject-confirm" role="group" aria-label="确认拒绝审核"><p>确认拒绝这条请求？拒绝后不会创建工单。</p><div class="action-buttons"><button class="button button-danger" type="button" :disabled="running" @click="continueRun(false)">确认拒绝</button><button class="button button-secondary" type="button" :disabled="running" @click="rejecting = false">取消</button></div></div><div v-else class="action-buttons"><button class="button button-primary" type="submit" :disabled="running"><AppIcon name="check" />通过并创建工单</button><button class="button button-secondary" type="button" :disabled="running" @click="rejecting = true">拒绝</button></div></form>
                <button v-else class="button button-secondary" type="button" :disabled="running" @click="openRun(result.run_id)"><AppIcon name="refresh" />刷新处理状态</button>
              </div></section>
              <ResultPanel :result="result" /><AgentTimeline :steps="result.steps" />
            </template>
            <section v-else class="workflow-placeholder" aria-labelledby="flow-heading"><div class="section-head"><div><h2 id="flow-heading">一次请求的处理路径</h2><p>根据问题选择必要步骤，执行结果会在这里展开。</p></div><AppIcon name="layers" /></div><ol class="flow-line"><li><span class="flow-node"><AppIcon name="message" /></span><b>识别问题</b><small>理解意图与订单号</small></li><li><span class="flow-node"><AppIcon name="book" /></span><b>查询依据</b><small>订单信息或企业政策</small></li><li><span class="flow-node"><AppIcon name="shield" /></span><b>按需审核</b><small>需建单时等待客服</small></li><li><span class="flow-node"><AppIcon name="check" /></span><b>返回结果</b><small>保留处理记录与依据</small></li></ol><div class="workflow-note"><AppIcon name="clock" /><p>等待补充或审核的请求会保存进度，重启后仍可继续。</p></div></section>
          </div>
          <aside class="secondary-column" aria-label="请求记录与审核">
            <HistoryPanel v-if="identity?.role === 'support'" id="review-queue" title="待审核请求" :runs="reviewQueue" :loading="historyLoading" :error="reviewError" :disabled="running" :selected-id="result?.run_id" queue @refresh="loadHistory" @open="openRun" />
            <HistoryPanel id="recent-runs" :runs="history" :loading="historyLoading" :error="historyError" :disabled="running" :selected-id="result?.run_id" @refresh="loadHistory" @open="openRun" />
            <section class="capability-card"><h2>处理保障</h2><ul><li><AppIcon name="shield" /><div><b>按身份访问</b><small>订单数据按客户归属校验</small></div></li><li><AppIcon name="book" /><div><b>政策有依据</b><small>回复可查看检索来源与片段</small></div></li><li><AppIcon name="history" /><div><b>进度可恢复</b><small>审核与补充信息均保存状态</small></div></li></ul></section>
          </aside>
        </div>
        <footer class="workspace-footer"><span translate="no">ServiceFlow</span><span>测试业务环境 · 不执行真实退款或赔偿</span></footer>
      </div>
    </main>
  </div>
</template>
