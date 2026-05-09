from __future__ import annotations

from datetime import datetime, timedelta

from backend.scheduler.constraints import apply_constraints
from backend.scheduler.data import BEST_TIMES, CONTENT_MAPPING
from backend.scheduler.formatter import to_output
from backend.scheduler.scoring import calculate_score


def _day_name(date_obj: datetime) -> str:
    return date_obj.strftime("%A")


def _to_time(hour: int) -> str:
    return f"{hour:02d}:00"


def generate_schedule(payload: dict) -> dict:
    platforms = [str(item).lower() for item in payload.get("platforms", ["instagram", "youtube"]) if str(item).strip()]
    if not platforms:
        platforms = ["instagram", "youtube"]

    start_date = str(payload.get("startDate") or payload.get("start_date") or "").strip()
    if not start_date:
        raise ValueError("startDate is required")

    days = int(payload.get("days", 30))
    posts_per_day = int(payload.get("postsPerDay") or payload.get("posts_per_day") or 3)
    markets = [str(item).strip() for item in payload.get("markets", ["Global"]) if str(item).strip()] or ["Global"]
    content_types = [str(item).lower().strip() for item in payload.get("contentTypes", payload.get("content_types", [])) if str(item).strip()]

    start = datetime.strptime(start_date, "%Y-%m-%d")
    candidates: list[dict] = []

    for day_index in range(days):
        date_obj = start + timedelta(days=day_index)
        date_str = date_obj.strftime("%Y-%m-%d")
        js_day = (date_obj.weekday() + 1) % 7
        market = markets[day_index % len(markets)]

        for platform in platforms:
            times = BEST_TIMES.get(platform, [9, 18])
            content_map = CONTENT_MAPPING.get(platform, ["post"])
            active_content = [item for item in content_map if not content_types or item in content_types]
            if not active_content:
                active_content = content_map

            for idx, hour in enumerate(times):
                content_type = active_content[idx % len(active_content)]
                score, reasoning = calculate_score(platform, hour, js_day, content_type)
                candidates.append(
                    {
                        "date": date_str,
                        "dayOfWeek": _day_name(date_obj),
                        "market": market,
                        "platform": platform,
                        "time": _to_time(hour),
                        "content_type": content_type,
                        "score": score,
                        "reasoning": f"{reasoning}\n- market context: {market}",
                    }
                )

    calendar = apply_constraints(candidates, posts_per_day=posts_per_day)
    return to_output(calendar)
