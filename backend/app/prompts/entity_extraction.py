"""Prompt for conditional entity extraction from a user chat message.

used by the heuristic gate in chat_service when the message plausibly references
a specific anime title or asks about current/airing season.

output: {anime_titles: list[str], wants_current_season: bool}
"""

from __future__ import annotations

# JSON schema for response_schema enforcement in chat() call
ENTITY_EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "anime_titles": {
            "type": "array",
            "items": {"type": "string"},
            "description": "exact or near-exact anime titles mentioned in the message",
        },
        "wants_current_season": {
            "type": "boolean",
            "description": "true if the user is asking about currently airing or this season's anime",
        },
    },
    "required": ["anime_titles", "wants_current_season"],
    "additionalProperties": False,
}

ENTITY_EXTRACTION_SYSTEM = (
    "You are a data extraction assistant. Output only valid JSON. No commentary."
)


def build_entity_extraction_prompt(user_message: str) -> str:
    return f"""\
Extract structured information from this anime-related message.

MESSAGE: {user_message}

Return ONLY valid JSON - no explanation, no markdown fences:
{{
  "anime_titles": ["<title>", ...],
  "wants_current_season": <true|false>
}}

Rules:
- anime_titles: only extract titles that are clearly named; empty list if none
- wants_current_season: true only if the user asks about airing/this season/current season
"""
