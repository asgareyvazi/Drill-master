"""M50 §7: the legacy AI import mapper keeps workbook cells on this computer.

Audit findings fixed here (before M50 the mapper accepted any
DRILLMASTER_OLLAMA_URL, followed redirects and proxies, listed and used Ollama
cloud models, and its catalog offered two cloud models and the
non-commercial ``qwen2.5:3b``).

The HTTP server below is a FAKE stand-in for Ollama on 127.0.0.1 - it isolates
the external service to test the transport policy only and says nothing about
model quality (no real model was run: NOT RUN, no local model installed).
Synthetic workbook context only.
"""
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from core import ai_import_mapper as aim
from core.local_llm import is_remote_model

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = {"sheet": "SYN", "cells": [{"row": 3, "column": "B", "text": "Depth (m)", "value": 1234.5}]}
PROPOSAL = {"field": sorted(aim.ALLOWED_FIELDS)[0], "source_sheet": "SYN", "source_row": 3, "source_column": "B",
            "value": 1234.5, "confidence": 0.9}


class FakeOllama:
    """Loopback stand-in: records every request path; serves a scripted model list."""

    def __init__(self, models, redirect_to=None):
        self.models, self.redirect_to, self.paths = models, redirect_to, []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, code, payload, headers=()):
                body = json.dumps(payload).encode()
                self.send_response(code)
                for key, value in headers:
                    self.send_header(key, value)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                owner.paths.append(self.path)
                if owner.redirect_to:
                    self._reply(302, {}, [("Location", owner.redirect_to)])
                else:
                    self._reply(200, {"models": owner.models})

            def do_POST(self):
                owner.paths.append(self.path)
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                self._reply(200, {"response": json.dumps({"proposals": [PROPOSAL]})})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("DRILLMASTER_AI_IMPORT", "1")
    monkeypatch.delenv("DRILLMASTER_AI_MODEL", raising=False)
    monkeypatch.setattr(aim, "get_selected_model", lambda: "")


@pytest.fixture
def server():
    servers = []

    def make(models, **kwargs):
        servers.append(FakeOllama(models, **kwargs))
        return servers[-1]
    yield make
    for s in servers:
        s.close()


@pytest.mark.parametrize("url", ["http://10.1.2.3:11434", "http://ollama.example.invalid:11434",
                                 "http://someone@[::1]:11434", "ftp://127.0.0.1:11434"])
def test_non_loopback_endpoint_is_never_contacted(enabled, monkeypatch, url):
    opened = []
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", lambda self, *a, **k: opened.append(a))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: opened.append(a))
    mapper = aim.AIImportMapper(endpoint=url, model="qwen2.5:7b-instruct")
    assert mapper.endpoint is None and mapper.endpoint_error
    assert mapper.installed_models() == [] and mapper.last_status == "invalid-url"
    assert mapper.map_context(CONTEXT) == [] and mapper.last_status == "invalid-url"
    assert opened == []


def test_environment_endpoint_is_validated_too(enabled, monkeypatch):
    monkeypatch.setenv("DRILLMASTER_OLLAMA_URL", "http://192.0.2.10:11434")
    mapper = aim.AIImportMapper(model="qwen2.5:7b-instruct")
    assert mapper.endpoint is None and not mapper.available() and mapper.last_status == "invalid-url"


@pytest.mark.parametrize("model", ["kimi-k2.6:cloud", "minimax-m2.7:cloud", "gpt-oss:120b-cloud"])
def test_cloud_model_is_not_listed_and_never_receives_workbook_cells(enabled, server, model):
    fake = server([{"name": model}, {"name": "qwen2.5:7b-instruct"}])
    mapper = aim.AIImportMapper(endpoint=fake.url, model=model)
    assert mapper.installed_models() == ["qwen2.5:7b-instruct"] and mapper.rejected_models == [model]
    assert mapper.map_context(CONTEXT) == [] and mapper.last_status == "remote-rejected"
    assert "/api/generate" not in fake.paths


