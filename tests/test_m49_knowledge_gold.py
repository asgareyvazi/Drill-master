"""M49 - gold-question evaluation gate (SYNTHETIC corpus, hand-labelled gold).

Hard invariants are exact (0 scope violations, 0 identity / open errors,
0 unapproved leaks, 0 answers to unanswerable questions, every conflict and
injection case).  The two ratio floors are deliberately BELOW the measured
values (measured at M49: Recall@5 1.0, state accuracy 38/40 = 0.95) so a
legitimate tie change does not fail the gate, while a real regression does.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "quality"))
sys.path.insert(0, str(ROOT / "tests"))

import knowledge_eval_m49 as ev  # noqa: E402
from m49_gold_questions import GOLD  # noqa: E402


@pytest.fixture(scope="module")
def result():
    return ev.evaluate()


def test_gold_set_shape():
    assert len(GOLD) >= 30 and len({q["id"] for q in GOLD}) == len(GOLD)
    langs = {q["lang"] for q in GOLD}
    assert langs == {"en", "fa", "mixed"}
    kinds = {q["kind"] for q in GOLD}
    for required in ("exact", "paraphrase", "arabic-letters", "english", "mixed", "scoped", "missing-page",
                     "multi-doc", "not-in-corpus", "injection", "unapproved", "edited-page", "wrong-size"):
        assert required in kinds, required
    assert any(q.get("conflict") for q in GOLD)


def test_hard_invariants(result):
    s = result["summary"]
    assert s["evidence_items"] > 50
    assert (s["scope_violations"], s["identity_errors"], s["open_errors"], s["unapproved_leaks"]) == (0, 0, 0, 0)
    assert s["false_answers_on_unanswerable"] == 0
    done, total = map(int, s["no_evidence_correct"].split("/"))
    assert done == total >= 9
    for key in ("conflict_detection", "injection_flagged_not_answered", "forbidden_value_absent"):
        done, total = map(int, s[key].split("/"))
        assert done == total > 0, key
    assert all(s["stub_model_guards"].values()), s["stub_model_guards"]


def test_ratio_floors(result):
    s = result["summary"]
    assert s["hybrid_recall_at_5"] >= 0.9
    assert s["state_accuracy"] >= 0.9
    assert s["hybrid_mrr"] >= 0.85


def test_not_run_items_are_labelled(result):
    s = result["summary"]
    assert s["semantic_retrieval"].startswith("NOT RUN") and s["real_generation"].startswith("NOT RUN")
