export interface AgentStep {
  name: string;
  detail: Record<string, unknown>;
}

export interface RetrievedDocument {
  source: string;
  text: string;
  score?: number;
}

export interface AgentResult {
  run_id: string;
  status: "running" | "failed" | "completed" | "awaiting_input" | "awaiting_review";
  pending: { kind: "order_id" | "approval"; message: string }[];
  user_id: string;
  user_input: string;
  intent: string;
  intent_confidence: number;
  intent_reason: string;
  order_id: string | null;
  tool_results: Record<string, unknown>;
  retrieved_docs: RetrievedDocument[];
  need_human: boolean;
  final_response: string;
  steps: AgentStep[];
  latency_ms: number;
  created_at?: string;
}

export interface Health {
  status: string;
  service: string;
}

export interface AgentHistoryItem {
  run_id: string;
  user_id: string;
  user_input: string;
  intent: string;
  order_id: string | null;
  need_human: boolean;
  final_response: string;
  steps: AgentStep[];
  tool_results: Record<string, unknown>;
  retrieved_docs: RetrievedDocument[];
  latency_ms: number;
  created_at: string;
  status: AgentResult["status"];
}

export interface Identity { user_id: string; role: "customer" | "support" }
