<script setup lang="ts">
import { ref } from "vue";
const props = defineProps<{ disabled: boolean; busy: boolean }>();
const emit = defineEmits<{ send: [content: string] }>();
const text = ref("");
function send() { if (props.disabled || props.busy || !text.value.trim()) return; emit("send", text.value); text.value = ""; }
function keyboard(event: KeyboardEvent) { if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); send(); } }
function fill(value: string) { text.value = value; }
defineExpose({ fill });
</script>
<template>
  <form class="chat-composer" :aria-busy="busy" @submit.prevent="send">
    <label for="chat-input">向客服提问</label>
    <textarea id="chat-input" v-model="text" maxlength="1000" rows="3" :disabled="disabled || busy" placeholder="例如：我的订单 ORD1001 到哪了？" aria-describedby="chat-input-help" @keydown="keyboard" />
    <div><small id="chat-input-help">Enter 发送 · Shift+Enter 换行 · {{ text.length }}/1000</small><button class="button button-primary" :disabled="disabled || busy || !text.trim()">{{ busy ? '正在处理…' : '发送消息' }}</button></div>
  </form>
</template>
