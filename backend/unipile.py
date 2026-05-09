from __future__ import annotations

import json
import os
from html import escape
from typing import Any
from urllib.parse import quote

import httpx


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


class UniPileConfig:
    def __init__(self) -> None:
        base = _env("UNIPILE_BASE_URL", "https://api31.unipile.com:16154")
        if not base.startswith("http"):
            base = f"https://{base}"
        self.base_url = base.rstrip("/")
        self.api_key = _env("UNIPILE_API_KEY")
        self.email_account_id = _env("UNIPILE_EMAIL_ACCOUNT_ID")
        self.linkedin_account_id = _env("UNIPILE_LINKEDIN_ACCOUNT_ID")
        self.telegram_account_id = _env("UNIPILE_TELEGRAM_ACCOUNT_ID")
        self.whatsapp_account_id = _env("UNIPILE_WHATSAPP_ACCOUNT_ID")
        self.email_timeout_seconds = float(_env("UNIPILE_EMAIL_TIMEOUT_SECONDS", "120"))


class UniPileClient:
    def __init__(self, config: UniPileConfig | None = None) -> None:
        self.config = config or UniPileConfig()

    @property
    def headers(self) -> dict[str, str]:
        return {
            "X-API-KEY": self.config.api_key,
            "accept": "application/json",
            "content-type": "application/json",
        }

    @property
    def auth_headers(self) -> dict[str, str]:
        return {
            "X-API-KEY": self.config.api_key,
            "accept": "application/json",
        }

    async def list_accounts(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{self.config.base_url}/api/v1/accounts", headers=self.headers)
            response.raise_for_status()
            return response.json() if response.content else {"ok": True}

    async def _post_with_fallbacks(self, payload: dict[str, Any], endpoints: list[str]) -> dict[str, Any]:
        last_error = ""
        payload_preview = {
            "account_id": payload.get("account_id"),
            "channel": payload.get("channel"),
            "to": payload.get("to"),
            "subject": payload.get("subject"),
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            for endpoint in endpoints:
                url = f"{self.config.base_url}{endpoint}"
                try:
                    response = await client.post(url, headers=self.headers, json=payload)
                    if 200 <= response.status_code < 300:
                        data = response.json() if response.content else {}
                        return {
                            "ok": True,
                            "endpoint": endpoint,
                            "status_code": response.status_code,
                            "data": data,
                        }
                    last_error = f"{endpoint} -> {response.status_code}: {response.text[:240]}"
                except Exception as exc:
                    last_error = f"{endpoint} -> {exc}"
        return {"ok": False, "error": last_error, "payload": payload_preview}

    async def send_email(self, to_email: str, subject: str, html_body: str, text_body: str = "") -> dict[str, Any]:
        recipient_payload = [{"display_name": to_email.split("@")[0], "identifier": to_email}]
        data = {
            "account_id": self.config.email_account_id,
            "subject": subject,
            "body": html_body,
            "to": json.dumps(recipient_payload),
        }

        try:
            timeout = httpx.Timeout(self.config.email_timeout_seconds, connect=20.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.config.base_url}/api/v1/emails",
                    headers=self.auth_headers,
                    data=data,
                )
            if 200 <= response.status_code < 300:
                return {
                    "ok": True,
                    "endpoint": "/api/v1/emails",
                    "status_code": response.status_code,
                    "data": response.json() if response.content else {"status": "accepted"},
                }
            return {
                "ok": False,
                "error": f"/api/v1/emails -> {response.status_code}: {response.text[:240]}",
                "payload": {
                    "account_id": self.config.email_account_id,
                    "to": recipient_payload,
                    "subject": subject,
                },
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": f"/api/v1/emails -> {type(exc).__name__}: {repr(exc)}",
                "payload": {
                    "account_id": self.config.email_account_id,
                    "to": recipient_payload,
                    "subject": subject,
                },
            }

    async def _start_chat(self, account_id: str, attendee_id: str, message: str, channel: str) -> dict[str, Any]:
        payload = {
            "account_id": account_id,
            "text": message,
            "attendees_ids": [attendee_id],
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.config.base_url}/api/v1/chats",
                    headers=self.headers,
                    json=payload,
                )
            if 200 <= response.status_code < 300:
                return {
                    "ok": True,
                    "endpoint": "/api/v1/chats",
                    "status_code": response.status_code,
                    "data": response.json() if response.content else {},
                }
            return {
                "ok": False,
                "error": f"/api/v1/chats ({channel}) -> {response.status_code}: {response.text[:240]}",
                "payload": {
                    "account_id": account_id,
                    "attendees_ids": [attendee_id],
                },
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": f"/api/v1/chats ({channel}) -> {exc}",
                "payload": {
                    "account_id": account_id,
                    "attendees_ids": [attendee_id],
                },
            }

    async def send_whatsapp(self, to_phone: str, message: str) -> dict[str, Any]:
        normalized = to_phone if to_phone.endswith("@s.whatsapp.net") else f"{to_phone}@s.whatsapp.net"
        return await self._start_chat(
            account_id=self.config.whatsapp_account_id,
            attendee_id=normalized,
            message=message,
            channel="whatsapp",
        )

    async def send_telegram(self, to_phone: str, message: str) -> dict[str, Any]:
        return await self._start_chat(
            account_id=self.config.telegram_account_id,
            attendee_id=to_phone,
            message=message,
            channel="telegram",
        )


