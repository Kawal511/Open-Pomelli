export type Platform = "instagram" | "youtube" | "twitter" | "linkedin";

export type ContentType = "post" | "reel" | "video" | "carousel";

export interface ScheduleInput {
  platforms: Platform[];
  startDate: string;
  days: number;
  postsPerDay?: number;
  markets?: string[];
  contentTypes?: ContentType[];
}

export interface ScheduleItem {
  date: string;
  dayOfWeek: string;
  platform: Platform;
  time: string;
  contentType: ContentType;
  score: number;
  reasoning: string;
}

export interface ScheduleOutput {
  calendar: ScheduleItem[];
  summary: {
    totalPosts: number;
    platformDistribution: Record<Platform, number>;
  };
}
