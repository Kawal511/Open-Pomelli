export type CampaignStatus = "queued" | "running" | "completed" | "error";

export type PresetConfig = {
  id: string;
  label: string;
  industry: string;
  description: string;
  toneKeywords: string[];
  contentTaboos: string[];
  defaultAudience: string;
  defaultMarkets: string[];
  defaultChannels: string[];
};

export type BrandInput = {
  name: string;
  description: string;
  tone: string[];
  audience: string;
  taboos: string[];
  industry: string;
  website_url?: string;
};

export type UploadedAssetContext = {
  name: string;
  type: string;
  size: number;
  base64: string;
};

export type CampaignStartRequest = {
  brand: BrandInput;
  target_markets: string[];
  campaign_goal: string;
  channels: string[];
  budget_tier: string;
  operator_notes?: string;
  competitors: string[];
  reuse_brand_identity?: boolean;
  font_preferences?: Record<string, string>;
  model_overrides?: Record<string, unknown>;
};

export type CampaignStartResponse = {
  campaign_id: string;
  status: CampaignStatus;
};

export type CampaignStatusResponse = {
  campaign_id: string;
  status: CampaignStatus;
  current_node: string;
  refinement_count: number;
  updated_at: string;
  created_at: string;
  progress: {
    completed: number;
    total: number;
    target_markets: number;
    percent: number;
  };
  completed_nodes: string[];
};

export type CampaignLog = {
  seq: number;
  ts: string;
  agent: string;
  level: string;
  message: string;
  latency_ms?: number;
  extra: Record<string, unknown>;
};

export type NodeSnapshot = {
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  error?: string;
};

export type CampaignLogsResponse = {
  campaign_id: string;
  logs: CampaignLog[];
};

export type CampaignHistoryItem = {
  campaign_id: string;
  status: CampaignStatus;
  current_node: string;
  created_at: string;
  updated_at: string;
  start_payload: Record<string, unknown>;
  content_hub: {
    has_content: boolean;
    asset_card_count: number;
    markets: string[];
    providers_used: string[];
    has_schedule: boolean;
  };
};

export type CampaignHistoryResponse = {
  campaigns: CampaignHistoryItem[];
};

export type GalleryImageItem = {
  id: number;
  user_id: string;
  campaign_id: string;
  node_name: string;
  source_type: string;
  asset_type: string;
  prompt: string;
  image_url?: string;
  image_path?: string;
  provider?: string;
  model?: string;
  width?: number;
  height?: number;
  status?: string;
  attempted_providers?: Array<{ provider: string; error: string }>;
  error?: string;
  created_at: string;
  updated_at: string;
  brand_name?: string;
};

export type GeneratedVideoItem = {
  id: number;
  user_id: string;
  campaign_id: string;
  node_name: string;
  source_type: string;
  asset_type: string;
  prompt: string;
  image_url?: string;
  provider?: string;
  model?: string;
  status?: string;
  error?: string;
  created_at: string;
  updated_at: string;
  brand_name?: string;
};

export type GalleryTextItem = {
  campaign_id: string;
  brand_name?: string;
  title: string;
  goal?: string;
  markets: string[];
  asset_card_count: number;
  created_at: string;
};

export type GalleryResponse = {
  images: GalleryImageItem[];
  texts: GalleryTextItem[];
  campaigns: CampaignHistoryItem[];
};

export type GalleryBrandIngestRequest = {
  campaign_id: string;
  brand_name: string;
  limit?: number;
};

export type GalleryBrandIngestResponse = {
  campaign_id: string;
  brand_name: string;
  saved_images: number;
  searched_urls: string[];
};

export type SearchReferenceImageItem = {
  id: string;
  image_url: string;
  description: string;
  photographer_name: string;
  photographer_url: string;
  source: string;
};

export type SearchReferenceImageRequest = {
  query: string;
  limit?: number;
  page?: number;
  campaign_id?: string;
  persist_to_gallery?: boolean;
};

export type SearchReferenceImageResponse = {
  query: string;
  provider: string;
  page: number;
  saved_images: number;
  images: SearchReferenceImageItem[];
};

export type UnsplashImageItem = SearchReferenceImageItem;

export type AssetCard = {
  market: string;
  hero_concept: string;
  luxury_video_concepts: string[];
  ugc_concepts: string[];
  social_posts: Record<string, string>;
  direct_copy: Record<string, string>;
  keywords: string[];
  poster_assets?: Array<{
    label: string;
    asset_type?: "poster" | "banner" | "social_ad";
    channel?: string;
    aspect: string;
    width?: number;
    height?: number;
    prompt: string;
    caption?: string;
    image_url: string;
    provider?: string;
    model?: string;
    status?: string;
    attempted?: Array<{ provider: string; error: string }>;
    error?: string;
  }>;
  revision_notes?: string;
};

export type CriticEval = {
  score: number;
  feedback: string;
  diff_log: Array<{ before: string; after: string }>;
};

export type BrandPaletteColor = {
  name: string;
  hex: string;
  usage: string;
};

