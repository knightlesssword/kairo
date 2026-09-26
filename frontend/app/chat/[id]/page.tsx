"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useParams } from "next/navigation";

import { API_BASE, ApiError, createConversation, fetchMe, getConversation, isUnauthorized, sendMessage, type Me, type Message } from "@/lib/api";
import { readSSEStream, type AnimeCard } from "@/lib/stream";
import MessageList, { type ChatMessage } from "@/components/chat/message-list";
import MessageInput from "@/components/chat/message-input";
import ReconnectBanner from "@/components/reconnect-banner";
import SyncStatus from "@/components/sync-status";
import ConversationList from "@/components/sidebar/conversation-list";
import ChatTopbar from "@/components/chat/chat-topbar";
import KairoLogo from "@/components/kairo-logo";

const SIDEBAR_KEY = "kairo:sidebar-open";

function readSidebarPref(): boolean {
  try {
    const v = localStorage.getItem(SIDEBAR_KEY);
    return v === null ? true : v === "true";
  } catch {
    return true;
  }
}

export default function ConversationPage() {
  const router = useRouter();
  const params = useParams();
  const conversationId = params.id as string;

  const [me, setMe] = useState<Me | null>(null);
  const [convTitle, setConvTitle] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [creating, setCreating] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // read sidebar pref from localStorage after mount (avoids SSR mismatch)
  useEffect(() => {
    setSidebarOpen(readSidebarPref());
  }, []);

  // Ctrl+B / Cmd+B keyboard shortcut to toggle sidebar
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === "b") {
        e.preventDefault();
        setSidebarOpen((prev) => {
          const next = !prev;
          try { localStorage.setItem(SIDEBAR_KEY, String(next)); } catch {}
          return next;
        });
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function toggleSidebar() {
    setSidebarOpen((prev) => {
      const next = !prev;
      try { localStorage.setItem(SIDEBAR_KEY, String(next)); } catch {}
      return next;
    });
  }

  useEffect(() => {
    let active = true;
    setLoading(true);
    setConvTitle(null);

    // auth first, then conversation: only an explicit 401 means "logged out".
    // anything else (network/5xx) is backend trouble -> error UI, not /login.
    // a missing/forbidden conversation (403/404) still routes to /chat.
    async function load() {
      let user;
      try {
        user = await fetchMe();
      } catch {
        if (!active) return;
        setLoadError(`cannot reach the kairo backend at ${API_BASE} — is it running?`);
        setLoading(false);
        return;
      }
      if (!active) return;
      if (!user) {
        router.replace("/login");
        return;
      }

      let conv;
      try {
        conv = await getConversation(conversationId);
      } catch (err) {
        if (!active) return;
        if (isUnauthorized(err)) {
          router.replace("/login");
          return;
        }
        if (err instanceof ApiError && (err.status === 403 || err.status === 404)) {
          router.replace("/chat");
          return;
        }
        setLoadError(`cannot reach the kairo backend at ${API_BASE} — is it running?`);
        setLoading(false);
        return;
      }
      if (!active) return;
      setMe(user);
      setConvTitle(conv.title);
      setMessages(
        conv.messages.map((m: Message) => ({
          id: m.id,
          role: m.role,
          content: m.content,
        }))
      );
      setLoading(false);
    }

    load().catch(() => {
      if (active) {
        setLoadError(`cannot reach the kairo backend at ${API_BASE} — is it running?`);
        setLoading(false);
      }
    });

    return () => {
      active = false;
    };
  }, [conversationId, router, retryKey]);

  const handleNewConversation = useCallback(async () => {
    if (creating) return;
    setCreating(true);
    try {
      const conv = await createConversation();
      router.push(`/chat/${conv.id}`);
    } finally {
      setCreating(false);
    }
  }, [creating, router]);

  const handleSend = useCallback(
    async (content: string) => {
      if (streaming) return;

      const userMsgId = `local-user-${Date.now()}`;
      const assistantMsgId = `local-assistant-${Date.now()}`;

      setMessages((prev) => [
        ...prev,
        { id: userMsgId, role: "user", content },
        { id: assistantMsgId, role: "assistant", content: "", streaming: true, animeCards: [] },
      ]);
      setStreaming(true);

      const abort = new AbortController();
      abortRef.current = abort;

      try {
        const response = await sendMessage(conversationId, content, abort.signal);

        await readSSEStream(
          response,
          {
            onDelta: (delta) => {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId ? { ...m, content: m.content + delta } : m
                )
              );
            },
            onAnimeCard: (anime: AnimeCard) => {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, animeCards: [...(m.animeCards ?? []), anime] }
                    : m
                )
              );
            },
            onDone: () => {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId ? { ...m, streaming: false } : m
                )
              );
            },
            onError: (msg) => {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, content: `error: ${msg}`, streaming: false }
                    : m
                )
              );
            },
          },
          abort.signal,
        );

        // stop (or unmount) resolves the reader without done/error: settle the
        // cursor so it does not spin forever on the partial message.
        if (abort.signal.aborted) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, streaming: false } : m
            )
          );
        }
      } catch {
        // aborted fetch rejects: settle the cursor with no error text (the
        // user stopped it); real failures still show "connection error".
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? abort.signal.aborted
                ? { ...m, streaming: false }
                : { ...m, content: "connection error", streaming: false }
              : m
          )
        );
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [conversationId, streaming]
  );

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  if (loadError) {
    return (
      <div className="flex h-screen items-center justify-center bg-void">
        <div
          className="flex flex-col items-center gap-4 text-center px-6"
          style={{ animation: "fade-in 400ms ease both" }}
        >
          <KairoLogo size={56} />
          <span
            className="text-sm text-text-dim max-w-sm"
            style={{ fontFamily: "var(--font-noto), sans-serif" }}
          >
            {loadError}
          </span>
          <button
            onClick={() => {
              setLoadError(null);
              setRetryKey((k) => k + 1);
            }}
            className="mt-1 h-10 rounded-full px-6 font-medium text-white text-sm cursor-pointer
                       transition-all duration-200"
            style={{
              background: "linear-gradient(135deg, #EC4899, #8B5CF6)",
              fontFamily: "var(--font-noto), sans-serif",
            }}
          >
            retry
          </button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-void">
        <div
          className="flex flex-col items-center gap-4"
          style={{ animation: "fade-in 400ms ease both" }}
        >
          <div style={{ animation: "spin-slow 8s linear infinite" }}>
            <KairoLogo size={56} />
          </div>
          <span
            className="text-xs tracking-[0.3em] text-text-dim uppercase"
            style={{ fontFamily: "var(--font-cinzel), serif" }}
          >
            loading
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-void">
      {me && !me.anilist_connected && <ReconnectBanner />}
      <div className="flex flex-1 overflow-hidden">
        <ConversationList me={me} isOpen={sidebarOpen} />
        <div className="flex flex-1 flex-col overflow-hidden">
          <ChatTopbar
            title={convTitle}
            sidebarOpen={sidebarOpen}
            onToggleSidebar={toggleSidebar}
            onNewConversation={handleNewConversation}
            creating={creating}
          />
          {me && (
            <SyncStatus
              me={me}
              onSyncComplete={(updated) => setMe(updated)}
            />
          )}
          <MessageList messages={messages} />
          <MessageInput onSend={handleSend} onStop={handleStop} disabled={streaming} />
        </div>
      </div>
    </div>
  );
}
