export interface AgentStep {
  name: string;
  detail: Record<string, unknown>;
}

export interface RetrievedDocument {
  source: string;
  text: string;
  score?: number;
  score_type?: "tfidf_cosine" | "dense_cosine" | "rrf";
  retrieval_mode?: "tfidf" | "dense" | "hybrid";
  chunk_id?: string;
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
  tool_calling_trace?: ToolCallingTrace;
}

export interface ToolAttempt {
  run_id: string; tool: string; tool_call_id: string;
  parameters_checked?: boolean; parameters_valid: boolean; allowed: boolean;
  executed: boolean; success: boolean; permission_blocked: boolean;
  error_type: string | null; latency_ms: number; cached: boolean;
}
export interface ToolCallingTrace {
  enabled?: boolean; status?: string; tools?: ToolAttempt[];
  tool_call_count?: number; tool_execution_count?: number; fallback_tool_execution_count?: number;
  rounds?: number; fallback_used?: boolean; error_type?: string | null;
  fallback_error_type?: string;
  model_calls?: { actual_model_calls: number; max_model_calls: number; simulated?: boolean;
    token_usage?: { input_tokens: number; output_tokens: number; total_tokens: number } | null;
    usage_complete?: boolean };
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

export interface Conversation {
  conversation_id: string; owner_user_id: string; title: string;
  created_at: string; updated_at: string; last_message_at: string | null;
  status: string; verified_order_id: string | null;
}
export interface ConversationMessage {
  sequence: number; message_id: string; conversation_id: string; run_id: string | null;
  role: "user" | "assistant" | "system"; content: string; status: string; created_at: string;
  metadata: { result?: AgentResult; request_id?: string };
}
export interface MessagePage { messages: ConversationMessage[]; next_before: number | null }
export interface ChatResult extends AgentResult {
  conversation_id: string; message_id: string; assistant_message_id: string;
}
export interface EvaluationReport {
  generated_at: string; mode: string; data_provenance: string;
  intent: { metrics: { accuracy: number; macro_f1: number; per_class: Record<string, { precision: number; recall: number; f1: number }> }; cases: EvaluationCase[] };
  rag: { metrics: { recall_at_1: number; recall_at_3: number; recall_at_5: number; mrr: number; mean_ms?: number }; cases: EvaluationCase[] };
  workflow: { metrics: { passed: number; sample_count: number; pass_rate: number; timing: { mean_ms: number; p95_ms: number }; tool_success_rate?: number; model_fallback_rate?: number }; cases: EvaluationCase[] };
}
export interface EvaluationCase {
  id: string; passed: boolean; [key: string]: unknown;
}
