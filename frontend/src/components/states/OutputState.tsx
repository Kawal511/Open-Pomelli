import { useEffect, useState } from "react";
import { useCampaignStore } from "../../store/campaignStore";
import type { CampaignStateResponse } from "../../types";
import { Link } from "react-router-dom";
import { listCampaignHistory } from "../../lib/api";
import { CampaignHeader } from "../layout/CampaignHeader";
import { CampaignIdeaBox } from "../boxes/CampaignIdeaBox";
import { BrandIdentityBox } from "../boxes/BrandIdentityBox";
import { CreativesBox } from "../boxes/CreativesBox";
import { ScheduleBox } from "../boxes/ScheduleBox";
import { InsightsBox } from "../boxes/InsightsBox";
import { KeywordGraphBox } from "../boxes/KeywordGraphBox";
import { CreativeAgentBox } from "../boxes/CreativeAgentBox";
import { CommunicationsBox } from "../boxes/CommunicationsBox";
import { BentoGrid } from "../layout/BentoGrid";

export function OutputState() {
  const { campaign, campaignId, selectCampaign } = useCampaignStore();
  const [historyOptions, setHistoryOptions] = useState<Array<{ id: string; label: string }>>([]);
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const loadHistory = async () => {
      try {
        const result = await listCampaignHistory(200);
        if (cancelled) {
          return;
        }
        const options = (result.campaigns ?? []).map((entry) => {
          const payload = entry.start_payload ?? {};
          const brand = String(payload.brand_name ?? "Unknown brand");
          return {
            id: entry.campaign_id,
            label: `${brand} · ${entry.campaign_id.slice(0, 8)}`,
          };
        });
        setHistoryOptions(options);
      } catch {
        if (!cancelled) {
          setHistoryOptions([]);
        }
      }
    };
    void loadHistory();
    return () => {
      cancelled = true;
    };
  }, [campaignId]);

  const typedCampaign = campaign as CampaignStateResponse | null;

  if (!typedCampaign) {
    return <div className="content-hub-shell">No campaign data</div>;
  }

  const exportFilenameBase = String((typedCampaign.start_payload?.brand_name as string) || "campaign")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "campaign";

  const downloadJson = () => {
    const blob = new Blob([JSON.stringify(typedCampaign, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${exportFilenameBase}-dashboard.json`;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  };

  const downloadPdf = () => {
    const popup = window.open("", "_blank", "width=980,height=1280");
    if (!popup) {
      return;
    }
    const brand = String(typedCampaign.start_payload?.brand_name || "Campaign");
    const goal = String(typedCampaign.start_payload?.campaign_goal || "n/a");
    const markets = Array.isArray(typedCampaign.start_payload?.target_markets)
      ? (typedCampaign.start_payload?.target_markets as string[]).join(", ")
      : "n/a";
    popup.document.write(`
      <html>
        <head><title>${brand} Dashboard Export</title></head>
        <body style="font-family: ui-monospace, SFMono-Regular, Menlo, monospace; padding: 24px; color: #111;">
          <h1 style="margin: 0 0 12px;">${brand} - Campaign Dashboard</h1>
          <p><strong>Goal:</strong> ${goal}</p>
          <p><strong>Markets:</strong> ${markets}</p>
          <h2>Schedule Snapshot</h2>
          <pre style="white-space: pre-wrap; border: 1px solid #ddd; padding: 12px;">${JSON.stringify(typedCampaign.schedule || {}, null, 2)}</pre>
          <h2>Creative Snapshot</h2>
          <pre style="white-space: pre-wrap; border: 1px solid #ddd; padding: 12px;">${JSON.stringify(typedCampaign.creative_agent || {}, null, 2)}</pre>
        </body>
      </html>
    `);
    popup.document.close();
    popup.focus();
    popup.print();
  };

  return (
    <section className="content-hub-shell">
      <div className="history-wrap content-hub-switcher">
        <div className="history-header">
          <p className="mono overline">Content Hub Campaign Switcher</p>
          <div className="campaign-switcher-controls">
            <select
              value={campaignId ?? ""}
              onChange={async (event) => {
                const selected = event.target.value;
                if (!selected || selected === campaignId) {
                  return;
                }
                try {
                  setSwitching(true);
                  await selectCampaign(selected);
                } finally {
                  setSwitching(false);
                }
              }}
            >
              <option value="">Select campaign</option>
              {historyOptions.map((option) => (
                <option key={option.id} value={option.id}>{option.label}</option>
              ))}
            </select>
            {switching && <span className="mono campaign-switching">Switching...</span>}
          </div>
        </div>
      </div>

      <CampaignHeader campaign={typedCampaign} />

      <div className="content-hub-export-actions">
        <button type="button" className="chip" onClick={downloadPdf}>Download PDF</button>
        <button type="button" className="chip" onClick={downloadJson}>Download JSON</button>
      </div>

      <BentoGrid>
        <BrandIdentityBox campaign={typedCampaign} />
        <CampaignIdeaBox campaign={typedCampaign} />
        <CreativesBox campaign={typedCampaign} />
        <KeywordGraphBox campaign={typedCampaign} />
        <CommunicationsBox campaign={typedCampaign} />
        <CreativeAgentBox campaign={typedCampaign} />
        <ScheduleBox campaign={typedCampaign} />
        <InsightsBox campaign={typedCampaign} />
      </BentoGrid>

      <div className="content-hub-debug-link-wrap">
        <Link to="/debug" className="content-hub-debug-link">Advanced settings</Link>
      </div>
    </section>
  );
}
