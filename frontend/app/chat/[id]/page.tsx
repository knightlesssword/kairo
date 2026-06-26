"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useParams } from "next/navigation";

import { fetchMe, getConversation, sendMessage, type Me, type Message } from "@/lib/api";
import { readSSEStream, type AnimeCard } from "@/lib/stream";
import MessageList, { type ChatMessage } from "@/components/chat/message-list";
import MessageInput from "@/components/chat/message-input";
import ReconnectBanner from "@/components/reconnect-banner";
import SyncStatus from "@/components/sync-status";
import ConversationList from "@/components/sidebar/conversation-list";
import KairoLogo from "@/components/kairo-logo";

export default function ConversationPage() {
  const router = useRouter();
  const params = useParams();
  const conversationId = params.id as string;

  const [me, setMe] = useState<Me | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [loading, setLoading] = useState(true);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);

    Promise.all([fetchMe(), getConversation(conversationId)])
      .then(([user, conv]) => {
        if (!active) return;
        if (!user) {
          router.replace("/login");
          return;
        }
        setMe(user);
        setMessages(
          conv.messages.map((m: Message) => ({
            id: m.id,
            role: m.role,
            content: m.content,
          }))
        );
        setLoading(false);
      })
      .catch(() => {
        if (active) router.replace("/chat");
      });

    return () => {
      active = false;
    };
  }, [conversationId, router]);

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
        const response = await sendMessage(conversationId, content);

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
      } catch (err) {
        if (!abort.signal.aborted) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? { ...m, content: "connection error", streaming: false }
                : m
            )
          );
        }
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
        <ConversationList me={me} />
        <div className="flex flex-1 flex-col overflow-hidden">
          {me && (
            <SyncStatus
              me={me}
              onSyncComplete={(updated) => setMe(updated)}
            />
          )}
          <MessageList messages={messages} />
          <MessageInput onSend={handleSend} disabled={streaming} />
        </div>
      </div>
    </div>
  );
}
