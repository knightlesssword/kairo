# Plan 05 — Anime-Themed Frontend Redesign

**Goal:** Transform kairo's plain zinc/gray frontend into a vibrant, anime-aesthetic UI without
touching any backend logic or breaking any existing functionality (streaming, SSE, auth, sync).

**Stack facts (verified):**
- Next.js 16.2.9, React 19.2.4, TypeScript
- Tailwind CSS **v4** — CSS-first config. Theme extensions live in `globals.css` inside `@theme`
  blocks. There is no `tailwind.config.js`. Keyframes go directly in CSS; animations registered
  via `--animate-*` custom properties in `@theme`.
- Fonts loaded via `next/font/google` in `layout.tsx`
- No animation library installed — all motion is CSS keyframes + Tailwind utility classes

---

## Design Language

### Palette

| Token | Value | Role |
|---|---|---|
| `--void` | `#06010F` | Page background |
| `--surface` | `#0E0920` | Card / sidebar surfaces |
| `--surface-2` | `#160D2E` | Elevated surfaces (input, hover) |
| `--border` | `rgba(139,92,246,0.25)` | Default borders |
| `--border-glow` | `rgba(139,92,246,0.7)` | Active / focused borders |
| `--primary` | `#8B5CF6` | Electric purple — primary accent |
| `--primary-dim` | `#6D28D9` | Pressed / hover darken |
| `--pink` | `#EC4899` | Hot pink — user bubble, cta |
| `--cyan` | `#06B6D4` | Info states, streaming cursor |
| `--gold` | `#F59E0B` | Score highlights, sync "done" |
| `--text` | `#EDE9FE` | Primary text (lavender-white) |
| `--text-dim` | `#A78BFA` | Secondary text (muted purple) |
| `--text-muted` | `#6D5F8A` | Tertiary / placeholder |
| `--danger` | `#F43F5E` | Errors, reconnect warning |
| `--danger-dim` | `rgba(244,63,94,0.15)` | Danger banner bg |

### Typography

Two Google Fonts added to `layout.tsx`:
- **Cinzel** (`weights: [400, 600, 700]`) — display font for logo, page titles, section headers.
  Evokes classic anime title cards. CSS var: `--font-display`.
- **Noto Sans JP** (`weights: [400, 500, 700]`, `subsets: ['latin','japanese']`) — body font.
  Used everywhere prose appears. CSS var: `--font-body`.

Geist Mono stays as `--font-mono` for code blocks.

### Motion Principles

- All durations: `150ms` (micro), `250ms` (standard), `400ms` (entrance), `600ms` (dramatic)
- Easing: `cubic-bezier(0.4, 0, 0.2, 1)` standard; `cubic-bezier(0.16, 1, 0.3, 1)` spring exits
- Page entrance: fade-up on load (`opacity 0→1, translateY 12px→0`)
- Interactive feedback: glow pulse on focus/hover, not just color change
- No layout shifts — all animations are `opacity` + `transform` only

---

## Phase 1 — Design System (`globals.css`)

**File:** `frontend/app/globals.css`

Replace entirely with:

