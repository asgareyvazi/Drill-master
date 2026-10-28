"""Integrity of the M51 gold set (independent of the retriever and the answerer)."""
from __future__ import annotations

from collections import Counter

from core import knowledge_retrieval as kr
from m51_gold_questions import GOLD_M51
from m51_knowledge_fixtures import DOCS, LINKS, REJECTED, m51_corpus_db

REQUIRED_KINDS = {"cross-lingual", "mixed", "arabic-chars", "digits", "unit-spelling", "paraphrase-duration",
                  "paraphrase-depth", "paraphrase-pressure", "paraphrase-density", "paraphrase-frequency",
                  "synonym", "reorder", "conflict", "wrong-well", "wrong-report", "wrong-size", "partial-overlap",
                  "unanswerable", "no-page", "empty-scope", "injection", "procedure"}


def test_size_splits_and_unique_ids():
    ids = [g["id"] for g in GOLD_M51]
    assert len(ids) == len(set(ids)) >= 100
    splits = Counter(g["split"] for g in GOLD_M51)
    assert set(splits) == {"dev", "heldout"} and min(splits.values()) >= 40


def test_every_required_category_is_in_both_splits_or_at_least_once():
    kinds = {g["kind"] for g in GOLD_M51}
    assert REQUIRED_KINDS <= kinds
    for lang in ("en", "fa", "mixed", "ar"):
        assert any(g["lang"] == lang for g in GOLD_M51)
    # Cross-lingual in both directions, in both splits.
    for split in ("dev", "heldout"):
        assert any(g["split"] == split and g["kind"] == "cross-lingual" and g["lang"] == "fa" for g in GOLD_M51)
        assert any(g["split"] == split and g["kind"] == "cross-lingual" and g["lang"] == "en" for g in GOLD_M51)


def test_labels_are_supported_by_the_gold_page_text():
    for g in GOLD_M51:
        for role, page in g["gold"]:
            assert role in DOCS and 1 <= page <= len(DOCS[role][2]) and (role, page) not in REJECTED, g["id"]
        if g["expect"] == "ready":
            assert g["gold"], g["id"]
            text = kr.fold(" ".join(DOCS[r][2][p - 1] for r, p in g["gold"]))
            for needle in g.get("include", []):
                assert kr.fold(needle) in text, (g["id"], needle)


def test_corpus_builds_with_the_rejected_page_left_out():
    db, ids = m51_corpus_db()
    try:
        snapshot = kr.read_corpus(db)
        assert len(snapshot.pages) == sum(len(p) for _n, _m, p in DOCS.values()) - len(REJECTED)
        assert not any("qx7" in kr.fold(p.text) for p in snapshot.pages.values())
        linked = {ids[d] for d, _w, _r in LINKS}
        assert ids["catalog"] not in linked and ids["inject_m51"] not in linked
    finally:
        db.engine.dispose()
