"""Adapter for a LOCAL Ollama server (M49 Knowledge Assistant).

Nothing here is required: the Knowledge Assistant answers extractively from
the reviewed document pages when no model is available.  When a model is
used, these rules hold (each one has a test in tests/test_m49_local_llm.py):

* loopback only - the base URL must be ``http(s)://127.0.0.1|localhost|[::1]``
  (``localhost`` must also *resolve* to loopback addresses only); anything
  else is rejected before a socket is opened;
* no proxy (``HTTP_PROXY`` & co. are ignored) and no redirect is followed,
  so a local server cannot bounce a request to another host;
* only the read/inference endpoints are reachable (``/api/version``,
  ``/api/tags``, ``/api/show``, ``/api/chat``, ``/api/embed``) - never
  ``/api/pull``, ``/api/push``, ``/api/create``, ``/api/delete``: the
  application never downloads or changes models;
* Ollama "cloud models" are refused: a local Ollama can forward a model to
  ollama.com (``/api/tags`` then shows ``remote_host``/``remote_model``,
  the tag is ``cloud`` or ``*-cloud``).  Such models are listed as rejected
  and a streamed response that reports a ``remote_host`` is aborted;
* no API key, no ``tools`` field, no ``format`` - the model only returns text;
* every failure is an exception with a state (``not_running``,
  ``model_missing``, ``timeout``, ``cancelled``, ...) - never an empty answer.

Ollama API reference: docs/api.md of github.com/ollama/ollama (tag v0.40.11):
``POST /api/chat`` streams NDJSON objects ``{"message": {"content": ...},
"done": bool}``; errors are ``{"error": "..."}`` with a 4xx/5xx status.
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Optional

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
ENV_URL = "DRILLMASTER_OLLAMA_URL"
ENV_CHAT_MODEL = "DRILLMASTER_LLM_MODEL"
ENV_EMBED_MODEL = "DRILLMASTER_EMBED_MODEL"

LOOPBACK_NAMES = frozenset({"127.0.0.1", "localhost", "::1"})
ALLOWED_PATHS = frozenset({"/api/version", "/api/tags", "/api/show", "/api/chat", "/api/embed"})
MAX_RESPONSE_BYTES = 2 * 1024 * 1024          # one answer / one model list
MAX_ANSWER_CHARS = 8000

# States shown by the UI.  Each has its own message; none means "no answer".
READY = "ready"
NOT_CONFIGURED = "not_configured"      # no model name chosen
NOT_RUNNING = "not_running"            # nothing answers on the loopback port
MODEL_MISSING = "model_missing"        # server runs, model not installed locally
REMOTE_REJECTED = "remote_rejected"    # the chosen model would run off this computer
INVALID_URL = "invalid_url"            # non-loopback / malformed endpoint
TIMEOUT = "timeout"
CANCELLED = "cancelled"
PROTOCOL_ERROR = "protocol_error"      # unexpected / malformed response
SERVER_ERROR = "server_error"          # {"error": ...} from the server

SETUP_GUIDANCE = (
    "Optional: install Ollama yourself (https://ollama.com, MIT licence), start it, pull a model "
    "whose weights licence you have checked (for example `ollama pull qwen2.5:1.5b`, Apache-2.0 weights; "
    "licences differ even within one family - qwen2.5:3b is research-only), set "
    "OLLAMA_NO_CLOUD=1 so it can only run local models, then press 'Check model'. "
    "Drill Master never downloads models and only talks to 127.0.0.1/localhost.")


class LocalLLMError(RuntimeError):
    """A failure with a UI state; the message never contains document text."""

    def __init__(self, state: str, message: str):
        super().__init__(message)
        self.state = state


def validate_loopback_url(url: str) -> str:
    """Return the normalised base URL or raise ``LocalLLMError(INVALID_URL)``."""
    try:
        parts = urllib.parse.urlsplit((url or "").strip())
        port = parts.port
    except ValueError as exc:
        raise LocalLLMError(INVALID_URL, f"Malformed model URL ({exc})") from None
    if parts.scheme not in ("http", "https"):
        raise LocalLLMError(INVALID_URL, "The model URL must start with http:// or https://")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise LocalLLMError(INVALID_URL, "The model URL must not contain a user name or password")
    host = (parts.hostname or "").lower()
    if host not in LOOPBACK_NAMES:
        raise LocalLLMError(INVALID_URL, "Only a model on this computer is allowed "
                                         "(127.0.0.1, localhost or [::1]); remote hosts are rejected")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise LocalLLMError(INVALID_URL, "Give only the server address, e.g. http://127.0.0.1:11434")
    if host == "localhost":
        _require_loopback_resolution(host)
    netloc = f"[{host}]" if ":" in host else host
    return f"{parts.scheme}://{netloc}" + (f":{port}" if port else "")


def _require_loopback_resolution(host: str) -> None:
    """``localhost`` can be redefined in the hosts file; every address must be loopback."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise LocalLLMError(INVALID_URL, f"'{host}' does not resolve ({type(exc).__name__})") from None
    addresses = {info[4][0].split("%", 1)[0] for info in infos}
    if not addresses or not all(ipaddress.ip_address(a).is_loopback for a in addresses):
        raise LocalLLMError(INVALID_URL, f"'{host}' resolves to a non-loopback address; use 127.0.0.1")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LocalLLMError(PROTOCOL_ERROR, "The model server tried to redirect the request; refused")


