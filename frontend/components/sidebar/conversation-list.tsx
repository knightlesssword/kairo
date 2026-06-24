"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  createConversation,
  listConversations,
  type Conversation,
} from "@/lib/api";

interface Props {
  onNewConversation?: (conv: Conversation) => void;
}

export default function ConversationList({ onNewConversation }: Props) {
  const pathname = usePathname();
  const [items, setItems] = useState<Conversation[]>([]);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    listConversations()
      .then((r) => setItems(r.items))
      .catch(() => {});
  }, []);

  async function handleNew() {
    if (creating) return;
    setCreating(true);
    try {
      const conv = await createConversation();
      setItems((prev) => [conv, ...prev]);
      onNewConversation?.(conv);
    } finally {
      setCreating(false);
    }
  }

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="p-3">
        <button
          onClick={handleNew}
          disabled={creating}
          className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-left text-sm text-zinc-700 transition-colors hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
        >
          + new chat
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 pb-4">
        {items.length === 0 ? (
          <p className="px-2 py-3 text-xs text-zinc-400">no conversations yet</p>
        ) : (
          items.map((conv) => {
            const isActive = pathname === `/chat/${conv.id}`;
            return (
              <Link
                key={conv.id}
                href={`/chat/${conv.id}`}
                className={`block truncate rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? "bg-zinc-200 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
                    : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
                }`}
              >
                {conv.title ?? "new conversation"}
              </Link>
            );
          })
        )}
      </nav>
    </aside>
  );
}
