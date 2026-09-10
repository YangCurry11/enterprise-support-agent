<script setup lang="ts">
import type { AgentStep } from "../types";

defineProps<{ steps: AgentStep[] }>();

const labels: Record<string, string> = {
  IntentAgent: "识别用户意图",
  OrderAgent: "查询订单系统",
  PolicyAgent: "检索政策知识库",
  TicketAgent: "创建售后工单",
  ResponseAgent: "生成客服回复",
  LLMResponseAgent: "大模型回复与降级",
};
</script>

<template>
  <section class="card timeline-card">
    <div class="section-head">
      <div><span class="eyebrow">WORKFLOW TRACE</span><h2>Agent 执行链路</h2></div>
      <span class="count-pill">{{ steps.length }} 个节点</span>
    </div>
    <div class="timeline">
      <details v-for="(step, index) in steps" :key="`${step.name}-${index}`" class="timeline-step">
        <summary>
          <span class="step-number">{{ String(index + 1).padStart(2, "0") }}</span>
          <span class="step-copy"><b>{{ step.name }}</b><small>{{ labels[step.name] || "处理业务状态" }}</small></span>
          <span class="step-state">完成</span>
        </summary>
        <pre>{{ JSON.stringify(step.detail, null, 2) }}</pre>
      </details>
    </div>
  </section>
</template>
