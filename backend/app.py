from __future__ import annotations

import ipaddress
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from backend.auth import AuthUser, get_current_user
from backend.intelligence import (
    build_inline_assets,
    call_groq,
    extract_json_object,
    fetch_website_context,
    generate_image_asset,
    serpapi_image_search,
)
from backend.models import (
    BrandIdentityLookupResponse,
    BrandIdentityPatchRequest,
    CampaignHistoryResponse,
    CampaignLogsResponse,
    GalleryBrandIngestRequest,
    GalleryBrandIngestResponse,
    ReferenceImageSearchRequest,
    ReferenceImageSearchResponse,
    VadooVideoRequest,
    VadooVideoResponse,
    MiniAgentRunRequest,
    MiniAgentRunResponse,
    CampaignStartRequest,
    CampaignStartResponse,
    CampaignStatusResponse,
    DeterministicScheduleRequest,
    DeterministicScheduleResponse,
    SchedulerGenerateRequest,
    SchedulerGenerateResponse,
    UniPileBundleRequest,
    UniPileBundleResponse,
)
from backend.unipile import UniPileClient, build_communication_bundle
from backend.scheduler import generate_schedule
from backend.service import CampaignService


def _load_local_env_file() -> None:
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    force_override_keys = {
        "OPENPOMELLI_DISABLE_AUTH",
        "CLERK_ISSUER",
        "CLERK_JWKS_URL",
        "CLERK_AUDIENCE",
    }
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        cleaned = value.strip().strip("'").strip('"')
        if key in force_override_keys:
            os.environ[key] = cleaned
        else:
            os.environ.setdefault(key, cleaned)


_load_local_env_file()

DB_PATH = os.getenv("OPEN_POMELLI_DB_PATH", "open_pomelli_v2.db")

_BEST_TIMES: dict[str, list[int]] = {
    "instagram": [9, 12, 18, 21],
    "youtube": [12, 15, 20],
    "twitter": [8, 13, 17],
}

_BEST_DAYS: dict[str, list[int]] = {
    "instagram": [1, 3, 5],
    "youtube": [2, 4, 6],
    "twitter": [1, 2, 3, 4, 5],
}

_PLATFORM_WEIGHT: dict[str, float] = {
    "instagram": 1.0,
    "youtube": 0.9,
    "twitter": 0.8,
}

_CONTENT_DISTRIBUTION: dict[str, list[str]] = {
    "instagram": ["post", "reel"],
    "youtube": ["video"],
    "twitter": ["post"],
}

_CONTENT_WEIGHT: dict[str, float] = {
    "post": 0.8,
    "reel": 1.0,
    "video": 0.9,
}


def _to_time_score(platform: str, hour: int) -> float:
    return 1.0 if hour in _BEST_TIMES.get(platform, []) else 0.5


def _to_day_score(platform: str, js_day: int) -> float:
    return 1.0 if js_day in _BEST_DAYS.get(platform, []) else 0.6


def _build_deterministic_schedule(request: DeterministicScheduleRequest) -> list[dict]:
    try:
        start = datetime.strptime(request.start_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="start_date must be in YYYY-MM-DD format") from exc

    rows: list[dict] = []
    filtered_content = [item for item in request.content_types if item in {"post", "reel", "video"}]

    for offset in range(request.days):
        current = start + timedelta(days=offset)
        date_str = current.strftime("%Y-%m-%d")
        js_day = (current.weekday() + 1) % 7
        market = request.markets[offset % len(request.markets)] if request.markets else "Global"

        day_candidates: list[dict] = []
        for platform in request.platforms:
            times = _BEST_TIMES.get(platform, [9, 18])
            default_content = _CONTENT_DISTRIBUTION.get(platform, ["post"])
            available_content = [item for item in default_content if not filtered_content or item in filtered_content]
            content_pool = available_content if available_content else default_content

            for idx, hour in enumerate(times):
                content_type = content_pool[idx % len(content_pool)]
                time_score = _to_time_score(platform, hour)
                day_score = _to_day_score(platform, js_day)
                platform_score = _PLATFORM_WEIGHT.get(platform, 0.7)
                content_score = _CONTENT_WEIGHT.get(content_type, 0.7)
                score = (
                    time_score * 0.4
                    + day_score * 0.3
                    + platform_score * 0.2
                    + content_score * 0.1
                )

                day_candidates.append(
                    {
                        "date": date_str,
                        "market": market,
                        "platform": platform,
                        "time": f"{hour:02d}:00",
                        "content_type": content_type,
                        "score": round(score, 3),
                        "score_breakdown": {
                            "timeScore": time_score,
                            "dayScore": day_score,
                            "platformScore": platform_score,
                            "contentScore": content_score,
                        },
                        "reason": (
                            f"Selected {platform} {content_type} at {hour:02d}:00 for {market} "
                            "using deterministic best-day/best-time scoring."
                        ),
                    }
                )

        day_candidates.sort(key=lambda item: float(item["score"]), reverse=True)
        rows.extend(day_candidates[: request.max_slots_per_day])

    rows.sort(key=lambda item: (item["date"], -float(item["score"])))
    return rows


