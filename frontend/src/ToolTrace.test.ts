import { expect, it } from "vitest";
import { createApp } from "vue";
import ResultPanel from "./components/ResultPanel.vue";
import type { AgentResult, ToolCallingTrace } from "./types";

function render(trace?: ToolCallingTrace, tools: Record<string, unknown> = {}) {
  const result: AgentResult = { run_id: "test", status: "completed", pending: [], user_id: "U1001",
    user_input: "退款", intent: "refund_policy", intent_confidence: 1, intent_reason: "", order_id: null,
    tool_results: tools, retrieved_docs: [], need_human: false, final_response: "核实政策", steps: [], latency_ms: 1,
    tool_calling_trace: trace };
  const root = document.createElement("div");
  const app = createApp(ResultPanel, { result }); app.mount(root);
  return { root, close: () => app.unmount() };
}
it("keeps legacy records without a tool trace compatible", () => {
  const { root, close } = render();
  try { expect(root.textContent).not.toContain("只读工具调用轨迹"); expect(root.textContent).toContain("核实政策"); }
  finally { close(); }
});
it("discloses sanitized success counters in a native collapsed details", () => {
  const { root, close } = render({ enabled: true, status: "model_generated", tool_call_count: 1, tool_execution_count: 1,
    fallback_tool_execution_count: 0, model_calls: { actual_model_calls: 2, max_model_calls: 4, simulated: true },
    tools: [{ run_id: "test", tool: "query_order", tool_call_id: "call_1", parameters_checked: true, parameters_valid: true,
      allowed: true, executed: true, success: true, permission_blocked: false, error_type: null, latency_ms: 2, cached: false }] });
  try {
    expect(root.querySelector(".tool-trace")?.hasAttribute("open")).toBe(false);
    expect(root.querySelector(".tool-trace summary")?.textContent).toContain("只读工具调用轨迹");
    expect(root.textContent).toContain("执行成功"); expect(root.textContent).toContain("参数校验通过");
    expect(root.textContent).toContain("2 / 4"); expect(root.textContent).toContain("模拟");
  } finally { close(); }
});
it("shows permission refusal and RAG fallback as text, with escaped identifiers", () => {
  const { root, close } = render({ enabled: true, status: "fallback", fallback_used: true, error_type: "tool_not_allowed", fallback_error_type: "tool_budget_exhausted",
    tools: [{ run_id: "test", tool: "not_allowed", tool_call_id: "<img src=x onerror=alert(1)>",
      parameters_checked: false, parameters_valid: false, allowed: false, executed: false, success: false,
      permission_blocked: true, error_type: "order_context_mismatch", latency_ms: 0, cached: false }] },
    { search_policy: { retrieval: { configured_mode: "hybrid", actual_mode: "tfidf", fallback_reason: "index_stale" } } });
  try {
    expect(root.textContent).toContain("权限拦截"); expect(root.textContent).toContain("参数未校验");
    expect(root.textContent).toContain("回退读取未完成：tool_budget_exhausted");
    expect(root.textContent).toContain("hybrid → tfidf"); expect(root.textContent).toContain("index_stale");
    expect(root.textContent).toContain("已使用原有规则与模板"); expect(root.querySelector("img")).toBeNull();
  } finally { close(); }
});
it("does not invent counters on guarded or older partial traces", () => {
  const { root, close } = render({ enabled: true, status: "guarded_workflow" });
  try { expect(root.textContent).toContain("交由原人工审核流程"); expect(root.textContent).toContain("未包含模型请求统计"); }
  finally { close(); }
});
