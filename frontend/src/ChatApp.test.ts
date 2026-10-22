import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createApp, nextTick, type App as VueApp } from "vue";
import App from "./App.vue";
import { ApiError, supportApi } from "./api";
import { useConversation } from "./composables/useConversation";
vi.mock("./api", () => ({
  ApiError: class ApiError extends Error { constructor(message: string, public status: number) { super(message); } },
  setCredential: vi.fn(),
  supportApi: { me: vi.fn(), conversations: vi.fn(), conversation: vi.fn(), messages: vi.fn(), createConversation: vi.fn(), sendMessage: vi.fn(), get: vi.fn(), resume: vi.fn(), retry: vi.fn(), review: vi.fn(), evaluation: vi.fn() },
}));
const conversation = { conversation_id: "c1", owner_user_id: "U1001", title: "订单问题", created_at: "2026-10-22T00:00:00Z", updated_at: "2026-10-22T00:00:00Z", last_message_at: null, status: "active", verified_order_id: null };
const run = { conversation_id: "c1", message_id: "u1", assistant_message_id: "a1", run_id: "r1", user_id: "U1001", user_input: "订单 ORD1001", status: "completed" as const, final_response: "订单已发货", pending: [], intent: "order_query", intent_confidence: 1, intent_reason: "规则", order_id: "ORD1001", tool_results: {}, retrieved_docs: [], steps: [], need_human: false, latency_ms: 5 };
let app: VueApp | undefined, host: HTMLDivElement;
async function flush() { for (let i = 0; i < 15; i++) await nextTick(); }
function button(text: string) { const found = [...host.querySelectorAll("button")].find(b => b.textContent?.includes(text)); expect(found, text).toBeTruthy(); return found!; }
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear();
  vi.mocked(supportApi.me).mockResolvedValue({user_id: "U1001", role: "customer"});
  vi.mocked(supportApi.conversations).mockResolvedValue([conversation]);
  vi.mocked(supportApi.conversation).mockResolvedValue(conversation);
  vi.mocked(supportApi.createConversation).mockResolvedValue(conversation);
  vi.mocked(supportApi.messages).mockResolvedValue({ messages: [], next_before: null });
  vi.mocked(supportApi.sendMessage).mockResolvedValue(run);
  host = document.createElement("div"); document.body.append(host);
});
afterEach(() => { app?.unmount(); app = undefined; host.remove(); });

it("creates and sends continuous chat, restores saved messages and hides customer approvals", async () => {
  app = createApp(App); app.mount(host); await flush();
  button("新建会话").click(); await flush();
  const input = host.querySelector<HTMLTextAreaElement>("#chat-input")!;
  input.value = "订单 ORD1001"; input.dispatchEvent(new Event("input")); await flush();
  vi.mocked(supportApi.messages).mockResolvedValue({ messages: [{sequence: 2, message_id: "a1", conversation_id: "c1", run_id: "r1", role: "assistant", content: "订单已发货", status: "completed", created_at: conversation.created_at, metadata: { result: run }}], next_before: null });
  input.dispatchEvent(new KeyboardEvent("keydown", {key: "Enter", bubbles: true})); await flush();
  expect(supportApi.sendMessage).toHaveBeenCalledTimes(1);
  expect(host.textContent).toContain("订单已发货");
  expect(host.textContent).not.toContain("通过并创建工单");
  expect(localStorage.getItem("serviceflow:conversation:U1001")).toBe("c1");
});

it("Shift+Enter and IME Enter never send", async () => {
  app = createApp(App); app.mount(host); await flush();
  const input = host.querySelector<HTMLTextAreaElement>("#chat-input")!;
  input.value = "问题"; input.dispatchEvent(new Event("input")); await flush();
  input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", shiftKey: true, bubbles: true }));
  input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", isComposing: true, bubbles: true })); await flush();
  expect(supportApi.sendMessage).not.toHaveBeenCalled();
});

it("retries a lost response with exactly the original request_id and prevents double sends", async () => {
  const chat = useConversation(); await chat.authenticate(); await chat.create();
  vi.mocked(supportApi.sendMessage).mockRejectedValueOnce(new ApiError("网络断开", 0));
  await chat.send("订单 ORD1001");
  const key = vi.mocked(supportApi.sendMessage).mock.calls[0]![2];
  expect(chat.pending.value?.key).toBe(key);
  expect(await chat.send("不应该发出第二条")).toBe(false);
  await chat.retry();
  expect(vi.mocked(supportApi.sendMessage).mock.calls[1]).toEqual(["c1", "订单 ORD1001", key]);
  expect(chat.pending.value).toBeNull();
});

it("drops late old-account responses and clears all conversation state on account switch", async () => {
  const chat = useConversation(); await chat.authenticate(); await chat.create();
  let resolve!: (value: typeof run) => void;
  vi.mocked(supportApi.sendMessage).mockImplementationOnce(() => new Promise(r => { resolve = r; }));
  const oldRequest = chat.send("订单 ORD1001"); await flush();
  vi.mocked(supportApi.me).mockResolvedValue({user_id: "U1002", role: "customer"});
  vi.mocked(supportApi.conversations).mockResolvedValue([]);
  chat.token.value = "other"; await chat.authenticate();
  resolve(run); await oldRequest;
  expect(chat.identity.value?.user_id).toBe("U1002");
  expect(chat.current.value).toBeNull(); expect(chat.messages.value).toEqual([]); expect(chat.result.value).toBeNull();
});

