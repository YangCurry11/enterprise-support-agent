import type { AgentHistoryItem, AgentResult, Health, Identity, Conversation, MessagePage, ChatResult, EvaluationReport } from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
let credential = "";
export function setCredential(token: string) { credential = token.trim(); }

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (credential) headers.set("Authorization", `Bearer ${credential}`);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError("无法连接后端，请先启动 FastAPI 服务。", 0);
  }
  if (!response.ok) {
    let message = `请求失败（HTTP ${response.status}）`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = "请求参数不符合要求，请检查输入。";
    } catch {
      // Keep the HTTP fallback for non-JSON errors.
    }
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

export const supportApi = {
  createConversation: (owner?: string) => request<Conversation>("/agent/conversations", {
    method: "POST", body: JSON.stringify(owner ? { owner_user_id: owner } : {}),
  }),
  conversations: async (offset = 0) => (await request<{conversations: Conversation[]}>(`/agent/conversations?limit=30&offset=${offset}`)).conversations,
  conversation: (id: string) => request<Conversation>(`/agent/conversations/${encodeURIComponent(id)}`),
  messages: (id: string, before?: number) => request<MessagePage>(`/agent/conversations/${encodeURIComponent(id)}/messages?limit=50${before ? `&before=${before}` : ""}`),
  sendMessage: (id: string, content: string, key: string) => request<ChatResult>(`/agent/conversations/${encodeURIComponent(id)}/messages`, {
    method: "POST", body: JSON.stringify({ content, request_id: key }),
  }),
  evaluation: async () => (await request<{report: EvaluationReport | null}>("/agent/evaluations/latest")).report,
  health: () => request<Health>("/"),
  me: () => request<Identity>("/me"),
  run: (userInput: string, userId: string, requestId: string) => request<AgentResult>("/agent/run", {
    method: "POST",
    body: JSON.stringify({ user_input: userInput, user_id: userId, request_id: requestId }),
  }),
  history: async (limit = 10) =>
    (await request<{ runs: AgentHistoryItem[] }>(`/agent/runs?limit=${limit}`)).runs,
  reviews: async () => (await request<{ runs: AgentHistoryItem[] }>("/agent/reviews")).runs,
  get: (runId: string) => request<AgentResult>(`/agent/runs/${encodeURIComponent(runId)}`),
  retry: (runId: string) => request<AgentResult>(`/agent/runs/${encodeURIComponent(runId)}/retry`, { method: "POST" }),
  resume: (runId: string, orderId: string) => request<AgentResult>(`/agent/runs/${encodeURIComponent(runId)}/resume`, {
    method: "POST", body: JSON.stringify({ order_id: orderId }),
  }),
  review: (runId: string, approved: boolean, note: string) => request<AgentResult>(`/agent/runs/${encodeURIComponent(runId)}/review`, {
    method: "POST", body: JSON.stringify({ approved, note }),
  }),
};