```css
@import "tailwindcss";

/* ── Keyframes ───────────────────────────────────────────── */

@keyframes fade-up {
  from { opacity: 0; transform: translateY(14px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

@keyframes glow-pulse {
  0%, 100% { box-shadow: 0 0 6px var(--primary), 0 0 12px rgba(139,92,246,0.3); }
  50%       { box-shadow: 0 0 14px var(--primary), 0 0 28px rgba(139,92,246,0.5), 0 0 48px rgba(139,92,246,0.2); }
}

@keyframes shimmer {
  0%   { background-position: -200% center; }
  100% { background-position:  200% center; }
}

@keyframes stream-blink {
  0%, 100% { opacity: 1; transform: scaleY(1); }
  40%       { opacity: 0.4; transform: scaleY(0.6); }
}

@keyframes spin-slow {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}

@keyframes sakura-fall {
  0%   { transform: translateY(-20px) rotate(0deg);   opacity: 0; }
  10%  { opacity: 0.7; }
  90%  { opacity: 0.5; }
  100% { transform: translateY(110vh) rotate(720deg); opacity: 0; }
}

@keyframes constellation-drift {
  0%   { transform: translate(0, 0) scale(1);     opacity: 0.6; }
  50%  { transform: translate(8px, -6px) scale(1.1); opacity: 1; }
  100% { transform: translate(0, 0) scale(1);     opacity: 0.6; }
}

@keyframes slide-in-left {
  from { transform: translateX(-100%); opacity: 0; }
  to   { transform: translateX(0);     opacity: 1; }
}

@keyframes bounce-subtle {
  0%, 100% { transform: translateY(0); }
  50%       { transform: translateY(-4px); }
}

/* ── Theme tokens ────────────────────────────────────────── */

@theme inline {
  /* Colors */
  --color-void:        #06010F;
  --color-surface:     #0E0920;
  --color-surface-2:   #160D2E;
  --color-border:      rgba(139,92,246,0.25);
  --color-border-glow: rgba(139,92,246,0.7);
  --color-primary:     #8B5CF6;
  --color-primary-dim: #6D28D9;
  --color-pink:        #EC4899;
  --color-pink-dim:    #BE185D;
  --color-cyan:        #06B6D4;
  --color-gold:        #F59E0B;
  --color-text:        #EDE9FE;
  --color-text-dim:    #A78BFA;
  --color-text-muted:  #6D5F8A;
  --color-danger:      #F43F5E;
  --color-danger-dim:  rgba(244,63,94,0.15);

  /* Fonts */
  --font-display: var(--font-cinzel);
  --font-body:    var(--font-noto);
  --font-mono:    var(--font-geist-mono);

  /* Animations */
  --animate-fade-up:            fade-up 400ms cubic-bezier(0.16,1,0.3,1) both;
  --animate-fade-in:            fade-in 300ms ease both;
  --animate-glow-pulse:         glow-pulse 2.4s ease-in-out infinite;
  --animate-shimmer:            shimmer 2s linear infinite;
  --animate-stream-blink:       stream-blink 1s ease-in-out infinite;
  --animate-spin-slow:          spin-slow 8s linear infinite;
  --animate-sakura:             sakura-fall 12s ease-in infinite;
  --animate-constellation:      constellation-drift 6s ease-in-out infinite;
  --animate-slide-in-left:      slide-in-left 350ms cubic-bezier(0.16,1,0.3,1) both;
  --animate-bounce-subtle:      bounce-subtle 2s ease-in-out infinite;
}

/* ── Base styles ─────────────────────────────────────────── */

:root {
  color-scheme: dark;
}

html, body {
  background-color: var(--color-void);
  color: var(--color-text);
  font-family: var(--font-body), "Noto Sans JP", system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* scrollbar */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: rgba(139,92,246,0.35);
  border-radius: 2px;
}
::-webkit-scrollbar-thumb:hover { background: var(--color-primary); }

/* selection */
::selection {
  background: rgba(139,92,246,0.35);
  color: var(--color-text);
}

/* focus ring */
:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* prose overrides for markdown messages */
.kairo-prose {
  color: var(--color-text);
  font-family: var(--font-body), sans-serif;
  line-height: 1.75;
}
.kairo-prose strong { color: var(--color-primary); font-weight: 600; }
.kairo-prose em    { color: var(--color-text-dim); }
.kairo-prose a     { color: var(--color-cyan); text-decoration: underline; }
.kairo-prose code  {
  font-family: var(--font-mono), monospace;
  background: rgba(139,92,246,0.15);
  color: var(--color-cyan);
  padding: 0.15em 0.4em;
  border-radius: 4px;
  font-size: 0.875em;
}
.kairo-prose pre {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 1rem;
  overflow-x: auto;
}
.kairo-prose h1, .kairo-prose h2, .kairo-prose h3 {
  font-family: var(--font-display), serif;
  color: var(--color-text);
  letter-spacing: 0.03em;
}
.kairo-prose hr {
  border-color: var(--color-border);
}
.kairo-prose table {
  width: 100%;
  border-collapse: collapse;
}
.kairo-prose th {
  background: var(--color-surface-2);
  color: var(--color-text-dim);
  padding: 0.5rem 0.75rem;
  text-align: left;
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.kairo-prose td {
  border-top: 1px solid var(--color-border);
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
}

/* shimmer gradient helper */
.shimmer-bg {
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(139,92,246,0.15) 50%,
    transparent 100%
  );
  background-size: 200% 100%;
  animation: var(--animate-shimmer);
}

/* glow card helper */
.glow-card {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  box-shadow: 0 0 0 transparent;
  transition: border-color 250ms ease, box-shadow 250ms ease;
}
.glow-card:hover {
  border-color: var(--color-border-glow);
  box-shadow: 0 0 16px rgba(139,92,246,0.2), inset 0 0 16px rgba(139,92,246,0.04);
}
```

