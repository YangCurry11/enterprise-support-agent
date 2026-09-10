import type { AgentHistoryItem, AgentResult, Health } from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError("无法连接后端，请先启动 FastAPI 服务。", 0);
  }
  if (!response.ok) {
    let message = `请求失败（HTTP ${response.status}）`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the HTTP fallback for non-JSON errors.
    }
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

export const supportApi = {
  health: () => request<Health>("/"),
  run: (userInput: string, userId: string) => request<AgentResult>("/agent/run", {
    method: "POST",
    body: JSON.stringify({ user_input: userInput, user_id: userId }),
  }),
  history: async (limit = 10) =>
    (await request<{ runs: AgentHistoryItem[] }>(`/agent/runs?limit=${limit}`)).runs,
};
