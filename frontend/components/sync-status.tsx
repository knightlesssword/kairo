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
          // transient poll error; keep polling
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
        // deduplicated job that already finished
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

  // auto-trigger on first load if never synced
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
    <div className="flex items-center gap-3 px-4 py-2 text-sm text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-zinc-800">
      {syncState === "syncing" ? (
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
          syncing your anime list…
        </span>
      ) : syncState === "error" ? (
        <span className="text-red-500">{errorMsg}</span>
      ) : lastSyncedAt ? (
        <span>synced {relativeTime(lastSyncedAt)}</span>
      ) : (
        <span>not yet synced</span>
      )}

      {syncState !== "syncing" && (
        <button
          onClick={startSync}
          className="ml-auto text-xs underline underline-offset-2 hover:text-zinc-800 dark:hover:text-zinc-200 transition-colors"
        >
          sync now
        </button>
      )}
    </div>
  );
}
