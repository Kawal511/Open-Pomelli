import { useMemo, useState } from "react";
import { sendUniPileBundle } from "../../lib/api";
import type { CampaignStateResponse, UniPileBundleResponse } from "../../types";

interface CommunicationsBoxProps {
  campaign: CampaignStateResponse;
}

const DEFAULT_TARGETS = {
  email: "atharva.v.deo@gmail.com",
  whatsapp: "7249169164",
  telegram: "8624909429",
};

export function CommunicationsBox({ campaign }: CommunicationsBoxProps) {
  const [sending, setSending] = useState<"email" | "whatsapp" | "telegram" | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [lastResponse, setLastResponse] = useState<UniPileBundleResponse | null>(null);

  const campaignId = String(campaign.campaign_id || "").trim();
  const promotionMessage = useMemo(() => {
    const creative = campaign.creative_agent || {};
    const linkedin = String(creative.linkedin?.post || "").trim();
    const whatsapp = String(creative.whatsapp?.message || "").trim();
    const fallback = String(campaign.strategy?.core_message || "Campaign launch message").trim();
    return whatsapp || linkedin || fallback;
  }, [campaign.creative_agent, campaign.strategy?.core_message]);

  const sendByChannel = async (channel: "email" | "whatsapp" | "telegram") => {
    if (!campaignId) {
      setStatusMessage("Campaign ID missing. Reload dashboard.");
      return;
    }
    try {
      setSending(channel);
      setStatusMessage(null);
      const result = await sendUniPileBundle({
        campaign_id: campaignId,
        channel,
        promotion_message: promotionMessage,
      });
      setLastResponse(result);

      const success = channel === "email"
        ? result.email_sent
        : channel === "whatsapp"
          ? result.whatsapp_sent
          : result.telegram_sent;

      setStatusMessage(success
        ? `Sent successfully via ${channel.toUpperCase()}.`
        : `Send failed via ${channel.toUpperCase()}. Check provider trace in backend logs.`);
    } catch (error) {
      const detail = error instanceof Error ? error.message : "Unknown error";
      setStatusMessage(`Send failed via ${channel.toUpperCase()}: ${detail}`);
    } finally {
      setSending(null);
    }
  };

  const targets = lastResponse?.fixed_targets || DEFAULT_TARGETS;

  return (
    <section className="content-bento-card communications-box">
      <div className="creative-section-head">
        <p className="mono overline">Campaign Communications</p>
        <p className="creative-section-count">Send brand identity + posters via UniPile</p>
      </div>

      <div className="communications-targets">
        <p className="data-label">Fixed Recipients</p>
        <p className="muted-copy">Email: {targets.email}</p>
        <p className="muted-copy">WhatsApp: {targets.whatsapp}</p>
        <p className="muted-copy">Telegram: {targets.telegram}</p>
      </div>

      <div className="communications-actions">
        <button type="button" className="chip" disabled={sending !== null} onClick={() => void sendByChannel("email")}>
          {sending === "email" ? "Sending Email..." : "Send to Email"}
        </button>
        <button type="button" className="chip" disabled={sending !== null} onClick={() => void sendByChannel("whatsapp")}>
          {sending === "whatsapp" ? "Sending WhatsApp..." : "Send to WhatsApp"}
        </button>
        <button type="button" className="chip" disabled={sending !== null} onClick={() => void sendByChannel("telegram")}>
          {sending === "telegram" ? "Sending Telegram..." : "Send to Telegram"}
        </button>
      </div>

      {statusMessage ? <p className="communications-status">{statusMessage}</p> : null}

      {lastResponse?.linkedin_url ? (
        <div className="communications-links">
          <a href={lastResponse.linkedin_url} target="_blank" rel="noreferrer" className="empty-state-action mono">Open LinkedIn Post Link</a>
          <a href={lastResponse.telegram_url} target="_blank" rel="noreferrer" className="empty-state-action mono">Open Telegram Share Link</a>
        </div>
      ) : null}
    </section>
  );
}
