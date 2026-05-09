import type { ContentType, Platform } from "./types";

export const BEST_TIMES: Record<Platform, number[]> = {
  instagram: [9, 12, 18, 21],
  youtube: [12, 15, 20],
  twitter: [8, 13, 17],
  linkedin: [9, 11, 17],
};

export const BEST_DAYS: Record<Platform, number[]> = {
  instagram: [1, 3, 5],
  youtube: [2, 4, 6],
  twitter: [1, 2, 3, 4, 5],
  linkedin: [1, 2, 3, 4],
};

export const PLATFORM_WEIGHT: Record<Platform, number> = {
  instagram: 1.0,
  youtube: 0.9,
  twitter: 0.8,
  linkedin: 0.85,
};

export const CONTENT_DISTRIBUTION: Record<Platform, ContentType[]> = {
  instagram: ["post", "reel", "carousel"],
  youtube: ["video"],
  twitter: ["post"],
  linkedin: ["post", "carousel"],
};

export const CONTENT_WEIGHT: Record<ContentType, number> = {
  post: 0.8,
  reel: 1.0,
  video: 0.9,
  carousel: 0.95,
};
