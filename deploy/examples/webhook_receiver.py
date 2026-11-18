#!/usr/bin/env python3
"""Reference webhook receiver for the CRM (API spec 19.6). Standard library only.

It shows what every consumer must do with a delivery:

1. Recompute the signature: hex HMAC-SHA256 of "<t>.<raw body>" with the
   subscription's secret, compared in constant time with each `v1=` value of
   `X-CRM-Signature` (two values for 24 hours after a secret rotation).
2. Reject timestamps older than 5 minutes (replays).
3. Deduplicate on the event `id`: delivery is at least once.
4. Answer 2xx quickly (within 10 seconds) and do the real work afterwards.

Run (the secret comes from the environment, never the command line):

    WEBHOOK_SECRET=whsec_... python3 webhook_receiver.py --port 8443 \\
        --tls-cert cert.pem --tls-key key.pem

Several secrets may be given, comma-separated. Verified events are printed as JSON
lines. Without --tls-cert the server speaks plain HTTP, which the CRM accepts only
outside production.
"""

import argparse
import hashlib
import hmac
import json
import os
import ssl
import sys
import threading
import time
from collections.abc import Callable, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

TOLERANCE_SECONDS = 300
MAX_BODY_BYTES = 1_000_000


def verify_signature(
    secrets: Sequence[str],
    header: str,
    body: bytes,
    now: float | None = None,
    tolerance: int = TOLERANCE_SECONDS,
) -> bool:
    """True when the header carries a fresh timestamp and a signature made with one of
    `secrets` over this exact body."""
    timestamp: int | None = None
    signatures: list[str] = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t" and value.isdigit():
            timestamp = int(value)
        elif key == "v1":
            signatures.append(value)
    if timestamp is None or not signatures:
        return False
    if abs((time.time() if now is None else now) - timestamp) > tolerance:
        return False
    message = f"{timestamp}.".encode() + body
    for secret in secrets:
        expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
        if any(hmac.compare_digest(expected, s) for s in signatures):
            return True
    return False


class _Seen:
    """Event IDs already handled (in memory; use a database table in production)."""

    def __init__(self, limit: int = 10_000) -> None:
        self._ids: dict[str, None] = {}
        self._limit = limit
        self._lock = threading.Lock()

    def first_time(self, event_id: str) -> bool:
        with self._lock:
            if event_id in self._ids:
                return False
            self._ids[event_id] = None
            if len(self._ids) > self._limit:
                self._ids.pop(next(iter(self._ids)))
            return True


def make_server(
    host: str,
    port: int,
    secrets: Sequence[str],
    on_event: Callable[[dict[str, Any]], None],
) -> ThreadingHTTPServer:
    """An HTTP server that verifies deliveries and calls `on_event` once per event."""
    seen = _Seen()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                self._reply(413)
                return
            body = self.rfile.read(length)
            if not verify_signature(secrets, self.headers.get("X-CRM-Signature", ""), body):
                self._reply(401)
                return
            try:
                event = json.loads(body)
            except ValueError:
                self._reply(400)
                return
            if seen.first_time(str(event.get("id"))):
                on_event(event)
            self._reply(204)

        def _reply(self, status: int) -> None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib name
            sys.stderr.write(f"{self.address_string()} {format % args}\n")

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104 - a server for other hosts
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--tls-cert", help="PEM certificate (chain) for HTTPS")
    parser.add_argument("--tls-key", help="PEM private key for HTTPS")
    args = parser.parse_args()
    secrets = [s for s in os.environ.get("WEBHOOK_SECRET", "").split(",") if s]
    if not secrets:
        parser.error("set WEBHOOK_SECRET (comma-separated during a rotation)")

    def print_event(event: dict[str, Any]) -> None:
        print(json.dumps(event, ensure_ascii=False), flush=True)  # noqa: T201

    server = make_server(args.host, args.port, secrets, print_event)
    if args.tls_cert:
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(args.tls_cert, args.tls_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    sys.stderr.write(f"Listening on {args.host}:{args.port}\n")
    server.serve_forever()


if __name__ == "__main__":
    main()
