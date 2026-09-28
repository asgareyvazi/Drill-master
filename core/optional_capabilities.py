"""Explicit, offline-safe detection for optional AI/document capabilities."""

from __future__ import annotations

from core.ai_import_mapper import AIImportMapper
from core.mineru_engine import MinerUAdapter


def detect_optional_capabilities(*, probe_network: bool = False) -> dict[str, dict[str, object]]:
    """Return capability states without network access unless explicitly asked.

    Ollama/Qwen detection uses the existing opt-in mapper. MinerU detection
    uses the external adapter and does not import or install the package into
    DrillMaster's environment.
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

    mineru_health = MinerUAdapter().health_check()
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
            "status": "available" if mineru_health.available else "not-installed",
            "installed": mineru_health.available,
            "enabled": mineru_health.enabled,
            "executable": mineru_health.executable,
            "version": mineru_health.version,
            "error": mineru_health.error,
            "network_probed": False,
        },
    }
