"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { createConversation, fetchMe, listConversations } from "@/lib/api";
import KairoLogo from "@/components/kairo-logo";

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