export type BrandDNA = {
  brand_name: string;
  industry: string;
  tone_of_voice: string[];
  target_audience: string;
  taboos: string[];
  value_proposition: string;
  website_url?: string;
  operating_markets: string[];
  identity?: {
    font_system: {
      display: string;
      ui: string;
      technical: string;
    };
    font_options?: {
      display?: Array<{ family: string; rationale: string }>;
      ui?: Array<{ family: string; rationale: string }>;
      technical?: Array<{ family: string; rationale: string }>;
    };
    font_reasoning?: string;
    palette: BrandPaletteColor[];
    brand_values: string[];
    aesthetic_tags: string[];
  };
  tagline_suggestions?: string[];
  business_overview?: string;
  identity_origin?: "generated" | "cached";
  analysis_sources?: {
    website_scan?: {
      url?: string;
      domain?: string;
      status?: string;
      status_code?: number;
      title?: string;
      signals?: string[];
      headings?: string[];
    };
    image_scan?: {
      asset_count?: number;
      used_asset_count?: number;
      asset_types?: string[];
      used_assets?: Array<{ name: string; type: string; size: number }>;
      skipped_assets?: Array<{ name: string; reason: string }>;
      signals?: string[];
    };
    model_trace?: {
      provider?: string;
      model?: string;
      success?: boolean;
      error?: string;
      attempted_models?: Array<{ model: string; error: string }>;
    };
  };
  identity_reasoning?: {
    summary?: string;
    evidence?: string[];
    website_observations?: string[];
    image_observations?: string[];
  };
};

export type BrandIdentityLookupResponse = {
  exists: boolean;
  brand_name: string;
  profile?: BrandDNA;
  updated_at?: string;
  source_campaign_id?: string;
};

export type ContextualCampaignIdea = {
  title: string;
  objective: string;
  market: string;
  rationale: string;
  deliverables: string[];
  priority: string;
};

export type CampaignStateResponse = {
  campaign_id: string;
  status: CampaignStatus;
  current_node: string;
  refinement_count: number;
  progress: {
    completed: number;
    total: number;
    target_markets: number;
    percent: number;
  };
  start_payload: Record<string, unknown>;
  brand_dna?: BrandDNA;
  strategy?: {
    goal: string;
    core_message: string;
    pillars: string[];
    channel_plan: Record<string, string>;
    risk_controls: Record<string, unknown>;
    contextual_campaign_ideas?: ContextualCampaignIdea[];
  };
  market_brief?: {
    goal?: string;
    market_signals?: Array<Record<string, unknown>>;
    budget_tier?: string;
    channel_bias?: string[];
    market_news?: Array<Record<string, unknown>>;
    reddit_trends?: Array<Record<string, unknown>>;
    source_trace?: Record<string, unknown>;
    structured_brief?: {
      goal?: string;
      brand?: string;
      markets?: string[];
      market_hypotheses?: Array<Record<string, unknown>>;
      channel_playbook?: Record<string, Record<string, unknown>>;
      search_queries?: string[];
      research_trace?: Record<string, unknown>;
    };
  };
  keyword_strategy?: {
    top_10?: string[];
    secondary?: string[];
    search_intent_map?: Array<Record<string, unknown>>;
    seed_terms?: string[];
    trace?: Record<string, unknown>;
  };
  content?: {
    asset_cards: AssetCard[];
    export_bundle?: {
      markets?: string[];
      channel_count?: number;
      providers_used?: string[];
      moodboard_style_prompt?: string;
      moodboard_style_trace?: Record<string, unknown>;
      brand_logo_asset?: {
        label: string;
        aspect: string;
        prompt: string;
        image_url: string;
        provider?: string;
        model?: string;
        status?: string;
      };
      [key: string]: unknown;
    };
  };
  creative_agent?: {
    linkedin?: {
      post?: string;
      hashtags?: string[];
      best_time?: string;
      suggestion?: string;
    };
    instagram?: {
      caption?: string;
      hashtags?: string[];
      best_time?: string;
      suggestion?: string;
    };
    email?: {
      subject?: string;
      body?: string;
      best_time?: string;
      suggestion?: string;
    };
    whatsapp?: {
      message?: string;
      send_window?: string;
      suggestion?: string;
    };
  };
  schedule?: {
    days: Array<{
      day: number;
      date?: string;
      market: string;
      platform?: string;
      time?: string;
      timezone: string;
      hook: string;
      reason?: string;
      score?: number;
      platforms?: Array<{
        name: string;
        time: string;
        reason: string;
        expected_reach?: string;
        color?: string;
      }>;
    }>;
    rules: string[];
  };
  critic_eval?: CriticEval;
  completed_nodes: string[];
  agent_logs: CampaignLog[];
  node_outputs?: Record<string, NodeSnapshot>;
  generated_videos?: GeneratedVideoItem[];
};

export type MiniAgentType =
  | "hook-writer"
  | "seo-analyzer"
  | "image-prompter"
  | "competitor-roaster"
  | "instagram-generator"
  | "linkedin-generator"
  | "email-drafter";

export type MiniAgentRunRequest = {
  input: string;
  agent_type: MiniAgentType;
  website_url?: string;
  context_notes?: string;
  uploaded_assets?: UploadedAssetContext[];
  model_overrides?: Record<string, unknown>;
};

export type MiniAgentRunResponse = {
  output: string;
  trace: Record<string, unknown>;
};

export type VadooVideoRequest = {
  campaign_id: string;
  brand_name: string;
  duration?: string;
  aspect_ratio?: string;
};

export type VadooVideoResponse = {
  campaign_id: string;
  brand_name: string;
  prompt: string;
  video_url?: string;
  watermark_url?: string;
  model: string;
  status: string;
  task_id?: string;
  trace: Record<string, unknown>;
};

export type KlingVideoRequest = VadooVideoRequest;
export type KlingVideoResponse = VadooVideoResponse;

export type UniPileBundleRequest = {
  campaign_id: string;
  channel: "email" | "whatsapp" | "telegram" | "all";
  promotion_message?: string;
};

export type UniPileBundleResponse = {
  campaign_id: string;
  email_sent: boolean;
  whatsapp_sent: boolean;
  telegram_sent: boolean;
  linkedin_url: string;
  telegram_url: string;
  fixed_targets: {
    email: string;
    whatsapp: string;
    telegram: string;
  };
  provider_trace: Record<string, unknown>;
};
