"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
  API_BASE,
  createConversation,
  fetchMe,
  isUnauthorized,
  listConversations,
} from "@/lib/api";
import KairoLogo from "@/components/kairo-logo";

function backendDownMessage(): string {
  return `cannot reach the kairo backend at ${API_BASE} — is it running?`;
}

export default function ChatPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let active = true;

    async function redirect() {
      // auth check first: only an explicit 401 (null user) means "logged out".
      // a throw here is network/5xx -> backend unreachable, not a logout.
      let user;
      try {
        user = await fetchMe();
      } catch {
        if (active) setError(backendDownMessage());
        return;
      }
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
      } catch (err) {
        // session died mid-flow -> login; anything else is backend trouble.
        if (!active) return;
        if (isUnauthorized(err)) {
          router.replace("/login");
          return;
        }
        try {
          const conv = await createConversation();
          if (active) router.replace(`/chat/${conv.id}`);
        } catch (retryErr) {
          if (!active) return;
          if (isUnauthorized(retryErr)) router.replace("/login");
          else setError(backendDownMessage());
        }
      }
    }

    redirect().catch(() => {
      if (active) setError(backendDownMessage());
    });

    return () => {
      active = false;
    };
  }, [router, retryKey]);

  if (error) {
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
            {error}
          </span>
          <button
            onClick={() => {
              setError(null);
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
