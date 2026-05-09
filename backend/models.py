from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Literal

from pydantic import BaseModel, Field, field_validator


class BrandInput(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    tone: List[str] = Field(min_length=1)
    audience: str = Field(min_length=1)
    taboos: List[str] = Field(default_factory=list)
    industry: str = Field(default="general")
    website_url: Optional[str] = None


class CampaignStartRequest(BaseModel):
    brand: BrandInput
    target_markets: List[str] = Field(min_length=2)
    campaign_goal: str = Field(default="awareness")
    channels: List[str] = Field(default_factory=lambda: ["instagram", "linkedin", "email", "whatsapp"])
    budget_tier: str = Field(default="balanced")
    operator_notes: Optional[str] = None
    competitors: List[str] = Field(default_factory=list)
    reuse_brand_identity: bool = Field(default=True)
    font_preferences: Dict[str, str] = Field(default_factory=dict)
    model_overrides: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("target_markets")
    @classmethod
    def validate_target_markets(cls, value: List[str]) -> List[str]:
        cleaned = [market.strip() for market in value if market.strip()]
        if len(cleaned) < 2:
            raise ValueError("At least two target markets are required.")
        return cleaned

    def to_state_payload(self) -> Dict[str, Any]:
        brand = self.brand.model_dump()
        model_overrides = dict(self.model_overrides or {})

        if not isinstance(model_overrides.get("image_provider"), str) or not str(model_overrides.get("image_provider", "")).strip():
            model_overrides["image_provider"] = os.getenv("OPENPOMELLI_DEFAULT_IMAGE_PROVIDER", "kie")

        providers = model_overrides.get("image_providers")
        if not isinstance(providers, list) or not providers:
            model_overrides["image_providers"] = ["kie", "fal", "pollinations"]

        if not isinstance(model_overrides.get("gemini_model"), str) or not str(model_overrides.get("gemini_model", "")).strip():
            model_overrides["gemini_model"] = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-image-preview")

        return {
            "brand_name": brand["name"],
            "brand_description": brand["description"],
            "tone": brand["tone"],
            "audience": brand["audience"],
            "taboos": brand["taboos"],
            "industry": brand["industry"],
            "website_url": brand.get("website_url"),
            "target_markets": self.target_markets,
            "campaign_goal": self.campaign_goal,
            "channels": self.channels,
            "budget_tier": self.budget_tier,
            "operator_notes": self.operator_notes,
            "competitors": self.competitors,
            "reuse_brand_identity": self.reuse_brand_identity,
            "font_preferences": self.font_preferences,
            "model_overrides": model_overrides,
        }


class CampaignStartResponse(BaseModel):
    campaign_id: str
    status: str


class CampaignStatusResponse(BaseModel):
    campaign_id: str
    status: str
    current_node: str
    refinement_count: int
    updated_at: str
    created_at: str
    progress: Dict[str, Any]
    completed_nodes: List[str]


class CampaignLogsResponse(BaseModel):
    campaign_id: str
    logs: List[Dict[str, Any]]


class CampaignHistoryItem(BaseModel):
    campaign_id: str
    status: str
    current_node: str
    created_at: str
    updated_at: str
    start_payload: Dict[str, Any] = Field(default_factory=dict)
    content_hub: Dict[str, Any] = Field(default_factory=dict)


class CampaignHistoryResponse(BaseModel):
    campaigns: List[CampaignHistoryItem] = Field(default_factory=list)


class MiniAgentRunRequest(BaseModel):
    input: str = Field(min_length=1)
    agent_type: str = Field(min_length=1)
    website_url: Optional[str] = None
    context_notes: Optional[str] = None
    uploaded_assets: List[Dict[str, Any]] = Field(default_factory=list)
    model_overrides: Dict[str, Any] = Field(default_factory=dict)


class MiniAgentRunResponse(BaseModel):
    output: str
    trace: Dict[str, Any] = Field(default_factory=dict)


class BrandIdentityLookupResponse(BaseModel):
    exists: bool
    brand_name: str
    profile: Optional[Dict[str, Any]] = None
    updated_at: Optional[str] = None
    source_campaign_id: Optional[str] = None


class BrandIdentityPatchRequest(BaseModel):
    profile_patch: Dict[str, Any] = Field(default_factory=dict)


class GalleryBrandIngestRequest(BaseModel):
    campaign_id: str = Field(min_length=1)
    brand_name: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=25)


