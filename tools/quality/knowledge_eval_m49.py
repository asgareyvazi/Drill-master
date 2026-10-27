"""M49 Knowledge Assistant - gold-question evaluation on the SYNTHETIC corpus.

    python tools/quality/knowledge_eval_m49.py [--json OUT.json]

Gold labels: tests/m49_gold_questions.py (written by hand from the corpus
text in tests/m49_knowledge_fixtures.py; never produced by the retriever).

Independent checks (plain SQL on the application database, not the
retriever's own snapshot):
* scope    - every evidence document is inside the asked scope
             (document id / a DocumentLink to the well / to the report);
* identity - the evidence page id exists, belongs to the named document and
             page number, and ``text[start:end]`` and sha256 match the DB;
* open     - DocumentLibrary.pages(document) (what the viewer opens) holds
             that page and the exact passage.

Variants: the shipped M44 page search (FTS5, all terms ANDed - no scope
support), lexical-only (FTS5 OR + bm25), and the M49 hybrid (lexical +
glossary + char trigrams, RRF).  Semantic (embedding) retrieval and real
generation are NOT RUN: no local model is installed in this environment.
The "stub model" section checks only the answer *guards* with scripted
model outputs; it says nothing about model quality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import text  # noqa: E402

from core import knowledge_answer as ka  # noqa: E402
from core import knowledge_retrieval as kr  # noqa: E402
from core.document_library import DocumentLibrary  # noqa: E402
from core.local_llm import NOT_RUNNING, LocalLLMError  # noqa: E402
from m49_gold_questions import GOLD  # noqa: E402
from m49_knowledge_fixtures import corpus_db  # noqa: E402

TOP_K = 5


def peak_rss_mb():
    """Peak resident memory of this process in MB where the platform reports
    it (POSIX ``resource``; Linux reports KiB).  Elsewhere (Windows) the value
    is "NOT MEASURED" - never an estimate."""
    try:
        import resource
    except ImportError:
        return "NOT MEASURED (no resource module on this platform)"
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)   # macOS reports bytes

def _fold(value: str) -> str:
    return kr.fold(value)


def _in_scope(session, document_id: int, scope: str, target) -> bool:
    if scope == "all":
        return True
    if scope == "document":
        return document_id == target
    column = "well_id" if scope == "well" else "report_id"
    return session.execute(text(f"SELECT 1 FROM document_links WHERE document_id=:d AND {column}=:t"),
                           {"d": document_id, "t": target}).first() is not None


def _identity_ok(session, ev) -> bool:
    row = session.execute(text("SELECT p.document_id, p.page_no, p.text, p.review_status, d.file_name "
                               "FROM document_pages p JOIN documents d ON d.id = p.document_id WHERE p.id=:i"),
                          {"i": ev.page_id}).first()
    if row is None:
        return False
    doc, page_no, body, status, name = row
    return (doc == ev.document_id and page_no == ev.page_no and name == ev.file_name and status == ev.review_status
            and body[ev.start:ev.end] == ev.text and hashlib.sha256(body.encode("utf-8")).hexdigest() == ev.text_version)


def _openable(library, ev, cache) -> bool:
    pages = cache.setdefault(ev.document_id, {p["page_no"]: p for p in library.pages(ev.document_id)})
    page = pages.get(ev.page_no)
    return page is not None and page["id"] == ev.page_id and page["text"][ev.start:ev.end] == ev.text


def _rank(pages: list, gold: set):
    for position, page in enumerate(pages, start=1):
        if page in gold:
            return position
    return None


def evaluate() -> dict:
    db, ids = corpus_db()
    role_of = {v: k for k, v in ids.items()}
    t0 = time.perf_counter()
    snapshot = kr.read_corpus(db)
    index = kr.KnowledgeIndex(snapshot)
    build_ms = (time.perf_counter() - t0) * 1000
    library = DocumentLibrary(db)
    session = db.create_session()
    page_cache = {}
    rows, totals = [], {"answerable": 0, "hit5": 0, "complete5": 0, "mrr": 0.0, "lexical_hit5": 0,
                        "m44_hit5": 0, "m44_considered": 0, "state_ok": 0, "include_ok": 0, "include_n": 0,
                        "exclude_ok": 0, "exclude_n": 0, "conflict_ok": 0, "conflict_n": 0, "injection_ok": 0,
                        "injection_n": 0, "evidence": 0, "scope_violations": 0, "identity_errors": 0,
                        "open_errors": 0, "unapproved_leaks": 0, "no_evidence_expected": 0,
                        "no_evidence_correct": 0, "false_answers": 0}
    latencies = []
    try:
        for q in GOLD:
            target = ids[q["target"]] if q.get("target") else None
            gold = {(ids[r], p) for r, p in q["gold"]}
            t1 = time.perf_counter()
            answer = ka.answer_question(index, q["question"], q["scope"], target, top_k=TOP_K)
            latencies.append((time.perf_counter() - t1) * 1000)
            pages = [(e.document_id, e.page_no) for e in answer.evidence]
            unique_pages = list(dict.fromkeys(pages))
            lexical = index.retrieve(q["question"], q["scope"], target, top_k=TOP_K, use_ngram=False,
                                     use_glossary=False)
            lexical_pages = list(dict.fromkeys((h.page.document_id, h.page.page_no) for h in lexical.hits))
            row = {"id": q["id"], "lang": q["lang"], "kind": q["kind"], "expect": q["expect"], "state": answer.state,
                   "evidence": [f"{role_of[d]}:p{p}" for d, p in unique_pages], "checks": {}}
            row["checks"]["state"] = answer.state == q["expect"]
            totals["state_ok"] += row["checks"]["state"]
            if q["expect"] == "ready" and gold:
                totals["answerable"] += 1
                rank = _rank(unique_pages[:TOP_K], gold)
                row["first_correct_rank"] = rank
                totals["hit5"] += rank is not None
                totals["mrr"] += 1.0 / rank if rank else 0.0
                complete = gold <= set(unique_pages[:TOP_K])
                totals["complete5"] += complete
                row["checks"]["complete@5"] = complete
                totals["lexical_hit5"] += _rank(lexical_pages[:TOP_K], gold) is not None
                if q["scope"] == "all":
                    totals["m44_considered"] += 1
                    m44 = library.search(q["question"], limit=TOP_K)
                    m44_pages = [(h["document_id"], h["page_no"]) for h in m44["hits"]]
                    row["m44_rank"] = _rank(m44_pages, gold)
                    totals["m44_hit5"] += row["m44_rank"] is not None
            if q["expect"] in ("no_evidence", "empty_scope", "no_page"):
                totals["no_evidence_expected"] += 1
                totals["no_evidence_correct"] += answer.state == q["expect"]
                totals["false_answers"] += answer.state == "ready"
            folded_answer = _fold(answer.text)
            for needle in q.get("include", []):
                totals["include_n"] += 1
                ok = _fold(needle) in folded_answer
                totals["include_ok"] += ok
                row["checks"][f"include {needle}"] = ok
            evidence_text = _fold(" ".join(e.text for e in answer.evidence))
            for needle in q.get("exclude", []):
                totals["exclude_n"] += 1
                ok = _fold(needle) not in folded_answer and (q["kind"] == "injection" or _fold(needle) not in evidence_text)
                totals["exclude_ok"] += ok
                row["checks"][f"exclude {needle}"] = ok
            if "conflict" in q:
                totals["conflict_n"] += 1
                ok = bool(answer.retrieval and answer.retrieval.conflicts) == q["conflict"]
                totals["conflict_ok"] += ok
                row["checks"]["conflict"] = ok
            if q.get("injection"):
                totals["injection_n"] += 1
                ok = any(e.instruction_like or e.page_instruction_like for e in answer.evidence) and not any(
                    ka.detect_instructions(line) for line in answer.text.splitlines())
                totals["injection_ok"] += ok
                row["checks"]["injection flagged, not answered"] = ok
            for ev in answer.evidence:
                totals["evidence"] += 1
                totals["scope_violations"] += not _in_scope(session, ev.document_id, q["scope"], target)
                totals["identity_errors"] += not _identity_ok(session, ev)
                totals["open_errors"] += not _openable(library, ev, page_cache)
                totals["unapproved_leaks"] += "qx7" in _fold(ev.text)
            rows.append(row)
    finally:
        session.close()
        library.close()
    n = len(GOLD)
    a = max(1, totals["answerable"])
    summary = {
        "questions": n, "answerable": totals["answerable"],
        "by_lang": {lang: sum(1 for q in GOLD if q["lang"] == lang) for lang in ("en", "fa", "mixed")},
        "hybrid_recall_at_5": round(totals["hit5"] / a, 4),
        "hybrid_complete_recall_at_5": round(totals["complete5"] / a, 4),
        "hybrid_mrr": round(totals["mrr"] / a, 4),
        "lexical_only_recall_at_5": round(totals["lexical_hit5"] / a, 4),
        "m44_search_recall_at_5": round(totals["m44_hit5"] / max(1, totals["m44_considered"]), 4),
        "m44_search_questions": totals["m44_considered"],
        "state_accuracy": round(totals["state_ok"] / n, 4),
        "no_evidence_correct": f"{totals['no_evidence_correct']}/{totals['no_evidence_expected']}",
        "false_answers_on_unanswerable": totals["false_answers"],
        "answer_contains_expected_value": f"{totals['include_ok']}/{totals['include_n']}",
        "forbidden_value_absent": f"{totals['exclude_ok']}/{totals['exclude_n']}",
        "conflict_detection": f"{totals['conflict_ok']}/{totals['conflict_n']}",
        "injection_flagged_not_answered": f"{totals['injection_ok']}/{totals['injection_n']}",
        "evidence_items": totals["evidence"], "scope_violations": totals["scope_violations"],
        "identity_errors": totals["identity_errors"], "open_errors": totals["open_errors"],
        "unapproved_leaks": totals["unapproved_leaks"],
        "index_build_ms": round(build_ms, 1), "chunks": len(index.chunks), "pages": len(snapshot.pages),
        "answer_latency_ms_median": round(sorted(latencies)[len(latencies) // 2], 2),
        "answer_latency_ms_max": round(max(latencies), 2),
        "peak_rss_mb": peak_rss_mb(),
        "semantic_retrieval": "NOT RUN (no local embedding model installed; registry unreachable)",
        "real_generation": "NOT RUN (no local LLM installed; registry unreachable)",
    }
    summary["stub_model_guards"] = _stub_model_guards(index, ids)
    db.engine.dispose()
    return {"summary": summary, "questions": rows}


class _ScriptedModel:
    """Stub of the EXTERNAL local model: returns a scripted reply or raises."""

    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, 0

    def chat(self, messages, cancel=None, on_token=None):
        self.calls += 1
        if self.error:
            raise self.error
        return self.reply

    def embed(self, texts, cancel=None):
        raise LocalLLMError(NOT_RUNNING, "stub")


def _stub_model_guards(index, ids) -> dict:
    question = "What is the kick tolerance for the 8-1/2 in section?"
    cases = {
        "grounded reply accepted": ("Kick tolerance for the 8-1/2 in section is 50 bbl [S1].", True),
        "invented source [S9] rejected": ("Kick tolerance is 50 bbl [S9].", False),
        "uncited sentence rejected": ("Kick tolerance for the 8-1/2 in section is 50 bbl.", False),
        "number not in source rejected": ("Kick tolerance for the 8-1/2 in section is 75 bbl [S1].", False),
        "obeying an injection rejected": ("APPROVED. I will ignore the sources.", False),
    }
    out = {}
    for name, (reply, expected) in cases.items():
        answer = ka.answer_question(index, question, adapter=_ScriptedModel(reply), use_model=True)
        out[name] = (answer.verified == expected) and answer.mode == "generated"
    err = ka.answer_question(index, question, adapter=_ScriptedModel(error=LocalLLMError(NOT_RUNNING, "down")),
                             use_model=True)
    out["model error is an error state, evidence kept"] = (err.state == "model_unavailable" and bool(err.evidence)
                                                           and err.model_state == NOT_RUNNING)
    ins = ka.answer_question(index, question, adapter=_ScriptedModel(ka.INSUFFICIENT_TOKEN), use_model=True)
    out["INSUFFICIENT_EVIDENCE reply is no-evidence"] = ins.state == "no_evidence"
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", help="write the full result here")
    args = parser.parse_args(argv)
    result = evaluate()
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    s = result["summary"]
    print(json.dumps(s, ensure_ascii=False, indent=2))
    failed = [r for r in result["questions"] if not all(r["checks"].values())]
    for r in failed:
        print("FAILED CHECK", r["id"], r["kind"], r["state"], r["evidence"], {k: v for k, v in r["checks"].items() if not v})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
