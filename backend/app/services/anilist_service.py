"""AniList GraphQL client.

all functions accept a plain decrypted access token. callers (sync_service) are
responsible for:
  1. calling anilist_guard.assert_token_valid before invoking here
  2. calling anilist_guard.handle_unauthorized on AniListAuthError

pydantic models use extra="ignore" so unknown fields from the API are silently dropped
rather than causing parse failures when AniList adds new fields.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel, ConfigDict, field_validator

from app.config import get_settings

_HTTP_TIMEOUT = httpx.Timeout(30.0)
_PER_PAGE = 50


class AniListError(Exception):
    """non-auth AniList API error."""


class AniListAuthError(AniListError):
    """AniList returned 401. caller must call handle_unauthorized."""


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------

async def _query(token: str, query: str, variables: dict | None = None) -> dict:
    """execute one GraphQL query. returns the `data` dict.

    raises AniListAuthError on 401, AniListError on any other failure.
    """
    settings = get_settings()
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(
            settings.anilist_graphql_url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    if resp.status_code == 401:
        raise AniListAuthError("AniList returned 401")
    if resp.status_code != 200:
        raise AniListError(f"AniList returned {resp.status_code}")

    body = resp.json()
    if "errors" in body and body["errors"]:
        # graphql-level errors (e.g. rate limit, bad query)
        msg = body["errors"][0].get("message", "unknown graphql error")
        raise AniListError(f"AniList graphql error: {msg}")

    data = body.get("data")
    if data is None:
        raise AniListError("AniList response missing 'data' field")

    return data


# ---------------------------------------------------------------------------
# response models
# ---------------------------------------------------------------------------

class _MediaTitle(BaseModel):
    model_config = ConfigDict(extra="ignore")
    romaji: str | None = None
    english: str | None = None


class _Media(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    title: _MediaTitle | None = None
    genres: list[str] = []
    episodes: int | None = None


class AnimeListEntry(BaseModel):
    """one row in a user's anime list, ready to upsert into user_anime_list."""
    model_config = ConfigDict(extra="ignore")

    mediaId: int
    status: str
    score: float | None = None
    progress: int = 0
    updatedAt: int | None = None  # unix timestamp from AniList
    media: _Media | None = None

    @field_validator("score", mode="before")
    @classmethod
    def _zero_score_to_null(cls, v: float | None) -> float | None:
        # AniList returns 0 for unscored entries; treat as null
        if v == 0:
            return None
        return v

    @property
    def title(self) -> str | None:
        if self.media and self.media.title:
            return self.media.title.english or self.media.title.romaji
        return None

    @property
    def genres(self) -> list[str]:
        return self.media.genres if self.media else []

    @property
    def episodes(self) -> int | None:
        return self.media.episodes if self.media else None

    @property
    def updated_at(self) -> datetime | None:
        if self.updatedAt:
            return datetime.fromtimestamp(self.updatedAt, tz=timezone.utc)
        return None


class _AnimeStats(BaseModel):
    model_config = ConfigDict(extra="ignore")
    count: int = 0
    meanScore: float = 0.0


class _Statistics(BaseModel):
    model_config = ConfigDict(extra="ignore")
    anime: _AnimeStats = _AnimeStats()


class AnilistStats(BaseModel):
    """viewer stats for anilist_profiles."""
    model_config = ConfigDict(extra="ignore")
    id: int
    name: str
    statistics: _Statistics = _Statistics()

    @property
    def anime_count(self) -> int:
        return self.statistics.anime.count

    @property
    def mean_score(self) -> float:
        return self.statistics.anime.meanScore


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

_ANIME_LIST_QUERY = """
query ($userId: Int, $page: Int, $perPage: Int) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { hasNextPage }
    mediaList(userId: $userId, type: ANIME) {
      mediaId
      status
      score(format: POINT_10_DECIMAL)
      progress
      updatedAt
      media {
        id
        title { romaji english }
        genres
        episodes
      }
    }
  }
}
"""

_VIEWER_STATS_QUERY = """
query {
  Viewer {
    id
    name
    statistics {
      anime { count meanScore }
    }
  }
}
"""


