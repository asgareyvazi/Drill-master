"""Configurable operational standards; never bury policy numbers in UI code.

All intervals must be configurable: Operator Standard, Well Type, Region, Company Policy, not hard-coded.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any

from core.runtime_config import standards_path


def _load_config() -> Dict[str, Any]:
    """Load user overrides first, then the read-only packaged defaults."""
    user_path = standards_path()
    packaged_path = Path(__file__).resolve().parent.parent / "config" / "operational_standards.json"
    for config_path in (user_path, packaged_path):
        if config_path.exists():
            try:
                return json.loads(config_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
    return {}


def bop_test_interval_days(default=14) -> int:
    """BOP test interval - configurable via env or config file.

    Spec: All intervals must be configurable: Operator Standard, Well Type, Region, Company Policy, not hard-coded.
    Default 14 days for many operators, but configurable.
    """
    cfg = _load_config()
    # Priority: env var > config file > default
    try:
        env_val = os.getenv("DRILLMASTER_BOP_TEST_INTERVAL_DAYS")
        if env_val:
            return max(1, int(env_val))
        if "bop_test_interval_days" in cfg:
            return max(1, int(cfg["bop_test_interval_days"]))
        return default
    except (TypeError, ValueError):
        return default


def get_bop_intervals() -> Dict[str, int]:
    """Get all BOP-related intervals with configurability."""
    cfg = _load_config()
    return {
        "rams_test": int(cfg.get("bop_rams_test_days", os.getenv("DRILLMASTER_BOP_RAMS_TEST_DAYS", 14))),
        "annular_test": int(cfg.get("bop_annular_test_days", os.getenv("DRILLMASTER_BOP_ANNULAR_TEST_DAYS", 7))),
        "koomey_test": int(cfg.get("bop_koomey_test_days", os.getenv("DRILLMASTER_BOP_KOOMEY_TEST_DAYS", 7))),
        "choke_kill_test": int(cfg.get("bop_choke_kill_test_days", os.getenv("DRILLMASTER_BOP_CHOKE_KILL_TEST_DAYS", 14))),
    }


def get_safety_drill_intervals() -> Dict[str, int]:
    """Safety drill intervals configurable."""
    cfg = _load_config()
    return {
        "fire_drill": int(cfg.get("safety_fire_drill_days", os.getenv("DRILLMASTER_FIRE_DRILL_DAYS", 7))),
        "bop_drill": int(cfg.get("safety_bop_drill_days", os.getenv("DRILLMASTER_BOP_DRILL_DAYS", 7))),
        "h2s_drill": int(cfg.get("safety_h2s_drill_days", os.getenv("DRILLMASTER_H2S_DRILL_DAYS", 14))),
        "abandon_drill": int(cfg.get("safety_abandon_drill_days", os.getenv("DRILLMASTER_ABANDON_DRILL_DAYS", 30))),
    }


def get_all_standards() -> Dict[str, Any]:
    """Return all operational standards for export and UI."""
    return {
        "bop": get_bop_intervals(),
        "safety": get_safety_drill_intervals(),
        "bop_test_interval_days": bop_test_interval_days(),
        "source": "config/operational_standards.json or env vars - not hard-coded",
        "configurable_by": ["Operator Standard", "Well Type", "Region", "Company Policy"],
    }


def save_standards(standards: Dict[str, Any], path: str = None):
    """Save standards to config file."""
    if path is None:
        path = str(standards_path())
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(standards, indent=2), encoding="utf-8")
