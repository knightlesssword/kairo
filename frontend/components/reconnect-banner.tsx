import { anilistLoginUrl } from "@/lib/api";

// shown on /chat when /auth/me reports anilist_connected=false (token expired or revoked).
export default function ReconnectBanner() {
  return (
    <div className="w-full bg-amber-100 text-amber-900 px-4 py-3 text-sm flex items-center justify-between dark:bg-amber-950 dark:text-amber-200">
      <span>your AniList connection expired. reconnect to keep syncing your list.</span>
      <a
        href={anilistLoginUrl()}
        className="ml-4 font-medium underline underline-offset-2 hover:no-underline"
      >
        Reconnect
      </a>
    </div>
  );
}