**Verification:** Run `npm run dev`. Page background must be `#06010F`, not white.

---

## Phase 2 — Layout + Fonts (`layout.tsx`)

**File:** `frontend/app/layout.tsx`

Changes:
1. Remove `Geist` and `Geist_Mono` imports (keep only `Geist_Mono` for code)
2. Add `Cinzel` and `Noto_Sans_JP` from `next/font/google`
3. Set `--font-cinzel` and `--font-noto` CSS variables on `<html>`
4. Update metadata: title `"kairo"`, description matching the app

```tsx
import type { Metadata } from "next";
import { Cinzel, Noto_Sans_JP, Geist_Mono } from "next/font/google";
import "./globals.css";

const cinzel = Cinzel({
  variable: "--font-cinzel",
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  display: "swap",
});

const notoSans = Noto_Sans_JP({
  variable: "--font-noto",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "kairo",
  description: "an ai that remembers your anime taste",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${cinzel.variable} ${notoSans.variable} ${geistMono.variable} h-full`}
    >
      <body className="min-h-full flex flex-col bg-void text-text antialiased">
        {children}
      </body>
    </html>
  );
}
```

**Verification:** DevTools → Computed → font-family on `<body>` should show Noto Sans JP.

---

## Phase 3 — Login Page Hero (`login/page.tsx`)

This page is the **first impression**. Make it count.

### Layout

Full-screen dark void with three layers:
1. **Background layer** — CSS grid of faint constellation dots (pure CSS, `radial-gradient` + `::before`/`::after` pseudo-elements)
2. **Sakura layer** — 8 absolutely positioned `<span>` elements animated with `sakura-fall` at staggered delays. Each is a simple SVG petal (inline, ~200 bytes).
3. **Content layer** — centered column: logo mark + name + tagline + CTA button

### Logo Mark (pure SVG, inline)

A stylized `カ` (katakana "ka") inside a hexagonal frame, with a circuit-line detail.
Render at 80×80px. Colors: `--color-primary` fill, `--color-cyan` accent line.

```tsx
function KairoLogo() {
  return (
    <svg width="80" height="80" viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* Hexagon frame */}
      <polygon
        points="40,4 72,22 72,58 40,76 8,58 8,22"
        stroke="#8B5CF6"
        strokeWidth="1.5"
        fill="rgba(139,92,246,0.08)"
      />
      {/* Inner glow ring */}
      <circle cx="40" cy="40" r="24" stroke="#06B6D4" strokeWidth="0.75" strokeDasharray="3 4" />
      {/* Katakana カ stylized */}
      <text
        x="40" y="52"
        textAnchor="middle"
        fontFamily="serif"
        fontSize="30"
        fontWeight="700"
        fill="#EDE9FE"
        letterSpacing="0"
      >カ</text>
      {/* Circuit accent lines */}
      <line x1="40" y1="76" x2="40" y2="68" stroke="#06B6D4" strokeWidth="1" />
      <line x1="8"  y1="22" x2="16" y2="27" stroke="#06B6D4" strokeWidth="1" />
      <line x1="72" y1="22" x2="64" y2="27" stroke="#06B6D4" strokeWidth="1" />
    </svg>
  );
}
```

### Sakura Petals (pure CSS SVG)

```tsx
const PETAL_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 16">
  <ellipse cx="6" cy="8" rx="5" ry="7" fill="rgba(236,72,153,0.6)" />
</svg>`;

const PETALS = [
  { left: "8%",  delay: "0s",    duration: "12s", size: 14 },
  { left: "20%", delay: "2.5s",  duration: "15s", size: 10 },
  { left: "35%", delay: "5s",    duration: "11s", size: 16 },
  { left: "50%", delay: "1s",    duration: "14s", size: 12 },
  { left: "62%", delay: "3.5s",  duration: "13s", size: 9  },
  { left: "75%", delay: "6s",    duration: "16s", size: 11 },
  { left: "85%", delay: "0.5s",  duration: "12s", size: 15 },
  { left: "93%", delay: "4s",    duration: "10s", size: 13 },
];
```

