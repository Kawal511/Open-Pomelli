from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal

Platform = Literal["instagram", "youtube", "twitter", "linkedin"]
ContentType = Literal["post", "reel", "video", "carousel"]


@dataclass(frozen=True)
class ScheduleInput:
    platforms: List[Platform]
    start_date: str
    days: int
    posts_per_day: int = 3
    markets: List[str] = field(default_factory=lambda: ["Global"])
    content_types: List[ContentType] = field(default_factory=list)


@dataclass(frozen=True)
class ScheduleItem:
    date: str
    day_of_week: str
    platform: Platform
    time: str
    content_type: ContentType
    score: float
    reasoning: str


@dataclass(frozen=True)
class ScheduleOutput:
    calendar: List[ScheduleItem]
    summary: Dict[str, object]
