"""Prompt for LLM-generated taste profile.

input:  compact summary of the user's scored/completed/dropped anime entries
output: JSON matching TasteProfileSchema
        {likes, dislikes, favorites, watch_style: {prefers_completed, preferred_length}}
"""

from __future__ import annotations


def build_taste_extraction_prompt(entries_summary: str) -> str:
    """build the user-turn message for taste profile generation.

    entries_summary is a compact plaintext block, one entry per line:
      <title> | <status> | score:<score> | genres:<g1,g2>
    caller is responsible for trimming to a reasonable token count before passing in.
    """
    return f"""\
Analyze the following anime list and generate a taste profile as JSON.

ANIME LIST:
{entries_summary}

Return ONLY valid JSON matching this exact structure - no explanation, no markdown fences:
{{
  "likes": ["<qualitative descriptor>", ...],
  "dislikes": ["<qualitative descriptor>", ...],
  "favorites": ["<anime title>", ...],
  "watch_style": {{
    "prefers_completed": <true|false>,
    "preferred_length": "<short|medium|long>"
  }}
}}

Rules:
- likes/dislikes: qualitative descriptors (themes, pacing, tone, tropes) — not genre names, not anime titles
- favorites: actual titles from the list with score >= 8 only; unscored entries do not qualify
- prefers_completed: true if COMPLETED count > PLANNING + CURRENT count combined
- preferred_length: short (<13 eps), medium (13-50 eps), long (>50 eps) — pick the mode by count of COMPLETED entries only
- minimum 2 items in likes; minimum 1 in favorites if any qualify
- if the list is too sparse to infer preferences, use reasonable defaults
"""


TASTE_EXTRACTION_SYSTEM = (
    "You are a data extraction assistant. Output only valid JSON. No commentary."
)
