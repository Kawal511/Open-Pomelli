import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDropzone } from "react-dropzone";
import { getBrandIdentity, listCampaignHistory, searchReferenceImages, toProxiedAssetUrl } from "../lib/api";
import { BUDGET_TIERS, CAMPAIGN_GOALS, CHANNEL_OPTIONS, INDUSTRY_PRESETS } from "../lib/presets";
import { useCampaignStore } from "../store/campaignStore";
import type {
  BrandIdentityLookupResponse,
  CampaignHistoryItem,
  CampaignStartRequest,
  PresetConfig,
} from "../types";

type UploadedAsset = {
  name: string;
  type: string;
  size: number;
  base64: string;
};

type BrandColorPreference = {
  id: string;
  name: string;
  hex: string;
  usage: string;
};

type CreativeFormatOption = {
  id: string;
  label: string;
  hint: string;
};

type IntakeOperatorNotes = {
  intake_mode?: string;
  preset?: string;
  uploaded_assets?: UploadedAsset[];
  palette_preferences?: Array<{ name: string; hex: string; usage: string }>;
  custom_model_params?: string;
};

type MoodboardImage = {
  id: string;
  image_url: string;
  description: string;
};

const MAX_FILE_SIZE = 1024 * 1024;
const HEX_COLOR_PATTERN = /^#[0-9a-fA-F]{6}$/;
const DISPLAY_FONT_FALLBACKS = [
  "Fraunces",
  "Bodoni Moda",
  "Cormorant Garamond",
  "Cinzel",
  "Space Grotesk",
  "Playfair Display",
  "Abril Fatface",
  "Libre Baskerville",
  "Lora",
  "Merriweather",
  "Oswald",
  "Bebas Neue",
  "Archivo Black",
  "Montserrat",
  "Poppins",
  "Raleway",
  "Outfit",
  "Rubik",
  "Urbanist",
  "Figtree",
  "DM Serif Display",
  "Prata",
];
const UI_FONT_FALLBACKS = [
  "Sora",
  "Manrope",
  "Plus Jakarta Sans",
  "DM Sans",
  "Source Sans 3",
  "Inter",
  "Figtree",
  "Outfit",
  "Urbanist",
  "Nunito Sans",
  "Work Sans",
  "Rubik",
  "Poppins",
  "Montserrat",
  "Lato",
  "Open Sans",
  "Noto Sans",
  "Raleway",
  "Mukta",
  "Cabin",
  "Karla",
  "Assistant",
];
const TECH_FONT_FALLBACKS = [
  "IBM Plex Mono",
  "JetBrains Mono",
  "Space Mono",
  "Source Code Pro",
  "Recursive",
  "Fira Code",
  "Inconsolata",
  "Cousine",
  "Roboto Mono",
  "Ubuntu Mono",
  "PT Mono",
  "Overpass Mono",
  "Anonymous Pro",
  "B612 Mono",
  "Share Tech Mono",
  "Major Mono Display",
  "Red Hat Mono",
  "Victor Mono",
  "Cutive Mono",
  "Courier Prime",
];
const DEFAULT_PALETTE_PREFERENCES: BrandColorPreference[] = [
  { id: "palette-1", name: "Primary", hex: "#111111", usage: "Primary text and dominant brand anchor" },
  { id: "palette-2", name: "Secondary", hex: "#f3d33b", usage: "Buttons and call-to-action highlights" },
  { id: "palette-3", name: "Background", hex: "#f4f5ed", usage: "Canvas and large layout surfaces" },
];

const CREATIVE_FORMAT_OPTIONS: CreativeFormatOption[] = [
  { id: "poster", label: "Poster", hint: "Hero poster with editorial treatment" },
  { id: "banner", label: "Banner", hint: "Wide campaign banner visual" },
  { id: "ad_instagram", label: "Instagram Ad", hint: "Platform-ready Instagram marketing ad" },
  { id: "ad_facebook", label: "Facebook Ad", hint: "Conversion-oriented Facebook creative" },
  { id: "ad_linkedin", label: "LinkedIn Ad", hint: "Professional LinkedIn ad visual" },
];

const BANNER_SIZE_OPTIONS = ["16:9", "1.91:1", "4:1", "3:1"];