async def fetch_anime_list(token: str, anilist_user_id: int) -> list[AnimeListEntry]:
    """fetch all pages of a user's anime list. returns typed entries, unknown fields dropped."""
    entries: list[AnimeListEntry] = []
    page = 1

    while True:
        data = await _query(token, _ANIME_LIST_QUERY, {
            "userId": anilist_user_id,
            "page": page,
            "perPage": _PER_PAGE,
        })

        page_data = data.get("Page") or {}
        raw_entries = page_data.get("mediaList") or []
        has_next = (page_data.get("pageInfo") or {}).get("hasNextPage", False)

        for raw in raw_entries:
            try:
                entries.append(AnimeListEntry.model_validate(raw))
            except Exception:
                # skip malformed entries rather than aborting the whole sync
                continue

        if not has_next:
            break
        page += 1

    return entries


async def fetch_viewer_stats(token: str) -> AnilistStats:
    """fetch viewer profile + statistics for the authenticated user."""
    data = await _query(token, _VIEWER_STATS_QUERY)
    viewer = (data or {}).get("Viewer")
    if not viewer:
        raise AniListError("Viewer field missing in stats response")
    return AnilistStats.model_validate(viewer)


# ---------------------------------------------------------------------------
# chat-service lookups (bounded: <=1 query each, called at most once per message)
# ---------------------------------------------------------------------------

class AnimeSearchResult(BaseModel):
    """metadata for one anime from a title search or season query."""
    model_config = ConfigDict(extra="ignore")
    id: int
    title: _MediaTitle | None = None
    genres: list[str] = []
    episodes: int | None = None
    averageScore: int | None = None
    status: str | None = None
    description: str | None = None
    format: str | None = None
    season: str | None = None
    seasonYear: int | None = None

    @property
    def display_title(self) -> str:
        if self.title:
            return self.title.english or self.title.romaji or "Unknown"
        return "Unknown"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.display_title,
            "genres": self.genres,
            "episodes": self.episodes,
            "average_score": self.averageScore,
            "status": self.status,
            "description": self.description,
            "format": self.format,
            "season": self.season,
            "season_year": self.seasonYear,
        }


_MEDIA_FIELDS = """id title { romaji english } genres episodes averageScore
    status description(asHtml: false) format season seasonYear"""

_SEASON_QUERY = """
query ($season: MediaSeason, $seasonYear: Int) {
  Page(perPage: 20) {
    media(season: $season, seasonYear: $seasonYear, type: ANIME,
          sort: POPULARITY_DESC, status: RELEASING) {
      %s
    }
  }
}
""" % _MEDIA_FIELDS


def _current_season_vars() -> dict:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    month = now.month
    year = now.year
    if month in (1, 2, 3):
        season = "WINTER"
    elif month in (4, 5, 6):
        season = "SPRING"
    elif month in (7, 8, 9):
        season = "SUMMER"
    else:
        season = "FALL"
    return {"season": season, "seasonYear": year}


async def search_anime(token: str, titles: list[str]) -> list[AnimeSearchResult]:
    """batch title search in one GraphQL query using field aliases.

    capped at 5 titles to keep query size reasonable. returns found results only
    (unmatched aliases are absent from the response, not an error).
    """
    if not titles:
        return []

    # cap at 5 to stay within reasonable query size
    capped = titles[:5]

    # build aliased query: t0: Media(search: "...", type: ANIME) { fields }
    alias_blocks = "\n".join(
        f't{i}: Media(search: {json.dumps(t)}, type: ANIME) {{ {_MEDIA_FIELDS} }}'
        for i, t in enumerate(capped)
    )
    query = f"query {{\n{alias_blocks}\n}}"

    data = await _query(token, query)

    results: list[AnimeSearchResult] = []
    for i in range(len(capped)):
        raw = data.get(f"t{i}")
        if raw:
            try:
                results.append(AnimeSearchResult.model_validate(raw))
            except Exception:
                continue
    return results


async def fetch_current_season(token: str) -> list[AnimeSearchResult]:
    """fetch top 20 currently airing anime for the current season."""
    vars_ = _current_season_vars()
    data = await _query(token, _SEASON_QUERY, vars_)
    raw_list = (data.get("Page") or {}).get("media") or []
    results: list[AnimeSearchResult] = []
    for raw in raw_list:
        try:
            results.append(AnimeSearchResult.model_validate(raw))
        except Exception:
            continue
    return results
