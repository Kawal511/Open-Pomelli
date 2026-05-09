import type { CampaignStateResponse } from "../../types";

interface InsightsBoxProps {
  campaign: CampaignStateResponse;
}

export function InsightsBox({ campaign }: InsightsBoxProps) {
  const strategy = campaign.strategy as Record<string, unknown>;
  const brandDna = campaign.brand_dna as Record<string, unknown>;
  const keywordTop = campaign.keyword_strategy?.top_10?.slice(0, 3) ?? [];
  const audience = String(brandDna?.target_audience ?? "");
  const coreMessage = String(strategy?.core_message ?? "");
  const taglines = Array.isArray(brandDna?.tagline_suggestions) ? (brandDna.tagline_suggestions as string[]) : [];

  const hasInsights = Boolean(
    coreMessage || audience || taglines.length > 0 || keywordTop.length > 0
  );

  if (!hasInsights) {
    return null;
  }

  return (
    <section className="insights-wrap content-bento-card">
      <div className="creative-section-head">
        <p className="data-label">Insights</p>
      </div>
      <div className="insight-mini-grid">
        <article className="insight-mini-card">
          <p className="data-label">Audience Insight</p>
          <p>{audience || "Audience profile pending"}</p>
        </article>
        <article className="insight-mini-card">
          <p className="data-label">Keyword Cluster</p>
          <p>{keywordTop.length > 0 ? keywordTop.join(" · ") : "Keyword cluster pending"}</p>
        </article>
        <article className="insight-mini-card">
          <p className="data-label">Performance Expectation</p>
          <p>{coreMessage || (taglines[0] ?? "Message strategy pending")}</p>
        </article>
      </div>
    </section>
  );
}
