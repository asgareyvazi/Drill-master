"""M197: no exception handler in the UI claims a success; every match of success wording is reviewed."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _tool():
    spec = importlib.util.spec_from_file_location("ux197", ROOT / "tools" / "quality" / "ux_success_audit_m197.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_unreviewed_success_message_in_an_exception_handler():
    tool = _tool()
    assert tool.unreviewed(tool.findings()) == []


def test_every_reviewed_entry_still_exists_so_the_list_cannot_go_stale():
    tool = _tool()
    found = tool.findings()
    for path, prefix in tool.REVIEWED:
        assert any(f[0] == path and f[1].startswith(prefix) for f in found), (path, prefix)


def test_a_new_success_claim_in_a_handler_is_reported(tmp_path, monkeypatch):
    tool = _tool()
    (tmp_path / "tabs").mkdir()
    (tmp_path / "dialogs").mkdir()
    (tmp_path / "main_window.py").write_text("", encoding="utf-8")
    (tmp_path / "tabs" / "x.py").write_text(
        "def f(label):\n    try:\n        save()\n    except Exception:\n        label.setText('Saved ✅')\n"
        "    try:\n        save()\n    except Exception as e:\n        label.setText(f'Updated {e}')\n",
        encoding="utf-8")
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    assert tool.unreviewed(tool.findings()) == [("tabs/x.py", "Saved ✅"), ("tabs/x.py", "Updated")]
