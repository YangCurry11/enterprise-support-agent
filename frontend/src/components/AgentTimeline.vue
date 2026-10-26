<script setup lang="ts">
import type { AgentStep } from "../types";
import AppIcon from "./AppIcon.vue";
defineProps<{ steps: AgentStep[] }>();
const labels: Record<string, string> = {
  IntentAgent: "识别用户意图", OrderAgent: "查询订单信息", PolicyAgent: "检索企业政策", TicketAgent: "执行工单操作",
  ResponseAgent: "组织客服回复", LLMResponseAgent: "生成或降级回复", ReviewAgent: "记录审核与权限校验", ClarificationAgent: "补充订单信息",
  SafeToolCalling: "受控只读工具规划与执行",
};
</script>

<template>
  <section class="card timeline-card">
    <div class="section-head"><h2>实际执行链路</h2><span class="panel-count">{{ steps.length }} 条执行记录</span></div>
    <ol v-if="steps.length" class="timeline"><li v-for="(step, index) in steps" :key="`${step.name}-${index}`"><details class="timeline-step"><summary><span class="step-number">{{ index + 1 }}</span><span class="step-copy"><b>{{ labels[step.name] || "处理业务状态" }}</b><small translate="no">{{ step.name }}</small></span><span class="step-state">已执行</span><AppIcon name="down" class="step-chevron" /></summary><pre>{{ JSON.stringify(step.detail, null, 2) }}</pre></details></li></ol>
    <div v-else class="empty-state"><p>暂时没有节点记录</p><small>流程开始执行后，会在此展示实际经过的步骤。</small></div>
  </section>
</template>