class GalleryBrandIngestResponse(BaseModel):
    campaign_id: str
    brand_name: str
    saved_images: int
    searched_urls: List[str] = Field(default_factory=list)


class ReferenceImageSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=30)
    page: int = Field(default=0, ge=0, le=20)
    campaign_id: Optional[str] = None
    persist_to_gallery: bool = False


class ReferenceImageItem(BaseModel):
    id: str
    image_url: str
    description: str
    photographer_name: str
    photographer_url: str
    source: str = "google_images"


class ReferenceImageSearchResponse(BaseModel):
    query: str
    provider: str
    page: int = 0
    saved_images: int = 0
    images: List[ReferenceImageItem] = Field(default_factory=list)


class VadooVideoRequest(BaseModel):
    campaign_id: str = Field(min_length=1)
    brand_name: str = Field(min_length=1)
    duration: str = Field(default="5")
    aspect_ratio: str = Field(default="1:1")


class VadooVideoResponse(BaseModel):
    campaign_id: str
    brand_name: str
    prompt: str
    video_url: Optional[str] = None
    watermark_url: Optional[str] = None
    model: str = "vadoo-ai-story"
    status: str
    task_id: Optional[str] = None
    trace: Dict[str, Any] = Field(default_factory=dict)


SchedulerPlatform = Literal["instagram", "youtube", "twitter"]
SchedulerContentType = Literal["post", "reel", "video"]


class DeterministicScheduleRequest(BaseModel):
    platforms: List[SchedulerPlatform] = Field(default_factory=lambda: ["instagram", "youtube"])
    markets: List[str] = Field(default_factory=lambda: ["Global"])
    content_types: List[SchedulerContentType] = Field(default_factory=list)
    start_date: str = Field(min_length=10)
    days: int = Field(default=30, ge=1, le=90)
    max_slots_per_day: int = Field(default=3, ge=1, le=8)


class DeterministicScheduleItem(BaseModel):
    date: str
    market: str
    platform: SchedulerPlatform
    time: str
    content_type: SchedulerContentType
    score: float
    score_breakdown: Dict[str, float] = Field(default_factory=dict)
    reason: str


class DeterministicScheduleResponse(BaseModel):
    schedule: List[DeterministicScheduleItem] = Field(default_factory=list)
    rules: List[str] = Field(default_factory=list)


class SchedulerGenerateRequest(BaseModel):
    platforms: List[SchedulerPlatform] = Field(default_factory=lambda: ["instagram", "youtube"])
    startDate: str = Field(min_length=10)
    days: int = Field(default=30, ge=1, le=90)
    postsPerDay: int = Field(default=3, ge=1, le=8)
    markets: List[str] = Field(default_factory=lambda: ["Global"])
    contentTypes: List[SchedulerContentType] = Field(default_factory=list)


class SchedulerSummary(BaseModel):
    totalPosts: int
    platformDistribution: Dict[str, int] = Field(default_factory=dict)


class SchedulerGenerateResponse(BaseModel):
    calendar: List[Dict[str, Any]] = Field(default_factory=list)
    summary: SchedulerSummary


class UniPileBundleRequest(BaseModel):
    campaign_id: str = Field(min_length=1)
    channel: Literal["email", "whatsapp", "telegram", "all"] = "all"
    promotion_message: str = Field(default="")


class UniPileBundleResponse(BaseModel):
    campaign_id: str
    email_sent: bool = False
    whatsapp_sent: bool = False
    telegram_sent: bool = False
    linkedin_url: str
    telegram_url: str
    fixed_targets: Dict[str, str] = Field(default_factory=dict)
    provider_trace: Dict[str, Any] = Field(default_factory=dict)


# Backward-compatible aliases.
KlingVideoRequest = VadooVideoRequest
KlingVideoResponse = VadooVideoResponse
