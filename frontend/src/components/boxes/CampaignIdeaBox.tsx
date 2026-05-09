import type { CampaignStateResponse } from "../../types";

interface CampaignIdeaBoxProps {
  campaign: CampaignStateResponse;
}

export function CampaignIdeaBox({ campaign }: CampaignIdeaBoxProps) {
  const strategy = campaign.strategy as Record<string, unknown>;
  const ideas = strategy?.contextual_campaign_ideas || [];
  const creative = campaign.creative_agent;
  const cards = Array.isArray(campaign.content?.asset_cards) ? campaign.content.asset_cards : [];
  const displayFont = String(campaign.brand_dna?.identity?.font_system?.display || "").trim();
  const mainIdea = Array.isArray(ideas) ? ideas[0] as Record<string, unknown> : null;

  if (!mainIdea) {
    return (
      <article className="content-bento-card campaign-idea-box">
        <p className="content-empty-note">No campaign idea generated yet.</p>
      </article>
    );
  }

  const title = String(mainIdea.title ?? "Campaign Concept");
  const visualMode = title.length % 2 === 0 ? "idea-dark" : "idea-beige";
  const brandName = String((campaign.start_payload as Record<string, unknown>)?.brand_name ?? "Brand");

  const firstPipelineText = (recordKey: "social_posts" | "direct_copy", channel: string): string => {
    for (const card of cards) {
      const container = card?.[recordKey];
      if (!container || typeof container !== "object") {
        continue;
      }
      const value = String((container as Record<string, unknown>)[channel] ?? "").trim();
      if (value) {
        return value;
      }
    }
    return "";
  };

  const fallbackCore = String(strategy?.core_message ?? "").trim();
  const linkedinText = String(creative?.linkedin?.post ?? "").trim()
    || firstPipelineText("social_posts", "linkedin")
    || firstPipelineText("direct_copy", "linkedin")
    || fallbackCore
    || `${brandName} campaign copy is ready in the pipeline.`;
  const instagramText = String(creative?.instagram?.caption ?? "").trim()
    || firstPipelineText("social_posts", "instagram")
    || firstPipelineText("direct_copy", "instagram")
    || fallbackCore
    || `${brandName} visual-first campaign caption is ready in the pipeline.`;
  const rawEmailSubject = String(creative?.email?.subject ?? "").trim();
  const campaignGoal = String((campaign.start_payload as Record<string, unknown>)?.campaign_goal ?? "engagement");
  const primaryMarket = String(mainIdea.market ?? "primary market");
  const rawEmailBody = String(creative?.email?.body ?? "").trim()
    || firstPipelineText("direct_copy", "email")
    || firstPipelineText("social_posts", "email")
    || fallbackCore
    || `Hi team,\n\n${brandName} campaign messaging is prepared and ready for activation.\n\nBest,\nOpen Pomelli`;

  const normalizeEmailContent = (subject: string, body: string): { subject: string; body: string } => {
    const lines = body
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    const subjectLines = lines.filter((line) => /^subject\s*:/i.test(line));
    const cleanedBodyLines = lines.filter((line) => !/^subject\s*:/i.test(line));
    const normalizedSubject = subject
      || (subjectLines.length > 0 ? subjectLines[0].replace(/^subject\s*:/i, "").trim() : "")
      || `${brandName} campaign draft`;
    const fallbackBody = [
      "Hi team,",
      "",
      `I am sharing the finalized campaign communication draft for ${brandName}, tailored for ${primaryMarket} and aligned to your ${campaignGoal} objective.`,
      "",
      "This plan is intentionally structured to be execution-ready:",
      "- LinkedIn narrative for professional credibility and trust",
      "- Instagram caption architecture optimized for local engagement",
      "- Deterministic 30-day channel cadence with predictable publishing logic",
      "",
      "Strategic rationale:",
      fallbackCore ? `- ${fallbackCore}` : "- Messaging prioritizes clarity, local relevance, and stronger CTA progression",
      "- Copy structure is proof-led to reduce generic brand positioning",
      "- Platform timing is tuned to likely audience attention windows",
      "",
      "If you approve, the next step is immediate rollout with final asset lock, publishing calendar handoff, and monitoring hooks for rapid iteration.",
      "",
      "Best regards,",
      "Open Pomelli",
    ].join("\n");
    const normalizedBody = cleanedBodyLines.join("\n").trim();
    const bodyLooksUseful = normalizedBody.length >= 120
      && /(hi|hello|team|dear)/i.test(normalizedBody)
      && /(best|regards|thanks)/i.test(normalizedBody);

    return {
      subject: normalizedSubject,
      body: bodyLooksUseful ? normalizedBody : fallbackBody,
    };
  };

  const email = normalizeEmailContent(rawEmailSubject, rawEmailBody);

  const linkedinTags = Array.isArray(creative?.linkedin?.hashtags)
    ? creative.linkedin.hashtags.map((tag) => (String(tag).startsWith("#") ? String(tag) : `#${String(tag).replace(/\s+/g, "")}`)).join(" ")
    : "";
  const instagramTags = Array.isArray(creative?.instagram?.hashtags)
    ? creative.instagram.hashtags.map((tag) => (String(tag).startsWith("#") ? String(tag) : `#${String(tag).replace(/\s+/g, "")}`)).join(" ")
    : "";

  return (
    <article className={`content-bento-card campaign-idea-box campaign-idea-hero ${visualMode}`}>
      <p className="data-label">Campaign Idea</p>
      <h3 style={displayFont ? { fontFamily: displayFont } : undefined}>{title}</h3>

      <div className="campaign-idea-copy-grid">
        <article className="campaign-idea-copy-card">
          <p className="mono overline">LinkedIn Message</p>
          <div className="campaign-copy-scroll">
            <p className="creative-caption">{linkedinText}</p>
            {linkedinTags ? <p className="creative-agent-tags">{linkedinTags}</p> : null}
          </div>
          <button
            type="button"
            className="creative-copy-button campaign-copy-btn"
            onClick={async () => {
              const text = [linkedinText, linkedinTags].filter(Boolean).join("\n\n");
              await navigator.clipboard.writeText(text);
            }}
          >
            Copy
          </button>
        </article>

        <article className="campaign-idea-copy-card">
          <p className="mono overline">Instagram Message</p>
          <div className="campaign-copy-scroll">
            <p className="creative-caption">{instagramText}</p>
            {instagramTags ? <p className="creative-agent-tags">{instagramTags}</p> : null}
          </div>
          <button
            type="button"
            className="creative-copy-button campaign-copy-btn"
            onClick={async () => {
              const text = [instagramText, instagramTags].filter(Boolean).join("\n\n");
              await navigator.clipboard.writeText(text);
            }}
          >
            Copy
          </button>
        </article>

        <article className="campaign-idea-copy-card">
          <p className="mono overline">Draft Email</p>
          <div className="campaign-copy-scroll">
            <p className="creative-agent-tip">Subject: {email.subject}</p>
            <p className="creative-caption">{email.body}</p>
          </div>
          <button
            type="button"
            className="creative-copy-button campaign-copy-btn"
            onClick={async () => {
              const subject = `Subject: ${email.subject}`;
              const body = email.body;
              const text = [subject, body].filter(Boolean).join("\n\n");
              await navigator.clipboard.writeText(text);
            }}
          >
            Copy
          </button>
        </article>
      </div>
    </article>
  );
}
