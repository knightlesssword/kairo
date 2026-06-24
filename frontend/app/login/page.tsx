"use client";

import { anilistLoginUrl } from "@/lib/api";

export default function LoginPage() {
  return (
    <main className="flex flex-1 min-h-screen flex-col items-center justify-center gap-8 bg-zinc-50 dark:bg-black">
      <div className="flex flex-col items-center gap-3 text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
          kairo
        </h1>
        <p className="max-w-sm text-zinc-600 dark:text-zinc-400">
          an ai assistant that remembers your anime taste. connect AniList to begin.
        </p>
      </div>
      <button
        onClick={() => {
          window.location.href = anilistLoginUrl();
        }}
        className="h-12 rounded-full bg-blue-600 px-6 font-medium text-white transition-colors hover:bg-blue-700"
      >
        Connect AniList
      </button>
    </main>
  );
}
