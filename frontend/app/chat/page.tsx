"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { createConversation, fetchMe, listConversations } from "@/lib/api";

// redirect to most recent conversation, or create a new one if none exist.
export default function ChatPage() {
  const router = useRouter();

  useEffect(() => {
    let active = true;

    async function redirect() {
      const user = await fetchMe();
      if (!active) return;
      if (!user) {
        router.replace("/login");
        return;
      }

      try {
        const list = await listConversations();
        if (!active) return;
        if (list.items.length > 0) {
          router.replace(`/chat/${list.items[0].id}`);
        } else {
          const conv = await createConversation();
          if (!active) return;
          router.replace(`/chat/${conv.id}`);
        }
      } catch {
        // if something fails, create a fresh conversation
        try {
          const conv = await createConversation();
          if (active) router.replace(`/chat/${conv.id}`);
        } catch {
          if (active) router.replace("/login");
        }
      }
    }

    redirect().catch(() => {
      if (active) router.replace("/login");
    });

    return () => {
      active = false;
    };
  }, [router]);

  return (
    <div className="flex h-screen items-center justify-center text-zinc-500 text-sm">
      loading…
    </div>
  );
}
