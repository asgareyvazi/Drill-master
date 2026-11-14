#!/usr/bin/env python3
"""Repeatable mutation run for the M171-M200 guards (review-queue correction, description headers, well identity,
route provenance, saved trajectory views / export / legacy retirement).

Each mutant removes ONE guard in a scratch copy of the working tree and must be KILLED by the listed tests.
Engine: ``tools/quality/mutation_m46.py``. It runs a green baseline first, and an anchor that does not match
exactly once is reported INVALID, never killed. The repository is never modified.

Usage::

    python tools/quality/mutation_m171_m200.py [--json OUT] [--only ID[,ID...]]

SYNTHETIC test data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

RSC = "core/review_scalar_correction.py"
RDLG = "dialogs/import_review_dialog.py"
DB = "core/database.py"
HA = "core/ddr_header_aliases.py"
MIN = "core/mineru_engine.py"
WI = "core/ddr_well_identity.py"
SVC = "core/ddr_import_service.py"
T173 = ["tests/test_m173_scalar_correction.py"]
T174 = ["tests/test_m174_header_aliases.py"]
T175 = ["tests/test_m175_well_identity.py"]
T176 = ["tests/test_m176_route_parity.py"]
PGT = "core/import_adapters/pdf_generic_tables.py"
PIPE = "core/ddr_import_pipeline.py"
TV = "core/trajectory_views.py"
TI = "core/engineering/tubular_import.py"
RB = "core/engineering/reference_binding.py"
APD = "dialogs/engineering_dialogs.py"
W13 = "tabs/w13_Engineering_Calculator.py"
WA = "core/well_architecture.py"
W3B = "tabs/w3b_wellbore_schematic_tab.py"
CCP = "tabs/calculation_cases_panel.py"
T182 = ["tests/test_m181_m183_tubular_import.py"]
T184 = ["tests/test_m184_m189_reference_integration.py"]
JR = "packaging/junit_report.py"
T195 = ["tests/test_junit_report.py"]
TVP = "tabs/trajectory_saved_views_panel.py"
TVW = "tabs/trajectory_viewer.py"
GUARDS = "core/storage_guards.py"
T178 = ["tests/test_m178_trajectory_views.py"]
DCI = "tools/quality/density_constant_inventory_m192.py"
OSS = "tools/quality/oss_reaudit_m193.py"
UX = "tools/quality/ux_success_audit_m197.py"
T192 = ["tests/test_m192_density_constants.py"]
T193 = ["tests/test_m193_oss_reaudit.py"]
T197 = ["tests/test_m197_ux_success_audit.py"]

MUTANTS = [
    # ---- M173 correction of a deferred scalar from the persisted queue ----
    Mutant("M173-bool-accepted", RSC, '    if isinstance(raw, bool) and target.sql_type != "boolean":\n',
           "    if False:\n", T173, "a yes/no value is stored as the text 'True' in a text field"),
    Mutant("M173-non-finite-accepted", RSC, "        if not math.isfinite(value) or abs(value) > MAX_MAGNITUDE:\n",
           "        if False:\n", T173, "NaN/inf/overflow reach the canonical record"),
    Mutant("M173-empty-becomes-value", RSC, "    if not text:\n        raise CorrectionRefused(\"An empty",
           "    if False:\n        raise CorrectionRefused(\"An empty", T173, "an empty edit is saved instead of refused"),
    Mutant("M173-bounds-ignored", RSC, "        if spec.min_val is not None and value < spec.min_val:\n",
           "        if False:\n", T173, "a value below the field's plausible minimum is saved"),
    Mutant("M173-percent-unbounded", RSC, '    if canonical_unit == "%" and not 0 <= value <= 100:\n',
           "    if False:\n", T173, "a percentage above 100 is saved"),
    Mutant("M173-unit-not-converted", RSC, "    if unit and canonical_unit and unit.strip() != canonical_unit:\n",
           "    if False:\n", T173, "a value entered in ft is stored as metres without conversion"),
    Mutant("M173-confirmation-skipped", RSC, "    if not confirmed:\n", "    if False:\n", T173,
           "an unconfirmed correction is written"),
    Mutant("M173-reason-optional", RSC,
           '    if not str(reason or "").strip():\n        raise CorrectionRefused("A reason is required for a correction',
           '    if False:\n        raise CorrectionRefused("A reason is required for a correction', T173,
           "a correction without a reason is written"),
    Mutant("M173-concurrency-ignored", RSC, "        if current != expected:\n", "        if False:\n", T173,
           "a value someone changed meanwhile is silently overwritten"),
    Mutant("M173-foreign-well-item", RSC, "    if item is None or item.well_id != well_id:\n",
           "    if item is None:\n", T173, "an item of another well is corrected from the selected well"),
    Mutant("M173-bulk-table-guessed", RSC, "    if entity in NOT_CORRECTABLE:\n", "    if False:\n", T173,
           "a multi-row table value is written to a guessed row"),
    Mutant("M173-decided-item-overwritten", RSC,
           "            raise CorrectionRefused(f\"The review item is already decided ({item.state}); reopen it first\")\n",
           "            pass\n", T173, "an already decided item is corrected again without being reopened"),
    Mutant("M173-history-lost", RSC, "    item.decision_history_json = json.dumps(entries",
           "    item.decision_history_json = json.dumps(entries[-1:]", T173,
           "earlier decisions are dropped from the item's history"),
    Mutant("M173-mud-loss-not-redirected", RSC,
           'STORED_AS = {"daily_report.mud_lost_downhole": "mud_report.loss_downhole"}',
           "STORED_AS = {}", T173, "the mud-loss item cannot be corrected although the import stores it on the mud report"),
    Mutant("M173-save-without-preview", RDLG,
           '        ready = bool(self.preview and not self.preview.get("conflict") and self.confirm_box.isChecked()\n',
           '        ready = bool(self.confirm_box.isChecked()\n', T173, "Save is enabled without a valid preview"),
    Mutant("M173-snapshot-missing", DB, '                    payload["target_at_creation"] = snapshot_target(active, row)\n',
           "                    pass\n", T173, "new queue items lose their target-at-creation snapshot"),
    # ---- M174 description headers ----
    Mutant("M174-ambiguity-guessed", HA, "    if len(candidates) > 1:\n", "    if False:\n", T174,
           "two candidate description columns: the first one is mapped without an operator decision"),
    Mutant("M174-outside-time-log", HA, "    if section is None:\n        return fields, dict(outcome, state=\"NOT_TIME_LOG\")\n",
           "    if section is None:\n        section = \"time_log\"\n", T174,
           "a generic 'Description' column outside a time log is mapped as activity text"),
    Mutant("M174-explicit-overridden", HA, "    if target in fields:\n", "    if False:\n", T174,
           "a generic header overrides an explicitly mapped activity column"),
    Mutant("M174-fuzzy-prefix", HA,
           "if index < len(fields) and fields[index] is None and normalize_header(header) in keys]",
           "if index < len(fields) and fields[index] is None and any(normalize_header(header).startswith(k) "
           "for k in keys)]", T174, "partial matches such as 'Activity Code' are mapped as the description"),
    Mutant("M174-override-ignored", HA, "    if RULE_KEY in rules:\n", "    if False:\n", T174,
           "a profile's own header list (or an explicit off switch) is ignored"),
    Mutant("M174-persian-forms-lost", HA, "    value = unicodedata.normalize(\"NFKC\", str(text or \"\")).translate(_LETTERS)\n",
           "    value = unicodedata.normalize(\"NFKC\", str(text or \"\"))\n", T174,
           "Arabic-script letter variants of a Persian header no longer match"),
    Mutant("M174-provenance-dropped", MIN,
           "            outcome = dict(outcome, source=self._table_source(table.provenance, table),\n",
           "            outcome = dict(outcome, source={},\n", T174,
           "the mapped header loses its page and bounding box"),
    # ---- M175 well identity ----
    Mutant("M175-twin-hidden", WI,
           "    return [w for w in wells if getattr(w, attribute) and _norm(getattr(w, attribute)) == _norm(value)]\n",
           "    exact = [w for w in wells if getattr(w, attribute) == value]\n    return exact or [w for w in wells "
           "if getattr(w, attribute) and _norm(getattr(w, attribute)) == _norm(value)]\n", T175,
           "an equivalent spelling on another well is hidden and the import routed to the exact spelling"),
    Mutant("M175-stale-decision-accepted", WI, "    if stale:\n        raise WellIdentityRefused(",
           "    if False:\n        raise WellIdentityRefused(", T175,
           "a decision made against another source or database state is applied"),
    Mutant("M175-decision-not-required", WI,
           "    if not isinstance(decision, Mapping):\n        raise WellIdentityRefused(f\"NOT SAVED: {assessment.message} "
           "Choose the target well explicitly.\", assessment)\n",
           "    if not isinstance(decision, Mapping):\n        return assessment.selected.id, False\n", T175,
           "a source naming another well is imported into the selected well without a decision"),
    Mutant("M175-refusal-ignored", WI, "    if assessment.refused:\n        raise WellIdentityRefused(assessment.message, "
           "assessment)\n", "    if False:\n        raise WellIdentityRefused(assessment.message, assessment)\n", T175,
           "an ambiguous or contradictory identity is imported"),
    Mutant("M175-project-scope-lost", WI,
           "    scope = [w for w in wells if selected is None or w.project_id == selected.project_id]\n",
           "    scope = list(wells)\n", T175, "a same-named well in another project makes the selected well's import ambiguous"),
    Mutant("M175-master-overwritten", SVC, "            if wi and keep_selected_master:\n", "            if False:\n",
           T175, "importing into the selected well overwrites its master data with the other well's header"),
    Mutant("M175-decision-in-fingerprint", SVC,
           '        if isinstance(metadata, dict) and {"well_identity_decision", "source_provenance"} & set(metadata):\n',
           "        if False:\n", T175, "a retry with a fresh decision is not recognised as the same source"),
    # ---- M176 route parity and provenance ----
    Mutant("M176-wrapped-join-silent", PGT,
           '                    joins.append({"row": len(rows), "column": col, "text": row_cells[0][2]})\n',
           "                    pass\n", T176, "a PDF line is joined to the row above without a review notice"),
    Mutant("M176-join-row-offset-lost", PGT, '                    dict(j, row=j["row"] + offset) for j in table["wrapped_joins"])',
           '                    dict(j) for j in table["wrapped_joins"])', T176,
           "a join on page 2 of a continued table points at the wrong row"),
    Mutant("M176-row-page-lost", MIN, "    if 0 < row_number <= len(pages) and pages[row_number - 1] is not None:\n",
           "    if False:\n", T176, "rows that continue on the next PDF page are recorded on the first page"),
    Mutant("M176-morning-heading-ignored", MIN,
           '        target = "time_log_morning" if named("time_log_morning") else "time_log" if named("time_log") else None\n',
           '        target = None\n', T176, "a morning time log under an explicit heading is parked unstored"),
    Mutant("M176-unstored-table-silent", MIN, '                if storage_key == "document_tables" and table_records:\n',
           "                if False:\n", T176, "rows of a mixed table are parked without telling the operator"),
    Mutant("M176-sha-missing", PIPE, '        "sha256": file_fingerprint(str(source)),\n', '        "sha256": None,\n', T176,
           "the imported file's SHA-256 is not recorded"),
    Mutant("M176-size-zero", PIPE, "        size = None\n", "        size = 0\n", T176,
           "an unreadable file size is recorded as 0 instead of unknown"),
    Mutant("M176-applied-profile-lost", PIPE,
           '                    if isinstance(applied := metadata.get("profile"), dict) and applied.get("key") else None),\n',
           "                    if False else None),\n", T176, "the profile that shaped the result is not recorded"),
    # ---- M178-M180 saved trajectory views, export, legacy retirement ----
    Mutant("M178-name-optional", TV, '    if not text:\n        raise TrajectoryViewError("A saved view needs a name.")\n',
           '    if False:\n        raise TrajectoryViewError("A saved view needs a name.")\n', T178,
           "an unnamed view is saved"),
    Mutant("M178-duplicate-name", TV, "        if key != except_key and head.status == ACTIVE and head.name.casefold() == folded:\n",
           "        if False:\n", T178, "two active views of one well get the same name"),
    Mutant("M178-foreign-wellbore", TV, "    if bore is None or bore.well_id != int(well_id):\n        raise TrajectoryViewError",
           "    if bore is None:\n        raise TrajectoryViewError", T178,
           "a view is bound to a wellbore of another well"),
    Mutant("M178-foreign-revision", TV, '        if revision is None or revision["well_id"] != int(well_id):\n',
           "        if revision is None:\n", T178, "a view is built from another well's survey revision"),
    Mutant("M178-tampered-revision-used", TV, '        if revision["integrity"] != "VERIFIED":\n', "        if False:\n",
           T178 + ["tests/test_m72_surveys_solver.py"], "a survey revision that failed its hash is used"),
    Mutant("M178-foreign-report-rows", TV, "    if foreign:\n        raise TrajectoryViewError(",
           "    if False:\n        raise TrajectoryViewError(", T178,
           "survey stations of another well's report are saved into this well's view"),
    Mutant("M178-undrawable-saved", TV, "    if not c.trajectory.drawable:\n", "    if False:\n", T178,
           "a view without a drawable trajectory is saved"),
    Mutant("M178-stale-head-accepted", TV,
           "    if expected_revision is None or int(expected_revision) != head.revision:\n", "    if False:\n", T178,
           "a revision based on an outdated view silently supersedes another user's revision"),
    Mutant("M178-archived-revisable", TV,
           "        if head.status != ACTIVE:\n            raise TrajectoryViewError(\"An archived view is read-only",
           "        if False:\n            raise TrajectoryViewError(\"An archived view is read-only", T178,
           "an archived view is revised"),
    Mutant("M178-reason-optional", TV,
           '    if not reason:\n        raise TrajectoryViewError(f"{action.title()} needs a reason.")\n',
           '    if False:\n        raise TrajectoryViewError(f"{action.title()} needs a reason.")\n', T178,
           "a view is archived or restored without a reason"),
    Mutant("M178-hash-not-checked", TV,
           '    elif len(out["stations"]) != row.station_count or snapshot_sha256(out["stations"]) != row.stations_sha256:\n',
           "    elif False:\n", T178, "a tampered snapshot is reported VERIFIED"),
    Mutant("M178-drift-always-match", TV, '    if current.stations_sha256 == record["stations_sha256"]:\n',
           "    if True:\n", T178, "a reopened view says MATCH although the surveys changed"),
    Mutant("M178-no-audit", TV, '    db._add_mandatory_audit(session, "trajectory_view_" + action.lower(),',
           '    (lambda *a, **k: None)(session, "trajectory_view_" + action.lower(),', T178,
           "a saved view leaves no audit record"),
    Mutant("M178-update-guard-missing", GUARDS,
           '        f"trg_trajectory_view_immutable_v{v}": (\n            f"CREATE TRIGGER trg_trajectory_view_immutable_v{v} BEFORE UPDATE ON trajectory_view_revisions "\n            f"WHEN {view_change} BEGIN',
           '        f"trg_trajectory_view_immutable_v{v}": (\n            f"CREATE TRIGGER trg_trajectory_view_immutable_v{v} BEFORE UPDATE ON trajectory_view_revisions "\n            f"WHEN 0 BEGIN',
           T178, "a saved view revision can be rewritten by raw SQL"),
    Mutant("M178-snapshot-recomputed-on-open", TVW, "        self.stations = list(stations)\n        self.selected_index = None\n        self._apply_settings",
           "        self.stations = list(stations)\n        self.selected_index = None\n        return self.reload() or True\n        self._apply_settings",
           T178, "opening a saved view redraws the current data instead of the stored snapshot"),
    Mutant("M178-fail-message-claims-saved", TVP, '        self.status.setText(f"NOT SAVED — {message}")\n',
           '        self.status.setText(f"Saved — {message}")\n', T178, "a failed save tells the user it was saved"),
    Mutant("M179-compare-interpolates", TV,
           '        match = next((s for s in remaining if abs(s["md"] - station["md"]) <= MD_TOLERANCE), None)\n',
           '        match = next((s for s in remaining if abs(s["md"] - station["md"]) <= 1000.0), None)\n', T178,
           "stations at different MDs are paired (a comparison by nearest station)"),
    Mutant("M179-missing-exported-as-zero", TV,
           "    number = _finite(value)\n    if number is None:\n        return None\n    return number * FT_PER_M",
           "    number = _finite(value)\n    if number is None:\n        return 0.0\n    return number * FT_PER_M",
           T178, "a value the snapshot does not hold is exported as 0"),
    Mutant("M179-feet-not-converted", TV, '    return number * FT_PER_M if unit == "ft" else number\n',
           "    return number\n", T178, "an export labelled ft holds metres"),
    Mutant("M179-dls-not-converted", TV, '    return number * DLS_30M_TO_100FT if unit == "ft" else number\n',
           "    return number\n", T178, "DLS labelled deg/100ft holds deg/30m"),
    Mutant("M179-tampered-exported", TV,
           '        raise TrajectoryViewError(f"The stored snapshot is {record.get(\'integrity\')}; it is not exported.")\n',
           "        pass\n", T178, "a snapshot that failed its hash is exported"),
    Mutant("M180-legacy-other-well", TV, "                .filter(DailyReport.well_id == int(well_id)).order_by(TrajectoryPlot.id).all())\n",
           "                .order_by(TrajectoryPlot.id).all())\n", T178,
           "legacy snapshots of another well are listed under this well"),
    Mutant("M180-legacy-unreadable-hidden", TV, "                readable = isinstance(parsed, dict)\n",
           "                readable = True\n", T178, "a broken legacy payload is listed as readable"),
    # ---- M182 controlled tubular importer
    Mutant("M182-boolean-number", TI, '        return None, "a boolean is not a number"\n',
           "        return 1.0 if value else 0.0, None\n", T182, "a TRUE/FALSE cell is imported as 1 / 0"),
    Mutant("M182-formula-accepted", TI,
           '            return None, "an Excel formula is a computed (derived) value; enter the documented value"\n',
           "            text = text.lstrip('=')\n", T182, "an Excel formula is imported as a documented value"),
    Mutant("M182-nonfinite-accepted", TI, "    if not math.isfinite(number):\n        return None, f\"{value!r} is not finite\"\n",
           "    if False:\n        return None, f\"{value!r} is not finite\"\n", T182, "NaN / inf is imported"),
    Mutant("M182-conflict-overwrites", TI, "        elif key in identities:\n            row.status = CONFLICT\n",
           "        elif key in identities:\n            row.status = NEW\n", T182,
           "a row with the identity of a stored item and other values is imported next to it"),
    Mutant("M182-standards-not-blocked", TI, "    for pattern in STANDARD_TABLE_PATTERNS:\n",
           "    for pattern in ():\n", T182, "a file citing API 5DP / 5CT tables is imported"),
    Mutant("M182-partial-without-consent", TI,
           "    if not accept_partial and (counts[INVALID] or counts[CONFLICT]):\n", "    if False:\n", T182,
           "invalid / conflicting rows are skipped silently"),
    Mutant("M182-file-change-ignored", TI, "    if current != preview.sha256:\n", "    if False:\n", T182,
           "a file changed after the preview is imported"),
    Mutant("M182-published-target", TI, "        if ref is None or ref.status != tr.DRAFT:\n", "        if ref is None:\n",
           T182, "rows are written into a published (immutable) set"),
    Mutant("M182-no-audit", TI, '        db._add_mandatory_audit(session, "tubular_reference_import",',
           '        (lambda *a, **k: None)(session, "tubular_reference_import",', T182, "an import leaves no audit record"),
    Mutant("M182-row-limit", TI, "MAX_ROWS = 5000\n", "MAX_ROWS = 10 ** 9\n", T182, "an oversized file is read whole"),
    # ---- M184-M189 shared binding service and consumers
    Mutant("M189-unavailable-filled", RB,
           "        if value is None or (isinstance(value, str) and not value.strip()):\n            unavailable.append(key)\n        else:\n            values[key] = value\n",
           "        if value is None or (isinstance(value, str) and not value.strip()):\n            values[key] = 0.0\n        else:\n            values[key] = value\n",
           T184, "a value missing from the library is bound as 0"),
    Mutant("M189-damaged-snapshot-bound", RB,
           '    if problems:\n        raise BindingError("The library snapshot is not intact: " + "; ".join(problems))\n',
           '    if False:\n        raise BindingError("The library snapshot is not intact: " + "; ".join(problems))\n',
           T184, "a snapshot that failed its fingerprint is bound"),
    Mutant("M189-edit-keeps-binding", RB, "            if key in values and not _same(values.get(key), expected)]\n",
           "            if False]\n", T184, "an edited value keeps the library binding"),
    Mutant("M189-absent-key-is-edit", RB, "            if key in values and not _same(values.get(key), expected)]\n",
           "            if not _same(values.get(key), expected)]\n", T184,
           "a module without a grade column always loses the binding"),
    Mutant("M189-tolerance-loose", RB, "VALUE_TOLERANCE = 1e-9\n", "VALUE_TOLERANCE = 0.1\n", T184,
           "a small OD edit keeps the binding"),
    Mutant("M189-unreadable-as-match", RB, '    if problems:\n        return Drift(UNREADABLE, "; ".join(problems))\n',
           '    if False:\n        return Drift(UNREADABLE, "; ".join(problems))\n', T184,
           "a tampered stored snapshot is reported against the library"),
    Mutant("M189-missing-set-different", RB,
           '            return Drift(NOT_REPRODUCIBLE, f"{label} is not in this database; the stored snapshot stays valid")\n',
           '            return Drift(MATCH, f"{label} is not in this database; the stored snapshot stays valid")\n',
           T184, "a snapshot from another database is reported MATCH"),
    Mutant("M189-fingerprint-ignored", RB,
           '        if ref.status != tr.PUBLISHED or ref.content_fingerprint != snapshot.get("set_fingerprint"):\n',
           "        if ref.status != tr.PUBLISHED:\n", T184, "a changed library set is reported MATCH"),
    Mutant("M189-newer-version-hidden", RB,
           '    note = f"; {newer} newer published version(s) exist and are NOT applied" if newer else ""\n',
           '    note = ""\n', T184, "a newer published version is not reported"),
    Mutant("M189-report-failure-match", CCP,
           '            return [{"path": "/", "designation": None, "set": "?", "state": rb.UNREADABLE,\n',
           '            return [{"path": "/", "designation": None, "set": "?", "state": rb.MATCH,\n', T184,
           "a failed library check is shown as MATCH"),
    Mutant("M185-dialog-binding-not-saved", APD,
           "        self.result = rb.attach(self.result, self._tubular_binding)    # dropped when a bound value was edited\n",
           "        pass\n", T184, "a library pick is not stored with the component"),
    Mutant("M185-dialog-unavailable-kept", APD,
           "            widget.setValue(float(values[key]) if key in values else 0.0)     # 0 = not entered (unavailable)\n",
           "            widget.setValue(float(values[key])) if key in values else None\n", T184,
           "a stale value stays in a field the library item does not provide"),
    Mutant("M188-yield-not-unknown", W13,
           "                getattr(self, attr).setValue(0.0)       # 0 shown, recorded as unknown\n                provenance[key] = \"unknown\"\n",
           "                getattr(self, attr).setValue(0.0)       # 0 shown, recorded as unknown\n                provenance[key] = \"reference\"\n",
           T184, "an unknown yield is recorded as a library value"),
    Mutant("M188-wall-derived-unlabelled", W13, '                provenance[key] = "derived"\n',
           '                provenance[key] = "reference"\n', T184, "a derived wall is labelled as a library value"),
    Mutant("M184-architecture-edit-keeps-binding", WA, "            if rb.binding_holds(binding, item):\n",
           "            if True:\n", T184, "an edited architecture string keeps the library binding"),
    Mutant("M184-w3b-id-derived", W3B,
           '        casing.id_inch = float(values["id_in"]) if "id_in" in values else None       # unknown, never derived\n',
           '        casing.id_inch = float(values["id_in"]) if "id_in" in values else casing.od_inch - 0.5\n', T184,
           "an unavailable library ID is guessed"),
    Mutant("M189-guard-set-frozen", GUARDS, "            f\"WHEN OLD.status = 'PUBLISHED' AND ({set_change}) BEGIN SELECT RAISE(ABORT, \"\n",
           "            f\"WHEN 0 AND ({set_change}) BEGIN SELECT RAISE(ABORT, \"\n", T184,
           "a published reference set can be rewritten by raw SQL"),
    Mutant("M189-guard-item-frozen", GUARDS,
           "            f\"WHEN {published.format('OLD')} OR {published.format('NEW')} BEGIN SELECT RAISE(ABORT, \"\n",
           "            f\"WHEN {published.format('OLD')} BEGIN SELECT RAISE(ABORT, \"\n", T184,
           "a draft item can be moved into a published set"),
    Mutant("M189-guard-item-insert", GUARDS,
           "            f\"CREATE TRIGGER trg_tubular_item_noinsert_v{t} BEFORE INSERT ON tubular_reference_items \"\n"
           "            f\"WHEN {published.format('NEW')} BEGIN",
           "            f\"CREATE TRIGGER trg_tubular_item_noinsert_v{t} BEFORE INSERT ON tubular_reference_items \"\n"
           "            f\"WHEN 0 BEGIN", T184, "a published set takes new items through raw SQL"),
    # ---- M195 crash-marker classification
    Mutant("M195-breadcrumb-marker", JR, "    text = line if at < 0 else line[:at]\n", "    text = line\n", T195,
           "a banner quoted in a test id inside a breadcrumb is reported as a crash dump"),
    Mutant("M195-bare-current-thread", JR, '                 re.compile(r"Current thread 0x[0-9A-Fa-f]+"))\n',
           '                 re.compile(r"Current thread"))\n', T195,
           "the words 'Current thread' in ordinary output are reported as a crash dump"),
    Mutant("M195-banner-without-colon", JR, 'CRASH_MARKERS = (re.compile(r"Fatal Python error: "),',
           'CRASH_MARKERS = (re.compile(r"Fatal Python error"),', T195, "prose naming a fatal error is a crash dump"),
    Mutant("M195-dotted-banner-missed", JR, "    return any(pattern.search(text) for pattern in CRASH_MARKERS)\n",
           "    return any(pattern.match(text) for pattern in CRASH_MARKERS)\n", T195,
           "a banner after progress dots is not found"),
    # ---- M192 / M193 / M197 audit tools
    Mutant("M192-pattern-prefix", DCI, 'PATTERNS = {"7.48": re.compile(r"(?<![\\d.])7\\.48(?!\\d)"),',
           'PATTERNS = {"7.48": re.compile(r"7\\.48(?!\\d)"),', T192, "27.48 is counted as the 7.48 constant"),
    Mutant("M193-noassertion-changed", OSS, "        return spdx in _SPDX_EQUIVALENT[recorded]\n",
           "        return spdx is None\n", T193, "a NOASSERTION licence on an unlicensed repo is a licence change"),
    Mutant("M193-licence-change-missed", OSS, '    return (spdx or "").lower() == recorded.lower()\n',
           "    return True\n", T193, "MIT -> Apache-2.0 is not reported"),
    Mutant("M193-error-as-gone", OSS, "    if error:\n        out.update(state=ERROR", "    if False:\n        out.update(state=ERROR",
           T193, "a failed lookup is reported GONE instead of NOT CHECKED"),
    Mutant("M193-archived-missed", OSS, '    if remote.get("archived"):\n', "    if False:\n", T193,
           "an archived repository is not reported"),
    Mutant("M193-moved-missed", OSS, '    if remote.get("sha") and remote.get("sha") != entry.get("sha"):\n',
           "    if False:\n", T193, "new commits are not reported"),
    Mutant("M197-prefix-ignored", UX, "    return sorted(f for f in found if not any(f[0] == path and f[1].startswith(prefix)\n",
           "    return sorted(f for f in found if not any(f[0] == path\n", T197,
           "a reviewed file hides every other success claim in it"),
    Mutant("M197-success-anywhere", UX, 'SUCCESS = re.compile(r"^\\s*(', 'SUCCESS = re.compile(r"^.*?(', T197,
           "'NOT SAVED' (a success word inside failure wording) is reported as a success claim"),
    Mutant("M197-whole-file-scanned", UX, "            if not isinstance(node, ast.ExceptHandler):\n                continue\n",
           "            pass\n", T197, "success messages outside exception handlers are reported"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
