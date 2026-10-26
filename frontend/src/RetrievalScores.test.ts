import { expect, it } from "vitest";
import { createApp } from "vue";
import ResultPanel from "./components/ResultPanel.vue";
import type { AgentResult } from "./types";

it.each([
  ["rrf", "RRF 排名融合分"],
  ["dense_cosine", "Dense 余弦相似度"],
  ["tfidf_cosine", "TF-IDF 检索相似度"],
  [undefined, "TF-IDF 检索相似度"],
] as const)("labels %s scores without claiming confidence", (scoreType, expected) => {
  const result: AgentResult = {
    run_id: "test", status: "completed", pending: [], user_id: "U1001", user_input: "退款",
    intent: "refund_policy", intent_confidence: 1, intent_reason: "", order_id: null,
    tool_results: {}, need_human: false, final_response: "需核实政策", steps: [], latency_ms: 1,
    retrieved_docs: [{ source: "refund_policy.md", text: "政策条件", score: .032, score_type: scoreType }],
  };
  const root = document.createElement("div");
  const app = createApp(ResultPanel, { result });
  try {
    app.mount(root);
    expect(root.textContent).toContain(expected);
    expect(root.textContent).toContain("分数不代表答案置信度");
    expect(root.textContent).toContain("refund_policy.md");
  } finally { app.unmount(); }
});