Each petal is:
```tsx
<img
  key={i}
  src={`data:image/svg+xml,${encodeURIComponent(PETAL_SVG)}`}
  alt=""
  aria-hidden="true"
  style={{
    position: "absolute",
    top: "-20px",
    left: p.left,
    width: p.size,
    height: p.size * 1.3,
    animation: `sakura-fall ${p.duration} ease-in ${p.delay} infinite`,
    pointerEvents: "none",
  }}
/>
```

### CTA Button

Pill shape, gradient bg from `--pink` to `--primary`, white text, glow on hover:

```css
background: linear-gradient(135deg, #EC4899, #8B5CF6);
box-shadow: 0 0 0 transparent;
transition: box-shadow 250ms ease, transform 150ms ease;

&:hover {
  box-shadow: 0 0 20px rgba(139,92,246,0.5), 0 0 40px rgba(236,72,153,0.3);
  transform: translateY(-1px);
}
&:active { transform: translateY(0); }
```

### Tagline

```
"an ai that knows your anime."
```
Font: Noto Sans JP, `text-text-dim`, weight 400, italic, text-center.

### Constellation background

Use a CSS `radial-gradient` tiled pattern for stars:

```css
background-image:
  radial-gradient(1px 1px at 20% 30%, rgba(139,92,246,0.5) 0%, transparent 100%),
  radial-gradient(1px 1px at 80% 10%, rgba(6,182,212,0.4) 0%, transparent 100%),
  radial-gradient(1.5px 1.5px at 60% 70%, rgba(236,72,153,0.4) 0%, transparent 100%),
  radial-gradient(1px 1px at 40% 85%, rgba(139,92,246,0.3) 0%, transparent 100%),
  radial-gradient(1px 1px at 90% 55%, rgba(245,158,11,0.35) 0%, transparent 100%);
```

This is applied on the `<main>` element directly as inline style (not Tailwind — too granular).

### Full component structure

```tsx
"use client";
import { anilistLoginUrl } from "@/lib/api";

// KairoLogo and PETALS defined above

export default function LoginPage() {
  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-void">
      {/* Constellation bg */}
      <div className="absolute inset-0 [background-image:radial-gradient(...)] opacity-60" />

      {/* Sakura petals */}
      {PETALS.map((p, i) => <img key={i} ... />)}

      {/* Content */}
      <div className="relative z-10 flex flex-col items-center gap-6 animate-[fade-up_600ms_cubic-bezier(0.16,1,0.3,1)_both]">
        <KairoLogo />

        <div className="flex flex-col items-center gap-2 text-center">
          <h1 className="font-[family-name:var(--font-cinzel)] text-5xl font-semibold tracking-[0.15em] text-text uppercase">
            kairo
          </h1>
          <p className="text-text-dim text-sm italic max-w-[260px]">
            an ai that knows your anime.
          </p>
        </div>

        <button
          onClick={() => { window.location.href = anilistLoginUrl(); }}
          className="mt-4 h-12 rounded-full px-8 font-medium text-white text-sm
                     bg-gradient-to-r from-pink to-primary
                     shadow-[0_0_0_transparent] hover:shadow-[0_0_20px_rgba(139,92,246,0.5),0_0_40px_rgba(236,72,153,0.3)]
                     hover:-translate-y-px active:translate-y-0
                     transition-all duration-250"
        >
          Connect AniList
        </button>

        <p className="text-xs text-text-muted mt-2">
          your list, your taste — private by default.
        </p>
      </div>
    </main>
  );
}
```

**Verification:** Visit `/login`. You must see dark void bg, falling pink petals, glowing button on hover.

---

## Phase 4 — Loading State (`chat/page.tsx`)

Replace the plain `text-zinc-500 "loading…"` with an animated kairo logo spinner.

```tsx
return (
  <div className="flex h-screen items-center justify-center bg-void">
    <div className="flex flex-col items-center gap-4 animate-[fade-in_400ms_ease_both]">
      {/* Logo spinning slowly */}
      <div className="animate-[spin-slow_8s_linear_infinite]">
        <KairoLogo />  {/* import from a shared components/kairo-logo.tsx */}
      </div>
      <span className="font-[family-name:var(--font-cinzel)] text-xs tracking-[0.3em] text-text-dim uppercase">
        loading
      </span>
    </div>
  </div>
);
```

Extract `KairoLogo` into `frontend/components/kairo-logo.tsx` (shared between login + loading).

---