def is_remote_model(entry: dict) -> bool:
    """True for an Ollama model that runs off this computer (cloud/remote)."""
    if not isinstance(entry, dict):
        return True
    if entry.get("remote_host") or entry.get("remote_model"):
        return True
    name = str(entry.get("name") or entry.get("model") or "")
    tag = name.rsplit(":", 1)[1] if ":" in name else ""
    return tag == "cloud" or tag.endswith("-cloud")


@dataclass
class ModelStatus:
    state: str
    message: str
    server_version: Optional[str] = None
    chat_model: Optional[str] = None
    embed_model: Optional[str] = None
    embed_state: str = NOT_CONFIGURED
    local_models: list = field(default_factory=list)
    rejected_models: list = field(default_factory=list)

    @property
    def chat_ready(self) -> bool:
        return self.state == READY

    @property
    def embed_ready(self) -> bool:
        return self.embed_state == READY


class CancelToken:
    """Set from the UI thread; aborts a streaming read in the worker thread."""

    def __init__(self):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._response = None

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            response = self._response
        if response is not None:
            _abort_response(response)

    def _attach(self, response) -> None:
        with self._lock:
            self._response = response
        if self._event.is_set():
            _abort_response(response)

    def _detach(self) -> None:
        with self._lock:
            self._response = None


def _abort_response(response) -> None:
    """Unblock a read in another thread without ever waiting for that thread.

    Called from the UI thread.  It must not touch the ``http.client``
    response: closing it needs the buffered reader's lock, which the reading
    worker holds while it is blocked - on Windows that froze the caller until
    the server sent more data (M49 Windows CI, ~10 s).  Only the OS socket is
    used: ``shutdown`` wakes a blocked read on Linux/macOS but not on Windows;
    closing the socket handle wakes it on Windows (Winsock: a blocking call -
    including ``select`` - outstanding on a socket closed by another thread
    fails with WSAEINTR).  The handle is detached first, so the Python socket
    object holds -1 and can never reach a reused handle.  The worker then
    fails its read, sees the token and reports CANCELLED, and closes the
    response itself in its ``finally``.
    """
    try:
        sock = response.fp.raw._sock  # http.client response -> socket.SocketIO -> socket
    except AttributeError:  # silent-ok: response already closed (fp is None); nothing is blocked on it
        return
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:  # silent-ok: best-effort shutdown; the socket may already be closed or reset
        pass
    try:
        handle = sock.detach()
    except OSError:  # silent-ok: already closed; detach has nothing to hand over
        return
    if handle is not None and handle >= 0:
        try:
            socket.close(handle)
        except OSError:  # silent-ok: the handle was already released by the peer reset; nothing left to close
            pass


