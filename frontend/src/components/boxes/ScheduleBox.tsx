import { useMemo, useState } from "react";
import type { CampaignStateResponse } from "../../types";
import { generateSchedule, type Platform } from "../../scheduler";

interface ScheduleBoxProps {
  campaign: CampaignStateResponse;
}

type SchedulePlatform = {
  name: string;
  time: string;
  reason: string;
  expected_reach?: string;
  color?: string;
};

type ScheduleDay = {
  day: number;
  date?: string;
  market: string;
  timezone: string;
  hook: string;
  score?: number;
  platform?: string;
  time?: string;
  reason?: string;
  platforms?: SchedulePlatform[];
};

function toDayPlatforms(day: ScheduleDay): SchedulePlatform[] {
  if (Array.isArray(day.platforms) && day.platforms.length > 0) {
    return day.platforms.map((item) => ({
      name: String(item.name || "platform"),
      time: String(item.time || "09:00"),
      reason: String(item.reason || "Deterministic scheduling rule."),
      expected_reach: item.expected_reach,
      color: item.color,
    }));
  }

  if (day.platform && day.time) {
    return [
      {
        name: String(day.platform),
        time: String(day.time),
        reason: String(day.reason || "Deterministic scheduling rule."),
        expected_reach: "1200",
      },
    ];
  }

  return [];
}

function dotClass(color?: string): string {
  const normalized = String(color || "").toLowerCase();
  if (normalized === "pink") return "schedule-dot schedule-dot-pink";
  if (normalized === "blue") return "schedule-dot schedule-dot-blue";
  if (normalized === "green") return "schedule-dot schedule-dot-green";
  return "schedule-dot schedule-dot-neutral";
}

