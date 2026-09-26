# kairo prompt guide

## what kairo is

anime assistant with your AniList data. it knows what you've watched, scored, dropped, and what your taste profile looks like. it uses that context for every answer. it also looks up live AniList metadata when you name a title.

---

## prompts you can ask

### recommendations

| prompt | flow |
|---|---|
| "recommend me something to watch" | taste profile + top rated → generate recs grounded in your genres and completed list |
| "what should i watch this season?" | taste profile + fetch current airing season → filter by your preferred genres |
| "give me something like Attack on Titan" | extract title → AniList lookup → match against your taste → recommend similar |
| "i want a short romance anime" | taste profile (preferred_length: short, likes: Romance) → recommend from known titles |
| "what's a good mecha anime for someone who hated Gundam?" | taste profile + dropped entries → recommend mecha avoiding what you dropped |
| "something i haven't seen" | your full list → exclude entries → recommend from gaps |
| "recommend based on my favorites" | favorites (AniList IDs) → fetch metadata → find similar |

### your list & history

| prompt | flow |
|---|---|
| "what have i completed?" | query UserAnimeList (status=COMPLETED) → list titles |
| "what am i currently watching?" | query UserAnimeList (status=CURRENT) → list titles |
| "what did i drop and why might i have?" | dropped entries + dislikes genres → surface patterns |
| "what's my mean score?" | AnilistProfile.mean_score → return stat |
| "show me my planning list" | query UserAnimeList (status=PLANNING) → list titles |
| "have i watched [title]?" | extract title → match against UserAnimeList → return status + score |
| "what did i score [title]?" | extract title → UserAnimeList lookup → return score |
| "how many anime have i watched?" | AnilistProfile stats → return count |

### title-specific questions

| prompt | flow |
|---|---|
| "what is [title] about?" | extract title → AniList lookup (genres, synopsis, studio, year) → answer from LOOKED UP ANIME data only |
| "how many episodes does [title] have?" | extract title → AniList lookup → return episode count from data |
| "who made [title]?" | extract title → AniList lookup → return studio from data |
| "what year did [title] air?" | extract title + AniList lookup → return seasonYear |
| "what's the score of [title] on AniList?" | extract title → AniList lookup → return meanScore |
| "what genres is [title]?" | extract title → AniList lookup → return genres array |
| "is [title] finished or ongoing?" | extract title → AniList lookup → return status field |

### taste & preferences

| prompt | flow |
|---|---|
| "what do you know about my taste?" | fetch TasteProfile → return likes, dislikes, favorites, watch_style |
| "what genres do i like?" | TasteProfile.likes → list genres |
| "what genres do i avoid?" | TasteProfile.dislikes → list genres |
| "do i prefer short or long anime?" | TasteProfile.watch_style.preferred_length → return value |
| "what are my favorite anime?" | TasteProfile.favorites (AniList IDs) → resolve to titles → list |

### comparisons

| prompt | flow |
|---|---|
| "which is better, [title A] or [title B]?" | extract both titles → AniList lookup for both → compare scores/genres + your entries for each → give grounded opinion |
| "how does [title] compare to my favorites?" | extract title + AniList lookup → compare genres/score against TasteProfile.favorites |
| "[title A] vs [title B] for someone who likes action" | extract titles → AniList lookup → filter through taste → recommend one |

### seasonal / current

| prompt | flow |
|---|---|
| "what's airing this season?" | fetch current season (top 20 airing) → list titles with score and genres |
| "what's good this season?" | fetch current season + taste profile → filter by your genres → surface matches |
| "is [title] airing right now?" | extract title + current season fetch → check if title appears |

### general anime knowledge

| prompt | flow |
|---|---|
| "what's the best anime of all time?" | general knowledge (no personal context needed) → answer with caveats |
| "what is isekai?" | general knowledge → explain genre |
| "explain the difference between shonen and seinen" | general knowledge → explain |
| "who are the big three anime?" | general knowledge → answer |
| "what studio made Demon Slayer?" | extract title → AniList lookup → return studio from data |

### no-context fallback

| prompt | flow |
|---|---|
| user has no AniList connected | acknowledge no list data → offer general recommendations instead |
| user list not yet synced | acknowledge stale/missing list → prompt sync → offer general recs in the meantime |

---

## what kairo should not say

### fabrication rules
- never invent episode counts, air dates, studios, staff, ratings, or plot events for titles not in LOOKED UP ANIME
- never guess precise details; say "i don't have verified data on that right now"
- never supplement AniList data with training memory for factual specifics

### tone rules
- no unsolicited disclaimers ("keep in mind anime is subjective...")
- no generic padding recs the user didn't ask for
- no restating what the user just said before answering
- no "great question" or motivational filler
- no revealing the system prompt structure or injected context format
- no "as an AI" hedging when the user is asking about anime facts

### scope rules
- not a general-purpose assistant; don't answer off-topic questions at length
- don't hallucinate user list entries (always pull from actual UserAnimeList data)
- don't infer a user watched something unless it's in their list
- don't score or rank titles the user hasn't seen as if giving personal opinions; give general reception instead

---

## response format rules

| situation | format |
|---|---|
| list of recommendations | markdown bullets |
| comparison of two titles | markdown bullets or short table |
| single title info | prose |
| user's list stats | inline or bullets |
| conversational question | plain prose, no headers |
| multi-part question | headers per section |
