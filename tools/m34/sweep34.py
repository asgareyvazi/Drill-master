"""M34 fresh semantic sweep: deterministic, read-only, source files only.

Families are the M33 set (recorded verbatim in the M33 sweep evidence) so the inventories are
comparable, extended with the M34 families the mission lists (serialization, permissions,
packaging, resource lifecycle, security, currency, plan/actual, snapshot).
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from common import ROOT, enclosing_function, file_lines, file_sha, iter_source_files, norm  # noqa: E402

FAMILIES: dict[str, str] = {
    # --- M33 set (identical regexes) ---
    "or-zero": r"\bor\s+0(?:\.0)?\b",
    "or-empty-string": r"""\bor\s+(?:''|"")\b""",
    "if-not-falsy": r"\bif\s+not\s+[A-Za-z_(]",
    "orm-single-fetch": r"\.(?:first|one|one_or_none|scalar|scalar_one|scalar_one_or_none)\s*\(",
    "broad-except": r"except\s+(?:Exception|BaseException)\s*(?:as\s+\w+)?\s*:|except\s*:",
    "pass-statement": r"^\s*pass\s*$",
    "return-none-false": r"^\s*return\s+(?:None|False|0(?:\.0)?|\[\]|\{\}|''|\"\")\s*$",
    "assert-true": r"assert\s+(?:True|1)\b",
    "sum-or-zero": r"\bsum\([^)]*\bor\s+0",
    "float-int-or-zero": r"\b(?:float|int)\([^)]*\bor\s+0",
    "default-zero-param": r"(?:default|value)\s*=\s*0(?:\.0)?\b",
    "setvalue-zero": r"\.setValue\(\s*0(?:\.0)?\s*\)",
    "get-default": r"\.get\([^)]*,\s*0(?:\.0)?\s*\)",
    "numeric-coalesce": r"\bor\s+(?:0\.0|0)\b(?!\s*\))",
    # --- M34 additions (mission Part D families not covered above) ---
    "bare-except-return": r"except\s*:\s*$",
    "skip-call": r"\bpytest\.skip\s*\(|\.skipTest\s*\(|@pytest\.mark\.skip",
    "xfail-marker": r"@pytest\.mark\.xfail",
    "shell-subprocess": r"subprocess\.(?:run|Popen|call|check_output|check_call)\s*\(",
    "shell-true": r"\bshell\s*=\s*True",
    "raw-sql-text": r"text\s*\(\s*[\"']",
    "credential-literal": r"""(?:password|passwd|secret|token|api_key)\s*=\s*["'][^"']{3,}["']""",
    "temp-file": r"tempfile\.|NamedTemporaryFile|mkstemp",
    "session-lifecycle": r"session_scope\(|create_session\(|SessionLocal\(|\.close\(\)",
    "currency-arithmetic": r"(?:\bUSD\b|\bEUR\b|\bNOK\b|currency|fx_rate|exchange_rate)",
    "plan-actual": r"\b(?:planned|actual)_\w+|\bforecast\w*\b|\bbaseline\w*\b",
    "snapshot-serialize": r"json\.dumps\(|json\.loads\(|to_dict\(|as_dict\(|model_dump\(",
    "float-or-zero-strict": r"\bfloat\([^)]*\)\s+or\s+0(?:\.0)?",
}


def hits_for_file(rel: str) -> list[dict]:
    lines = file_lines(rel)
    sha = file_sha(rel)
    found = []
    for lineno, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if stripped.startswith("#"):
            continue
        for family, pattern in FAMILIES.items():
            if re.search(pattern, raw):
                fn = enclosing_function(rel, lineno)
                found.append({
                    "file": rel, "line": lineno, "family": family,
                    "symbol": fn[2] if fn else None,
                    "text": norm(raw)[:200],
                    "source_sha256": sha,
                })
    return found


def main() -> None:
    hits: list[dict] = []
    scanned = 0
    per_file = {}
    for rel in iter_source_files():
        scanned += 1
        file_hits = hits_for_file(rel)
        if file_hits:
            per_file[rel] = len(file_hits)
        hits.extend(file_hits)
    # stable content fingerprint per occurrence (context, not line number)
    seen: dict[tuple, int] = {}
    for h in hits:
        key = (h["file"], h["family"], h["symbol"] or "", h["text"])
        ordinal = seen.get(key, 0)
        seen[key] = ordinal + 1
        h["ordinal"] = ordinal
        h["context_fingerprint"] = hashlib.sha256(
            "|".join([h["file"], h["family"], h["symbol"] or "", h["text"], str(ordinal)])
            .encode("utf-8")).hexdigest()
    out = {
        "schema": "m34-fresh-sweep", "scope": "source files only (.py, .github/**, pyproject.toml)",
        "families": FAMILIES, "files_scanned": scanned, "hits": hits,
        "per_file": dict(sorted(per_file.items(), key=lambda kv: -kv[1])),
    }
    target = ROOT / "docs/audits/m34-evidence/m34-fresh-sweep.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    from collections import Counter
    print("files scanned:", scanned, "| hits:", len(hits), "| files with hits:", len(per_file))
    print("by family:", Counter(h["family"] for h in hits).most_common())


if __name__ == "__main__":
    main()
