"""M50 - gold evaluation gate: 40 M49 + 86 M50 questions (SYNTHETIC, hand-labelled).

Hard invariants are exact on EVERY split (0 scope violations, identity / open
errors, unapproved leaks, fabricated citation ids, unsupported numbers,
number/unit confusions, wrong-size answers).  Ratio floors sit BELOW the
values measured at M50 so a legitimate tie change does not fail the gate:

    split    measured (retrieval v3)                    floor here
    m49      40/40, 0 false answers, MRR 1.0            >= 39/40, 0, >= 0.9
    dev      41/43, 0 false answers                     >= 39/43, 0
    heldout  official (1ec2dca, evaluated once): 35/43,    >= 34/43, <= 3
             4 false answers, all pre-existing since M49.
             Final code (post-hoc, held-out spent): 35/43,
             3 false answers (+N62 paragraph-injection fix,
             -N45 after dropping glossary entries without
             dev evidence)

The held-out floor is a no-regression guard, not a tuning target: the
remaining held-out false answers (missing well code is a weight, not a veto;
undetected Persian instruction) are open findings in the M50 report.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "quality"))
sys.path.insert(0, str(ROOT / "tests"))

import knowledge_eval_m50 as ev  # noqa: E402
from m50_gold_questions import GOLD_M50  # noqa: E402


@pytest.fixture(scope="module")
def result():
    return ev.evaluate("all")


def test_gold_set_shape():
    assert len(GOLD_M50) >= 80 and len({q["id"] for q in GOLD_M50}) == len(GOLD_M50)
    splits = {s: [q for q in GOLD_M50 if q["split"] == s] for s in ("dev", "heldout")}
    assert set(q["split"] for q in GOLD_M50) == {"dev", "heldout"}
    assert min(len(v) for v in splits.values()) >= 40
    kinds = {q["kind"] for q in GOLD_M50}
    for required in ("exact", "persian", "mixed", "arabic-letters", "digits", "units", "number-unit", "decimals",
                     "abbreviation", "paraphrase-quantity", "reordering", "scoped", "conflict", "wrong-size",
                     "wrong-well", "unanswerable", "partial-overlap", "injection", "cross-lingual", "no-page"):
        assert required in kinds, required
    assert {q["lang"] for q in GOLD_M50} == {"en", "fa", "mixed"}


def test_hard_invariants_on_every_split(result):
    for split, s in result["summary"]["by_split"].items():
        for key in ("scope_violations", "identity_errors", "open_errors", "unapproved_leaks", "fabricated_ids",
                    "unsupported_numbers", "number_unit_confusions", "wrong_size_false_answers",
                    "citation_check_failures"):
            assert s[key] == 0, (split, key, s[key])


def _done(s):
    return int(s["all_checks"].split("/")[0])


def test_m49_questions_and_their_former_failures(result):
    s = result["summary"]["by_split"]["m49"]
    assert _done(s) >= 39 and s["false_answers_on_unanswerable"] == 0
    assert s["mrr"] >= 0.9 and s["refusal_precision"] >= 0.9
    rows = {r["id"]: r for r in result["questions"] if r["split"] == "m49"}
    for qid in ("Q09", "Q16", "Q19"):          # the three M49 failures, fixed by general mechanisms
        assert rows[qid]["all_checks"], (qid, rows[qid]["checks"])


def test_dev_split_floors(result):
    s = result["summary"]["by_split"]["dev"]
    assert _done(s) >= 39 and s["false_answers_on_unanswerable"] == 0
    assert s["recall_at_5"] >= 0.9 and s["refusal_recall"] >= 0.9


def test_heldout_does_not_regress(result):
    s = result["summary"]["by_split"]["heldout"]
    assert _done(s) >= 34
    assert s["false_answers_on_unanswerable"] <= 3


def test_not_run_items_are_labelled(result):
    s = result["summary"]
    assert s["semantic_retrieval"].startswith("NOT RUN") and s["real_generation"].startswith("NOT RUN")


def test_m50_modules_import_without_posix_only_modules():
    """Windows has no ``resource``/``fcntl``: import every M50 knowledge module
    in a fresh interpreter in which those modules are unavailable."""
    import subprocess
    code = ("import sys\n"
            "for name in ('resource', 'fcntl', 'termios', 'pwd', 'grp'): sys.modules[name] = None\n"
            f"sys.path[:0] = [{str(ROOT)!r}, {str(ROOT / 'tests')!r}, {str(ROOT / 'tools' / 'quality')!r}]\n"
            "import importlib\n"
            "for m in ('knowledge_eval_m50', 'm50_knowledge_fixtures', 'm50_gold_questions',\n"
            "          'test_m50_knowledge_retrieval', 'test_m50_knowledge_gold'):\n"
            "    importlib.import_module(m)\n"
            "print('ok')\n")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr[-2000:]
