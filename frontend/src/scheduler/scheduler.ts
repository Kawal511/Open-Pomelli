import { BEST_TIMES, CONTENT_DISTRIBUTION } from "./data";
import { calculateScore } from "./scoring";
import { applyConstraints } from "./constraints";
import { formatScheduleOutput } from "./formatter";
import type { ScheduleInput, ScheduleItem, ScheduleOutput } from "./types";

function toDateString(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function toTime(hour: number): string {
  return `${String(hour).padStart(2, "0")}:00`;
}

function dayName(date: Date): string {
  return date.toLocaleDateString("en-US", { weekday: "long" });
}

export function generateSchedule(input: ScheduleInput): ScheduleOutput {
  const {
    platforms,
    markets = ["Global"],
    contentTypes,
    startDate,
    days,
    postsPerDay = 3,
  } = input;

  const candidates: ScheduleItem[] = [];
  const start = new Date(startDate);

  if (!Number.isFinite(start.getTime())) {
    throw new Error("Invalid startDate. Use YYYY-MM-DD format.");
  }

  for (let i = 0; i < days; i++) {
    const currentDate = addDays(start, i);
    const day = currentDate.getDay();
    const date = toDateString(currentDate);
    const market = markets[i % markets.length] || "Global";

    for (const platform of platforms) {
      const times = BEST_TIMES[platform];
      const defaultContent = CONTENT_DISTRIBUTION[platform];
      const availableContent = contentTypes && contentTypes.length > 0
        ? defaultContent.filter((item) => contentTypes.includes(item))
        : defaultContent;
      const contentPool = availableContent.length > 0 ? availableContent : defaultContent;

      for (let idx = 0; idx < times.length; idx++) {
        const hour = times[idx];
        const contentType = contentPool[idx % contentPool.length];
        const scored = calculateScore(platform, hour, day, contentType);

        candidates.push({
          date,
          dayOfWeek: dayName(currentDate),
          platform,
          time: toTime(hour),
          contentType,
          score: scored.score,
          reasoning: `${scored.reasoning}\n- market context: ${market}`,
        });
      }
    }
  }

  const constrained = applyConstraints(candidates, Math.max(1, Math.trunc(postsPerDay)));
  return formatScheduleOutput(constrained);
}
