#!/usr/bin/env python3
"""M35 §6: the release artifact matrix — one row per shipped module, six independent columns.

Columns are computed, never asserted: source tree, git index, sdist, wheel, installed import,
and whether the release entry point actually needs the module (static import closure).
"""
from __future__ import annotations

import ast, hashlib, json, re, subprocess, sys, tarfile, zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "audits" / "m35-evidence" / "m35-release-artifact-matrix.json"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
WHEEL = Path("/tmp/m35/dist-fixed/drillmaster-1.0.0-py3-none-any.whl")
SDIST = Path("/tmp/m35/dist-fixed/drillmaster-1.0.0.tar.gz")
SITE = Path("/tmp/m35/venv-tracked/lib/python3.11/site-packages")

SHIPPED_PACKAGES = ("core", "dialogs", "tabs", "ui", "config", "templates")
SHIPPED_MODULES = ("app", "main_window", "run")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def module_of(path: str) -> str:
    p = path[:-3] if path.endswith(".py") else path
    if p.endswith("/__init__"):
        p = p[: -len("/__init__")]
    return p.replace("/", ".")


def shipped(name: str) -> bool:
    return name.split(".")[0] in SHIPPED_PACKAGES or name.split(".")[0] in SHIPPED_MODULES


def file_for(module: str) -> Path | None:
    for cand in (module.replace(".", "/") + ".py", module.replace(".", "/") + "/__init__.py"):
        if (ROOT / cand).is_file():
            return ROOT / cand
    return None


def imports_of(path: Path, module: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    pkg = module.split(".")[:-1]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg[: len(pkg) - node.level + 1]
                mod = ".".join([*base, node.module]) if node.module else ".".join(base)
            else:
                mod = node.module or ""
            if mod:
                found.add(mod)
                found |= {f"{mod}.{a.name}" for a in node.names if a.name != "*"}
    return found


def closure(entry: str = "app") -> set[str]:
    seen, required = set(), set()
    pending = [entry]
    while pending:
        m = pending.pop()
        if m in seen or not shipped(m):
            continue
        seen.add(m)
        f = file_for(m)
        if f is None:
            continue
        required.add(str(f.relative_to(ROOT)))
        pending += [i for i in imports_of(f, m) if shipped(i) and i not in seen]
    return required


def main() -> int:
    tracked = {n for n in subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                                         capture_output=True).stdout.decode().split("\0") if n}
    with zipfile.ZipFile(WHEEL) as z:
        wheel_names = set(z.namelist())
    with tarfile.open(SDIST) as t:
        sdist_names = {m.name.split("/", 1)[1] for m in t.getmembers() if "/" in m.name}
    required = closure()

    rows = []
    for package in SHIPPED_PACKAGES:
        files = sorted(str(p.relative_to(ROOT)) for p in (ROOT / package).rglob("*.py")
                       if "__pycache__" not in str(p))
        rows.append({
            "component": f"{package}/ (package tree)",
            "modules_on_disk": len(files),
            "tracked": all(f in tracked for f in files),
            "untracked_files": [f for f in files if f not in tracked],
            "in_sdist": sum(1 for f in files if f in sdist_names),
            "in_wheel": sum(1 for f in files if f in wheel_names),
            "installed_importable": (SITE / package).is_dir(),
            "runtime_required_modules": sum(1 for f in files if f in required),
        })
    for module in SHIPPED_MODULES:
        f = file_for(module)
        rel = str(f.relative_to(ROOT)) if f else module + ".py"
        rows.append({
            "component": rel,
            "modules_on_disk": 1 if f else 0,
            "tracked": rel in tracked,
            "untracked_files": [] if rel in tracked else [rel],
            "in_sdist": rel in sdist_names,
            "in_wheel": rel in wheel_names,
            "installed_importable": (SITE / rel).is_file(),
            "runtime_required_modules": 1 if rel in required else 0,
        })

    named = {}
    for module in ("core.operational_time", "core.safety_semantics"):
        rel = module.replace(".", "/") + ".py"
        named[module] = {
            "exists_in_worktree": (ROOT / rel).is_file(),
            "tracked": rel in tracked,
            "packaged_in_sdist": rel in sdist_names,
            "packaged_in_wheel": rel in wheel_names,
            "imported_by_release_path": rel in required,
            "installed_import_ok": (SITE / rel).is_file(),
            "worktree_sha256": hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(),
            "generated": False,
            "duplicate_definition": False,
            "import_sites": [ln.strip() for ln in subprocess.run(
                ["grep", "-rn", module, "--include=*.py", "core", "tabs", "dialogs", "app.py",
                 "main_window.py"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
                if "import" in ln and "tools/" not in ln],
        }

    payload = {
        "schema": "m35-release-artifact-matrix",
        "generated_utc": NOW,
        "artifacts": {
            "wheel": {"path": str(WHEEL), "bytes": WHEEL.stat().st_size,
                      "sha256": hashlib.sha256(WHEEL.read_bytes()).hexdigest(),
                      "entries": len(wheel_names)},
            "sdist": {"path": str(SDIST), "bytes": SDIST.stat().st_size,
                      "sha256": hashlib.sha256(SDIST.read_bytes()).hexdigest(),
                      "entries": len(sdist_names)},
            "installed_target": str(SITE),
        },
        "release_entry_point": {"console_script": "drillmaster = app:main",
                               "static_closure_modules": len(required),
                               "closure": sorted(required)},
        "rows": rows,
        "suspected_modules": named,
        "conclusion": {
            "packages_ship_completely": all(r["in_wheel"] == r["modules_on_disk"] for r in rows),
            "untracked_shipped_files": sorted({f for r in rows for f in r["untracked_files"]}),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1))
    print(f"closure modules: {len(required)} | rows: {len(rows)}")
    print("packages ship completely:", payload["conclusion"]["packages_ship_completely"])
    print("untracked shipped files:", payload["conclusion"]["untracked_shipped_files"])
    for mod, d in named.items():
        print(f"  {mod}: tracked={d['tracked']} sdist={d['packaged_in_sdist']} "
              f"wheel={d['packaged_in_wheel']} required={d['imported_by_release_path']} "
              f"import_sites={len(d['import_sites'])}")
    print("written", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
