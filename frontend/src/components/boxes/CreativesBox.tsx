import type { CampaignStateResponse, AssetCard } from "../../types";
import { toProxiedAssetUrl } from "../../lib/api";

interface CreativesBoxProps {
  campaign: CampaignStateResponse;
}

function toPollinationsPosterUrl(prompt: string, width?: number, height?: number): string {
  const safePrompt = String(prompt || "brand campaign poster").trim() || "brand campaign poster";
  const w = Number.isFinite(width) && Number(width) > 0 ? Number(width) : 1200;
  const h = Number.isFinite(height) && Number(height) > 0 ? Number(height) : 900;
  return `https://image.pollinations.ai/prompt/${encodeURIComponent(safePrompt)}?model=flux&width=${Math.trunc(w)}&height=${Math.trunc(h)}&nologo=true`;
}

export function CreativesBox({ campaign }: CreativesBoxProps) {
  const cards = campaign.content?.asset_cards || [];
  const videos = (campaign.generated_videos || []).filter((video) => video.asset_type === "video");

  const visualAssets = cards.flatMap((card) =>
    (card.poster_assets || []).map((asset, index) => ({
      id: `${card.market}-${asset.label}-${index}`,
      market: card.market,
      heroConcept: card.hero_concept,
      caption:
        asset.caption ||
        (asset.channel ? card.social_posts?.[asset.channel] : "") ||
        card.direct_copy?.banner ||
        "",
      ...asset,
    }))
  );

  const dedupedVisualAssets = visualAssets.filter((asset, index, list) => {
    const assetUrl = String(asset.image_url || "").trim();
    if (!assetUrl) {
      return true;
    }
    return list.findIndex((row) => String(row.image_url || "").trim() === assetUrl) === index;
  });

  const posterAssets = dedupedVisualAssets.filter((asset) => (asset.asset_type || "poster") === "poster");
  const bannerAssets = dedupedVisualAssets.filter((asset) => asset.asset_type === "banner");
  const socialAdAssets = dedupedVisualAssets.filter((asset) => asset.asset_type === "social_ad");

  if (cards.length === 0 && videos.length === 0) {
    return (
      <article className="content-bento-card creatives-box-full">
        <p className="mono overline">Creative Assets</p>
        <h3 className="creative-section-title">No generated creatives yet</h3>
        <p className="creative-empty-copy">
          Once generation completes, this panel will show your poster outputs, key concept text, and quick copy actions.
        </p>
        <div className="creative-skeleton-grid">
          {[0, 1, 2].map((slot) => (
            <div key={slot} className="creative-skeleton-card">
              <div className="creative-skeleton-thumb" />
              <p className="mono overline">Awaiting image</p>
            </div>
          ))}
        </div>
      </article>
    );
  }

  return (
    <section className="creatives-stack">
      {videos.length > 0 && (
        <div className="creative-section-grid two-col">
          {videos.slice(0, 2).map((video) => (
            <article key={`video-${video.id}`} className="content-bento-card creative-video-card">
              <p className="mono overline">Vadoo Video</p>
              <video src={video.image_url} controls playsInline className="creative-video-frame" />
              <p className="creative-caption">{video.prompt}</p>
            </article>
          ))}
        </div>
      )}

      {posterAssets.length > 0 && (
        <CreativeSection title="Poster" assets={posterAssets} />
      )}

      {bannerAssets.length > 0 && (
        <CreativeSection title="Banner" assets={bannerAssets} />
      )}

      {socialAdAssets.length > 0 && (
        <CreativeSection title="Marketing Ads" assets={socialAdAssets} />
      )}

      {(posterAssets.length === 0 && bannerAssets.length === 0 && socialAdAssets.length === 0 && cards.length > 0) && (
        <div className="creative-section-grid">
          {cards.slice(0, 3).map((card: AssetCard, idx) => (
            <FallbackCreativeCard key={`${card.market}-${idx}`} card={card} />
          ))}
        </div>
      )}
    </section>
  );
}

type VisualAsset = {
  id: string;
  label: string;
  market: string;
  heroConcept: string;
  caption: string;
  channel?: string;
  asset_type?: "poster" | "banner" | "social_ad";
  aspect: string;
  width?: number;
  height?: number;
  prompt: string;
  image_url: string;
  provider?: string;
  model?: string;
  status?: string;
};

