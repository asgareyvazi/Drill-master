"""M112: dependency and licence audit (read-only; installs and downloads nothing).

* Every pinned package of ``requirements-lock.txt`` with the licence its installed distribution declares
  (``importlib.metadata``) and a licence class.
* Every third-party import of the product code (``core``, ``tabs``, ``dialogs`` and the root modules) mapped
  to a declared distribution, or to a listed OPTIONAL module that must be imported inside ``try`` (guarded);
  anything else is a FAIL finding.
* The method catalogue with, per entry, the test files that name its method id or module (exact count).

``--write`` stores the result in ``docs/engineering/dependency_audit.json``; ``--check`` exits 1 when the
committed file is stale or a FAIL finding exists.  Licences of optional packages that are NOT installed come
from their published PyPI metadata (read 2026-11-03, versions given) and are marked "published metadata;
not installed here".  Copyleft and unknown licences are owner gates, never decided here.

M137 (v2) reconciles the declarations with each other and with packaging: ``pyproject.toml`` dependencies equal
``requirements.txt``; every declared distribution is pinned in the lock; every pin of
``requirements-optional.txt`` and ``requirements-build.txt`` has a recorded licence of exactly the pinned version;
every owner-gated optional module and the forbidden GPL bindings are excluded by ``packaging/DrillMaster.spec``
and rejected by ``packaging/package_smoke.py``. ``--write`` also regenerates the bundled-runtime section of
``THIRD_PARTY_NOTICES.md`` (``--check`` fails when it is stale).
"""
from __future__ import annotations

import argparse
import ast
import importlib.metadata as metadata
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "engineering" / "dependency_audit.json"
AUDIT_VERSION = "M137 dependency audit v2"
PRODUCT_DIRS = ("core", "tabs", "dialogs")

#: import name -> distribution in requirements.txt / requirements-lock.txt
DECLARED_IMPORTS = {
    "PySide6": "PySide6", "sqlalchemy": "SQLAlchemy", "openpyxl": "openpyxl", "bcrypt": "bcrypt",
    "numpy": "numpy", "matplotlib": "matplotlib", "mpl_toolkits": "matplotlib", "pandas": "pandas",
    "pyqtgraph": "pyqtgraph", "fitz": "PyMuPDF", "PIL": "pillow",
}

#: optional imports (not declared; must be guarded).  Licence = published PyPI metadata, 2026-11-03.
OPTIONAL_IMPORTS: Dict[str, Dict[str, str]] = {
    "camelot": {"distribution": "camelot-py", "licence": "MIT (camelot-py 2.0.0)", "gate": "OCR / PDF tables (requirements-optional)"},
    "pytesseract": {"distribution": "pytesseract", "licence": "Apache-2.0 (0.3.13)", "gate": "OCR (requirements-optional)"},
    "pdf2image": {"distribution": "pdf2image", "licence": "MIT (1.17.0)", "gate": "OCR (requirements-optional chain)"},
    "rapidocr": {"distribution": "rapidocr", "licence": "Apache-2.0 (3.10.0)", "gate": "OCR / models (requirements-optional)"},
    "torch": {"distribution": "torch", "licence": "Apache-2.0 AND BSD-3-Clause AND MIT AND others (2.15.0)", "gate": "AI/ML, weights, GPU (MinerU probe only)"},
    "welleng": {"distribution": "welleng", "licence": "Apache-2.0 (0.30.0); ISCWSA model tables need review", "gate": "ISCWSA / welleng"},
    "torque_drag": {"distribution": "torque-drag", "licence": "LGPL-3.0 (0.1.1)", "gate": "pwptemp / torque_drag (LGPL)"},
    "lasio": {"distribution": "lasio", "licence": "MIT (0.32)", "gate": "none recorded (LAS import/export is optional)"},
    "reportlab": {"distribution": "reportlab", "licence": "BSD (5.1.0)", "gate": "none recorded (chart/procedure PDF fallback)"},
    "qtribbon": {"distribution": "qtribbon", "licence": "UNKNOWN — not published on PyPI", "gate": "unknown licence (ribbon UI fallback)"},
}

#: requirements-optional.txt is never installed by the audit (owner gate: OCR / onnxruntime)
FORBIDDEN_IMPORTS = {"PyQt5": "GPL-3.0 binding; the product is PySide6 only", "PyQt6": "GPL-3.0 binding; the product is PySide6 only"}