## Phase 5 — Chat Layout (`chat/[id]/page.tsx`)

No logic changes. Only className changes:

```tsx
// outer wrapper — fill screen, dark bg
<div className="flex h-screen flex-col bg-void">

// reconnect banner stays at top (styled in Phase 8)

// main area
<div className="flex flex-1 overflow-hidden">
  <ConversationList />                        {/* styled in Phase 6 */}
  <div className="flex flex-1 flex-col overflow-hidden">
    <SyncStatus ... />                        {/* styled in Phase 9 */}
    <MessageList messages={messages} />       {/* styled in Phase 7 */}
    <MessageInput onSend={handleSend} ... />  {/* styled in Phase 7 */}
  </div>
</div>
```

Note: `SyncStatus` is rendered in the conversation page — wire it here if it isn't already. Looking at current code, SyncStatus is NOT currently rendered in `[id]/page.tsx` — only `ReconnectBanner` is. Add it:
- Fetch `me` and pass `onSyncComplete` that calls `setMe`.
- Position `SyncStatus` between the banner and the message list.

---

## Phase 6 — Sidebar (`conversation-list.tsx`)

### Structure changes

Add a **user profile header** at the top of the sidebar (requires fetching `me` inside this component or receiving it as a prop — accept it as a prop `me?: Me` to avoid a second API call).

```tsx
interface Props {
  me?: Me;
  onNewConversation?: (conv: Conversation) => void;
}
```

Parent (`[id]/page.tsx`) already has `me` state — thread it down as `<ConversationList me={me} />`.

### Visual spec

```
┌────────────────────────────────┐
│  [avatar circle]  username     │  ← profile header, border-b border-border
│  ● connected                   │
├────────────────────────────────┤
│  + new conversation            │  ← gradient border button
├────────────────────────────────┤
│  [active] Conv title           │  ← bg-surface-2, left-border 2px primary
│  Conv title 2                  │
│  Conv title 3                  │
└────────────────────────────────┘
```

```tsx
<aside className="flex w-64 shrink-0 flex-col border-r border-border bg-surface">

  {/* Profile header */}
  {me && (
    <div className="flex items-center gap-3 px-4 py-4 border-b border-border">
      {/* Avatar — first letter of username in a gradient circle */}
      <div className="h-9 w-9 rounded-full bg-gradient-to-br from-primary to-pink
                      flex items-center justify-center shrink-0
                      text-white font-bold text-sm uppercase shadow-[0_0_12px_rgba(139,92,246,0.4)]">
        {me.username[0]}
      </div>
      <div className="flex flex-col min-w-0">
        <span className="text-sm font-medium text-text truncate">{me.username}</span>
        <span className={`text-xs ${me.anilist_connected ? "text-cyan" : "text-danger"}`}>
          {me.anilist_connected ? "● connected" : "● disconnected"}
        </span>
      </div>
    </div>
  )}

  {/* New conversation button */}
  <div className="p-3">
    <button
      onClick={handleNew}
      disabled={creating}
      className="w-full rounded-lg border border-border bg-surface-2
                 px-3 py-2 text-left text-sm text-text-dim
                 hover:border-border-glow hover:text-text hover:bg-[rgba(139,92,246,0.08)]
                 disabled:opacity-40 transition-all duration-200
                 flex items-center gap-2"
    >
      <span className="text-primary font-bold text-base leading-none">+</span>
      new conversation
    </button>
  </div>

  {/* Conversation list */}
  <nav className="flex-1 overflow-y-auto px-2 pb-4 space-y-0.5">
    {items.length === 0 ? (
      <p className="px-3 py-3 text-xs text-text-muted italic">
        no conversations yet
      </p>
    ) : (
      items.map((conv) => {
        const isActive = pathname === `/chat/${conv.id}`;
        return (
          <Link
            key={conv.id}
            href={`/chat/${conv.id}`}
            className={`
              block truncate rounded-lg px-3 py-2.5 text-sm transition-all duration-150
              ${isActive
                ? "bg-surface-2 text-text border-l-2 border-primary pl-[10px] shadow-[inset_0_0_12px_rgba(139,92,246,0.08)]"
                : "text-text-dim hover:bg-[rgba(139,92,246,0.06)] hover:text-text border-l-2 border-transparent pl-[10px]"
              }
            `}
          >
            {conv.title ?? "new conversation"}
          </Link>
        );
      })
    )}
  </nav>
</aside>
```

