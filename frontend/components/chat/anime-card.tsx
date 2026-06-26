import type { AnimeCard } from "@/lib/stream";

interface Props {
  anime: AnimeCard;
}

export default function AnimeCardComponent({ anime }: Props) {
  return (
    <div
      className="glow-card mt-2 flex gap-0 rounded-xl overflow-hidden max-w-sm"
      style={{ animation: "fade-up 300ms ease both" }}
    >
      {/* Cover image or fallback gradient */}
      <div
        className="shrink-0 w-14 flex items-center justify-center"
        style={{ background: "linear-gradient(180deg, #8B5CF6, #EC4899)" }}
      >
        {anime.cover_image ? (
          <img
            src={anime.cover_image}
            alt={anime.title}
            className="h-full w-full object-cover"
            style={{ minHeight: "80px" }}
          />
        ) : (
          <span className="text-white text-xl font-bold select-none" style={{ fontFamily: "serif" }}>
            {anime.title[0]}
          </span>
        )}
      </div>

      {/* Info */}
      <div className="flex flex-col gap-1.5 py-3 px-3 min-w-0">
        <span
          className="text-sm font-semibold text-text truncate leading-tight"
          style={{ fontFamily: "var(--font-cinzel), serif" }}
        >
          {anime.title}
        </span>

        <div
          className="flex items-center gap-2 text-xs flex-wrap"
          style={{ color: "var(--color-text-muted)" }}
        >
          {anime.average_score != null && (
            <span style={{ color: "var(--color-gold)", fontWeight: 500 }}>
              ★ {(anime.average_score / 10).toFixed(1)}
            </span>
          )}
          {anime.year && <span>{anime.year}</span>}
          {anime.episodes != null && <span>{anime.episodes} eps</span>}
        </div>

        <div className="flex flex-wrap gap-1 mt-0.5">
          {anime.genres.slice(0, 4).map((g) => (
            <span
              key={g}
              className="rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors duration-150"
              style={{
                background: "rgba(139,92,246,0.15)",
                color: "var(--color-primary)",
                border: "1px solid rgba(139,92,246,0.3)",
                fontFamily: "var(--font-noto), sans-serif",
              }}
            >
              {g}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
