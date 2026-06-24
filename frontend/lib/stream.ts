// SSE event reader for the /conversations/{id}/messages endpoint.
//
// the backend sends newline-delimited "data: {...}\n\n" events.
// event shapes:
//   {type: "delta", content: string}
//   {type: "anime_card", anime: AnimeCard}
//   {type: "done"}
//   {type: "error", message: string}

export interface AnimeCard {
  id: number;
  title: string;
  genres: string[];
  episodes: number | null;
  average_score: number | null;
}

export interface DeltaEvent {
  type: "delta";
  content: string;
}

export interface AnimeCardEvent {
  type: "anime_card";
  anime: AnimeCard;
}

export interface DoneEvent {
  type: "done";
}

export interface ErrorEvent {
  type: "error";
  message: string;
}

export type SSEEvent = DeltaEvent | AnimeCardEvent | DoneEvent | ErrorEvent;

export interface StreamCallbacks {
  onDelta: (content: string) => void;
  onAnimeCard: (anime: AnimeCard) => void;
  onDone: () => void;
  onError: (message: string) => void;
}

// reads the SSE stream from a fetch Response and calls the appropriate callback for each event.
// resolves when the stream ends (done or error).
export async function readSSEStream(
  response: Response,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  if (!response.ok) {
    callbacks.onError(`request failed: ${response.status}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    callbacks.onError("no response body");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      if (signal?.aborted) break;

      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // split on double-newline SSE message boundaries
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";

      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data: ")) continue;

        const raw = line.slice(6).trim();
        if (!raw) continue;

        let event: SSEEvent;
        try {
          event = JSON.parse(raw) as SSEEvent;
        } catch {
          continue;
        }

        switch (event.type) {
          case "delta":
            callbacks.onDelta(event.content);
            break;
          case "anime_card":
            callbacks.onAnimeCard(event.anime);
            break;
          case "done":
            callbacks.onDone();
            return;
          case "error":
            callbacks.onError(event.message);
            return;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
