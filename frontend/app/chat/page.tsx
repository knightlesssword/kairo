"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { fetchMe, logout, type Me } from "@/lib/api";
import ReconnectBanner from "@/components/reconnect-banner";
import SyncStatus from "@/components/sync-status";

// phase 2: auth guard + sync trigger + freshness indicator.
// real chat ui lands in phase 3.
export default function ChatPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    fetchMe()
      .then((m) => {
        if (!active) return;
        if (!m) {
          router.replace("/login");
          return;
        }
        setMe(m);
        setLoading(false);
      })
      .catch(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [router]);

  if (loading) {
    return (
      <main className="flex flex-1 min-h-screen items-center justify-center text-zinc-500">
        loading…
      </main>
    );
  }
  if (!me) return null;

  return (
    <main className="flex flex-1 min-h-screen flex-col">
      {!me.anilist_connected && <ReconnectBanner />}
      <SyncStatus me={me} onSyncComplete={setMe} />
      <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">
          welcome, {me.username}
        </h1>
        <p className="text-zinc-600 dark:text-zinc-400">chat ui lands in phase 3.</p>
        <button
          onClick={async () => {
            await logout();
            router.replace("/login");
          }}
          className="h-10 rounded-full border border-zinc-300 px-5 text-sm font-medium transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
        >
          log out
        </button>
      </div>
    </main>
  );
}
