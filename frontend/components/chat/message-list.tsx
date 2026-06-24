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
  // anime cards attached to this message (populated from SSE events)
  animeCards?: AnimeCard[];
  // true while the assistant is streaming this message
  streaming?: boolean;
}

interface Props {
  messages: ChatMessage[];
}

export default function MessageList({ messages }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-zinc-400 text-sm">
        ask anything about your anime taste
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-6 overflow-y-auto px-4 py-6">
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
        >
          <div
            className={`max-w-[75%] ${
              msg.role === "user"
                ? "rounded-2xl rounded-tr-sm bg-zinc-900 px-4 py-3 text-sm text-white dark:bg-zinc-100 dark:text-zinc-900"
                : "flex flex-col gap-2"
            }`}
          >
            {msg.role === "user" ? (
              <span className="whitespace-pre-wrap">{msg.content}</span>
            ) : (
              <>
                <div className="prose prose-sm dark:prose-invert max-w-none text-zinc-800 dark:text-zinc-200">
                  {msg.content ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  ) : msg.streaming ? (
                    <span className="animate-pulse text-zinc-400">▍</span>
                  ) : null}
                </div>
                {msg.animeCards?.map((anime) => (
                  <AnimeCardComponent key={anime.id} anime={anime} />
                ))}
              </>
            )}
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
