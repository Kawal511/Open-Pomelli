from __future__ import annotations

import unittest

from backend.scheduler import generate_schedule


class SchedulerTests(unittest.TestCase):
    def test_single_platform(self) -> None:
        result = generate_schedule(
            {
                "platforms": ["instagram"],
                "startDate": "2026-04-15",
                "days": 3,
                "postsPerDay": 2,
            }
        )
        self.assertTrue(len(result["calendar"]) > 0)
        self.assertTrue(all(item["platform"] == "instagram" for item in result["calendar"]))

    def test_multi_platform(self) -> None:
        result = generate_schedule(
            {
                "platforms": ["instagram", "youtube", "linkedin"],
                "startDate": "2026-04-15",
                "days": 7,
                "postsPerDay": 3,
            }
        )
        platforms = {item["platform"] for item in result["calendar"]}
        self.assertTrue("instagram" in platforms)
        self.assertTrue("youtube" in platforms or "linkedin" in platforms)

    def test_one_day(self) -> None:
        result = generate_schedule(
            {
                "platforms": ["instagram", "twitter"],
                "startDate": "2026-04-15",
                "days": 1,
                "postsPerDay": 3,
            }
        )
        dates = {item["date"] for item in result["calendar"]}
        self.assertEqual(len(dates), 1)

    def test_thirty_days(self) -> None:
        result = generate_schedule(
            {
                "platforms": ["instagram", "youtube", "twitter", "linkedin"],
                "startDate": "2026-04-15",
                "days": 30,
                "postsPerDay": 3,
            }
        )
        dates = {item["date"] for item in result["calendar"]}
        self.assertEqual(len(dates), 30)

    def test_no_duplicate_time_slots_per_day(self) -> None:
        result = generate_schedule(
            {
                "platforms": ["instagram", "youtube", "twitter"],
                "startDate": "2026-04-15",
                "days": 10,
                "postsPerDay": 3,
            }
        )
        seen: dict[str, set[str]] = {}
        for item in result["calendar"]:
            seen.setdefault(item["date"], set())
            self.assertNotIn(item["time"], seen[item["date"]])
            seen[item["date"]].add(item["time"])

    def test_scoring_descending_by_day(self) -> None:
        result = generate_schedule(
            {
                "platforms": ["instagram", "youtube", "twitter"],
                "startDate": "2026-04-15",
                "days": 5,
                "postsPerDay": 3,
            }
        )
        grouped: dict[str, list[float]] = {}
        for item in result["calendar"]:
            grouped.setdefault(item["date"], []).append(float(item["score"]))

        for scores in grouped.values():
            sorted_scores = sorted(scores, reverse=True)
            self.assertEqual(scores, sorted_scores)


if __name__ == "__main__":
    unittest.main()