**Verification:** Sidebar shows user avatar with gradient, active conversation has purple left border.

---

## Phase 7 — Message Components

### 7a. `message-list.tsx`

#### Empty state

Replace `text-zinc-400 "ask anything..."` with a centered panel:

```tsx
<div className="flex flex-1 items-center justify-center">
  <div className="flex flex-col items-center gap-4 text-center animate-[fade-up_400ms_ease_both]">
    <div className="text-4xl">カ</div>   {/* or use KairoLogo at 48px */}
    <p className="font-[family-name:var(--font-cinzel)] text-text-dim text-sm tracking-widest uppercase">
      what should we watch next?
    </p>
    <p className="text-xs text-text-muted max-w-[200px]">
      ask about your list, get recommendations, or just talk anime.
    </p>
  </div>
</div>
```

#### Message bubbles — user

```tsx
// user bubble
className="max-w-[72%] rounded-2xl rounded-tr-sm px-4 py-3 text-sm text-white
           bg-gradient-to-br from-pink to-primary
           shadow-[0_2px_12px_rgba(236,72,153,0.25)]"
```

#### Message bubbles — assistant

No bubble background — just left-aligned content with a small purple dot avatar:

```tsx
<div className="flex gap-3 max-w-[85%]">
  {/* Avatar dot */}
  <div className="h-6 w-6 shrink-0 mt-0.5 rounded-full bg-gradient-to-br from-primary to-cyan
                  flex items-center justify-center text-[10px] font-bold text-white shadow-[0_0_8px_rgba(139,92,246,0.5)]">
    カ
  </div>
  <div className="flex flex-col gap-2 min-w-0">
    <div className="kairo-prose text-sm">
      {content ? <ReactMarkdown ...>{content}</ReactMarkdown> : streaming ? <StreamCursor /> : null}
    </div>
    {animeCards?.map(card => <AnimeCardComponent key={card.id} anime={card} />)}
  </div>
</div>
```

#### Streaming cursor

Extract a `<StreamCursor />` component instead of the inline `▍`:

```tsx
function StreamCursor() {
  return (
    <span className="inline-flex items-center gap-1">
      {[0, 1, 2].map(i => (
        <span
          key={i}
          className="inline-block h-1.5 w-1.5 rounded-full bg-cyan
                     animate-[stream-blink_1s_ease-in-out_infinite]"
          style={{ animationDelay: `${i * 0.2}s` }}
        />
      ))}
    </span>
  );
}
```
Three dots, staggered blink. Cyan color.

#### Scroll container

```tsx
<div className="flex flex-1 flex-col gap-5 overflow-y-auto px-6 py-6">
```

### 7b. `message-input.tsx`

```tsx
<div className="border-t border-border bg-surface px-4 py-4">
  <div className="mx-auto flex max-w-3xl items-end gap-3">
    <textarea
      ...
      className="flex-1 resize-none overflow-hidden rounded-xl
                 border border-border bg-surface-2
                 px-4 py-3 text-sm text-text placeholder:text-text-muted
                 focus:outline-none focus:border-primary
                 focus:shadow-[0_0_0_3px_rgba(139,92,246,0.2),0_0_16px_rgba(139,92,246,0.15)]
                 disabled:opacity-40
                 transition-all duration-200"
    />
    <button
      ...
      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl
                 bg-gradient-to-br from-pink to-primary text-white
                 hover:shadow-[0_0_16px_rgba(139,92,246,0.5)]
                 disabled:opacity-30 disabled:shadow-none
                 transition-all duration-200"
      aria-label="send"
    >
      {/* keep existing SVG arrow icon */}
    </button>
  </div>
</div>
```

**Verification:** Textarea focus shows purple glow ring. Send button has pink-to-purple gradient.

---

## Phase 8 — Anime Card (`anime-card.tsx`)

This component gets the biggest upgrade. Add cover art support (AniList provides `coverImage.large`),
richer genre tags, score ring, and glassmorphism styling.

### Data shape change

The `AnimeCard` type (in `lib/stream.ts`) needs two new optional fields:
- `cover_image?: string` — URL to AniList cover image
- `year?: number` — anime year

Add these to the `AnimeCard` interface. The backend already has access to this data via
`anilist_service.py` — plumbing the fields into the SSE payload is a backend task (out of scope
for this frontend plan, but the UI must gracefully handle absence with a fallback gradient).

