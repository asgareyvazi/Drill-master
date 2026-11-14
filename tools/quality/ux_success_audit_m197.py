"""M197: find success wording inside exception handlers of the UI (tabs, dialogs, main window).

A failure path must say NOT SAVED / NOT UPDATED / NOT IMPORTED (or explain the failure); a handler that shows
"Saved", "Imported", "Updated", "✅" ... claims a success the code did not reach. Each finding is reviewed by a person
and either fixed or listed in REVIEWED with the reason it is truthful. Read-only; AST only, nothing is imported.

Usage: python tools/quality/ux_success_audit_m197.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUCCESS = re.compile(r"^\s*(✅|✔|Saved|Imported|Updated|Exported|Published|Success|Successfully|Done)\b", re.I)

# (file, literal prefix) -> why it is truthful
REVIEWED = {
    ("dialogs/excel_import_dialog.py", "imported"): "a dict key of the failure result ('imported': 0)",
    ("tabs/knowledge_assistant.py", "done"): "a progress-dict key ('done': 0) of a cancelled index build",
    ("tabs/trajectory_saved_views_panel.py", "Saved trajectory views could not be read"): "names the failure",
    ("tabs/trajectory_saved_views_panel.py", "Saved views could not be read"): "names the failure",
    ("tabs/w10_Planning_Widget.py", "SAVED — display refresh failed"):
        "reached only after the commit succeeded (`committed` is True); the refresh failure is stated",
    ("tabs/w1_well_info.py", "Success"): "fallback helper definitions inside `except ImportError`, not a result",
    ("tabs/well_plan_designer_panel.py", "Saved plans could not be loaded"): "names the failure",
}


def findings():
    files = sorted(list((ROOT / "tabs").rglob("*.py")) + list((ROOT / "dialogs").rglob("*.py"))
                   + [ROOT / "main_window.py"])
    out = set()
    for path in files:
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.ExceptHandler):
                continue
            for sub in ast.walk(node):
                text = None
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    text = sub.value
                elif isinstance(sub, ast.JoinedStr) and sub.values and isinstance(sub.values[0], ast.Constant):
                    text = str(sub.values[0].value)
                if text is not None and SUCCESS.match(text):
                    out.add((rel, text.strip()))
    return out


def unreviewed(found):
    return sorted(f for f in found if not any(f[0] == path and f[1].startswith(prefix)
                                                for path, prefix in REVIEWED))


def main() -> int:
    left = unreviewed(findings())
    for path, text in left:
        print(f"{path}: {text[:100]!r}")
    print(f"{len(left)} unreviewed success message(s) in exception handlers")
    return 1 if left else 0


if __name__ == "__main__":
    sys.exit(main())
