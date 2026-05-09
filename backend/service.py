from __future__ import annotations

import asyncio
from typing import Any, Dict

from backend.graph import (
    build_log,
    _snapshot_node_input,
    _snapshot_node_output,
    a01_brand_dna,
    a02_market_intel,
    a03_audience,
    a04_localisation,
    a05_strategy,
    a06_content,
    a11_creative_agent,
    a07_critic,
    a08_keyword_graph,
    a09_scheduler,
    a10_competitor_gaps,
    build_graph,
    critic_router,
    instrument_node,
    merge_state,
)
from backend.intelligence import (
    call_groq,
    extract_json_object,
    extract_pics_extract_images,
    firecrawl_search,
    vadoo_get_my_balance,
    vadoo_text_to_video,
)
from backend.models import CampaignStartRequest
from backend.repository import CampaignRepository
from backend.state import CampaignContext, initial_state


class CampaignService:
    def __init__(self, db_path: str):
        self.repository = CampaignRepository(db_path)
        self.repository.initialize()
        self.graph = build_graph(self.repository)
        self._resume_nodes = {
            "A01_BrandDNA": instrument_node("A01_BrandDNA", a01_brand_dna, self.repository),
            "A02_MarketIntel": instrument_node("A02_MarketIntel", a02_market_intel, self.repository),
            "A08_KeywordGraph": instrument_node("A08_KeywordGraph", a08_keyword_graph, self.repository),
            "A10_Competitors": instrument_node("A10_Competitors", a10_competitor_gaps, self.repository),
            "A03_Audience": instrument_node("A03_Audience", a03_audience, self.repository),
            "A04_Localisation": instrument_node("A04_Localisation", a04_localisation, self.repository),
            "A05_Strategy": instrument_node("A05_Strategy", a05_strategy, self.repository),
            "A06_Content": instrument_node("A06_Content", a06_content, self.repository),
            "A11_CreativeAgent": instrument_node("A11_CreativeAgent", a11_creative_agent, self.repository),
            "A07_Critic": instrument_node("A07_Critic", a07_critic, self.repository),
            "A09_Scheduler": instrument_node("A09_Scheduler", a09_scheduler, self.repository),
        }

    async def start_campaign(
        self,
        request: CampaignStartRequest,
        user_id: str,
        *,
        user_email: str | None = None,
        user_name: str | None = None,
    ) -> CampaignContext:
        payload = request.to_state_payload()
        payload["auth_user_id"] = user_id
        if request.reuse_brand_identity:
            cached_identity = self.repository.get_brand_identity(user_id, request.brand.name)
            if cached_identity:
                payload["cached_brand_identity"] = cached_identity["profile"]
                payload["cached_brand_identity_updated_at"] = cached_identity["updated_at"]
        state = initial_state(payload)
        self.repository.upsert_user(user_id, email=user_email, display_name=user_name)
        self.repository.create_campaign(state, user_id)
        return state

    async def run_campaign(self, campaign_id: str) -> CampaignContext:
        return await self.resume_campaign(campaign_id)

    async def rerun_critic_agent(self, campaign_id: str, user_id: str) -> CampaignContext:
        state = self.repository.get_campaign(campaign_id, user_id)
        started_status = str(state.get("status") or "running")

        critic_update = await a07_critic(state)
        emitted_logs = critic_update.pop("_emitted_logs", [])

        next_update: Dict[str, Any] = {
            **critic_update,
            "current_node": "A07_Critic",
            "status": started_status,
            "completed_nodes": [],
            "agent_logs": emitted_logs,
            "node_outputs": {
                "A07_Critic": {
                    "input": _snapshot_node_input(state, "A07_Critic"),
                    "output": _snapshot_node_output(critic_update),
                }
            },
        }

        merged = merge_state(state, next_update)

        if started_status == "completed":
            merged["status"] = "completed"

        if not isinstance(emitted_logs, list) or len(emitted_logs) == 0:
            emitted_logs = [
                build_log(
                    state,
                    "A07_Critic",
                    "Manual critic rerun executed from Command Center.",
                    extra={"manual_trigger": True},
                )
            ]

        self.repository.save_transition(merged, "A07_Critic", emitted_logs)
        return merged

    async def resume_campaign(self, campaign_id: str) -> CampaignContext:
        state = self.repository.get_campaign(campaign_id)
        while state["status"] not in {"completed", "error"}:
            next_step = self._next_node(state)
            if next_step is None:
                break

            if next_step == "PARALLEL_FANOUT":
                state = await self._run_parallel_fanout(state)
                continue

            update = await self._resume_nodes[next_step](state)
            state = merge_state(state, update)
            if next_step == "A07_Critic" and critic_router(state) == "A06_Content":
                continue

        return state

    def get_campaign(self, campaign_id: str, user_id: str) -> CampaignContext:
        state = self.repository.get_campaign(campaign_id, user_id)
        videos = self.repository.get_generated_images_for_campaign(user_id, campaign_id, asset_type="video")
        if videos:
            state["generated_videos"] = videos  # type: ignore[index]
            content = state.get("content", {})
            if isinstance(content, dict):
                export_bundle = content.get("export_bundle", {})
                if not isinstance(export_bundle, dict):
                    export_bundle = {}
                export_bundle["generated_videos"] = videos
                state["content"] = {**content, "export_bundle": export_bundle}
        return state

    def get_status(self, campaign_id: str, user_id: str) -> Dict[str, Any]:
        return self.repository.get_status(campaign_id, user_id)

    def get_logs(self, campaign_id: str, user_id: str) -> Dict[str, Any]:
        return {"campaign_id": campaign_id, "logs": self.repository.get_logs(campaign_id, user_id)}

    def list_campaigns(self, user_id: str, limit: int | None = None) -> Dict[str, Any]:
        return {"campaigns": self.repository.list_campaigns(user_id, limit)}

    def get_brand_identity(self, user_id: str, brand_name: str) -> Dict[str, Any] | None:
        return self.repository.get_brand_identity(user_id, brand_name)

    def patch_brand_identity(self, user_id: str, brand_name: str, profile_patch: Dict[str, Any]) -> Dict[str, Any] | None:
        return self.repository.patch_brand_identity(user_id, brand_name, profile_patch)

    def get_gallery(self, user_id: str, campaign_id: str | None = None, limit: int = 300) -> Dict[str, Any]:
        images = self.repository.list_generated_images(user_id, campaign_id=campaign_id, limit=limit)
        campaigns = self.repository.list_campaigns(user_id, limit=200)

        text_cards: list[Dict[str, Any]] = []
        for campaign in campaigns:
            if campaign_id and campaign.get("campaign_id") != campaign_id:
                continue
            payload = campaign.get("start_payload") if isinstance(campaign.get("start_payload"), dict) else {}
            try:
                state = self.repository.get_campaign(str(campaign.get("campaign_id")), user_id)
            except KeyError:
                continue

            strategy = state.get("strategy") if isinstance(state.get("strategy"), dict) else {}
            content = state.get("content") if isinstance(state.get("content"), dict) else {}
            asset_cards = content.get("asset_cards") if isinstance(content.get("asset_cards"), list) else []

            text_cards.append(
                {
                    "campaign_id": campaign.get("campaign_id"),
                    "brand_name": payload.get("brand_name"),
                    "title": strategy.get("core_message") or payload.get("brand_description") or "Campaign Brief",
                    "goal": payload.get("campaign_goal"),
                    "markets": payload.get("target_markets", []),
                    "asset_card_count": len(asset_cards),
                    "created_at": campaign.get("created_at"),
                }
            )

        return {
            "images": images,
            "texts": text_cards,
            "campaigns": campaigns,
        }

    def save_reference_images(
        self,
        *,
        user_id: str,
        campaign_id: str,
        query: str,
        images: list[dict[str, Any]],
    ) -> int:
        _ = self.repository.get_campaign(campaign_id, user_id)
        existing = self.repository.get_generated_images_for_campaign(user_id, campaign_id)
        existing_urls = {
            str(row.get("image_url") or "").strip()
            for row in existing
            if isinstance(row, dict) and str(row.get("image_url") or "").strip()
        }

        saved = 0
        for item in images:
            if not isinstance(item, dict):
                continue
            image_url = str(item.get("image_url") or "").strip()
            if not image_url or image_url in existing_urls:
                continue
            title = str(item.get("description") or "SERP reference image").strip() or "SERP reference image"
            provider = str(item.get("source") or "google_images").strip() or "google_images"

            self.repository.save_generated_image(
                user_id=user_id,
                campaign_id=campaign_id,
                node_name="R01_GoogleReferences",
                source_type=f"serp-reference:{query}",
                asset_type="reference_image",
                prompt=title,
                image_url=image_url,
                provider=provider,
                model="serpapi-google-images",
                status="ok",
                attempted_providers=[],
                error=None,
            )
            existing_urls.add(image_url)
            saved += 1

        return saved

    async def run_vadoo_brand_video(
        self,
        *,
        user_id: str,
        campaign_id: str,
        brand_name: str,
        duration: str = "5",
        aspect_ratio: str = "1:1",
    ) -> Dict[str, Any]:
        state = self.repository.get_campaign(campaign_id, user_id)
        brand_profile = self.repository.get_brand_identity(user_id, brand_name)
        if not brand_profile:
            payload = state.get("start_payload", {})
            fallback_name = str(payload.get("brand_name") or "").strip()
            if fallback_name.lower() == brand_name.strip().lower() and isinstance(state.get("brand_dna"), dict):
                brand_profile = {"profile": state.get("brand_dna")}
        profile = brand_profile.get("profile") if isinstance(brand_profile, dict) else {}
        if not isinstance(profile, dict):
            profile = {}

        groq_prompt = (
            "Return ONLY valid JSON with schema: "
            "{\"prompt\":\"string\",\"negative_prompt\":\"string\",\"style_tags\":[\"string\"]}. "
            "Write a super-detailed 5-second cinematic video prompt for Vadoo AI based on this brand identity:\n"
            f"{profile}\n"
            f"Market context:\n{state.get('locale_profiles', [])}\n"
            f"Campaign strategy:\n{state.get('strategy', {})}\n"
            "Need high-end art direction, camera movement, subject framing, lighting, texture, and CTA moment."
        )
        groq_result = await call_groq(
            prompt=groq_prompt,
            model="llama-3.3-70b-versatile",
            temperature=0.25,
            max_tokens=700,
        )
        parsed = extract_json_object(str(groq_result.get("text") or ""))
        if isinstance(parsed, dict):
            video_prompt = str(parsed.get("prompt") or "").strip()
            negative_prompt = str(parsed.get("negative_prompt") or "").strip()
        else:
            video_prompt = ""
            negative_prompt = ""
        if not video_prompt:
            video_prompt = (
                f"Cinematic 5-second brand reveal for {brand_name}, premium dark editorial palette, "
                "hero product + logo lockup, smooth dolly-in, soft volumetric light, high contrast highlights, "
                "clean CTA end frame, photoreal quality."
            )

        mapped_duration = "30-60" if duration.strip() in {"", "5", "10", "15"} else duration
        vadoo_result = await vadoo_text_to_video(
            prompt=video_prompt,
            duration=mapped_duration,
            aspect_ratio=aspect_ratio,
        )

        video_url = str(vadoo_result.get("video_url") or "").strip()
        watermark_url = str(vadoo_result.get("watermark_url") or "").strip()
        status = "succeed" if vadoo_result.get("ok") and video_url else "failed"

        balance_trace = await vadoo_get_my_balance()

        self.repository.save_generated_image(
            user_id=user_id,
            campaign_id=campaign_id,
            node_name="P04_VadooVideo",
            source_type=f"brand-video:{brand_name}",
            asset_type="video",
            prompt=video_prompt,
            image_url=video_url or watermark_url or None,
            provider="vadooai",
            model="vadoo-ai-story",
            width=None,
            height=None,
            status=status,
            attempted_providers=[{"provider": "vadooai", "error": str(vadoo_result.get("error") or "")}] if not vadoo_result.get("ok") else [],
            error=str(vadoo_result.get("error") or "") if not vadoo_result.get("ok") else None,
        )

        return {
            "campaign_id": campaign_id,
            "brand_name": brand_name,
            "prompt": video_prompt,
            "video_url": video_url or None,
            "watermark_url": watermark_url or None,
            "model": "vadoo-ai-story",
            "status": status,
            "task_id": vadoo_result.get("task_id"),
            "trace": {
                "groq": {
                    "model": groq_result.get("model"),
                    "ok": groq_result.get("ok"),
                    "error": groq_result.get("error"),
                },
                "vadoo": vadoo_result,
                "balance": balance_trace,
            },
        }

    async def run_kling_brand_video(
        self,
        *,
        user_id: str,
        campaign_id: str,
        brand_name: str,
        duration: str = "5",
        aspect_ratio: str = "1:1",
    ) -> Dict[str, Any]:
        # Backward-compatible wrapper kept while frontend/API route names transition.
        return await self.run_vadoo_brand_video(
            user_id=user_id,
            campaign_id=campaign_id,
            brand_name=brand_name,
            duration=duration,
            aspect_ratio=aspect_ratio,
        )

    async def ingest_brand_gallery_images(
        self,
        *,
        user_id: str,
        campaign_id: str,
        brand_name: str,
        limit: int = 10,
    ) -> Dict[str, Any]:
        # Validate campaign ownership first.
        _ = self.repository.get_campaign(campaign_id, user_id)

        queries = [
            f"{brand_name} official website",
            f"{brand_name} brand campaign",
            f"{brand_name} instagram",
        ]
        search_results = await asyncio.gather(*[firecrawl_search(query, limit=4) for query in queries])
        candidate_urls: list[str] = []
        for result in search_results:
            rows = result.get("results") if isinstance(result, dict) else []
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                url = str(row.get("url") or "").strip()
                if url and url not in candidate_urls:
                    candidate_urls.append(url)
                if len(candidate_urls) >= 5:
                    break
            if len(candidate_urls) >= 5:
                break

        extraction_jobs = await asyncio.gather(
            *[extract_pics_extract_images(url, max_images=max(3, limit)) for url in candidate_urls[:3]]
        )
        collected: list[str] = []
        for job in extraction_jobs:
            images = job.get("images") if isinstance(job, dict) else []
            if not isinstance(images, list):
                continue
            for image_url in images:
                if isinstance(image_url, str) and image_url.startswith(("http://", "https://")) and image_url not in collected:
                    collected.append(image_url)
                if len(collected) >= max(1, limit):
                    break
            if len(collected) >= max(1, limit):
                break

        saved = 0
        for image_url in collected[: max(1, limit)]:
            self.repository.save_generated_image(
                user_id=user_id,
                campaign_id=campaign_id,
                node_name="A00_BrandImageIngest",
                source_type=f"brand-search:{brand_name}",
                asset_type="web_reference",
                prompt=f"{brand_name} web image ingest",
                image_url=image_url,
                provider="extract.pics",
                model="extract-v3.3",
                status="ok",
                attempted_providers=[],
                error=None,
            )
            saved += 1

        return {
            "campaign_id": campaign_id,
            "brand_name": brand_name,
            "saved_images": saved,
            "searched_urls": candidate_urls,
        }

    def schedule_background_run(self, campaign_id: str) -> asyncio.Task[CampaignContext]:
        return asyncio.create_task(self.run_campaign(campaign_id))

    async def _run_parallel_fanout(self, state: CampaignContext) -> CampaignContext:
        pending = [
            node_name
            for node_name in ["A02_MarketIntel", "A08_KeywordGraph", "A10_Competitors"]
            if node_name not in state.get("completed_nodes", [])
        ]
        updates = await asyncio.gather(*[self._resume_nodes[node_name](state) for node_name in pending])
        merged_state = state
        for update in updates:
            merged_state = merge_state(merged_state, update)
        return merged_state

    def _next_node(self, state: CampaignContext) -> str | None:
        completed = set(state.get("completed_nodes", []))
        if "A01_BrandDNA" not in completed:
            return "A01_BrandDNA"
        if not {"A02_MarketIntel", "A08_KeywordGraph", "A10_Competitors"}.issubset(completed):
            return "PARALLEL_FANOUT"
        if "A03_Audience" not in completed:
            return "A03_Audience"
        if "A04_Localisation" not in completed:
            return "A04_Localisation"
        if "A05_Strategy" not in completed:
            return "A05_Strategy"
        if "A06_Content" not in completed:
            return "A06_Content"
        if "A11_CreativeAgent" not in completed:
            return "A11_CreativeAgent"
        if "A07_Critic" not in completed:
            return "A07_Critic"
        if state.get("current_node") == "A07_Critic" and critic_router(state) == "A06_Content":
            return "A06_Content"
        if state.get("current_node") == "A06_Content" and state.get("critic_eval", {}).get("score", 0) < 60:
            return "A07_Critic"
        if "A09_Scheduler" not in completed:
            return "A09_Scheduler"
        return None
