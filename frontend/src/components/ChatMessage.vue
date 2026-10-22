<script setup lang="ts">
import { computed } from "vue";
import type { ConversationMessage } from "../types";
import { statusLabels } from "../presentation";
const props = defineProps<{ message: ConversationMessage; disabled: boolean }>();
defineEmits<{ trace: [id: string] }>();
const status = computed(() => statusLabels[props.message.status as keyof typeof statusLabels] || (props.message.status === "pending" ? "待确认" : props.message.status));
</script>
<template>
  <article :class="['chat-message', message.role]" :aria-label="message.role === 'user' ? '用户消息' : '客服回复'">
    <header><strong>{{ message.role === 'user' ? '你' : message.role === 'system' ? '系统' : 'ServiceFlow' }}</strong><time>{{ new Date(message.created_at).toLocaleTimeString() }}</time></header>
    <p>{{ message.content || '回复尚未完成，请查看处理状态。' }}</p>
    <footer><span :class="['chat-message-status', message.status]">{{ status }}</span><button v-if="message.role === 'assistant' && message.run_id" class="text-button" :disabled="disabled" @click="$emit('trace', message.run_id)">查看运行详情</button></footer>
    <small v-if="message.role === 'assistant' && message.run_id" class="chat-run-id">run_id: {{ message.run_id }}</small>
  </article>
</template>
