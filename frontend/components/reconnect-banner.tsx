import { anilistLoginUrl } from "@/lib/api";

export default function ReconnectBanner() {
  return (
    <div
      className="w-full px-4 py-3 text-sm flex items-center justify-between shrink-0 border-b"
      style={{
        background: "var(--color-danger-dim)",
        borderColor: "rgba(244,63,94,0.3)",
      }}
    >
      <div className="flex items-center gap-2">
        <span
          className="h-1.5 w-1.5 rounded-full shrink-0"
          style={{
            background: "var(--color-danger)",
            animation: "glow-pulse 2s ease-in-out infinite",
            boxShadow: "0 0 4px var(--color-danger)",
          }}
        />
        <span
          style={{ color: "var(--color-danger)", fontFamily: "var(--font-noto), sans-serif" }}
        >
          AniList connection expired — reconnect to keep syncing.
        </span>
      </div>
      <a
        href={anilistLoginUrl()}
        className="ml-4 rounded-full px-3 py-1 text-xs font-medium transition-all duration-200"
        style={{
          border: "1px solid var(--color-danger)",
          color: "var(--color-danger)",
          fontFamily: "var(--font-noto), sans-serif",
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLAnchorElement).style.background = "var(--color-danger)";
          (e.currentTarget as HTMLAnchorElement).style.color = "white";
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLAnchorElement).style.background = "";
          (e.currentTarget as HTMLAnchorElement).style.color = "var(--color-danger)";
        }}
      >
        Reconnect
      </a>
    </div>
  );
}