function toShortDate(value?: string): string {
  if (!value) {
    return "n/a";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function plusMinutes(time: string, addMinutes: number): string {
  const [hRaw, mRaw] = String(time || "09:00").split(":");
  const h = Number(hRaw);
  const m = Number(mRaw);
  if (!Number.isFinite(h) || !Number.isFinite(m)) {
    return "18:30";
  }
  const total = (h * 60 + m + addMinutes) % (24 * 60);
  const hh = String(Math.floor(total / 60)).padStart(2, "0");
  const mm = String(total % 60).padStart(2, "0");
  return `${hh}:${mm}`;
}

function currentIsoDate(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function shiftIsoDate(baseIsoDate: string, dayOffset: number): string {
  const base = new Date(`${baseIsoDate}T00:00:00`);
  if (Number.isNaN(base.getTime())) {
    return baseIsoDate;
  }
  base.setDate(base.getDate() + Math.max(0, dayOffset));
  const y = base.getFullYear();
  const m = String(base.getMonth() + 1).padStart(2, "0");
  const d = String(base.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function toSchedulerPlatforms(rawChannels: string[]): Platform[] {
  const mapped = rawChannels
    .map((channel) => String(channel || "").trim().toLowerCase())
    .map((channel) => {
      if (channel === "instagram") return "instagram" as const;
      if (channel === "youtube") return "youtube" as const;
      if (channel === "twitter" || channel === "x") return "twitter" as const;
      if (channel === "linkedin") return "linkedin" as const;
      return null;
    })
    .filter((item): item is Platform => item !== null);

  if (mapped.length === 0) {
    return ["instagram", "youtube", "twitter", "linkedin"];
  }

  return Array.from(new Set(mapped));
}

function colorForPlatform(name: string): string {
  const key = String(name || "").toLowerCase();
  if (key === "instagram") return "pink";
  if (key === "youtube") return "blue";
  if (key === "twitter") return "green";
  if (key === "linkedin") return "blue";
  return "neutral";
}

function buildFallbackDays(campaign: CampaignStateResponse): ScheduleDay[] {
  const payload = (campaign.start_payload || {}) as Record<string, unknown>;
  const channels = Array.isArray(payload.channels)
    ? payload.channels.map((value) => String(value || ""))
    : [];
  const markets = Array.isArray(payload.target_markets)
    ? payload.target_markets.map((value) => String(value || "").trim()).filter(Boolean)
    : [];
  const platforms = toSchedulerPlatforms(channels);
  const strategy = (campaign.strategy || {}) as Record<string, unknown>;
  const hook = String(strategy.core_message || "Consistency-led campaign narrative").trim() || "Consistency-led campaign narrative";

  const output = generateSchedule({
    platforms,
    startDate: currentIsoDate(),
    days: 30,
    postsPerDay: 3,
    markets,
  });
  const rows = output.calendar;

  const grouped = new Map<string, typeof rows>();
  for (const row of rows) {
    const list = grouped.get(row.date) || [];
    list.push(row);
    grouped.set(row.date, list);
  }

  const orderedDates = Array.from(grouped.keys()).sort((a, b) => a.localeCompare(b));

  return orderedDates.map((date, index) => {
    const items = grouped.get(date) || [];
    const avgScore = items.length > 0
      ? items.reduce((sum, item) => sum + item.score, 0) / items.length
      : 0.8;

    const platformsForDay: SchedulePlatform[] = items.map((item) => ({
      name: item.platform,
      time: item.time,
      reason: `${item.reasoning} (content: ${item.contentType}, score: ${item.score.toFixed(2)})`,
      expected_reach: String(Math.round(900 + item.score * 700)),
      color: colorForPlatform(item.platform),
    }));

    return {
      day: index + 1,
      date,
      market: markets.length > 0 ? markets[index % markets.length] : "Global",
      timezone: "UTC",
      hook,
      score: Math.round(avgScore * 100),
      platforms: platformsForDay,
      platform: platformsForDay[0]?.name,
      time: platformsForDay[0]?.time,
      reason: platformsForDay[0]?.reason,
    };
  });
}

export function ScheduleBox({ campaign }: ScheduleBoxProps) {
  const schedule = campaign.schedule;
  const backendDays = Array.isArray(schedule?.days) ? (schedule.days as ScheduleDay[]) : [];
  const fallbackDays = useMemo(() => (backendDays.length > 0 ? [] : buildFallbackDays(campaign)), [backendDays.length, campaign]);
  const days = backendDays.length > 0 ? backendDays : fallbackDays;
  const normalizedDays = useMemo(() => {
    if (days.length === 0) {
      return [] as ScheduleDay[];
    }

    const knownDates = days
      .map((day) => String(day.date || "").trim())
      .filter((value) => value.length > 0);
    const anchorDate = knownDates.length > 0 ? knownDates[0] : currentIsoDate();

    return days.map((day, index) => {
      if (String(day.date || "").trim()) {
        return day;
      }
      const dayNumber = Number(day.day || index + 1);
      const offset = Number.isFinite(dayNumber) ? Math.max(0, dayNumber - 1) : index;
      return {
        ...day,
        date: shiftIsoDate(anchorDate, offset),
      };
    });
  }, [days]);

  const sortedDays = useMemo(
    () => [...normalizedDays].sort((a, b) => Number(a.day || 0) - Number(b.day || 0)),
    [normalizedDays]
  );
  const [selectedDayNumber, setSelectedDayNumber] = useState<number>(1);

  if (sortedDays.length === 0) {
    return (
      <article className="content-bento-card schedule-box-full">
        <p className="content-empty-note">No schedule generated yet.</p>
      </article>
    );
  }

  const selectedDay = sortedDays.find((day) => day.day === selectedDayNumber) || sortedDays[0];
  const selectedPlatforms = toDayPlatforms(selectedDay);
  const expectedReach = selectedPlatforms.reduce((sum, platform) => sum + Number(platform.expected_reach || 0), 0);
  const peakEngagement = selectedPlatforms.length > 0 ? plusMinutes(selectedPlatforms[0].time, 30) : "18:30";
  const riskFactor = expectedReach >= 1800 ? "Low" : expectedReach >= 1200 ? "Medium" : "Elevated";

  const alignmentLines = [
    selectedDay.hook ? `Matches active market hook: ${selectedDay.hook}` : "Matches active market trend timeline.",
    selectedPlatforms.length > 0
      ? `Capitalizes on ${selectedPlatforms.map((platform) => `${platform.name} ${platform.time}`).join(" + ")} windows.`
      : "Capitalizes on deterministic posting windows.",
  ];

  return (
    <article className="content-bento-card schedule-box-full">
      <div className="creative-section-head">
        <p className="mono overline">Campaign Calendar Engine</p>
        <p className="creative-section-count">30-day zero-LLM deterministic scheduler</p>
      </div>

      <div className="schedule-command-layout">
        <section className="schedule-heatmap-panel">
          <p className="mono overline">30-Day Heatmap</p>
          <div className="schedule-heatmap-grid">
            {sortedDays.map((day) => {
              const platforms = toDayPlatforms(day);
              return (
                <button
                  key={`day-${day.day}`}
                  type="button"
                  className={day.day === selectedDay.day ? "schedule-heatmap-cell schedule-heatmap-cell-active" : "schedule-heatmap-cell"}
                  onClick={() => setSelectedDayNumber(day.day)}
                >
                  <p className="mono">D{day.day}</p>
                  <p className="schedule-heatmap-date">{toShortDate(day.date)}</p>
                  <div className="schedule-dot-row">
                    {platforms.map((platform, index) => (
                      <span key={`${day.day}-${platform.name}-${index}`} className={dotClass(platform.color)} title={platform.name} />
                    ))}
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        <section className="schedule-inspector-panel">
          <p className="mono overline">Day Inspector</p>
          <p className="schedule-inspector-head mono">
            DATE: {toShortDate(selectedDay.date).toUpperCase()} | MARKET: {String(selectedDay.market || "Global").toUpperCase()} | TZ: {String(selectedDay.timezone || "UTC")}
          </p>

          <div className="schedule-platform-list">
            {selectedPlatforms.map((platform, index) => (
              <article key={`${platform.name}-${index}`} className="schedule-platform-card">
                <p className="mono overline">{platform.name.toUpperCase()} · {platform.time}</p>
                <p className="schedule-day-reason">Reason: {platform.reason}</p>
                <p className="schedule-day-hook">Expected Reach: {Number(platform.expected_reach || 0).toLocaleString()} accounts</p>
              </article>
            ))}
          </div>

          <div className="schedule-terminal-box">
            <p className="mono overline">[ SIMULATED PERFORMANCE METRICS ]</p>
            <pre>{`Expected Reach:    ${expectedReach.toLocaleString()} accounts\nPeak Engagement:   ${peakEngagement} ${selectedDay.timezone || "UTC"}\nRisk Factor:       ${riskFactor} (Consistent scheduling)`}</pre>
            <p className="mono overline">[ STRATEGY ALIGNMENT ]</p>
            <ul className="insights-list">
              {alignmentLines.map((line, index) => (
                <li key={`align-${index}`}>✓ {line}</li>
              ))}
            </ul>
          </div>
        </section>
      </div>

      <div className="schedule-rules-wrap">
        <p className="mono overline">Scheduler Rules</p>
        <ul className="insights-list">
          {((schedule?.rules && schedule.rules.length > 0
            ? schedule.rules
            : [
                "Deterministic scoring only: no AI inference needed.",
                "Score = time(0.4) + day(0.3) + platform(0.2) + content(0.1).",
                "Top daily slots selected by descending score.",
              ])).map((rule, index) => (
            <li key={`rule-${index}`}>{rule}</li>
          ))}
        </ul>
      </div>
    </article>
  );
}
