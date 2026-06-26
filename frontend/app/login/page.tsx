"use client";

import { anilistLoginUrl } from "@/lib/api";
import KairoLogo from "@/components/kairo-logo";

const PETAL_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 16"><ellipse cx="6" cy="8" rx="5" ry="7" fill="rgba(236,72,153,0.55)" /></svg>`;

const PETALS = [
  { left: "8%",  delay: "0s",    duration: "13s", size: 14 },
  { left: "20%", delay: "2.5s",  duration: "16s", size: 10 },
  { left: "35%", delay: "5s",    duration: "11s", size: 16 },
  { left: "50%", delay: "1s",    duration: "15s", size: 12 },
  { left: "62%", delay: "3.5s",  duration: "14s", size: 9  },
  { left: "75%", delay: "6s",    duration: "17s", size: 11 },
  { left: "85%", delay: "0.5s",  duration: "12s", size: 15 },
  { left: "93%", delay: "4s",    duration: "10s", size: 13 },
];

const STAR_BG = [
  "radial-gradient(1px 1px at 15% 20%, rgba(139,92,246,0.6) 0%, transparent 100%)",
  "radial-gradient(1px 1px at 80% 10%, rgba(6,182,212,0.5) 0%, transparent 100%)",
  "radial-gradient(1.5px 1.5px at 60% 65%, rgba(236,72,153,0.45) 0%, transparent 100%)",
  "radial-gradient(1px 1px at 40% 85%, rgba(139,92,246,0.35) 0%, transparent 100%)",
  "radial-gradient(1px 1px at 90% 50%, rgba(245,158,11,0.4) 0%, transparent 100%)",
  "radial-gradient(1px 1px at 25% 75%, rgba(6,182,212,0.3) 0%, transparent 100%)",
  "radial-gradient(1.5px 1.5px at 70% 30%, rgba(139,92,246,0.4) 0%, transparent 100%)",
  "radial-gradient(1px 1px at 5%  55%, rgba(236,72,153,0.3) 0%, transparent 100%)",
  "radial-gradient(1px 1px at 55% 15%, rgba(245,158,11,0.3) 0%, transparent 100%)",
  "radial-gradient(1px 1px at 95% 80%, rgba(139,92,246,0.4) 0%, transparent 100%)",
].join(",");

export default function LoginPage() {
  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-void">
      {/* Constellation background */}
      <div
        className="pointer-events-none absolute inset-0 opacity-70"
        style={{ backgroundImage: STAR_BG }}
      />

      {/* Falling sakura petals */}
      {PETALS.map((p, i) => (
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
            height: p.size * 1.33,
            animation: `sakura-fall ${p.duration} ease-in ${p.delay} infinite`,
            pointerEvents: "none",
          }}
        />
      ))}

      {/* Content */}
      <div
        className="relative z-10 flex flex-col items-center gap-6 text-center"
        style={{ animation: "fade-up 600ms cubic-bezier(0.16,1,0.3,1) both" }}
      >
        {/* Logo with glow */}
        <div
          style={{
            filter: "drop-shadow(0 0 18px rgba(139,92,246,0.5)) drop-shadow(0 0 36px rgba(139,92,246,0.25))",
          }}
        >
          <KairoLogo size={88} />
        </div>

        {/* Title + tagline */}
        <div className="flex flex-col items-center gap-2">
          <h1
            style={{ fontFamily: "var(--font-cinzel), serif" }}
            className="text-5xl font-semibold tracking-[0.18em] text-text uppercase"
          >
            kairo
          </h1>
          <p className="text-text-dim text-sm italic max-w-[260px]" style={{ fontFamily: "var(--font-noto), sans-serif" }}>
            an ai that knows your anime.
          </p>
        </div>

        {/* CTA */}
        <button
          onClick={() => { window.location.href = anilistLoginUrl(); }}
          className="mt-2 h-12 rounded-full px-8 font-medium text-white text-sm cursor-pointer
                     transition-all duration-250"
          style={{
            background: "linear-gradient(135deg, #EC4899, #8B5CF6)",
            fontFamily: "var(--font-noto), sans-serif",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.boxShadow =
              "0 0 20px rgba(139,92,246,0.55), 0 0 40px rgba(236,72,153,0.3)";
            (e.currentTarget as HTMLButtonElement).style.transform = "translateY(-1px)";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.boxShadow = "none";
            (e.currentTarget as HTMLButtonElement).style.transform = "translateY(0)";
          }}
          onMouseDown={(e) => {
            (e.currentTarget as HTMLButtonElement).style.transform = "translateY(0)";
          }}
        >
          Connect AniList
        </button>

        <p className="text-xs text-text-muted" style={{ fontFamily: "var(--font-noto), sans-serif" }}>
          your list, your taste — private by default.
        </p>
      </div>
    </main>
  );
}
