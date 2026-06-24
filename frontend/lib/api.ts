// typed client for the kairo backend.
// all requests send the session cookie (credentials: "include"); the backend is a
// different origin (port) but the same site, so the samesite=lax session cookie flows.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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
  if (!res.ok) throw new Error(`/auth/me failed: ${res.status}`);
  return (await res.json()) as Me;
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, { method: "POST", credentials: "include" });
}
