"""M50 citation verifier: separate dimensions, adversarial drafts, failed draft keeps the extractive answer.

Pure core tests (no Qt).  The "model" is a scripted stand-in for the external
local LLM - it only isolates the external dependency; it proves nothing about
model quality (real-model runs are NOT RUN: no local model installed).
Evidence texts are SYNTHETIC and written for these tests.
"""
import hashlib

import pytest

from core import knowledge_answer as ka
from core import knowledge_retrieval as kr


def _ev(label, text, doc=1, page_id=1):
    return ka.Evidence(label, doc, f"doc{doc}.pdf", page_id, 1, "page 1", 0, len(text), text, "sha", "approved",
                       "pdf-text", "all", 0.1, {"lexical": 1}, 1.0, ka.detect_instructions(text))


EVIDENCE = [
    _ev("S1", "The planned flow rate in the 12-1/4 in section is 3200 l/min at a standpipe pressure of 3200 psi."),
    _ev("S2", "The equivalent circulating density (ECD) must stay below 1.42 sg.", page_id=2),
    _ev("S3", "The cement slurry density for the 9-5/8 in casing is 1.42 sg.", doc=2, page_id=3),
    _ev("S4", "The planned mud weight for the 16 in section is 1.08 sg.", doc=3, page_id=4),
    _ev("S5", "The mud weight for the 16 in section is reduced to 1.05 sg.", doc=4, page_id=5),
]
CONFLICT = kr.Conflict("mud weight", "sg", [(1.08, "p4:0-10"), (1.05, "p5:0-10")])


def _check(reply, conflicts=()):
    return ka.validate_citations(reply, EVIDENCE, conflicts)


# ------------------------------------------------------------ positive controls
@pytest.mark.parametrize("reply", [
    "The standpipe pressure is 3200 psi [S1].",
    "The flow rate in the 12-1/4 in section is 3200 l/min [S1].",
    "The ECD limit is 1.42 sg [S2].",
    "The cement slurry density for the 9-5/8 in casing is 1.42 sg [S3].",
])
def test_grounded_statements_pass_every_applicable_dimension(reply):
    check = _check(reply)
    assert check.citation_checks_passed, check.problems
    assert all(v is not False for v in check.dimensions.values())
    assert check.label == ka.CITATION_PASSED_LABEL and check.semantic_verified is False


# ------------------------------------------------------------ adversarial drafts
@pytest.mark.parametrize("reply, dimension, problem", [
    # the same number for a different quantity (3200 is both the flow rate and the pressure)
    ("The flow rate is 3200 psi [S1].", "quantity_relationship", 'do not link "flow rate" to 3200 psi'),
    # the right number in the wrong unit
    ("The ECD limit is 1.42 ppg [S2].", "units_match", "1.42 ppg is stated as 1.42 sg"),
    # a size the source does not cover
    ("The flow rate for the 8-1/2 in section is 3200 l/min [S1].", "sizes_match", "Size 8-1/2 in"),
    # an invented conversion
    ("The ECD limit is 1.42 sg (11.8 ppg) [S2].", "numbers_in_cited_source", "Number 11.8"),
    # a citation whose passage has the number for another quantity
    ("The ECD limit is 1.42 sg [S3].", "quantity_relationship", 'do not link "ecd" to 1.42 sg'),
    # a shared generic qualifier ("planned") does not link another quantity to the value
    ("The planned flow rate is 1.08 sg [S4].", "quantity_relationship", 'do not link "flow rate" to 1.08 sg'),
    # no citation at all
    ("The ECD limit is 1.42 sg.", "claims_cited", "without a citation"),
    # a label that names no retrieved passage
    ("The ECD limit is 1.42 sg [S9].", "citations_resolve", "[S9]"),
    # a citation that does not contain the value at all
    ("The standpipe pressure is 3200 psi [S2].", "numbers_in_cited_source", "Number 3200"),
])
def test_adversarial_draft_fails_exactly_the_named_dimension(reply, dimension, problem):
    check = _check(reply)
    assert not check.citation_checks_passed
    assert check.dimensions[dimension] is False, check.dimensions
    assert any(problem in p for p in check.problems), check.problems
    assert check.label == ka.CITATION_FAILED_LABEL


def test_same_number_other_quantity_keeps_number_and_unit_dimensions_passing():
    check = _check("The flow rate is 3200 psi [S1].")
    assert check.dimensions["numbers_in_cited_source"] is True and check.dimensions["units_match"] is True
    assert check.dimensions["quantity_relationship"] is False


def test_conflict_must_be_disclosed():
    one_side = _check("The mud weight for the 16 in section is 1.08 sg [S4].", (CONFLICT,))
    assert one_side.dimensions["conflicts_disclosed"] is False
    assert any("1.05" in p for p in one_side.problems)
    both = _check("The program's mud weight for the 16 in section is 1.08 sg [S4]; the update gives a mud weight "
                  "of 1.05 sg [S5].", (CONFLICT,))
    assert both.citation_checks_passed, both.problems
    assert both.dimensions["conflicts_disclosed"] is True


