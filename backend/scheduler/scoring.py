from __future__ import annotations

from backend.scheduler.data import BEST_DAYS, BEST_TIMES, PLATFORM_WEIGHT, CONTENT_MAPPING


def time_score(platform: str, hour: int) -> float:
    best = BEST_TIMES.get(platform, [])
    if hour in best:
        return 1.0
    if any(abs(hour - candidate) <= 1 for candidate in best):
        return 0.6
    return 0.5


def day_score(platform: str, day: int) -> float:
    return 1.0 if day in BEST_DAYS.get(platform, []) else 0.7


def content_score(platform: str, content_type: str) -> float:
    native = CONTENT_MAPPING.get(platform, [])
    return 1.0 if content_type in native else 0.8


def calculate_score(platform: str, hour: int, day: int, content_type: str) -> tuple[float, str]:
    t_score = time_score(platform, hour)
    d_score = day_score(platform, day)
    p_weight = PLATFORM_WEIGHT.get(platform, 0.8)
    c_score = content_score(platform, content_type)

    score = (t_score * 0.4) + (d_score * 0.3) + (p_weight * 0.2) + (c_score * 0.1)
    reasoning = "\n".join(
        [
            "Chosen because:",
            f"- {hour:02d}:00 is {'peak' if t_score == 1.0 else 'near-peak'} {platform} engagement",
            f"- day score is {d_score:.1f} for this platform",
            f"- platform weight is {p_weight:.2f}",
            f"- content matches platform preference score {c_score:.2f}",
        ]
    )
    return round(score, 3), reasoning
