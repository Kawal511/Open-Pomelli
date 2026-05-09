import type { Platform, ScheduleItem, ScheduleOutput } from "./types";

export function formatScheduleOutput(calendar: ScheduleItem[]): ScheduleOutput {
  const platformDistribution: Record<Platform, number> = {
    instagram: 0,
    youtube: 0,
    twitter: 0,
    linkedin: 0,
  };

  for (const item of calendar) {
    platformDistribution[item.platform] += 1;
  }

  return {
    calendar,
    summary: {
      totalPosts: calendar.length,
      platformDistribution,
    },
  };
}

export function groupByDate(calendar: ScheduleItem[]): Record<string, Array<{ platform: Platform; time: string; contentType: string }>> {
  const grouped: Record<string, Array<{ platform: Platform; time: string; contentType: string }>> = {};

  for (const item of calendar) {
    if (!grouped[item.date]) {
      grouped[item.date] = [];
    }
    grouped[item.date].push({
      platform: item.platform,
      time: item.time,
      contentType: item.contentType,
    });
  }

  return grouped;
}
