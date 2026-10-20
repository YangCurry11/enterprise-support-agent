import type { AgentResult } from "./types";

export const intentLabels: Record<string, string> = {
  order_query: "订单查询", refund_policy: "退款政策", shipping_policy: "物流政策",
  after_sales: "售后处理", complaint: "投诉处理", human_escalation: "人工转接",
  chit_chat: "日常咨询", unknown: "待识别问题",
};
export const statusLabels: Record<AgentResult["status"], string> = {
  running: "处理中", completed: "已完成", awaiting_input: "待补充", awaiting_review: "待审核", failed: "可恢复",
};
export function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "时间未记录" : new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(date);
}
export function formatNumber(value: number) { return new Intl.NumberFormat("zh-CN").format(value); }