function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`Failed to read ${file.name}`));
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error(`Invalid file encoding for ${file.name}`));
        return;
      }
      resolve(result.split(",")[1] ?? "");
    };
    reader.readAsDataURL(file);
  });
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes}B`;
  }
  return `${(bytes / 1024).toFixed(0)}KB`;
}

function asStringArray(input: unknown): string[] {
  if (!Array.isArray(input)) {
    return [];
  }
  return input
    .map((item) => String(item ?? "").trim())
    .filter((item) => item.length > 0);
}

function parseOperatorNotes(raw: unknown): IntakeOperatorNotes {
  if (typeof raw !== "string" || !raw.trim()) {
    return {};
  }
  try {
    const parsed = JSON.parse(raw);
    return typeof parsed === "object" && parsed ? (parsed as IntakeOperatorNotes) : {};
  } catch {
    return {};
  }
}

function normalizeUploadedAssets(input: unknown): UploadedAsset[] {
  if (!Array.isArray(input)) {
    return [];
  }
  return input
    .filter((item) => typeof item === "object" && item)
    .map((item) => {
      const candidate = item as Record<string, unknown>;
      return {
        name: String(candidate.name ?? "asset"),
        type: String(candidate.type ?? "application/octet-stream"),
        size: Number(candidate.size ?? 0),
        base64: String(candidate.base64 ?? ""),
      };
    })
    .filter((item) => item.base64.length > 0);
}

function normalizePaletteWithIds(input: unknown): BrandColorPreference[] {
  if (!Array.isArray(input)) {
    return [];
  }
  return input
    .filter((item) => typeof item === "object" && item)
    .map((item, index) => {
      const candidate = item as Record<string, unknown>;
      return {
        id: `palette-history-${Date.now()}-${index}`,
        name: String(candidate.name ?? "Color"),
        hex: String(candidate.hex ?? "").toLowerCase(),
        usage: String(candidate.usage ?? ""),
      };
    })
    .filter((item) => item.name.trim() && HEX_COLOR_PATTERN.test(item.hex));
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

export function IntakePage() {
  const navigate = useNavigate();
  const { start, isLoading, status, campaignId, error, clearError } = useCampaignStore();
  const [step, setStep] = useState<1 | 2>(1);
  const [preset, setPreset] = useState<PresetConfig | null>(null);
  const [customMode, setCustomMode] = useState(false);
  const [assets, setAssets] = useState<UploadedAsset[]>([]);
  const [assetError, setAssetError] = useState<string | null>(null);

  const [brandName, setBrandName] = useState("");
  const [brandDescription, setBrandDescription] = useState("");
  const [campaignGoal, setCampaignGoal] = useState(CAMPAIGN_GOALS[0]);
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [audience, setAudience] = useState("");
  const [marketsText, setMarketsText] = useState("");
  const [channels, setChannels] = useState<string[]>([]);
  const [budgetTier, setBudgetTier] = useState(BUDGET_TIERS[1]);
  const [competitorsText, setCompetitorsText] = useState("");
  const [customIndustry, setCustomIndustry] = useState("general");
  const [customToneText, setCustomToneText] = useState("editorial, confident, clear");
  const [customTaboosText, setCustomTaboosText] = useState("generic messaging");
  const [customModelParams, setCustomModelParams] = useState("");
  const [intakeTab, setIntakeTab] = useState<"setup" | "moodboard">("setup");
  const [moodboardQuery, setMoodboardQuery] = useState("");
  const [moodboardLoading, setMoodboardLoading] = useState(false);
  const [moodboardImages, setMoodboardImages] = useState<MoodboardImage[]>([]);
  const [selectedMoodboardImage, setSelectedMoodboardImage] = useState<string>("");
  const [creativeFormats, setCreativeFormats] = useState<string[]>([
    "poster",
    "banner",
    "ad_instagram",
    "ad_facebook",
    "ad_linkedin",
  ]);
  const [bannerSize, setBannerSize] = useState("16:9");

  const [brandLookup, setBrandLookup] = useState<BrandIdentityLookupResponse | null>(null);
  const [lookupLoading, setLookupLoading] = useState(false);
  const [reuseBrandIdentity, setReuseBrandIdentity] = useState(true);
  const [fontPreferences, setFontPreferences] = useState({ display: "", ui: "", technical: "" });
  const [palettePreferences, setPalettePreferences] = useState<BrandColorPreference[]>(DEFAULT_PALETTE_PREFERENCES);
  const [campaignHistory, setCampaignHistory] = useState<CampaignHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const hasCampaign = useMemo(() => Boolean(campaignId && status), [campaignId, status]);

  useEffect(() => {
    let cancelled = false;
    const loadHistory = async () => {
      try {
        setHistoryLoading(true);
        const result = await listCampaignHistory();
        if (!cancelled) {
          setCampaignHistory(result.campaigns ?? []);
          setHistoryError(null);
        }
      } catch (historyLoadError) {
        if (!cancelled) {
          setHistoryError(historyLoadError instanceof Error ? historyLoadError.message : "Failed to load campaign history.");
        }
      } finally {
        if (!cancelled) {
          setHistoryLoading(false);
        }
      }
    };

    void loadHistory();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (step !== 2) {
      return;
    }

    const query = brandName.trim();
    if (query.length < 2) {
      setBrandLookup(null);
      setLookupLoading(false);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        setLookupLoading(true);
        const found = await getBrandIdentity(query);
        if (cancelled) {
          return;
        }
        setBrandLookup(found);
        if (found.exists) {
          setReuseBrandIdentity(true);
          const cachedFonts = found.profile?.identity?.font_system;
          if (cachedFonts) {
            setFontPreferences({
              display: cachedFonts.display ?? "",
              ui: cachedFonts.ui ?? "",
              technical: cachedFonts.technical ?? "",
            });
          }
        } else {
          setReuseBrandIdentity(false);
        }
      } catch {
        if (!cancelled) {
          setBrandLookup(null);
        }
      } finally {
        if (!cancelled) {
          setLookupLoading(false);
        }
      }
    }, 500);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [brandName, step]);

  useEffect(() => {
    if (step !== 2) {
      return;
    }
    const industrySeed = (customMode ? customIndustry : preset?.industry) || "brand design";
    if (!moodboardQuery.trim()) {
      setMoodboardQuery(String(industrySeed));
    }
  }, [step, customMode, customIndustry, preset?.industry, moodboardQuery]);

  const loadMoodboard = async (queryValue?: string) => {
    const sourceQuery = String(queryValue || moodboardQuery || customIndustry || preset?.industry || "brand design").trim();
    if (!sourceQuery) {
      return;
    }
    try {
      setMoodboardLoading(true);
      const photos = await searchReferenceImages(sourceQuery, 9);
      setMoodboardImages(
        photos.slice(0, 9).map((item) => ({
          id: item.id,
          image_url: item.image_url,
          description: item.description,
        }))
      );
      if (!selectedMoodboardImage && photos[0]?.image_url) {
        setSelectedMoodboardImage(photos[0].image_url);
      }
    } catch {
      setMoodboardImages([]);
    } finally {
      setMoodboardLoading(false);
    }
  };

  useEffect(() => {
    if (intakeTab !== "moodboard") {
      return;
    }
    if (moodboardImages.length > 0 || moodboardLoading) {
      return;
    }
    void loadMoodboard(moodboardQuery || customIndustry || preset?.industry || "brand design");
  }, [intakeTab, moodboardImages.length, moodboardLoading, moodboardQuery, customIndustry, preset?.industry]);

  const roleFontOptions = useMemo(() => {
    const optionMap = brandLookup?.profile?.identity?.font_options;
    const fromLookup = {
      display: (optionMap?.display ?? []).map((item) => item.family),
      ui: (optionMap?.ui ?? []).map((item) => item.family),
      technical: (optionMap?.technical ?? []).map((item) => item.family),
    };

    return {
      display: [...new Set([...fromLookup.display, ...DISPLAY_FONT_FALLBACKS])],
      ui: [...new Set([...fromLookup.ui, ...UI_FONT_FALLBACKS])],
      technical: [...new Set([...fromLookup.technical, ...TECH_FONT_FALLBACKS])],
    };
  }, [brandLookup]);

  const onDrop = async (acceptedFiles: File[]) => {
    setAssetError(null);
    clearError();
    const tooLarge = acceptedFiles.find((file) => file.size > MAX_FILE_SIZE);
    if (tooLarge) {
      setAssetError(`${tooLarge.name} is larger than 1MB. Keep uploads lightweight for hackathon speed.`);
      return;
    }

    try {
      const encoded = await Promise.all(
        acceptedFiles.map(async (file) => ({
          name: file.name,
          type: file.type,
          size: file.size,
          base64: await toBase64(file),
        }))
      );
      setAssets((current) => [...current, ...encoded]);
    } catch (dropError) {
      setAssetError(dropError instanceof Error ? dropError.message : "Failed to encode files.");
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: true,
    accept: {
      "application/pdf": [".pdf"],
      "image/*": [".png", ".jpg", ".jpeg", ".webp"],
    },
  });

  const selectPreset = (selected: PresetConfig) => {
    setCustomMode(false);
    setPreset(selected);
    setAudience(selected.defaultAudience);
    setMarketsText(selected.defaultMarkets.join(", "));
    setChannels(selected.defaultChannels);
    setStep(2);
  };

  const selectCustom = () => {
    setCustomMode(true);
    setPreset(null);
    setAudience("");
    setMarketsText("Mumbai, London");
    setChannels(["instagram", "linkedin", "email"]);
    setStep(2);
  };

  const loadCampaignIntoForm = (entry: CampaignHistoryItem) => {
    const payload = entry.start_payload ?? {};
    const asRecord = (value: unknown): Record<string, unknown> =>
      typeof value === "object" && value ? (value as Record<string, unknown>) : {};

    const notes = parseOperatorNotes(payload.operator_notes);
    const modelOverrides = asRecord(payload.model_overrides);
    const toneValues = asStringArray(payload.tone);
    const tabooValues = asStringArray(payload.taboos);
    const marketValues = asStringArray(payload.target_markets);
    const channelValues = asStringArray(payload.channels);
    const competitorValues = asStringArray(payload.competitors);
    const formatValues = asStringArray(modelOverrides.creative_formats);

    const presetId = String(notes.preset ?? "").trim();
    const shouldUseCustom =
      presetId === "custom" ||
      String(notes.intake_mode ?? "").toLowerCase().includes("custom");
    const matchedPreset = INDUSTRY_PRESETS.find((item) => item.id === presetId) ?? null;

    setBrandName(String(payload.brand_name ?? ""));
    setBrandDescription(String(payload.brand_description ?? ""));
    setCampaignGoal(String(payload.campaign_goal ?? CAMPAIGN_GOALS[0]));
    setWebsiteUrl(String(payload.website_url ?? ""));
    setAudience(String(payload.audience ?? ""));
    setMarketsText(marketValues.join(", "));
    setChannels(channelValues.length ? channelValues : ["instagram", "linkedin", "email"]);
    setBudgetTier(String(payload.budget_tier ?? BUDGET_TIERS[1]));
    setCompetitorsText(competitorValues.join(", "));
    setCreativeFormats(
      formatValues.length > 0
        ? formatValues
        : ["poster", "banner", "ad_instagram", "ad_facebook", "ad_linkedin"]
    );
    setBannerSize(String(modelOverrides.banner_size ?? "16:9"));
    setSelectedMoodboardImage(String(modelOverrides.moodboard_image_url ?? ""));
    if (String(modelOverrides.moodboard_query ?? "").trim()) {
      setMoodboardQuery(String(modelOverrides.moodboard_query));
    }
    setCustomIndustry(String(payload.industry ?? "general"));
    setCustomToneText(toneValues.join(", "));
    setCustomTaboosText(tabooValues.join(", "));
    setReuseBrandIdentity(Boolean(payload.reuse_brand_identity ?? true));

    const savedFonts = asRecord(payload.font_preferences);
    setFontPreferences({
      display: String(savedFonts.display ?? ""),
      ui: String(savedFonts.ui ?? ""),
      technical: String(savedFonts.technical ?? ""),
    });

    const restoredAssets = normalizeUploadedAssets(notes.uploaded_assets);
    setAssets(restoredAssets);

    const paletteFromNotes = normalizePaletteWithIds(notes.palette_preferences);
    const paletteFromOverrides = normalizePaletteWithIds(modelOverrides.palette_preferences);
    const mergedPalette = paletteFromNotes.length > 0 ? paletteFromNotes : paletteFromOverrides;
    setPalettePreferences(mergedPalette.length > 0 ? mergedPalette : DEFAULT_PALETTE_PREFERENCES);

    if (notes.custom_model_params && String(notes.custom_model_params).trim()) {
      setCustomModelParams(String(notes.custom_model_params));
    } else if (Object.keys(modelOverrides).length > 0) {
      setCustomModelParams(JSON.stringify(modelOverrides, null, 2));
    } else {
      setCustomModelParams("");
    }

    if (shouldUseCustom) {
      setCustomMode(true);
      setPreset(null);
    } else {
      setCustomMode(false);
      setPreset(matchedPreset);
    }

    setAssetError(null);
    clearError();
    setStep(2);
  };

  const toggleChannel = (channel: string) => {
    setChannels((current) => {
      if (current.includes(channel)) {
        return current.filter((item) => item !== channel);
      }
      return [...current, channel];
    });
  };

  const toggleCreativeFormat = (formatId: string) => {
    setCreativeFormats((current) => {
      if (current.includes(formatId)) {
        return current.filter((item) => item !== formatId);
      }
      return [...current, formatId];
    });
  };

  const updatePalettePreference = (id: string, key: "name" | "hex" | "usage", value: string) => {
    setPalettePreferences((current) =>
      current.map((item) => {
        if (item.id !== id) {
          return item;
        }
        return {
          ...item,
          [key]: key === "hex" ? value.toLowerCase() : value,
        };
      })
    );
  };

  const addPalettePreference = () => {
    setPalettePreferences((current) => [
      ...current,
      {
        id: `palette-${Date.now()}-${current.length}`,
        name: `Color ${current.length + 1}`,
        hex: "#808080",
        usage: "Custom brand color",
      },
    ]);
  };

  const removePalettePreference = (id: string) => {
    setPalettePreferences((current) => current.filter((item) => item.id !== id));
  };

  const submit = async () => {
    clearError();
    if (!preset && !customMode) {
      setAssetError("Choose an industry preset first.");
      return;
    }

    const targetMarkets = marketsText
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);

    if (targetMarkets.length < 2) {
      setAssetError("Add at least two markets, separated by commas.");
      return;
    }

    if (!brandName.trim() || !brandDescription.trim() || !audience.trim()) {
      setAssetError("Brand name, description, and audience are required.");
      return;
    }

    if (creativeFormats.length === 0) {
      setAssetError("Select at least one creative format (poster, banner, or platform ad).");
      return;
    }

    const toneKeywords = (customMode ? customToneText : preset?.toneKeywords.join(",") ?? "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);

    if (toneKeywords.length === 0) {
      setAssetError("Provide at least one tone keyword.");
      return;
    }

    const taboos = (customMode ? customTaboosText : preset?.contentTaboos.join(",") ?? "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);

    const activeIndustry = customMode ? customIndustry.trim() || "general" : preset?.industry ?? "general";

    let modelOverrides: Record<string, unknown> = {};
    if (customModelParams.trim()) {
      try {
        const parsed = JSON.parse(customModelParams);
        modelOverrides = typeof parsed === "object" && parsed ? (parsed as Record<string, unknown>) : {};
      } catch {
        modelOverrides = { custom_instructions: customModelParams.trim() };
      }
    }

    const cleanedPalettePreferences = palettePreferences
      .map((item) => ({
        name: item.name.trim(),
        hex: item.hex.trim().toLowerCase(),
        usage: item.usage.trim(),
      }))
      .filter((item) => item.name && HEX_COLOR_PATTERN.test(item.hex));

    if (cleanedPalettePreferences.length > 0) {
      modelOverrides = {
        ...modelOverrides,
        palette_preferences: cleanedPalettePreferences,
      };
    }

    modelOverrides = {
      ...modelOverrides,
      creative_formats: creativeFormats,
      banner_size: bannerSize,
      caption_provider: "groq",
      image_provider: "kie",
      moodboard_query: moodboardQuery.trim(),
      moodboard_image_url: selectedMoodboardImage || undefined,
    };

    const notes = {
      intake_mode: customMode ? "custom_plus_multimodal" : "preset_plus_multimodal",
      preset: customMode ? "custom" : preset?.id,
      uploaded_assets: assets.map((asset) => ({
        name: asset.name,
        type: asset.type,
        size: asset.size,
        base64: asset.base64,
      })),
      palette_preferences: cleanedPalettePreferences,
      custom_model_params: customModelParams.trim(),
    };

    const cleanedFontPreferences = Object.fromEntries(
      Object.entries(fontPreferences).filter(([, value]) => value.trim().length > 0)
    );

    const payload: CampaignStartRequest = {
      brand: {
        name: brandName.trim(),
        description: brandDescription.trim(),
        tone: toneKeywords,
        audience: audience.trim(),
        taboos,
        industry: activeIndustry,
        website_url: websiteUrl.trim() || undefined,
      },
      target_markets: targetMarkets,
      campaign_goal: campaignGoal,
      channels: channels.length ? channels : preset?.defaultChannels ?? ["instagram", "linkedin", "email"],
      budget_tier: budgetTier,
      operator_notes: JSON.stringify(notes),
      competitors: competitorsText
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean),
      reuse_brand_identity: reuseBrandIdentity,
      font_preferences: cleanedFontPreferences,
      model_overrides: modelOverrides,
    };

    try {
      await start(payload);
      navigate("/admin");
    } catch (submitError) {
      setAssetError(submitError instanceof Error ? submitError.message : "Failed to start campaign.");
    }
  };

  return (
    <section className="intake-layout">
      <div className="intake-visual">
        <p className="mono overline">FOR HUMANS / FOR AI AGENTS</p>
        <h2>Campaigns are mathematical.</h2>
        <p>
          Marketing is mathematical. Let&apos;s define your variables with industry presets, live context,
          and multimodal brand assets.
        </p>
      </div>

      <div className="intake-panel">
        <div className="stepper">
          <button
            type="button"
            onClick={() => setStep(1)}
            className={step === 1 ? "step-active" : "step"}
          >
            01 PRESET
          </button>
          <button
            type="button"
            onClick={() => setStep(2)}
            disabled={!preset && !customMode}
            className={step === 2 ? "step-active" : "step"}
          >
            02 FEED THE BRAIN
          </button>
        </div>

        {step === 1 && (
          <div className="preset-grid">
            <button
              type="button"
              className={customMode ? "preset-card preset-card-active" : "preset-card"}
              onClick={selectCustom}
            >
              <span className="mono">CUSTOM</span>
              <p>Start from scratch with custom industry, tone, taboos, and model instructions.</p>
            </button>
            {INDUSTRY_PRESETS.map((item) => (
              <button
                key={item.id}
                type="button"
                className={preset?.id === item.id ? "preset-card preset-card-active" : "preset-card"}
                onClick={() => selectPreset(item)}
              >
                <span className="mono">{item.label}</span>
                <p>{item.description}</p>
              </button>
            ))}
          </div>
        )}

        {step === 2 && (preset || customMode) && (
          <div className="form-grid">
            <div className="span-2 intake-subtabs">
              <button
                type="button"
                className={intakeTab === "setup" ? "tab tab-active" : "tab"}
                onClick={() => setIntakeTab("setup")}
              >
                Campaign Setup
              </button>
              <button
                type="button"
                className={intakeTab === "moodboard" ? "tab tab-active" : "tab"}
                onClick={() => setIntakeTab("moodboard")}
              >
                Moodboard
              </button>
            </div>

            <div className="span-2 history-wrap">
              <div className="history-header">
                <p className="mono overline">PREVIOUS CHATS / SAVED ONBOARDING SESSIONS</p>
                <button
                  type="button"
                  className="chip"
                  onClick={async () => {
                    try {
                      setHistoryLoading(true);
                      const refreshed = await listCampaignHistory();
                      setCampaignHistory(refreshed.campaigns ?? []);
                      setHistoryError(null);
                    } catch (refreshError) {
                      setHistoryError(refreshError instanceof Error ? refreshError.message : "Failed to refresh history.");
                    } finally {
                      setHistoryLoading(false);
                    }
                  }}
                >
                  {historyLoading ? "REFRESHING..." : "REFRESH HISTORY"}
                </button>
              </div>

              {historyError && <p className="form-error history-error">{historyError}</p>}

              {!historyLoading && campaignHistory.length === 0 && (
                <p className="history-empty">No prior chats yet. Start one campaign and it will appear here.</p>
              )}

              <div className="history-list">
                {campaignHistory.map((item) => {
                  const payload = item.start_payload ?? {};
                  const brandLabel = String(payload.brand_name ?? "Unknown Brand");
                  const goalLabel = String(payload.campaign_goal ?? "n/a");
                  const marketLabel = asStringArray(payload.target_markets).join(", ") || "n/a";
                  const providers = item.content_hub?.providers_used?.join(", ") || "n/a";
                  return (
                    <article key={item.campaign_id} className="history-item">
                      <div className="history-item-head">
                        <div>
                          <p className="mono history-title">{brandLabel}</p>
                          <p className="history-meta">
                            {formatTimestamp(item.created_at)} · {String(item.status).toUpperCase()} · {item.current_node}
                          </p>
                        </div>
                        <button type="button" className="chip chip-active" onClick={() => loadCampaignIntoForm(item)}>
                          LOAD INTO FORM
                        </button>
                      </div>
                      <p className="history-line">Goal: {goalLabel}</p>
                      <p className="history-line">Markets: {marketLabel}</p>
                      <p className="history-line">
                        Content Hub: {item.content_hub?.has_content ? "saved" : "pending"} · Cards: {item.content_hub?.asset_card_count ?? 0}
                        {" · "}
                        Providers: {providers}
                      </p>
                    </article>
                  );
                })}
              </div>
            </div>

            {intakeTab === "moodboard" && (
              <div className="span-2 moodboard-wrap">
                <div className="moodboard-head">
                  <p className="mono overline">Moodboard</p>
                  <p>Select one style reference image. Gemini analyzes it and KIE uses that style for generated posters.</p>
                </div>

                <div className="moodboard-controls">
                  <input
                    value={moodboardQuery}
                    onChange={(event) => setMoodboardQuery(event.target.value)}
                    placeholder="Industry mood (Google Images), e.g. Minimalist Coffee"
                  />
                  <button
                    type="button"
                    className={moodboardLoading ? "chip loading-button" : "chip"}
                    onClick={() => void loadMoodboard(moodboardQuery)}
                    disabled={moodboardLoading}
                  >
                    {moodboardLoading ? "LOADING REFERENCES..." : "Load Google Moodboard"}
                  </button>
                </div>

                <div className="moodboard-grid">
                  {moodboardImages.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={selectedMoodboardImage === item.image_url ? "moodboard-item moodboard-item-active" : "moodboard-item"}
                      onClick={() => setSelectedMoodboardImage(item.image_url)}
                    >
                      <img
                        src={toProxiedAssetUrl(item.image_url)}
                        alt={item.description || "Moodboard reference"}
                        loading="lazy"
                        referrerPolicy="no-referrer"
                        onError={(event) => {
                          const element = event.currentTarget;
                          element.onerror = null;
                          element.src = `https://picsum.photos/seed/moodboard-${item.id}/900/600`;
                        }}
                      />
                    </button>
                  ))}
                </div>

                {selectedMoodboardImage && (
                  <p className="moodboard-selected mono">Selected style reference locked for campaign generation.</p>
                )}
              </div>
            )}

            <label>
              Brand Name
              <input value={brandName} onChange={(event) => setBrandName(event.target.value)} />
            </label>

            {lookupLoading && <p className="mono status-line">Checking saved Brand Identity...</p>}

            {brandLookup?.exists && (
              <div className="span-2 identity-reuse-box">
                <p className="mono overline">EXISTING BRAND PROFILE FOUND</p>
                <p>
                  We found saved Business DNA for <strong>{brandLookup.brand_name}</strong>.
                  {" "}
                  Updated at {brandLookup.updated_at ?? "unknown"}. Use it directly or regenerate and edit.
                </p>
                <div className="channels-grid">
                  <button
                    type="button"
                    className={reuseBrandIdentity ? "chip chip-active" : "chip"}
                    onClick={() => setReuseBrandIdentity(true)}
                  >
                    USE SAVED IDENTITY
                  </button>
                  <button
                    type="button"
                    className={!reuseBrandIdentity ? "chip chip-active" : "chip"}
                    onClick={() => setReuseBrandIdentity(false)}
                  >
                    EDIT / REGENERATE
                  </button>
                </div>
              </div>
            )}

            <label>
              Campaign Goal
              <select value={campaignGoal} onChange={(event) => setCampaignGoal(event.target.value)}>
                {CAMPAIGN_GOALS.map((goal) => (
                  <option key={goal} value={goal}>
                    {goal}
                  </option>
                ))}
              </select>
            </label>
            <label className="span-2">
              Brand Description
              <textarea
                rows={4}
                value={brandDescription}
                onChange={(event) => setBrandDescription(event.target.value)}
              />
            </label>
            <label>
              Website URL
              <input value={websiteUrl} onChange={(event) => setWebsiteUrl(event.target.value)} />
            </label>
            <label>
              Audience
              <input value={audience} onChange={(event) => setAudience(event.target.value)} />
            </label>
            <label className="span-2">
              Target Markets (comma separated)
              <input value={marketsText} onChange={(event) => setMarketsText(event.target.value)} />
            </label>

            <div className="span-2 channels-wrap">
              <p className="mono overline">CHANNELS</p>
              <div className="channels-grid">
                {CHANNEL_OPTIONS.map((channel) => (
                  <button
                    key={channel}
                    type="button"
                    onClick={() => toggleChannel(channel)}
                    className={channels.includes(channel) ? "chip chip-active" : "chip"}
                  >
                    {channel.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>

            <div className="span-2 channels-wrap creative-format-wrap">
              <p className="mono overline">CREATIVE FORMAT ROUTING</p>
              <p className="creative-format-subtitle">
                Captions are generated via Groq while visuals route to KIE in parallel. Choose the output types first.
              </p>
              <div className="creative-format-grid">
                {CREATIVE_FORMAT_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => toggleCreativeFormat(option.id)}
                    className={creativeFormats.includes(option.id) ? "creative-format-chip creative-format-chip-active" : "creative-format-chip"}
                  >
                    <span className="creative-format-title">{option.label}</span>
                    <span className="creative-format-hint">{option.hint}</span>
                  </button>
                ))}
              </div>
              <label className="creative-size-row">
                Banner Size
                <select value={bannerSize} onChange={(event) => setBannerSize(event.target.value)}>
                  {BANNER_SIZE_OPTIONS.map((size) => (
                    <option key={size} value={size}>
                      {size}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label>
              Budget Tier
              <select value={budgetTier} onChange={(event) => setBudgetTier(event.target.value)}>
                {BUDGET_TIERS.map((tier) => (
                  <option key={tier} value={tier}>
                    {tier}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Competitors (comma separated)
              <input value={competitorsText} onChange={(event) => setCompetitorsText(event.target.value)} />
            </label>

            <div className="span-2 channels-wrap">
              <p className="mono overline">FONT PREFERENCES (EDITABLE + SAVED)</p>
              <div className="form-grid">
                <label>
                  Display Font
                  <select
                    value={fontPreferences.display}
                    onChange={(event) =>
                      setFontPreferences((current) => ({ ...current, display: event.target.value }))
                    }
                  >
                    <option value="">Auto-select</option>
                    {roleFontOptions.display.map((font) => (
                      <option key={font} value={font}>
                        {font}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  UI Font
                  <select
                    value={fontPreferences.ui}
                    onChange={(event) =>
                      setFontPreferences((current) => ({ ...current, ui: event.target.value }))
                    }
                  >
                    <option value="">Auto-select</option>
                    {roleFontOptions.ui.map((font) => (
                      <option key={font} value={font}>
                        {font}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Technical Font
                  <select
                    value={fontPreferences.technical}
                    onChange={(event) =>
                      setFontPreferences((current) => ({ ...current, technical: event.target.value }))
                    }
                  >
                    <option value="">Auto-select</option>
                    {roleFontOptions.technical.map((font) => (
                      <option key={font} value={font}>
                        {font}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </div>

            <div className="span-2 channels-wrap palette-editor-wrap">
              <p className="mono overline">BRAND PALETTE PREFERENCES (USER-DEFINED)</p>
              <p className="palette-editor-note">
                Build your own palette. These values are passed to the model and used as direct identity overrides.
              </p>
              <div className="palette-editor-grid">
                {palettePreferences.map((item) => (
                  <div key={item.id} className="palette-editor-row">
                    <input
                      type="color"
                      value={HEX_COLOR_PATTERN.test(item.hex) ? item.hex : "#808080"}
                      onChange={(event) => updatePalettePreference(item.id, "hex", event.target.value)}
                      aria-label={`${item.name || "Custom"} color picker`}
                    />
                    <input
                      value={item.name}
                      onChange={(event) => updatePalettePreference(item.id, "name", event.target.value)}
                      placeholder="Color name"
                    />
                    <input
                      value={item.hex}
                      onChange={(event) => updatePalettePreference(item.id, "hex", event.target.value)}
                      placeholder="#RRGGBB"
                    />
                    <input
                      value={item.usage}
                      onChange={(event) => updatePalettePreference(item.id, "usage", event.target.value)}
                      placeholder="Usage"
                    />
                    <button type="button" className="palette-remove" onClick={() => removePalettePreference(item.id)}>
                      REMOVE
                    </button>
                  </div>
                ))}
              </div>
              <button type="button" className="palette-add" onClick={addPalettePreference}>
                ADD COLOR
              </button>
            </div>

            {customMode && (
              <>
                <label>
                  Custom Industry
                  <input value={customIndustry} onChange={(event) => setCustomIndustry(event.target.value)} />
                </label>
                <label>
                  Tone Keywords (comma separated)
                  <input value={customToneText} onChange={(event) => setCustomToneText(event.target.value)} />
                </label>
                <label className="span-2">
                  Taboos (comma separated)
                  <input value={customTaboosText} onChange={(event) => setCustomTaboosText(event.target.value)} />
                </label>
                <label className="span-2">
                  Custom Model Parameters (JSON or free text)
                  <textarea
                    rows={4}
                    value={customModelParams}
                    onChange={(event) => setCustomModelParams(event.target.value)}
                    placeholder='{"priority":"high", "campaign_window":"Q3"}'
                  />
                </label>
              </>
            )}

            <div className="span-2 dropzone-wrap">
              <p className="mono overline">MULTIMODAL DROPZONE</p>
              <div {...getRootProps()} className={isDragActive ? "dropzone dropzone-active" : "dropzone"}>
                <input {...getInputProps()} />
                <p>Drop PDFs or images. Files are converted to Base64 and sent with intake context.</p>
              </div>
              {assets.length > 0 && (
                <ul className="asset-list">
                  {assets.map((asset) => (
                    <li key={`${asset.name}-${asset.size}`} className="mono">
                      {asset.name} · {formatBytes(asset.size)}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {(assetError || error) && <p className="form-error">{assetError || error}</p>}

            <button
              type="button"
              className={isLoading ? "primary-action loading-button" : "primary-action"}
              onClick={submit}
              disabled={isLoading}
            >
              {isLoading ? "GENERATING..." : "GENERATE CAMPAIGN ->"}
            </button>

            {hasCampaign && (
              <p className="mono status-line">
                CAMPAIGN {campaignId?.slice(0, 8)} · STATUS {status?.status.toUpperCase()} · NODE {status?.current_node}
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
