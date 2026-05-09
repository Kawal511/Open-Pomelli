import { useEffect, useState } from "react";
import { listCampaignHistory } from "../../lib/api";
import { useCampaignStore } from "../../store/campaignStore";

type RecentCampaign = {
  id: string;
  label: string;
};

export function EmptyState() {
  const selectCampaign = useCampaignStore((state) => state.selectCampaign);
  const [recent, setRecent] = useState<RecentCampaign[]>([]);
  const [loadingRecent, setLoadingRecent] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        setLoadingRecent(true);
        const result = await listCampaignHistory(6);
        if (cancelled) {
          return;
        }
        const options = (result.campaigns || []).map((item) => {
          const payload = item.start_payload || {};
          const brandName = String(payload.brand_name || "Untitled").trim() || "Untitled";
          const goal = String(payload.campaign_goal || "goal n/a").trim() || "goal n/a";
          return {
            id: item.campaign_id,
            label: `${brandName} - ${goal} - ${item.status}`,
          };
        });
        setRecent(options);
      } catch {
        if (!cancelled) {
          setRecent([]);
        }
      } finally {
        if (!cancelled) {
          setLoadingRecent(false);
        }
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="empty-state-shell">
      <div className="empty-state-card">
        <h1>No Campaign Yet</h1>
        <p>
          Start a new campaign from Onboarding to see generated results here.
        </p>
        <a
          href="/intake"
          className="empty-state-action mono"
        >
          Start Campaign →
        </a>
        <div className="history-wrap" style={{ marginTop: "14px", textAlign: "left" }}>
          <p className="data-label">Restore Recent Campaign</p>
          {loadingRecent ? <p className="history-empty">Loading recent campaigns...</p> : null}
          {!loadingRecent && recent.length === 0 ? <p className="history-empty">No recent campaigns found.</p> : null}
          {!loadingRecent && recent.length > 0 ? (
            <div className="history-list">
              {recent.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="history-item"
                  onClick={() => void selectCampaign(item.id)}
                >
                  <div className="history-item-head">
                    <p className="history-title">{item.label}</p>
                  </div>
                  <p className="history-meta mono">{item.id}</p>
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
