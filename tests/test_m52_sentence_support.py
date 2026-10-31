"""M52 §2.3/2.4: a quoted sentence needs its own support (sentence-level evidence).

A well code stated once on a page - or only in the file name - makes the passage
eligible for a question about that well; it never makes an unrelated sentence on
that page an answer.  SYNTHETIC corpus written for M52 (new well codes SYN-QA-*;
the spent M51 held-out set is not used).  In-memory database; no model.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import knowledge_answer as ka  # noqa: E402
from core import knowledge_retrieval as kr  # noqa: E402

DOCS = {
    # The well code is in the file name only, except on page 3 (two similar codes on one page).
    "qa_notes": ("SYN-QA-21 rig notes.pdf", [
        "SYNTHETIC rig notes.\n\nGeneral remarks for the crew are kept here for reference only.",
        "The BOP test pressure was 5000 psi. The rig move took 3 days to complete.",
        "Offset well SYN-QA-12 used a mud weight of 1.30 sg. SYN-QA-21 mud weight is 1.18 sg.",
        "The planned cement slurry density is 1.90 sg. The revised cement slurry density is 1.95 sg.",
        "The 7 in liner shoe is at 3100 m. The top of cement for the 7 in liner is at 2650 m.",
        "Kick tolerance\n\nThe calculated limit is 48 bbl at the 9-5/8 in shoe. Crew change happened at noon.",
    ]),
    # A sentence that states only the asked well code, next to the one that answers.
    "qa_log": ("SYN-QA-21 daily log.pdf", [
        "This daily log belongs to SYN-QA-21. The trip tank volume was 12 m3 at midnight.",
    ]),
    # A heading names the subject; no sentence below it states anything about it.
    "qa_review": ("SYN-QA-21 office review.pdf", [
        "Swab and surge margin\n\nThe calculated limit was reviewed by the office team.",
    ]),
    # The file name states SYN-QB-31; the only page is about the similar well SYN-QB-13.
    "qb_notes": ("SYN-QB-31 handover notes.pdf", [
        "Offset well SYN-QB-13 reached 2000 m before the rig moved.",
    ]),
}


def _make_corpus():
    from document_link_fixtures import without_session_user
    from m49_knowledge_fixtures import make_db

    from core.database import Company, DocumentLink, Project, Well
    from core.document_library import PAGE_OK, READY, DocumentExtract, DocumentLibrary, PageDecision, PageExtract
    db = make_db()
    with without_session_user():
        session = db.create_session()
        try:
            company = Company(name="SYNTHETIC M52 SENTENCE CO", code="SYN-M52CO")
            session.add(company)
            session.flush()
            project = Project(name="SYNTHETIC M52 PROJECT", code="SYN-M52P", company_id=company.id)
            session.add(project)
            session.flush()
            ids = {}
            for key, name, code in (("well_q", "SYN-QA-21", "SYN-QA"), ("well_r", "SYN-QA-12", "SYN-QR"),
                                    ("well_b", "SYN-QB-31", "SYN-QB"), ("well_c", "SYN-QB-13", "SYN-QC")):
                well = Well(name=name, code=code, project_id=project.id)
                session.add(well)
                session.flush()
                ids[key] = well.id
            session.commit()
        finally:
            session.close()
        library = DocumentLibrary(db)
        try:
            for role, (name, pages) in DOCS.items():
                body = f"m52:{role}\x00" + "\x00".join(pages)
                extract = DocumentExtract(
                    path=f"/synthetic/m52/{role}", file_name=name, size_bytes=len(body.encode("utf-8")),
                    sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(), kind="pdf", page_count=len(pages),
                    status=READY, pages=[PageExtract(i, f"page {i}", text, "pdf-text", PAGE_OK)
                                         for i, text in enumerate(pages, start=1)])
                outcome = library.import_reviewed(extract, {i: PageDecision(approved=True)
                                                            for i in range(1, len(pages) + 1)})
                assert outcome.status == "imported", outcome.message
                ids[role] = outcome.document_id
        finally:
            library.close()
        session = db.create_session()
        try:
            session.add(DocumentLink(document_id=ids["qa_notes"], well_id=ids["well_q"], linked_by="synthetic"))
            session.add(DocumentLink(document_id=ids["qb_notes"], well_id=ids["well_b"], linked_by="synthetic"))
            for role in ("qa_log", "qa_review"):
                session.add(DocumentLink(document_id=ids[role], well_id=ids["well_q"], linked_by="synthetic"))
            session.commit()
        finally:
            session.close()
    return db, ids


@pytest.fixture(scope="module")
def index():
    db, _ids = _make_corpus()
    return kr.KnowledgeIndex(kr.read_corpus(db))


def _quotes(index, question):
    answer = ka.answer_question(index, question)
    return answer, [line for line in (answer.text or "").splitlines() if line.startswith("•")]


def test_file_name_only_identity_quotes_only_the_sentence_that_answers(index):
    answer, quotes = _quotes(index, "BOP test pressure SYN-QA-21")
    assert answer.state == "ready" and quotes
    assert all("5000 psi" in q for q in quotes), quotes
    assert not any("rig move" in q for q in quotes), quotes            # same page, same inherited well code
    answer, quotes = _quotes(index, "How long did the rig move take for SYN-QA-21?")
    assert quotes and all("3 days" in q for q in quotes), quotes
    assert not any("psi" in q for q in quotes), quotes


def test_a_sentence_naming_a_similar_well_is_never_quoted(index):
    answer, quotes = _quotes(index, "mud weight SYN-QA-21")
    assert answer.state == "ready" and any("1.18 sg" in q for q in quotes), quotes
    assert not any("1.30" in q or "SYN-QA-12" in q for q in quotes), quotes


def test_a_same_page_conflict_keeps_both_sides(index):
    _answer, quotes = _quotes(index, "cement slurry density SYN-QA-21")
    text = " ".join(quotes)
    assert "1.90 sg" in text and "1.95 sg" in text, quotes             # never silently pick one


def test_partial_overlap_leads_with_the_full_answer_and_a_wrong_size_gets_none(index):
    _answer, quotes = _quotes(index, "top of cement for the 7 in liner SYN-QA-21")
    assert quotes and "2650 m" in quotes[0], quotes
    answer, quotes = _quotes(index, "top of cement for the 9-5/8 in casing SYN-QA-21")
    assert not any("2650" in q for q in quotes), (answer.state, quotes)  # the 7 in value never answers 9-5/8 in


def test_a_page_heading_supports_its_value_sentence_but_not_an_unrelated_one(index):
    _answer, quotes = _quotes(index, "kick tolerance SYN-QA-21")
    assert any("48 bbl" in q for q in quotes), quotes
    assert not any("Crew change" in q for q in quotes), quotes
    assert not any(q.startswith("• «Kick tolerance»") for q in quotes), quotes   # a subject, not a value


def test_a_sentence_stating_only_the_well_code_is_not_quoted(index):
    for question in ("trip tank volume SYN-QA-21",
                     "tank SYN-QA-21"):                  # one topical word: the well code must not outweigh it
        _answer, quotes = _quotes(index, question)
        assert quotes and all("12 m3" in q for q in quotes), (question, quotes)
        assert not any("belongs to" in q for q in quotes), (question, quotes)


def test_a_heading_match_with_no_stated_value_quotes_nothing_and_says_why(index):
    answer, quotes = _quotes(index, "swab and surge margin SYN-QA-21")
    assert answer.retrieval.status == "no_evidence" and answer.state == "no_evidence", answer.state
    assert quotes == [] and "reviewed by the office" not in (answer.text or "")
    assert any("no sentence in them states it" in note for note in answer.notes), answer.notes
    assert not any("instruction-like" in note for note in answer.notes), answer.notes


def test_identity_only_match_is_not_quoted_through_the_first_sentence_fallback(index):
    retrieval = index.retrieve("BOP test pressure SYN-QA-21")
    evidence = [e for e in ka.make_evidence(retrieval) if "rig move" in e.text]
    assert evidence
    item = evidence[0]
    # Same passage, a question whose only match on it is the inherited identity: nothing to quote ([]),
    # which is distinct from "no word matched" (None -> the n-gram first-sentence fallback).
    identity_only = index.retrieve("trip tank volume SYN-QA-21")
    assert ka._best_sentences(index, item, identity_only) == []
    typo_only = index.retrieve("BOPP tsst presure")
    assert ka._best_sentences(index, item, typo_only) is None


# ---- M50 survivors R-file-name-context-dropped / R-absent-ignores-context (M52 §2.4) ---------
# Since M51 sufficiency is measured on the topic terms without the code parts, the file-name code
# context matters only for a question that names nothing but a well code.  For such a question about
# a document whose FILE NAME states the code while its page is about a similar well, the explanation
# must say "about another well" and must never claim the code's words are absent from the scope.
def test_a_code_only_question_on_a_file_name_identity_explains_the_other_well(index):
    retrieval = index.retrieve("SYN-QB-31")
    assert retrieval.status == "no_evidence"
    rules = dict(retrieval.constraints)
    assert "other_entity" in rules, retrieval.constraints            # the page is about SYN-QB-13
    assert "absent" not in rules, retrieval.constraints              # the file name states syn / qb / 31
    _found, reasons = ka.describe_no_evidence(retrieval, ka.make_evidence(retrieval))
    assert any("about another well or entity" in r for r in reasons), reasons
    assert not any("which no passage in this scope mentions" in r for r in reasons), reasons
    assert not retrieval.absent_terms, retrieval.absent_terms


# ---- the M50 regression questions that showed the defect (N16, N18, N19) --------------------
@pytest.fixture(scope="module")
def m50_index():
    from m50_knowledge_fixtures import m50_corpus_db
    db, _ids = m50_corpus_db()
    return kr.KnowledgeIndex(kr.read_corpus(db))


@pytest.mark.parametrize("question, wanted, unrelated", [
    ("What is the MAASP for SYN-KF-06?", "1450 psi", "top of cement"),
    # N14: the MAASP sentence names no size; the paragraph's 9-5/8 in alone never makes it support.
    ("SYN-KF-06 casing shoe depth for the 9-5/8 in casing", "9150 ft", "MAASP"),
    # N30: the ECD sentence names no size but inherits the paragraph's 12-1/4 in - it stays the answer.
    ("ECD در بخش 12-1/4 اینچ چقدر است؟", "1.42 sg", "MAASP"),
    ("Where is the top of cement for the 9-5/8 in casing planned in SYN-KF-06?", "6000 ft", "MAASP"),
    ("cement top depth 9-5/8 in casing SYN-KF-06", "6000 ft", "MAASP"),
])
def test_m50_file_name_identity_questions_quote_no_unrelated_sentence(m50_index, question, wanted, unrelated):
    answer, quotes = _quotes(m50_index, question)
    assert answer.state == "ready" and any(wanted in q for q in quotes), quotes
    assert not any(unrelated in q for q in quotes), quotes


# ---- M50 mutant A-sentence-inherits-any-size after the M52 support gate ---------------------
# The own-support gate repeats the size rule, so the M50 gold question no longer observes the ranking
# stage; the ranking still decides WHICH supported sentences fill the two quote slots.  A sentence about
# another size must not inherit the asked size there either, or it displaces a sentence that names no
# size and is quoted for the asked size.
def _size_corpus():
    from document_link_fixtures import without_session_user
    from m49_knowledge_fixtures import make_db

    from core.database import Company, DocumentLink, Project, Well
    from core.document_library import PAGE_OK, READY, DocumentExtract, DocumentLibrary, PageDecision, PageExtract
    pages = [["The LOT at the 9-5/8 in shoe gave 1.85 sg EMW. The LOT at the 13-3/8 in shoe gave 1.65 sg EMW. "
              "The LOT EMW was confirmed by the office."],
             ["The 9-5/8 in casing was run to 2400 m."]]
    db = make_db()
    with without_session_user():
        session = db.create_session()
        try:
            company = Company(name="SYNTHETIC M52 SIZE CO", code="SYN-M52SZ")
            session.add(company)
            session.flush()
            project = Project(name="SYNTHETIC M52 SIZE", code="SYN-M52SP", company_id=company.id)
            session.add(project)
            session.flush()
            well = Well(name="SYN-QD-41", code="SYN-QD", project_id=project.id)
            session.add(well)
            session.flush()
            well_id = well.id
            session.commit()
        finally:
            session.close()
        library = DocumentLibrary(db)
        ids = []
        try:
            for n, texts in enumerate(pages):
                body = f"m52-size:{n}\x00" + "\x00".join(texts)
                extract = DocumentExtract(
                    path=f"/synthetic/m52-size/{n}", file_name=f"SYN-QD-41 size notes {n}.pdf",
                    size_bytes=len(body.encode("utf-8")), sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
                    kind="pdf", page_count=len(texts), status=READY,
                    pages=[PageExtract(i, f"page {i}", t, "pdf-text", PAGE_OK) for i, t in enumerate(texts, start=1)])
                outcome = library.import_reviewed(extract, {i: PageDecision(approved=True)
                                                            for i in range(1, len(texts) + 1)})
                assert outcome.status == "imported", outcome.message
                ids.append(outcome.document_id)
        finally:
            library.close()
        session = db.create_session()
        try:
            for document_id in ids:
                session.add(DocumentLink(document_id=document_id, well_id=well_id, linked_by="synthetic"))
            session.commit()
        finally:
            session.close()
    return kr.KnowledgeIndex(kr.read_corpus(db))


@pytest.mark.parametrize("question", ["LOT EMW 9-5/8 in shoe", "LOT 9-5/8 in shoe", "EMW at the 9-5/8 in shoe"])
def test_a_sentence_about_another_size_never_takes_a_quote_slot(question):
    index = _size_corpus()
    retrieval = index.retrieve(question)
    item = next(e for e in ka.make_evidence(retrieval) if "13-3/8" in e.text)
    quoted = ka._best_sentences(index, item, retrieval)
    assert quoted and "1.85 sg" in quoted[0], quoted
    assert not any("13-3/8" in s for s in quoted), quoted          # 1.65 sg belongs to another casing size
