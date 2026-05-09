import type { CampaignStateResponse } from "../../types";

interface CreativeAgentBoxProps {
  campaign: CampaignStateResponse;
}

function hashtagLine(tags?: string[]): string {
  if (!Array.isArray(tags) || tags.length === 0) {
    return "";
  }
  return tags.map((tag) => (tag.startsWith("#") ? tag : `#${tag.replace(/\s+/g, "")}`)).join(" ");
}

export function CreativeAgentBox({ campaign }: CreativeAgentBoxProps) {
  const creative = campaign.creative_agent;
  if (!creative) {
    return null;
  }

  const linkedinTags = hashtagLine(creative.linkedin?.hashtags);
  const instagramTags = hashtagLine(creative.instagram?.hashtags);

  return (
    <section className="content-bento-card creative-agent-box">
      <div className="creative-section-head">
        <p className="mono overline">Creative Agent Copy Pack</p>
      </div>

      <div className="creative-agent-grid">
        <article className="creative-agent-card">
          <p className="mono overline">LinkedIn Post</p>
          <p className="creative-caption">{creative.linkedin?.post || "Not generated yet."}</p>
          {linkedinTags ? <p className="creative-agent-tags">{linkedinTags}</p> : null}
          <p className="creative-agent-tip">Best Time: {creative.linkedin?.best_time || "n/a"}</p>
          <p className="creative-agent-tip">Tip: {creative.linkedin?.suggestion || "n/a"}</p>
        </article>

        <article className="creative-agent-card">
          <p className="mono overline">Instagram Caption</p>
          <p className="creative-caption">{creative.instagram?.caption || "Not generated yet."}</p>
          {instagramTags ? <p className="creative-agent-tags">{instagramTags}</p> : null}
          <p className="creative-agent-tip">Best Time: {creative.instagram?.best_time || "n/a"}</p>
          <p className="creative-agent-tip">Tip: {creative.instagram?.suggestion || "n/a"}</p>
        </article>

        <article className="creative-agent-card">
          <p className="mono overline">Client Email Draft</p>
          <p className="creative-agent-tip">Subject: {creative.email?.subject || "Not generated yet."}</p>
          <p className="creative-caption">{creative.email?.body || "Not generated yet."}</p>
          <p className="creative-agent-tip">Best Time: {creative.email?.best_time || "n/a"}</p>
          <p className="creative-agent-tip">Tip: {creative.email?.suggestion || "n/a"}</p>
        </article>
      </div>
    </section>
  );
}
