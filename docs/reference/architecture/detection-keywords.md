---
title: Detection Keyword Service
parent: Architecture
grand_parent: Technical Reference
nav_order: 6
docs_version: "2.3.1"
---

# Detection Keyword Service

The `DetectionKeywordService` provides centralized pattern-based detection for stream classification. This service abstracts the source of detection patterns, enabling future database-backed customization.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        API / Consumer Layer                          │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  classifier.py              │  stream_filter.py                      │
│  - classify_stream()        │  - is_placeholder()                    │
│  - is_event_card()          │  - detect_sport_hint()                 │
│  - detect_league_hint()     │  - FilterService                       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    DetectionKeywordService                           │
│  ─────────────────────────────────────────────────────────────────  │
│  Pattern Accessors:                                                  │
│  - get_combat_keywords()       - get_league_hints()                  │
│  - get_sport_hints()           - get_placeholder_patterns()          │
│  - get_card_segment_patterns() - get_exclusion_patterns()            │
│  - get_separators()                                                  │
│  ─────────────────────────────────────────────────────────────────  │
│  Detection Methods:                                                  │
│  - is_combat_sport(text)       - detect_league(text)                 │
│  - detect_sport(text)          - is_placeholder(text)                │
│  - detect_card_segment(text)   - is_excluded(text)                   │
│  - find_separator(text)                                              │
│  ─────────────────────────────────────────────────────────────────  │
│  Cache Management:                                                   │
│  - invalidate_cache()          - warm_cache()                        │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 1: constants.py          │  Phase 2: Database (future)        │
│  - COMBAT_SPORTS_KEYWORDS       │  - detection_keywords table         │
│  - LEAGUE_HINT_PATTERNS         │  - User-defined patterns            │
│  - PLACEHOLDER_PATTERNS         │  - Runtime customization            │
│  - ...                          │                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Design Principles

### 1. Layer Separation

**Classifier and filter modules should NOT:**
- Import pattern constants directly
- Compile regex patterns themselves
- Have hardcoded detection logic

**Classifier and filter modules SHOULD:**
- Call DetectionKeywordService methods
- Handle orchestration logic only
- Remain unaware of pattern sources

### 2. Pattern Sources

**Phase 1 (Current):** Built-in patterns from `teamarr/utilities/constants.py` plus user-defined patterns from the `detection_keywords` database table (managed via the Detection Library UI).

- COMBAT_SPORTS_KEYWORDS (100+ keywords)
- LEAGUE_HINT_PATTERNS (70+ patterns, including multi-league umbrellas)
- SPORT_HINT_PATTERNS (38 patterns, including multi-sport hints)
- PLACEHOLDER_PATTERNS (19 patterns)
- CARD_SEGMENT_PATTERNS (8 patterns)
- COMBAT_SPORTS_EXCLUDE_PATTERNS (13 patterns)
- GAME_SEPARATORS (10 separators: vs, @, at, v, x, contre, gegen, contra)

User-defined patterns (league hints, sport hints, event type keywords) are stored in the `detection_keywords` table and managed through **Detection Library** in the UI. These extend the built-in patterns.

**Phase 2 (Future):** Full database-backed override of all pattern categories
- User patterns override built-in defaults
- Runtime modification without restart

### 3. Pattern Caching

Patterns are compiled once and cached at class level:
- Lazy initialization on first access
- No recompilation overhead
- `invalidate_cache()` for testing or DB updates

### 4. Word Boundary Matching

Combat sports keywords use word boundary matching (`\b`) to avoid false positives:
- "wbo" matches "WBO Championship" but NOT "Cowboys"
- "pbc" matches "PBC Boxing" but NOT embedded substrings

## Stream Classification Flow

```
Stream Name
     │
     ▼
┌─────────────────────┐
│ 1. Placeholder?     │──Yes──▶ Skip (no event info)
└─────────────────────┘
     │ No
     ▼
┌─────────────────────┐
│ 2. Combat Sports?   │──Yes──▶ EVENT_CARD category
└─────────────────────┘         (UFC, Boxing, MMA)
     │ No
     ▼
┌─────────────────────┐
│ 3. Has Separator?   │──Yes──▶ TEAM_VS_TEAM category
└─────────────────────┘         (NFL, NBA, Soccer)
     │ No
     ▼
    Fallback logic

Note: skip_builtin_filter bypasses steps 1-2 in stream_filter.py
```

## skip_builtin_filter Option

Groups can set `skip_builtin_filter=True` to bypass built-in filtering:
- Placeholder detection skipped
- Unsupported sport detection skipped
- Custom regex still applies

This allows users to match streams that would normally be filtered (e.g., individual sports like golf or tennis that Teamarr can't schedule-match but user wants in EPG).

## Multi-Sport Hints

Some keywords are ambiguous across sports. Sport hints support multi-sport targets:

```python
# Single sport
"hockey" → "Hockey"

# Multiple sports (bare "football" is ambiguous)
"football" → ["Soccer", "Football"]
```

When a multi-sport hint matches, the matcher tries all listed sports. In stream filtering, a stream is only excluded if **all** its hinted sports are unsupported.

Multi-sport targets are stored as JSON arrays in the database (`'["Soccer", "Football"]'`) and parsed back to lists. Single-element arrays are collapsed to plain strings.

## Multi-League Hints

League hints can map to multiple leagues for umbrella brands:

| Keyword | Maps To |
|---------|---------|
| `EFL` | `eng.2`, `eng.3`, `eng.4`, `eng.fa` |
| `Bundesliga` | `ger.1`, `ger.2` |
| `CHL` | `ohl`, `whl`, `qmjhl` |
| `NCAAB` | `mens-college-basketball`, `womens-college-basketball` |

When a stream matches a multi-league hint, the matcher tries events from all listed leagues.

## Usage Examples

```python
from teamarr.services.detection_keywords import DetectionKeywordService

# Check if stream is combat sports
if DetectionKeywordService.is_combat_sport("UFC 315: Main Card"):
    # Handle EVENT_CARD classification

# Detect league from stream name
league = DetectionKeywordService.detect_league("NFL: Cowboys vs Eagles")
# Returns: "nfl"

# Umbrella brands return lists
league = DetectionKeywordService.detect_league("EFL: Team A vs Team B")
# Returns: ["eng.2", "eng.3", "eng.4", "eng.fa"]

# Pre-warm cache on startup
stats = DetectionKeywordService.warm_cache()
# Returns: {'combat_keywords': 45, 'league_hints': 59, ...}
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/detection-keywords` | List all keywords |
| GET | `/api/v1/detection-keywords/categories` | Describe available categories |
| GET | `/api/v1/detection-keywords/{category}` | Filter by category |
| POST | `/api/v1/detection-keywords` | Create keyword |
| PUT | `/api/v1/detection-keywords/id/{id}` | Update keyword |
| DELETE | `/api/v1/detection-keywords/id/{id}` | Delete keyword |
| POST | `/api/v1/detection-keywords/import` | Bulk import (upsert) |
| GET | `/api/v1/detection-keywords/export` | Export keywords as JSON |

## File Locations

| Component | Location |
|-----------|----------|
| Service | `teamarr/services/detection_keywords.py` |
| Classifier | `teamarr/consumers/matching/classifier.py` |
| Stream Filter | `teamarr/services/stream_filter.py` |
| Constants | `teamarr/utilities/constants.py` |
| DB CRUD | `teamarr/database/detection_keywords.py` |
| API Routes | `teamarr/api/routes/detection_keywords.py` |
