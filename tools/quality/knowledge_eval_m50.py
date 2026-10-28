"""M50 Knowledge Assistant evaluation: 40 M49 + 86 M50 gold questions (SYNTHETIC).

    python tools/quality/knowledge_eval_m50.py [--split all|dev|heldout|m49] [--json OUT.json]

Sets
* ``m49``     - tests/m49_gold_questions.py (unchanged) on the M49 corpus;
                tuned on in M49, so development data.
* ``dev``     - M50 questions with split "dev" on the M50 corpus.
* ``heldout`` - M50 questions with split "heldout" on the M50 corpus.  NEVER
                used to tune anything (see tests/m50_gold_questions.py).

Independent checks reuse tools/quality/knowledge_eval_m49.py (plain SQL scope,
page identity + sha256, DocumentLibrary openability).  Added here:
* unsupported numbers - numbers in the answer that occur in none of the
  cited passages (citations / page labels removed first);
* fabricated ids      - [S n] labels in the answer with no evidence item n;
* number/unit confusion - a forbidden value (same number, other unit or
  quantity) in the answer of a ``number-unit`` question;
* refusal precision / recall, top-1 document+page accuracy, answered rate.

Semantic retrieval and real generation are NOT RUN unless a local model is
installed (none in the environment this was written in); lexical/glossary/
trigram retrieval is not semantic retrieval.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools" / "quality"))

from core import knowledge_answer as ka  # noqa: E402
from core import knowledge_retrieval as kr  # noqa: E402
from core.document_library import DocumentLibrary  # noqa: E402
from knowledge_eval_m49 import _identity_ok, _in_scope, _openable, _rank, peak_rss_mb  # noqa: E402
from m49_gold_questions import GOLD as GOLD_M49  # noqa: E402
from m49_knowledge_fixtures import DOCS as DOCS_M49  # noqa: E402
from m49_knowledge_fixtures import corpus_db  # noqa: E402
from m50_gold_questions import GOLD_M50  # noqa: E402
from m50_knowledge_fixtures import DOCS as DOCS_M50  # noqa: E402
from m50_knowledge_fixtures import m50_corpus_db  # noqa: E402

TOP_K = 5
REFUSALS = ("no_evidence", "empty_scope", "no_page")
_LABEL = re.compile(r"\[S(\d+)\]")
_PAGE_WORDS = re.compile(r"\b(?:page|p\.)\s*\d+|صفحه\s*\d+", re.IGNORECASE)


def _numbers(text: str) -> set:
    return {n for n in ka._numbers(_PAGE_WORDS.sub(" ", _LABEL.sub(" ", text)))}


def run_set(questions: list, db, ids: dict, roles=None) -> list:
    # Document, well and report ids share one integer space: map document roles only.
    roles = list(DOCS_M49) + list(DOCS_M50) if roles is None else list(roles)
    role_of = {ids[k]: k for k in roles if k in ids}
    index = kr.KnowledgeIndex(kr.read_corpus(db))
    library = DocumentLibrary(db)
    session = db.create_session()
    cache, rows = {}, []
    try:
        for q in questions:
            target = ids[q["target"]] if q.get("target") else None
            gold = {(ids[r], p) for r, p in q["gold"]}
            t0 = time.perf_counter()
            answer = ka.answer_question(index, q["question"], q["scope"], target, top_k=TOP_K)
            latency = (time.perf_counter() - t0) * 1000
            pages = list(dict.fromkeys((e.document_id, e.page_no) for e in answer.evidence))
            lexical = index.retrieve(q["question"], q["scope"], target, top_k=TOP_K, use_ngram=False,
                                     use_glossary=False)
            lexical_pages = list(dict.fromkeys((h.page.document_id, h.page.page_no) for h in lexical.hits))
            folded = kr.fold(answer.text)
            evidence_text = kr.fold(" ".join(e.text for e in answer.evidence))
            row = {"id": q["id"], "split": q.get("split", "m49"), "lang": q["lang"], "kind": q["kind"],
                   "expect": q["expect"], "state": answer.state, "latency_ms": latency,
                   "evidence": [f"{role_of[d]}:p{p}" for d, p in pages], "checks": {}}
            row["checks"]["state"] = answer.state == q["expect"]
            row["answerable"] = q["expect"] == "ready" and bool(gold)
            if row["answerable"]:
                rank = _rank(pages[:TOP_K], gold)
                row["rank"] = rank
                row["complete"] = gold <= set(pages[:TOP_K])
                row["top1"] = bool(pages) and pages[0] in gold
                row["lexical_hit"] = _rank(lexical_pages[:TOP_K], gold) is not None
                row["checks"]["recall@5"] = rank is not None
                if q.get("all_gold"):
                    row["checks"]["complete@5"] = row["complete"]
            row["refused"] = answer.state in REFUSALS
            row["refusal_expected"] = q["expect"] in REFUSALS
            for needle in q.get("include", []):
                row["checks"][f"include {needle}"] = kr.fold(needle) in folded
            row["excluded_in_closest"] = 0
            for needle in q.get("exclude", []):
                in_evidence = kr.fold(needle) in evidence_text
                # A refusal shows the closest passages marked insufficient (M49 design): then a
                # forbidden value is checked in the ANSWER and counted separately in the evidence.
                lenient = q["kind"] == "injection" or answer.state in REFUSALS
                row["checks"][f"exclude {needle}"] = kr.fold(needle) not in folded and (lenient or not in_evidence)
                row["excluded_in_closest"] += int(in_evidence and answer.state in REFUSALS)
            if "conflict" in q:
                row["checks"]["conflict"] = bool(answer.retrieval and answer.retrieval.conflicts) == q["conflict"]
            if q.get("injection"):
                row["checks"]["injection flagged, not obeyed"] = any(
                    e.instruction_like or e.page_instruction_like for e in answer.evidence) and not any(
                    ka.detect_instructions(line) for line in answer.text.splitlines())
            if q.get("not_flagged"):    # ordinary procedure text is not an instruction to the assistant
                row["checks"]["ordinary text not flagged"] = not any(
                    e.instruction_like or e.page_instruction_like for e in answer.evidence)
            labels = {int(n) for n in _LABEL.findall(answer.text)}
            row["fabricated_ids"] = sum(1 for n in labels if not 1 <= n <= len(answer.evidence))
            row["unsupported_numbers"] = sorted(_numbers(answer.text) - _numbers(evidence_text)) \
                if answer.state == "ready" else []
            row["scope_violations"] = sum(not _in_scope(session, e.document_id, q["scope"], target)
                                          for e in answer.evidence)
            row["identity_errors"] = sum(not _identity_ok(session, e) for e in answer.evidence)
            row["open_errors"] = sum(not _openable(library, e, cache) for e in answer.evidence)
            row["unapproved_leaks"] = sum("qx7" in kr.fold(e.text) for e in answer.evidence)
            # Every answer shown as ready must pass the citation checks (M50 verifier dimensions).
            passed = answer.check is not None and answer.check.citation_checks_passed
            row["citation_check_failed"] = answer.state == "ready" and not passed
            row["failed_dimensions"] = sorted(k for k, v in answer.check.dimensions.items() if v is False) \
                if answer.state == "ready" and answer.check is not None else []
            row["all_checks"] = all(row["checks"].values())
            rows.append(row)
    finally:
        session.close()
        library.close()
        index.close()
    return rows


def aggregate(rows: list) -> dict:
    if not rows:
        return {}
    ans = [r for r in rows if r["answerable"]]
    refused = [r for r in rows if r["refused"]]
    expected_refusals = [r for r in rows if r["refusal_expected"]]
    nu = [r for r in rows if r["kind"] == "number-unit"]
    lat = [r["latency_ms"] for r in rows]

    def rate(items, key):
        return round(sum(1 for r in items if r.get(key)) / len(items), 4) if items else None
    return {
        "n": len(rows), "answerable": len(ans),
        "all_checks": f"{sum(r['all_checks'] for r in rows)}/{len(rows)}",
        "recall_at_5": rate(ans, "rank"),
        "complete_evidence_recall_at_5": rate(ans, "complete"),
        "mrr": round(sum(1 / r["rank"] for r in ans if r.get("rank")) / len(ans), 4) if ans else None,
        "top1_doc_page_accuracy": rate(ans, "top1"),
        "answered_rate": round(sum(r["state"] == "ready" for r in ans) / len(ans), 4) if ans else None,
        "lexical_only_recall_at_5": rate(ans, "lexical_hit"),
        "refusal_precision": round(sum(r["refusal_expected"] for r in refused) / len(refused), 4) if refused else None,
        "refusal_recall": round(sum(r["refused"] for r in expected_refusals) / len(expected_refusals), 4)
        if expected_refusals else None,
        "false_answers_on_unanswerable": sum(r["state"] == "ready" for r in expected_refusals),
        "wrong_size_false_answers": sum(r["state"] == "ready" for r in rows if r["kind"] == "wrong-size"),
        "number_unit_confusions": sum(not v for r in nu for k, v in r["checks"].items() if k.startswith("exclude")),
        "unsupported_numbers": sum(len(r["unsupported_numbers"]) for r in rows),
        "excluded_value_in_closest_passages": sum(r["excluded_in_closest"] for r in rows),
        "fabricated_ids": sum(r["fabricated_ids"] for r in rows),
        "scope_violations": sum(r["scope_violations"] for r in rows),
        "identity_errors": sum(r["identity_errors"] for r in rows),
        "open_errors": sum(r["open_errors"] for r in rows),
        "unapproved_leaks": sum(r["unapproved_leaks"] for r in rows),
        "citation_check_failures": sum(r["citation_check_failed"] for r in rows),
        "include_ok": f"{sum(v for r in rows for k, v in r['checks'].items() if k.startswith('include'))}/"
                      f"{sum(1 for r in rows for k in r['checks'] if k.startswith('include'))}",
        "latency_ms_median": round(statistics.median(lat), 2), "latency_ms_max": round(max(lat), 2),
    }


def evaluate(split: str = "all") -> dict:
    rows = []
    if split in ("all", "m49"):
        db, ids = corpus_db()
        try:
            rows += run_set(GOLD_M49, db, ids)
        finally:
            db.engine.dispose()
    if split in ("all", "dev", "heldout"):
        wanted = [g for g in GOLD_M50 if split == "all" or g["split"] == split]
        db, ids = m50_corpus_db()
        try:
            rows += run_set(wanted, db, ids)
        finally:
            db.engine.dispose()
    by_split, by_kind, by_lang = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in rows:
        by_split[r["split"]].append(r)
        by_kind[r["kind"]].append(r)
        by_lang[r["lang"]].append(r)
    cross = [r for r in rows if r["kind"] == "cross-lingual" or r["lang"] == "mixed"]
    summary = {
        "split": split, "overall": aggregate(rows),
        "by_split": {k: aggregate(v) for k, v in sorted(by_split.items())},
        "by_language": {k: aggregate(v) for k, v in sorted(by_lang.items())},
        "cross_lingual_and_mixed": aggregate(cross),
        "by_category": {k: aggregate(v) for k, v in sorted(by_kind.items())},
        "peak_rss_mb": peak_rss_mb(),
        "semantic_retrieval": "NOT RUN (no local embedding model installed)",
        "real_generation": "NOT RUN (no local LLM installed)",
    }
    return {"summary": summary, "questions": rows}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", default="all", choices=("all", "dev", "heldout", "m49"))
    parser.add_argument("--json", help="write the full result here")
    parser.add_argument("--quiet", action="store_true", help="summary only (no per-question failures)")
    args = parser.parse_args(argv)
    result = evaluate(args.split)
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    s = result["summary"]
    print(json.dumps({"overall": s["overall"], "by_split": s["by_split"]}, ensure_ascii=False, indent=2))
    if not args.quiet:
        for r in result["questions"]:
            if not r["all_checks"]:
                print("FAILED", r["id"], r["split"], r["kind"], r["state"], r["evidence"][:3],
                      {k: v for k, v in r["checks"].items() if not v}, r["unsupported_numbers"] or "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
