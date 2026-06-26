"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchMe, getSyncJob, postSync, type Me, type SyncJob } from "@/lib/api";

interface Props {
  me: Me;
  onSyncComplete: (updated: Me) => void;
}

type SyncState = "idle" | "syncing" | "done" | "error";

function relativeTime(iso: string): string {
  const secs = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

export default function SyncStatus({ me, onSyncComplete }: Props) {
  const [syncState, setSyncState] = useState<SyncState>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(me.last_synced_at);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const activeRef = useRef(true);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const pollJob = useCallback(
    (jobId: string) => {
      pollRef.current = setInterval(async () => {
        try {
          const job: SyncJob = await getSyncJob(jobId);
          if (!activeRef.current) return;

          if (job.status === "completed") {
            stopPolling();
            setSyncState("done");
            const updated = await fetchMe();
            if (updated && activeRef.current) {
              setLastSyncedAt(updated.last_synced_at);
              onSyncComplete(updated);
            }
          } else if (job.status === "failed") {
            stopPolling();
            setSyncState("error");
            setErrorMsg(job.error ?? "sync failed");
          }
        } catch {
          // transient poll error — keep polling
        }
      }, 3000);
    },
    [onSyncComplete],
  );

  const startSync = useCallback(async () => {
    setSyncState("syncing");
    setErrorMsg(null);
    try {
      const job = await postSync();
      if (!activeRef.current) return;

      if (job.status === "completed") {
        setSyncState("done");
        const updated = await fetchMe();
        if (updated && activeRef.current) {
          setLastSyncedAt(updated.last_synced_at);
          onSyncComplete(updated);
        }
      } else if (job.status === "failed") {
        setSyncState("error");
        setErrorMsg(job.error ?? "sync failed");
      } else {
        pollJob(job.job_id);
      }
    } catch (e) {
      if (activeRef.current) {
        setSyncState("error");
        setErrorMsg(e instanceof Error ? e.message : "sync request failed");
      }
    }
  }, [onSyncComplete, pollJob]);

  useEffect(() => {
    activeRef.current = true;
    if (!me.last_synced_at) {
      startSync();
    }
    return () => {
      activeRef.current = false;
      stopPolling();
    };
    // run once on mount only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="shrink-0 border-b border-border bg-surface">
      {/* Shimmer progress bar during sync */}
      {syncState === "syncing" && (
        <div className="relative h-0.5 w-full overflow-hidden" style={{ background: "var(--color-surface-2)" }}>
          <div className="absolute inset-0 shimmer-bg" />
        </div>
      )}

      <div className="flex items-center gap-3 px-4 py-2 text-xs">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {syncState === "syncing" ? (
            <>
              <span
                className="h-1.5 w-1.5 rounded-full shrink-0"
                style={{ background: "var(--color-cyan)", animation: "glow-pulse 2s ease-in-out infinite" }}
              />
              <span style={{ color: "var(--color-cyan)", fontFamily: "var(--font-noto), sans-serif" }}>
                syncing your anime list…
              </span>
            </>
          ) : syncState === "error" ? (
            <>
              <span className="h-1.5 w-1.5 rounded-full shrink-0" style={{ background: "var(--color-danger)" }} />
              <span className="truncate" style={{ color: "var(--color-danger)", fontFamily: "var(--font-noto), sans-serif" }}>
                {errorMsg}
              </span>
            </>
          ) : syncState === "done" ? (
            <>
              <span className="h-1.5 w-1.5 rounded-full shrink-0" style={{ background: "var(--color-gold)" }} />
              <span style={{ color: "var(--color-gold)", fontFamily: "var(--font-noto), sans-serif" }}>
                synced just now
              </span>
            </>
          ) : lastSyncedAt ? (
            <span style={{ color: "var(--color-text-muted)", fontFamily: "var(--font-noto), sans-serif" }}>
              synced {relativeTime(lastSyncedAt)}
            </span>
          ) : (
            <span style={{ color: "var(--color-text-muted)", fontFamily: "var(--font-noto), sans-serif" }}>
              not yet synced
            </span>
          )}
        </div>

        {syncState !== "syncing" && (
          <button
            onClick={startSync}
            className="transition-colors duration-150 shrink-0"
            style={{
              color: "var(--color-text-muted)",
              fontFamily: "var(--font-noto), sans-serif",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.color = "var(--color-primary)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-muted)";
            }}
          >
            sync now
          </button>
        )}
      </div>
    </div>
  );
}
