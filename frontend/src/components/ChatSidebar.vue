<script setup lang="ts">
import type { Conversation, Identity } from "../types";
defineProps<{ conversations: Conversation[]; currentId?: string; identity: Identity | null; disabled: boolean; more: boolean }>();
defineEmits<{ create: []; select: [id: string]; more: [] }>();
</script>
<template>
  <aside class="chat-sidebar" aria-label="会话导航">
    <a class="chat-brand" href="#chat-main">ServiceFlow<span>企业客服 · 多轮工作空间</span></a>
    <button class="button button-primary" :disabled="disabled || !identity" @click="$emit('create')">新建会话</button>
    <h2>历史会话</h2>
    <nav class="chat-conversations" aria-label="历史会话">
      <button v-for="item in conversations" :key="item.conversation_id" :class="{ selected: currentId === item.conversation_id }" :aria-current="currentId === item.conversation_id ? 'page' : undefined" :disabled="disabled" @click="$emit('select', item.conversation_id)">
        <span>{{ item.title }}</span><small>{{ item.owner_user_id }} · {{ new Date(item.updated_at).toLocaleDateString() }}</small>
      </button>
      <p v-if="!conversations.length">{{ identity ? '还没有会话，从新建开始。' : '验证身份后加载会话。' }}</p>
      <button v-if="more" :disabled="disabled" @click="$emit('more')">加载更多会话</button>
    </nav>
    <div class="chat-account"><strong>{{ identity?.user_id || '未验证身份' }}</strong><span>{{ identity?.role === 'support' ? '客服 / 可审核' : '客户 / 仅本人数据' }}</span></div>
    <slot />
  </aside>
</template>