class OllamaAdapter:
    """Talks to one loopback Ollama server.  Thread-safe for one call at a time per token."""

    def __init__(self, base_url: Optional[str] = None, chat_model: Optional[str] = None,
                 embed_model: Optional[str] = None, *, connect_timeout: float = 3.0,
                 request_timeout: float = 180.0, read_timeout: float = 60.0):
        raw_url = base_url if base_url is not None else os.environ.get(ENV_URL, DEFAULT_BASE_URL)
        self.url_error = None
        try:
            self.base_url = validate_loopback_url(raw_url)
        except LocalLLMError as exc:
            self.base_url, self.url_error = None, str(exc)
        self.chat_model = (chat_model if chat_model is not None else os.environ.get(ENV_CHAT_MODEL, "")).strip()
        self.embed_model = (embed_model if embed_model is not None else os.environ.get(ENV_EMBED_MODEL, "")).strip()
        self.connect_timeout = connect_timeout
        self.request_timeout = request_timeout
        self.read_timeout = read_timeout
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    # ----------------------------------------------------------- transport
    def _request(self, path: str, payload: Optional[dict], timeout: float):
        if self.base_url is None:
            raise LocalLLMError(INVALID_URL, self.url_error or "No model URL")
        if path not in ALLOWED_PATHS:
            raise LocalLLMError(PROTOCOL_ERROR, f"Endpoint {path} is not allowed")
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(self.base_url + path, data=data, method="GET" if data is None else "POST",
                                         headers={"Content-Type": "application/json"})
        try:
            return self._opener.open(request, timeout=timeout)
        except LocalLLMError:
            raise
        except urllib.error.HTTPError as exc:
            raise LocalLLMError(*_http_error_state(exc)) from None
        except (urllib.error.URLError, ConnectionError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, (socket.timeout, TimeoutError)):
                # urllib wraps only connect/send errors in URLError.  The host
                # is always loopback, where a listening server - even a hung
                # one - is accepted by the kernel at once; a connection not
                # accepted in time means nothing listens (Windows retries the
                # SYN to a closed port for ~2 s instead of refusing at once).
                raise LocalLLMError(NOT_RUNNING, f"No local model server accepted a connection at {self.base_url} "
                                                 f"within {timeout:g} s") from None
            raise LocalLLMError(NOT_RUNNING, "No local model server is running at "
                                             f"{self.base_url} ({type(reason).__name__})") from None
        except (socket.timeout, TimeoutError):
            raise LocalLLMError(TIMEOUT, "The local model server did not answer in time") from None

    def _get_json(self, path: str, payload: Optional[dict] = None, timeout: Optional[float] = None) -> dict:
        response = self._request(path, payload, timeout or self.connect_timeout)
        try:
            body = response.read(MAX_RESPONSE_BYTES + 1)
        except (socket.timeout, TimeoutError):
            raise LocalLLMError(TIMEOUT, "The local model server did not answer in time") from None
        except OSError as exc:
            raise LocalLLMError(PROTOCOL_ERROR, f"Reading the model server response failed ({type(exc).__name__})") \
                from None
        finally:
            response.close()
        if len(body) > MAX_RESPONSE_BYTES:
            raise LocalLLMError(PROTOCOL_ERROR, "The model server response is too large")
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise LocalLLMError(PROTOCOL_ERROR, "The model server returned something that is not JSON") from None
        if not isinstance(value, dict):
            raise LocalLLMError(PROTOCOL_ERROR, "Unexpected response from the model server")
        if value.get("error"):
            raise LocalLLMError(SERVER_ERROR, f"Model server error: {str(value['error'])[:200]}")
        return value

    # -------------------------------------------------------------- status
    def status(self) -> ModelStatus:
        """Probe the server and the configured models; never raises."""
        if self.base_url is None:
            return ModelStatus(INVALID_URL, self.url_error or "Invalid model URL")
        try:
            version = str(self._get_json("/api/version").get("version") or "unknown")
            entries = self._get_json("/api/tags").get("models")
        except LocalLLMError as exc:
            return ModelStatus(exc.state, str(exc))
        if not isinstance(entries, list):
            return ModelStatus(PROTOCOL_ERROR, "The model list from the server is malformed", version)
        local, rejected = [], []
        for entry in entries:
            name = str((entry or {}).get("name") or (entry or {}).get("model") or "") if isinstance(entry, dict) else ""
            if not name:
                continue
            (rejected if is_remote_model(entry) else local).append(name)
        status = ModelStatus(READY, "", version, self.chat_model or None, self.embed_model or None,
                             local_models=sorted(local), rejected_models=sorted(rejected))
        status.state, status.message = self._model_state(self.chat_model, local, rejected, "answer")
        status.embed_state, _ = self._model_state(self.embed_model, local, rejected, "embedding")
        return status

    @staticmethod
    def _model_state(name: str, local: list, rejected: list, role: str):
        if not name:
            return NOT_CONFIGURED, f"No local {role} model chosen"
        if is_remote_model({"name": name}) or _matches(name, rejected):
            return REMOTE_REJECTED, (f"'{name}' runs outside this computer (Ollama cloud/remote model) and "
                                     "is refused; documents never leave this computer")
        if not _matches(name, local):
            return MODEL_MISSING, f"Model '{name}' is not installed in the local Ollama (install it yourself)"
        return READY, f"Local {role} model '{name}' is available"

    # ---------------------------------------------------------------- chat
    def chat(self, messages: list, cancel: Optional[CancelToken] = None,
             on_token: Optional[Callable[[str], None]] = None) -> str:
        """Stream a chat completion; return the full text or raise LocalLLMError."""
        if not self.chat_model:
            raise LocalLLMError(NOT_CONFIGURED, "No local answer model chosen")
        if is_remote_model({"name": self.chat_model}):
            raise LocalLLMError(REMOTE_REJECTED, "Cloud/remote models are refused")
        cancel = cancel or CancelToken()
        if cancel.cancelled:
            raise LocalLLMError(CANCELLED, "Cancelled")
        payload = {"model": self.chat_model, "messages": messages, "stream": True,
                   "options": {"temperature": 0.1}, "keep_alive": "5m"}
        deadline = time.monotonic() + self.request_timeout
        response = self._request("/api/chat", payload, self.read_timeout)
        cancel._attach(response)
        parts, size = [], 0
        try:
            while True:
                if cancel.cancelled:
                    raise LocalLLMError(CANCELLED, "Cancelled")
                if time.monotonic() > deadline:
                    raise LocalLLMError(TIMEOUT, f"No complete answer within {self.request_timeout:.0f} s")
                try:
                    line = response.readline(MAX_RESPONSE_BYTES)
                except (socket.timeout, TimeoutError):
                    raise LocalLLMError(TIMEOUT, "The local model stopped sending data") from None
                except (OSError, ValueError, AttributeError, http.client.HTTPException):
                    if cancel.cancelled:
                        raise LocalLLMError(CANCELLED, "Cancelled") from None
                    raise LocalLLMError(PROTOCOL_ERROR, "The model connection broke") from None
                if not line:
                    if cancel.cancelled:
                        raise LocalLLMError(CANCELLED, "Cancelled")
                    raise LocalLLMError(PROTOCOL_ERROR, "The model stream ended before the answer was complete")
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    raise LocalLLMError(PROTOCOL_ERROR, "The model stream is not valid JSON lines") from None
                if not isinstance(chunk, dict):
                    raise LocalLLMError(PROTOCOL_ERROR, "Unexpected model stream item")
                if chunk.get("error"):
                    raise LocalLLMError(SERVER_ERROR, f"Model server error: {str(chunk['error'])[:200]}")
                if chunk.get("remote_host") or chunk.get("remote_model"):
                    raise LocalLLMError(REMOTE_REJECTED, "The answer was produced by a remote (cloud) model; "
                                                         "discarded")
                message = chunk.get("message") or {}
                if message.get("tool_calls"):
                    raise LocalLLMError(PROTOCOL_ERROR, "The model asked to call a tool; refused")
                piece = message.get("content") or ""
                if piece:
                    size += len(piece)
                    if size > MAX_ANSWER_CHARS:
                        raise LocalLLMError(PROTOCOL_ERROR, "The model answer is too long")
                    parts.append(piece)
                    if on_token is not None:
                        on_token(piece)
                if chunk.get("done"):
                    break
        finally:
            cancel._detach()
            try:
                response.close()
            except OSError:  # silent-ok: best-effort close in finally; the result or error is already decided
                pass
        return "".join(parts)

    # ----------------------------------------------------------- embedding
    def embed(self, texts: list, cancel: Optional[CancelToken] = None) -> list:
        """Vectors for ``texts`` (same order) or raise LocalLLMError."""
        if not self.embed_model:
            raise LocalLLMError(NOT_CONFIGURED, "No local embedding model chosen")
        if is_remote_model({"name": self.embed_model}):
            raise LocalLLMError(REMOTE_REJECTED, "Cloud/remote models are refused")
        if cancel is not None and cancel.cancelled:
            raise LocalLLMError(CANCELLED, "Cancelled")
        value = self._get_json("/api/embed", {"model": self.embed_model, "input": list(texts)},
                               timeout=self.read_timeout)
        if value.get("remote_host") or value.get("remote_model"):
            raise LocalLLMError(REMOTE_REJECTED, "Embeddings came from a remote (cloud) model; discarded")
        vectors = value.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise LocalLLMError(PROTOCOL_ERROR, "The embedding response has the wrong number of vectors")
        dims = {len(v) for v in vectors if isinstance(v, list)}
        if len(dims) != 1 or 0 in dims or any(not isinstance(v, list) for v in vectors):
            raise LocalLLMError(PROTOCOL_ERROR, "The embedding vectors are malformed")
        try:
            return [[float(x) for x in v] for v in vectors]
        except (TypeError, ValueError):
            raise LocalLLMError(PROTOCOL_ERROR, "The embedding vectors are not numbers") from None


def _matches(name: str, names: list) -> bool:
    """Ollama treats ``model`` as ``model:latest``."""
    wanted = {name, name + ":latest"} if ":" not in name else {name}
    return any(candidate in wanted for candidate in names)


def _http_error_state(exc: urllib.error.HTTPError):
    try:
        detail = json.loads(exc.read(64 * 1024).decode("utf-8")).get("error", "")
    except (OSError, ValueError, UnicodeDecodeError, AttributeError):  # silent-ok: optional error detail; the state comes from the HTTP status code
        detail = ""
    finally:
        exc.close()
    detail = str(detail)[:200]
    if exc.code == 404 and "not found" in detail.lower():
        return MODEL_MISSING, f"Model not installed in the local Ollama ({detail})"
    return SERVER_ERROR, f"Model server error HTTP {exc.code}" + (f": {detail}" if detail else "")
