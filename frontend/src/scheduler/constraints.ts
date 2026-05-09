import type { ScheduleItem } from "./types";

type MutableCounters = {
  perDayCount: Map<string, number>;
  perDayTimes: Map<string, Set<string>>;
  perWeekPlatform: Map<string, Map<string, number>>;
  lastPlatformByDay: Map<string, string>;
};

function weekBucket(date: string): string {
  const dt = new Date(date);
  const first = new Date(dt.getFullYear(), 0, 1);
  const dayOfYear = Math.floor((dt.getTime() - first.getTime()) / 86400000) + 1;
  const week = Math.ceil(dayOfYear / 7);
  return `${dt.getFullYear()}-W${String(week).padStart(2, "0")}`;
}

function canUseByDiversity(item: ScheduleItem, counters: MutableCounters): boolean {
  const bucket = weekBucket(item.date);
  const platformCounts = counters.perWeekPlatform.get(bucket) ?? new Map<string, number>();
  const entries = Array.from(platformCounts.values());
  const minCount = entries.length > 0 ? Math.min(...entries) : 0;
  const current = platformCounts.get(item.platform) ?? 0;
  return current <= minCount + 1;
}

function mark(item: ScheduleItem, counters: MutableCounters): void {
  counters.perDayCount.set(item.date, (counters.perDayCount.get(item.date) ?? 0) + 1);
  const times = counters.perDayTimes.get(item.date) ?? new Set<string>();
  times.add(item.time);
  counters.perDayTimes.set(item.date, times);

  const bucket = weekBucket(item.date);
  const platformCounts = counters.perWeekPlatform.get(bucket) ?? new Map<string, number>();
  platformCounts.set(item.platform, (platformCounts.get(item.platform) ?? 0) + 1);
  counters.perWeekPlatform.set(bucket, platformCounts);

  counters.lastPlatformByDay.set(item.date, item.platform);
}

export function applyConstraints(candidates: ScheduleItem[], postsPerDay: number): ScheduleItem[] {
  const sorted = [...candidates].sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    if (a.date !== b.date) return a.date.localeCompare(b.date);
    if (a.platform !== b.platform) return a.platform.localeCompare(b.platform);
    return a.time.localeCompare(b.time);
  });

  const counters: MutableCounters = {
    perDayCount: new Map<string, number>(),
    perDayTimes: new Map<string, Set<string>>(),
    perWeekPlatform: new Map<string, Map<string, number>>(),
    lastPlatformByDay: new Map<string, string>(),
  };

  const selected: ScheduleItem[] = [];

  for (const item of sorted) {
    const usedCount = counters.perDayCount.get(item.date) ?? 0;
    if (usedCount >= postsPerDay) continue;

    const usedTimes = counters.perDayTimes.get(item.date) ?? new Set<string>();
    if (usedTimes.has(item.time)) continue;

    const lastPlatform = counters.lastPlatformByDay.get(item.date);
    if (lastPlatform === item.platform) continue;

    if (!canUseByDiversity(item, counters)) continue;

    selected.push(item);
    mark(item, counters);
  }

  return selected.sort((a, b) => {
    if (a.date !== b.date) return a.date.localeCompare(b.date);
    return b.score - a.score;
  });
}