def test_dimensions_not_applicable_are_none_not_passed():
    check = _check("The flow rate is given in the hydraulics section [S1].")
    assert check.citation_checks_passed
    for name in ("numbers_in_cited_source", "units_match", "quantity_relationship", "sizes_match",
                 "conflicts_disclosed"):
        assert check.dimensions[name] is None, name


def test_verified_alias_is_citation_checks_only():
    check = _check("The ECD limit is 1.42 sg [S2].")
    assert check.verified is check.citation_checks_passed is True
    assert check.semantic_verified is False
    assert {name for name, _ in ka.VALIDATION_DIMENSIONS} == set(check.dimensions)


def test_unit_synonyms_across_scripts_are_the_same_unit():
    ev = [_ev("S1", "Kick tolerance for the 8-1/2 in section is 50 bbl.")]
    check = ka.validate_citations("تحمل فوران در بخش ۸-۱/۲ اینچ برابر ۵۰ بشکه است [S1].", ev)
    assert check.citation_checks_passed, check.problems


# ------------------------------------------------------------ flow: a failed draft never becomes the answer
class Scripted:
    """Stand-in for the external local model (isolation only)."""

    def __init__(self, reply):
        self.reply = reply

    def chat(self, messages, cancel=None):
        return self.reply

    def embed(self, texts, cancel=None):
        raise AssertionError("no embedding configured in this test")


def _index(pages):
    records = {}
    for pid, (doc, name, text) in enumerate(pages, start=1):
        records[pid] = kr.PageRecord(pid, doc, name, 1, "page 1", text, "pdf-text", "approved",
                                     hashlib.sha256(text.encode()).hexdigest())
    return kr.KnowledgeIndex(kr.CorpusSnapshot(records, {}, {}, ("t",), {d: n for d, n, _ in pages}))


def test_failed_draft_is_kept_apart_and_the_extractive_answer_stays():
    index = _index([(1, "hyd.pdf", "The equivalent circulating density (ECD) must stay below 1.42 sg.")])
    answer = ka.answer_question(index, "ECD", adapter=Scripted("The ECD limit is 1.42 ppg [S1]."),
                                use_model=True)
    assert answer.state == "ready" and answer.mode == "extractive"
    assert "1.42 sg" in answer.text and "ppg" not in answer.text
    assert answer.citation_checks_passed and answer.check.citation_checks_passed
    assert answer.draft == "The ECD limit is 1.42 ppg [S1]."
    assert answer.draft_check.dimensions["units_match"] is False
    assert any("failed" in n and "citation check" in n for n in answer.notes)
    assert answer.semantic_verified is False


def test_draft_hiding_one_side_of_a_conflict_is_not_used():
    index = _index([(1, "program.pdf", "The planned mud weight for the 16 in section is 1.08 sg."),
                    (2, "update.pdf", "The mud weight for the 16 in section is reduced to 1.05 sg.")])
    answer = ka.answer_question(index, "mud weight for the 16 in section",
                                adapter=Scripted("The mud weight for the 16 in section is 1.08 sg [S1]."),
                                use_model=True)
    assert answer.retrieval.conflicts
    assert answer.mode == "extractive" and "1.08" in answer.text and "1.05" in answer.text
    assert answer.draft_check.dimensions["conflicts_disclosed"] is False


def test_passing_draft_is_used_and_labelled_citation_checks_only():
    index = _index([(1, "hyd.pdf", "The equivalent circulating density (ECD) must stay below 1.42 sg.")])
    answer = ka.answer_question(index, "ECD", adapter=Scripted("The ECD limit is 1.42 sg [S1]."),
                                use_model=True)
    assert (answer.mode, answer.citation_checks_passed, answer.draft) == ("generated", True, "")
    assert answer.check.label == ka.CITATION_PASSED_LABEL and answer.semantic_verified is False


def test_conflict_passages_are_never_cut_by_the_source_limit():
    pages = [(d, f"doc{d}.pdf", f"The mud weight for the 16 in section is 1.0{d} sg.") for d in range(1, 6)]
    index = _index(pages)
    answer = ka.answer_question(index, "mud weight for the 16 in section")
    stated = {v for v in ("1.01", "1.02", "1.03", "1.04", "1.05") if v in answer.text}
    assert len(stated) == 5, answer.text           # all five conflicting values, beyond max_sources=3
    assert answer.check.citation_checks_passed, answer.check.problems


def test_values_for_different_sizes_are_not_a_conflict():
    index = _index([(1, "a.pdf", "The mud weight for the 16 in section is 1.08 sg."),
                    (2, "b.pdf", "The mud weight for the 12-1/4 in section is 1.25 sg.")])
    assert index.retrieve("mud weight").conflicts == []
