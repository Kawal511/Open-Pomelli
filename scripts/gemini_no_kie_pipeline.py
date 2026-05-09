#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.intelligence import call_gemini, extract_json_object, generate_image_asset


def _fallback_prompts(brief: str) -> Dict[str, str]:
    return {
        "image_prompt": (
            "Cinematic premium coffee campaign key visual, rainy city backdrop, warm interior glow, "
            "hero product focus, high-contrast editorial lighting, luxury ad photography style. "
            f"Brand brief: {brief}"
        ),
        "video_prompt": (
            "Slow dolly-in from rainy exterior to warm interior, subtle steam motion from cup, "
            "glass reflections shimmering, end frame with clean CTA lockup."
        ),
        "title": "Crafted For The Rain",
        "cta": "Order The Monsoon Reserve",
    }


async def _build_prompts(brief: str, model: str | None) -> tuple[Dict[str, str], Dict[str, Any]]:
    prompt = (
        "You are a senior ad creative director. "
        "Return ONLY valid JSON with keys: image_prompt, video_prompt, title, cta. "
        "Write for a 4-second mobile-first ad. Keep outputs concrete and production ready.\n\n"
        f"Brand brief: {brief}\n"
        "Constraints:\n"
        "- image_prompt: one paragraph, 40-90 words\n"
        "- video_prompt: one paragraph, 40-90 words\n"
        "- title: max 6 words\n"
        "- cta: max 6 words\n"
    )

    result = await call_gemini(
        prompt=prompt,
        model=model,
        temperature=0.4,
        max_output_tokens=700,
        response_mime_type="application/json",
    )

    parsed = extract_json_object(str(result.get("text", ""))) if result.get("ok") else None
    if isinstance(parsed, dict):
        prompts = {
            "image_prompt": str(parsed.get("image_prompt", "")).strip(),
            "video_prompt": str(parsed.get("video_prompt", "")).strip(),
            "title": str(parsed.get("title", "")).strip(),
            "cta": str(parsed.get("cta", "")).strip(),
        }
        if all(prompts.values()):
            return prompts, result

    return _fallback_prompts(brief), result


async def _download_image(url: str, out_path: Path) -> None:
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        out_path.write_bytes(response.content)


def _render_video_from_image(image_path: Path, video_path: Path) -> None:
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "zoompan=z='min(zoom+0.0015,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=96:s=1080x1920,"
        "fade=t=in:st=0:d=0.35,"
        "fade=t=out:st=3.2:d=0.8"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-framerate",
        "24",
        "-i",
        str(image_path),
        "-vf",
        vf,
        "-t",
        "4",
        "-r",
        "24",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(video_path),
    ]

    subprocess.run(cmd, check=True, capture_output=True, text=True)


async def run_pipeline(brief: str, output_dir: Path, gemini_model: str | None) -> Dict[str, Any]:
    # Hard disable any KIE-backed image provider in this pipeline run.
    os.environ["OPENPOMELLI_DISABLE_KIE"] = "true"

    prompts, gemini_trace = await _build_prompts(brief, gemini_model)

    image_result = await generate_image_asset(
        prompt=prompts["image_prompt"],
        width=1080,
        height=1920,
        model_overrides={
            "image_provider": "pollinations",
            "image_providers": ["pollinations"],
        },
    )

    image_url = str(image_result.get("image_url", "")).strip()
    if not image_url:
        raise RuntimeError(f"Image generation failed without KIE: {image_result}")

    run_id = uuid.uuid4().hex[:10]
    run_dir = output_dir / f"run_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    image_path = run_dir / "keyframe.jpg"
    video_path = run_dir / "ad_clip.mp4"

    await _download_image(image_url, image_path)
    _render_video_from_image(image_path, video_path)

    manifest = {
        "mode": "gemini_no_kie",
        "kie_disabled": True,
        "brief": brief,
        "gemini": {
            "ok": bool(gemini_trace.get("ok")),
            "model": gemini_trace.get("model"),
            "error": gemini_trace.get("error"),
            "attempted_models": gemini_trace.get("attempted_models", []),
        },
        "prompts": prompts,
        "image": {
            "provider": image_result.get("provider"),
            "model": image_result.get("model"),
            "status": image_result.get("status"),
            "source_url": image_url,
            "local_path": str(image_path),
        },
        "video": {
            "engine": "ffmpeg-local",
            "duration_seconds": 4,
            "local_path": str(video_path),
        },
    }

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return manifest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Gemini-first pipeline with KIE disabled.")
    parser.add_argument(
        "--brief",
        default=(
            "Starbucks Reserve monsoon evening launch in Mumbai, premium lifestyle audience, "
            "cinematic luxury tone, strong CTA for in-store visit"
        ),
        help="Campaign brief used to generate prompts.",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/gemini_no_kie",
        help="Directory where outputs are written.",
    )
    parser.add_argument(
        "--gemini-model",
        default="gemini-2.5-flash",
        help="Optional Gemini model override.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = asyncio.run(
        run_pipeline(
            brief=args.brief,
            output_dir=output_dir,
            gemini_model=args.gemini_model,
        )
    )

    print("gemini_model=", manifest["gemini"]["model"])
    print("kie_disabled=", manifest["kie_disabled"])
    print("image_provider=", manifest["image"]["provider"])
    print("image_model=", manifest["image"]["model"])
    print("image_url=", manifest["image"]["source_url"])
    print("image_local=", manifest["image"]["local_path"])
    print("video_local=", manifest["video"]["local_path"])


if __name__ == "__main__":
    main()
