"""M223: lineage library item -> architecture revision -> cement worksheet case, and no library picker on the scalar
cement worksheet.

The cement worksheet is derived from a frozen architecture revision (SHA-256 pinned); the revision pins the
tubular library snapshot of the casing it uses. A later library version or an edited architecture never changes the
saved case, its re-run stays MATCH against the revision it names, and every result stays labelled WORKSHEET.
SYNTHETIC data only.
"""
from __future__ import annotations

import json

from PySide6 import QtWidgets

from core import calculation_cases as cc
from core import well_architecture as wa
from core.engineering import reference_binding as rb
from core.engineering import tubular_reference as tr
from tests.test_m184_m189_reference_integration import ARCH, PROV, app, env, snap, w13  # noqa: F401


def _lineage(db, ids):
    binding = rb.make_binding(snap(db, "SYN-CSG-96"), rb.ARCHITECTURE_FIELDS)
    items = json.loads(json.dumps(ARCH))
    items[1].update(od_in=9.611, id_in=8.703, weight_ppf=46.1, grade="SYN-80", tubular_reference=binding,
                    hole_in=12.25)
    rev = wa.save_revision(db, ids["A"][0], items, wellbore_id=ids["A"][1])
    stored = wa.get_revision(db, rev["id"])
    work = wa.cement_annulus(stored["components"], items[1]["name"], open_hole_in=12.25, excess_pct=10.0)
    work = {**work, "architecture_revision_id": stored["id"], "architecture_revision": stored["revision"],
            "components_sha256": stored["components_sha256"], "open_hole_in": 12.25,
            "wellbore_id": stored.get("wellbore_id")}
    inputs, results = wa.cement_case_payload(work)
    case = cc.save_case(db, calculator=wa.CEMENT_CALCULATOR, name="SYN cement", inputs=inputs, results=results,
                        method=work["method"], method_version=work["version"], well_id=ids["A"][0],
                        note=f"{wa.CEMENT_WORKSHEET_LABEL} — {work['label']}")
    return binding, stored, case


def test_the_cement_case_names_the_revision_that_pins_the_library_snapshot(env):  # noqa: F811
    db, ids, _path = env
    binding, stored, case = _lineage(db, ids)
    saved = cc.get_case(db, case["id"])
    revision_id = saved["inputs"]["architecture_revision_id"]["value"]
    assert revision_id == stored["id"]
    assert saved["inputs"]["components_sha256"]["value"] == stored["components_sha256"]
    pinned = wa.get_revision(db, revision_id)["components"][1][rb.BINDING_KEY]
    assert pinned == binding and tr.verify_snapshot(pinned["snapshot"]) == []
    assert wa.CEMENT_WORKSHEET_LABEL in saved["note"] and "WORKSHEET" in wa.CEMENT_WORKSHEET_LABEL
    outcome = wa.verify_cement_case(db, saved["inputs"], saved["results"], saved["method_version"])
    assert outcome["status"] == "MATCH", outcome


def test_a_new_library_version_and_a_new_architecture_revision_leave_the_case_unchanged(env):  # noqa: F811
    db, ids, _path = env
    binding, stored, case = _lineage(db, ids)
    before = cc.get_case(db, case["id"])
    later = tr.create_set(db, "SYN library")["id"]                      # a second library version
    tr.add_item(db, later, tr.TubularSpec("CASING", "SYN-CSG-96", PROV, grade="SYN-80", nominal_od_in=9.611,
                                          id_in=8.611, wall_in=0.5, weight_ppf=53.5))
    tr.publish_set(db, later)
    edited = json.loads(json.dumps(stored["components"]))
    edited[1]["id_in"] = 8.6                                             # an edit drops the binding
    newer = wa.save_revision(db, ids["A"][0], edited, wellbore_id=ids["A"][1])
    assert rb.BINDING_KEY not in wa.get_revision(db, newer["id"])["components"][1]
    after = cc.get_case(db, case["id"])
    assert (after["inputs"], after["results"]) == (before["inputs"], before["results"])
    assert wa.get_revision(db, stored["id"])["components"][1][rb.BINDING_KEY] == binding
    assert wa.verify_cement_case(db, after["inputs"], after["results"], after["method_version"])["status"] == "MATCH"


def test_the_scalar_cement_worksheet_has_no_tubular_library_picker(w13):  # noqa: F811
    group = w13.cmt_hole.parentWidget()
    buttons = [b.text() for b in group.findChildren(QtWidgets.QPushButton)]
    assert not any("Library" in text for text in buttons), buttons
    assert w13.csg_lib_btn.parentWidget() is not group                  # the picker lives on Casing Strength only