### Visual spec

```
┌─────────────────────────────────────────────┐
│ [cover img 56×80]  Title (Cinzel font)      │
│                    ★ score  •  year  •  eps  │
│                    [Genre] [Genre] [Genre]   │
└─────────────────────────────────────────────┘
```

```tsx
export default function AnimeCardComponent({ anime }: Props) {
  return (
    <div className="glow-card mt-2 flex gap-3 rounded-xl overflow-hidden max-w-sm
                    animate-[fade-up_300ms_ease_both]">
      {/* Cover image or fallback gradient */}
      <div className="shrink-0 w-14 bg-gradient-to-b from-primary to-pink">
        {anime.cover_image ? (
          <img
            src={anime.cover_image}
            alt={anime.title}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="h-full w-full flex items-center justify-center text-white text-xl font-bold">
            {anime.title[0]}
          </div>
        )}
      </div>

      {/* Info */}
      <div className="flex flex-col gap-1.5 py-3 pr-3 min-w-0">
        <span className="font-[family-name:var(--font-cinzel)] text-sm font-semibold text-text truncate leading-tight">
          {anime.title}
        </span>

        <div className="flex items-center gap-2 text-xs text-text-muted flex-wrap">
          {anime.average_score != null && (
            <span className="text-gold font-medium">★ {(anime.average_score / 10).toFixed(1)}</span>
          )}
          {anime.year && <span>{anime.year}</span>}
          {anime.episodes != null && <span>{anime.episodes} eps</span>}
        </div>

        <div className="flex flex-wrap gap-1 mt-0.5">
          {anime.genres.slice(0, 4).map((g) => (
            <span
              key={g}
              className="rounded-full px-2 py-0.5 text-[10px] font-medium
                         bg-[rgba(139,92,246,0.15)] text-primary
                         border border-[rgba(139,92,246,0.3)]
                         hover:bg-[rgba(139,92,246,0.25)] transition-colors"
            >
              {g}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
```

**Verification:** Anime card has cover-image slot, gold score, glowing genre tags.

---

## Phase 9 — Reconnect Banner (`reconnect-banner.tsx`)

```tsx
<div className="w-full px-4 py-3 text-sm flex items-center justify-between
                bg-danger-dim border-b border-[rgba(244,63,94,0.3)]">
  <div className="flex items-center gap-2">
    <span className="h-1.5 w-1.5 rounded-full bg-danger animate-pulse" />
    <span className="text-danger">
      AniList connection expired — reconnect to keep syncing.
    </span>
  </div>
  <a
    href={anilistLoginUrl()}
    className="ml-4 rounded-full px-3 py-1 text-xs font-medium
               border border-danger text-danger
               hover:bg-danger hover:text-white
               transition-all duration-200"
  >
    Reconnect
  </a>
</div>
```

---

## Phase 10 — Sync Status (`sync-status.tsx`)

### Syncing state — animated bar

Replace the single pulsing dot with a shimmer progress bar:

```tsx
{syncState === "syncing" && (
  <div className="relative h-0.5 w-full overflow-hidden rounded-full bg-surface-2">
    <div className="absolute inset-0 shimmer-bg" />
  </div>
)}
```

And the status text row:

```tsx
<div className="flex items-center gap-3 px-4 py-2 text-xs border-b border-border bg-surface">

  {/* Status text */}
  <div className="flex items-center gap-2 flex-1 min-w-0">
    {syncState === "syncing" ? (
      <>
        <span className="h-1.5 w-1.5 rounded-full bg-cyan animate-pulse" />
        <span className="text-cyan">syncing your anime list…</span>
      </>
    ) : syncState === "error" ? (
      <>
        <span className="h-1.5 w-1.5 rounded-full bg-danger" />
        <span className="text-danger truncate">{errorMsg}</span>
      </>
    ) : syncState === "done" ? (
      <>
        <span className="h-1.5 w-1.5 rounded-full bg-gold" />
        <span className="text-gold">synced just now</span>
      </>
    ) : lastSyncedAt ? (
      <span className="text-text-muted">synced {relativeTime(lastSyncedAt)}</span>
    ) : (
      <span className="text-text-muted">not yet synced</span>
    )}
  </div>

  {/* Manual sync trigger */}
  {syncState !== "syncing" && (
    <button
      onClick={startSync}
      className="text-text-muted hover:text-primary transition-colors duration-150 text-xs"
    >
      sync now
    </button>
  )}
</div>
```

