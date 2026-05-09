from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Tuple, cast
from urllib.parse import quote
from urllib.parse import urlparse

import httpx
import jwt
from bs4 import BeautifulSoup

GEMINI_API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-image-preview")

SUPPORTED_ASSET_MIME_PREFIXES = ("image/", "application/pdf")
MAX_INLINE_ASSETS = 3
MAX_BASE64_CHARS = 1_500_000

DEFAULT_FAL_MODEL = os.getenv("FAL_IMAGE_MODEL", "fal-ai/flux/schnell")
DEFAULT_KIE_ENDPOINT = (
    os.getenv("KIE_API_ENDPOINT")
    or os.getenv("KLIE_API_ENDPOINT")
    or "https://api.kie.ai/api/v1/jobs/createTask"
).strip()
DEFAULT_KIE_RECORD_INFO_ENDPOINT = (
    os.getenv("KIE_RECORD_INFO_ENDPOINT")
    or os.getenv("KLIE_RECORD_INFO_ENDPOINT")
    or "https://api.kie.ai/api/v1/jobs/recordInfo"
).strip()

LOGGER = logging.getLogger(__name__)

KIE_BACKED_IMAGE_PROVIDERS = {"kie", "nanobanna", "nanobanna-2"}


def _env_flag(name: str) -> bool:
    value = (os.getenv(name) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _is_kie_disabled() -> bool:
    return _env_flag("OPENPOMELLI_DISABLE_KIE")


def _http_verify_option() -> bool | str:
    """Return TLS verification settings based on explicit env configuration.

    Default is secure verification. Set OPENPOMELLI_CA_BUNDLE to a CA bundle path
    for self-signed/private CAs. OPENPOMELLI_ALLOW_INSECURE_TLS=true is supported
    only as an explicit opt-in for non-production troubleshooting.
    """
    ca_bundle = (os.getenv("OPENPOMELLI_CA_BUNDLE") or "").strip()
    if ca_bundle:
        return ca_bundle

    allow_insecure = (os.getenv("OPENPOMELLI_ALLOW_INSECURE_TLS") or "").strip().lower()
    if allow_insecure in {"1", "true", "yes"}:
        LOGGER.warning("OPENPOMELLI_ALLOW_INSECURE_TLS=true enabled; TLS verification is disabled.")
        return False

    return True


def _safe_error_message(provider: str, exc: Exception | None = None, *, status_code: int | None = None) -> str:
    if status_code is not None:
        return f"{provider} request failed with HTTP {status_code}."
    if exc is not None:
        return f"{provider} request failed ({exc.__class__.__name__})."
    return f"{provider} request failed."


def get_gemini_api_key() -> str | None:
    env_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if env_key:
        return env_key

    try:
        from api_secrets import GEMINI_API_KEY  # type: ignore

        if isinstance(GEMINI_API_KEY, str) and GEMINI_API_KEY.strip():
            return GEMINI_API_KEY.strip()
    except Exception:
        return None

    return None


def get_fal_api_key() -> str | None:
    for env_name in ["FAL_KEY", "FAL_API_KEY"]:
        value = (os.getenv(env_name) or "").strip()
        if value:
            return value
    return None


def get_kie_api_key() -> str | None:
    for env_name in ["KIE_API_KEY", "KIE_KEY", "KLIE_API_KEY", "KLIE_KEY"]:
        value = (os.getenv(env_name) or "").strip()
        if value:
            return value
    try:
        from api_secrets import KIE_API_KEY as API_SECRETS_KIE_API_KEY  # type: ignore

        if isinstance(API_SECRETS_KIE_API_KEY, str) and API_SECRETS_KIE_API_KEY.strip():
            return API_SECRETS_KIE_API_KEY.strip()
    except Exception:
        pass

    try:
        from api_secrets import KLIE_API_KEY as API_SECRETS_KLIE_API_KEY  # type: ignore

        if isinstance(API_SECRETS_KLIE_API_KEY, str) and API_SECRETS_KLIE_API_KEY.strip():
            return API_SECRETS_KLIE_API_KEY.strip()
    except Exception:
        pass

    return None


def get_klie_api_key() -> str | None:
    # Backward-compatible alias for older callers.
    return get_kie_api_key()


def _first_url(value: Any) -> str | None:
    if isinstance(value, str):
        if value.startswith("http://") or value.startswith("https://"):
            return value
        return None
    if isinstance(value, dict):
        for key in ["url", "image_url", "imageUrl", "output_url", "href"]:
            candidate = _first_url(value.get(key))
            if candidate:
                return candidate
        for nested in value.values():
            candidate = _first_url(nested)
            if candidate:
                return candidate
    if isinstance(value, list):
        for item in value:
            candidate = _first_url(item)
            if candidate:
                return candidate
    return None


def _extract_task_id(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ["taskId", "task_id", "recordId", "record_id", "id"]:
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
        data = value.get("data")
        task_id = _extract_task_id(data)
        if task_id:
            return task_id
    return None


async def _poll_kie_task_result(
    *,
    task_id: str,
    api_key: str,
    record_info_endpoint: str,
    timeout_seconds: int = 600,
    poll_interval_seconds: float = 2.5,
) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    start = time.time()

    async with httpx.AsyncClient(timeout=30.0, verify=_http_verify_option()) as client:
        while True:
            response = await client.get(
                record_info_endpoint,
                params={"taskId": task_id},
                headers=headers,
            )

            if response.status_code >= 400:
                return {
                    "ok": False,
                    "error": _safe_error_message("KIE task query", status_code=response.status_code),
                }

            body = response.json()
            if isinstance(body, dict):
                api_code = body.get("code")
                api_msg = str(body.get("msg", "")).strip()
                if isinstance(api_code, int) and api_code != 200:
                    # KIE can return 422 "recordInfo is null" before task is indexed.
                    if api_code == 422 and "recordinfo is null" in api_msg.lower():
                        if time.time() - start > timeout_seconds:
                            return {"ok": False, "error": "KIE task polling timed out."}
                        await asyncio.sleep(poll_interval_seconds)
                        continue
                    return {
                        "ok": False,
                        "error": api_msg or f"KIE task query failed with code {api_code}.",
                    }

            data = body.get("data") if isinstance(body, dict) else None
            if not isinstance(data, dict):
                return {"ok": False, "error": "KIE task query returned invalid data payload."}

            state = str(data.get("state", "")).strip().lower()
            if state == "success":
                result_json_raw = data.get("resultJson")
                if isinstance(result_json_raw, str) and result_json_raw.strip():
                    try:
                        result_json_obj = json.loads(result_json_raw)
                    except json.JSONDecodeError:
                        result_json_obj = {"raw": result_json_raw}
                else:
                    result_json_obj = result_json_raw

                url = _first_url(result_json_obj) or _first_url(data)
                if not url:
                    return {"ok": False, "error": "KIE task succeeded but no output URL was returned."}
                return {"ok": True, "image_url": url}

            if state == "fail":
                fail_code = str(data.get("failCode", "")).strip()
                fail_msg = str(data.get("failMsg", "")).strip()
                suffix = f" ({fail_code})" if fail_code else ""
                message = f"KIE task failed{suffix}."
                if fail_msg:
                    message = f"{message} {fail_msg[:180]}"
                return {"ok": False, "error": message}

            if time.time() - start > timeout_seconds:
                return {"ok": False, "error": "KIE task polling timed out."}

            await asyncio.sleep(poll_interval_seconds)


def _pollinations_url(prompt: str, *, width: int, height: int) -> str:
    escaped = quote(prompt)
    return f"https://image.pollinations.ai/prompt/{escaped}?model=flux&width={width}&height={height}&nologo=true"


async def _generate_with_fal(
    *,
    prompt: str,
    width: int,
    height: int,
    model: str,
) -> Dict[str, Any]:
    api_key = get_fal_api_key()
    if not api_key:
        return {"ok": False, "error": "FAL API key not configured."}

    endpoint = f"https://fal.run/{model}"
    payload = {
        "prompt": prompt,
        "image_size": {"width": width, "height": height},
        "num_images": 1,
    }
    headers = {
        "Authorization": f"Key {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=70.0, verify=_http_verify_option()) as client:
        response = await client.post(endpoint, json=payload, headers=headers)
    if response.status_code >= 400:
        return {"ok": False, "error": _safe_error_message("FAL", status_code=response.status_code)}

    body = response.json()

    if isinstance(body, dict):
        api_code = body.get("code")
        api_msg = str(body.get("msg", "")).strip()
        if isinstance(api_code, int) and api_code != 200:
            return {
                "ok": False,
                "error": api_msg or f"FAL request failed with code {api_code}.",
            }

    url = _first_url(body)
    if not url:
        return {"ok": False, "error": "FAL response contained no image URL."}
    return {"ok": True, "image_url": url}


def _extract_gemini_image_url(body: Dict[str, Any]) -> str | None:
    candidates = body.get("candidates")
    if not isinstance(candidates, list):
        return None

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue

        for part in parts:
            if not isinstance(part, dict):
                continue

            inline_data = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline_data, dict):
                encoded = inline_data.get("data")
                if isinstance(encoded, str) and encoded.strip():
                    mime_type = str(inline_data.get("mimeType") or inline_data.get("mime_type") or "image/png").strip()
                    if mime_type.startswith("image/"):
                        return f"data:{mime_type};base64,{encoded}"

            file_data = part.get("fileData") or part.get("file_data")
            if isinstance(file_data, dict):
                uri = file_data.get("fileUri") or file_data.get("uri") or file_data.get("url")
                if isinstance(uri, str) and uri.strip().startswith(("http://", "https://")):
                    return uri.strip()

            text_chunk = part.get("text")
            if isinstance(text_chunk, str):
                url = _first_url(text_chunk)
                if url:
                    return url

    return None


async def _generate_with_gemini_image(
    *,
    prompt: str,
    width: int,
    height: int,
    model: str,
) -> Dict[str, Any]:
    api_key = get_gemini_api_key()
    if not api_key:
        return {"ok": False, "error": "GEMINI_API_KEY not configured."}

    preferred_model = (model or "").strip()
    fallback_models = [
        preferred_model,
        "gemini-2.0-flash-preview-image-generation",
        "gemini-3.1-flash-image-preview",
        "gemini-2.5-flash-image-preview",
        DEFAULT_GEMINI_MODEL,
    ]
    candidate_models = [candidate for candidate in fallback_models if candidate]

    unique_models: List[str] = []
    for candidate in candidate_models:
        if candidate not in unique_models:
            unique_models.append(candidate)

    prompt_with_constraints = (
        f"{prompt}\n\n"
        "Generate a production-ready marketing image output (not text-only). "
        f"Target framing should approximate {width}x{height}."
    )
    payload: Dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt_with_constraints}]}],
        "generationConfig": {
            "temperature": 0.35,
            "maxOutputTokens": 800,
            "responseModalities": ["TEXT", "IMAGE"],
        },
    }

    attempted: List[Dict[str, str]] = []
    for chosen_model in unique_models:
        endpoint = GEMINI_API_ENDPOINT.format(model=chosen_model)
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=40.0, verify=_http_verify_option()) as client:
                    response = await client.post(
                        endpoint,
                        params={"key": api_key},
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )

                if response.status_code in {404, 400}:
                    attempted.append({"model": chosen_model, "error": f"HTTP {response.status_code}"})
                    break

                if response.status_code == 429:
                    attempted.append({"model": chosen_model, "error": f"HTTP 429 attempt {attempt + 1}"})
                    await asyncio.sleep(min(4, attempt + 1))
                    continue

                response.raise_for_status()
                body = response.json()
                image_url = _extract_gemini_image_url(body)
                if image_url:
                    return {
                        "ok": True,
                        "image_url": image_url,
                        "model": chosen_model,
                        "attempted_models": attempted,
                    }

                attempted.append({"model": chosen_model, "error": "No image output in Gemini response."})
                break
            except Exception as exc:
                attempted.append({"model": chosen_model, "error": _safe_error_message("Gemini image", exc)})
                if attempt < 1:
                    await asyncio.sleep(1)
                    continue
                break

    return {
        "ok": False,
        "error": "No Gemini image model returned an image output.",
        "attempted_models": attempted,
    }


