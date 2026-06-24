import type { AnimeCard } from "@/lib/stream";

interface Props {
  anime: AnimeCard;
}

export default function AnimeCardComponent({ anime }: Props) {
  return (
    <div className="mt-2 inline-flex flex-col gap-1 rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm dark:border-zinc-700 dark:bg-zinc-900">
      <span className="font-semibold text-zinc-900 dark:text-zinc-100">{anime.title}</span>
      <div className="flex flex-wrap gap-1">
        {anime.genres.slice(0, 4).map((g) => (
          <span
            key={g}
            className="rounded-full bg-zinc-200 px-2 py-0.5 text-xs text-zinc-700 dark:bg-zinc-700 dark:text-zinc-300"
          >
            {g}
          </span>
        ))}
      </div>
      <div className="flex gap-4 text-xs text-zinc-500 dark:text-zinc-400">
        {anime.episodes != null && <span>{anime.episodes} eps</span>}
        {anime.average_score != null && <span>score {anime.average_score}/100</span>}
      </div>
    </div>
  );
}
