"""SYNTHETIC fixtures for the M45 document-link and Persian-search tests.

Everything here is invented for tests: company, project, well names, codes,
dates and document text are synthetic and carry a SYNTHETIC/SYN marker.

World (``build_link_world``):

* well ``SYN-ALPHA-01`` (code ``SYN-A1``) with reports #1 and #2;
* two wells both named ``SYN-TWIN`` (codes ``SYN-T1`` / ``SYN-T2``) in two
  different projects, to prove the picker tells same-name wells apart;
* well ``چاه نمونه ۷`` (Persian name, code ``SYN-FA-7``);
* documents (text files, imported through the real reviewed-import path):
  - ``syn_alpha_daily.txt``  - mentions SYN-ALPHA-01 twice (pages = 80-line sections);
  - ``syn_twin_note.txt``    - mentions SYN-TWIN (ambiguous);
  - ``syn_fa_arabic.txt``    - Persian words typed with ARABIC yeh/kaf (cp1256 bytes);
  - ``syn_unrelated.txt``    - no well name at all.
"""
from __future__ import annotations

from datetime import date

from core.database import Company, DailyReport, Project, Section, Well
from core.document_library import DocumentLibrary, extract_document

ARABIC_YEH, PERSIAN_YEH = "\u064a", "\u06cc"
ARABIC_KAF, PERSIAN_KAF = "\u0643", "\u06a9"
ZWNJ = "\u200c"
# Persian words typed with ARABIC yeh (U+064A) and kaf (U+0643); the well
# name "چاه نمونه ۷" appears with an ASCII 7 (cp1256 has no Persian digits).
ARABIC_TEXT = (f"گزارش مصنوع{ARABIC_YEH}: {ARABIC_KAF}{ARABIC_YEH}س{ARABIC_YEH}نگ چاه نمونه 7 در عمق 1250 متر\n"
               "SYNTHETIC")


def _add(session, obj):
    session.add(obj)
    session.flush()
    return obj.id


def build_link_world(db) -> dict:
    """Create the SYNTHETIC hierarchy; return ids by role."""
    session = db.create_session()
    try:
        company = _add(session, Company(name="SYNTHETIC LINK CO", code="SYN-CO"))
        project_a = _add(session, Project(name="SYNTHETIC PROJECT EAST", code="SYN-PE", company_id=company))
        project_b = _add(session, Project(name="SYNTHETIC PROJECT WEST", code="SYN-PW", company_id=company))
        alpha = _add(session, Well(name="SYN-ALPHA-01", code="SYN-A1", project_id=project_a, field_name="SYN FIELD",
                                   rig_name="SYN RIG 1", spud_date=date(2026, 1, 1)))
        twin_1 = _add(session, Well(name="SYN-TWIN", code="SYN-T1", project_id=project_a, rig_name="SYN RIG 2"))
        twin_2 = _add(session, Well(name="SYN-TWIN", code="SYN-T2", project_id=project_b, rig_name="SYN RIG 3"))
        persian = _add(session, Well(name="چاه نمونه ۷", code="SYN-FA-7", project_id=project_b))
        section = _add(session, Section(well_id=alpha, name="SYN 12 1/4 in"))
        report_1 = _add(session, DailyReport(well_id=alpha, section_id=section, report_date=date(2026, 1, 2),
                                             report_number=1, depth_2400=850.0))
        report_2 = _add(session, DailyReport(well_id=alpha, section_id=section, report_date=date(2026, 1, 3),
                                             report_number=2, depth_2400=1100.0))
        twin_report = _add(session, DailyReport(well_id=twin_1, report_date=date(2026, 1, 2), report_number=1))
        session.commit()
    finally:
        session.close()
    return {"alpha": alpha, "twin_1": twin_1, "twin_2": twin_2, "persian": persian, "report_1": report_1,
            "report_2": report_2, "twin_report": twin_report}


def write_documents(folder) -> dict:
    """Write the SYNTHETIC source files; return paths by role."""
    folder.mkdir(parents=True, exist_ok=True)
    alpha_lines = [f"SYNTHETIC line {i}" for i in range(1, 81)]
    alpha_lines[4] = "SYNTHETIC daily summary for SYN-ALPHA-01: casing shoe set at 1250 m"
    alpha_lines += ["SYNTHETIC page two: SYN-ALPHA-01 mud weight 1.25 sg", "SYNTHETIC end"]
    paths = {
        "alpha": folder / "syn_alpha_daily.txt",
        "twin": folder / "syn_twin_note.txt",
        "arabic": folder / "syn_fa_arabic.txt",
        "unrelated": folder / "syn_unrelated.txt",
    }
    paths["alpha"].write_text("\n".join(alpha_lines), encoding="utf-8")
    paths["twin"].write_text("SYNTHETIC rig note: SYN-TWIN pump pressure check", encoding="utf-8")
    # cp1256 has no Persian yeh/keheh: the bytes decode to ARABIC yeh and kaf,
    # which is how such files look when they come from older Arabic keyboards.
    paths["arabic"].write_bytes(ARABIC_TEXT.encode("cp1256"))
    paths["unrelated"].write_text("SYNTHETIC generic procedure without any well reference", encoding="utf-8")
    return paths


def import_documents(db, paths) -> dict:
    """Import through the real reviewed path (text pages are pre-approved)."""
    library = DocumentLibrary(db)
    ids = {}
    for role, path in paths.items():
        outcome = library.import_reviewed(extract_document(path))
        assert outcome.status == "imported", (role, outcome.status, outcome.message)
        ids[role] = outcome.document_id
    library.close()
    return ids