---

## Phase 11 — Shared Logo Component

Create `frontend/components/kairo-logo.tsx`:

```tsx
interface Props {
  size?: number;
}

export default function KairoLogo({ size = 64 }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 80 80"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="kairo"
      role="img"
    >
      <polygon
        points="40,4 72,22 72,58 40,76 8,58 8,22"
        stroke="#8B5CF6"
        strokeWidth="1.5"
        fill="rgba(139,92,246,0.08)"
      />
      <circle
        cx="40" cy="40" r="24"
        stroke="#06B6D4"
        strokeWidth="0.75"
        strokeDasharray="3 4"
      />
      <text
        x="40" y="52"
        textAnchor="middle"
        fontFamily="serif"
        fontSize="30"
        fontWeight="700"
        fill="#EDE9FE"
      >
        カ
      </text>
      <line x1="40" y1="76" x2="40" y2="68" stroke="#06B6D4" strokeWidth="1" />
      <line x1="8"  y1="22" x2="16" y2="27" stroke="#06B6D4" strokeWidth="1" />
      <line x1="72" y1="22" x2="64" y2="27" stroke="#06B6D4" strokeWidth="1" />
    </svg>
  );
}
```

Import in `login/page.tsx` and `chat/page.tsx`.

---

## Phase 12 — `next.config.ts` (image domains)

AniList cover images are served from `s4.anilist.co`. To use `<img>` (not Next `<Image>`)
this is fine without config. If we later switch to `<Image>`, add:

```ts
const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "s4.anilist.co" },
    ],
  },
};
```

Add this now so it's ready.

---

## Implementation Order (execute in this sequence)

| # | File | Depends on |
|---|---|---|
| 1 | `globals.css` | nothing |
| 2 | `layout.tsx` | globals.css |
| 3 | `components/kairo-logo.tsx` (new) | nothing |
| 4 | `login/page.tsx` | layout, kairo-logo |
| 5 | `chat/page.tsx` | kairo-logo |
| 6 | `components/sidebar/conversation-list.tsx` | globals |
| 7 | `components/chat/message-list.tsx` | globals |
| 8 | `components/chat/message-input.tsx` | globals |
| 9 | `components/chat/anime-card.tsx` | globals |
| 10 | `components/reconnect-banner.tsx` | globals |
| 11 | `components/sync-status.tsx` | globals |
| 12 | `app/chat/[id]/page.tsx` | sidebar (me prop), sync-status |
| 13 | `next.config.ts` | nothing |

---

## Verification Checklist

- [ ] `/login` — dark void bg, falling pink petals visible, logo renders, button glows on hover
- [ ] `/chat` redirect — logo spins during load (not plain text "loading…")
- [ ] Sidebar — avatar gradient circle, active conversation left border purple
- [ ] Message input — focus shows purple glow ring
- [ ] User messages — pink-to-purple gradient bubble
- [ ] Assistant messages — kairo avatar dot + prose text renders correctly with markdown
- [ ] Streaming cursor — three cyan dots blinking in staggered sequence (not `▍`)
- [ ] Anime cards — cover image slot present, genre tags glowing purple
- [ ] Reconnect banner — red danger styling visible when anilist_connected=false
- [ ] Sync status — cyan shimmer bar during sync, gold dot when done, red on error
- [ ] Scrollbar — thin purple scrollbar (not default browser chrome)
- [ ] Font — Cinzel on logo/headings, Noto Sans JP on body prose
- [ ] `npm run build` — zero TypeScript errors

---

## Anti-Patterns to Avoid

- Do NOT use `dark:` Tailwind variants — this UI is dark-only by design. Remove all existing `dark:` classes.
- Do NOT use `@apply` in globals.css — Tailwind v4 discourages it; use real CSS classes or `@layer components`.
- Do NOT use `tailwind.config.js` — v4 is CSS-first. All theme extensions go in `@theme inline {}` in globals.css.
- Do NOT use `next/image` for AniList covers unless `remotePatterns` is configured — use plain `<img>` for now.
- Do NOT break SSE streaming logic in `[id]/page.tsx` — only className props change.
- Do NOT add animation libraries (framer-motion, etc.) — all motion is CSS keyframes only.
- Do NOT use `style={{ animation: ... }}` for Tailwind-registered animations — use `className="animate-[name_duration]"` syntax.
