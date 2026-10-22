<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import type { ConversationMessage } from "../types";
import ChatMessage from "./ChatMessage.vue";
const props = defineProps<{ messages: ConversationMessage[]; loading: boolean; busy: boolean; hasOlder: boolean }>();
defineEmits<{ trace: [id: string]; older: []; example: [text: string] }>();
const end = ref<HTMLElement | null>(null);
watch(() => { const last = props.messages.at(-1); return last ? `${last.message_id}:${last.content}:${last.status}` : ""; }, async () => { await nextTick(); end.value?.scrollIntoView?.({ block: "nearest" }); });
</script>
<template>
  <section class="chat-window" aria-label="聊天记录" :aria-busy="loading">
    <button v-if="hasOlder" class="button button-secondary chat-older" :disabled="loading || busy" @click="$emit('older')">加载更早的消息</button>
    <p v-if="loading" role="status">正在加载会话…</p>
    <div v-if="!messages.length && !loading" class="chat-welcome"><h2>从一个问题，跟进到处理结果。</h2><p>订单、政策与售后可在同一会话继续。涉及建单时，仍需客服审核。</p><div><button v-for="text in ['我的订单 ORD1001 到哪了？', '退款需要满足哪些条件？', '帮我查一下订单']" :key="text" class="button button-secondary" @click="$emit('example', text)">{{ text }}</button></div></div>
    <ChatMessage v-for="message in messages" :key="message.message_id" :message="message" :disabled="busy" @trace="$emit('trace', $event)" />
    <p v-if="busy" class="chat-working" role="status">正在执行工作流，结果以服务端保存状态为准…</p>
    <div ref="end" />
  </section>
</template>
