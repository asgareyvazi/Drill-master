"""M49 - the local model adapter: loopback only, no cloud models, explicit states.

The model server is the scripted stand-in in tests/m49_fake_ollama.py
(an external dependency); every rule of core/local_llm.py runs for real.
"""
from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import local_llm as ll  # noqa: E402
from m49_fake_ollama import FakeOllama  # noqa: E402


def _closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ------------------------------------------------------------- URL policy
@pytest.mark.parametrize("url, expected", [
    ("http://127.0.0.1:11434", "http://127.0.0.1:11434"),
    ("http://127.0.0.1:11434/", "http://127.0.0.1:11434"),
    ("http://[::1]:11434", "http://[::1]:11434"),
    ("HTTP://LOCALHOST:8080", "http://localhost:8080"),
])
def test_loopback_urls_are_accepted(url, expected):
    assert ll.validate_loopback_url(url) == expected


@pytest.mark.parametrize("url", [
    "http://10.0.0.5:11434", "http://192.168.1.2:11434", "http://0.0.0.0:11434", "http://ollama.com",
    "https://ollama.com/api", "http://127.0.0.1.nip.io:11434", "http://localhost.example.com:11434",
    "http://user:pw@localhost:11434", "http://127.0.0.1@evil.example.invalid:80", "ftp://127.0.0.1:11434",
    "file:///etc/passwd", "http://[::ffff:7f00:1]:11434", "http://127.0.0.2:11434", "http://127.0.0.1:11434/v1",
    "http://127.0.0.1:99999", "", "127.0.0.1:11434",
])
def test_remote_or_odd_urls_are_rejected_before_any_connection(url, monkeypatch):
    def no_socket(*a, **k):
        raise AssertionError("a socket was opened for a rejected URL")
    monkeypatch.setattr(socket, "create_connection", no_socket)
    with pytest.raises(ll.LocalLLMError) as info:
        ll.validate_loopback_url(url)
    assert info.value.state == ll.INVALID_URL
    adapter = ll.OllamaAdapter(url, "syn-chat")
    status = adapter.status()
    assert status.state == ll.INVALID_URL and not status.chat_ready


def test_localhost_that_resolves_to_a_remote_address_is_rejected(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port: [(2, 1, 6, "", ("203.0.113.9", 0))])
    with pytest.raises(ll.LocalLLMError) as info:
        ll.validate_loopback_url("http://localhost:11434")
    assert info.value.state == ll.INVALID_URL


def test_environment_url_is_validated_too(monkeypatch):
    monkeypatch.setenv(ll.ENV_URL, "http://203.0.113.9:11434")
    adapter = ll.OllamaAdapter(chat_model="syn-chat")
    assert adapter.base_url is None and adapter.status().state == ll.INVALID_URL


# ----------------------------------------------------------------- status
def test_status_ready_lists_local_models_only():
    with FakeOllama(models=[{"name": "syn-chat:latest"}, {"name": "big:cloud"},
                            {"name": "relay:latest", "remote_host": "https://ollama.com:443"}]) as fake:
        status = ll.OllamaAdapter(fake.url, "syn-chat", "syn-embed").status()
    assert status.state == ll.READY and status.chat_ready
    assert status.local_models == ["syn-chat:latest"]
    assert status.rejected_models == ["big:cloud", "relay:latest"]
    assert status.embed_state == ll.MODEL_MISSING


@pytest.mark.parametrize("model, state", [
    ("", ll.NOT_CONFIGURED), ("absent-model", ll.MODEL_MISSING), ("big:cloud", ll.REMOTE_REJECTED),
    ("gpt-oss:120b-cloud", ll.REMOTE_REJECTED), ("relay", ll.REMOTE_REJECTED)])
def test_status_states_for_the_chosen_model(model, state):
    with FakeOllama(models=[{"name": "syn-chat:latest"}, {"name": "big:cloud"},
                            {"name": "relay:latest", "remote_model": "x"}]) as fake:
        status = ll.OllamaAdapter(fake.url, model).status()
    assert status.state == state and not status.chat_ready
    assert status.message


def test_status_when_nothing_listens_is_not_running():
    status = ll.OllamaAdapter(f"http://127.0.0.1:{_closed_port()}", "syn-chat", connect_timeout=1).status()
    assert status.state == ll.NOT_RUNNING and "No local model server" in status.message


def test_malformed_model_list_is_a_protocol_error():
    with FakeOllama(tags_body="this is not json") as fake:
        assert ll.OllamaAdapter(fake.url, "syn-chat").status().state == ll.PROTOCOL_ERROR


def test_proxy_environment_is_ignored(monkeypatch):
    dead = f"http://127.0.0.1:{_closed_port()}"
    for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, dead)
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    with FakeOllama() as fake:
        assert ll.OllamaAdapter(fake.url, "syn-chat").status().state == ll.READY


def test_redirects_are_refused_not_followed():
    with FakeOllama(redirect_to="http://203.0.113.9/api/tags") as fake:
        status = ll.OllamaAdapter(fake.url, "syn-chat").status()
        assert status.state == ll.PROTOCOL_ERROR and "redirect" in status.message
        assert fake.paths() == ["/api/version"]


def test_management_endpoints_are_never_called():
    with FakeOllama() as fake:
        adapter = ll.OllamaAdapter(fake.url, "syn-chat")
        for path in ("/api/pull", "/api/push", "/api/create", "/api/delete", "/api/copy"):
            with pytest.raises(ll.LocalLLMError):
                adapter._request(path, {"model": "x"}, 1)
        assert fake.requests == []


