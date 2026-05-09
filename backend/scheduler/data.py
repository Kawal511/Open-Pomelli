from __future__ import annotations

BEST_TIMES: dict[str, list[int]] = {
    "instagram": [9, 12, 18, 21],
    "youtube": [12, 15, 20],
    "twitter": [8, 13, 17],
    "linkedin": [9, 11, 17],
}

BEST_DAYS: dict[str, list[int]] = {
    "instagram": [1, 3, 5],
    "youtube": [2, 4, 6],
    "twitter": [1, 2, 3, 4, 5],
    "linkedin": [1, 2, 3, 4],
}

PLATFORM_WEIGHT: dict[str, float] = {
    "instagram": 1.0,
    "youtube": 0.9,
    "twitter": 0.8,
    "linkedin": 0.85,
}

CONTENT_MAPPING: dict[str, list[str]] = {
    "instagram": ["post", "reel", "carousel"],
    "youtube": ["video"],
    "twitter": ["post"],
    "linkedin": ["post", "carousel"],
}
