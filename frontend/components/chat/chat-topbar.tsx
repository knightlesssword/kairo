"use client";

interface Props {
  title: string | null;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  onNewConversation: () => void;
  creating?: boolean;
}

export default function ChatTopbar({
  title,
  sidebarOpen,
  onToggleSidebar,
  onNewConversation,
  creating = false,
}: Props) {
  return (
    <div
      className="flex h-11 shrink-0 items-center gap-3 border-b border-border bg-surface px-3"
    >
      {/* Sidebar toggle */}
      <button
        onClick={onToggleSidebar}
        aria-label={sidebarOpen ? "collapse sidebar" : "expand sidebar"}
        title={`${sidebarOpen ? "collapse" : "expand"} sidebar (Ctrl+B)`}
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded transition-all duration-150"
        style={{ color: "var(--color-text-muted)" }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLButtonElement).style.color = "var(--color-primary)";
          (e.currentTarget as HTMLButtonElement).style.background = "rgba(139,92,246,0.1)";
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-muted)";
          (e.currentTarget as HTMLButtonElement).style.background = "";
        }}
      >
        {sidebarOpen ? (
          /* panel-left-close icon */
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <path d="M9 3v18" />
            <path d="m14 9-3 3 3 3" />
          </svg>
        ) : (
          /* panel-left-open icon */
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <path d="M9 3v18" />
            <path d="m15 9-3 3 3 3" />
          </svg>
        )}
      </button>

      {/* Conversation title */}
      <div className="flex-1 min-w-0">
        <span
          className="block truncate text-sm text-text-dim"
          style={{ fontFamily: "var(--font-cinzel), serif", letterSpacing: "0.04em" }}
        >
          {title ?? "new conversation"}
        </span>
      </div>

      {/* New conversation */}
      <button
        onClick={onNewConversation}
        disabled={creating}
        aria-label="new conversation"
        title="new conversation"
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded transition-all duration-150 disabled:opacity-40"
        style={{ color: "var(--color-text-muted)" }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLButtonElement).style.color = "var(--color-primary)";
          (e.currentTarget as HTMLButtonElement).style.background = "rgba(139,92,246,0.1)";
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-muted)";
          (e.currentTarget as HTMLButtonElement).style.background = "";
        }}
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 5v14M5 12h14" />
        </svg>
      </button>
    </div>
  );
}
