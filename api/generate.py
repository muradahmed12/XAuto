"""Generate a draft post via Gemini and persist it to Vercel KV."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(__file__))

from lib.http_utils import send_json, send_options
from lib.kv_store import KVStoreError, upsert_post

PROMPT = """You are drafting a single, high-impact X (Twitter) post for @devmuradahmed. You are acting as an experienced Software Engineer and System Designer navigating the modern tech landscape.

Randomly select ONE of the following broad IT and AI-era themes for this post:
1. The AI Shift: Pragmatic insights on building software in the AI era. This includes integrating LLMs into apps, shifting from writing boilerplate to system design, or the realities of "AI coding" vs. actual software engineering.
2. Architecture & Scale: High-level thoughts on system design, building clean backend architectures, APIs, handling state, or managing complexity in enterprise platforms.
3. Full-Stack Engineering: The balance between backend stability and frontend user experience, performance optimization, and the evolution of modern web apps.
4. Developer Culture & Philosophy: Sharp, witty, or contrarian observations about clean code, technical debt, agile workflows, debugging under pressure, or general industry trends.

Strict Constraints:
- Maximum length: 280 characters.
- Tone: Authoritative, practical, and punchy. Write like an active builder sharing unfiltered insights from the trenches. Avoid generic motivational talk.
- NO emojis whatsoever.
- NO hashtags.
- NO thread markers (e.g., 1/x, 🧵).
- NO conversational filler. Start directly with the hook or insight.
- Output ONLY the raw text of the post."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _generate_content() -> str:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise RuntimeError("google-generativeai package is not installed") from exc

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    try:
        response = model.generate_content(PROMPT)
    except Exception as exc:
        raise RuntimeError(f"Gemini API request failed: {exc}") from exc

    text = (getattr(response, "text", None) or "").strip()
    if not text and getattr(response, "candidates", None):
        parts = response.candidates[0].content.parts
        text = "".join(getattr(part, "text", "") for part in parts).strip()

    if not text:
        raise RuntimeError("Gemini returned an empty response")

    # Strip wrapping quotes and enforce tweet length.
    text = text.strip("\"'")
    if len(text) > 280:
        text = text[:277].rstrip() + "..."

    return text


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        send_options(self)

    def do_GET(self) -> None:
        self._handle_generate()

    def do_POST(self) -> None:
        self._handle_generate()

    def _handle_generate(self) -> None:
        try:
            content = _generate_content()
            now = _utc_now()
            scheduled_for = now + timedelta(hours=4)

            post = {
                "id": str(uuid.uuid4()),
                "content": content,
                "scheduled_for": _iso(scheduled_for),
                "status": "draft",
                "created_at": _iso(now),
            }
            saved = upsert_post(post)

            send_json(
                self,
                201,
                {
                    "success": True,
                    "message": "Draft generated and saved",
                    "post": saved,
                },
            )
        except KVStoreError as exc:
            send_json(self, 503, {"success": False, "error": str(exc)})
        except RuntimeError as exc:
            send_json(self, 502, {"success": False, "error": str(exc)})
        except Exception as exc:
            send_json(
                self,
                500,
                {"success": False, "error": f"Unexpected error: {exc}"},
            )
