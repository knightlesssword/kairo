"""AniList GraphQL client.

all functions accept a plain decrypted access token. callers (sync_service) are
responsible for:
  1. calling anilist_guard.assert_token_valid before invoking here
  2. calling anilist_guard.handle_unauthorized on AniListAuthError

pydantic models use extra="ignore" so unknown fields from the API are silently dropped
rather than causing parse failures when AniList adds new fields.
"""

from __future__ import annotations

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
