"""CRUD operations for scheduled posts stored in Vercel KV."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(__file__))

from lib.http_utils import read_json_body, send_json, send_options
from lib.kv_store import KVStoreError, delete_post, get_all_posts, get_post_by_id, upsert_post

VALID_STATUSES = {"draft", "approved", "published"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validate_post_payload(data: dict) -> tuple[str | None, str | None]:
    content = data.get("content")
    scheduled_for = data.get("scheduled_for")

    if not isinstance(content, str) or not content.strip():
        return None, "content is required and must be a non-empty string"
    if len(content.strip()) > 280:
        return None, "content must be 280 characters or fewer"

    if not isinstance(scheduled_for, str) or not scheduled_for.strip():
        return None, "scheduled_for is required and must be an ISO timestamp string"

    try:
        _parse_iso(scheduled_for.strip())
    except ValueError:
        return None, "scheduled_for must be a valid ISO timestamp"

    return content.strip(), None


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        send_options(self)

    def do_GET(self) -> None:
        try:
            posts = get_all_posts()
            posts.sort(key=lambda p: p.get("created_at", ""), reverse=True)
            send_json(self, 200, {"success": True, "posts": posts, "count": len(posts)})
        except KVStoreError as exc:
            send_json(self, 503, {"success": False, "error": str(exc)})
        except Exception as exc:
            send_json(self, 500, {"success": False, "error": f"Unexpected error: {exc}"})

    def do_POST(self) -> None:
        try:
            data = read_json_body(self)
            action = data.get("action", "create")

            if action == "approve":
                self._approve_post(data)
                return

            if action == "create":
                self._create_post(data)
                return

            send_json(
                self,
                400,
                {"success": False, "error": "action must be 'create' or 'approve'"},
            )
        except ValueError as exc:
            send_json(self, 400, {"success": False, "error": str(exc)})
        except KVStoreError as exc:
            send_json(self, 503, {"success": False, "error": str(exc)})
        except Exception as exc:
            send_json(self, 500, {"success": False, "error": f"Unexpected error: {exc}"})

    def do_DELETE(self) -> None:
        try:
            data = read_json_body(self)
            post_id = data.get("id")
            if not isinstance(post_id, str) or not post_id.strip():
                send_json(self, 400, {"success": False, "error": "id is required"})
                return

            removed = delete_post(post_id.strip())
            if not removed:
                send_json(self, 404, {"success": False, "error": "Post not found"})
                return

            send_json(self, 200, {"success": True, "message": "Post deleted", "id": post_id})
        except ValueError as exc:
            send_json(self, 400, {"success": False, "error": str(exc)})
        except KVStoreError as exc:
            send_json(self, 503, {"success": False, "error": str(exc)})
        except Exception as exc:
            send_json(self, 500, {"success": False, "error": f"Unexpected error: {exc}"})

    def _approve_post(self, data: dict) -> None:
        post_id = data.get("id")
        if not isinstance(post_id, str) or not post_id.strip():
            send_json(self, 400, {"success": False, "error": "id is required to approve a post"})
            return

        post = get_post_by_id(post_id.strip())
        if post is None:
            send_json(self, 404, {"success": False, "error": "Post not found"})
            return

        current_status = post.get("status")
        if current_status == "published":
            send_json(
                self,
                409,
                {"success": False, "error": "Published posts cannot be re-approved"},
            )
            return

        post["status"] = "approved"
        saved = upsert_post(post)
        send_json(
            self,
            200,
            {"success": True, "message": "Post approved", "post": saved},
        )

    def _create_post(self, data: dict) -> None:
        content, error = _validate_post_payload(data)
        if error:
            send_json(self, 400, {"success": False, "error": error})
            return

        status = data.get("status", "draft")
        if status not in VALID_STATUSES:
            send_json(
                self,
                400,
                {"success": False, "error": f"status must be one of: {', '.join(sorted(VALID_STATUSES))}"},
            )
            return

        now = _utc_now()
        post = {
            "id": str(uuid.uuid4()),
            "content": content,
            "scheduled_for": _parse_iso(data["scheduled_for"].strip()).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "status": status,
            "created_at": _iso(now),
        }
        saved = upsert_post(post)
        send_json(
            self,
            201,
            {"success": True, "message": "Post created", "post": saved},
        )
