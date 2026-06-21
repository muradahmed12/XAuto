#!/usr/bin/env python3
"""Local dev server — runs XAuto without Vercel CLI login."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "api"
sys.path.insert(0, str(API_DIR))


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_env_file(ROOT / ".env.local")
load_env_file(ROOT / ".env")

import generate as generate_api  # noqa: E402
import posts as posts_api  # noqa: E402
import publish as publish_api  # noqa: E402

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".svg": "image/svg+xml",
}


def invoke_api(module: Any, method: str, path: str, headers: dict[str, str], body: bytes) -> tuple[int, bytes, list[tuple[str, str]]]:
    captured: dict[str, Any] = {"status": 200, "headers": [], "body": b""}

    class CapturingHandler(module.handler):
        def setup(self) -> None:
            self.rfile = BytesIO(body)
            self.wfile = BytesIO()

        def send_response(self, code: int, message: str | None = None) -> None:
            captured["status"] = code

        def send_header(self, keyword: str, value: str) -> None:
            captured["headers"].append((keyword, value))

        def end_headers(self) -> None:
            return

        def log_message(self, format: str, *args: Any) -> None:
            return

    handler = CapturingHandler.__new__(CapturingHandler)
    handler.request = None
    handler.client_address = ("127.0.0.1", 0)
    handler.server = None
    handler.setup()
    handler.raw_requestline = f"{method} {path} HTTP/1.1\r\n".encode("utf-8")
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.command = method
    handler.path = path
    handler.request_version = "HTTP/1.1"
    handler.headers = _build_headers(headers, body)

    method_fn = getattr(handler, f"do_{method}", None)
    if method_fn is None:
        handler.send_error(HTTPStatus.METHOD_NOT_ALLOWED)
    else:
        method_fn()

    captured["body"] = handler.wfile.getvalue()
    return captured["status"], captured["body"], captured["headers"]


def _build_headers(headers: dict[str, str], body: bytes):
    from http.client import HTTPMessage

    lines = []
    for key, value in headers.items():
        lines.append(f"{key}: {value}")
    if body:
        lines.append(f"Content-Length: {len(body)}")
    lines.extend(["", ""])
    block = "\r\n".join(lines).encode("utf-8")
    return HTTPMessage(BytesIO(block))


def serve_static(path: str) -> tuple[int, bytes, str]:
    clean = unquote(path.split("?", 1)[0])
    if clean in ("/", ""):
        clean = "/index.html"
    file_path = (ROOT / clean.lstrip("/")).resolve()
    if not str(file_path).startswith(str(ROOT.resolve())):
        return 403, b"Forbidden", "text/plain; charset=utf-8"
    if not file_path.is_file():
        return 404, b"Not Found", "text/plain; charset=utf-8"
    content = file_path.read_bytes()
    mime = MIME_TYPES.get(file_path.suffix.lower(), "application/octet-stream")
    return 200, content, mime


API_ROUTES = {
    "/api/generate": generate_api,
    "/api/posts": posts_api,
    "/api/publish": publish_api,
}


class LocalServerHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[local] {self.address_string()} - {format % args}")

    def _send(self, status: int, body: bytes, content_type: str, extra_headers: list[tuple[str, str]] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        if extra_headers:
            for key, value in extra_headers:
                if key.lower() != "content-type":
                    self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self._send(204, b"", "text/plain; charset=utf-8")

    def _dispatch(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/") or "/"

        if route.startswith("/api/"):
            module = API_ROUTES.get(route)
            if module is None:
                self._send(404, b'{"success":false,"error":"Not found"}', "application/json; charset=utf-8")
                return

            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else b""
            headers = {key: self.headers[key] for key in self.headers}

            status, response_body, response_headers = invoke_api(
                module,
                self.command,
                parsed.path,
                headers,
                body,
            )
            content_type = "application/json; charset=utf-8"
            for key, value in response_headers:
                if key.lower() == "content-type":
                    content_type = value
            self._send(status, response_body, content_type, response_headers)
            return

        status, body, mime = serve_static(parsed.path)
        self._send(status, body, mime)

    do_GET = _dispatch
    do_POST = _dispatch
    do_DELETE = _dispatch


def main() -> None:
    port = int(os.environ.get("PORT", "3000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), LocalServerHandler)
    print(f"XAuto local server running at http://127.0.0.1:{port}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    missing = []
    if not (
        os.environ.get("KV_REST_API_URL")
        or os.environ.get("xauto_db_KV_REST_API_URL")
    ) or not (
        os.environ.get("KV_REST_API_TOKEN")
        or os.environ.get("xauto_db_KV_REST_API_TOKEN")
    ):
        missing.append(
            "KV (link Vercel KV and add KV_REST_API_* or xauto_db_KV_REST_API_* to .env.local)"
        )
    if not os.environ.get("GEMINI_API_KEY"):
        missing.append("GEMINI_API_KEY (needed for Generate Draft)")
    if missing:
        print("\nNote — not yet configured:", flush=True)
        for item in missing:
            print(f"  - {item}", flush=True)
        print(flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
