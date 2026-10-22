<script setup lang="ts">
import { ref, watch } from "vue";
import type { AgentResult } from "../types";
import ResultPanel from "./ResultPanel.vue";
import AgentTimeline from "./AgentTimeline.vue";
const props = defineProps<{ result: AgentResult; reviewer: boolean; busy: boolean }>();
defineEmits<{ close: []; refresh: []; action: [action: "resume" | "approve" | "reject" | "recover", value?: string] }>();
const order = ref(""), note = ref(""), rejecting = ref(false);
watch(() => props.result.run_id, () => { order.value = ""; note.value = ""; rejecting.value = false; });
</script>
<template>
  <aside class="chat-trace" aria-label="运行详情"><header class="chat-trace-head"><h2>运行详情</h2><button class="button button-secondary" @click="$emit('close')">收起</button></header>
    <p class="chat-run-id">{{ result.run_id }}</p><button class="text-button" :disabled="busy" @click="$emit('refresh')">刷新运行与消息</button>
    <form v-if="result.status === 'awaiting_input'" class="chat-action" @submit.prevent="$emit('action', 'resume', order)"><h3>补充订单号</h3><p>也可直接在聊天中补充，继续同一条运行。</p><label for="trace-order">订单号</label><input id="trace-order" v-model="order" pattern="[Oo][Rr][Dd][0-9]{4,}" maxlength="40" required /><button class="button button-primary" :disabled="busy">继续处理</button></form>
    <section v-if="result.status === 'awaiting_review'" class="chat-action"><h3>等待客服审核</h3><p>尚未建单。普通聊天消息不能替代审核。</p><form v-if="reviewer" @submit.prevent="$emit('action', 'approve', note)"><label for="trace-note">审核说明（选填）</label><textarea id="trace-note" v-model="note" maxlength="500" rows="2" /><div class="chat-action-buttons"><button class="button button-primary" :disabled="busy">通过并创建工单</button><button class="button button-secondary" type="button" :disabled="busy" @click="rejecting = !rejecting">{{ rejecting ? '取消拒绝' : '拒绝' }}</button><button v-if="rejecting" class="button button-danger" type="button" :disabled="busy" @click="$emit('action', 'reject', note)">确认拒绝，不创建工单</button></div></form><p v-else>请等待客服处理，随后刷新状态。</p></section>
    <button v-if="result.status === 'failed' || result.status === 'running'" class="button button-secondary" :disabled="busy" @click="$emit('action', 'recover')">从检查点重试恢复</button>
    <ResultPanel :result="result" /><AgentTimeline :steps="result.steps" />
  </aside>
</template>