function CreativeSection({ title, assets }: { title: string; assets: VisualAsset[] }) {
  return (
    <section className="content-bento-card creatives-box-full">
      <div className="creative-section-head">
        <p className="mono overline">{title}</p>
        <p className="creative-section-count">{assets.length} generated</p>
      </div>
      <div className="creative-section-grid">
        {assets.map((asset) => (
          <CreativeAssetCard key={asset.id} asset={asset} />
        ))}
      </div>
    </section>
  );
}

function CreativeAssetCard({ asset }: { asset: VisualAsset }) {
  const captionText = asset.caption || asset.heroConcept || "Caption is not available for this creative yet.";

  return (
    <article className="creative-asset-card">
      {asset.image_url ? (
        <div className="creative-thumb-wrap">
          <img
            src={toProxiedAssetUrl(asset.image_url)}
            alt={asset.label || asset.market}
            className="creative-thumb"
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={(event) => {
              const element = event.currentTarget;
              if (!element.dataset.pollinationsFallbackApplied) {
                element.dataset.pollinationsFallbackApplied = "1";
                element.src = toPollinationsPosterUrl(asset.prompt, asset.width, asset.height);
                return;
              }
              const fallbackSeed = encodeURIComponent(`${asset.market}-${asset.label}-${asset.id}`);
              if (!element.dataset.picsumFallbackApplied) {
                element.dataset.picsumFallbackApplied = "1";
                element.src = `https://picsum.photos/seed/${fallbackSeed}/1200/900`;
                return;
              }
              element.onerror = null;
            }}
          />
          <span className="creative-pill mono">{asset.label}</span>
        </div>
      ) : (
        <div className="creative-thumb-empty">Image Pending</div>
      )}

      <div className="creative-asset-copy">
        <p className="mono overline">
          {asset.market}
          {asset.channel ? ` · ${asset.channel}` : ""}
        </p>
        <p className="creative-caption">{captionText}</p>
      </div>

      <div className="creative-meta-row mono">
        <span>{asset.aspect}</span>
        <span>{asset.provider || "unknown"}</span>
      </div>

      <button
        type="button"
        className="creative-copy-button"
        onClick={async () => {
          const text = `${asset.market} ${asset.channel ? `(${asset.channel})` : ""}: ${captionText}`;
          await navigator.clipboard.writeText(text);
        }}
      >
        Copy Caption
      </button>
    </article>
  );
}

function FallbackCreativeCard({ card }: { card: AssetCard }) {
  const posterAssets = card.poster_assets || [];
  const firstPoster = posterAssets[0];
  const heroText = card.hero_concept ? card.hero_concept.trim() : "No hero concept text was generated for this card yet.";

  return (
    <article className="creative-asset-card">
      {firstPoster?.image_url ? (
        <div className="creative-thumb-wrap">
          <img
            src={toProxiedAssetUrl(firstPoster.image_url)}
            alt={card.market}
            className="creative-thumb"
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={(event) => {
              const element = event.currentTarget;
              if (!element.dataset.pollinationsFallbackApplied) {
                element.dataset.pollinationsFallbackApplied = "1";
                element.src = toPollinationsPosterUrl(firstPoster.prompt, firstPoster.width, firstPoster.height);
                return;
              }
              const fallbackSeed = encodeURIComponent(`${card.market}-fallback`);
              if (!element.dataset.picsumFallbackApplied) {
                element.dataset.picsumFallbackApplied = "1";
                element.src = `https://picsum.photos/seed/${fallbackSeed}/1200/900`;
                return;
              }
              element.onerror = null;
            }}
          />
          <span className="creative-pill mono">Generated Image</span>
        </div>
      ) : (
        <div className="creative-thumb-empty">
          Visual output has not been generated for this card yet.
        </div>
      )}

      <div className="creative-asset-copy">
        <p className="mono overline">{card.market}</p>
        <p className="creative-caption">{heroText}</p>
      </div>

      <button
        type="button"
        className="creative-copy-button"
        onClick={async () => {
          await navigator.clipboard.writeText(`${card.market}: ${heroText}`);
        }}
      >
        Copy
      </button>
    </article>
  );
}