async def _generate_with_kie(
    *,
    prompt: str,
    width: int,
    height: int,
    endpoint: str,
    api_key: str,
    model: str,
    model_overrides: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not endpoint:
        return {"ok": False, "error": "KIE_API_ENDPOINT not configured."}
    overrides = model_overrides or {}
    record_info_endpoint = str(
        overrides.get(
            "kie_record_info_endpoint",
            overrides.get("klie_record_info_endpoint", DEFAULT_KIE_RECORD_INFO_ENDPOINT),
        )
    ).strip() or DEFAULT_KIE_RECORD_INFO_ENDPOINT

    overrides = model_overrides or {}
    payload: Dict[str, Any]

    if model in {"nano-banana-2", "google/nano-banana", "google/nano-banana-2"}:
        payload = await _build_nano_banana_task_payload(
            prompt=prompt,
            width=width,
            height=height,
            model_overrides=overrides,
        )
    elif model == "bytedance/seedream-v4-edit":
        seedream_input = await _build_seedream_edit_input(
            base_prompt=prompt,
            width=width,
            height=height,
            model_overrides=overrides,
        )
        payload = {
            "input": json.dumps(seedream_input, separators=(",", ":")),
            "model": model,
        }
    else:
        payload = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "model": model,
        }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=70.0, verify=_http_verify_option()) as client:
        response = await client.post(endpoint, json=payload, headers=headers)

    if response.status_code >= 400:
        return {"ok": False, "error": _safe_error_message("KIE", status_code=response.status_code)}

    body = response.json()
    if isinstance(body, dict):
        api_code = body.get("code")
        api_msg = str(body.get("msg", "")).strip()
        if isinstance(api_code, int) and api_code != 200:
            return {
                "ok": False,
                "error": api_msg or f"KIE request failed with code {api_code}.",
            }

    url = _first_url(body)
    if not url:
        task_id = _extract_task_id(body)
        if task_id:
            return await _poll_kie_task_result(
                task_id=task_id,
                api_key=api_key,
                record_info_endpoint=record_info_endpoint,
            )
        return {"ok": False, "error": "KIE response contained no image URL or taskId."}
    return {"ok": True, "image_url": url}


