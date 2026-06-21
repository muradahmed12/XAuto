"""Vercel KV (Upstash Redis REST) storage layer for scheduled posts."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

POSTS_KEY = "xauto:posts"


class KVStoreError(Exception):
    """Raised when KV operations fail."""


def _env_value(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def _kv_config() -> tuple[str, str]:
    url = _env_value("KV_REST_API_URL", "xauto_db_KV_REST_API_URL").rstrip("/")
    token = _env_value("KV_REST_API_TOKEN", "xauto_db_KV_REST_API_TOKEN")
    if not url or not token:
        raise KVStoreError(
            "KV_REST_API_URL and KV_REST_API_TOKEN must be configured. "
            "Link a Vercel KV store to this project."
        )
    return url, token


def _request(method: str, path: str, body: bytes | None = None) -> Any:
    base_url, token = _kv_config()
    req = Request(
        f"{base_url}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=10) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise KVStoreError(f"KV HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise KVStoreError(f"KV connection failed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise KVStoreError("KV returned invalid JSON") from exc


def _key_path(key: str) -> str:
    return quote(key, safe="")


def get_all_posts() -> list[dict[str, Any]]:
    payload = _request("GET", f"/get/{_key_path(POSTS_KEY)}")
    result = payload.get("result")
    if result is None:
        return []
    if isinstance(result, str):
        try:
            posts = json.loads(result)
        except json.JSONDecodeError as exc:
            raise KVStoreError("Stored posts payload is not valid JSON") from exc
    elif isinstance(result, list):
        posts = result
    else:
        raise KVStoreError("Stored posts payload has an unexpected shape")

    if not isinstance(posts, list):
        raise KVStoreError("Stored posts payload must be a JSON array")
    return posts


def save_all_posts(posts: list[dict[str, Any]]) -> None:
    encoded = json.dumps(posts, separators=(",", ":"))
    _request("POST", f"/set/{_key_path(POSTS_KEY)}", encoded.encode("utf-8"))


def get_post_by_id(post_id: str) -> dict[str, Any] | None:
    for post in get_all_posts():
        if post.get("id") == post_id:
            return post
    return None


def upsert_post(post: dict[str, Any]) -> dict[str, Any]:
    posts = get_all_posts()
    updated = False
    for index, existing in enumerate(posts):
        if existing.get("id") == post.get("id"):
            posts[index] = post
            updated = True
            break
    if not updated:
        posts.append(post)
    save_all_posts(posts)
    return post


def delete_post(post_id: str) -> bool:
    posts = get_all_posts()
    filtered = [post for post in posts if post.get("id") != post_id]
    if len(filtered) == len(posts):
        return False
    save_all_posts(filtered)
    return True
