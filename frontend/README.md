# Kairo frontend

Next.js 16.2.9 + React 19 + TypeScript 5 + Tailwind v4 chat UI for Kairo: AniList
login, conversation sidebar, streaming markdown chat with anime cards, sync status.

Backend pairing: this app is a dumb client of `http://localhost:8000` by default
(see root `README.md`). Without the backend running, `/chat` shows a
"cannot reach the kairo backend" error with retry instead of bouncing to login.

## Routes

- `/` → redirects to `/chat`
- `/login` — landing + "Connect AniList" (full navigation to the backend, which 302s to AniList)
- `/chat` — auth guard: 401 → `/login`, backend-down → error UI; else redirects to first conversation or creates one
- `proxy.ts` — edge pre-check: no `kairo_session` cookie → instant server redirect to `/login` (no flash, no backend call); validation itself stays in the pages
- `/chat/[id]` — sidebar + topbar + sync status + message list + input

## Structure

- `lib/api.ts` — typed fetch client (`credentials: "include"`); `ApiError` carries HTTP status so pages split 401 from backend-down
- `lib/stream.ts` — SSE reader (`delta | anime_card | done | error`), abort-aware
- `components/chat/` — `message-list`, `message-input` (stop button while streaming), `chat-topbar`, `anime-card` (plain `<img>`, no `next/image`)
- `components/sidebar/conversation-list.tsx`, `components/sync-status.tsx`, `components/reconnect-banner.tsx`

## Setup

```sh
npm install
npm run dev      # http://localhost:3000
```

Only env var: `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`).
It is **build-time**: changing it needs `npm run build` again (or restart `dev`).
It must agree with the backend's `FRONTEND_ORIGIN`, or session cookies/CORS break.
There is intentionally no frontend service in `docker-compose.yml` — run it locally.

## Verify

```sh
npm run lint     # eslint
npx tsc --noEmit # typecheck
npm run build    # production build
```

Note: `eslint` currently reports 2 pre-existing `set-state-in-effect` errors in
`app/chat/[id]/page.tsx` (also on `master`); do not add new ones.
