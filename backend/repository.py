from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List

from backend.state import AgentLog, CampaignContext


BOOTSTRAP_USER_ID = "bootstrap-user"


class CampaignRepository:
    def __init__(self, db_path: str):
        self.db_path = str(Path(db_path))

    def initialize(self) -> None:
        conn = self._connect()
        try:
            schema_path = Path(__file__).with_name("schema.sql")
            conn.executescript(schema_path.read_text(encoding="utf-8"))
            self._migrate_user_ownership(conn)
            conn.commit()
        finally:
            conn.close()

    def create_campaign(self, state: CampaignContext, user_id: str) -> None:
        conn = self._connect()
        try:
            self._upsert_user(conn, user_id)
            conn.execute(
                """
                INSERT INTO campaigns (
                    id, user_id, status, current_node, refinement_count, start_payload, cco
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state["campaign_id"],
                    user_id,
                    state["status"],
                    state["current_node"],
                    state["refinement_count"],
                    json.dumps(state["start_payload"]),
                    json.dumps(state),
                ),
            )
            conn.execute(
                """
                INSERT INTO campaign_checkpoints (campaign_id, node_name, status, snapshot_json)
                VALUES (?, ?, ?, ?)
                """,
                (state["campaign_id"], state["current_node"], state["status"], json.dumps(state)),
            )
            conn.commit()
        finally:
            conn.close()

    def save_transition(
        self,
        state: CampaignContext,
        node_name: str,
        emitted_logs: Iterable[AgentLog],
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE campaigns
                SET status = ?, current_node = ?, refinement_count = ?, start_payload = ?, cco = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    state["status"],
                    state["current_node"],
                    state["refinement_count"],
                    json.dumps(state["start_payload"]),
                    json.dumps(state),
                    state["campaign_id"],
                ),
            )
            conn.execute(
                """
                INSERT INTO campaign_checkpoints (campaign_id, node_name, status, snapshot_json)
                VALUES (?, ?, ?, ?)
                """,
                (state["campaign_id"], node_name, state["status"], json.dumps(state)),
            )
            for entry in emitted_logs:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO campaign_logs
                    (campaign_id, seq, ts, agent, level, message, latency_ms, extra_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        state["campaign_id"],
                        entry["seq"],
                        entry["ts"],
                        entry["agent"],
                        entry.get("level", "info"),
                        entry["message"],
                        entry.get("latency_ms"),
                        json.dumps(entry.get("extra", {})) if entry.get("extra") else None,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def get_campaign(self, campaign_id: str, user_id: str | None = None) -> CampaignContext:
        if user_id:
            row = self._fetchone(
                "SELECT cco FROM campaigns WHERE id = ? AND user_id = ?",
                (campaign_id, user_id),
            )
        else:
            row = self._fetchone(
                "SELECT cco FROM campaigns WHERE id = ?",
                (campaign_id,),
            )
        if not row:
            raise KeyError(campaign_id)
        return json.loads(row["cco"])

    def get_status(self, campaign_id: str, user_id: str | None = None) -> Dict[str, Any]:
        if user_id:
            row = self._fetchone(
                """
                SELECT id, status, current_node, refinement_count, updated_at, created_at
                FROM campaigns WHERE id = ? AND user_id = ?
                """,
                (campaign_id, user_id),
            )
        else:
            row = self._fetchone(
                """
                SELECT id, status, current_node, refinement_count, updated_at, created_at
                FROM campaigns WHERE id = ?
                """,
                (campaign_id,),
            )
        if not row:
            raise KeyError(campaign_id)
        state = self.get_campaign(campaign_id, user_id)
        return {
            "campaign_id": row["id"],
            "status": row["status"],
            "current_node": row["current_node"],
            "refinement_count": row["refinement_count"],
            "updated_at": row["updated_at"],
            "created_at": row["created_at"],
            "progress": state.get("progress", {}),
            "completed_nodes": state.get("completed_nodes", []),
        }

    def list_campaigns(self, user_id: str, limit: int | None = None) -> List[Dict[str, Any]]:
        sql = """
            SELECT id, status, current_node, created_at, updated_at, start_payload, cco
            FROM campaigns
            WHERE user_id = ?
            ORDER BY datetime(created_at) DESC, id DESC
        """
        params: tuple[Any, ...] = (user_id,)
        if isinstance(limit, int) and limit > 0:
            sql += "\nLIMIT ?"
            params = (user_id, max(1, min(limit, 1000)))
        rows = self._fetchall(sql, params)
        campaigns: List[Dict[str, Any]] = []
        for row in rows:
            start_payload = self._safe_json_loads(row["start_payload"])
            state = self._safe_json_loads(row["cco"])
            content = state.get("content") if isinstance(state.get("content"), dict) else {}
            export_bundle = content.get("export_bundle") if isinstance(content.get("export_bundle"), dict) else {}
            asset_cards = content.get("asset_cards") if isinstance(content.get("asset_cards"), list) else []
            schedule = state.get("schedule") if isinstance(state.get("schedule"), dict) else {}
            campaigns.append(
                {
                    "campaign_id": row["id"],
                    "status": row["status"],
                    "current_node": row["current_node"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "start_payload": start_payload,
                    "content_hub": {
                        "has_content": bool(content),
                        "asset_card_count": len(asset_cards),
                        "markets": export_bundle.get("markets") if isinstance(export_bundle.get("markets"), list) else [],
                        "providers_used": export_bundle.get("providers_used") if isinstance(export_bundle.get("providers_used"), list) else [],
                        "has_schedule": bool(schedule.get("days")) if isinstance(schedule, dict) else False,
                    },
                }
            )
        return campaigns

    def get_logs(self, campaign_id: str, user_id: str | None = None) -> List[Dict[str, Any]]:
        if user_id:
            rows = self._fetchall(
                """
                SELECT l.seq, l.ts, l.agent, l.level, l.message, l.latency_ms, l.extra_json
                FROM campaign_logs l
                JOIN campaigns c ON c.id = l.campaign_id
                WHERE l.campaign_id = ? AND c.user_id = ?
                ORDER BY l.id ASC
                """,
                (campaign_id, user_id),
            )
        else:
            rows = self._fetchall(
                """
                SELECT seq, ts, agent, level, message, latency_ms, extra_json
                FROM campaign_logs
                WHERE campaign_id = ?
                ORDER BY id ASC
                """,
                (campaign_id,),
            )
        logs = []
        for row in rows:
            logs.append(
                {
                    "seq": row["seq"],
                    "ts": row["ts"],
                    "agent": row["agent"],
                    "level": row["level"],
                    "message": row["message"],
                    "latency_ms": row["latency_ms"],
                    "extra": json.loads(row["extra_json"]) if row["extra_json"] else {},
                }
            )
        return logs

    def list_checkpoints(self, campaign_id: str) -> List[Dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT id, node_name, status, created_at
            FROM campaign_checkpoints
            WHERE campaign_id = ?
            ORDER BY id ASC
            """,
            (campaign_id,),
        )
        return [dict(row) for row in rows]

    def get_brand_identity(self, user_id: str, brand_name: str) -> Dict[str, Any] | None:
        normalized = self._normalize_brand_name(brand_name)
        if not normalized:
            return None
        row = self._fetchone(
            """
            SELECT brand_name, normalized_brand_name, profile_json, source_campaign_id, created_at, updated_at
            FROM brand_identity_cache
            WHERE normalized_brand_name = ? AND user_id = ?
            """,
            (normalized, user_id),
        )
        if not row:
            return None
        return {
            "brand_name": row["brand_name"],
            "normalized_brand_name": row["normalized_brand_name"],
            "profile": json.loads(row["profile_json"]),
            "source_campaign_id": row["source_campaign_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def upsert_brand_identity(
        self,
        user_id: str,
        brand_name: str,
        profile: Dict[str, Any],
        source_campaign_id: str | None = None,
    ) -> Dict[str, Any]:
        normalized = self._normalize_brand_name(brand_name)
        if not normalized:
            raise ValueError("Brand name is required for identity caching.")
        conn = self._connect()
        try:
            self._upsert_user(conn, user_id)
            conn.execute(
                """
                INSERT INTO brand_identity_cache (user_id, brand_name, normalized_brand_name, profile_json, source_campaign_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, normalized_brand_name) DO UPDATE SET
                    brand_name = excluded.brand_name,
                    profile_json = excluded.profile_json,
                    source_campaign_id = excluded.source_campaign_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    brand_name.strip(),
                    normalized,
                    json.dumps(profile),
                    source_campaign_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        cached = self.get_brand_identity(user_id, brand_name)
        if not cached:
            raise RuntimeError("Failed to upsert brand identity.")
        return cached

    def patch_brand_identity(self, user_id: str, brand_name: str, profile_patch: Dict[str, Any]) -> Dict[str, Any] | None:
        existing = self.get_brand_identity(user_id, brand_name)
        if not existing:
            return None
        merged_profile = self._deep_merge(existing["profile"], profile_patch)
        return self.upsert_brand_identity(user_id, existing["brand_name"], merged_profile, existing.get("source_campaign_id"))

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def save_generated_image(
        self,
        user_id: str,
        campaign_id: str,
        node_name: str,
        source_type: str,
        asset_type: str,
        prompt: str,
        image_url: str | None = None,
        image_path: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        width: int | None = None,
        height: int | None = None,
        status: str = "ok",
        attempted_providers: List[Dict[str, str]] | None = None,
        error: str | None = None,
    ) -> int:
        """Save a generated image record to the database. Returns the image ID."""
        conn = self._connect()
        try:
            self._upsert_user(conn, user_id)
            cursor = conn.execute(
                """
                INSERT INTO generated_images (
                    user_id, campaign_id, node_name, source_type, asset_type, prompt,
                    image_url, image_path, provider, model, width, height,
                    status, attempted_providers, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    campaign_id,
                    node_name,
                    source_type,
                    asset_type,
                    prompt,
                    image_url,
                    image_path,
                    provider,
                    model,
                    width,
                    height,
                    status,
                    json.dumps(attempted_providers or []),
                    error,
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0
        finally:
            conn.close()

    def get_generated_images_for_campaign(
        self,
        user_id: str,
        campaign_id: str,
        asset_type: str | None = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve generated images for a campaign, optionally filtered by asset type."""
        sql = "SELECT * FROM generated_images WHERE user_id = ? AND campaign_id = ?"
        params: tuple[Any, ...] = (user_id, campaign_id)

        if asset_type:
            sql += " AND asset_type = ?"
            params = (user_id, campaign_id, asset_type)

        sql += " ORDER BY created_at DESC"

        rows = self._fetchall(sql, params)
        normalized: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            attempted_raw = item.get("attempted_providers")
            if isinstance(attempted_raw, str) and attempted_raw:
                try:
                    parsed = json.loads(attempted_raw)
                    item["attempted_providers"] = parsed if isinstance(parsed, list) else []
                except json.JSONDecodeError:
                    item["attempted_providers"] = []
            normalized.append(item)
        return normalized

    def list_generated_images(
        self,
        user_id: str,
        campaign_id: str | None = None,
        limit: int = 300,
    ) -> List[Dict[str, Any]]:
        bounded_limit = max(1, min(limit, 1000))
        if campaign_id:
            sql = """
                SELECT gi.*, c.start_payload
                FROM generated_images gi
                JOIN campaigns c ON c.id = gi.campaign_id
                WHERE gi.user_id = ? AND gi.campaign_id = ?
                ORDER BY gi.created_at DESC
                LIMIT ?
            """
            params: tuple[Any, ...] = (user_id, campaign_id, bounded_limit)
        else:
            sql = """
                SELECT gi.*, c.start_payload
                FROM generated_images gi
                JOIN campaigns c ON c.id = gi.campaign_id
                WHERE gi.user_id = ?
                ORDER BY gi.created_at DESC
                LIMIT ?
            """
            params = (user_id, bounded_limit)

        rows = self._fetchall(sql, params)
        items: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            attempted_raw = item.get("attempted_providers")
            if isinstance(attempted_raw, str) and attempted_raw:
                try:
                    parsed = json.loads(attempted_raw)
                    item["attempted_providers"] = parsed if isinstance(parsed, list) else []
                except json.JSONDecodeError:
                    item["attempted_providers"] = []
            payload = self._safe_json_loads(item.get("start_payload"))
            item["brand_name"] = str(payload.get("brand_name") or "")
            item.pop("start_payload", None)
            items.append(item)
        return items

    def upsert_user(self, user_id: str, email: str | None = None, display_name: str | None = None) -> None:
        conn = self._connect()
        try:
            self._upsert_user(conn, user_id, email=email, display_name=display_name)
            conn.commit()
        finally:
            conn.close()

    def _upsert_user(
        self,
        conn: sqlite3.Connection,
        user_id: str,
        *,
        email: str | None = None,
        display_name: str | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO users (id, email, display_name)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                email = COALESCE(excluded.email, users.email),
                display_name = COALESCE(excluded.display_name, users.display_name),
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, email, display_name),
        )

    def _migrate_user_ownership(self, conn: sqlite3.Connection) -> None:
        bootstrap_user_id = os.getenv("OPENPOMELLI_BOOTSTRAP_USER_ID", BOOTSTRAP_USER_ID).strip() or BOOTSTRAP_USER_ID
        self._upsert_user(conn, bootstrap_user_id)

        campaign_columns = {row["name"] for row in conn.execute("PRAGMA table_info(campaigns)").fetchall()}
        if "user_id" not in campaign_columns:
            conn.execute("ALTER TABLE campaigns ADD COLUMN user_id TEXT")
        conn.execute("UPDATE campaigns SET user_id = COALESCE(NULLIF(user_id, ''), ?)", (bootstrap_user_id,))

        brand_columns = {row["name"] for row in conn.execute("PRAGMA table_info(brand_identity_cache)").fetchall()}
        if "user_id" not in brand_columns:
            conn.execute("ALTER TABLE brand_identity_cache ADD COLUMN user_id TEXT")
        conn.execute("UPDATE brand_identity_cache SET user_id = COALESCE(NULLIF(user_id, ''), ?)", (bootstrap_user_id,))

        generated_columns = {row["name"] for row in conn.execute("PRAGMA table_info(generated_images)").fetchall()}
        if "user_id" not in generated_columns:
            conn.execute("ALTER TABLE generated_images ADD COLUMN user_id TEXT")
        conn.execute("UPDATE generated_images SET user_id = COALESCE(NULLIF(user_id, ''), ?)", (bootstrap_user_id,))

        # Rebuild brand identity table to support per-user uniqueness.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS brand_identity_cache_v2 (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id TEXT NOT NULL,
              brand_name TEXT NOT NULL,
              normalized_brand_name TEXT NOT NULL,
              profile_json TEXT NOT NULL,
              source_campaign_id TEXT,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (source_campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL,
              FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
              UNIQUE(user_id, normalized_brand_name)
            )
            """
        )
        existing_rows = conn.execute(
            """
            SELECT user_id, brand_name, normalized_brand_name, profile_json, source_campaign_id, created_at, updated_at
            FROM brand_identity_cache
            """
        ).fetchall()
        conn.execute("DELETE FROM brand_identity_cache_v2")
        conn.executemany(
            """
            INSERT OR REPLACE INTO brand_identity_cache_v2
            (user_id, brand_name, normalized_brand_name, profile_json, source_campaign_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["user_id"] or bootstrap_user_id,
                    row["brand_name"],
                    row["normalized_brand_name"],
                    row["profile_json"],
                    row["source_campaign_id"],
                    row["created_at"],
                    row["updated_at"],
                )
                for row in existing_rows
            ],
        )
        conn.execute("DROP TABLE brand_identity_cache")
        conn.execute("ALTER TABLE brand_identity_cache_v2 RENAME TO brand_identity_cache")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_brand_identity_normalized ON brand_identity_cache (user_id, normalized_brand_name)")

    def get_generated_image_by_id(self, image_id: int) -> Dict[str, Any] | None:
        """Retrieve a generated image by ID."""
        row = self._fetchone("SELECT * FROM generated_images WHERE id = ?", (image_id,))
        if not row:
            return None
        item = dict(row)
        attempted_raw = item.get("attempted_providers")
        if isinstance(attempted_raw, str) and attempted_raw:
            try:
                parsed = json.loads(attempted_raw)
                item["attempted_providers"] = parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                item["attempted_providers"] = []
        return item

    def _fetchone(self, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
        conn = self._connect()
        try:
            return conn.execute(sql, params).fetchone()
        finally:
            conn.close()

    def _fetchall(self, sql: str, params: tuple[Any, ...]) -> List[sqlite3.Row]:
        conn = self._connect()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    @staticmethod
    def _normalize_brand_name(brand_name: str) -> str:
        return " ".join((brand_name or "").strip().lower().split())

    @staticmethod
    def _safe_json_loads(raw: Any) -> Dict[str, Any]:
        if not isinstance(raw, str) or not raw:
            return {}
        try:
            loaded = json.loads(raw)
            return loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            return {}

    @classmethod
    def _deep_merge(cls, base: Any, patch: Any) -> Any:
        if isinstance(base, dict) and isinstance(patch, dict):
            merged: Dict[str, Any] = {**base}
            for key, value in patch.items():
                merged[key] = cls._deep_merge(base.get(key), value) if key in base else value
            return merged
        return patch
