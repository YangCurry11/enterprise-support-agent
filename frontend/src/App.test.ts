import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createApp, nextTick, type App as VueApp } from "vue";
// The original workbench is preserved intact behind the run/review navigation.
import App from "./LegacyWorkbench.vue";
import { supportApi } from "./api";

vi.mock("./api", () => ({
  ApiError: class ApiError extends Error {},
  setCredential: vi.fn(),
  supportApi: { health: vi.fn(), me: vi.fn(), history: vi.fn(), reviews: vi.fn(), run: vi.fn(), get: vi.fn(), review: vi.fn(), resume: vi.fn(), retry: vi.fn() },
}));

let app: VueApp;
let container: HTMLDivElement;
const pending = {
  run_id: "run-1", status: "awaiting_review", pending: [{ kind: "approval", message: "审核" }],
  user_id: "U1001", user_input: "我要投诉", final_response: "等待审核", need_human: true,
  intent: "complaint", intent_confidence: 0.9, intent_reason: "投诉", order_id: null,
  tool_results: {}, retrieved_docs: [], steps: [], latency_ms: 10,
};
async function flush() { await new Promise(resolve => setTimeout(resolve, 0)); await nextTick(); }
function button(text: string) { return Array.from(container.querySelectorAll("button")).find(item => item.textContent?.includes(text))!; }

beforeEach(() => {
  vi.mocked(supportApi.health).mockResolvedValue({ status: "ok", service: "test" });
  vi.mocked(supportApi.history).mockResolvedValue([{ ...pending, created_at: "now" }] as never);
  vi.mocked(supportApi.get).mockResolvedValue(pending as never);
  vi.mocked(supportApi.reviews).mockResolvedValue([]);
  container = document.createElement("div"); document.body.appendChild(container);
});
afterEach(() => { app.unmount(); container.remove(); vi.clearAllMocks(); });

it("lets a reviewer reopen a persisted run and approve it", async () => {
  vi.mocked(supportApi.me).mockResolvedValue({ user_id: "S1001", role: "support" });
  vi.mocked(supportApi.review).mockResolvedValue({ ...pending, status: "completed", final_response: "已创建工单" } as never);
  app = createApp(App); app.mount(container); await flush();
  button("打开处理").click(); await flush();
  button("通过并创建工单").click(); await flush();
  expect(supportApi.review).toHaveBeenCalledWith("run-1", true, "");
  expect(container.textContent).toContain("已创建工单");
});

it("does not present approval controls to a customer", async () => {
  vi.mocked(supportApi.me).mockResolvedValue({ user_id: "U1001", role: "customer" });
  app = createApp(App); app.mount(container); await flush();
  button("打开处理").click(); await flush();
  expect(container.textContent).not.toContain("通过并创建工单");
  expect((container.querySelector("#user-id") as HTMLInputElement).disabled).toBe(true);
});

it("requires confirmation before rejecting a request", async () => {
  vi.mocked(supportApi.me).mockResolvedValue({ user_id: "S1001", role: "support" });
  vi.mocked(supportApi.review).mockResolvedValue({ ...pending, status: "completed", final_response: "未创建工单" } as never);
  app = createApp(App); app.mount(container); await flush();
  button("打开处理").click(); await flush();
  button("拒绝").click(); await flush();
  expect(supportApi.review).not.toHaveBeenCalled();
  button("确认拒绝").click(); await flush();
  expect(supportApi.review).toHaveBeenCalledWith("run-1", false, "");
  expect(container.textContent).toContain("未创建工单");
});

it("preserves the review queue when recent history fails", async () => {
  vi.mocked(supportApi.me).mockResolvedValue({ user_id: "S1001", role: "support" });
  vi.mocked(supportApi.history).mockRejectedValueOnce(new Error("offline"));
  vi.mocked(supportApi.reviews).mockResolvedValue([{ ...pending, created_at: "now" }] as never);
  app = createApp(App); app.mount(container); await flush();
  expect(container.textContent).toContain("记录加载失败，请刷新重试。");
  expect(container.querySelector("#review-queue")?.textContent).toContain("我要投诉");
});