# --------------------------------------------------------------------------- M137 reconciliation
#: requirements-optional.txt pins -> published PyPI metadata of exactly that version (never installed here).
OPTIONAL_PINS: Dict[str, Dict[str, str]] = {
    "camelot-py": {"version": "0.11.0", "licence": "MIT", "read": "2026-11-07"},
    "pytesseract": {"version": "0.3.13", "licence": "Apache-2.0", "read": "2026-11-03"},
    "rapidocr": {"version": "3.10.0", "licence": "Apache-2.0; the wheel bundles PP-OCR ONNX models (model licence: "
                 "owner review)", "read": "2026-11-03"},
    "onnxruntime": {"version": "1.31.0", "licence": "MIT", "read": "2026-11-07"},
}
#: requirements-build.txt pins (Windows build machine only; never on users' machines) -> published metadata.
BUILD_PINS: Dict[str, Dict[str, str]] = {
    "pyinstaller": {"version": "6.11.1", "licence": "GPL-2.0-or-later with the PyInstaller bootloader exception "
                    "(build tool; the exception allows distributing the built application under its own terms)",
                    "read": "2026-11-07"},
    "pywin32-ctypes": {"version": "0.2.3", "licence": "BSD-3-Clause", "read": "2026-11-07"},
    "altgraph": {"version": "0.17.5", "licence": "MIT", "read": "2026-11-07"},
    "setuptools": {"version": "84.0.0", "licence": "MIT", "read": "2026-11-07"},
    "pefile": {"version": "2023.2.7", "licence": "MIT", "read": "2026-11-07"},
    "pyinstaller-hooks-contrib": {"version": "2025.1", "licence": "Apache-2.0; GPL-2.0 (classifiers only; no licence "
                                  "expression published)", "read": "2026-11-07"},
}
#: modules that must never be bundled: every owner-gated optional module and the forbidden GPL bindings.
#: lasio and reportlab (permissive, no gate) are not listed - whether they are bundled follows the lock.
BUNDLE_EXCLUDED = ("camelot", "gekko", "magic_pdf", "mineru", "ollama", "onnxruntime", "pdf2image", "PyQt5", "PyQt6",
                   "pytesseract", "qtribbon", "rapidocr", "torch", "torque_drag", "welleng")
SPEC = Path("packaging") / "DrillMaster.spec"
SMOKE = Path("packaging") / "package_smoke.py"
NOTICES = Path("THIRD_PARTY_NOTICES.md")
NOTICES_BEGIN = "<!-- BEGIN GENERATED: bundled runtime licences (tools/quality/dependency_audit.py --write) -->"
NOTICES_END = "<!-- END GENERATED: bundled runtime licences -->"


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).casefold()


def _pins(path: Path) -> Dict[str, str]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return {_norm(n): v for n, v in re.findall(r"^([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?==([^\s;\\]+)", text, re.M)}


