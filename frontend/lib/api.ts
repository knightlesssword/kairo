// typed client for the kairo backend.
// all requests send the session cookie (credentials: "include"); the backend is a
// different origin (port) but the same site, so the samesite=lax session cookie flows.

// exported so error UI can name the backend it failed to reach.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// HTTP failures carry their status so pages can tell "logged out" (401) apart
// from "backend broken/unreachable" (anything else, incl. network TypeErrors
// which never become ApiError). messages keep the old "{route} failed: {n}"
// shape so existing catch sites reading e.message are unaffected.
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function isUnauthorized(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}

export interface Me {
  id: string;
  username: string;
  anilist_id: number;
  anilist_connected: boolean;
  last_synced_at: string | null;
}

// full-navigation target: hits the backend, which 302s to AniList and sets the state cookie.
export function anilistLoginUrl(): string {
  return `${API_BASE}/auth/anilist/login`;
}

// returns the current user, or null when unauthenticated (401).
export async function fetchMe(): Promise<Me | null> {
  const res = await fetch(`${API_BASE}/auth/me`, { credentials: "include" });
  if (res.status === 401) return null;
  if (!res.ok) throw new ApiError(`/auth/me failed: ${res.status}`, res.status);
  return (await res.json()) as Me;
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, { method: "POST", credentials: "include" });
}

export interface SyncJob {
  job_id: string;
  status: "pending" | "running" | "completed" | "failed";
  error?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export async function postSync(): Promise<SyncJob> {
  const res = await fetch(`${API_BASE}/profile/sync`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) throw new ApiError(`/profile/sync failed: ${res.status}`, res.status);
  return (await res.json()) as SyncJob;
}

export async function getSyncJob(jobId: string): Promise<SyncJob> {
  const res = await fetch(`${API_BASE}/profile/sync/${jobId}`, {
    credentials: "include",
  });
  if (!res.ok) throw new ApiError(`/profile/sync/${jobId} failed: ${res.status}`, res.status);
  return (await res.json()) as SyncJob;
}

// ---------------------------------------------------------------------------
// conversations
// ---------------------------------------------------------------------------

export interface Conversation {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface ConversationList {
  items: Conversation[];
  next_cursor: string | null;
}

export async function createConversation(): Promise<Conversation> {
  const res = await fetch(`${API_BASE}/conversations`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) throw new ApiError(`/conversations POST failed: ${res.status}`, res.status);
  return (await res.json()) as Conversation;
}

export async function listConversations(cursor?: string): Promise<ConversationList> {
  const url = cursor
    ? `${API_BASE}/conversations?cursor=${encodeURIComponent(cursor)}`
    : `${API_BASE}/conversations`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new ApiError(`/conversations GET failed: ${res.status}`, res.status);
  return (await res.json()) as ConversationList;
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const res = await fetch(`${API_BASE}/conversations/${id}`, {
    credentials: "include",
  });
  if (!res.ok) throw new ApiError(`/conversations/${id} failed: ${res.status}`, res.status);
  return (await res.json()) as ConversationDetail;
}

export async function deleteConversation(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/conversations/${id}`, {
    method: "DELETE",
    credentials: "include",
  });
  // throw on non-2xx so callers never treat a failed delete as success
  // (backend answers 204 on success, 403/404 on wrong user or missing id).
  if (!res.ok) throw new ApiError(`/conversations/${id} DELETE failed: ${res.status}`, res.status);
}

// returns the fetch Response so callers can read the SSE body as a stream.
// pass an AbortSignal to genuinely cancel the request (stop button, unmount).
export function sendMessage(
  conversationId: string,
  content: string,
  signal?: AbortSignal,
): Promise<Response> {
  return fetch(`${API_BASE}/conversations/${conversationId}/messages`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
    signal,
  });
}
