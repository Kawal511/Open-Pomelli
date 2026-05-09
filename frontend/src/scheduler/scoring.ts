import { BEST_DAYS, BEST_TIMES, CONTENT_WEIGHT, PLATFORM_WEIGHT } from "./data";
import type { ContentType, Platform } from "./types";

export type ScoreWeights = {
  time: number;
  day: number;
  platform: number;
  content: number;
};

export const DEFAULT_WEIGHTS: ScoreWeights = {
  time: 0.4,
  day: 0.3,
  platform: 0.2,
  content: 0.1,
};

export function getTimeScore(platform: Platform, hour: number): number {
  const best = BEST_TIMES[platform];
  if (best.includes(hour)) {
    return 1;
  }
  const near = best.some((candidate) => Math.abs(candidate - hour) <= 1);
  return near ? 0.6 : 0.5;
}

export function getDayScore(platform: Platform, day: number): number {
  const best = BEST_DAYS[platform];
  return best.includes(day) ? 1 : 0.7;
}

export function getContentScore(contentType: ContentType): number {
  return CONTENT_WEIGHT[contentType] ?? 0.7;
}

export function calculateScore(
  platform: Platform,
  hour: number,
  day: number,
  contentType: ContentType,
  weights: ScoreWeights = DEFAULT_WEIGHTS
): {
  score: number;
  reasoning: string;
  breakdown: {
    timeScore: number;
    dayScore: number;
    platformScore: number;
    contentScore: number;
  };
} {
  const timeScore = getTimeScore(platform, hour);
  const dayScore = getDayScore(platform, day);
  const platformScore = PLATFORM_WEIGHT[platform];
  const contentScore = getContentScore(contentType);

  const score =
    timeScore * weights.time +
    dayScore * weights.day +
    platformScore * weights.platform +
    contentScore * weights.content;

  const reasoning = [
    "Chosen because:",
    `- ${String(hour).padStart(2, "0")}:00 is ${timeScore >= 1 ? "peak" : "near-peak"} ${platform} engagement`,
    `- day score is ${dayScore.toFixed(1)} for this platform`,
    `- platform weight is ${platformScore.toFixed(2)}`,
    `- content compatibility is ${contentScore.toFixed(2)}`,
  ].join("\n");

  return {
    score: Number(score.toFixed(3)),
    reasoning,
    breakdown: {
      timeScore,
      dayScore,
      platformScore,
      contentScore,
    },
  };
}