it("restores selected conversation after refresh and paginates older messages without duplicates", async () => {
  localStorage.setItem("serviceflow:conversation:U1001", "c1");
  const row = { sequence: 4, message_id: "u4", conversation_id: "c1", run_id: null, role: "user" as const, content: "较新", status: "completed", created_at: conversation.created_at, metadata: {} };
  vi.mocked(supportApi.messages).mockResolvedValueOnce({messages: [row], next_before: 4}).mockResolvedValueOnce({messages: [{...row, sequence: 2, message_id: "u2", content: "较早"}], next_before: null});
  const chat = useConversation(); await chat.authenticate(); await chat.older();
  expect(chat.messages.value.map(m => m.message_id)).toEqual(["u2", "u4"]);
  expect(supportApi.messages).toHaveBeenLastCalledWith("c1", 4);
});

it("recovers the retry key stored on failed messages after a browser refresh", async () => {
  localStorage.setItem("serviceflow:conversation:U1001", "c1");
  vi.mocked(supportApi.messages).mockResolvedValue({messages: [{sequence: 1, message_id: "u1", conversation_id: "c1", run_id: null, role: "user", content: "订单 ORD1001", status: "failed", created_at: conversation.created_at, metadata: {request_id: "original-key"}}], next_before: null});
  const chat = useConversation(); await chat.authenticate();
  expect(chat.pending.value?.key).toBe("original-key");
  await chat.retry(); expect(supportApi.sendMessage).toHaveBeenCalledWith("c1", "订单 ORD1001", "original-key");
});

it("authentication failure clears prior user data and disables sending", async () => {
  const chat = useConversation(); await chat.authenticate(); await chat.create();
  vi.mocked(supportApi.me).mockRejectedValue(new ApiError("访问凭证无效", 401));
  await chat.authenticate();
  expect(chat.identity.value).toBeNull(); expect(chat.messages.value).toEqual([]);
  expect(chat.canSend.value).toBe(false); expect(chat.error.value).toBe("访问凭证无效");
});

it("switches conversations without carrying the previous transcript or run", async () => {
  const chat = useConversation(); await chat.authenticate(); await chat.select("c1");
  await chat.send("订单 ORD1001"); expect(chat.result.value?.run_id).toBe("r1");
  vi.mocked(supportApi.conversation).mockResolvedValue({...conversation, conversation_id: "c2", title: "独立会话"});
  await chat.select("c2");
  expect(chat.current.value?.conversation_id).toBe("c2"); expect(chat.messages.value).toEqual([]); expect(chat.result.value).toBeNull();
});

it("shows a real pending review and its trace without granting customer approval controls", async () => {
  const pendingRun = {...run, status: "awaiting_review" as const, final_response: "等待客服审核", steps: [{name: "IntentAgent", detail: {intent: "after_sales"}}]};
  localStorage.setItem("serviceflow:conversation:U1001", "c1");
  vi.mocked(supportApi.messages).mockResolvedValue({messages: [{sequence: 2, message_id: "a1", conversation_id: "c1", run_id: "r1", role: "assistant", content: "等待客服审核", status: "awaiting_review", created_at: conversation.created_at, metadata: {result: pendingRun}}], next_before: null});
  vi.mocked(supportApi.get).mockResolvedValue(pendingRun);
  app = createApp(App); app.mount(host); await flush(); button("查看运行详情").click(); await flush();
  expect(host.textContent).toContain("IntentAgent"); expect(host.textContent).toContain("等待客服审核");
  expect(host.textContent).not.toContain("通过并创建工单");
});

it("reviewer evaluation page shows an honest empty state without invented metrics", async () => {
  vi.mocked(supportApi.me).mockResolvedValue({user_id: "S1001", role: "support"});
  vi.mocked(supportApi.evaluation).mockResolvedValue(null);
  app = createApp(App); app.mount(host); await flush(); button("Agent 评测").click(); await flush();
  expect(host.textContent).toContain("暂无评测数据"); expect(host.textContent).not.toContain("100%");
});

it("clears an unsent draft on both switching and creating conversations", async () => {
  const second = {...conversation, conversation_id: "c2", title: "第二会话"};
  vi.mocked(supportApi.conversations).mockResolvedValue([conversation, second]);
  vi.mocked(supportApi.conversation).mockImplementation(async id => id === "c2" ? second : conversation);
  vi.mocked(supportApi.createConversation).mockResolvedValue({...conversation, conversation_id: "c3", title: "新会话"});
  app = createApp(App); app.mount(host); await flush();
  button("订单问题").click(); await flush();
  let input = host.querySelector<HTMLTextAreaElement>("#chat-input")!;
  input.value = "不能发给另一客户的草稿"; input.dispatchEvent(new Event("input")); await flush();
  button("第二会话").click(); await flush();
  input = host.querySelector<HTMLTextAreaElement>("#chat-input")!; expect(input.value).toBe("");
  input.value = "新建前草稿"; input.dispatchEvent(new Event("input")); await flush();
  button("新建会话").click(); await flush();
  expect(host.querySelector<HTMLTextAreaElement>("#chat-input")!.value).toBe("");
});
