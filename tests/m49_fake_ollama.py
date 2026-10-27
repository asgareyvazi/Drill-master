"""A scripted stand-in for an EXTERNAL Ollama server, on 127.0.0.1 only.

It isolates the external dependency (the model server) so the adapter's own
logic - URL policy, streaming, errors, cancel, cloud refusal - runs for
real over real HTTP.  It says nothing about model quality.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeOllama:
    def __init__(self, *, models=None, chat_chunks=None, chat_status=200, chat_error=None, tags_body=None,
                 delay_before=0.0, hold_after_first=0.0, embed_dims=4, embed_extra=None, redirect_to=None):
        self.models = models if models is not None else [{"name": "syn-chat:latest"}, {"name": "syn-embed:latest"}]
        self.chat_chunks = chat_chunks if chat_chunks is not None else [
            {"message": {"role": "assistant", "content": "Kick tolerance is 50 bbl "}, "done": False},
            {"message": {"role": "assistant", "content": "[S1]."}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True}]
        self.chat_status, self.chat_error, self.tags_body = chat_status, chat_error, tags_body
        self.delay_before, self.hold_after_first = delay_before, hold_after_first
        self.embed_dims, self.embed_extra, self.redirect_to = embed_dims, embed_extra or {}, redirect_to
        self.requests = []           # (method, path, headers dict, body dict|None)
        self.release = threading.Event()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):     # keep test output clean
                pass

            def _body(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                return json.loads(raw) if raw else None

            def _json(self, status, value):
                data = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                owner.requests.append(("GET", self.path, dict(self.headers), None))
                if owner.redirect_to:
                    self.send_response(302)
                    self.send_header("Location", owner.redirect_to)
                    self.end_headers()
                    return
                if self.path == "/api/version":
                    return self._json(200, {"version": "0.0.0-synthetic"})
                if self.path == "/api/tags":
                    if owner.tags_body is not None:
                        data = owner.tags_body.encode()
                        self.send_response(200)
                        self.send_header("Content-Length", str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                        return
                    return self._json(200, {"models": owner.models})
                return self._json(404, {"error": "not found"})

            def do_POST(self):
                body = self._body()
                owner.requests.append(("POST", self.path, dict(self.headers), body))
                if owner.delay_before:
                    time.sleep(owner.delay_before)
                if self.path == "/api/embed":
                    texts = body.get("input") or []
                    vectors = [[float((hash(t) >> i) % 7) + 1.0 for i in range(owner.embed_dims)] for t in texts]
                    return self._json(200, {"model": body.get("model"), "embeddings": vectors, **owner.embed_extra})
                if self.path != "/api/chat":
                    return self._json(404, {"error": "not found"})
                if owner.chat_status != 200:
                    return self._json(owner.chat_status, {"error": owner.chat_error or "failure"})
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                for index, chunk in enumerate(owner.chat_chunks):
                    line = chunk if isinstance(chunk, str) else json.dumps(chunk)
                    try:
                        self.wfile.write(line.encode() + b"\n")
                        self.wfile.flush()
                    except OSError:
                        return
                    if index == 0 and owner.hold_after_first:
                        owner.release.wait(owner.hold_after_first)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()

    def paths(self):
        return [path for _method, path, _headers, _body in self.requests]
