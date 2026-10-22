<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useConversation } from "./composables/useConversation";
import ChatSidebar from "./components/ChatSidebar.vue";
import ChatWindow from "./components/ChatWindow.vue";
import ChatComposer from "./components/ChatComposer.vue";
import AgentTracePanel from "./components/AgentTracePanel.vue";
import EvaluationPanel from "./components/EvaluationPanel.vue";
import LegacyWorkbench from "./LegacyWorkbench.vue";
const chat = useConversation();
const { token, identity, conversations, current, messages, result, error, busy, authenticating, loading, owner, pending, canSend, moreConversations, before } = chat;
const page = ref<"chat" | "legacy" | "evaluation">("chat"), trace = ref(false), mobileNav = ref(false);
const composer = ref<InstanceType<typeof ChatComposer> | null>(null);
watch(() => result.value?.run_id, value => { if (value) trace.value = true; });
async function open(id: string) { await chat.openRun(id); trace.value = !!result.value; }
async function navigate(value: typeof page.value) { const previous = page.value; page.value = value; if (previous === "legacy" && value !== "legacy") await chat.authenticate(); }
async function authenticate() { trace.value = false; page.value = "chat"; await chat.authenticate(); }
onMounted(chat.authenticate);
watch(() => identity.value?.user_id, () => composer.value?.fill(""));
watch(() => current.value?.conversation_id, () => composer.value?.fill(""));
</script>
<template>
  <template v-if="page === 'legacy'"><div class="chat-return"><button class="button button-secondary" @click="navigate('chat')">返回连续会话</button><span>兼容工作台 · 最近运行与客服审核</span></div><LegacyWorkbench :initial-token="token" /></template>
  <div v-else class="chat-shell" :class="{ 'chat-nav-open': mobileNav }">
    <button class="chat-mobile-toggle button button-secondary" :aria-expanded="mobileNav" @click="mobileNav = !mobileNav">{{ mobileNav ? '收起会话导航' : '会话与身份设置' }}</button>
    <ChatSidebar :conversations="conversations" :current-id="current?.conversation_id" :identity="identity" :disabled="busy || loading || authenticating" :more="moreConversations" @create="chat.create()" @select="chat.select($event); mobileNav = false" @more="chat.loadMore()">
      <details class="chat-credentials"><summary>访问身份设置</summary><form @submit.prevent="authenticate"><label for="chat-token">访问凭证</label><input id="chat-token" v-model="token" type="password" autocomplete="off" /><button class="button button-secondary" :disabled="authenticating">{{ authenticating ? '验证中…' : '验证身份' }}</button></form></details>
      <div v-if="identity?.role === 'support'" class="chat-owner"><label for="chat-owner">新会话服务对象</label><input id="chat-owner" v-model="owner" maxlength="50" :disabled="busy" /></div>
      <nav class="chat-secondary-nav" aria-label="工作台功能"><button :disabled="busy" @click="navigate('legacy')">{{ identity?.role === 'support' ? '最近运行与客服审核' : '最近运行与恢复' }}</button><button v-if="identity?.role === 'support'" :disabled="busy" :aria-current="page === 'evaluation' ? 'page' : undefined" @click="page = page === 'evaluation' ? 'chat' : 'evaluation'">{{ page === 'evaluation' ? '返回聊天' : 'Agent 评测' }}</button></nav>
    </ChatSidebar>
    <main id="chat-main" class="chat-main"><EvaluationPanel v-if="page === 'evaluation' && identity?.role === 'support'" :key="identity.user_id" />
      <template v-else><header class="chat-heading"><div><h1>{{ current?.title || '客服会话' }}</h1><p>{{ current ? current.owner_user_id + ' · 历史已持久化，可刷新恢复' : '按身份访问，按运行追踪。' }}</p></div><div><button class="button button-secondary" :disabled="busy || !identity" @click="chat.refresh()">刷新消息</button><button v-if="result && !trace" class="button button-secondary" @click="trace = true">展开运行详情</button></div></header>
        <p v-if="error" role="alert" class="error-banner">{{ error }}</p><div v-if="pending && !busy" class="chat-retry"><p>请求尚未确认完成。重试会沿用原 request_id，不重复建单。</p><button class="button button-secondary" @click="chat.retry()">安全重试原消息</button></div>
        <div class="chat-body"><div class="chat-center"><ChatWindow :messages="messages" :loading="loading" :busy="busy" :has-older="!!before" @trace="open" @older="chat.older()" @example="composer?.fill($event)" /><ChatComposer ref="composer" :disabled="!canSend" :busy="busy" @send="chat.send($event)" /><p class="chat-sandbox">测试业务环境 · 不执行真实退款或赔偿 · 人工审核不能由聊天替代</p></div>
          <AgentTracePanel v-if="trace && result" :result="result" :reviewer="identity?.role === 'support'" :busy="busy" @close="trace = false" @refresh="chat.refresh()" @action="chat.act" />
        </div>
      </template>
    </main>
  </div>
</template>
