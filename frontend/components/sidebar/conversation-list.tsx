"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import {
  createConversation,
  deleteConversation,
  listConversations,
  logout,
  type Conversation,
  type Me,
} from "@/lib/api";

interface Props {
  me?: Me | null;
  isOpen?: boolean;
  onNewConversation?: (conv: Conversation) => void;
}

export default function ConversationList({ me, isOpen = true, onNewConversation }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const [items, setItems] = useState<Conversation[]>([]);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [loggingOut, setLoggingOut] = useState(false);

  // re-fetch on pathname changes so backend-set titles appear after first message
  useEffect(() => {
    listConversations()
      .then((r) => setItems(r.items))
      .catch(() => {});
  }, [pathname]);

  async function handleNew() {
    if (creating) return;
    setCreating(true);
    try {
      const conv = await createConversation();
      setItems((prev) => [conv, ...prev]);
      onNewConversation?.(conv);
      router.push(`/chat/${conv.id}`);
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(e: React.MouseEvent, convId: string) {
    e.preventDefault();
    e.stopPropagation();
    if (deletingId) return;
    setDeletingId(convId);

    // capture remaining BEFORE the state update to avoid stale closure in the redirect branch
    const remainingAfterDelete = items.filter((c) => c.id !== convId);

    try {
      await deleteConversation(convId);
      setItems(remainingAfterDelete);

      if (pathname === `/chat/${convId}`) {
        if (remainingAfterDelete.length > 0) {
          router.replace(`/chat/${remainingAfterDelete[0].id}`);
        } else {
          const fresh = await createConversation();
          setItems([fresh]);
          router.replace(`/chat/${fresh.id}`);
        }
      }
    } catch {
      // restore on failure
      setItems((prev) => {
        const already = prev.find((c) => c.id === convId);
        return already ? prev : items;
      });
    } finally {
      setDeletingId(null);
    }
  }

  async function handleLogout() {
    if (loggingOut) return;
    setLoggingOut(true);
    try {
      await logout();
    } finally {
      router.replace("/login");
    }
  }

  return (
    <aside
      className="flex shrink-0 flex-col border-r border-border bg-surface overflow-hidden transition-all duration-300"
      style={{ width: isOpen ? "256px" : "0px", opacity: isOpen ? 1 : 0 }}
    >

      {/* Profile header */}
      {me && (
        <div className="flex items-center gap-3 px-4 py-4 border-b border-border shrink-0">
          <div
            className="h-9 w-9 rounded-full flex items-center justify-center shrink-0 text-white font-bold text-sm uppercase"
            style={{
              background: "linear-gradient(135deg, #8B5CF6, #EC4899)",
              boxShadow: "0 0 12px rgba(139,92,246,0.4)",
            }}
          >
            {me.username[0]}
          </div>
          <div className="flex flex-col min-w-0">
            <span
              className="text-sm font-medium text-text truncate"
              style={{ fontFamily: "var(--font-noto), sans-serif" }}
            >
              {me.username}
            </span>
            <span
              className="text-xs"
              style={{ color: me.anilist_connected ? "var(--color-cyan)" : "var(--color-danger)" }}
            >
              {me.anilist_connected ? "● connected" : "● disconnected"}
            </span>
          </div>
        </div>
      )}

      {/* New conversation */}
      <div className="p-3 shrink-0">
        <button
          onClick={handleNew}
          disabled={creating}
          className="w-full rounded-lg border border-border bg-surface-2
                     px-3 py-2 text-left text-sm text-text-dim
                     hover:border-border-glow hover:text-text
                     disabled:opacity-40 transition-all duration-200
                     flex items-center gap-2"
          style={{
            fontFamily: "var(--font-noto), sans-serif",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.background = "rgba(139,92,246,0.08)";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.background = "";
          }}
        >
          <span className="text-primary font-bold text-base leading-none">+</span>
          {creating ? "creating…" : "new conversation"}
        </button>
      </div>

      {/* Conversation list */}
      <nav className="flex-1 overflow-y-auto px-2 pb-2 space-y-0.5">
        {items.length === 0 ? (
          <p
            className="px-3 py-3 text-xs text-text-muted italic"
            style={{ fontFamily: "var(--font-noto), sans-serif" }}
          >
            no conversations yet
          </p>
        ) : (
          items.map((conv) => {
            const isActive = pathname === `/chat/${conv.id}`;
            const isDeleting = deletingId === conv.id;
            return (
              <div key={conv.id} className="group relative flex items-center">
                <Link
                  href={`/chat/${conv.id}`}
                  className={`
                    flex-1 min-w-0 truncate rounded-lg px-3 py-2.5 text-sm transition-all duration-150
                    ${isActive
                      ? "bg-surface-2 text-text border-l-2 pl-[10px]"
                      : "text-text-dim hover:text-text border-l-2 border-transparent pl-[10px]"
                    }
                  `}
                  style={{
                    fontFamily: "var(--font-noto), sans-serif",
                    borderLeftColor: isActive ? "var(--color-primary)" : undefined,
                    boxShadow: isActive ? "inset 0 0 12px rgba(139,92,246,0.08)" : undefined,
                    background: isActive ? undefined : undefined,
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) (e.currentTarget as HTMLElement).style.background = "rgba(139,92,246,0.06)";
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) (e.currentTarget as HTMLElement).style.background = "";
                  }}
                >
                  {conv.title ?? "new conversation"}
                </Link>

                {/* Delete button — visible on group hover */}
                <button
                  onClick={(e) => handleDelete(e, conv.id)}
                  disabled={isDeleting}
                  aria-label="delete conversation"
                  className="absolute right-1 hidden group-hover:flex h-6 w-6 shrink-0
                             items-center justify-center rounded text-text-muted
                             hover:text-danger hover:bg-danger-dim transition-all duration-150
                             disabled:opacity-40"
                  title="delete"
                >
                  {isDeleting ? (
                    <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10" strokeOpacity="0.3" />
                      <path d="M12 2a10 10 0 0 1 10 10" />
                    </svg>
                  ) : (
                    <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                      <path d="M18 6 6 18M6 6l12 12" />
                    </svg>
                  )}
                </button>
              </div>
            );
          })
        )}
      </nav>

      {/* Sidebar footer — logout */}
      <div className="shrink-0 border-t border-border p-3">
        <button
          onClick={handleLogout}
          disabled={loggingOut}
          className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-text-muted
                     hover:text-danger hover:bg-danger-dim transition-all duration-200
                     disabled:opacity-40"
          style={{ fontFamily: "var(--font-noto), sans-serif" }}
        >
          <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
          {loggingOut ? "signing out…" : "sign out"}
        </button>
      </div>
    </aside>
  );
}
