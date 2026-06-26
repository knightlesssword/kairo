"use client";

import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { AnimeCard } from "@/lib/stream";
import AnimeCardComponent from "@/components/chat/anime-card";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  animeCards?: AnimeCard[];
  streaming?: boolean;
}

interface Props {
  messages: ChatMessage[];
}

function StreamCursor() {
  return (
    <span className="inline-flex items-center gap-1 ml-0.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="inline-block h-1.5 w-1.5 rounded-full bg-cyan"
          style={{
            animation: "stream-blink 1s ease-in-out infinite",
            animationDelay: `${i * 0.2}s`,
          }}
        />
      ))}
    </span>
  );
}

export default function MessageList({ messages }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center bg-void">
        <div
          className="flex flex-col items-center gap-4 text-center"
          style={{ animation: "fade-up 400ms ease both" }}
        >
          <div
            className="text-4xl select-none"
            style={{ color: "var(--color-primary)", opacity: 0.4 }}
          >
            カ
          </div>
          <p
            className="text-text-dim text-sm tracking-widest uppercase"
            style={{ fontFamily: "var(--font-cinzel), serif" }}
          >
            what should we watch next?
          </p>
          <p
            className="text-xs text-text-muted max-w-[220px]"
            style={{ fontFamily: "var(--font-noto), sans-serif" }}
          >
            ask about your list, get recommendations, or just talk anime.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto px-6 py-6 bg-void">
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
        >
          {msg.role === "user" ? (
            <div
              className="max-w-[72%] rounded-2xl rounded-tr-sm px-4 py-3 text-sm text-white whitespace-pre-wrap"
              style={{
                background: "linear-gradient(135deg, #EC4899, #8B5CF6)",
                boxShadow: "0 2px 12px rgba(236,72,153,0.25)",
                fontFamily: "var(--font-noto), sans-serif",
              }}
            >
              {msg.content}
            </div>
          ) : (
            <div className="flex gap-3 max-w-[85%]">
              {/* Avatar dot */}
              <div
                className="h-6 w-6 shrink-0 mt-0.5 rounded-full flex items-center justify-center text-[10px] font-bold text-white"
                style={{
                  background: "linear-gradient(135deg, #8B5CF6, #06B6D4)",
                  boxShadow: "0 0 8px rgba(139,92,246,0.5)",
                  fontFamily: "serif",
                }}
              >
                カ
              </div>

              {/* Message content */}
              <div className="flex flex-col gap-2 min-w-0">
                <div className="kairo-prose text-sm">
                  {msg.content ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content}
                    </ReactMarkdown>
                  ) : msg.streaming ? (
                    <StreamCursor />
                  ) : null}
                  {msg.streaming && msg.content && <StreamCursor />}
                </div>
                {msg.animeCards?.map((anime) => (
                  <AnimeCardComponent key={anime.id} anime={anime} />
                ))}
              </div>
            </div>
          )}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
