"""Explicit, offline-safe detection for optional AI/document capabilities."""

from __future__ import annotations

import importlib.util

from core.ai_import_mapper import AIImportMapper


def _module_installed(*names: str) -> bool:
    return any(importlib.util.find_spec(name) is not None for name in names)


def detect_optional_capabilities(*, probe_network: bool = False) -> dict[str, dict[str, object]]:
    """Return capability states without network access unless explicitly asked.

    Ollama/Qwen detection uses the existing opt-in mapper. MinerU detection is
    package-only and recognizes both common import names. No optional package
    is imported merely to report its state.
    """
    mapper = AIImportMapper()
    if not mapper.enabled:
        ollama_status = "disabled"
        qwen_status = "disabled"
        installed_models: list[str] = []
    elif probe_network:
        installed_models = mapper.installed_models()
        ollama_status = "available" if mapper.last_status == "ready" else mapper.last_status
        qwen_status = (
            "available"
            if any("qwen" in model.lower() for model in installed_models)
            else "model-not-installed"
        )
    else:
        installed_models = []
        ollama_status = "enabled-not-probed"
        qwen_status = "enabled-not-probed"

    mineru_installed = _module_installed("mineru", "magic_pdf")
    return {
        "ollama": {
            "status": ollama_status,
            "enabled": mapper.enabled,
            "endpoint": mapper.endpoint,
        },
        "qwen": {
            "status": qwen_status,
            "models": installed_models,
        },
        "mineru": {
            "status": "installed" if mineru_installed else "not-installed",
            "installed": mineru_installed,
            "network_probed": False,
        },
    }