def _first_hex(palette: list[dict[str, Any]], fallback: str) -> str:
    for item in palette:
        value = str(item.get("hex") or item.get("value") or "").strip()
        if value:
            return value
    return fallback


def _collect_poster_urls(content: dict[str, Any]) -> list[str]:
    cards = content.get("asset_cards") if isinstance(content.get("asset_cards"), list) else []
    urls: list[str] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        poster_assets = card.get("poster_assets") if isinstance(card.get("poster_assets"), list) else []
        for asset in poster_assets:
            if not isinstance(asset, dict):
                continue
            image_url = str(asset.get("image_url") or "").strip()
            if image_url and image_url not in urls:
                urls.append(image_url)
    return urls


def build_communication_bundle(campaign: dict[str, Any], promotion_message: str = "") -> dict[str, str]:
    payload = campaign.get("start_payload", {}) if isinstance(campaign.get("start_payload"), dict) else {}
    brand_dna = campaign.get("brand_dna", {}) if isinstance(campaign.get("brand_dna"), dict) else {}
    identity = brand_dna.get("identity", {}) if isinstance(brand_dna.get("identity"), dict) else {}
    palette = identity.get("palette", []) if isinstance(identity.get("palette"), list) else []
    creative = campaign.get("creative_agent", {}) if isinstance(campaign.get("creative_agent"), dict) else {}
    content = campaign.get("content", {}) if isinstance(campaign.get("content"), dict) else {}

    brand_name = str(brand_dna.get("brand_name") or payload.get("brand_name") or "Brand Campaign").strip() or "Brand Campaign"
    goal = str(payload.get("campaign_goal") or "awareness").strip() or "awareness"
    audience = str(brand_dna.get("target_audience") or payload.get("audience") or "your audience").strip() or "your audience"
    industry = str(brand_dna.get("industry") or payload.get("industry") or "general").strip() or "general"
    value_proposition = str(brand_dna.get("value_proposition") or "").strip()
    tone_list = brand_dna.get("tone_of_voice") if isinstance(brand_dna.get("tone_of_voice"), list) else []
    poster_urls = _collect_poster_urls(content)

    email_subject = str(((creative.get("email") or {}) if isinstance(creative.get("email"), dict) else {}).get("subject") or f"{brand_name} campaign launch kit").strip() or f"{brand_name} campaign launch kit"
    email_body = str(((creative.get("email") or {}) if isinstance(creative.get("email"), dict) else {}).get("body") or "").strip()
    if not email_body:
        email_body = (
            f"Hi team,\\n\\n"
            f"Your {brand_name} campaign is ready with deterministic timing, brand identity context, and visual posters. "
            f"This rollout focuses on {goal} for {audience}.\\n\\n"
            "Best regards,\\nOpen Pomelli"
        )

    linkedin_post = str(((creative.get("linkedin") or {}) if isinstance(creative.get("linkedin"), dict) else {}).get("post") or f"{brand_name} campaign is now ready to launch.").strip()
    telegram_text = promotion_message.strip() or linkedin_post
    linked_in_intent = f"https://www.linkedin.com/feed/?shareActive=true&text={quote(linkedin_post)}"
    telegram_intent = f"https://t.me/share/url?url={quote('https://openpomelli.local/campaign')}&text={quote(telegram_text)}"

    primary = _first_hex(palette, "#1f4dff")
    accent = _first_hex(palette[1:] if len(palette) > 1 else [], "#0f172a")

    identity_lines = [f"Industry: {industry}", f"Audience: {audience}"]
    if tone_list:
        identity_lines.append(f"Tone: {', '.join(str(item) for item in tone_list[:6])}")
    if value_proposition:
        identity_lines.append(f"Value proposition: {value_proposition}")

    poster_rows: list[str] = []
    if poster_urls:
        poster_cells = [
            f"<td style=\"padding:6px;\"><img src=\"{escape(url, quote=True)}\" alt=\"Poster\" style=\"display:block;width:100%;max-width:300px;border-radius:10px;border:1px solid #d7dbe4;\" /></td>"
            for url in poster_urls[:8]
        ]
        for index in range(0, len(poster_cells), 2):
            poster_rows.append(f"<tr>{''.join(poster_cells[index:index + 2])}</tr>")

    poster_block = ""
    if poster_rows:
        poster_block = (
            "<div style=\"margin:14px 0;\">"
            "<p style=\"margin:0 0 10px;font-weight:700;\">Poster pack</p>"
            "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">"
            f"{''.join(poster_rows)}"
            "</table>"
            "</div>"
        )
    else:
        poster_block = "<p style=\"margin:12px 0;color:#6b7280;\">No poster assets were attached for this campaign yet.</p>"

    escaped_brand_name = escape(brand_name)
    escaped_goal = escape(goal)
    escaped_body = escape(email_body)
    escaped_identity = "<br/>".join(escape(line) for line in identity_lines)

    visual_html = f"""
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f4f6fb;font-family:Inter,Arial,sans-serif;color:#111827;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:24px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="680" cellpadding="0" cellspacing="0" style="width:680px;max-width:95%;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e5e7eb;">
            <tr>
              <td style="padding:20px 24px;background:{primary};color:#ffffff;">
                <h1 style="margin:0;font-size:24px;line-height:1.3;">{escaped_brand_name} campaign package</h1>
                <p style="margin:8px 0 0;opacity:0.95;">Goal: {escaped_goal}</p>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 24px;">
                <p style="margin:0 0 12px;white-space:pre-wrap;line-height:1.6;">{escaped_body}</p>
                <div style="margin:12px 0 18px;padding:12px;border:1px solid #e5e7eb;border-radius:10px;background:#fafafa;">
                  <p style="margin:0 0 8px;font-weight:600;">Brand identity</p>
                  <p style="margin:0 0 10px;line-height:1.5;color:#374151;">{escaped_identity}</p>
                  <p style="margin:0 0 8px;font-weight:600;">Brand palette preview</p>
                  <div style="display:flex;gap:10px;">
                    <span style="display:inline-block;width:48px;height:48px;border-radius:8px;background:{primary};border:1px solid #d1d5db;" title="Primary"></span>
                    <span style="display:inline-block;width:48px;height:48px;border-radius:8px;background:{accent};border:1px solid #d1d5db;" title="Accent"></span>
                  </div>
                </div>
                {poster_block}
                <p style="margin:0 0 8px;font-weight:600;">Promotion quick actions</p>
                <a href="{linked_in_intent}" style="display:inline-block;margin-right:8px;padding:10px 14px;border-radius:8px;background:#0a66c2;color:#fff;text-decoration:none;font-weight:600;">Post to LinkedIn</a>
                <a href="{telegram_intent}" style="display:inline-block;padding:10px 14px;border-radius:8px;background:#229ed9;color:#fff;text-decoration:none;font-weight:600;">Send via Telegram</a>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
""".strip()

    whatsapp_lines = [
        f"{brand_name} campaign kit is ready.",
        f"Goal: {goal}",
        f"Audience: {audience}",
        f"Poster assets in email: {len(poster_urls)}",
        promotion_message.strip() or linkedin_post,
        "",
        f"Post to LinkedIn: {linked_in_intent}",
        f"Send via Telegram: {telegram_intent}",
    ]
    if poster_urls:
        whatsapp_lines.append("Poster URLs:")
        whatsapp_lines.extend(poster_urls[:5])
    whatsapp_text = "\\n".join(whatsapp_lines)

    return {
        "subject": email_subject,
        "html": visual_html,
        "text": email_body,
        "whatsapp": whatsapp_text,
        "telegram": whatsapp_text,
        "linkedin_url": linked_in_intent,
        "telegram_url": telegram_intent,
    }
