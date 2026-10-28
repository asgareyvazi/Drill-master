"""Optional offline-safe local AI assistant for ambiguous workbook mappings.

AI is opt-in and advisory only. Deterministic import validation remains the
source of truth; an unavailable Ollama service produces a clear capability
status and never blocks non-AI imports.

Workbook cells never leave this computer (M50 §7, same policy as the M49
assistant in ``core.local_llm``): the endpoint must be loopback, proxies and
redirects are refused, and Ollama cloud/remote models (``:cloud`` tags or a
``remote_host``/``remote_model`` entry) are neither listed nor used.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

from core.canonical_schema import CANONICAL_FIELDS
from core.local_llm import LocalLLMError, _NoRedirect, is_remote_model, validate_loopback_url
from core.runtime_config import ai_settings_path

logger = logging.getLogger(__name__)
ALLOWED_FIELDS = CANONICAL_FIELDS


def _catalog_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "ai_models.json"


def model_catalog():
    try:
        return json.loads(_catalog_path().read_text(encoding="utf-8")).get("models", [])
    except (OSError, ValueError):
        return []


def get_selected_model():
    try:
        return json.loads(ai_settings_path().read_text(encoding="utf-8")).get("model", "")
    except (OSError, ValueError):
        return ""


def set_selected_model(model):
    if not model:
        return
    path = ai_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": model}, indent=2), encoding="utf-8")


class AIImportMapper:
    """Capability-aware Ollama mapper; it never invents canonical values."""

    def __init__(self, endpoint=None, model=None, timeout=20):
        raw_endpoint = (endpoint or os.getenv("DRILLMASTER_OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")
        try:
            self.endpoint = validate_loopback_url(raw_endpoint)
            self.endpoint_error = ""
        except LocalLLMError as exc:       # a remote or malformed endpoint is never contacted
            self.endpoint, self.endpoint_error = None, str(exc)
        self.rejected_models = []          # installed, but they would run off this computer
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        self.model = (
            model
            or os.getenv("DRILLMASTER_AI_MODEL", "")
            or get_selected_model()
            or "qwen2.5-local"
        )
        try:
            requested_timeout = int(os.getenv("DRILLMASTER_AI_TIMEOUT", str(max(timeout, 30))))
        except ValueError:
            requested_timeout = max(timeout, 30)
        self.timeout = min(max(requested_timeout, 10), 45)
        self.last_status = "disabled"

    @property
    def enabled(self):
        return os.getenv("DRILLMASTER_AI_IMPORT", "0").lower() in {
            "1", "true", "yes", "on"
        }

    def installed_models(self):
        """List Ollama models only after the user explicitly enables AI."""
        if not self.enabled:
            self.last_status = "disabled"
            return []
        if self.endpoint is None:
            self.last_status = "invalid-url"
            return []
        try:
            with self._opener.open(f"{self.endpoint}/api/tags", timeout=2) as response:
                payload = json.loads(response.read().decode())
        except (OSError, urllib.error.URLError, ValueError, LocalLLMError):
            self.last_status = "ollama-unavailable"
            return []
        models = payload.get("models") if isinstance(payload, dict) else None
        local, rejected = [], []
        for item in models if isinstance(models, list) else []:
            name = item.get("name") if isinstance(item, dict) else None
            if name:
                (rejected if is_remote_model(item) else local).append(name)
        self.rejected_models = rejected
        self.last_status = "ready"
        return local

    def available(self):
        if not self.enabled:
            self.last_status = "disabled"
            return False
        if is_remote_model({"name": self.model}):
            self.last_status = "remote-rejected"
            return False
        installed = set(self.installed_models())
        if self.last_status != "ready":            # invalid-url / ollama-unavailable stay distinct
            return False
        if self.model in self.rejected_models:
            self.last_status = "remote-rejected"
            return False
        if self.model not in installed:
            self.last_status = "model-not-installed"
            return False
        self.last_status = "available"
        return True

    def map_context(self, context, allowed_fields=None):
        if not self.available():
            return []
        fields = sorted(set(allowed_fields or ALLOWED_FIELDS) & ALLOWED_FIELDS)
        prompt = {
            "task": "Map workbook cells to canonical drilling fields.",
            "rules": [
                "Return JSON only: {proposals: []}.",
                "Never invent values.",
                "Keep source_sheet, source_row and source_column.",
                "Return confidence between 0 and 1.",
                "Use null when ambiguous.",
            ],
            "allowed_fields": fields,
            "context": context,
        }
        body = json.dumps(
            {"model": self.model, "stream": False, "format": "json", "prompt": json.dumps(prompt)}
        ).encode()
        try:
            request = urllib.request.Request(
                f"{self.endpoint}/api/generate",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self._opener.open(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode())
            raw = payload.get("response", "{}")
            result = json.loads(raw) if isinstance(raw, str) else raw
            proposals = result.get("proposals", []) if isinstance(result, dict) else []
            valid = [proposal for proposal in proposals if self._valid_proposal(proposal, fields)]
            self.last_status = f"ok:{len(valid)}"
            return valid
        except (OSError, urllib.error.URLError, ValueError, TypeError, AttributeError, LocalLLMError):
            self.last_status = "request-failed"
            logger.warning("Local AI import mapping unavailable")
            return []

    @staticmethod
    def _valid_proposal(proposal, allowed):
        if (
            not isinstance(proposal, dict)
            or proposal.get("field") not in allowed
            or not proposal.get("source_sheet")
            or proposal.get("source_row") is None
            or proposal.get("value") is None
        ):
            return False
        try:
            confidence = float(proposal.get("confidence", 0))
        except (TypeError, ValueError):
            return False
        return 0 <= confidence <= 1
