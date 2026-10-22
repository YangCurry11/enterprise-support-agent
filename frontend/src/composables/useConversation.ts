import { computed, ref } from "vue";
import { ApiError, setCredential, supportApi } from "../api";
import type { AgentResult, Conversation, ConversationMessage, Identity } from "../types";

/** Conversation state is UI-scoped. Only the selected ID (not transcripts or credentials) survives refresh. */
export function useConversation() {
  const token = ref(import.meta.env.DEV ? "dev-customer-u1001" : "");
  const identity = ref<Identity | null>(null);
  const conversations = ref<Conversation[]>([]);
  const current = ref<Conversation | null>(null);
  const messages = ref<ConversationMessage[]>([]);
  const result = ref<AgentResult | null>(null);
  const error = ref("");
  const busy = ref(false), authenticating = ref(false), loading = ref(false);
  const moreConversations = ref(false), before = ref<number | null>(null);
  const owner = ref("U1001");
  const pending = ref<{ conversation: string; content: string; key: string } | null>(null);
  let epoch = 0, selection = 0;
  const selectedKey = () => `serviceflow:conversation:${identity.value?.user_id}`;
  const remember = () => { try { if (current.value) localStorage.setItem(selectedKey(), current.value.conversation_id); } catch { /* Storage is optional. */ } };
  const canSend = computed(() => !!identity.value && !busy.value && !loading.value && !pending.value);
  const messageError = (cause: unknown) => cause instanceof Error ? cause.message : "操作失败，请重试。";

  async function list(append = false) {
    const generation = epoch;
    const rows = await supportApi.conversations(append ? conversations.value.length : 0);
    if (generation !== epoch) return;
    conversations.value = append ? [...conversations.value, ...rows.filter(row => !conversations.value.some(old => old.conversation_id === row.conversation_id))] : rows;
    moreConversations.value = rows.length === 30;
    if (current.value) current.value = conversations.value.find(row => row.conversation_id === current.value?.conversation_id) || current.value;
  }
  function restoreRetry() {
    const unfinished = messages.value.find(m => m.role === "user" && ["pending", "failed"].includes(m.status) && m.metadata.request_id);
    if (unfinished && current.value) pending.value = { conversation: current.value.conversation_id, content: unfinished.content, key: unfinished.metadata.request_id! };
  }
  async function select(id: string) {
    if (busy.value) return;
    const generation = epoch, selected = ++selection;
    current.value = null; messages.value = []; result.value = null; pending.value = null; before.value = null;
    loading.value = true; error.value = "";
    try {
      const [conversation, page] = await Promise.all([supportApi.conversation(id), supportApi.messages(id)]);
      if (generation !== epoch || selected !== selection) return;
      current.value = conversation; messages.value = page.messages; before.value = page.next_before;
      restoreRetry(); remember();
    } catch (cause) { if (generation === epoch && selected === selection) error.value = messageError(cause); }
    finally { if (generation === epoch && selected === selection) loading.value = false; }
  }
  async function authenticate() {
    const generation = ++epoch; ++selection;
    identity.value = null; current.value = null; conversations.value = []; messages.value = [];
    pending.value = null; result.value = null; before.value = null; busy.value = false; loading.value = false;
    error.value = ""; authenticating.value = true;
    setCredential(token.value);
    try {
      const account = await supportApi.me();
      if (generation !== epoch) return;
      identity.value = account;
      await list();
      if (generation !== epoch) return;
      let remembered: string | null = null;
      try { remembered = localStorage.getItem(selectedKey()); } catch { /* Optional. */ }
      if (remembered) await select(remembered);
    } catch (cause) { if (generation === epoch) error.value = messageError(cause); }
    finally { if (generation === epoch) authenticating.value = false; }
  }
  async function create() {
    if (!identity.value || busy.value || loading.value) return;
    const generation = epoch; loading.value = true; error.value = "";
    try {
      const conversation = await supportApi.createConversation(identity.value.role === "support" ? owner.value.trim() : undefined);
      if (generation !== epoch) return;
      ++selection; current.value = conversation; messages.value = []; before.value = null; pending.value = null; result.value = null;
      remember(); await list();
    } catch (cause) { if (generation === epoch) error.value = messageError(cause); }
    finally { if (generation === epoch) loading.value = false; }
  }
  async function refreshMessages() {
    const id = current.value?.conversation_id, generation = epoch, selected = selection;
    if (!id) return;
    const page = await supportApi.messages(id);
    if (generation !== epoch || selected !== selection) return;
    messages.value = page.messages; before.value = page.next_before; restoreRetry();
  }
  async function older() {
    if (!current.value || !before.value || loading.value) return;
    const id = current.value.conversation_id, generation = epoch, selected = selection;
    loading.value = true;
    try {
      const page = await supportApi.messages(id, before.value);
      if (generation !== epoch || selected !== selection) return;
      messages.value = [...page.messages.filter(m => !messages.value.some(old => old.message_id === m.message_id)), ...messages.value];
      before.value = page.next_before;
    } catch (cause) { if (generation === epoch) error.value = messageError(cause); }
    finally { if (generation === epoch && selected === selection) loading.value = false; }
  }
  async function dispatch() {
    if (!pending.value || busy.value) return;
    const request = { ...pending.value }, generation = epoch;
    busy.value = true; error.value = "";
    try {
      const answer = await supportApi.sendMessage(request.conversation, request.content, request.key);
      if (generation !== epoch) return false;
      pending.value = null; result.value = answer;
      await refreshMessages(); await list(); return true;
    } catch (cause) {
      if (generation !== epoch) return false;
      error.value = messageError(cause);
      // Validation/auth failures have no pending write. Network/server failures keep the original idempotency key.
      if (cause instanceof ApiError && cause.status >= 400 && cause.status < 500 && cause.status !== 409) pending.value = null;
      try { await refreshMessages(); } catch { /* Preserve the original request error and retry key. */ }
      return false;
    } finally { if (generation === epoch) busy.value = false; }
  }
  async function send(content: string) {
    if (!canSend.value || !content.trim()) return false;
    const generation = epoch;
    if (!current.value) await create();
    if (!current.value || generation !== epoch) return false;
    pending.value = { conversation: current.value.conversation_id, content: content.trim(), key: crypto.randomUUID() };
    return dispatch();
  }
  async function openRun(id: string) {
    const generation = epoch, selected = selection;
    try { const run = await supportApi.get(id); if (generation === epoch && selected === selection) result.value = run; }
    catch (cause) { if (generation === epoch) error.value = messageError(cause); }
  }
  async function act(action: "resume" | "approve" | "reject" | "recover", value = "") {
    if (!result.value || busy.value) return;
    const generation = epoch; busy.value = true; error.value = "";
    try {
      const id = result.value.run_id;
      const updated = action === "resume" ? await supportApi.resume(id, value.toUpperCase().trim()) : action === "recover" ? await supportApi.retry(id) : await supportApi.review(id, action === "approve", value);
      if (generation !== epoch) return;
      result.value = updated; await refreshMessages(); await list();
    } catch (cause) { if (generation === epoch) error.value = messageError(cause); }
    finally { if (generation === epoch) busy.value = false; }
  }
  async function refresh() {
    const generation = epoch;
    try { await refreshMessages(); await list(); if (generation === epoch && result.value) await openRun(result.value.run_id); }
    catch (cause) { if (generation === epoch) error.value = messageError(cause); }
  }
  async function loadMore() { try { await list(true); } catch (cause) { error.value = messageError(cause); } }
  return { token, identity, conversations, current, messages, result, error, busy, authenticating, loading, owner,
    pending, canSend, moreConversations, before, authenticate, create, select, send, retry: dispatch, refresh, older, loadMore, openRun, act };
}
