#!/usr/bin/env python3
"""M51 §5 forensic trace of chosen gold questions (SYNTHETIC corpus, no model).

For every question id: the question terms, strict identifiers, entity codes,
answer types, glossary expansions, ranked lists used, the top passages
(document role, page, fused score, coverage, the terms that passage misses),
best coverage, missing / absent terms, conflicts, the decision (answer
state) and the reason the pipeline gives (notes).  No passage text is
printed (ids, terms and numbers only).

    python tools/quality/knowledge_forensics_m51.py N55 N59 ... [--json OUT]       # M50 set
    python tools/quality/knowledge_forensics_m51.py --set m51 M038 ... [--json OUT]  # M51 DEV only

M51 held-out ids are refused: that split is looked at only in aggregate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from core import knowledge_answer as ka  # noqa: E402
from core import knowledge_retrieval as kr  # noqa: E402
from m50_gold_questions import GOLD_M50  # noqa: E402
from m50_knowledge_fixtures import DOCS as DOCS_M50  # noqa: E402
from m50_knowledge_fixtures import m50_corpus_db  # noqa: E402
from m49_knowledge_fixtures import DOCS as DOCS_M49  # noqa: E402
from m51_gold_questions import GOLD_M51  # noqa: E402
from m51_knowledge_fixtures import DOCS as DOCS_M51  # noqa: E402
from m51_knowledge_fixtures import m51_corpus_db  # noqa: E402

TOP_K = 5


def trace(index, ids, q) -> dict:
    role_of = {ids[k]: k for k in list(DOCS_M49) + list(DOCS_M50) + list(DOCS_M51) if k in ids}
    target = ids[q["target"]] if q.get("target") else None
    answer = ka.answer_question(index, q["question"], q["scope"], target, top_k=TOP_K)
    r = answer.retrieval
    expansions = index._expansions_by_term(r.terms, kr.glossary_expansions(q["question"]))
    hits = []
    for h in r.hits:
        _cov, missing = index.coverage(r.terms, expansions, h.chunk.chunk_id, r.strict_terms, r.entity_codes)
        hits.append({"page": f"{role_of.get(h.page.document_id, h.page.document_id)}:p{h.page.page_no}",
                     "score": round(h.score, 5), "coverage": round(h.coverage, 3),
                     "lists": sorted(h.ranks), "missing": missing})
    gold = [f"{role}:p{page}" for role, page in q["gold"]]
    return {
        "id": q["id"], "split": q["split"], "lang": q["lang"], "kind": q["kind"], "expect": q["expect"],
        "gold": gold, "terms": r.terms, "strict_terms": list(r.strict_terms or []),
        "entity_codes": sorted(r.entity_codes or []), "answer_types": list(r.answer_types or []),
        "expansions": r.expansions, "lists_used": r.lists_used, "hits": hits,
        "best_coverage": round(r.best_coverage, 3), "missing_terms": r.missing_terms,
        "absent_terms": r.absent_terms, "conflicts": len(r.conflicts),
        "decision": answer.state, "mode": answer.mode, "reason": answer.notes,
        "answer_numbers": sorted(ka._numbers(answer.text)) if answer.state == "ready" else [],
        "gold_in_top5": any(h["page"] in gold for h in hits),
        "flagged_evidence": [e.label for e in answer.evidence if e.instruction_like or e.page_instruction_like],
        "correct": answer.state == q["expect"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="+")
    parser.add_argument("--json")
    parser.add_argument("--set", default="m50", choices=("m50", "m51"))
    args = parser.parse_args(argv)
    gold = GOLD_M50 if args.set == "m50" else GOLD_M51
    by_id = {q["id"]: q for q in gold}
    if args.set == "m51" and any(by_id[i]["split"] != "dev" for i in args.ids):
        parser.error("M51 held-out questions are looked at only in aggregate")
    db, ids = (m50_corpus_db if args.set == "m50" else m51_corpus_db)()
    index = kr.KnowledgeIndex(kr.read_corpus(db))
    try:
        rows = [trace(index, ids, by_id[i]) for i in args.ids]
    finally:
        index.close()
        db.engine.dispose()
    out = json.dumps({"questions": rows}, indent=1, ensure_ascii=False)
    if args.json:
        Path(args.json).write_text(out + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
