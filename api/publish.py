"""Cron-ready endpoint that publishes due approved posts to X (Twitter)."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(__file__))

from lib.http_utils import read_json_body, send_json, send_options
from lib.kv_store import KVStoreError, get_all_posts, upsert_post


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _verify_cron_auth(handler: BaseHTTPRequestHandler) -> bool:
    secret = os.environ.get("CRON_SECRET", "").strip()
    if not secret:
        # Allow unauthenticated calls when no secret is configured (local dev).
        return True

    auth_header = handler.headers.get("Authorization", "")
    if auth_header == f"Bearer {secret}":
        return True

    # Vercel Cron sends this header automatically when CRON_SECRET is set.
    cron_header = handler.headers.get("x-vercel-cron-secret", "")
    return cron_header == secret


def _create_tweet(content: str) -> str:
    consumer_key = os.environ.get("TWITTER_API_KEY", os.environ.get("TWITTER_CONSUMER_KEY", "")).strip()
    consumer_secret = os.environ.get("TWITTER_API_SECRET", os.environ.get("TWITTER_CONSUMER_SECRET", "")).strip()
    access_token = os.environ.get("TWITTER_ACCESS_TOKEN", "").strip()
    access_token_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", "").strip()

    missing = [
        name
        for name, value in [
            ("TWITTER_API_KEY (or TWITTER_CONSUMER_KEY)", consumer_key),
            ("TWITTER_API_SECRET (or TWITTER_CONSUMER_SECRET)", consumer_secret),
            ("TWITTER_ACCESS_TOKEN", access_token),
            ("TWITTER_ACCESS_TOKEN_SECRET", access_token_secret),
        ]
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing Twitter credentials: {', '.join(missing)}")

    try:
        import tweepy
    except ImportError as exc:
        raise RuntimeError("tweepy package is not installed") from exc

    client = tweepy.Client(
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
    )

    try:
        response = client.create_tweet(text=content)
    except Exception as exc:
        raise RuntimeError(f"Twitter API request failed: {exc}") from exc

    tweet_id = None
    if response and getattr(response, "data", None):
        tweet_id = response.data.get("id")

    if not tweet_id:
        raise RuntimeError("Twitter API did not return a tweet id")

    return str(tweet_id)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        send_options(self)

    def do_GET(self) -> None:
        self._publish_due_posts()

    def do_POST(self) -> None:
        self._publish_due_posts()

    def _publish_due_posts(self) -> None:
        if not _verify_cron_auth(self):
            send_json(self, 401, {"success": False, "error": "Unauthorized"})
            return

        action = ""
        if self.command == "POST":
            try:
                data = read_json_body(self)
            except ValueError:
                data = {}
            action = str(data.get("action", "")).strip().lower()

        publish_all = action == "publish_all"

        try:
            now = _utc_now()
            posts = get_all_posts()
            due_posts = []

            for post in posts:
                if post.get("status") != "approved":
                    continue
                if not publish_all:
                    scheduled_raw = post.get("scheduled_for")
                    if not isinstance(scheduled_raw, str):
                        continue
                    try:
                        scheduled_at = _parse_iso(scheduled_raw)
                    except ValueError:
                        continue
                    if scheduled_at > now:
                        continue
                due_posts.append(post)

            published = []
            errors = []

            for post in due_posts:
                post_id = post.get("id", "unknown")
                content = post.get("content", "")
                if not isinstance(content, str) or not content.strip():
                    errors.append({"id": post_id, "error": "Post has no content"})
                    continue

                try:
                    tweet_id = _create_tweet(content.strip())
                    post["status"] = "published"
                    post["published_at"] = _iso(now)
                    post["tweet_id"] = tweet_id
                    upsert_post(post)
                    published.append(
                        {
                            "id": post_id,
                            "tweet_id": tweet_id,
                            "content": content.strip(),
                        }
                    )
                except RuntimeError as exc:
                    errors.append({"id": post_id, "error": str(exc)})

            status_code = 200 if not errors else 207
            response_payload = {
                "success": len(errors) == 0,
                "checked_at": _iso(now),
                "action": "publish_all" if publish_all else "publish_due",
                "published_count": len(published),
                "published": published,
                "errors": errors,
            }
            if publish_all:
                response_payload["queued_count"] = len(due_posts)
            else:
                response_payload["due_count"] = len(due_posts)

            send_json(self, status_code, response_payload)
        except KVStoreError as exc:
            send_json(self, 503, {"success": False, "error": str(exc)})
        except Exception as exc:
            send_json(self, 500, {"success": False, "error": f"Unexpected error: {exc}"})
