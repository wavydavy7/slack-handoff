#!/usr/bin/env python3
"""Local server for the Slack handoff app.

Serves the UI and a tiny file-based bridge:
  POST /api/request        -> appends a JSON line to bridge/requests.jsonl
  GET  /api/response/<id>  -> returns bridge/responses/<id>.json when ready

Claude (running in the companion session) watches requests.jsonl, does the
Slack search / drafting / sending, and writes the response file.
"""
import hashlib
import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = os.path.join(BASE, "bridge")
RESPONSES = os.path.join(BRIDGE, "responses")
REQUESTS = os.path.join(BRIDGE, "requests.jsonl")
KEYS = os.path.join(BRIDGE, "keys.jsonl")
os.makedirs(RESPONSES, exist_ok=True)

PORT = 8931

# Read-only request types are answered from cache when an identical request was
# already answered, so repeats (double-clicks, page reloads) resolve instantly
# instead of waiting on a fresh Claude round trip. Sends always go to Claude.
CACHEABLE = ("prepare", "lookup")


def _cache_key(req):
    payload = {"type": req.get("type"), "payload": req.get("payload")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def _cached_response(key):
    if not os.path.exists(KEYS):
        return None
    with open(KEYS) as f:
        entries = [json.loads(line) for line in f if line.strip()]
    for entry in reversed(entries):
        if entry["key"] != key:
            continue
        path = os.path.join(RESPONSES, entry["id"] + ".json")
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    return None


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(BASE, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif self.path.startswith("/api/response/"):
            rid = "".join(c for c in self.path.rsplit("/", 1)[1] if c.isalnum())
            path = os.path.join(RESPONSES, rid + ".json")
            if os.path.exists(path):
                with open(path, "rb") as f:
                    self._send(200, f.read())
            else:
                self._send(202, {"status": "pending"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/api/request":
            try:
                n = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(n))
            except (ValueError, json.JSONDecodeError):
                self._send(400, {"error": "bad json"})
                return
            rid = uuid.uuid4().hex[:12]
            req["id"] = rid
            req["ts"] = time.time()
            if req.get("type") in CACHEABLE:
                key = _cache_key(req)
                cached = _cached_response(key)
                if cached is not None:
                    cached["id"] = rid
                    with open(os.path.join(RESPONSES, rid + ".json"), "w") as f:
                        json.dump(cached, f)
                    self._send(200, {"id": rid})
                    return
                with open(KEYS, "a") as f:
                    f.write(json.dumps({"id": rid, "key": key}) + "\n")
            with open(REQUESTS, "a") as f:
                f.write(json.dumps(req) + "\n")
            self._send(200, {"id": rid})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"handoff-app serving on http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