def _string_list(path: Path, name: str) -> List[str]:
    """The string elements of the list/set literal assigned to ``name`` in a Python file (not executed)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            if isinstance(node.value, (ast.List, ast.Set, ast.Tuple)):
                return [e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return []


def _requirement_set(lines) -> set:
    return {re.sub(r"\s+", "", line) for line in lines if line.strip() and not line.lstrip().startswith("#")}


def reconcile(root: Path = ROOT) -> Dict[str, Any]:
    """Declarations, pins, packaging exclusions and recorded licences agree (M137); returns facts and findings."""
    import tomllib

    findings: List[Dict[str, str]] = []

    def fail(where, text, level="FAIL"):
        findings.append({"level": level, "where": where, "finding": text})

    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project_deps = _requirement_set(pyproject.get("project", {}).get("dependencies", []))
    requirement_lines = _requirement_set((root / "requirements.txt").read_text(encoding="utf-8").splitlines())
    if project_deps != requirement_lines:
        fail("pyproject.toml", "dependencies differ from requirements.txt: "
             + ", ".join(sorted(project_deps ^ requirement_lines)))
    lock = _pins(root / "requirements-lock.txt")
    for line in sorted(requirement_lines):
        name = _norm(re.split(r"[<>=!~\[ ]", line, maxsplit=1)[0])
        if name not in lock:
            fail("requirements-lock.txt", f"declared {name} has no pin")
    for label, path, recorded in (("requirements-optional.txt", root / "requirements-optional.txt", OPTIONAL_PINS),
                                  ("requirements-build.txt", root / "requirements-build.txt", BUILD_PINS)):
        pins = _pins(path)
        known = {_norm(k): v for k, v in recorded.items()}
        for name, version in sorted(pins.items()):
            if name not in known:
                fail(label, f"{name}=={version} has no recorded licence")
            elif known[name]["version"] != version:
                fail(label, f"{name}=={version}: licence recorded for {known[name]['version']} (re-read the "
                     "published metadata of the pinned version)")
        for name in sorted(set(known) - set(pins)):
            fail(label, f"recorded licence for {name} which is not pinned", "WARN")
    excludes = _string_list(root / SPEC, "excludes")
    smoke = {m.casefold() for m in _string_list(root / SMOKE, "FORBIDDEN_MODULES")}
    for module in BUNDLE_EXCLUDED:
        if module not in excludes:
            fail(str(SPEC), f"gated module {module} is not excluded from the PyInstaller bundle")
        if module.casefold() not in smoke:
            fail(str(SMOKE), f"gated module {module} is not rejected by the bundle smoke check")
    return {"optional_pins": {k: dict(v) for k, v in sorted(OPTIONAL_PINS.items())},
            "build_pins": {k: dict(v) for k, v in sorted(BUILD_PINS.items())},
            "packaging": {"bundle_excluded": list(BUNDLE_EXCLUDED), "spec_excludes": excludes,
                          "smoke_forbidden": sorted(smoke)},
            "findings": findings}


def notices_section(lock_rows: List[Dict[str, Any]]) -> str:
    lines = [NOTICES_BEGIN, "",
             "## Bundled runtime libraries (generated)", "",
             "Every distribution pinned in `requirements-lock.txt` is bundled into the Windows application. The "
             "licence below is the one its installed metadata declares; the bundle carries each distribution's "
             "metadata folder (`*.dist-info`, with the licence files its wheel includes) next to this file. "
             "Copyleft entries are owner gates — shipping a licence text does not by itself meet AGPL or LGPL "
             "distribution obligations (source offer, relinking); no legal approval is implied.", "",
             "| Distribution | Version | Licence (installed metadata) | Class | Owner gate |",
             "|---|---|---|---|---|"]
    for row in lock_rows:
        lines.append(f"| {row['distribution']} | {row['pinned']} | {row['licence'].replace('|', '/')} | "
                     f"{row['class']} | {row['owner_gate'] or '—'} |")
    lines += ["", NOTICES_END]
    return "\n".join(lines)


def notices_text(root: Path, lock_rows: List[Dict[str, Any]]) -> str:
    """THIRD_PARTY_NOTICES.md with the generated section replaced (or appended)."""
    current = (root / NOTICES).read_text(encoding="utf-8")
    section = notices_section(lock_rows)
    if NOTICES_BEGIN in current and NOTICES_END in current:
        head, rest = current.split(NOTICES_BEGIN, 1)
        tail = rest.split(NOTICES_END, 1)[1]
        return head + section + tail
    return current.rstrip("\n") + "\n\n" + section + "\n"


def licence_class(text: str) -> str:
    t = (text or "").upper()
    if "AGPL" in t or "AFFERO" in t:
        return "strong copyleft (AGPL)"
    if "LGPL" in t or "LESSER" in t or "LIBRARY" in t:
        return "weak copyleft (LGPL)"
    if re.search(r"\bGPL\b|GNU GENERAL", t):
        return "strong copyleft (GPL)"
    if "UNKNOWN" in t or not t.strip():
        return "unknown"
    if any(k in t for k in ("MIT", "BSD", "APACHE", "PSF", "PYTHON SOFTWARE", "ISC", "ZLIB", "MATPLOTLIB")):
        return "permissive"
    return "custom / review"


def _lock() -> List[tuple]:
    text = (ROOT / "requirements-lock.txt").read_text(encoding="utf-8")
    return [tuple(m.split("==", 1)) for m in re.findall(r"^([A-Za-z0-9_.-]+==[^\s;\\]+)", text, re.M)]


def _declared() -> List[str]:
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    return sorted(re.split(r"[<>=!~\[ ]", line, maxsplit=1)[0] for line in text.splitlines()
                  if line.strip() and not line.lstrip().startswith("#"))


def _installed_licence(dist: str) -> tuple:
    try:
        d = metadata.distribution(dist)
    except metadata.PackageNotFoundError:
        return None, "NOT INSTALLED"
    m = d.metadata
    text = (m.get("License-Expression") or "").strip()
    classifiers = [c.split("::")[-1].strip() for c in (m.get_all("Classifier") or []) if c.startswith("License")]
    if not text:
        first = (m.get("License") or "").strip().splitlines()
        text = first[0] if first and len(first[0]) < 60 and not set(first[0]) <= set("=-") else ""
    if classifiers:
        text = f"{text} [{'; '.join(classifiers)}]" if text else "; ".join(classifiers)
    return d.version, text or "not declared in metadata"


def product_files(root: Path = ROOT) -> List[Path]:
    files = [p for d in PRODUCT_DIRS for p in sorted((root / d).rglob("*.py"))]
    return files + sorted(p for p in root.glob("*.py"))


def _local_names(root: Path) -> set:
    return {p.name for p in root.iterdir() if p.is_dir()} | {p.stem for p in root.glob("*.py")}


def _guarded(tree: ast.AST, node: ast.AST) -> bool:
    """True when ``node`` sits in the body of a ``try`` that catches ImportError (or a broader class)."""
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    current = node
    while current in parents:
        parent = parents[current]
        if isinstance(parent, ast.Try) and current in parent.body:
            for handler in parent.handlers:
                names = []
                if handler.type is None:
                    return True
                for t in (handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]):
                    names.append(getattr(t, "id", getattr(t, "attr", "")))
                if {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"} & set(names):
                    return True
        current = parent
    return False


def scan_imports(root: Path = ROOT, files: Optional[List[Path]] = None) -> List[Dict[str, Any]]:
    local = _local_names(root)
    found: Dict[tuple, Dict[str, Any]] = {}
    for path in files if files is not None else product_files(root):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                if top in sys.stdlib_module_names or top in local:
                    continue
                key = (top, path.relative_to(root).as_posix())
                entry = found.setdefault(key, {"module": top, "file": key[1], "lines": [], "guarded": True})
                entry["lines"].append(node.lineno)
                entry["guarded"] = entry["guarded"] and _guarded(tree, node)
    return [found[k] for k in sorted(found)]


def findings_for(imports: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    out = []
    for item in imports:
        module, where = item["module"], f"{item['file']}:{item['lines'][0]}"
        if module in FORBIDDEN_IMPORTS:
            out.append({"level": "FAIL", "where": where, "finding": f"{module}: {FORBIDDEN_IMPORTS[module]}"})
        elif module in DECLARED_IMPORTS:
            continue
        elif module in OPTIONAL_IMPORTS:
            if not item["guarded"]:
                out.append({"level": "FAIL", "where": where,
                            "finding": f"optional {module} is imported without an ImportError guard"})
        else:
            out.append({"level": "FAIL", "where": where, "finding": f"undeclared third-party import {module}"})
    return out


def _catalogue_evidence(root: Path) -> List[Dict[str, Any]]:
    sys.path.insert(0, str(root))
    from core import method_catalogue as mc
    tests = {p.name: p.read_text(encoding="utf-8") for p in sorted((root / "tests").glob("test_*.py"))}
    rows = []
    for entry in mc.catalogue():
        keys = [entry.method_id] + ([entry.module, Path(entry.module).stem] if entry.module else [])
        hits = sorted(name for name, text in tests.items() if any(k and k in text for k in keys))
        rows.append({"method_id": entry.method_id, "status": entry.status, "licence": entry.licence,
                     "approval": entry.approval, "evidence_tests": len(hits), "tests": hits})
    return rows


def build(root: Path = ROOT) -> Dict[str, Any]:
    lock = []
    for name, pinned in _lock():
        version, licence = _installed_licence(name)
        cls = licence_class(licence)
        gate = ("PyMuPDF (AGPL-3.0)" if cls.startswith("strong") else
                "Qt for Python (LGPL-3.0) distribution obligations" if cls.startswith("weak") else "")
        lock.append({"distribution": name, "pinned": pinned, "installed": version, "licence": licence,
                     "class": cls, "owner_gate": gate})
    imports = scan_imports(root)
    optional = [{"module": k, **v, "class": licence_class(v["licence"])} for k, v in sorted(OPTIONAL_IMPORTS.items())]
    findings = findings_for(imports)
    for row in lock:
        if row["installed"] not in (None, row["pinned"]):
            findings.append({"level": "WARN", "where": "requirements-lock.txt",
                             "finding": f"{row['distribution']} installed {row['installed']} != pinned {row['pinned']}"})
    reconciliation = reconcile(root)
    findings.extend(reconciliation.pop("findings"))
    catalogue = _catalogue_evidence(root)
    return {"version": AUDIT_VERSION, "declared": _declared(), "lock": lock, "optional_imports": optional,
            "imports": imports, "findings": findings, **reconciliation,
            "catalogue": {"entries": len(catalogue), "approved": sum(r["approval"].startswith("APPROVED") for r in catalogue),
                          "without_test_evidence": [r["method_id"] for r in catalogue if not r["evidence_tests"]],
                          "rows": catalogue}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    result = build()
    text = json.dumps(result, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    fails = [f for f in result["findings"] if f["level"] == "FAIL"]
    notices = notices_text(ROOT, result["lock"])
    if args.write:
        OUT.write_text(text, encoding="utf-8")
        (ROOT / NOTICES).write_text(notices, encoding="utf-8")
    for f in result["findings"]:
        print(f"{f['level']}: {f['where']}: {f['finding']}")
    print(f"lock {len(result['lock'])}; imports {len(result['imports'])}; findings {len(result['findings'])} "
          f"(FAIL {len(fails)}); catalogue {result['catalogue']['entries']} entries, "
          f"{result['catalogue']['approved']} approved")
    if args.check:
        stale = not OUT.exists() or OUT.read_text(encoding="utf-8") != text
        if stale:
            print("dependency_audit.json is stale (run --write)")
        if (ROOT / NOTICES).read_text(encoding="utf-8") != notices:
            stale = True
            print("THIRD_PARTY_NOTICES.md bundled-runtime section is stale (run --write)")
        return 1 if (stale or fails) else 0
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
