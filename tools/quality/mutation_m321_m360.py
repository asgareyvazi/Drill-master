#!/usr/bin/env python3
"""Repeatable mutation run for M321-M360 (M327): the M311 / M314 / M317 / M318 / M320 D / M320 E modules, the M308
window-release policy, and the M323 / M328 repairs (History replay, D89 new-record NULLs).

Each mutant introduces ONE realistic defect in a scratch copy of the working tree: a missing value read as zero, a
dropped gate, a one-sided check, a wrong conversion factor, a provenance field not frozen, a tolerance widened. The
listed tests must KILL it. Engine: ``tools/quality/mutation_m46.py``. Run on a green, COMMITTED tree. An anchor that
does not match exactly once is INVALID (never counted as killed), and ``--only`` never gives complete=True.

A mutant whose behaviour cannot differ from the original for any input reachable through the public API is declared
EQUIVALENT with the reason (``equivalent=``). It is still executed and reported.

Usage::

    python tools/quality/mutation_m321_m360.py [--json OUT] [--only ID[,ID...]]

SYNTHETIC test data only. IDs are stable: a mutant is never renamed; a retired one is removed and reported.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

AD = "core/architecture_diff.py"
HC = "core/ddr_hydraulics_check.py"
CJ = "core/cement_job_reconciliation.py"
TDS = "core/torque_drag_sensitivity.py"
RS = "core/report_sections.py"
CR = "core/citation_record.py"
QL = "core/qt_lifetime.py"
HR = "core/history_replay.py"
W3C = "tabs/w3c_section_data.py"

T323 = "tests/test_m323_m328_residuals_and_replay.py"
TAD = ["tests/test_m311_architecture_diff.py", "tests/test_m329_architecture_diff_table_export.py", T323]
WAP = "tabs/well_architecture_panel.py"
THC = ["tests/test_m314_ddr_hydraulics_check.py"]
TCJ = ["tests/test_m317_cement_job_reconciliation.py", T323]
TTDS = ["tests/test_m318_td_friction_sensitivity.py", T323]
TRS = ["tests/test_m320d_report_sections.py"]
TCR = ["tests/test_m320e_citation_record.py", "tests/test_m334_citation_record_navigation.py"]
KA = "tabs/knowledge_assistant.py"
TQL = ["tests/test_m308_window_release_policy.py", "tests/test_m326_window_lifecycle.py"]
THR = [T323, "tests/test_m314_ddr_hydraulics_check.py", "tests/test_m317_cement_job_reconciliation.py",
       "tests/test_m318_td_friction_sensitivity.py"]
TW3C = ["tests/test_cement_report_null_roundtrip.py"]

MUTANTS = [
    # ------------------------------------------------------------------ M311 architecture diff
    Mutant("AD-unknown-equals-zero", AD,
           "               if (old.get(f) if old.get(f) != \"\" else None) != (new.get(f) if new.get(f) != \"\" "
           "else None)]\n",
           "               if (old.get(f) or 0) != (new.get(f) or 0)]\n", TAD,
           "a field that went from 0 to unknown (or back) is not reported as a change"),
    Mutant("AD-binding-ignored", AD, "    if old.get(BINDING) != new.get(BINDING):\n",
           "    if False:\n", TAD, "a changed tubular-library binding is not reported"),
    Mutant("AD-duplicates-unstated", AD, "        if max(len(olds), len(news)) > 1:\n",
           "        if max(len(olds), len(news)) > 2:\n", TAD,
           "two components with the same identity are matched silently (no ambiguity note)"),
    Mutant("AD-added-as-removed", AD,
           "                rows.append({**base, \"status\": ADDED, \"changes\": [], \"new\": new})\n",
           "                rows.append({**base, \"status\": REMOVED, \"changes\": [], \"new\": new})\n",
           TAD, "an added component is reported as removed"),
    Mutant("AD-geometry-not-affecting", AD,
           "        r[\"status\"] in (ADDED, REMOVED) or any(c[\"field\"] in GEOMETRY for c in r[\"changes\"]))})\n",
           "        r[\"status\"] in (ADDED, REMOVED)))})\n", TAD,
           "a string whose depth / OD / ID changed is not listed as invalidating pinned worksheets"),
    Mutant("AD-identical-ignores-changes", AD,
           "\"identical\": counts[ADDED] == counts[REMOVED] == counts[CHANGED] == 0}",
           "\"identical\": counts[ADDED] == counts[REMOVED] == 0}", TAD,
           "two revisions that differ only in changed fields are reported identical"),
    Mutant("AD-cross-well-allowed", AD, "    if older[\"well_id\"] != newer[\"well_id\"]:\n", "    if False:\n", TAD,
           "revisions of two different wells are compared"),
    Mutant("AD-order-not-normalised", AD, "    if older[\"revision\"] > newer[\"revision\"]:\n", "    if False:\n", TAD,
           "selecting the newer revision first reverses ADDED / REMOVED"),
    Mutant("AD-casing-runs-not-listed", AD,
           "        for key in ch._architecture_users(session, d, revision_id, well_id):\n",
           "        for key in [k for k in ch._architecture_users(session, d, revision_id, well_id)\n"
           "                    if k.startswith(\"calculation_cases\")]:\n", TAD,
           "A-1 regression: casing-design runs pinned to the older revision are not listed"),
    Mutant("AD-pinned-to-newer", AD, "_pinned_cases(db, older[\"id\"], older[\"well_id\"])",
           "_pinned_cases(db, newer[\"id\"], older[\"well_id\"])", TAD,
           "the pinned-work list names cases of the newer revision instead of the superseded one"),
    Mutant("AD-unknown-shown-as-zero", AD, "    return \"unknown\" if value in (None, \"\") else",
           "    return \"0\" if value in (None, \"\") else", TAD, "an unknown value is displayed as 0"),
    # ------------------------------------------------------------------ M329 diff table / duplicates / export
    Mutant("AD-dup-no-exact-first", AD,
           "        exact = next((j for j in free_new if not _changes(old, news[j])), None)\n",
           "        exact = None\n", TAD, "reordered same-named components are reported as two spurious changes"),
    Mutant("AD-dup-remainder-not-flagged", AD,
           "free_new[k] if k < len(free_new) else None, True))\n",
           "free_new[k] if k < len(free_new) else None, False))\n", TAD,
           "a stored-order match of duplicates is not flagged ambiguous"),
    Mutant("AD-occurrence-off-by-one", AD, "\"occurrence_old\": oi + 1 if dup and oi is not None else None,",
           "\"occurrence_old\": oi if dup and oi is not None else None,", TAD,
           "the older occurrence number names the wrong duplicate"),
    Mutant("AD-table-always-unchanged", AD, "        if r[\"status\"] == UNCHANGED and not include_unchanged:\n",
           "        if False:\n", TAD, "the table lists unchanged components unless asked"),
    Mutant("AD-export-unknown-as-zero", AD, "    if value in (None, \"\"):\n        return \"\"\n",
           "    if value in (None, \"\"):\n        return 0\n", TAD, "an unknown value is exported as 0"),
    Mutant("AD-export-formula-live", AD,
           "    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):\n        return \"'\" + value\n",
           "    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):\n        return value\n", TAD,
           "a component name starting with '=' is exported as a live spreadsheet formula"),
    Mutant("AD-export-sha-wrong", AD, "(f\"{side} components SHA-256\", info[\"components_sha256\"])",
           "(f\"{side} components SHA-256\", info[\"id\"])", TAD,
           "the export does not carry the revision SHA-256 (cannot be tied to the frozen revision)"),
    Mutant("AD-export-ignores-unchanged-option", AD,
           "table_rows(result, include_unchanged=include_unchanged)", "table_rows(result)", TAD,
           "the export omits unchanged components although the user asked for them"),
    Mutant("AD-binding-label-top-level", AD, "    snap = binding.get(\"snapshot\") or {}\n",
           "    snap = binding\n", TAD,
           "D90 regression: the binding label reads the top level and shows every library change as unknown"),
    Mutant("AD-panel-comparison-outlives-refresh", WAP,
           "        self.last_comparison = None            # M329",
           "        pass  # M329", TAD, "a comparison of the previous well stays shown / exportable after refresh"),
    # ------------------------------------------------------------------ M314 DDR hydraulics check
    Mutant("HC-hsi-band-dropped", HC,
           "        inside = low * (1 - HSI_TOLERANCE) <= recorded_hsi <= high * (1 + HSI_TOLERANCE)\n",
           "        inside = low <= recorded_hsi <= high\n", THC,
           "the documented ±5 % display band is not applied (rounded recorded HSI reported as DIFFERS)"),
    Mutant("HC-hsi-one-sided", HC,
           "        inside = low * (1 - HSI_TOLERANCE) <= recorded_hsi <= high * (1 + HSI_TOLERANCE)\n",
           "        inside = recorded_hsi <= high * (1 + HSI_TOLERANCE)\n", THC,
           "a recorded HSI far below the recomputed value is accepted"),
    Mutant("HC-tfa-band-widened", HC, "        same = abs(recorded_tfa - nozzle_tfa) <= TFA_TOLERANCE * nozzle_tfa\n",
           "        same = abs(recorded_tfa - nozzle_tfa) <= 10 * TFA_TOLERANCE * nozzle_tfa\n", THC,
           "a recorded TFA 5 % off the nozzle TFA is accepted"),
    Mutant("HC-tfa-prefers-nozzles", HC,
           "    tfa, tfa_basis = (recorded_tfa, \"recorded TFA\") if recorded_tfa else \\\n",
           "    tfa, tfa_basis = (nozzle_tfa or recorded_tfa, \"recorded TFA\") if recorded_tfa else \\\n", THC,
           "the nozzle TFA is used while the basis says 'recorded TFA'"),
    Mutant("HC-conflicting-mud-picks-first", HC, "        mw_pcf = None\n    else:\n",
           "        mw_pcf = weights[0]\n    else:\n", THC, "two different mud weights: the lowest is chosen silently"),
    Mutant("HC-missing-mud-as-zero", HC, "MudProperties(mw_pcf=mw_pcf).mw_ppg if mw_pcf else None,",
           "MudProperties(mw_pcf=mw_pcf).mw_ppg if mw_pcf else 0.0,", THC,
           "an unrecorded mud weight becomes 0 ppg instead of missing"),
    Mutant("HC-two-dp-rows-first", HC, "    row = dp_rows[0] if len(dp_rows) == 1 else {}\n",
           "    row = dp_rows[0] if dp_rows else {}\n", THC,
           "with two drilling-parameter rows the first one's values are shown as the inputs"),
    Mutant("HC-nozzle-count-defaulted", HC,
           "        qty = (row or {}).get(\"quantity\") if isinstance(row, dict) else None\n",
           "        qty = ((row or {}).get(\"quantity\") or 1) if isinstance(row, dict) else 1\n", THC,
           "a nozzle row without a count is read as one nozzle"),
    Mutant("HC-zero-flow-accepted", HC,
           "    return number if number is not None and number > 0 else None\n",
           "    return number if number is not None and number >= 0 else None\n", THC,
           "a recorded 0 (bit size, TFA, flow, HSI) is used as a value"),
    Mutant("HC-no-hsi-differs", HC,
           "        hsi_check = {\"status\": NOT_CHECKED, \"reason\": \"no HSI recorded on this report\"}\n",
           "        hsi_check = {\"status\": DIFFERS, \"reason\": \"no HSI recorded on this report\"}\n", THC,
           "a report without a recorded HSI is reported as disagreeing"),
    Mutant("HC-problems-ignored", HC, "    if not missing and not data[\"problems\"]:\n", "    if not missing:\n",
           THC, "the check computes although the inputs are ambiguous"),
    Mutant("HC-pump-output-unnamed", HC, "    if not flows:\n        missing.append(\"pump output\")\n",
           "    if False:\n        missing.append(\"pump output\")\n", THC,
           "missing pump output is not named among the missing inputs"),
    Mutant("HC-snapshot-not-frozen", HC, "    inputs[\"snapshot\"] = {", "    inputs[\"_unfrozen\"] = {",
           THC + [T323], "M328: the gathered inputs are not frozen, so the case cannot be replayed"),
    # ------------------------------------------------------------------ M317 cement job reconciliation
    Mutant("CJ-yield-unit-assumed", CJ,
           "    elif yield_unit is None:\n"
           "        notes.append(\"pumped volume not computed: the yield unit is not stored on the report and was not "
           "declared\")\n"
           "    else:\n"
           "        pumped = job[\"sacks\"] * bbl_per_sack(job[\"yield\"], yield_unit)\n",
           "    else:\n"
           "        pumped = job[\"sacks\"] * bbl_per_sack(job[\"yield\"], yield_unit or \"ft3/sk\")\n", TCJ,
           "an undeclared yield unit is assumed to be ft³/sk"),
    Mutant("CJ-gal-factor-wrong", CJ, "\"gal/sk\": 42.0,", "\"gal/sk\": 31.5,", TCJ,
           "gal/sk converted with a wrong gallons-per-barrel factor"),
    Mutant("CJ-litre-factor-rounded", CJ, "\"L/sk\": 158.987294928,", "\"L/sk\": 159.0,", TCJ,
           "litres per barrel rounded (0.008 % volume error)"),
    Mutant("CJ-unit-validated-late", CJ,
           "    if yield_unit is not None and yield_unit not in YIELD_UNITS:\n        raise ReconciliationError(",
           "    if False:\n        raise ReconciliationError(", TCJ,
           "an unregistered yield unit is accepted (and stored) whenever sacks or yield is missing"),
    Mutant("CJ-zero-sacks-computed", CJ,
           "    zeros = [k for k in (\"sacks\", \"yield\") if k in (job.get(\"recorded_zero\") or [])]\n",
           "    zeros = []\n", TCJ, "A-4 regression: a recorded 0 sacks yields a pumped volume of 0 bbl"),
    Mutant("CJ-zero-flag-dropped", CJ, "if _recorded_zero(v)]}", "if False]}", TCJ,
           "the recorded job no longer says which fields were recorded as 0"),
    Mutant("CJ-displacement-band-dropped", CJ,
           "            over = job[\"displacement_bbl\"] > capacity * (1 + DISPLACEMENT_TOLERANCE)\n",
           "            over = job[\"displacement_bbl\"] > capacity\n", TCJ,
           "the documented 2 % allowance on the capacity to the shoe is not applied"),
    Mutant("CJ-claims-consistent", CJ, "                status=OVER_CAPACITY if over else WITHIN,\n",
           "                status=OVER_CAPACITY if over else \"CONSISTENT\",\n", TCJ,
           "A-3 regression: an upper-bound check is reported as consistency"),
    Mutant("CJ-liner-checked", CJ, "    if string[\"kind\"] == \"liner\":\n", "    if False:\n", TCJ,
           "a liner's displacement is compared with the liner capacity (the running string is not modelled)"),
    Mutant("CJ-inverted-interval-accepted", CJ, "    elif boc <= toc:\n", "    elif boc < toc:\n", TCJ,
           "a zero-length interval (BOC = TOC) gives a 0 bbl gauge annulus instead of being refused"),
    Mutant("CJ-surface-toc-missing", CJ, "    if toc is None or boc is None:\n", "    if not toc or not boc:\n", TCJ,
           "a recorded TOC of 0 m (cement to surface) is treated as not recorded"),
    Mutant("CJ-excess-sign", CJ, "    excess = (pumped - gauge) / gauge * 100.0",
           "    excess = (gauge - pumped) / gauge * 100.0", TCJ, "the implied excess has the wrong sign"),
    Mutant("CJ-toc-difference-sign", CJ, "    toc_difference = (toc - cement[\"top_md\"])",
           "    toc_difference = (cement[\"top_md\"] - toc)", TCJ, "the TOC difference has the wrong sign"),
    Mutant("CJ-job-not-frozen", CJ, "\"job_snapshot\": {\"value\": dict(job),", "\"job_snapshot\": {\"value\": None,",
           TCJ, "M328: the recorded job is not frozen with the case"),
    Mutant("CJ-zero-difference-hidden", CJ,
           "\" (recorded TOC equals the architecture record)\" if result[\"toc_difference_m\"] == 0 else",
           "\"\" if result[\"toc_difference_m\"] == 0 else", TCJ,
           "a zero TOC difference disappears from the summary"),
    Mutant("CJ-cross-well", CJ, "    if revision[\"well_id\"] != job[\"well_id\"]:\n", "    if False:\n", TCJ,
           "a cement job is reconciled with another well's architecture"),
    # ------------------------------------------------------------------ M318 T&D friction sensitivity
    Mutant("TDS-comma-decimal-accepted", TDS,
           "    for token in str(text).replace(\";\", \" \").split():\n",
           "    for token in str(text).replace(\",\", \".\").replace(\";\", \" \").split():\n", TTDS,
           "D86 class: '0,25' would be read as 0.25 if the comma gate were removed (gate kept, belt-and-braces)",
           equivalent="the comma gate two lines above raises for every text containing ',', so the replace is "
                      "unreachable; the gate itself is mutated by TDS-comma-gate-dropped"),
    Mutant("TDS-comma-gate-dropped", TDS, "    if \",\" in str(text):\n        raise SensitivityError(",
           "    if False:\n        raise SensitivityError(", TTDS,
           "commas are no longer refused with the D86 explanation"),
    Mutant("TDS-range-widened", TDS, "        if not 0.0 <= float(value) <= 1.0:\n",
           "        if not 0.0 <= float(value) <= 5.0:\n", TTDS, "a friction factor above 1 is accepted"),
    Mutant("TDS-max-factors", TDS, "    if len(factors) > MAX_FACTORS:\n", "    if len(factors) > 10 * MAX_FACTORS:\n",
           TTDS, "the per-sweep limit is not enforced"),
    Mutant("TDS-interpolates", TDS,
           "            return {\"curve\": curve, \"status\": BETWEEN, \"friction_factors\": [ff_a, ff_b], \"unit\": unit,\n",
           "            return {\"curve\": curve, \"status\": BETWEEN, \"friction_factors\": [(ff_a + ff_b) / 2], "
           "\"unit\": unit,\n", TTDS, "a friction factor is interpolated (a calibration claim)"),
    Mutant("TDS-nonmonotonic-located", TDS, "    if not (rising or falling) or values[0] == values[-1]:\n",
           "    if values[0] == values[-1]:\n", TTDS, "an observation is located on a non-monotonic curve"),
    Mutant("TDS-single-factor-located", TDS, "    if len(points) < 2:\n", "    if len(points) < 1:\n", TTDS,
           "an observation is 'located' with a single modelled factor"),
    Mutant("TDS-outside-not-flagged", TDS, "    if observed < low or observed > high:\n", "    if False:\n", TTDS,
           "an observation outside the modelled range is not flagged BELOW / ABOVE"),
    Mutant("TDS-below-above-swapped", TDS, "        status = BELOW if observed < low else ABOVE\n",
           "        status = ABOVE if observed < low else BELOW\n", TTDS, "BELOW_RANGE and ABOVE_RANGE swapped"),
    Mutant("TDS-failed-factor-dropped", TDS,
           "            rows.append({\"friction_factor\": ff, \"status\": \"FAILED\", \"reason\": result.error,\n"
           "                         **{name: None for name in CURVES}, \"buckling\": None})\n",
           "            pass\n", TTDS, "an engine refusal for one factor disappears from the table"),
    Mutant("TDS-unpinned-allowed", TDS, "    if not (run.get(\"survey_source\") or {}).get(\"revision_id\"):\n",
           "    if False:\n", TTDS, "A-6 regression: a sweep on an unpinned survey is accepted"),
    Mutant("TDS-snapshot-not-stored", TDS, "\"run_snapshot\": {\"value\": result.get(\"run_snapshot\"), \"unit\": \"\",",
           "\"run_snapshot\": {\"value\": None, \"unit\": \"\",", TTDS,
           "M328: the run snapshot is not stored with the case"),
    Mutant("TDS-components-hash-blind", TDS,
           "    payload = json.dumps([dict(c) for c in components], sort_keys=True, default=str)\n",
           "    payload = json.dumps([dict(c) for c in components][:0], sort_keys=True, default=str)\n", TTDS,
           "the string hash ignores the components, so a changed string replays as MATCH"),
    Mutant("TDS-zero-observation-missing", TDS,
           "    if observed is None or isinstance(observed, bool) or not math.isfinite(float(observed)):\n",
           "    if not observed or isinstance(observed, bool) or not math.isfinite(float(observed)):\n", TTDS,
           "an observed 0 is treated as 'no observation entered'"),
    # ------------------------------------------------------------------ M320 D report section manifest
    Mutant("RS-empty-dict-counted", RS,
           "        return 1 if any(v not in (None, \"\", [], {}) for v in value.values()) else 0\n",
           "        return 1 if value else 0\n", TRS, "a dict of empty values counts as a recorded section"),
    Mutant("RS-missing-as-included", RS,
           "    return _entry(title, INCLUDED if n else NOT_RECORDED, n, \"\" if n else (detail_empty",
           "    return _entry(title, INCLUDED, n, \"\" if n else (detail_empty", TRS, "an empty section is reported INCLUDED"),
    Mutant("RS-listed-empty-as-included", RS,
           "    return _entry(title, INCLUDED if n else NOT_RECORDED, n, \"\" if n else detail_empty)",
           "    return _entry(title, INCLUDED, n, \"\" if n else detail_empty)", TRS,
           "M333: an empty NPT / cost / plan section is reported INCLUDED"),
    Mutant("RS-time-analysis-assumed", RS,
           "        _entry(\"Time analysis\", INCLUDED if total else NOT_RECORDED, None,",
           "        _entry(\"Time analysis\", INCLUDED, None,", TRS,
           "no logged time is reported as an included time analysis (100 % productive)"),
    Mutant("RS-cost-failure-as-empty", RS,
           "    if cost is None or data.get(\"cost_query_status\") == \"query-failed\":\n",
           "    if data.get(\"cost_query_status\") == \"query-failed\":\n", TRS,
           "a cost query that returned nothing (None) is reported as 'no cost records'"),
    Mutant("RS-not-rendered-hidden", RS, "        entries.append(_entry(title, NOT_RENDERED, n,",
           "        entries.append(_entry(title, INCLUDED, n,", TRS,
           "collected-but-not-rendered EOWR data is reported as included"),
    Mutant("RS-unknown-kind-as-ddr", RS, "    if kind == \"ddr\":\n        return ddr_manifest(data)\n",
           "    if kind != \"eowr\":\n        return ddr_manifest(data)\n", TRS,
           "an NPT / cost / plan report gets a DDR manifest it does not have"),
    Mutant("RS-version-dropped", RS, "    out = [[\"section manifest\", MANIFEST_VERSION]]\n", "    out = []\n", TRS,
           "the manifest version row is not written into the report"),
    Mutant("RS-summarised-as-included", RS, "        _entry(\"7. Casing and cementing\", SUMMARISED,",
           "        _entry(\"7. Casing and cementing\", INCLUDED,", TRS,
           "a counts-only section is reported as fully included"),
    # ------------------------------------------------------------------ M333 NPT / Cost / Plan manifests
    Mutant("RS-npt-kind-unmapped", RS, "    builder = {\"npt\": npt_manifest, ", "    builder = {\"npt_\": npt_manifest, ",
           TRS, "the NPT report silently loses its manifest again"),
    Mutant("RS-npt-subcodes-not-summarised", RS, "SUMMARISED if sub > 15 else", "SUMMARISED if sub > 99 else", TRS,
           "only the top 15 sub codes are shown but the manifest claims all are included"),
    Mutant("RS-npt-window-cost-reason", RS,
           "    elif windowed:\n        cost = _entry(\"NPT cost (allocated)\", NOT_RECORDED,",
           "    elif False:\n        cost = _entry(\"NPT cost (allocated)\", NOT_RECORDED,", TRS,
           "a date-windowed NPT report does not say why no cost was allocated"),
    Mutant("RS-known-zero-as-unknown", RS,
           "    return _entry(title, INCLUDED if value is not None else NOT_RECORDED, None,",
           "    return _entry(title, INCLUDED if value else NOT_RECORDED, None,", TRS,
           "a computed figure of 0 is reported as not recorded"),
    Mutant("RS-aggregation-counted-as-one", RS,
           "    return len(value) if isinstance(value, (dict, list, tuple)) else _count(value)\n",
           "    return _count(value)\n", TRS, "an aggregation of N groups is reported as 1 row"),
    Mutant("RS-plan-versions-claimed-rendered", RS,
           "        _entry(\"Other plan versions\", NOT_RENDERED if others else INCLUDED,",
           "        _entry(\"Other plan versions\", INCLUDED,", TRS,
           "inactive plan versions are collected but the manifest claims they are rendered"),
    Mutant("RS-cost-projection-unknown-as-included", RS,
           "        _known(\"Projection (rate × days)\", data.get(\"projected_total_cost\"), no_rate),\n",
           "        _entry(\"Projection (rate × days)\", INCLUDED, None, \"\"),\n", TRS,
           "a cost report without rates claims a projection"),
    # ------------------------------------------------------------------ M334 citation record navigation
    Mutant("CR-nav-mismatch-opens", CR, "OPENABLE = (EXACT, PAGE_CHANGED)\n",
           "OPENABLE = (EXACT, PAGE_CHANGED, SPAN_MISMATCH)\n", TCR,
           "a span that does not hold the quote is opened as if it were the cited passage"),
    Mutant("CR-nav-changed-refused", CR, "OPENABLE = (EXACT, PAGE_CHANGED)\n", "OPENABLE = (EXACT,)\n", TCR,
           "a changed page cannot be opened although the viewer would state the change"),
    Mutant("CR-nav-misaligned-accepted", CR, "    if len(citations) != len(results):\n", "    if False:\n", TCR,
           "results of another record are paired with this record's citations"),
    Mutant("CR-nav-wrong-span", CR, "start=int(entry[\"start\"]), end=int(entry[\"end\"])",
           "start=int(entry[\"start\"]), end=int(entry[\"end\"]) + 1", TCR,
           "the opened span is not the recorded span"),
    Mutant("KA-nav-guard-dropped", KA, "        if not target[\"openable\"]:\n            self.citation_status.setText(",
           "        if False:\n            self.citation_status.setText(", TCR,
           "the open action bypasses the openable check"),
    Mutant("KA-nav-stale-targets", KA, "            self.citation_status.setText(f\"Not verified: {exc}\")\n"
           "            self._show_record_targets([])\n",
           "            self.citation_status.setText(f\"Not verified: {exc}\")\n", TCR,
           "an unreadable file leaves the previous record's passages openable"),
    # ------------------------------------------------------------------ M320 E citation record
    Mutant("CR-page-hash-unchecked", CR, "            if _sha(text) != entry[\"text_version\"]:\n",
           "            if False:\n", TCR, "a re-reviewed page is not reported PAGE_CHANGED"),
    Mutant("CR-span-unchecked", CR,
           "            if not (0 <= start < end <= len(text)) or text[start:end] != entry[\"quote\"]:\n",
           "            if not (0 <= start < end <= len(text)):\n", TCR,
           "a span that no longer holds the quote is reported EXACT"),
    Mutant("CR-foreign-page-accepted", CR,
           "            if page is None or page.document_id != int(entry[\"document_id\"]):\n",
           "            if page is None:\n", TCR, "a page id of another document is accepted"),
    Mutant("CR-document-unchecked", CR,
           "            if session.get(Document, int(entry[\"document_id\"])) is None:\n",
           "            if False:\n", TCR, "a deleted document is reported as a missing page"),
    Mutant("CR-quote-not-required", CR,
           "REQUIRED = (\"label\", \"document_id\", \"page_id\", \"page_no\", \"start\", \"end\", \"text_version\", \"quote\")",
           "REQUIRED = (\"label\", \"document_id\", \"page_id\", \"page_no\", \"start\", \"end\", \"text_version\")",
           TCR, "an entry without its quote is checked instead of reported UNREADABLE"),
    Mutant("CR-version-unchecked", CR,
           "    from core.database import Document, DocumentPage\n\n"
           "    if not isinstance(record, dict) or record.get(\"record_version\") != RECORD_VERSION:\n",
           "    from core.database import Document, DocumentPage\n\n    if not isinstance(record, dict):\n", TCR,
           "verify_record accepts any JSON dict as a citation record"),
    Mutant("CR-load-version-unchecked", CR,
           "from exc\n    if not isinstance(record, dict) or record.get(\"record_version\") != RECORD_VERSION:\n",
           "from exc\n    if not isinstance(record, dict):\n", TCR,
           "loading a file accepts any JSON dict as a citation record"),
    Mutant("CR-semantic-label-dropped", CR, "        \"semantic_label\": ka.SEMANTIC_LABEL,\n",
           "        \"semantic_label\": \"\",\n", TCR, "the 'Not semantically verified' label is not recorded"),
    Mutant("CR-uncited-recorded", CR,
           "    used = [e for e in answer.evidence if e.label in cited] if cited else list(answer.evidence)\n",
           "    used = list(answer.evidence)\n", TCR, "retrieved-but-uncited passages are recorded as citations"),
    # ------------------------------------------------------------------ M308 / D74 window-release policy
    Mutant("QL-threshold-6.8.1", QL, "FIXED_PYSIDE = (6, 8, 2)", "FIXED_PYSIDE = (6, 8, 1)", TQL,
           "closed windows are freed on the crashing PySide6 6.8.1.x"),
    Mutant("QL-operator-override-ignored", QL, "    if str(env.get(RETAIN_ENV, \"\")).strip() == \"1\":\n",
           "    if False:\n", TQL, "DRILLMASTER_RETAIN_CLOSED_WINDOWS=1 is ignored"),
    Mutant("QL-unknown-version-released", QL,
           "    if parsed is None:\n        return {\"release\": False,",
           "    if parsed is None:\n        return {\"release\": True,", TQL,
           "an unrecognised PySide6 version frees windows (unsafe default)"),
    Mutant("QL-lenient-version", QL, "        if not digits or digits != piece:\n", "        if not digits:\n", TQL,
           "'6.8.x'-like versions are parsed by stripping non-digits"),
    # ------------------------------------------------------------------ M328 History replay
    Mutant("HR-tolerance-widened", HR,
           "            if not (math.isfinite(a) and math.isfinite(b)) or abs(a - b) > tolerance:\n",
           "            if not (math.isfinite(a) and math.isfinite(b)) or abs(a - b) > 1.0:\n", THR,
           "a 0.01 bbl change replays as MATCH"),
    Mutant("HR-one-sided-fields-ignored", HR, "    for key in sorted(set(stored) | set(fresh)):\n",
           "    for key in sorted(set(stored) & set(fresh)):\n", THR,
           "a result field present on one side only is not reported"),
    Mutant("HR-text-not-compared", HR, "        elif a != b:\n", "        elif False:\n", THR,
           "a changed status / label (e.g. EXCEEDS_CAPACITY -> WITHIN_UPPER_BOUND) replays as MATCH"),
    Mutant("HR-keyerror-as-not-found", HR,
           "    except KeyError as exc:                         # a KeyError is a LookupError: a malformed snapshot, "
           "not a miss\n"
           "        return _outcome(\"UNREADABLE\", f\"the frozen snapshot lacks the field {exc}; nothing was "
           "recomputed\", current)\n", "", THR, "a malformed snapshot is reported NOT_REPRODUCIBLE"),
    Mutant("HR-survey-hash-unchecked", HR,
           "    if sr.stations_sha256(snap.get(\"survey\") or []) != pin.get(\"stations_sha256\") \\\n"
           "            or pin.get(\"stations_sha256\") != _input(inputs, \"survey_stations_sha256\"):\n",
           "    if False:\n", THR, "edited frozen survey stations are replayed"),
    Mutant("HR-architecture-pin-unchecked", HR,
           "    if revision[\"components_sha256\"] != _input(inputs, \"components_sha256\"):\n", "    if False:\n",
           THR, "a cement case is replayed against an architecture revision with another SHA-256"),
    Mutant("HR-m317-version-unchecked", HR, "    if version != cj.METHOD_VERSION:\n", "    if False:\n", THR,
           "a case of a retired M317 method version is replayed with the current method"),
    Mutant("HR-m318-legacy-replayed", HR,
           "    if not isinstance(_input(inputs, \"run_snapshot\"), dict):\n"
           "        return \"NOT REPRODUCIBLE\", \"the case was saved before M328 and holds no frozen run snapshot\"\n",
           "", THR, "a pre-M328 T&D case is claimed REPRODUCIBLE"),
    Mutant("HR-m314-legacy-replayed", HR,
           "    if not isinstance(_input(inputs, \"snapshot\"), dict):\n"
           "        return \"NOT REPRODUCIBLE\", \"the case was saved before M328 and holds no frozen input snapshot\"\n",
           "", THR, "a pre-M328 hydraulics case is claimed REPRODUCIBLE"),
    Mutant("HR-rerun-link-type", HR, "        source_link={\"link_type\": \"rerun_of\",",
           "        source_link={\"link_type\": \"recalculation_of\",", THR,
           "a replay is linked as a recalculation with another method"),
    Mutant("HR-m314-problems-dropped", HR,
           "    data = {\"inputs\": snapshot[\"inputs\"], \"problems\": list(snapshot[\"problems\"]),\n",
           "    data = {\"inputs\": snapshot[\"inputs\"], \"problems\": [],\n", THR,
           "frozen gathering problems are not replayed",
           equivalent="save_check stores only COMPUTED checks, and evaluate() computes only when problems == [], so "
                      "every frozen snapshot that reaches replay has problems == []; the presence check one line "
                      "above (list type) is still enforced"),
    # ------------------------------------------------------------------ M323 / D89 new-record NULLs
    Mutant("W3C-cement-placeholders-saved", W3C,
           "        self._loaded_cement_source = {key: None for key in self.CEMENT_NULL_FIELDS}\n",
           "        self._loaded_cement_source = {}\n", TW3C,
           "D89 regression: a new cement report stores yield 1.18 / TOC 0 placeholders as data"),
    Mutant("W3C-casing-placeholders-saved", W3C,
           "        self._loaded_casing_source = {key: None for key in self.CASING_NULL_FIELDS}\n",
           "        self._loaded_casing_source = {}\n", TW3C,
           "D89 regression: a new casing report stores 0 psi / 0 lbf placeholders as data"),
    Mutant("W3C-new-record-banner", W3C, "        self._cement_new_record = True\n",
           "        self._cement_new_record = False\n", TW3C,
           "a new cement report is labelled as database NULLs instead of NOT RECORDED YET"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
