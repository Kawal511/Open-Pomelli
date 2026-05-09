import type { CampaignStateResponse } from "../../types";

interface CampaignHeaderProps {
  campaign: CampaignStateResponse;
}

export function CampaignHeader({ campaign }: CampaignHeaderProps) {
  const payload = campaign.start_payload as Record<string, unknown>;
  const brandName = String(payload?.brand_name ?? "Campaign");
  const goal = String(payload?.campaign_goal ?? "");
  const audience = String(payload?.audience ?? "");
  const markets = Array.isArray(payload?.target_markets)
    ? (payload.target_markets as string[]).join(" • ")
    : "";

  return (
    <div className="campaign-header-shell">
      <div>
        <p className="data-label">Active Campaign</p>
        <h1 style={{ fontFamily: "var(--brand-display-font, var(--font-display))" }}>{brandName}</h1>
      </div>
      <div className="campaign-header-meta">
        <span className="campaign-meta-chip">{goal || "Goal pending"}</span>
        <span className="campaign-meta-chip">{audience || "Audience pending"}</span>
        <span className="campaign-meta-chip">{markets || "Markets pending"}</span>
      </div>
    </div>
  );
}
