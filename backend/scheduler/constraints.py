from __future__ import annotations

from collections import defaultdict


def _week_bucket(date_str: str) -> str:
    year, month, day = [int(part) for part in date_str.split("-")]
    day_of_year = (month - 1) * 31 + day
    week = (day_of_year + 6) // 7
    return f"{year}-W{week:02d}"


def apply_constraints(candidates: list[dict], posts_per_day: int = 3) -> list[dict]:
    sorted_candidates = sorted(
        candidates,
        key=lambda item: (-float(item["score"]), item["date"], item["platform"], item["time"]),
    )

    per_day_count: dict[str, int] = defaultdict(int)
    per_day_times: dict[str, set[str]] = defaultdict(set)
    per_day_last_platform: dict[str, str] = {}
    weekly_platform_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    selected: list[dict] = []
    for candidate in sorted_candidates:
        date = str(candidate["date"])
        platform = str(candidate["platform"])
        time = str(candidate["time"])

        if per_day_count[date] >= posts_per_day:
            continue
        if time in per_day_times[date]:
            continue
        if per_day_last_platform.get(date) == platform:
            continue

        bucket = _week_bucket(date)
        platform_map = weekly_platform_counts[bucket]
        min_count = min(platform_map.values()) if platform_map else 0
        current_count = platform_map.get(platform, 0)
        if current_count > min_count + 1:
            continue

        selected.append(candidate)
        per_day_count[date] += 1
        per_day_times[date].add(time)
        per_day_last_platform[date] = platform
        platform_map[platform] = current_count + 1

    return sorted(selected, key=lambda item: (item["date"], -float(item["score"])))
