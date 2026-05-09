import { useEffect, useMemo, useState } from "react";
import { getGallery, searchReferenceImagesDetailed, toProxiedAssetUrl } from "../lib/api";
import type { GalleryImageItem, GalleryTextItem, SearchReferenceImageItem } from "../types";

function fmt(ts?: string): string {
  if (!ts) {
    return "Unknown";
  }
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString();
}

export function GalleryPage() {
  const [campaignId, setCampaignId] = useState<string>("");
  const [campaigns, setCampaigns] = useState<Array<{ campaign_id: string; start_payload: Record<string, unknown> }>>([]);
  const [images, setImages] = useState<GalleryImageItem[]>([]);
  const [texts, setTexts] = useState<GalleryTextItem[]>([]);
  const [referenceImages, setReferenceImages] = useState<SearchReferenceImageItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [referenceLoading, setReferenceLoading] = useState(false);
  const [referencePage, setReferencePage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [brandQuery, setBrandQuery] = useState("");

  const loadGallery = async (selectedCampaignId?: string) => {
    try {
      setLoading(true);
      setError(null);
      const response = await getGallery(selectedCampaignId || undefined, 500);
      setImages(response.images ?? []);
      setTexts(response.texts ?? []);
      setCampaigns((response.campaigns ?? []).map((item) => ({
        campaign_id: item.campaign_id,
        start_payload: item.start_payload,
      })));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load gallery");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadGallery();
  }, []);

  const loadReferenceImages = async (query?: string, mode: "replace" | "append" = "replace") => {
    try {
      setReferenceLoading(true);
      const started = Date.now();
      const page = mode === "append" ? referencePage + 1 : 0;
      const selectedCampaignForSave = campaignId || campaigns[0]?.campaign_id || undefined;
      const result = await searchReferenceImagesDetailed(query || brandQuery || "design gallery", 10, {
        page,
        campaignId: selectedCampaignForSave,
        persistToGallery: Boolean(selectedCampaignForSave),
        fallbackToUnsplash: false,
      });

      const remaining = 5000 - (Date.now() - started);
      if (remaining > 0) {
        await new Promise((resolve) => window.setTimeout(resolve, remaining));
      }

      const nextItems = result.images.slice(0, 10);
      setReferencePage(page);
      if (mode === "append") {
        setReferenceImages((current) => {
          const merged = [...current];
          for (const item of nextItems) {
            if (!merged.some((existing) => existing.image_url === item.image_url)) {
              merged.push(item);
            }
          }
          return merged;
        });
      } else {
        setReferenceImages(nextItems);
      }

      if (selectedCampaignForSave && result.saved_images > 0) {
        await loadGallery(campaignId || undefined);
      }
    } catch {
      if (mode === "replace") {
        setReferenceImages([]);
      }
    } finally {
      setReferenceLoading(false);
    }
  };

  useEffect(() => {
    void loadReferenceImages("brand design campaign", "replace");
  }, []);

  const options = useMemo(() => {
    return campaigns.map((item) => {
      const payload = item.start_payload ?? {};
      const brand = String(payload.brand_name ?? "Unknown brand");
      return {
        value: item.campaign_id,
        label: `${brand} · ${item.campaign_id.slice(0, 8)}`,
      };
    });
  }, [campaigns]);

  useEffect(() => {
    if (!campaignId) {
      return;
    }
    const selected = campaigns.find((item) => item.campaign_id === campaignId);
    const brand = String(selected?.start_payload?.brand_name ?? "").trim();
    if (brand) {
      setBrandQuery(brand);
    }
  }, [campaignId, campaigns]);

  return (
    <section className="panel" style={{ display: "grid", gap: 16 }}>
      <div className="history-header">
        <div>
          <p className="mono overline">Design Gallery</p>
          <h2>Generated Images + Campaign Texts</h2>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <select
            value={campaignId}
            onChange={(event) => {
              const value = event.target.value;
              setCampaignId(value);
              void loadGallery(value || undefined);
            }}
          >
            <option value="">All campaigns</option>
            {options.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <button className="chip" type="button" onClick={() => void loadGallery(campaignId || undefined)}>
            Refresh
          </button>
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <input
          value={brandQuery}
          onChange={(event) => setBrandQuery(event.target.value)}
          placeholder="Google image query (brand, mood, product style...)"
          style={{ minWidth: 280 }}
        />
        <button
          className={referenceLoading ? "chip loading-button" : "chip"}
          type="button"
          onClick={() => void loadReferenceImages(brandQuery || "brand design campaign", "append")}
          disabled={referenceLoading}
        >
          {referenceLoading ? "LOADING...." : "LOAD MORE...."}
        </button>
      </div>

      {error && <p className="form-error">{error}</p>}
      {loading && <p className="mono">Loading gallery...</p>}

      <div className="history-wrap">
        <p className="mono overline">Campaign Text Cards</p>
        {texts.length === 0 ? (
          <p className="history-empty">No campaign text summaries yet.</p>
        ) : (
          <div className="history-list" style={{ maxHeight: 320 }}>
            {texts.map((item) => (
              <article key={`${item.campaign_id}-${item.created_at}`} className="history-item">
                <p className="history-title">{item.brand_name || "Campaign"}</p>
                <p className="history-line">{item.title}</p>
                <p className="history-meta">Goal: {item.goal || "n/a"}</p>
                <p className="history-meta">Markets: {(item.markets ?? []).join(", ") || "n/a"}</p>
                <p className="history-meta">Cards: {item.asset_card_count} · {fmt(item.created_at)}</p>
              </article>
            ))}
          </div>
        )}
      </div>

      <div className="history-wrap">
        <p className="mono overline">Generated Images</p>
        {images.length === 0 ? (
          <p className="history-empty">No generated images yet.</p>
        ) : (
          <div className="poster-grid" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 12 }}>
            {images.map((item) => (
              <figure key={item.id} className="poster-item">
                {item.image_url ? (
                  <img
                    src={item.image_url}
                    alt={item.prompt}
                    loading="lazy"
                    referrerPolicy="no-referrer"
                    onError={(event) => {
                      const element = event.currentTarget;
                      const targetUrl = String(item.image_url || "").trim();
                      if (targetUrl && !element.dataset.proxyFallbackApplied) {
                        element.dataset.proxyFallbackApplied = "1";
                        element.src = toProxiedAssetUrl(targetUrl);
                        return;
                      }
                      element.onerror = null;
                      element.src = `https://picsum.photos/seed/generated-${item.id}/1200/900`;
                    }}
                  />
                ) : (
                  <div className="w-full aspect-[3/4] bg-gray-200" />
                )}
                <figcaption>
                  <strong>{item.brand_name || item.asset_type}</strong>
                  <small>{item.provider || "unknown"} · {item.model || "n/a"}</small>
                  <small>{fmt(item.created_at)}</small>
                </figcaption>
              </figure>
            ))}
          </div>
        )}
      </div>

      <div className="history-wrap">
        <p className="mono overline">Google Image References</p>
        {referenceLoading ? (
          <div className="reference-loading-grid" aria-live="polite">
            {Array.from({ length: 6 }).map((_, idx) => (
              <div key={`reference-skeleton-${idx}`} className="reference-skeleton-card" />
            ))}
          </div>
        ) : referenceImages.length === 0 ? (
          <p className="history-empty">No image references loaded.</p>
        ) : (
          <div className="poster-grid" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 12 }}>
            {referenceImages.map((item) => (
              <figure key={item.id} className="poster-item">
                <img
                  src={item.image_url}
                  alt={item.description}
                  loading="lazy"
                  referrerPolicy="no-referrer"
                  onError={(event) => {
                    const element = event.currentTarget;
                    const targetUrl = String(item.image_url || "").trim();
                    if (targetUrl && !element.dataset.proxyFallbackApplied) {
                      element.dataset.proxyFallbackApplied = "1";
                      element.src = toProxiedAssetUrl(targetUrl);
                      return;
                    }
                    element.onerror = null;
                    element.src = `https://picsum.photos/seed/reference-${item.id}/1200/900`;
                  }}
                />
                <figcaption>
                  <strong>{item.description || "Google image reference"}</strong>
                  <small>
                    by <a href={item.photographer_url} target="_blank" rel="noreferrer">{item.photographer_name}</a>
                  </small>
                  <small>source: {item.source || "google_images"}</small>
                </figcaption>
              </figure>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