async def _generate_with_klie(
    *,
    prompt: str,
    width: int,
    height: int,
    endpoint: str,
    api_key: str,
    model: str,
    model_overrides: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    # Backward-compatible alias for older callers.
    return await _generate_with_kie(
        prompt=prompt,
        width=width,
        height=height,
        endpoint=endpoint,
        api_key=api_key,
        model=model,
        model_overrides=model_overrides,
    )


def _map_aspect_ratio(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "auto"
    ratio = width / height
    candidates = [
        ("1:1", 1.0),
        ("2:3", 2 / 3),
        ("3:2", 3 / 2),
        ("3:4", 3 / 4),
        ("4:3", 4 / 3),
        ("4:5", 4 / 5),
        ("5:4", 5 / 4),
        ("9:16", 9 / 16),
        ("16:9", 16 / 9),
        ("21:9", 21 / 9),
    ]
    best = min(candidates, key=lambda item: abs(ratio - item[1]))
    return best[0]


def _collect_reference_image_urls(model_overrides: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    for key in ["seedream_image_urls", "image_urls", "image_input", "kie_image_input", "reference_image_urls"]:
        raw = model_overrides.get(key)
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item.strip() and item.strip() not in candidates:
                    candidates.append(item.strip())
    return candidates[:14]


async def _build_nano_banana_task_payload(
    *,
    prompt: str,
    width: int,
    height: int,
    model_overrides: Dict[str, Any],
) -> Dict[str, Any]:
    structured_prompt = await _structure_image_prompt_with_react(
        base_prompt=prompt,
        model_overrides=model_overrides,
    )
    aspect_ratio = str(model_overrides.get("kie_aspect_ratio", _map_aspect_ratio(width, height))).strip() or "auto"
    resolution = str(model_overrides.get("kie_resolution", "1K")).strip() or "1K"
    output_format = str(model_overrides.get("kie_output_format", "jpg")).strip().lower() or "jpg"
    call_back_url = str(model_overrides.get("kie_callback_url", "")).strip()

    payload: Dict[str, Any] = {
        "model": "nano-banana-2",
        "input": {
            "prompt": structured_prompt,
            "image_input": _collect_reference_image_urls(model_overrides),
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "output_format": output_format,
        },
    }
    if call_back_url:
        payload["callBackUrl"] = call_back_url
    return payload


async def _structure_image_prompt_with_react(*, base_prompt: str, model_overrides: Dict[str, Any]) -> str:
    # Optional LangChain ReAct path. Falls back to direct Groq call if LangChain deps are unavailable.
    react_preferred = bool(model_overrides.get("use_langchain_react", True))
    if react_preferred:
        react_result = await _call_langchain_react_prompt_structurer(base_prompt, model_overrides)
        if react_result.get("ok") and isinstance(react_result.get("text"), str) and react_result.get("text", "").strip():
            return str(react_result.get("text")).strip()

    groq_model = str(model_overrides.get("groq_model", "qwen/qwen3-32b")).strip() or "qwen/qwen3-32b"
    groq_prompt = (
        "Return ONLY valid JSON with this schema: {\"prompt\":\"string\"}. "
        "Rewrite the following image-generation brief into one production-ready prompt for brand poster editing: "
        f"{base_prompt}"
    )
    groq_result = await call_groq(
        prompt=groq_prompt,
        model=groq_model,
        temperature=0.2,
        max_tokens=500,
    )
    if groq_result.get("ok"):
        parsed = extract_json_object(str(groq_result.get("text", "")))
        if isinstance(parsed, dict):
            prompt = str(parsed.get("prompt", "")).strip()
            if prompt:
                return prompt
    return base_prompt


async def _call_langchain_react_prompt_structurer(base_prompt: str, model_overrides: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from langchain.agents import AgentExecutor, create_react_agent  # type: ignore
        from langchain.tools import Tool  # type: ignore
        from langchain_openai import ChatOpenAI  # type: ignore
        from langchain_core.prompts import PromptTemplate  # type: ignore
    except Exception:
        return {"ok": False, "error": "LangChain ReAct dependencies not installed.", "text": ""}

    groq_api_key = get_groq_api_key()
    if not groq_api_key:
        return {"ok": False, "error": "Groq API key not configured.", "text": ""}

    model = str(model_overrides.get("groq_model", "qwen/qwen3-32b")).strip() or "qwen/qwen3-32b"

    def prompt_quality_check(text: str) -> str:
        lowered = text.lower()
        flags = []
        for token in ["composition", "lighting", "typography", "brand", "market", "cta"]:
            if token not in lowered:
                flags.append(token)
        return "missing:" + ",".join(flags) if flags else "ok"

    tools = [
        Tool(
            name="prompt_quality_check",
            func=prompt_quality_check,
            description="Checks whether a prompt includes key production guidance tokens.",
        )
    ]

    prompt_template = PromptTemplate.from_template(
        """You are a ReAct prompt structurer for image generation.
You have access to these tools:
{tools}

Use the following format:
Question: the input question
Thought: your reasoning
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (repeat Thought/Action/Action Input/Observation as needed)
Thought: I now know the final answer
Final Answer: a single production-ready image prompt string.

Question: {input}
{agent_scratchpad}"""
    )

    llm = ChatOpenAI(
        api_key=cast(Any, groq_api_key),
        base_url="https://api.groq.com/openai/v1",
        model=model,
        temperature=0.2,
    )

    agent = create_react_agent(llm=llm, tools=tools, prompt=prompt_template)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=False, handle_parsing_errors=True)
    result = await executor.ainvoke({"input": base_prompt})
    text = str(result.get("output", "")).strip()
    return {"ok": bool(text), "error": None if text else "ReAct agent returned empty output.", "text": text}


def _provider_candidates(model_overrides: Dict[str, Any] | None = None) -> List[str]:
    overrides = model_overrides or {}
    explicit_provider = str(overrides.get("image_provider", "")).strip().lower()
    providers = overrides.get("image_providers")
    candidates: List[str] = []

    alias_map = {
        "klie": "kie",
        "kie-ai": "kie",
        "kie ai": "kie",
        "kie_ai": "kie",
        "google": "gemini",
        "google-gemini": "gemini",
    }

    def normalize_provider_name(name: str) -> str:
        return alias_map.get(name, name)

    if isinstance(providers, list):
        for item in providers:
            if isinstance(item, str) and item.strip():
                candidates.append(normalize_provider_name(item.strip().lower()))
    if explicit_provider:
        candidates.insert(0, normalize_provider_name(explicit_provider))

    if _is_kie_disabled():
        candidates = [item for item in candidates if item not in KIE_BACKED_IMAGE_PROVIDERS]

    if candidates:
        unique: List[str] = []
        for item in candidates:
            if item not in unique:
                unique.append(item)
        return unique

    # Default routing prefers KIE first, then FAL, then legacy providers and final fallback.
    if _is_kie_disabled():
        candidates.extend(["fal", "pollinations"])
    else:
        candidates.extend(["kie", "fal", "nanobanna", "nanobanna-2", "pollinations"])

    unique: List[str] = []
    for item in candidates:
        if item not in unique:
            unique.append(item)
    return unique


async def generate_image_asset(
    *,
    prompt: str,
    width: int,
    height: int,
    model_overrides: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    overrides = model_overrides or {}
    explicit_provider = str(overrides.get("image_provider", "")).strip().lower()
    if explicit_provider == "klie":
        explicit_provider = "kie"

    normalized_image_providers = overrides.get("image_providers")
    if isinstance(normalized_image_providers, list):
        overrides["image_providers"] = [
            ("kie" if isinstance(item, str) and item.strip().lower() == "klie" else item)
            for item in normalized_image_providers
        ]
    configured_providers = overrides.get("image_providers")
    if _is_kie_disabled() and isinstance(configured_providers, list):
        overrides["image_providers"] = [
            item for item in configured_providers if not (isinstance(item, str) and item.strip().lower() in KIE_BACKED_IMAGE_PROVIDERS)
        ]
        configured_providers = overrides.get("image_providers")
    has_explicit_provider_list = isinstance(configured_providers, list) and len(configured_providers) > 0
    strict_provider_mode = bool(explicit_provider) or has_explicit_provider_list
    fal_model = str(overrides.get("fal_model", DEFAULT_FAL_MODEL)).strip() or DEFAULT_FAL_MODEL
    gemini_model = str(overrides.get("gemini_image_model", overrides.get("gemini_model", DEFAULT_GEMINI_MODEL))).strip() or DEFAULT_GEMINI_MODEL
    kie_model = str(overrides.get("kie_model", overrides.get("klie_model", "nano-banana-2"))).strip() or "nano-banana-2"
    kie_endpoint = str(overrides.get("kie_endpoint", overrides.get("klie_endpoint", DEFAULT_KIE_ENDPOINT))).strip() or DEFAULT_KIE_ENDPOINT
    kie_api_key = get_kie_api_key()
    attempted: List[Dict[str, str]] = []

    if _is_kie_disabled() and explicit_provider in KIE_BACKED_IMAGE_PROVIDERS:
        attempted.append(
            {
                "provider": explicit_provider,
                "error": "KIE-backed providers are disabled by OPENPOMELLI_DISABLE_KIE.",
            }
        )

    for provider in _provider_candidates(overrides):
        try:
            if _is_kie_disabled() and provider in KIE_BACKED_IMAGE_PROVIDERS:
                attempted.append(
                    {
                        "provider": provider,
                        "error": "KIE-backed providers are disabled by OPENPOMELLI_DISABLE_KIE.",
                    }
                )
                continue

            if provider == "fal":
                result = await _generate_with_fal(prompt=prompt, width=width, height=height, model=fal_model)
                if result.get("ok"):
                    return {
                        "image_url": result["image_url"],
                        "provider": "fal",
                        "model": fal_model,
                        "status": "ok",
                        "attempted": attempted.copy(),
                    }
                attempted.append({"provider": "fal", "error": str(result.get("error", "unknown"))})
                continue

            if provider == "gemini":
                result = await _generate_with_gemini_image(
                    prompt=prompt,
                    width=width,
                    height=height,
                    model=gemini_model,
                )
                if result.get("ok"):
                    return {
                        "image_url": result["image_url"],
                        "provider": "gemini",
                        "model": str(result.get("model", gemini_model)),
                        "status": "ok",
                        "attempted": attempted.copy(),
                    }
                attempted.append({"provider": "gemini", "error": str(result.get("error", "unknown"))})
                continue

            if provider == "kie":
                if not kie_api_key:
                    attempted.append({"provider": "kie", "error": "KIE API key not configured."})
                    continue
                result = await _generate_with_kie(
                    prompt=prompt,
                    width=width,
                    height=height,
                    endpoint=kie_endpoint,
                    api_key=kie_api_key,
                    model=kie_model,
                    model_overrides=overrides,
                )
                if result.get("ok"):
                    return {
                        "image_url": result["image_url"],
                        "provider": "kie",
                        "model": kie_model,
                        "status": "ok",
                        "attempted": attempted.copy(),
                    }
                attempted.append({"provider": "kie", "error": str(result.get("error", "unknown"))})
                continue

            if provider == "nanobanna":
                image_url = await _generate_with_nanobanna(prompt=prompt, width=width, height=height)
                if image_url:
                    return {
                        "image_url": image_url,
                        "provider": "nanobanna",
                        "model": "nanobanna",
                        "status": "ok",
                        "attempted": attempted.copy(),
                    }
                attempted.append({"provider": "nanobanna", "error": "NanoBanana generation failed; image_url was None."})
                continue

            if provider == "nanobanna-2":
                image_url = await _generate_with_nanobanna_2(prompt=prompt, width=width, height=height)
                if image_url:
                    return {
                        "image_url": image_url,
                        "provider": "nanobanna-2",
                        "model": "nanobanna-2",
                        "status": "ok",
                        "attempted": attempted.copy(),
                    }
                attempted.append({"provider": "nanobanna-2", "error": "NanoBanana 2 generation failed; image_url was None."})
                continue

            if provider == "pollinations":
                return {
                    "image_url": _pollinations_url(prompt, width=width, height=height),
                    "provider": "pollinations",
                    "model": "flux",
                    "status": "fallback",
                    "attempted": attempted.copy(),
                }

            attempted.append({"provider": provider, "error": "Unknown provider requested."})
        except Exception as exc:
            attempted.append({"provider": provider, "error": _safe_error_message(provider, exc)})

    if strict_provider_mode:
        strict_model = "unknown"
        if explicit_provider == "gemini":
            strict_model = gemini_model
        elif explicit_provider == "kie":
            strict_model = kie_model
        elif has_explicit_provider_list and isinstance(configured_providers, list):
            first_provider = next(
                (
                    str(item).strip().lower()
                    for item in configured_providers
                    if isinstance(item, str) and str(item).strip()
                ),
                "",
            )
            if first_provider == "gemini":
                strict_model = gemini_model
            elif first_provider == "kie":
                strict_model = kie_model

        return {
            "image_url": "",
            "provider": explicit_provider or "configured-provider",
            "model": strict_model,
            "status": "error",
            "attempted": attempted.copy(),
            "error": "All configured providers failed.",
        }

    return {
        "image_url": _pollinations_url(prompt, width=width, height=height),
        "provider": "pollinations",
        "model": "flux",
        "status": "fallback",
        "attempted": attempted.copy(),
        "error": "All configured providers failed; fallback applied.",
    }


async def _build_seedream_edit_input(
    *,
    base_prompt: str,
    width: int,
    height: int,
    model_overrides: Dict[str, Any],
) -> Dict[str, Any]:
    image_urls_raw = model_overrides.get("seedream_image_urls", model_overrides.get("image_urls", []))
    image_urls = [item for item in image_urls_raw if isinstance(item, str) and item.strip()] if isinstance(image_urls_raw, list) else []

    inferred_size = "square_hd" if width == height else ("portrait" if height > width else "landscape")
    image_size = str(model_overrides.get("seedream_image_size", inferred_size)).strip() or inferred_size
    image_resolution = str(model_overrides.get("seedream_image_resolution", "1K")).strip() or "1K"
    nsfw_checker = bool(model_overrides.get("seedream_nsfw_checker", True))
    max_images_raw = model_overrides.get("seedream_max_images", 1)
    try:
        max_images = max(1, int(max_images_raw))
    except (TypeError, ValueError):
        max_images = 1

    structured_prompt = base_prompt
    if get_groq_api_key():
        groq_model = str(model_overrides.get("groq_model", "qwen/qwen3-32b")).strip() or "qwen/qwen3-32b"
        groq_prompt = (
            "Return ONLY valid JSON, no markdown. "
            "Create a strict Seedream edit request body for a poster-edit task with this schema:\n"
            "{\n"
            "  \"image_size\": \"square_hd\",\n"
            "  \"image_resolution\": \"1K\",\n"
            "  \"prompt\": \"string\",\n"
            "  \"max_images\": 1,\n"
            "  \"nsfw_checker\": true\n"
            "}\n"
            f"Base prompt: {base_prompt}\n"
            f"Preferred image_size: {image_size}\n"
            f"Preferred image_resolution: {image_resolution}\n"
            f"Preferred max_images: {max_images}\n"
            f"Preferred nsfw_checker: {str(nsfw_checker).lower()}\n"
            "Keep the prompt vivid and production ready for brand poster editing."
        )
        groq_result = await call_groq(
            prompt=groq_prompt,
            model=groq_model,
            temperature=0.2,
            max_tokens=600,
        )
        if groq_result.get("ok"):
            parsed = extract_json_object(str(groq_result.get("text", "")))
            if isinstance(parsed, dict):
                candidate = str(parsed.get("prompt", "")).strip()
                if candidate:
                    structured_prompt = candidate
                image_size = str(parsed.get("image_size", image_size)).strip() or image_size
                image_resolution = str(parsed.get("image_resolution", image_resolution)).strip() or image_resolution
                nsfw_checker = bool(parsed.get("nsfw_checker", nsfw_checker))
                try:
                    max_images = max(1, int(parsed.get("max_images", max_images)))
                except (TypeError, ValueError):
                    max_images = max_images

    return {
        "image_size": image_size,
        "image_resolution": image_resolution,
        "image_urls": image_urls,
        "max_images": max_images,
        "prompt": structured_prompt,
        "nsfw_checker": nsfw_checker,
    }


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    candidate = url.strip()
    if not candidate:
        return None
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    return candidate


def extract_domain(url: str | None) -> str:
    normalized = normalize_url(url)
    if not normalized:
        return ""
    return urlparse(normalized).netloc.lower()


async def fetch_website_context(url: str | None) -> Dict[str, Any]:
    normalized = normalize_url(url)
    if not normalized:
        return {
            "enabled": False,
            "url": None,
            "domain": "",
            "status": "skipped",
            "signals": ["No website URL provided."],
        }

    result: Dict[str, Any] = {
        "enabled": True,
        "url": normalized,
        "domain": extract_domain(normalized),
        "status": "ok",
        "signals": [],
        "title": "",
        "meta_description": "",
        "headings": [],
        "excerpt": "",
        "status_code": None,
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12.0, verify=_http_verify_option()) as client:
            response = await client.get(
                normalized,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0 Safari/537.36 OpenPomelliBot/1.0"
                    )
                },
            )
        result["status_code"] = response.status_code
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        title = (soup.title.string or "").strip() if soup.title else ""
        meta = soup.find("meta", attrs={"name": re.compile("description", re.I)})
        meta_description = ""
        if meta and meta.get("content"):
            meta_description = str(meta.get("content")).strip()

        heading_tags = soup.find_all(["h1", "h2", "h3"], limit=12)
        headings = [tag.get_text(" ", strip=True) for tag in heading_tags if tag.get_text(strip=True)]

        excerpt_chunks = []
        for tag_name in ["p", "li"]:
            for node in soup.find_all(tag_name, limit=60):
                text = node.get_text(" ", strip=True)
                if text and len(text) > 20:
                    excerpt_chunks.append(text)
            if len(" ".join(excerpt_chunks)) > 2500:
                break

        excerpt = "\n".join(excerpt_chunks)[:1200]

        result["title"] = title
        result["meta_description"] = meta_description
        result["headings"] = headings[:10]
        result["excerpt"] = excerpt

        if title:
            result["signals"].append(f"Page title captured: {title}")
        if meta_description:
            result["signals"].append("Meta description captured for brand positioning clues.")
        if headings:
            result["signals"].append(f"Captured {len(headings[:10])} heading signals.")
        if excerpt:
            result["signals"].append("Extracted body copy excerpt for tone and value proposition analysis.")

    except Exception as exc:
        result["status"] = "error"
        result["error"] = _safe_error_message("Website fetch", exc)
        result["signals"] = [result["error"]]

    return result


def build_inline_assets(uploaded_assets: List[Dict[str, Any]] | None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    assets = uploaded_assets or []
    parts: List[Dict[str, Any]] = []
    used_assets: List[Dict[str, Any]] = []
    skipped_assets: List[Dict[str, str]] = []

    for asset in assets:
        if len(parts) >= MAX_INLINE_ASSETS:
            skipped_assets.append(
                {
                    "name": str(asset.get("name", "unnamed")),
                    "reason": f"Only the first {MAX_INLINE_ASSETS} multimodal assets are used.",
                }
            )
            continue

        mime_type = str(asset.get("type", "")).strip().lower()
        base64_data = str(asset.get("base64", "")).strip()

        if not mime_type or not any(mime_type.startswith(prefix) for prefix in SUPPORTED_ASSET_MIME_PREFIXES):
            skipped_assets.append(
                {
                    "name": str(asset.get("name", "unnamed")),
                    "reason": "Unsupported mime type for Gemini inline analysis.",
                }
            )
            continue

        if not base64_data:
            skipped_assets.append(
                {
                    "name": str(asset.get("name", "unnamed")),
                    "reason": "Missing base64 payload.",
                }
            )
            continue

        if len(base64_data) > MAX_BASE64_CHARS:
            skipped_assets.append(
                {
                    "name": str(asset.get("name", "unnamed")),
                    "reason": "Asset too large for inline model call.",
                }
            )
            continue

        parts.append(
            {
                "inlineData": {
                    "mimeType": mime_type,
                    "data": base64_data,
                }
            }
        )
        used_assets.append(
            {
                "name": str(asset.get("name", "unnamed")),
                "type": mime_type,
                "size": int(asset.get("size", 0) or 0),
            }
        )

    summary = {
        "asset_count": len(assets),
        "used_asset_count": len(used_assets),
        "used_assets": used_assets,
        "skipped_assets": skipped_assets,
        "asset_types": sorted({item.get("type", "unknown") for item in used_assets}),
    }

    return parts, summary


async def call_gemini(
    *,
    prompt: str,
    inline_parts: List[Dict[str, Any]] | None = None,
    model: str | None = None,
    temperature: float = 0.35,
    max_output_tokens: int = 1800,
    response_mime_type: str | None = None,
) -> Dict[str, Any]:
    api_key = get_gemini_api_key()
    if not api_key:
        return {
            "ok": False,
            "error": "GEMINI_API_KEY not configured.",
            "text": "",
            "model": model or DEFAULT_GEMINI_MODEL,
        }

    preferred_model = (model or "").strip()
    fallback_models = [
        DEFAULT_GEMINI_MODEL,
        "gemini-3.1-flash-image-preview",
        "gemini-3.1-flash",
        "gemini-3.0-flash",
        "gemini-3.0-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro-latest",
    ]
    candidate_models = [candidate for candidate in [preferred_model, *fallback_models] if candidate]
    # Preserve order while removing duplicates.
    unique_models: List[str] = []
    for candidate in candidate_models:
        if candidate not in unique_models:
            unique_models.append(candidate)

    parts = [{"text": prompt}]
    if inline_parts:
        parts.extend(inline_parts)

    payload: Dict[str, Any] = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        },
    }
    if response_mime_type:
        payload["generationConfig"]["responseMimeType"] = response_mime_type

    attempted: List[Dict[str, str]] = []
    for chosen_model in unique_models:
        endpoint = GEMINI_API_ENDPOINT.format(model=chosen_model)
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=40.0, verify=_http_verify_option()) as client:
                    response = await client.post(
                        endpoint,
                        params={"key": api_key},
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )

                if response.status_code in {404, 400}:
                    attempted.append({"model": chosen_model, "error": f"HTTP {response.status_code}"})
                    break

                if response.status_code == 429:
                    attempted.append({"model": chosen_model, "error": f"HTTP 429 attempt {attempt + 1}"})
                    await asyncio.sleep(min(6, attempt + 1))
                    continue

                response.raise_for_status()
                body = response.json()

                candidates = body.get("candidates") or []
                if not candidates:
                    attempted.append({"model": chosen_model, "error": "No candidates returned"})
                    break

                candidate = candidates[0]
                content = candidate.get("content", {})
                parts_out = content.get("parts", [])
                text_parts = [str(part.get("text", "")) for part in parts_out if isinstance(part, dict)]
                text = "\n".join([chunk for chunk in text_parts if chunk]).strip()

                return {
                    "ok": True,
                    "error": None,
                    "text": text,
                    "model": chosen_model,
                    "attempted_models": attempted,
                }
            except Exception as exc:
                attempted.append({"model": chosen_model, "error": _safe_error_message("Gemini", exc)})
                if attempt < 2:
                    await asyncio.sleep(min(6, attempt + 1))
                    continue
                break

    return {
        "ok": False,
        "error": "No Gemini model could be resolved for this key/region.",
        "text": "",
        "model": unique_models[0] if unique_models else None,
        "attempted_models": attempted,
    }


