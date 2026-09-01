#!/usr/bin/env python3
"""Local server for the Slack handoff app.

Serves the UI and a tiny file-based bridge:
  POST /api/request        -> appends a JSON line to bridge/requests.jsonl
  GET  /api/response/<id>  -> returns bridge/responses/<id>.json when ready

Claude (running in the companion session) watches requests.jsonl, does the
Slack search / drafting / sending, and writes the response file.
"""
import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = os.path.join(BASE, "bridge")
RESPONSES = os.path.join(BRIDGE, "responses")
REQUESTS = os.path.join(BRIDGE, "requests.jsonl")
os.makedirs(RESPONSES, exist_ok=True)

PORT = 8931


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
