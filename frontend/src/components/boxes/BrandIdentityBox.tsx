import { useEffect, useState } from "react";
import { patchBrandIdentity } from "../../lib/api";
import type { CampaignStateResponse } from "../../types";

interface BrandIdentityBoxProps {
  campaign: CampaignStateResponse;
}

export function BrandIdentityBox({ campaign }: BrandIdentityBoxProps) {
  const [brandNameDraft, setBrandNameDraft] = useState("");
  const [displayFont, setDisplayFont] = useState("");
  const [uiFont, setUiFont] = useState("");
  const [technicalFont, setTechnicalFont] = useState("");
  const [fontSaveMessage, setFontSaveMessage] = useState<string | null>(null);
  const [savingFonts, setSavingFonts] = useState(false);
  const brandDna = campaign.brand_dna;
  const palette = brandDna?.identity?.palette ?? [];
  const fontSystem = brandDna?.identity?.font_system;
  const fontOptions = brandDna?.identity?.font_options;
  const tones = brandDna?.tone_of_voice ?? [];
  const payload = campaign.start_payload as Record<string, unknown>;
  const industry = String(brandDna?.industry ?? payload?.industry ?? "general");
  const audience = String(brandDna?.target_audience ?? payload?.audience ?? "");
  const channels = Array.isArray(payload?.channels) ? (payload.channels as string[]) : [];
  const website = String(payload?.website_url ?? "");

  useEffect(() => {
    setBrandNameDraft(String(brandDna?.brand_name ?? ""));
  }, [brandDna?.brand_name]);

  useEffect(() => {
    setDisplayFont(String(fontSystem?.display ?? ""));
    setUiFont(String(fontSystem?.ui ?? ""));
    setTechnicalFont(String(fontSystem?.technical ?? ""));
    setFontSaveMessage(null);
  }, [fontSystem?.display, fontSystem?.ui, fontSystem?.technical]);

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }
    if (displayFont.trim()) {
      document.documentElement.style.setProperty("--brand-display-font", displayFont.trim());
      return;
    }
    document.documentElement.style.removeProperty("--brand-display-font");
  }, [displayFont]);

  if (!brandDna) return null;

  const displayChoices = Array.from(new Set([displayFont, ...(fontOptions?.display || []).map((item) => item.family).filter(Boolean)]));
  const uiChoices = Array.from(new Set([uiFont, ...(fontOptions?.ui || []).map((item) => item.family).filter(Boolean)]));
  const technicalChoices = Array.from(new Set([technicalFont, ...(fontOptions?.technical || []).map((item) => item.family).filter(Boolean)]));

  const saveFontSystem = async () => {
    const brandName = String(brandDna.brand_name || "").trim();
    if (!brandName || !displayFont || !uiFont || !technicalFont) {
      setFontSaveMessage("Pick all three font roles before saving.");
      return;
    }
    try {
      setSavingFonts(true);
      setFontSaveMessage(null);
      await patchBrandIdentity(brandName, {
        identity: {
          font_system: {
            display: displayFont,
            ui: uiFont,
            technical: technicalFont,
          },
        },
      });
      setFontSaveMessage("Font system saved.");
    } catch {
      setFontSaveMessage("Failed to save fonts. Try again.");
    } finally {
      setSavingFonts(false);
    }
  };

  return (
    <article className="content-bento-card brand-identity-box">
      <div className="brand-compact-head">
        <p className="data-label">Brand Identity</p>
        <input
          value={brandNameDraft}
          onChange={(event) => setBrandNameDraft(event.target.value)}
          className="brand-name-input"
          placeholder="Brand name"
          aria-label="Brand name"
        />
      </div>

      <div className="brand-inline-chips">
        <span className="inline-chip">{industry}</span>
        {audience ? <span className="inline-chip">{audience}</span> : null}
        {channels.slice(0, 3).map((channel) => (
          <span key={channel} className="inline-chip">{channel}</span>
        ))}
      </div>

      <div className="brand-palette-inline">
        <p className="data-label">Color Palette</p>
        <div className="palette-swatch-row">
          {palette.slice(0, 6).map((color, idx) => (
            <span
              key={`${color.hex}-${idx}`}
              className="palette-swatch"
              title={`${color.name} ${color.hex}`}
              style={{ backgroundColor: color.hex }}
            />
          ))}
          {palette.length === 0 ? <span className="muted-copy">No palette extracted yet.</span> : null}
        </div>
      </div>

      <div className="tone-pill-row">
        <p className="data-label">Tone</p>
        <div className="tone-pill-wrap">
          {tones.length > 0 ? tones.map((tone) => <span key={tone} className="tone-pill">{tone}</span>) : <span className="muted-copy">Tone pending</span>}
        </div>
      </div>

      <div className="brand-font-row">
        <p className="data-label">Font System</p>
        <div className="brand-font-controls">
          <label>
            Display
            <select value={displayFont} onChange={(event) => setDisplayFont(event.target.value)}>
              {displayChoices.map((family) => (
                <option key={`display-${family}`} value={family}>{family}</option>
              ))}
            </select>
          </label>
          <label>
            UI
            <select value={uiFont} onChange={(event) => setUiFont(event.target.value)}>
              {uiChoices.map((family) => (
                <option key={`ui-${family}`} value={family}>{family}</option>
              ))}
            </select>
          </label>
          <label>
            Technical
            <select value={technicalFont} onChange={(event) => setTechnicalFont(event.target.value)}>
              {technicalChoices.map((family) => (
                <option key={`technical-${family}`} value={family}>{family}</option>
              ))}
            </select>
          </label>
        </div>
        <button type="button" className={savingFonts ? "chip loading-button" : "chip"} disabled={savingFonts} onClick={() => void saveFontSystem()}>
          {savingFonts ? "SAVING..." : "Save Font System"}
        </button>
        {fontSaveMessage ? <p className="muted-copy">{fontSaveMessage}</p> : null}
      </div>

      {website ? <p className="muted-copy">Website: {website}</p> : null}
    </article>
  );
}