def extract_json_object(text: str) -> Dict[str, Any] | None:
    if not text.strip():
        return None

    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?", "", candidate).strip()
        candidate = re.sub(r"```$", "", candidate).strip()

    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        parsed = json.loads(candidate[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None

    return None


# ============================================================================
# Groq API Integration for Multi-Model Reasoning
# ============================================================================

def get_groq_api_key() -> str | None:
    """Retrieve Groq API key from environment or api_secrets."""
    env_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if env_key:
        return env_key
    try:
        from api_secrets import GROQ_API_KEY  # type: ignore
        if isinstance(GROQ_API_KEY, str) and GROQ_API_KEY.strip():
            return GROQ_API_KEY.strip()
    except Exception:
        return None
    return None


def get_firecrawl_api_key() -> str | None:
    for env_name in ["FIRECRAWL_API_KEY", "FIRECRAWL_KEY"]:
        value = (os.getenv(env_name) or "").strip()
        if value:
            return value
    return None


def get_serpapi_api_key() -> str | None:
    for env_name in ["SERPAPI_API_KEY", "SERP_API_KEY", "SERPAPI_KEY"]:
        value = (os.getenv(env_name) or "").strip()
        if value:
            return value

    try:
        from api_secrets import SERP_API_KEY  # type: ignore

        if isinstance(SERP_API_KEY, str) and SERP_API_KEY.strip():
            return SERP_API_KEY.strip()
    except Exception:
        pass

    return None


def normalize_poster_query(query: str) -> str:
    raw = str(query or "").strip()
    if not raw:
        return "brand posters"
    lowered = raw.lower()
    if "poster" in lowered:
        return raw
    return f"{raw} posters"


async def serpapi_search(query: str, *, limit: int = 6) -> Dict[str, Any]:
    api_key = get_serpapi_api_key()
    if not api_key:
        return {"ok": False, "error": "SERP API key not configured.", "results": [], "provider": "serpapi"}

    endpoint = "https://serpapi.com/search.json"
    params = {
        "q": query,
        "engine": "google",
        "num": max(1, min(limit, 20)),
        "api_key": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=25.0, verify=_http_verify_option()) as client:
            response = await client.get(endpoint, params=params)
        response.raise_for_status()
        body = response.json() if response.content else {}

        organic = body.get("organic_results") if isinstance(body, dict) else []
        if not isinstance(organic, list):
            organic = []

        normalized: List[Dict[str, str]] = []
        for item in organic:
            if not isinstance(item, dict):
                continue
            link = str(item.get("link") or item.get("url") or "").strip()
            if not link.startswith(("http://", "https://")):
                continue
            normalized.append(
                {
                    "url": link,
                    "title": str(item.get("title") or "").strip(),
                    "snippet": str(item.get("snippet") or "").strip(),
                    "source": str(item.get("source") or "google").strip() or "google",
                }
            )
            if len(normalized) >= limit:
                break

        return {"ok": True, "error": None, "results": normalized, "provider": "serpapi"}
    except Exception as exc:
        return {"ok": False, "error": _safe_error_message("SERP API", exc), "results": [], "provider": "serpapi"}


async def serpapi_image_search(query: str, *, limit: int = 10, page: int = 0) -> Dict[str, Any]:
    api_key = get_serpapi_api_key()
    if not api_key:
        return {"ok": False, "error": "SERP API key not configured.", "images": [], "provider": "serpapi"}

    normalized_query = normalize_poster_query(query)
    endpoint = "https://serpapi.com/search.json"
    params = {
        "q": normalized_query,
        "engine": "google_images",
        "ijn": str(max(0, min(page, 20))),
        "api_key": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=25.0, verify=_http_verify_option()) as client:
            response = await client.get(endpoint, params=params)
        response.raise_for_status()
        body = response.json() if response.content else {}

        image_results = body.get("images_results") if isinstance(body, dict) else []
        if not isinstance(image_results, list):
            image_results = []

        normalized: List[Dict[str, str]] = []
        for index, item in enumerate(image_results, start=1):
            if not isinstance(item, dict):
                continue
            image_url = str(item.get("original") or item.get("thumbnail") or "").strip()
            if not image_url.startswith(("http://", "https://")):
                continue

            source_page = str(item.get("link") or "").strip()
            source_name = str(item.get("source") or "Google Images").strip() or "Google Images"
            title = str(item.get("title") or f"Google image reference {index}").strip()

            normalized.append(
                {
                    "id": str(item.get("position") or index),
                    "image_url": image_url,
                    "description": title,
                    "photographer_name": source_name,
                    "photographer_url": source_page if source_page.startswith(("http://", "https://")) else "https://images.google.com",
                    "source": "google_images",
                }
            )
            if len(normalized) >= max(1, min(limit, 30)):
                break

        return {
            "ok": True,
            "error": None,
            "images": normalized,
            "provider": "serpapi",
            "query": normalized_query,
            "page": max(0, min(page, 20)),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": _safe_error_message("SERP API Images", exc),
            "images": [],
            "provider": "serpapi",
            "query": normalized_query,
            "page": max(0, min(page, 20)),
        }


async def firecrawl_search(query: str, *, limit: int = 6) -> Dict[str, Any]:
    api_key = get_firecrawl_api_key()
    if not api_key:
        return {"ok": False, "error": "Firecrawl API key not configured.", "results": [], "provider": "firecrawl"}

    endpoint = "https://api.firecrawl.dev/v1/search"
    payload = {
        "query": query,
        "limit": max(1, min(limit, 20)),
        "scrapeOptions": {"formats": ["markdown"]},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=25.0, verify=_http_verify_option()) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()

        raw_results = []
        if isinstance(body, dict):
            for key in ["data", "results", "items"]:
                candidate = body.get(key)
                if isinstance(candidate, list):
                    raw_results = candidate
                    break
        normalized = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            url = item.get("url") or item.get("link")
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                continue
            normalized.append(
                {
                    "url": url,
                    "title": str(item.get("title") or "").strip(),
                    "snippet": str(item.get("description") or item.get("snippet") or "").strip(),
                    "source": str(item.get("source") or "").strip(),
                }
            )
        return {"ok": True, "error": None, "results": normalized, "provider": "firecrawl"}
    except Exception as exc:
        return {"ok": False, "error": _safe_error_message("Firecrawl", exc), "results": [], "provider": "firecrawl"}


def get_extract_pics_api_key() -> str | None:
    for env_name in ["EXTRACT_PICS_API_KEY", "EXTRACT_PICS_KEY"]:
        value = (os.getenv(env_name) or "").strip()
        if value:
            return value
    return None


def get_kling_access_key() -> str | None:
    for env_name in ["KLING_ACCESS_KEY", "KLING_API_ACCESS_KEY"]:
        value = (os.getenv(env_name) or "").strip()
        if value:
            return value
    return None


def get_kling_secret_key() -> str | None:
    for env_name in ["KLING_SECRET_KEY", "KLING_API_SECRET_KEY"]:
        value = (os.getenv(env_name) or "").strip()
        if value:
            return value
    return None


def _kling_bearer_token() -> str | None:
    explicit = (os.getenv("KLING_BEARER_TOKEN") or "").strip()
    if explicit:
        return explicit

    access_key = get_kling_access_key()
    secret_key = get_kling_secret_key()
    if not access_key or not secret_key:
        return None

    now = int(time.time())
    payload = {
        "iss": access_key,
        "iat": now - 5,
        "nbf": now - 5,
        "exp": now + 1800,
    }
    try:
        token = jwt.encode(payload, secret_key, algorithm="HS256")
        if isinstance(token, bytes):
            return token.decode("utf-8")
        return str(token)
    except Exception:
        return None


async def kling_text_to_video(
    *,
    prompt: str,
    negative_prompt: str = "",
    duration: str = "5",
    aspect_ratio: str = "1:1",
    model_name: str = "kling-v2-6",
    mode: str = "pro",
    sound: str = "on",
) -> Dict[str, Any]:
    token = _kling_bearer_token()
    if not token:
        return {"ok": False, "error": "Kling credentials are not configured.", "task_id": None}

    create_url = "https://api-singapore.klingai.com/v1/videos/text2video"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model_name": model_name,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "duration": duration,
        "mode": mode,
        "sound": sound,
        "aspect_ratio": aspect_ratio,
        "callback_url": "",
        "external_task_id": "",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0, verify=_http_verify_option()) as client:
            create_res = await client.post(create_url, headers=headers, json=payload)
            if create_res.status_code >= 400:
                provider_message = ""
                provider_code = ""
                try:
                    error_body = create_res.json()
                    if isinstance(error_body, dict):
                        provider_message = str(error_body.get("message") or "").strip()
                        provider_code = str(error_body.get("code") or "").strip()
                except Exception:
                    provider_message = ""
                    provider_code = ""
                detail = _safe_error_message("Kling task create", status_code=create_res.status_code)
                if provider_message:
                    code_prefix = f"[{provider_code}] " if provider_code else ""
                    detail = f"{detail}: {code_prefix}{provider_message}"
                return {
                    "ok": False,
                    "error": detail,
                    "task_id": None,
                }
            create_body = create_res.json()
            data = create_body.get("data") if isinstance(create_body, dict) else None
            task_id = str(data.get("task_id") if isinstance(data, dict) else "").strip()
            if not task_id:
                return {"ok": False, "error": "Kling did not return task_id.", "task_id": None}

            status = str(data.get("task_status") if isinstance(data, dict) else "submitted").strip().lower()
            poll_url = f"{create_url}/{task_id}"
            poll_body = create_body
            attempts = 0
            while status not in {"succeed", "failed"} and attempts < 120:
                attempts += 1
                await asyncio.sleep(2.0)
                poll_res = await client.get(poll_url, headers={"Authorization": f"Bearer {token}"})
                if poll_res.status_code >= 400:
                    provider_message = ""
                    provider_code = ""
                    try:
                        error_body = poll_res.json()
                        if isinstance(error_body, dict):
                            provider_message = str(error_body.get("message") or "").strip()
                            provider_code = str(error_body.get("code") or "").strip()
                    except Exception:
                        provider_message = ""
                        provider_code = ""
                    detail = _safe_error_message("Kling task poll", status_code=poll_res.status_code)
                    if provider_message:
                        code_prefix = f"[{provider_code}] " if provider_code else ""
                        detail = f"{detail}: {code_prefix}{provider_message}"
                    return {
                        "ok": False,
                        "error": detail,
                        "task_id": task_id,
                    }
                poll_body = poll_res.json()
                poll_data = poll_body.get("data") if isinstance(poll_body, dict) else None
                status = str(poll_data.get("task_status") if isinstance(poll_data, dict) else "").strip().lower()

            poll_data = poll_body.get("data") if isinstance(poll_body, dict) else None
            task_result = poll_data.get("task_result") if isinstance(poll_data, dict) else None
            videos = task_result.get("videos") if isinstance(task_result, dict) and isinstance(task_result.get("videos"), list) else []
            first = videos[0] if videos and isinstance(videos[0], dict) else {}
            video_url = str(first.get("url") or "").strip()
            watermark_url = str(first.get("watermark_url") or "").strip()
            if status != "succeed" or not video_url:
                message = str(poll_data.get("task_status_msg") if isinstance(poll_data, dict) else "").strip()
                return {
                    "ok": False,
                    "error": message or f"Kling task ended with status={status}",
                    "task_id": task_id,
                }
            return {
                "ok": True,
                "error": None,
                "task_id": task_id,
                "status": status,
                "video_url": video_url,
                "watermark_url": watermark_url,
                "model": model_name,
                "duration": str(first.get("duration") or duration),
            }
    except Exception as exc:
        return {
            "ok": False,
            "error": _safe_error_message("Kling", exc),
            "task_id": None,
        }


def get_vadoo_api_key() -> str | None:
    for env_name in ["VADOO_AI_API_KEY", "VADOO_API_KEY"]:
        value = (os.getenv(env_name) or "").strip()
        if value:
            return value

    try:
        from api_secrets import VADOO_API_KEY  # type: ignore

        if isinstance(VADOO_API_KEY, str) and VADOO_API_KEY.strip():
            return VADOO_API_KEY.strip()
    except Exception:
        pass

    return None


def _normalize_vadoo_duration(duration: str) -> str:
    raw = str(duration or "").strip().lower()
    allowed = {"30-60", "60-90", "90-120", "120-180", "5 min", "10 min"}
    if raw in allowed:
        return raw
    return "30-60"


async def vadoo_get_my_balance() -> Dict[str, Any]:
    api_key = get_vadoo_api_key()
    if not api_key:
        return {"ok": False, "error": "Vadoo API key not configured.", "credits": None}

    url = "https://aiapi.vadoo.tv/api/get_my_balance"
    headers = {"X-Api-Key": api_key}
    try:
        async with httpx.AsyncClient(timeout=20.0, verify=_http_verify_option()) as client:
            response = await client.get(url, headers=headers)
        if response.status_code >= 400:
            return {
                "ok": False,
                "error": _safe_error_message("Vadoo balance", status_code=response.status_code),
                "credits": None,
            }
        body = response.json() if response.content else {}
        credits = body.get("credits") if isinstance(body, dict) else None
        return {"ok": True, "error": None, "credits": credits}
    except Exception as exc:
        return {"ok": False, "error": _safe_error_message("Vadoo balance", exc), "credits": None}


async def vadoo_text_to_video(
    *,
    prompt: str,
    duration: str = "30-60",
    aspect_ratio: str = "1:1",
    voice: str = "Onyx",
    language: str = "English",
    style: str = "None",
    theme: str = "Hormozi_1",
) -> Dict[str, Any]:
    api_key = get_vadoo_api_key()
    if not api_key:
        return {"ok": False, "error": "Vadoo API key not configured.", "task_id": None}

    create_url = "https://aiapi.vadoo.tv/api/generate_video"
    poll_url = "https://aiapi.vadoo.tv/api/get_video_url"
    headers = {"X-Api-Key": api_key, "Content-Type": "application/json"}
    create_payload = {
        "topic": "Custom",
        "duration": _normalize_vadoo_duration(duration),
        "prompt": prompt,
        "voice": voice,
        "language": language,
        "aspect_ratio": aspect_ratio,
        "style": style,
        "theme": theme,
        "use_ai": 0,
        "include_voiceover": 1,
        "speed": 1.0,
    }

    try:
        async with httpx.AsyncClient(timeout=45.0, verify=_http_verify_option()) as client:
            create_res = await client.post(create_url, headers=headers, json=create_payload)
            if create_res.status_code >= 400:
                provider_message = ""
                try:
                    error_body = create_res.json()
                    if isinstance(error_body, dict):
                        provider_message = str(error_body.get("message") or error_body.get("error") or "").strip()
                except Exception:
                    provider_message = ""
                detail = _safe_error_message("Vadoo task create", status_code=create_res.status_code)
                if provider_message:
                    detail = f"{detail}: {provider_message}"
                balance = await vadoo_get_my_balance()
                return {
                    "ok": False,
                    "error": detail,
                    "task_id": None,
                    "credits": balance.get("credits"),
                }

            create_body = create_res.json() if create_res.content else {}
            task_id = ""
            if isinstance(create_body, dict):
                task_id = str(create_body.get("vid") or create_body.get("id") or create_body.get("request_id") or "").strip()
            if not task_id:
                return {"ok": False, "error": "Vadoo did not return video id.", "task_id": None}

            attempts = 0
            latest: Dict[str, Any] = {}
            while attempts < 120:
                attempts += 1
                await asyncio.sleep(2.0)
                poll_res = await client.get(poll_url, headers={"X-Api-Key": api_key}, params={"id": task_id})
                if poll_res.status_code >= 400:
                    provider_message = ""
                    try:
                        error_body = poll_res.json()
                        if isinstance(error_body, dict):
                            provider_message = str(error_body.get("message") or error_body.get("error") or "").strip()
                    except Exception:
                        provider_message = ""
                    detail = _safe_error_message("Vadoo task poll", status_code=poll_res.status_code)
                    if provider_message:
                        detail = f"{detail}: {provider_message}"
                    return {"ok": False, "error": detail, "task_id": task_id}

                latest = poll_res.json() if poll_res.content else {}
                status = str(latest.get("status") if isinstance(latest, dict) else "").strip().lower()
                if status in {"completed", "failed"}:
                    if status == "completed":
                        video_url = str(latest.get("url") or "").strip()
                        if video_url:
                            return {
                                "ok": True,
                                "error": None,
                                "task_id": task_id,
                                "status": status,
                                "video_url": video_url,
                                "watermark_url": None,
                                "model": "vadoo-ai-story",
                                "duration": _normalize_vadoo_duration(duration),
                            }
                    fail_error = str(latest.get("error") or latest.get("message") or f"Vadoo task ended with status={status}").strip()
                    return {"ok": False, "error": fail_error, "task_id": task_id}

            return {"ok": False, "error": "Vadoo poll timeout before completion.", "task_id": task_id}
    except Exception as exc:
        return {
            "ok": False,
            "error": _safe_error_message("Vadoo", exc),
            "task_id": None,
        }


async def extract_pics_extract_images(url: str, *, max_images: int = 10) -> Dict[str, Any]:
    api_key = get_extract_pics_api_key()
    if not api_key:
        return {"ok": False, "error": "extract.pics API key not configured.", "images": []}

    if not url.startswith(("http://", "https://")):
        return {"ok": False, "error": "Invalid URL format for extract.pics extraction.", "images": []}

    base = "https://api.extract.pics/v0/extractions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=_http_verify_option()) as client:
            start_res = await client.post(base, headers=headers, json={"url": url})
            if start_res.status_code >= 400:
                return {
                    "ok": False,
                    "error": _safe_error_message("extract.pics start", status_code=start_res.status_code),
                    "images": [],
                }
            start_body = start_res.json()
            extraction = start_body.get("data") if isinstance(start_body, dict) else None
            extraction_id = str(extraction.get("id") if isinstance(extraction, dict) else "").strip()
            if not extraction_id:
                return {"ok": False, "error": "extract.pics did not return extraction id.", "images": []}

            status = str(extraction.get("status") if isinstance(extraction, dict) else "pending").strip().lower()
            attempts = 0
            poll_body = start_body
            while status not in {"done", "error"} and attempts < 25:
                attempts += 1
                await asyncio.sleep(1.2)
                poll_res = await client.get(f"{base}/{extraction_id}", headers={"Authorization": f"Bearer {api_key}"})
                if poll_res.status_code == 429:
                    await asyncio.sleep(2.0)
                    continue
                if poll_res.status_code >= 400:
                    return {
                        "ok": False,
                        "error": _safe_error_message("extract.pics poll", status_code=poll_res.status_code),
                        "images": [],
                    }
                poll_body = poll_res.json()
                data = poll_body.get("data") if isinstance(poll_body, dict) else None
                status = str(data.get("status") if isinstance(data, dict) else "error").strip().lower()

            data = poll_body.get("data") if isinstance(poll_body, dict) else None
            images = data.get("images") if isinstance(data, dict) and isinstance(data.get("images"), list) else []
            if status != "done":
                return {"ok": False, "error": f"extract.pics extraction status={status}", "images": []}

            urls: List[str] = []
            for item in images:
                if not isinstance(item, dict):
                    continue
                image_url = item.get("url")
                if isinstance(image_url, str) and image_url.startswith(("http://", "https://")) and image_url not in urls:
                    urls.append(image_url)
                if len(urls) >= max(1, max_images):
                    break
            return {"ok": True, "error": None, "images": urls, "status": status}
    except Exception as exc:
        return {"ok": False, "error": _safe_error_message("extract.pics", exc), "images": []}


async def call_groq(
    prompt: str,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> Dict[str, Any]:
    """Call Groq API for reasoning tasks. Supports qwen/qwen3-32b and other models."""
    api_key = get_groq_api_key()
    if not api_key:
        return {
            "ok": False,
            "error": "Groq API key not configured.",
            "text": "",
            "model": model or "qwen/qwen3-32b",
            "attempted_models": [],
        }

    chosen_model = model or "qwen/qwen3-32b"
    endpoint = "https://api.groq.com/openai/v1/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=_http_verify_option()) as client:
            response = await client.post(
                endpoint,
                json={
                    "model": chosen_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
        response.raise_for_status()
        body = response.json()
        text = ""
        if "choices" in body and len(body["choices"]) > 0:
            choice = body["choices"][0]
            if "message" in choice and "content" in choice["message"]:
                text = str(choice["message"]["content"]).strip()

        return {
            "ok": bool(text),
            "error": None if text else "No response content from Groq.",
            "text": text,
            "model": chosen_model,
            "attempted_models": [chosen_model],
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": _safe_error_message("Groq", exc),
            "text": "",
            "model": chosen_model,
            "attempted_models": [chosen_model],
        }


# ============================================================================
# NanoBanana Image Generation on KIE AI / KIE API
# ============================================================================

def get_nanobanna_config() -> Tuple[str | None, str | None]:
    """Get NanoBanana configuration from environment.
    Returns: (api_key, api_endpoint)
    """
    api_key = get_kie_api_key()
    api_endpoint = (
        os.getenv("KIE_API_ENDPOINT")
        or os.getenv("KLIE_API_ENDPOINT")
        or DEFAULT_KIE_ENDPOINT
    ).strip()
    return (api_key, api_endpoint)


async def _generate_with_nanobanna(
    prompt: str,
    width: int = 768,
    height: int = 1024,
) -> str | None:
    """Generate image using NanoBanana model on KIE AI endpoint."""
    api_key, endpoint = get_nanobanna_config()
    if not api_key or not endpoint:
        return None

    try:
        async with httpx.AsyncClient(timeout=60.0, verify=_http_verify_option()) as client:
            response = await client.post(
                endpoint,
                json={
                    "prompt": prompt,
                    "model": "nanobanna",
                    "width": width,
                    "height": height,
                    "steps": 30,
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
        response.raise_for_status()
        body = response.json()

        # Extract image URL from NanoBanana response
        image_url = _first_url(body)
        return image_url

    except Exception as exc:
        LOGGER.debug("NanoBanana request failed: %s", _safe_error_message("NanoBanana", exc))
        return None


async def _generate_with_nanobanna_2(
    prompt: str,
    width: int = 768,
    height: int = 1024,
) -> str | None:
    """Generate image using NanoBanana 2 model on KIE API endpoint."""
    api_key, endpoint = get_nanobanna_config()
    if not api_key or not endpoint:
        return None

    try:
        async with httpx.AsyncClient(timeout=60.0, verify=_http_verify_option()) as client:
            response = await client.post(
                endpoint,
                json={
                    "prompt": prompt,
                    "model": "nanobanna-2",
                    "width": width,
                    "height": height,
                    "quality": "high",
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
        response.raise_for_status()
        body = response.json()

        # Extract image URL from NanoBanana 2 response
        image_url = _first_url(body)
        return image_url

    except Exception as exc:
        LOGGER.debug("NanoBanana 2 request failed: %s", _safe_error_message("NanoBanana 2", exc))
        return None