def _configure_langsmith_tracing() -> None:
    key = (os.getenv("LANGSMITH_API_KEY") or "").strip()
    if not key:
        try:
            from api_secrets import LANGSMITH_API_KEY  # type: ignore

            if isinstance(LANGSMITH_API_KEY, str) and LANGSMITH_API_KEY.strip():
                key = LANGSMITH_API_KEY.strip()
        except Exception:
            key = ""

    if not key:
        return

    os.environ["LANGSMITH_API_KEY"] = key
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", "open-pomelli")


_configure_langsmith_tracing()

app = FastAPI(title="Open Pomelli Backend", version="0.1.0")
service = CampaignService(DB_PATH)

app.add_middleware(
    CORSMiddleware,
    # Allow local frontend dev servers regardless of the Vite port in use.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _is_safe_external_asset_url(raw_url: str) -> bool:
    try:
        parsed = urlparse(raw_url)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    except ValueError:
        pass
    return True


def _mini_agent_instruction(agent_type: str) -> str:
    if agent_type == "hook-writer":
        return (
            "Generate 6 headline hooks with clear emotional angle, one-line rationale per hook, and one CTA variant each. "
            "Avoid generic language and make hooks specific to available context."
        )
    if agent_type == "seo-analyzer":
        return (
            "Produce a practical SEO brief: primary intent, 12 keyword cluster terms, 4 content angles, and metadata draft. "
            "Use website context heavily when available."
        )
    if agent_type == "image-prompter":
        return (
            "Generate production-ready visual prompts for posters/social creatives. Include 4 variations with framing, lighting, "
            "typographic direction, palette notes, and negative prompt guidance."
        )
    if agent_type == "competitor-roaster":
        return (
            "Create a competitor teardown: likely category patterns, stale messaging tropes, differentiation wedges, "
            "and 5 contrarian positioning moves."
        )
    if agent_type == "instagram-generator":
        return (
            "Create an Instagram message generator output with 5 caption variants, hook-first first line, CTA, "
            "emoji-light style, and hashtag clusters tuned to market + audience."
        )
    if agent_type == "linkedin-generator":
        return (
            "Create a LinkedIn post generator output with 4 professional post variants, a concise insight-led caption for each, "
            "and a credibility-first CTA for B2B audiences."
        )
    if agent_type == "email-drafter":
        return (
            "Create professional client-ready email drafts: subject lines, opening, body, CTA, and sign-off. "
            "Tone must be polished, specific, and outcome-oriented."
        )
    return "Respond with a focused analysis based on the user input and provided context."


def _normalize_mini_agent_type(agent_type: str) -> str:
    raw = (agent_type or "").strip().lower().replace("_", "-")
    aliases = {
        "hook writer": "hook-writer",
        "hooks": "hook-writer",
        "seo analyzer": "seo-analyzer",
        "seo": "seo-analyzer",
        "image prompter": "image-prompter",
        "image-prompt": "image-prompter",
        "competitor roaster": "competitor-roaster",
        "competitor": "competitor-roaster",
        "instagram generator": "instagram-generator",
        "instagram": "instagram-generator",
        "linkedin generator": "linkedin-generator",
        "linkedin": "linkedin-generator",
        "email drafter": "email-drafter",
        "email": "email-drafter",
    }
    normalized = aliases.get(raw, raw)
    allowed = {
        "hook-writer",
        "seo-analyzer",
        "image-prompter",
        "competitor-roaster",
        "instagram-generator",
        "linkedin-generator",
        "email-drafter",
    }
    return normalized if normalized in allowed else "hook-writer"


def _mini_agent_structured_schema(agent_type: str) -> str:
    if agent_type == "hook-writer":
        return (
            '{"title":"string","audience_angle":"string","hooks":[{"headline":"string","rationale":"string","cta":"string"}],'
            '"closing_recommendations":["string"]}'
        )
    if agent_type == "seo-analyzer":
        return (
            '{"title":"string","primary_intent":"string","keyword_clusters":["string"],"content_angles":["string"],'
            '"metadata":{"title":"string","description":"string"},"technical_notes":["string"]}'
        )
    if agent_type == "image-prompter":
        return (
            '{"title":"string","campaign_frame":"string","prompts":[{"title":"string","prompt":"string",'
            '"composition":"string","lighting":"string","typography":"string","palette":"string","negative_prompt":"string"}],'
            '"generation_notes":["string"]}'
        )
    if agent_type == "instagram-generator":
        return (
            '{"title":"string","positioning":"string","captions":[{"variant":"string","caption":"string","cta":"string","hashtags":["string"]}],'
            '"posting_notes":["string"]}'
        )
    if agent_type == "linkedin-generator":
        return (
            '{"title":"string","thought_leadership_angle":"string","posts":[{"variant":"string","post":"string","caption":"string","cta":"string","hashtags":["string"]}],'
            '"posting_notes":["string"]}'
        )
    if agent_type == "email-drafter":
        return (
            '{"title":"string","audience":"string","emails":[{"variant":"string","subject":"string","preview":"string","body":"string","cta":"string","signoff":"string"}],'
            '"send_notes":["string"]}'
        )
    return (
        '{"title":"string","summary":"string","stale_patterns":["string"],"differentiation_wedges":["string"],'
        '"recommended_moves":["string"]}'
    )


def _structured_output_to_markdown(agent_type: str, payload: dict) -> str:
    title = str(payload.get("title") or "Agent Output").strip() or "Agent Output"
    lines = [f"## {title}"]

    if agent_type == "hook-writer":
        angle = str(payload.get("audience_angle") or "").strip()
        hooks = payload.get("hooks") if isinstance(payload.get("hooks"), list) else []
        recommendations = payload.get("closing_recommendations") if isinstance(payload.get("closing_recommendations"), list) else []
        if angle:
            lines.extend(["", "### Audience Angle", f"- {angle}"])
        if hooks:
            lines.append("")
            lines.append("### Hooks")
            for index, hook in enumerate(hooks, start=1):
                if not isinstance(hook, dict):
                    continue
                headline = str(hook.get("headline") or "").strip()
                rationale = str(hook.get("rationale") or "").strip()
                cta = str(hook.get("cta") or "").strip()
                if headline:
                    lines.append(f"- Hook {index}: {headline}")
                if rationale:
                    lines.append(f"- Rationale: {rationale}")
                if cta:
                    lines.append(f"- CTA: {cta}")
                lines.append("")
        if recommendations:
            lines.extend(["", "### Recommendations"])
            for recommendation in recommendations:
                if isinstance(recommendation, str) and recommendation.strip():
                    lines.append(f"- {recommendation.strip()}")
        return "\n".join(line for line in lines if line is not None).strip()

    if agent_type == "seo-analyzer":
        intent = str(payload.get("primary_intent") or "").strip()
        clusters = payload.get("keyword_clusters") if isinstance(payload.get("keyword_clusters"), list) else []
        angles = payload.get("content_angles") if isinstance(payload.get("content_angles"), list) else []
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        notes = payload.get("technical_notes") if isinstance(payload.get("technical_notes"), list) else []
        if intent:
            lines.extend(["", "### Primary Intent", f"- {intent}"])
        if clusters:
            lines.extend(["", "### Keyword Clusters"])
            for cluster in clusters:
                if isinstance(cluster, str) and cluster.strip():
                    lines.append(f"- {cluster.strip()}")
        if angles:
            lines.extend(["", "### Content Angles"])
            for angle in angles:
                if isinstance(angle, str) and angle.strip():
                    lines.append(f"- {angle.strip()}")
        meta_title = str(metadata.get("title") or "").strip()
        meta_description = str(metadata.get("description") or "").strip()
        if meta_title or meta_description:
            lines.extend(["", "### Metadata Draft"])
            if meta_title:
                lines.append(f"- Title: {meta_title}")
            if meta_description:
                lines.append(f"- Description: {meta_description}")
        if notes:
            lines.extend(["", "### Technical Notes"])
            for note in notes:
                if isinstance(note, str) and note.strip():
                    lines.append(f"- {note.strip()}")
        return "\n".join(lines).strip()

    if agent_type == "image-prompter":
        campaign_frame = str(payload.get("campaign_frame") or "").strip()
        prompts = payload.get("prompts") if isinstance(payload.get("prompts"), list) else []
        generation_notes = payload.get("generation_notes") if isinstance(payload.get("generation_notes"), list) else []
        if campaign_frame:
            lines.extend(["", "### Campaign Frame", f"- {campaign_frame}"])
        if prompts:
            lines.extend(["", "### Prompt Blocks"])
            for index, prompt in enumerate(prompts, start=1):
                if not isinstance(prompt, dict):
                    continue
                block_title = str(prompt.get("title") or f"Prompt {index}").strip()
                block_prompt = str(prompt.get("prompt") or "").strip()
                composition = str(prompt.get("composition") or "").strip()
                lighting = str(prompt.get("lighting") or "").strip()
                typography = str(prompt.get("typography") or "").strip()
                palette = str(prompt.get("palette") or "").strip()
                negative_prompt = str(prompt.get("negative_prompt") or "").strip()
                lines.append(f"- {block_title}")
                if block_prompt:
                    lines.append(f"- Prompt: {block_prompt}")
                if composition:
                    lines.append(f"- Composition: {composition}")
                if lighting:
                    lines.append(f"- Lighting: {lighting}")
                if typography:
                    lines.append(f"- Typography: {typography}")
                if palette:
                    lines.append(f"- Palette: {palette}")
                if negative_prompt:
                    lines.append(f"- Negative Prompt: {negative_prompt}")
                lines.append("")
        if generation_notes:
            lines.extend(["", "### Generation Notes"])
            for note in generation_notes:
                if isinstance(note, str) and note.strip():
                    lines.append(f"- {note.strip()}")
        return "\n".join(lines).strip()

    if agent_type == "instagram-generator":
        positioning = str(payload.get("positioning") or "").strip()
        captions = payload.get("captions") if isinstance(payload.get("captions"), list) else []
        notes = payload.get("posting_notes") if isinstance(payload.get("posting_notes"), list) else []
        if positioning:
            lines.extend(["", "### Positioning", f"- {positioning}"])
        if captions:
            lines.extend(["", "### Instagram Captions"])
            for row in captions:
                if not isinstance(row, dict):
                    continue
                variant = str(row.get("variant") or "Variant").strip()
                caption = str(row.get("caption") or "").strip()
                cta = str(row.get("cta") or "").strip()
                tags = row.get("hashtags") if isinstance(row.get("hashtags"), list) else []
                lines.append(f"- {variant}")
                if caption:
                    lines.append(f"- Caption: {caption}")
                if cta:
                    lines.append(f"- CTA: {cta}")
                if tags:
                    clean_tags = [f"#{str(tag).strip().lstrip('#')}" for tag in tags if str(tag).strip()]
                    if clean_tags:
                        lines.append(f"- Hashtags: {' '.join(clean_tags)}")
                lines.append("")
        if notes:
            lines.extend(["", "### Posting Notes"])
            for note in notes:
                if isinstance(note, str) and note.strip():
                    lines.append(f"- {note.strip()}")
        return "\n".join(lines).strip()

    if agent_type == "linkedin-generator":
        angle = str(payload.get("thought_leadership_angle") or "").strip()
        posts = payload.get("posts") if isinstance(payload.get("posts"), list) else []
        notes = payload.get("posting_notes") if isinstance(payload.get("posting_notes"), list) else []
        if angle:
            lines.extend(["", "### Thought Leadership Angle", f"- {angle}"])
        if posts:
            lines.extend(["", "### LinkedIn Posts + Captions"])
            for row in posts:
                if not isinstance(row, dict):
                    continue
                variant = str(row.get("variant") or "Variant").strip()
                post = str(row.get("post") or "").strip()
                caption = str(row.get("caption") or "").strip()
                cta = str(row.get("cta") or "").strip()
                tags = row.get("hashtags") if isinstance(row.get("hashtags"), list) else []
                lines.append(f"- {variant}")
                if post:
                    lines.append(f"- Post: {post}")
                if caption:
                    lines.append(f"- Caption: {caption}")
                if cta:
                    lines.append(f"- CTA: {cta}")
                if tags:
                    clean_tags = [f"#{str(tag).strip().lstrip('#')}" for tag in tags if str(tag).strip()]
                    if clean_tags:
                        lines.append(f"- Hashtags: {' '.join(clean_tags)}")
                lines.append("")
        if notes:
            lines.extend(["", "### Posting Notes"])
            for note in notes:
                if isinstance(note, str) and note.strip():
                    lines.append(f"- {note.strip()}")
        return "\n".join(lines).strip()

    if agent_type == "email-drafter":
        audience = str(payload.get("audience") or "").strip()
        emails = payload.get("emails") if isinstance(payload.get("emails"), list) else []
        notes = payload.get("send_notes") if isinstance(payload.get("send_notes"), list) else []
        if audience:
            lines.extend(["", "### Audience", f"- {audience}"])
        if emails:
            lines.extend(["", "### Professional Email Drafts"])
            for row in emails:
                if not isinstance(row, dict):
                    continue
                variant = str(row.get("variant") or "Variant").strip()
                subject = str(row.get("subject") or "").strip()
                preview = str(row.get("preview") or "").strip()
                body = str(row.get("body") or "").strip()
                cta = str(row.get("cta") or "").strip()
                signoff = str(row.get("signoff") or "").strip()
                lines.append(f"- {variant}")
                if subject:
                    lines.append(f"- Subject: {subject}")
                if preview:
                    lines.append(f"- Preview: {preview}")
                if body:
                    lines.append(f"- Body: {body}")
                if cta:
                    lines.append(f"- CTA: {cta}")
                if signoff:
                    lines.append(f"- Signoff: {signoff}")
                lines.append("")
        if notes:
            lines.extend(["", "### Send Notes"])
            for note in notes:
                if isinstance(note, str) and note.strip():
                    lines.append(f"- {note.strip()}")
        return "\n".join(lines).strip()

    summary = str(payload.get("summary") or "").strip()
    stale = payload.get("stale_patterns") if isinstance(payload.get("stale_patterns"), list) else []
    wedges = payload.get("differentiation_wedges") if isinstance(payload.get("differentiation_wedges"), list) else []
    moves = payload.get("recommended_moves") if isinstance(payload.get("recommended_moves"), list) else []
    if summary:
        lines.extend(["", "### Summary", f"- {summary}"])
    if stale:
        lines.extend(["", "### Stale Patterns"])
        for item in stale:
            if isinstance(item, str) and item.strip():
                lines.append(f"- {item.strip()}")
    if wedges:
        lines.extend(["", "### Differentiation Wedges"])
        for item in wedges:
            if isinstance(item, str) and item.strip():
                lines.append(f"- {item.strip()}")
    if moves:
        lines.extend(["", "### Recommended Moves"])
        for item in moves:
            if isinstance(item, str) and item.strip():
                lines.append(f"- {item.strip()}")
    return "\n".join(lines).strip()


async def _generate_image_prompter_previews(prompts_payload: list, model_overrides: dict) -> list[dict]:
    previews: list[dict] = []
    for index, item in enumerate(prompts_payload[:2], start=1):
        if not isinstance(item, dict):
            continue
        prompt_text = str(item.get("prompt") or "").strip()
        title = str(item.get("title") or f"Preview {index}").strip()
        if not prompt_text:
            continue
        result = await generate_image_asset(
            prompt=prompt_text,
            width=1024,
            height=1024,
            model_overrides=model_overrides,
        )
        previews.append(
            {
                "title": title,
                "prompt": prompt_text,
                "image_url": result.get("image_url", ""),
                "provider": result.get("provider", "unknown"),
                "model": result.get("model", "unknown"),
                "status": result.get("status", "error"),
                "error": result.get("error"),
            }
        )
    return previews


def _mini_agent_fallback_output(
    *,
    agent_type: str,
    user_input: str,
    website_context: dict,
    asset_summary: dict,
    error: str,
) -> str:
    title = str(website_context.get("title") or "").strip()
    headings = website_context.get("headings") or []
    heading_sample = [str(item).strip() for item in headings[:4] if str(item).strip()]
    excerpt = str(website_context.get("excerpt") or "").strip()
    excerpt_sample = excerpt[:220].replace("\n", " ")

    base_lines = [
        "Model call unavailable, using evidence-only fallback from scraped context.",
        f"Failure reason: {error}",
        f"Website title: {title or 'n/a'}",
        f"Heading sample: {', '.join(heading_sample) if heading_sample else 'n/a'}",
        f"Assets used for context: {asset_summary.get('used_asset_count', 0)}",
    ]

    if agent_type == "hook-writer":
        hooks = [
            f"{title or 'Your brand'}, but with proof-first positioning.",
            f"Stop vague promises. Start with measurable outcomes from {website_context.get('domain', 'your market')}.",
            f"{user_input[:90].strip()} - now anchored to what your site already signals.",
        ]
        return "\n".join(base_lines + ["", "Fallback Hooks:"] + [f"- {hook}" for hook in hooks])

    if agent_type == "seo-analyzer":
        terms = []
        for segment in ([title] + heading_sample + [excerpt_sample]):
            for token in segment.split():
                cleaned = token.strip(" ,.!?:;()[]{}\"'").lower()
                if len(cleaned) >= 5 and cleaned.isalpha() and cleaned not in terms:
                    terms.append(cleaned)
                if len(terms) >= 12:
                    break
            if len(terms) >= 12:
                break
        return "\n".join(base_lines + ["", "Fallback SEO Terms:"] + [f"- {term}" for term in terms])

    if agent_type == "image-prompter":
        prompt = (
            f"Poster prompt from website evidence: {title or 'Brand headline'}, "
            f"reference headings {', '.join(heading_sample[:2]) or 'n/a'}, "
            "structured typography, campaign-ready composition, premium lighting."
        )
        return "\n".join(base_lines + ["", "Fallback Visual Prompt:", prompt])

    if agent_type == "instagram-generator":
        caption = (
            f"{title or 'Brand update'} built for audience-first Instagram storytelling. "
            "Clear hook, value line, and direct CTA."
        )
        return "\n".join(base_lines + ["", "Fallback Instagram Caption:", f"- {caption}", "- CTA: DM us to get the full campaign plan."])

    if agent_type == "linkedin-generator":
        post = (
            f"{title or 'Strategic update'}: we translated website signals into a more focused market position. "
            "Result: clearer messaging, stronger proof, and actionable campaign direction."
        )
        return "\n".join(base_lines + ["", "Fallback LinkedIn Post:", f"- {post}", "- Caption: Built from live website evidence, not generic templates."])

    if agent_type == "email-drafter":
        email = (
            "Subject: Campaign Draft Ready\n"
            "Hi team,\n\n"
            "We prepared a professional campaign draft based on your current website signals and audience context. "
            "If helpful, we can share the final rollout pack with creatives and schedule next.\n\n"
            "Best regards,\nOpen Pomelli"
        )
        return "\n".join(base_lines + ["", "Fallback Email Draft:", email])

    return "\n".join(base_lines + ["", "Fallback Competitor Insight:", f"Use '{title or user_input[:60]}' as the anchor and counter generic category messaging with specific proof points."])


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/scheduler/deterministic", response_model=DeterministicScheduleResponse)
async def deterministic_scheduler(
    request: DeterministicScheduleRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> DeterministicScheduleResponse:
    _ = current_user
    rows = _build_deterministic_schedule(request)
    return DeterministicScheduleResponse(
        schedule=rows,
        rules=[
            "Score = time(0.4) + day(0.3) + platform(0.2) + content(0.1).",
            "Best time/day values are deterministic and hardcoded per platform.",
            "Each day keeps top max_slots_per_day ranked rows.",
        ],
    )


@app.post("/api/scheduler/generate", response_model=SchedulerGenerateResponse)
async def scheduler_generate(
    request: SchedulerGenerateRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> SchedulerGenerateResponse:
    _ = current_user
    result = generate_schedule(request.model_dump())
    return SchedulerGenerateResponse(**result)


@app.post("/api/communications/unipile/send-bundle", response_model=UniPileBundleResponse)
async def unipile_send_bundle(
    request: UniPileBundleRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> UniPileBundleResponse:
    try:
        campaign = service.get_campaign(request.campaign_id, current_user.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Campaign not found") from exc

    bundle = build_communication_bundle(campaign, promotion_message=request.promotion_message)
    client = UniPileClient()

    fixed_email = (os.getenv("UNIPILE_FIXED_EMAIL") or "atharva.v.deo@gmail.com").strip()
    fixed_whatsapp = (os.getenv("UNIPILE_FIXED_WHATSAPP") or "7249169164").strip()
    fixed_telegram = (os.getenv("UNIPILE_FIXED_TELEGRAM") or "8624909429").strip()

    trace: dict[str, Any] = {}
    email_sent = False
    whatsapp_sent = False
    telegram_sent = False

    if request.channel in {"email", "all"}:
        email_result = await client.send_email(
            to_email=fixed_email,
            subject=bundle["subject"],
            html_body=bundle["html"],
            text_body=bundle["text"],
        )
        trace["email"] = email_result
        email_sent = bool(email_result.get("ok"))

    if request.channel in {"whatsapp", "all"}:
        whatsapp_result = await client.send_whatsapp(
            to_phone=fixed_whatsapp,
            message=bundle["whatsapp"],
        )
        trace["whatsapp"] = whatsapp_result
        whatsapp_sent = bool(whatsapp_result.get("ok"))

    if request.channel in {"telegram", "all"}:
        telegram_result = await client.send_telegram(
            to_phone=fixed_telegram,
            message=bundle["telegram"],
        )
        trace["telegram"] = telegram_result
        telegram_sent = bool(telegram_result.get("ok"))

    return UniPileBundleResponse(
        campaign_id=request.campaign_id,
        email_sent=email_sent,
        whatsapp_sent=whatsapp_sent,
        telegram_sent=telegram_sent,
        linkedin_url=bundle["linkedin_url"],
        telegram_url=bundle["telegram_url"],
        fixed_targets={
            "email": fixed_email,
            "whatsapp": fixed_whatsapp,
            "telegram": fixed_telegram,
        },
        provider_trace=trace,
    )


@app.get("/api/assets/proxy")
async def proxy_external_asset(
    url: str = Query(min_length=8),
) -> Response:
    if not _is_safe_external_asset_url(url):
        raise HTTPException(status_code=400, detail="Unsupported asset URL")

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            upstream = await client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 OpenPomelliAssetProxy/1.0"
                    ),
                    "Referer": "https://openpomelli.local/",
                },
            )
        upstream.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Asset fetch failed: {exc}") from exc

    media_type = str(upstream.headers.get("content-type") or "application/octet-stream").split(";")[0].strip()
    return Response(content=upstream.content, media_type=media_type)


@app.post("/api/campaign/start", response_model=CampaignStartResponse)
async def start_campaign(
    request: CampaignStartRequest,
    background_tasks: BackgroundTasks,
    current_user: AuthUser = Depends(get_current_user),
) -> CampaignStartResponse:
    state = await service.start_campaign(
        request,
        current_user.user_id,
        user_email=current_user.email,
        user_name=current_user.name,
    )
    background_tasks.add_task(service.run_campaign, state["campaign_id"])
    return CampaignStartResponse(campaign_id=state["campaign_id"], status=state["status"])


@app.get("/api/campaign/{campaign_id}")
async def get_campaign(campaign_id: str, current_user: AuthUser = Depends(get_current_user)) -> dict:
    try:
        return service.get_campaign(campaign_id, current_user.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Campaign not found") from exc


@app.get("/api/campaign/{campaign_id}/status", response_model=CampaignStatusResponse)
async def get_campaign_status(campaign_id: str, current_user: AuthUser = Depends(get_current_user)) -> CampaignStatusResponse:
    try:
        return CampaignStatusResponse(**service.get_status(campaign_id, current_user.user_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Campaign not found") from exc


@app.post("/api/campaign/{campaign_id}/critic/rerun", response_model=CampaignStatusResponse)
async def rerun_critic_agent(campaign_id: str, current_user: AuthUser = Depends(get_current_user)) -> CampaignStatusResponse:
    try:
        await service.rerun_critic_agent(campaign_id, current_user.user_id)
        return CampaignStatusResponse(**service.get_status(campaign_id, current_user.user_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Campaign not found") from exc


@app.get("/api/campaign/{campaign_id}/logs", response_model=CampaignLogsResponse)
async def get_campaign_logs(campaign_id: str, current_user: AuthUser = Depends(get_current_user)) -> CampaignLogsResponse:
    try:
        return CampaignLogsResponse(**service.get_logs(campaign_id, current_user.user_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Campaign not found") from exc


@app.get("/api/campaigns/history", response_model=CampaignHistoryResponse)
async def list_campaign_history(
    limit: int | None = Query(default=None, ge=1, le=1000),
    current_user: AuthUser = Depends(get_current_user),
) -> CampaignHistoryResponse:
    return CampaignHistoryResponse(**service.list_campaigns(current_user.user_id, limit))


@app.get("/api/gallery")
async def get_gallery(
    campaign_id: str | None = Query(default=None),
    limit: int = Query(default=300, ge=1, le=1000),
    current_user: AuthUser = Depends(get_current_user),
) -> dict:
    return service.get_gallery(current_user.user_id, campaign_id=campaign_id, limit=limit)


@app.post("/api/gallery/brand-images", response_model=GalleryBrandIngestResponse)
async def ingest_gallery_brand_images(
    request: GalleryBrandIngestRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> GalleryBrandIngestResponse:
    try:
        result = await service.ingest_brand_gallery_images(
            user_id=current_user.user_id,
            campaign_id=request.campaign_id,
            brand_name=request.brand_name,
            limit=request.limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Campaign not found") from exc
    return GalleryBrandIngestResponse(**result)


@app.post("/api/references/google-images", response_model=ReferenceImageSearchResponse)
async def search_google_reference_images(
    request: ReferenceImageSearchRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> ReferenceImageSearchResponse:
    result = await serpapi_image_search(request.query, limit=request.limit, page=request.page)
    saved_images = 0
    campaign_id = str(request.campaign_id or "").strip()
    if request.persist_to_gallery and campaign_id:
        try:
            saved_images = service.save_reference_images(
                user_id=current_user.user_id,
                campaign_id=campaign_id,
                query=str(result.get("query") or request.query),
                images=result.get("images") if isinstance(result.get("images"), list) else [],
            )
        except KeyError:
            saved_images = 0

    return ReferenceImageSearchResponse(
        query=str(result.get("query") or request.query),
        provider=str(result.get("provider") or "serpapi"),
        page=int(result.get("page") or request.page),
        saved_images=saved_images,
        images=result.get("images") if isinstance(result.get("images"), list) else [],
    )


@app.post("/api/mini-agent/vadoo-video", response_model=VadooVideoResponse)
async def run_vadoo_video_agent(
    request: VadooVideoRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> VadooVideoResponse:
    try:
        result = await service.run_vadoo_brand_video(
            user_id=current_user.user_id,
            campaign_id=request.campaign_id,
            brand_name=request.brand_name,
            duration=request.duration,
            aspect_ratio=request.aspect_ratio,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Campaign not found") from exc
    return VadooVideoResponse(**result)


@app.post("/api/mini-agent/kling-video", response_model=VadooVideoResponse)
async def run_kling_video_agent_legacy(
    request: VadooVideoRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> VadooVideoResponse:
    # Legacy route preserved for older frontend clients.
    return await run_vadoo_video_agent(request, current_user)


@app.get("/api/brand/{brand_name}/identity", response_model=BrandIdentityLookupResponse)
async def get_brand_identity(brand_name: str, current_user: AuthUser = Depends(get_current_user)) -> BrandIdentityLookupResponse:
    cached = service.get_brand_identity(current_user.user_id, brand_name)
    if not cached:
        return BrandIdentityLookupResponse(exists=False, brand_name=brand_name)
    return BrandIdentityLookupResponse(
        exists=True,
        brand_name=cached["brand_name"],
        profile=cached["profile"],
        updated_at=cached.get("updated_at"),
        source_campaign_id=cached.get("source_campaign_id"),
    )


@app.put("/api/brand/{brand_name}/identity", response_model=BrandIdentityLookupResponse)
async def patch_brand_identity(
    brand_name: str,
    request: BrandIdentityPatchRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> BrandIdentityLookupResponse:
    updated = service.patch_brand_identity(current_user.user_id, brand_name, request.profile_patch)
    if not updated:
        raise HTTPException(status_code=404, detail="Brand identity not found")
    return BrandIdentityLookupResponse(
        exists=True,
        brand_name=updated["brand_name"],
        profile=updated["profile"],
        updated_at=updated.get("updated_at"),
        source_campaign_id=updated.get("source_campaign_id"),
    )


@app.post("/api/mini-agent/run", response_model=MiniAgentRunResponse)
async def run_mini_agent(request: MiniAgentRunRequest, current_user: AuthUser = Depends(get_current_user)) -> MiniAgentRunResponse:
    normalized_agent_type = _normalize_mini_agent_type(request.agent_type)
    model_overrides = request.model_overrides if isinstance(request.model_overrides, dict) else {}
    website_context = await fetch_website_context(request.website_url)
    inline_assets, asset_summary = build_inline_assets(request.uploaded_assets)

    prompt = (
        "You are running inside Open Pomelli Agent Playground. "
        "Be concrete, avoid boilerplate, and use all available context.\n\n"
        f"Agent mode: {normalized_agent_type}\n"
        f"Instruction: {_mini_agent_instruction(normalized_agent_type)}\n"
        f"User input: {request.input}\n"
        f"Context notes: {request.context_notes or 'None'}\n"
        f"Website context: {website_context}\n"
        f"Asset summary: {asset_summary}\n"
        f"Model overrides: {model_overrides}\n\n"
        "Return ONLY valid JSON and no markdown.\n"
        f"JSON schema: {_mini_agent_structured_schema(normalized_agent_type)}"
    )

    groq_result = await call_groq(
        prompt=prompt,
        model=(str(model_overrides.get("groq_model") or "").strip() or "llama-3.3-70b-versatile"),
        temperature=0.35,
        max_tokens=1400,
    )

    if groq_result.get("ok"):
        raw_text = str(groq_result.get("text", "")).strip()
        structured_payload = extract_json_object(raw_text)
        generated_images: list[dict] = []
        output_text = raw_text or "Model returned an empty response."
        if isinstance(structured_payload, dict):
            output_text = _structured_output_to_markdown(normalized_agent_type, structured_payload)
            if normalized_agent_type == "image-prompter":
                prompts_payload = structured_payload.get("prompts") if isinstance(structured_payload.get("prompts"), list) else []
                generated_images = await _generate_image_prompter_previews(prompts_payload, model_overrides)
                successful_urls = [img.get("image_url") for img in generated_images if isinstance(img.get("image_url"), str) and img.get("image_url")]
                if successful_urls:
                    output_text = "\n\n".join(
                        [
                            output_text,
                            "### Generated Image Previews",
                            *[f"- {url}" for url in successful_urls],
                        ]
                    )

        return MiniAgentRunResponse(
            output=output_text,
            trace={
                "provider": "groq",
                "model": groq_result.get("model"),
                "agent_type": normalized_agent_type,
                "structured": isinstance(structured_payload, dict),
                "website": {
                    "url": website_context.get("url"),
                    "status": website_context.get("status"),
                    "domain": website_context.get("domain"),
                    "status_code": website_context.get("status_code"),
                },
                "attempted_models": groq_result.get("attempted_models", []),
                "assets": {
                    "count": asset_summary.get("asset_count", 0),
                    "used": asset_summary.get("used_asset_count", 0),
                },
                "generated_images": generated_images,
            },
        )

    fallback_output = _mini_agent_fallback_output(
        agent_type=normalized_agent_type,
        user_input=request.input,
        website_context=website_context,
        asset_summary=asset_summary,
        error=str(groq_result.get("error", "unknown error")),
    )
    return MiniAgentRunResponse(
        output=fallback_output,
        trace={
            "provider": "groq",
            "model": groq_result.get("model"),
            "agent_type": normalized_agent_type,
            "error": groq_result.get("error"),
            "fallback_mode": "website-evidence",
            "website": {
                "url": website_context.get("url"),
                "status": website_context.get("status"),
                "domain": website_context.get("domain"),
                "status_code": website_context.get("status_code"),
            },
            "attempted_models": groq_result.get("attempted_models", []),
            "assets": {
                "count": asset_summary.get("asset_count", 0),
                "used": asset_summary.get("used_asset_count", 0),
            },
        },
    )