# ------------------------------------------------------------------- chat
def test_chat_streams_and_sends_no_tools_and_no_key():
    with FakeOllama() as fake:
        tokens = []
        text = ll.OllamaAdapter(fake.url, "syn-chat").chat([{"role": "user", "content": "q"}], on_token=tokens.append)
        (method, path, headers, body), = [r for r in fake.requests if r[1] == "/api/chat"]
    assert text == "Kick tolerance is 50 bbl [S1]." and "".join(tokens) == text
    assert (method, body["model"], body["stream"]) == ("POST", "syn-chat", True)
    assert "tools" not in body and "format" not in body
    assert not any(h.lower() == "authorization" for h in headers)


@pytest.mark.parametrize("chunks, state", [
    ([{"message": {"content": "x"}, "done": False, "remote_host": "https://ollama.com:443"}], ll.REMOTE_REJECTED),
    ([{"error": "model crashed"}], ll.SERVER_ERROR),
    ([{"message": {"content": "", "tool_calls": [{"function": {"name": "shell"}}]}, "done": False}], ll.PROTOCOL_ERROR),
    (["not json at all"], ll.PROTOCOL_ERROR),
    ([{"message": {"content": "partial"}, "done": False}], ll.PROTOCOL_ERROR),   # stream ends early
])
def test_chat_failures_are_states_never_empty_answers(chunks, state):
    with FakeOllama(chat_chunks=chunks) as fake:
        with pytest.raises(ll.LocalLLMError) as info:
            ll.OllamaAdapter(fake.url, "syn-chat").chat([{"role": "user", "content": "q"}])
    assert info.value.state == state


def test_a_tool_call_is_refused_even_when_the_stream_then_completes():
    """The tool-call guard itself must fire - not just a later protocol error
    from an unfinished stream."""
    chunks = [{"message": {"content": "", "tool_calls": [{"function": {"name": "shell"}}]}, "done": False},
              {"message": {"content": "Kick tolerance is 50 bbl [S1]."}, "done": False},
              {"message": {"content": ""}, "done": True}]
    with FakeOllama(chat_chunks=chunks) as fake:
        with pytest.raises(ll.LocalLLMError) as info:
            ll.OllamaAdapter(fake.url, "syn-chat").chat([{"role": "user", "content": "q"}])
    assert info.value.state == ll.PROTOCOL_ERROR and "tool" in str(info.value)


def test_missing_model_on_chat_is_model_missing():
    with FakeOllama(chat_status=404, chat_error="model 'syn-chat' not found") as fake:
        with pytest.raises(ll.LocalLLMError) as info:
            ll.OllamaAdapter(fake.url, "syn-chat").chat([{"role": "user", "content": "q"}])
    assert info.value.state == ll.MODEL_MISSING


def test_cloud_model_name_is_refused_without_a_request():
    with FakeOllama() as fake:
        with pytest.raises(ll.LocalLLMError) as info:
            ll.OllamaAdapter(fake.url, "gemma4:cloud").chat([{"role": "user", "content": "q"}])
        assert info.value.state == ll.REMOTE_REJECTED and fake.requests == []


def test_slow_server_times_out():
    with FakeOllama(delay_before=2.0) as fake:
        adapter = ll.OllamaAdapter(fake.url, "syn-chat", read_timeout=0.5)
        started = time.monotonic()
        with pytest.raises(ll.LocalLLMError) as info:
            adapter.chat([{"role": "user", "content": "q"}])
    assert info.value.state == ll.TIMEOUT and time.monotonic() - started < 1.9


def test_cancel_interrupts_a_stream_that_is_waiting():
    with FakeOllama(hold_after_first=10.0) as fake:
        adapter = ll.OllamaAdapter(fake.url, "syn-chat", read_timeout=30)
        token = ll.CancelToken()
        outcome = {}

        def run():
            try:
                adapter.chat([{"role": "user", "content": "q"}], token)
            except ll.LocalLLMError as exc:
                outcome["state"] = exc.state

        worker = threading.Thread(target=run)
        worker.start()
        time.sleep(0.4)
        started = time.monotonic()
        token.cancel()
        worker.join(5)
    assert not worker.is_alive() and outcome.get("state") == ll.CANCELLED
    assert time.monotonic() - started < 2.0


# -------------------------------------------------------------- embedding
def test_embed_returns_vectors_and_refuses_remote_results():
    with FakeOllama(embed_dims=6) as fake:
        vectors = ll.OllamaAdapter(fake.url, embed_model="syn-embed").embed(["a", "b"])
    assert len(vectors) == 2 and {len(v) for v in vectors} == {6}
    with FakeOllama(embed_extra={"remote_host": "https://ollama.com:443"}) as fake:
        with pytest.raises(ll.LocalLLMError) as info:
            ll.OllamaAdapter(fake.url, embed_model="syn-embed").embed(["a"])
    assert info.value.state == ll.REMOTE_REJECTED


def test_every_connection_goes_to_loopback(monkeypatch):
    seen = []
    real_connect = socket.socket.connect

    def recording_connect(self, address):
        seen.append(address[0])
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", recording_connect)
    with FakeOllama() as fake:
        adapter = ll.OllamaAdapter(fake.url, "syn-chat", "syn-embed")
        adapter.status()
        adapter.chat([{"role": "user", "content": "q"}])
        adapter.embed(["x"])
    assert seen and all(address in ("127.0.0.1", "::1") for address in seen)
