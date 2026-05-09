from __future__ import annotations


def to_ui_grouped(calendar: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for item in calendar:
        grouped.setdefault(str(item["date"]), []).append(
            {
                "platform": item["platform"],
                "time": item["time"],
                "contentType": item["content_type"],
            }
        )
    return grouped


def to_output(calendar: list[dict]) -> dict:
    distribution = {
        "instagram": 0,
        "youtube": 0,
        "twitter": 0,
        "linkedin": 0,
    }
    for item in calendar:
        platform = str(item["platform"])
        if platform in distribution:
            distribution[platform] += 1

    return {
        "calendar": calendar,
        "summary": {
            "totalPosts": len(calendar),
            "platformDistribution": distribution,
        },
    }
