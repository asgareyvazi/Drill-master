#!/usr/bin/env python3
"""M51 Knowledge Assistant evaluation on the new M51 corpus (SYNTHETIC).

    python tools/quality/knowledge_eval_m51.py --split dev [--json OUT]
    python tools/quality/knowledge_eval_m51.py --split heldout --json OUT   # aggregates only

Sets
* ``dev``     - tests/m51_gold_questions.py split "dev"; may guide changes.
* ``heldout`` - split "heldout"; NEVER used to tune.  This tool prints and
                saves only aggregate metrics for it (no per-question rows,
                no failure list), refuses to run on a dirty work tree and
                records the exact commit, so each held-out run is tied to one
                frozen SHA.  Protocol: one run on the unchanged baseline, one
                run on the frozen final SHA; then the set is spent.

The M49 (40) and M50 (86) sets remain regression sets
(tools/quality/knowledge_eval_m50.py).  Per-question checks are those of the
M50 evaluator (independent SQL scope, page identity + sha256, openability,
unsupported numbers, fabricated ids, conflicts, injection) plus
``not_flagged`` for ordinary procedures.

Lexical / glossary / trigram retrieval is NOT semantic retrieval; semantic
retrieval and real generation are NOT RUN without a local model.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools" / "quality"))

from knowledge_eval_m49 import peak_rss_mb  # noqa: E402
from knowledge_eval_m50 import aggregate, run_set  # noqa: E402
from m51_gold_questions import GOLD_M51  # noqa: E402
from m51_knowledge_fixtures import DOCS as DOCS_M51  # noqa: E402
from m51_knowledge_fixtures import m51_corpus_db  # noqa: E402

CROSS = {"fa_to_en": lambda r: r["lang"] == "fa" and r["kind"] == "cross-lingual",
         "en_to_fa": lambda r: r["lang"] == "en" and r["kind"] == "cross-lingual",
         "mixed": lambda r: r["lang"] == "mixed"}


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()


def summarize(rows: list) -> dict:
    out = aggregate(rows)
    answerable = [r for r in rows if r["answerable"]]
    out["refusal_rate"] = round(sum(r["refused"] for r in rows) / len(rows), 4) if rows else None
    out["refused_answerable"] = sum(r["refused"] for r in answerable)
    out["procedures_flagged"] = sum(not r["checks"].get("ordinary text not flagged", True) for r in rows)
    return out


def evaluate(split: str) -> dict:
    wanted = [g for g in GOLD_M51 if g["split"] == split]
    db, ids = m51_corpus_db()
    try:
        rows = run_set(wanted, db, ids, roles=DOCS_M51)
    finally:
        db.engine.dispose()
    by_lang = defaultdict(list)
    for r in rows:
        by_lang[r["lang"]].append(r)
    summary = {
        "split": split, "commit": _git("rev-parse", "HEAD"), "overall": summarize(rows),
        "by_language": {k: summarize(v) for k, v in sorted(by_lang.items())},
        "cross_lingual": {k: summarize([r for r in rows if f(r)]) for k, f in CROSS.items()},
        "peak_rss_mb": peak_rss_mb(),
        "semantic_retrieval": "NOT RUN (no local embedding model installed)",
        "real_generation": "NOT RUN (no local LLM installed)",
    }
    if split == "dev":
        by_kind = defaultdict(list)
        for r in rows:
            by_kind[r["kind"]].append(r)
        summary["by_category"] = {k: summarize(v) for k, v in sorted(by_kind.items())}
        return {"summary": summary, "questions": rows}
    return {"summary": summary}     # held-out: aggregates only


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", required=True, choices=("dev", "heldout"))
    parser.add_argument("--json", help="write the result here")
    args = parser.parse_args(argv)
    if args.split == "heldout" and _git("status", "--porcelain"):
        print("refusing: held-out runs need a clean work tree (frozen commit)", file=sys.stderr)
        return 2
    result = evaluate(args.split)
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    s = result["summary"]
    print(json.dumps({k: s[k] for k in ("split", "commit", "overall", "cross_lingual")}, ensure_ascii=False,
                     indent=2))
    if args.split == "dev":
        for r in result["questions"]:
            if not r["all_checks"]:
                print("FAILED", r["id"], r["kind"], r["state"], r["evidence"][:3],
                      {k: v for k, v in r["checks"].items() if not v}, r["unsupported_numbers"] or "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