def test_cloud_selection_is_refused_before_any_request(enabled, server):
    fake = server([])
    mapper = aim.AIImportMapper(endpoint=fake.url, model="kimi-k2.6:cloud")
    assert not mapper.available() and mapper.last_status == "remote-rejected"
    assert fake.paths == []


def test_model_reported_remote_by_ollama_is_refused_whatever_its_name(enabled, server):
    fake = server([{"name": "qwen2.5:7b-instruct", "remote_host": "https://ollama.com:443"}])
    mapper = aim.AIImportMapper(endpoint=fake.url, model="qwen2.5:7b-instruct")
    assert mapper.installed_models() == []
    assert mapper.map_context(CONTEXT) == [] and mapper.last_status == "remote-rejected"
    assert "/api/generate" not in fake.paths


def test_local_model_maps_on_loopback_only(enabled, server):
    fake = server([{"name": "qwen2.5:7b-instruct"}])
    mapper = aim.AIImportMapper(endpoint=fake.url, model="qwen2.5:7b-instruct")
    assert mapper.map_context(CONTEXT) == [PROPOSAL] and mapper.last_status == "ok:1"
    assert fake.paths == ["/api/tags", "/api/generate"]


def test_redirect_is_refused_not_followed(enabled, server):
    elsewhere = server([{"name": "qwen2.5:7b-instruct"}])
    fake = server([], redirect_to=elsewhere.url + "/api/tags")
    mapper = aim.AIImportMapper(endpoint=fake.url, model="qwen2.5:7b-instruct")
    assert mapper.installed_models() == [] and mapper.last_status == "ollama-unavailable"
    assert elsewhere.paths == []


def test_proxy_environment_is_ignored(enabled, server, monkeypatch):
    proxy = server([{"name": "qwen2.5:7b-instruct"}])
    fake = server([{"name": "qwen2.5:7b-instruct"}])
    for name in ("HTTP_PROXY", "http_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, proxy.url)
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setattr(urllib.request, "_opener", None)   # urlopen caches its proxy settings at first use
    mapper = aim.AIImportMapper(endpoint=fake.url, model="qwen2.5:7b-instruct")
    assert mapper.installed_models() == ["qwen2.5:7b-instruct"]
    assert proxy.paths == [] and fake.paths == ["/api/tags"]


def test_unreachable_server_is_reported_as_such_not_as_a_missing_model(enabled):
    mapper = aim.AIImportMapper(endpoint="http://127.0.0.1:9", model="qwen2.5:7b-instruct")
    assert not mapper.available() and mapper.last_status == "ollama-unavailable"


def test_disabled_by_default_makes_no_request(monkeypatch):
    monkeypatch.delenv("DRILLMASTER_AI_IMPORT", raising=False)
    opened = []
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", lambda self, *a, **k: opened.append(a))
    mapper = aim.AIImportMapper(model="qwen2.5:7b-instruct")
    assert mapper.installed_models() == [] and mapper.map_context(CONTEXT) == [] and opened == []
    assert mapper.last_status == "disabled"


def test_catalog_offers_no_cloud_model_and_not_the_non_commercial_3b():
    catalog = aim.model_catalog()
    assert catalog, "the catalog must still load"
    names = {entry["model"] for entry in catalog}
    assert "qwen2.5:3b" not in names and "qwen2.5:72b" not in names
    for entry in catalog:
        assert not is_remote_model({"name": entry["model"]}), entry["model"]
        assert entry.get("licence"), entry["model"]
        assert "recommended" not in entry.get("description", "").lower()


def test_deployment_guide_does_not_suggest_the_3b_model():
    text = (ROOT / "DEPLOYMENT.md").read_text(encoding="utf-8")
    assert 'DRILLMASTER_AI_MODEL = "qwen2.5:3b"' not in text
    assert "loopback" in text and "cloud" in text
