"""Application DDR import service, shared by the desktop dialog and certification.

No Qt dependency. Preview/confirmation remains in the dialog; this service is
its sole transactional domain/persistence pathway (not an alternate importer).
"""
import os
from pathlib import Path
import json
import logging
from datetime import date as dt_date
from typing import Optional
from core.value_normalizer import ValueNormalizer
from core.text_utils import wrap_text
from core.import_quality import ImportValidator, find_duplicates, TimeLogValidator, ReviewItem
from core.import_diagnostics import PersistenceIssue, ImportStatus, determine_import_status

logger = logging.getLogger(__name__)

def _canonical_review_row(payload: dict, *, default_status: str = "REVIEW_REQUIRED") -> dict:
    """Normalize every producer to the shared, lossless ReviewItem shape.

    Persistence producers may only have a row-level ``_source_cells`` map,
    while field mapping has an Excel cell.  Both are retained: ``source_cell``
    is the compact display token and ``source_location`` is the structured
    lineage object used by audits and exports.
    """
    row = dict(payload or {})
    if "row" not in row and row.get("source_row") is not None:
        row["row"] = row["source_row"]
    if "source_location" not in row and row.get("source_cells") is not None:
        row["source_location"] = row["source_cells"]
    location = row.get("source_location")
    if isinstance(location, dict):
        location = dict(location)
        location.setdefault("file", row.get("file") or row.get("source_document", ""))
        location.setdefault("sheet", row.get("sheet", ""))
        if row.get("row"):
            location.setdefault("row", row["row"])
        if row.get("column") not in (None, ""):
            location.setdefault("column", row["column"])
        row["source_location"] = location
    if isinstance(row.get("source_cell"), dict):
        row["source_location"] = row.get("source_location") or row["source_cell"]
        cell_map = row["source_cell"]
        row["source_cell"] = (
            cell_map.get("cell") or cell_map.get("source_cell")
            or "; ".join(str(value) for value in cell_map.values() if value not in (None, ""))
        )
    elif not row.get("source_cell") and isinstance(location, dict):
        # Use a compact cell token for display, while retaining the complete
        # row/table cell map in source_location.
        row["source_cell"] = location.get("cell") or location.get("address") or ""
        if not row["source_cell"] and isinstance(location.get("cells"), dict):
            row["source_cell"] = "; ".join(
                str(value) for value in location["cells"].values() if value not in (None, "")
            )
        if not row["source_cell"]:
            row["source_cell"] = "; ".join(
                str(value) for key, value in location.items()
                if key not in {"file", "sheet", "row", "column", "table"}
                and value not in (None, "")
                and not isinstance(value, (dict, list))
            )
    row.setdefault("source_document", row.get("file", ""))
    field = row.get("field") or row.get("canonical_field") or row.get("target_field", "")
    row["field"] = field
    if not row.get("entity"):
        row["entity"] = "time_log_morning" if "continuation_text" in row else row.get("record_type", "time_log")
    if row.get("entity") == "time_log" and "." in field:
        row["entity"] = field.split(".", 1)[0]
    row.setdefault("detected_table", row.get("entity", ""))
    row.setdefault("expected_type", "canonical value")
    row.setdefault("mapping_method", row.get("extraction_method") or (
        "excel-template" if row.get("sheet") or row.get("file") else "persistence-validation"
    ))
    row.setdefault("classification", row.get("classification") or "review-required")
    row.setdefault("status", default_status)
    row.setdefault("decision", "REVIEW")
    row.setdefault("reason", row.get("message", "Review required"))
    row.setdefault("validation_message", row.get("reason", "Review required"))
    return ReviewItem.from_dict(row).to_dict()


def _enrich_record_reviews(items: list, records: list, entity: str) -> list:
    """Attach table provenance to persistence-generated review rows."""
    indexed = {
        record.get("_source_row"): record
        for record in records or []
        if isinstance(record, dict) and record.get("_source_row") is not None
    }
    for item in items or []:
        record = indexed.get(item.get("source_row"))
        if record is None and isinstance(item.get("source_location"), dict):
            source_cells = item["source_location"].get("cells") or item["source_location"]
            record = next(
                (candidate for candidate in records or []
                 if isinstance(candidate, dict) and candidate.get("_source_cells") == source_cells),
                None,
            )
        if not isinstance(record, dict):
            record = {}
        location = dict(record.get("_source_location") or {})
        location.setdefault("file", record.get("_source_file", ""))
        location.setdefault("sheet", record.get("_source_sheet", ""))
        location.setdefault("row", record.get("_source_row"))
        location.setdefault("cells", record.get("_source_cells", {}))
        item.setdefault("source_location", location)
        item.setdefault("file", record.get("_source_file", ""))
        item.setdefault("sheet", record.get("_source_sheet", ""))
        item.setdefault("source_document", record.get("_source_file", ""))
        item.setdefault("entity", entity)
        item.setdefault("detected_table", entity)
        item.setdefault("mapping_method", "excel-template-table")
        item.setdefault("expected_type", "canonical row")
    return items


class DDRImportService:
    def __init__(self, db_manager=None, well_id=None):
        self.db = db_manager
        self.well_id = well_id

    def import_records(self, extracted):
        from core.save_outcome import public_status
        result = self._do_import(extracted)
        result["outcome_status"] = public_status(result["status"])
        return result

    def _resolve_import_well(self, well_info, session=None):
        """Resolve workbook well with universal aliases."""
        from core.database import Well, Project
        # Universal alias handling
        name_candidates = ["name", "well_name", "well", "well_number", "well_id", "well_number_text", "نام چاه", "well designation", "wellname"]
        name = ""
        for k in name_candidates:
            v = (well_info or {}).get(k)
            if v and str(v).strip():
                name = str(v).strip()
                break
        code = self._safe_text((well_info or {}).get("code"), "") or self._safe_text((well_info or {}).get("well_code"), "")

        if not name and not code:
            return self.well_id

        owns_session = session is None
        session = session or self.db.create_session()
        try:
            from core.combo_identity import ComboOption, resolve_options
            fallback = session.get(Well, self.well_id) if self.well_id else None
            query = session.query(Well)
            if fallback:
                query = query.filter(Well.project_id == fallback.project_id)
            options = [ComboOption(w.id, w.name, w.code) for w in query.all()]
            resolution = resolve_options(code or name, options, field="well.identity")
            if resolution.accepted:
                self.well_id = resolution.identity
                return self.well_id
            if resolution.method == "ambiguous":
                raise ValueError("Well identity is ambiguous in the selected project; select a unique well/code")
            project_ids = [r[0] for r in session.query(Project.id).all()]
            if fallback:
                project_id = fallback.project_id
            elif len(project_ids) == 1:
                project_id = project_ids[0]
            else:
                raise ValueError("Select a well/project context before importing: project identity is ambiguous")
            if not project_id:
                raise ValueError("Cannot create imported well: no project exists")
            valid_keys = {c.name for c in Well.__table__.columns}
            values = {k: v for k, v in (well_info or {}).items() if k in valid_keys and k != "id"}
            values.update({"project_id": project_id, "name": name or code})
            if code:
                values["code"] = code
            values = self.db.coerce_model_values(Well, values)
            well = Well(**values)
            session.add(well)
            session.flush()
            if owns_session:
                session.commit()
            self.well_id = well.id
            return well.id
        finally:
            if owns_session:
                session.close()


    def _do_import(self, extracted, refresh_ui=True):
        from core.save_outcome import public_status
        result = self._execute_import(extracted, refresh_ui=refresh_ui)
        result["outcome_status"] = public_status(result["status"])
        return result

    def _execute_import(self, extracted: dict, refresh_ui: bool = True) -> dict:
        """Core import logic with atomic transaction and no fake defaults."""
        from copy import deepcopy
        extracted = deepcopy(extracted)
        import hashlib
        source_snapshot = json.loads(json.dumps(extracted, sort_keys=True, default=str))
        source_fingerprint = hashlib.sha256(json.dumps(source_snapshot, sort_keys=True).encode("utf-8")).hexdigest()
        results = {
            "imported": 0,
            "failed": 0,
            "details": [],
            "well_id": self.well_id,
            "report_id": None,
            "section_id": None,
            "import_report": None,
            "status": "ACCEPT",
            "review": 0,
            "review_items": [],
            "diagnostics": [],
            "validation_errors": 0,
            "validation_diagnostics": [],
        }
        # Every object created or updated below participates in this one
        # session. Helpers receive it explicitly and only flush for IDs.
        try:
            self.db.assert_import_schema_supported()
        except Exception as schema_exc:
            issue = getattr(schema_exc, "issue", None) or PersistenceIssue.from_exception(
                schema_exc,
                stage="schema.compatibility",
                entity="database",
                operation="verify-before-import",
                status=ImportStatus.PERSISTENCE_ERROR.value,
            )
            results["status"] = ImportStatus.PERSISTENCE_ERROR.value
            results["failed"] = 1
            results["diagnostics"].append(issue.to_dict())
            results["details"].append(f"❌ Import blocked by schema compatibility: {issue.message}")
            return results
        session = self.db.create_session()
        report_id = None
        stage = "validation"

        try:
            from core.database import Section
            report_data = extracted.get("daily_report", {})
            quality = ImportValidator.validate_rows([report_data], "daily_report", "Daily Report")
            time_logs = extracted.get("time_logs_24h", []) or []

            # Professional time log validation
            time_validation = TimeLogValidator.validate_logs(time_logs, sheet="Time Logs 24H")
            quality.issues.extend(time_validation.issues)

            # Keep every source row through the persistence boundary. Invalid
            # and continuation rows are represented as ReviewItems there;
            # they are never silently filtered out before provenance capture.
            extracted["time_logs_24h"] = time_logs

            duplicate_indexes = set(find_duplicates(time_logs, "time_log"))
            quality.total += time_validation.total
            quality.failed += time_validation.failed
            results["import_report"] = quality.as_dict()
            results["import_report"]["review"].extend((extracted.get("metadata") or {}).get("review_matrix", []))
            results["import_report"]["review"] = [
                _canonical_review_row(item)
                for item in results["import_report"].get("review", [])
            ]
            results["review"] = len(results["import_report"].get("review", []))
            results["review_items"].extend(results["import_report"].get("review", []))

            # Every collected validation error participates in final status.
            # Validation is completed before any destructive/write operation.
            if quality.errors:
                results["validation_errors"] = len(quality.errors)
                results["validation_diagnostics"] = [
                    PersistenceIssue(
                        stage="validation.import",
                        entity=issue.field or "import_record",
                        field=issue.field or "",
                        source={"file": extracted.get("metadata", {}).get("source_file", ""), "sheet": issue.sheet, "row": issue.row},
                        row=issue.row,
                        original_value=issue.value,
                        expected_type="canonical value",
                        operation="validate",
                        message=issue.message,
                        status=ImportStatus.VALIDATION_ERROR.value,
                    ).to_dict()
                    for issue in quality.errors
                ]
                results["diagnostics"].extend(results["validation_diagnostics"])
                results["status"] = ImportStatus.VALIDATION_ERROR.value
                results["details"].append(
                    f"❌ Import stopped before persistence: {len(quality.errors)} validation error(s)"
                )
                session.rollback()
                return results

            if duplicate_indexes:
                results["details"].append(f"⚠️ Skipped {len(duplicate_indexes)} duplicate time-log rows")

            # Well
            stage = "well"
            wi = extracted.get("well_info", {})
            # Well-level header attributes that live in the report header
            # (LTA days, actual rig days) belong on the Well record too —
            # generic copy, not company-specific.
            _dr_header = extracted.get("daily_report", {}) or {}
            for _wkey in ("lta_day", "actual_rig_days"):
                if (
                    _wkey in _dr_header
                    and _dr_header.get(_wkey) not in (None, "")
                    and _wkey not in wi
                ):
                    wi[_wkey] = _dr_header[_wkey]
            if not self.well_id or wi.get("name") or wi.get("code"):
                self._resolve_import_well(wi, session=session)
                results["well_id"] = self.well_id
            previous = self.db.find_import_audit(source_fingerprint, session=session, well_id=self.well_id)
            if previous:
                prior_result = dict(previous["result"])
                prior_result.update(imported=0, reimport=True)
                prior_result["details"] = ["Identical source already imported; existing report retained without duplicate records"]
                self.well_id = prior_result["well_id"]
                return prior_result

            if wi:
                wi_save = dict(wi)
                wi_save["id"] = self.well_id
                if self.db.save_well(wi_save, session=session):
                    results["details"].append(f"✅ Well Info: {len(wi)} fields (identity resolved via universal aliases)")

            # Wellbore (Schema v3) — attribute ONLY when the source explicitly
            # names one. No wellbore is invented from a rig, a well name, or a
            # section: an ambiguous DDR leaves wellbore_id = NULL ("unknown"),
            # preserving uncertainty over fabricating certainty. A sidetrack
            # name is a distinct wellbore and is never merged into its parent.
            stage = "wellbore"
            wellbore_id = None
            wellbore_name = self._safe_text(
                wi.get("wellbore_name") or wi.get("wellbore"), ""
            )
            if wellbore_name:
                wellbore_type = (
                    "sidetrack"
                    if self._safe_text(wi.get("wellbore_type"), "").lower()
                    == "sidetrack"
                    else "original"
                )
                wellbore_id = self.db.get_or_create_wellbore(
                    self.well_id,
                    wellbore_name,
                    session=session,
                    wellbore_type=wellbore_type,
                )
                if wellbore_id:
                    results["wellbore_id"] = wellbore_id
                    results["details"].append(
                        f"✅ Wellbore '{wellbore_name}' resolved "
                        f"(identity: well + wellbore name)"
                    )

            # Section
            stage = "section"
            section_name = self._safe_text(wi.get("section_name"), "Imported Section")
            section_id = None

            existing = session.query(Section).filter(
                Section.well_id == self.well_id,
                Section.name == section_name,
            ).first()

            if existing:
                section_id = existing.id
                # Backfill wellbore_id only when we now have a deterministic
                # attribution and the section had none — never overwrite an
                # existing, possibly different, wellbore assignment.
                if wellbore_id and existing.wellbore_id is None:
                    existing.wellbore_id = wellbore_id
            else:
                dr_data = extracted.get("daily_report", {})
                depth_from = ValueNormalizer.to_float(dr_data.get("depth_0000"))
                depth_to = ValueNormalizer.to_float(dr_data.get("depth_2400"))
                new_section = Section(
                    well_id=self.well_id,
                    wellbore_id=wellbore_id,
                    name=section_name,
                    code=self._safe_text(wi.get("section_code"), ""),
                    depth_from=depth_from,
                    depth_to=depth_to,
                )
                session.add(new_section)
                session.flush()
                section_id = new_section.id
                results["details"].append(f"✅ Section '{section_name}' created (identity: name + depth range)")

            if not section_id:
                results["validation_errors"] += 1
                results["status"] = ImportStatus.VALIDATION_ERROR.value
                issue = PersistenceIssue(
                    stage="validation.section", entity="section", field="section_id",
                    original_value=section_name, operation="validate",
                    message="No valid section could be resolved", status=ImportStatus.VALIDATION_ERROR.value,
                )
                results["diagnostics"].append(issue.to_dict())
                results["details"].append("❌ No valid section - MISSING_INPUT")
                session.rollback()
                return results

            results["section_id"] = section_id

            # Daily Report - no fake defaults
            stage = "daily_report"
            dr = dict(extracted.get("daily_report", {}))
            dr["well_id"] = self.well_id
            dr["section_id"] = section_id
            # Carry the deterministically-resolved wellbore onto the report;
            # stays absent (NULL) when the source did not name a wellbore.
            if wellbore_id:
                dr["wellbore_id"] = wellbore_id
            raw_report_date = dr.get("report_date") or wi.get("report_date")
            if raw_report_date in (None, ""):
                results["validation_errors"] += 1
                results["status"] = ImportStatus.VALIDATION_ERROR.value
                issue = PersistenceIssue(
                    stage="validation.daily_report", entity="daily_report", field="report_date",
                    original_value=raw_report_date, operation="validate",
                    message="Report date is required", status=ImportStatus.VALIDATION_ERROR.value,
                )
                results["diagnostics"].append(issue.to_dict())
                results["details"].append("❌ Import stopped: report date is missing - MISSING_INPUT")
                session.rollback()
                return results
            dr["report_date"] = self._normalize_date(raw_report_date)
            dr.setdefault("status", "Draft")

            supplied_report_number = ValueNormalizer.to_int(dr.get("report_number"))
            report_num = self._ensure_report_number(dr, section_id, session=session)
            dr["report_number"] = report_num
            dr["report_number_source"] = "imported" if supplied_report_number else "generated"

            if not dr.get("rig_day"):
                dr["rig_day"] = report_num
            else:
                dr["rig_day"] = ValueNormalizer.to_int(dr["rig_day"]) or report_num

            # Depth fields - preserve None, no fake 0
            for depth_field in ["depth_0000", "depth_0600", "depth_2400"]:
                parsed_depth = ValueNormalizer.to_float(dr.get(depth_field))
                dr[depth_field] = parsed_depth  # None if missing, not 0

            # Notes (Note#01/Note#02 ...) -> report summary, deduplicated
            # and stripped of stray label cells; the note_* keys themselves
            # are not DailyReport columns and are dropped by the saver.
            note_values = []
            for key in sorted(k for k in dr if k.startswith("note_")):
                val = dr.get(key)
                if isinstance(val, str) and val.strip() and val.strip().lower().startswith("note#"):
                    if val not in note_values:
                        note_values.append(val.strip())
            if note_values:
                existing_summary = (dr.get("summary") or "").strip()
                if existing_summary:
                    dr["summary"] = existing_summary + "\n\n" + "\n".join(note_values)
                else:
                    dr["summary"] = "\n".join(note_values)

            # Operation forecast (next-day plan) from the report header
            # -> DailyReport.forecast (nullable; absent stays absent).
            if dr.get("forecast") in (None, ""):
                forecast_val = extracted.get("daily_report", {}).get("forecast")
                if isinstance(forecast_val, str) and forecast_val.strip():
                    dr["forecast"] = forecast_val.strip()

            # The outer transaction itself protects existing reports; taking
            # a separately committed snapshot would create a second boundary.
            saved = self.db.save_daily_report(dr, session=session)
            report_id = None

            if saved and saved.get("id"):
                report_id = saved["id"]
                results["report_id"] = report_id
                results["imported"] += 1
                results["details"].append(f"✅ Report #{saved.get('report_number', '?')} - Atomic transaction started")
            else:
                report_id = self._create_fallback_report(dr, section_id, report_num, results, session=session)

            if not report_id:
                results["details"].append("❌ Could not create Daily Report")
                results["validation_errors"] += 1
                results["status"] = ImportStatus.VALIDATION_ERROR.value
                issue = PersistenceIssue(
                    stage="persistence.daily_report", entity="daily_report", field="id",
                    original_value=dr, operation="insert",
                    message="Daily report could not be created", status=ImportStatus.VALIDATION_ERROR.value,
                )
                results["diagnostics"].append(issue.to_dict())
                session.rollback()
                return results

            results["report_id"] = report_id

            # Mud with unit preservation
            stage = "mud_report"
            mud_data = extracted.get("mud_report", {}) or {}
            # The existing MudReport widget/model is PCF-native. Source
            # representation remains in immutable audit; all explicit units
            # reach the same domain unit, including suffix-bearing strings.
            from core.mud_records import mud_density_pcf
            mud_data, density_lineage = mud_density_pcf(mud_data)
            if density_lineage:
                results["details"].append("Density converted to PCF using the existing UnitManager")

            self._save_mud_report(mud_data, report_id, dr["report_date"],
                                  daily_report=dr, session=session)

            # Drilling params with universal aliases
            stage = "drilling_parameters"
            drilling_extracted = extracted.get("drilling_params", {})
            # Map WOB aliases
            wob_aliases = ["wob", "wt. on bit", "bit load", "weight on bit", "w.o.b", "wob_max"]
            for alias in wob_aliases:
                if alias in drilling_extracted and "wob_max" not in drilling_extracted:
                    drilling_extracted["wob_max"] = drilling_extracted[alias]

            self._save_drilling_params(
                drilling_extracted, report_id, dr["report_date"],
                param_table=extracted.get("drilling_params_table") or [],
                scr_data=extracted.get("scr_data") or [],
                session=session,
            )

            if extracted.get("time_logs_24h"):
                stage = "time_logs_24h"
                time_result = self._save_time_logs(report_id, extracted["time_logs_24h"], session=session)
                results.setdefault("review_items", []).extend(
                    _canonical_review_row(item) for item in time_result.get("review", [])
                )
                results["review"] = results.get("review", 0) + len(time_result.get("review", []))
                results["details"].append(
                    f"✅ Time logs: {time_result.get('valid', 0)} valid, "
                    f"{len(time_result.get('review', []))} reviewable - no invented times"
                )

            if extracted.get("time_logs_morning"):
                stage = "time_logs_morning"
                morning_result = self._save_morning_logs(report_id, extracted["time_logs_morning"], session=session)
                results.setdefault("review_items", []).extend(
                    _canonical_review_row(item) for item in morning_result.get("review", [])
                )
                results["review"] = results.get("review", 0) + len(morning_result.get("review", []))
                results["details"].append(
                    f"✅ Morning logs: {morning_result.get('valid', 0)} valid, "
                    f"{len(morning_result.get('review', []))} reviewable continuation/invalid rows"
                )

            # Atomic multi-tab import
            stage = "multi_tab_persistence"
            if hasattr(self.db, 'save_imported_multi_tab_data_atomic'):
                try:
                    multi_res = self.db.save_imported_multi_tab_data_atomic(
                        self.well_id, report_id, extracted, session=session
                    )
                    results.setdefault("diagnostics", []).extend(multi_res.get("diagnostics", []))
                    review_rows = [
                        _canonical_review_row(item)
                        for item in multi_res.get("review_rows", [])
                    ]
                    results.setdefault("review_items", []).extend(review_rows)
                    results["review"] = results.get("review", 0) + multi_res.get("review", 0)
                    results["validation_errors"] = results.get("validation_errors", 0) + multi_res.get("validation_errors", 0)
                    if multi_res.get("validation_errors", 0):
                        session.rollback()
                        results["status"] = ImportStatus.VALIDATION_ERROR.value
                        results["imported"] = 0
                        results["failed"] = 0
                        results["details"].append(
                            "❌ Import rolled back before commit: validation errors in report-scoped rows"
                        )
                        return results
                    for k, count in multi_res.items():
                        if k in ("failed", "error", "imported", "review", "diagnostics", "review_rows", "validation_errors", "survey_review", "survey_rejected", "survey_calculated"):
                            if k == "failed":
                                results["failed"] += int(count or 0)
                            continue
                        if isinstance(count, (int, float)) and count > 0:
                            results["details"].append(f"✅ {k}: {count} records imported (atomic)")
                    results["imported"] += multi_res.get("imported", 0)
                except Exception as atomic_exc:
                    logger.error(f"Atomic multi-tab import failed: {atomic_exc}", exc_info=True)
                    diagnostic = getattr(atomic_exc, "issue", None)
                    atomic_result = getattr(atomic_exc, "result", {}) or {}
                    results.setdefault("diagnostics", []).extend(
                        item for item in atomic_result.get("diagnostics", [])
                        if item not in results["diagnostics"]
                    )
                    if diagnostic is not None and diagnostic.to_dict() not in results["diagnostics"]:
                        results.setdefault("diagnostics", []).append(diagnostic.to_dict())
                    results.setdefault("review_items", []).extend(
                        _canonical_review_row(item)
                        for item in atomic_result.get("review_rows", [])
                    )
                    results["failed"] += 1
                    results["details"].append(f"↩️ Atomic rollback: {atomic_exc} - No partial data kept")
                    raise

            if results["failed"]:
                session.rollback()
                results["details"].append("↩️ Import rolled back: no partial report was kept - Transaction integrity preserved")
                results["imported"] = 0
                return results

            results["status"] = determine_import_status(
                persistence_error=False,
                validation_error=bool(results.get("validation_errors", 0)),
                review_required=bool(results.get("review", 0)),
            )
            stage = "daily_report_calculations"
            self.db.auto_update_from_daily_report(report_id, session=session)
            self.db.save_import_audit(report_id, source_fingerprint, source_snapshot, results, session=session)
            # Provenance/reviews and domain rows commit together.
            session.commit()
            results["details"].append("✅ Atomic transaction committed - valid rows saved; review rows retained in import audit")
            return results

        except Exception as e:
            results["failed"] = max(1, results.get("failed", 0))
            diagnostic = getattr(e, "issue", None)
            if diagnostic is None:
                diagnostic = PersistenceIssue.from_exception(
                    e,
                    stage=f"import.{stage}",
                    entity=stage,
                    operation="flush/commit",
                )
            results["status"] = diagnostic.status
            issue_dict = diagnostic.to_dict()
            if issue_dict not in results.setdefault("diagnostics", []):
                results["diagnostics"].append(issue_dict)
            results["details"].append(f"❌ Error: {str(e)}")
            logger.error(f"Import error: {e}", exc_info=True)
            if session:
                try:
                    session.rollback()
                    results["details"].append("↩️ Import rolled back after failure - No orphan data")
                except Exception:
                    logger.error("Import rollback failed", exc_info=True)
            return results
        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass


    def _ensure_report_number(self, dr: dict, section_id: int, session=None) -> int:
        if dr.get("report_number"):
            num = ValueNormalizer.to_int(dr["report_number"])
            if num and num > 0:
                return num

        from core.database import DailyReport
        owns_session = session is None
        session = session or self.db.create_session()
        try:
            last = session.query(DailyReport).filter(
                DailyReport.section_id == section_id,
            ).order_by(DailyReport.report_number.desc()).first()
            return (last.report_number + 1) if last else 1
        finally:
            if owns_session:
                session.close()


    def _create_fallback_report(self, dr: dict, section_id: int, report_num: int, results: dict, session=None) -> int:
        from core.database import DailyReport
        owns_session = session is None
        session = session or self.db.create_session()
        try:
            existing = session.query(DailyReport).filter(
                DailyReport.well_id == self.well_id,
                DailyReport.section_id == section_id,
                DailyReport.report_number == report_num,
            ).first()

            if not existing:
                existing = DailyReport(
                    well_id=self.well_id,
                    section_id=section_id,
                    report_number=report_num,
                    report_date=dr["report_date"],
                    status="Draft",
                    rig_day=report_num,
                    depth_0000=dr.get("depth_0000"),
                    depth_0600=dr.get("depth_0600"),
                    depth_2400=dr.get("depth_2400"),
                    summary=dr.get("summary", ""),
                )
                session.add(existing)
                session.flush()
                if owns_session:
                    session.commit()
                results["details"].append(f"⚠️ Fallback report #{report_num} - No fake defaults, depth preserved as NULL if missing")

            report_id = existing.id
            results["report_id"] = report_id
            return report_id

        except Exception as e:
            if owns_session:
                session.rollback()
                logger.error(f"Fallback report error: {e}")
                return None
            raise
        finally:
            if owns_session:
                session.close()


    def _save_mud_report(self, mr: dict, report_id: int, report_date, daily_report=None, session=None):
        if not mr:
            return
        mr_save = dict(mr)
        mr_save.update({
            "well_id": self.well_id,
            "report_id": report_id,
            "report_date": report_date,
        })
        float_fields = [
            'mw', 'pv', 'yp', 'funnel_vis', 'gel_10s',
            'gel_10m', 'fl', 'cake_thickness', 'ph',
            'temperature', 'solid_percent', 'oil_percent',
            'water_percent', 'chloride', 'volume_hole',
            'loss_surface', 'loss_downhole',
            'calcium', 'kcl', 'mbt', 'pf_mf',
            'total_hardness', 'flowline_temp',
        ]
        for field in float_fields:
            if field in mr_save and mr_save[field] not in (None, ""):
                # Preserve None, don't convert empty to 0
                converted = ValueNormalizer.to_float(mr_save[field])
                mr_save[field] = converted  # None if missing

        # Report-header mud volume block (pit readings) -> MudReport.
        # Values only; header labels are never stored.
        if daily_report:
            pit_block = {}
            pit_labels = {
                "suction1_mw": "suction1_mw", "suction1_vol": "suction1_vol",
                "suction2_mw": "suction2_mw", "suction2_vol": "suction2_vol",
                "degasser_mw": "degasser_mw", "degasser_vol": "degasser_vol",
                "desander_mw": "desander_mw", "desander_vol": "desander_vol",
                "desilter_vol": "desilter_vol",
                "middle_mw": "middle_mw", "middle_vol": "middle_vol",
                "reserve1_mw": "reserve1_mw", "reserve1_vol": "reserve1_vol",
                "reserve2_mw": "reserve2_mw", "reserve2_vol": "reserve2_vol",
                "reserve3_mw": "reserve3_mw", "reserve3_vol": "reserve3_vol",
                "sand_trap_mw": "sand_trap_mw", "sand_trap_vol": "sand_trap_vol",
            }
            for src_key, dst_key in pit_labels.items():
                val = daily_report.get(src_key)
                if val not in (None, ""):
                    pit_block[dst_key] = val
            if pit_block:
                mr_save["pit_volumes_json"] = json.dumps(pit_block, ensure_ascii=False)
            # Scalar mud-volume fields from the report header when the mud
            # table itself did not supply them.
            if mr_save.get("volume_hole") in (None, "") and daily_report.get("vol_in_hole") not in (None, ""):
                mr_save["volume_hole"] = ValueNormalizer.to_float(daily_report["vol_in_hole"])
            if mr_save.get("total_circulated") in (None, "") and daily_report.get("total_circ_vol") not in (None, ""):
                mr_save["total_circulated"] = ValueNormalizer.to_float(daily_report["total_circ_vol"])
            if mr_save.get("loss_downhole") in (None, "") and daily_report.get("mud_lost_downhole") not in (None, ""):
                mr_save["loss_downhole"] = ValueNormalizer.to_float(daily_report["mud_lost_downhole"])
            if mr_save.get("loss_surface") in (None, "") and daily_report.get("mud_lost_surface") not in (None, ""):
                mr_save["loss_surface"] = ValueNormalizer.to_float(daily_report["mud_lost_surface"])

        # Preserve original source tokens for non-numeric properties
        # (e.g. 'N.C' -> NULL + provenance) instead of dropping them.
        # Raw/source tokens live in the immutable import audit, not in the
        # user's mud summary or a numeric model column.
        for key in list(mr_save):
            if key.endswith("_source"):
                mr_save.pop(key)

        try:
            self.db.save_mud_report(mr_save, session=session)
        except Exception:
            # Persistence failures belong to the outer import transaction;
            # never convert them into a successful-looking empty phase.
            raise


    @staticmethod
    def _fraction_to_32nds(text) -> Optional[float]:
        """'18/32"' -> 18; '3/4"' -> 24; None for Open/text values."""
        if not text:
            return None
        s = str(text).strip().replace('"', '').replace('"', '')
        parts = s.split("/")
        try:
            if len(parts) == 1:
                return float(parts[0]) * 32.0
            return float(parts[0]) / float(parts[1]) * 32.0
        except (ValueError, ZeroDivisionError):
            return None


    def _save_drilling_params(self, dp: dict, report_id: int, report_date, param_table=None, scr_data=None, session=None):
        if not dp:
            return
        dp_save = dict(dp)
        dp_save.update({
            "well_id": self.well_id,
            "report_id": report_id,
            "report_date": report_date,
        })

        # Pack nozzle anchors (nozzle1_no/1_size, nozzle2_no/2_size) into
        # the nozzles_json column, preserving the original text tokens
        # (e.g. '18/32"', 'Open') so no size is invented.
        nozzles = []
        for idx in (1, 2):
            qty = ValueNormalizer.to_int(dp_save.get(f"nozzle{idx}_no"))
            size_text = dp_save.get(f"nozzle{idx}_size")
            if qty is None and not size_text:
                continue
            size_32 = self._fraction_to_32nds(size_text)
            nozzles.append({
                "row": idx,
                "size_32nd": size_32,
                "quantity": qty,
                "diameter_inch": round(size_32 / 32.0, 4) if size_32 is not None else None,
                "text": str(size_text).strip() if size_text is not None else "",
            })
        if nozzles:
            dp_save["nozzles_json"] = json.dumps(nozzles, ensure_ascii=False)

        # Merge the Drilling Parameters table rows (W.O.B / RPM / Torque /
        # Pump Pressure min-max) into the scalar record — generic keyword
        # matching on the parameter name, not company-specific.
        if param_table:
            param_keywords = {
                "w.o.b": "wob", "wt. on bit": "wob", "weight on bit": "wob",
                "bit load": "wob", "wob": "wob",
                "surf. rpm": "rpm", "rotary speed": "rpm", "rotary": "rpm",
                "rpm": "rpm",
                "torque": "torque",
                "pump pressure": "pump_pressure",
                "pump output": "pump_output",
            }
            for row in param_table:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name", "")).lower().strip()
                for keyword, field in param_keywords.items():
                    if keyword in name:
                        if row.get("min") not in (None, "") and f"{field}_min" not in dp_save:
                            dp_save[f"{field}_min"] = ValueNormalizer.to_float(row["min"])
                        if row.get("max") not in (None, "") and f"{field}_max" not in dp_save:
                            dp_save[f"{field}_max"] = ValueNormalizer.to_float(row["max"])
                        break

        # Bit run summary keys map onto the DrillingParameters bit columns;
        # canonical aliases (bit_cum_drilled, bit_hours_on_bottom, ...) are
        # normalized here — never dropped.
        bit_key_map = {
            "bit_cum_drilled": "cum_drilled",
            "bit_hours_on_bottom": "hours_on_bottom",
            "bit_cum_hrs_on_bottom": "cum_hours",
            "cum_bit_avg_rop": "avg_rop",
        }
        for src_key, dst_key in bit_key_map.items():
            if src_key in dp_save and dp_save[src_key] not in (None, ""):
                if dst_key not in dp_save or dp_save[dst_key] in (None, ""):
                    dp_save[dst_key] = dp_save[src_key]
            dp_save.pop(src_key, None)

        # SCR table rows (pump/SPM/FR/SPP) -> pumpN_spm / pumpN_spp columns.
        # Generic pump-number extraction from the pump name ('Pump No. #1').
        scr_rows = scr_data or []
        if isinstance(scr_rows, list):
            for row in scr_rows:
                if not isinstance(row, dict):
                    continue
                pump_name = str(row.get("pump", "")).strip()
                if not pump_name:
                    continue
                digits = [ch for ch in pump_name if ch.isdigit()]
                if not digits:
                    continue
                pump_no = int(digits[0])
                if pump_no not in (1, 2, 3):
                    continue
                for key, col in (("spm", f"pump{pump_no}_spm"),
                                 ("spp", f"pump{pump_no}_spp")):
                    val = row.get(key)
                    if val not in (None, "") and col not in dp_save:
                        dp_save[col] = ValueNormalizer.to_float(val)

        float_fields = [
            'bit_size', 'depth_in', 'depth_out', 'avg_rop',
            'wob_min', 'wob_max', 'rpm_min', 'rpm_max',
            'torque_min', 'torque_max',
            'pump_pressure_min', 'pump_pressure_max',
            'pump_output_min', 'pump_output_max',
            'tfa', 'hours_on_bottom',
        ]
        for field in float_fields:
            if field in dp_save and dp_save[field] not in (None, ""):
                dp_save[field] = ValueNormalizer.to_float(dp_save[field])

        try:
            self.db.save_drilling_parameters(dp_save, session=session)
        except Exception:
            raise


    def _save_time_logs(self, report_id: int, logs: list, session=None):
        """Save valid 24-hour rows in the caller's transaction.

        Invalid source rows are returned as review items rather than swallowed;
        a caller-owned session receives exceptions so the outer import can
        rollback every report-scoped object.
        """
        owns_session = session is None
        session = session or self.db.create_session()
        review_items = []
        saved = 0
        try:
            from core.database import TimeLog24H
            session.query(TimeLog24H).filter(TimeLog24H.report_id == report_id).delete()
            from core.domain_records import npt_record
            from core.database import Company, ServiceCompany
            companies = {row[0] for row in session.query(Company.name).all() if row[0]}
            companies.update(row[0] for row in session.query(ServiceCompany.company_name).all() if row[0])
            for index, log in enumerate(logs):
                log, npt_reviews = npt_record(log, companies)
                review_items.extend(npt_reviews)
                time_from = ValueNormalizer.to_time(log.get("time_from"))
                time_to = ValueNormalizer.to_time(log.get("time_to"))
                if time_from is None or time_to is None:
                    review_items.append({
                        "source_cell": log.get("source_cell") or log.get("source_cells"),
                        "source_row": log.get("source_row") or log.get("_source_row") or index,
                        "original_value": {"time_from": log.get("time_from"), "time_to": log.get("time_to")},
                        "normalized_value": {"time_from": time_from, "time_to": time_to},
                        "classification": "invalid_time_range",
                        "reason": "Both time anchors are required for persistence",
                        "status": "REVIEW_REQUIRED",
                    })
                    continue
                raw_duration = log.get("duration")
                try:
                    duration = None if raw_duration in (None, "") else float(raw_duration)
                except (TypeError, ValueError, OverflowError):
                    duration = None
                if raw_duration not in (None, "") and duration is None:
                    review_items.append({
                        "source_cell": log.get("source_cell") or log.get("source_cells"),
                        "source_row": log.get("source_row") or log.get("_source_row") or index,
                        "original_value": raw_duration,
                        "normalized_value": None,
                        "classification": "invalid_duration",
                        "reason": "Duration must be numeric when supplied",
                        "status": "REVIEW_REQUIRED",
                    })
                    continue
                if duration is not None and (duration < 0 or duration > 24):
                    review_items.append({
                        "source_cell": log.get("source_cell") or log.get("source_cells"),
                        "source_row": log.get("source_row") or log.get("_source_row") or index,
                        "original_value": raw_duration,
                        "normalized_value": duration,
                        "classification": "invalid_duration",
                        "reason": "Duration must be between 0 and 24 hours",
                        "status": "REVIEW_REQUIRED",
                    })
                    continue
                combo_resolution = log.get("_combo_resolution") or {}
                unresolved_combo = [
                    item for item in combo_resolution.values()
                    if isinstance(item, dict) and item.get("status") != "ACCEPT"
                ]
                if unresolved_combo:
                    for item in unresolved_combo:
                        review_items.append({
                            "source_cell": log.get("source_cell") or log.get("source_cells"),
                            "source_row": log.get("source_row") or log.get("_source_row") or index,
                            "field": item.get("field", ""),
                            "original_value": item.get("source_value"),
                            "normalized_value": None,
                            "classification": "combo_" + str(item.get("method", "unresolved")),
                            "reason": item.get("reason", "ComboBox value requires review"),
                            "status": "REVIEW_REQUIRED",
                        })
                    continue
                session.add(TimeLog24H(
                    report_id=report_id, time_from=time_from, time_to=time_to,
                    duration=duration, main_phase=str(log.get("main_phase", ""))[:100],
                    main_code=str(log.get("main_code", ""))[:100],
                    sub_code=str(log.get("sub_code", ""))[:100],
                    status=str(log.get("status", ""))[:50], is_npt=bool(log.get("is_npt", False)),
                    npt_category=str(log.get("npt_category", ""))[:100],
                    activity_description=wrap_text(str(log.get("activity_description", ""))),
                    contractor=str(log.get("contractor") or "")[:100],
                ))
                saved += 1
            session.flush()
            if owns_session:
                session.commit()
            return {"valid": saved, "review": _enrich_record_reviews(review_items, logs, "time_log")}
        except Exception:
            if owns_session:
                session.rollback()
            logger.exception("Time log save error")
            raise
        finally:
            if owns_session:
                session.close()


    def _save_morning_logs(self, report_id: int, logs: list, session=None):
        """Persist anchored morning rows and retain continuation rows as review."""
        owns_session = session is None
        session = session or self.db.create_session()
        review_items = []
        saved = 0
        try:
            from core.database import TimeLogMorning
            session.query(TimeLogMorning).filter(TimeLogMorning.report_id == report_id).delete()
            from core.domain_records import npt_record
            from core.database import Company, ServiceCompany
            companies = {row[0] for row in session.query(Company.name).all() if row[0]}
            companies.update(row[0] for row in session.query(ServiceCompany.company_name).all() if row[0])
            for index, log in enumerate(logs):
                log, npt_reviews = npt_record(log, companies)
                review_items.extend(npt_reviews)
                time_from = ValueNormalizer.to_time(log.get("time_from"))
                time_to = ValueNormalizer.to_time(log.get("time_to"))
                description = str(log.get("activity_description") or "").strip()
                if time_from is None or time_to is None:
                    classification = log.get("classification") or (
                        "continuation" if description else "invalid_time_range"
                    )
                    review_items.append({
                        "source_cell": log.get("source_cell") or log.get("source_cells"),
                        "source_row": log.get("source_row") or log.get("_source_row") or index,
                        "continuation_text": description if classification == "continuation" else "",
                        "original_value": {"time_from": log.get("time_from"), "time_to": log.get("time_to"), "description": description},
                        "normalized_value": {"time_from": time_from, "time_to": time_to},
                        "classification": classification,
                        "reason": log.get("review_reason") or (
                            "Continuation row has no independent time anchor; no time was invented"
                            if classification == "continuation" else
                            "Both time anchors are required for persistence"
                        ),
                        "status": "REVIEW_REQUIRED",
                    })
                    continue
                raw_duration = log.get("duration")
                try:
                    duration = None if raw_duration in (None, "") else float(raw_duration)
                except (TypeError, ValueError, OverflowError):
                    duration = None
                if raw_duration not in (None, "") and duration is None:
                    review_items.append({
                        "source_cell": log.get("source_cell") or log.get("source_cells"),
                        "source_row": log.get("source_row") or log.get("_source_row") or index,
                        "original_value": raw_duration,
                        "normalized_value": None,
                        "classification": "invalid_duration",
                        "reason": "Duration must be numeric when supplied",
                        "status": "REVIEW_REQUIRED",
                    })
                    continue
                if duration is not None and (duration < 0 or duration > 24):
                    review_items.append({
                        "source_cell": log.get("source_cell") or log.get("source_cells"),
                        "source_row": log.get("source_row") or log.get("_source_row") or index,
                        "original_value": raw_duration,
                        "normalized_value": duration,
                        "classification": "invalid_duration",
                        "reason": "Duration must be between 0 and 24 hours",
                        "status": "REVIEW_REQUIRED",
                    })
                    continue
                combo_resolution = log.get("_combo_resolution") or {}
                unresolved_combo = [
                    item for item in combo_resolution.values()
                    if isinstance(item, dict) and item.get("status") != "ACCEPT"
                ]
                if unresolved_combo:
                    for item in unresolved_combo:
                        review_items.append({
                            "source_cell": log.get("source_cell") or log.get("source_cells"),
                            "source_row": log.get("source_row") or log.get("_source_row") or index,
                            "field": item.get("field", ""),
                            "original_value": item.get("source_value"),
                            "normalized_value": None,
                            "classification": "combo_" + str(item.get("method", "unresolved")),
                            "reason": item.get("reason", "ComboBox value requires review"),
                            "status": "REVIEW_REQUIRED",
                        })
                    continue
                session.add(TimeLogMorning(
                    report_id=report_id, time_from=time_from, time_to=time_to,
                    duration=duration, main_phase=str(log.get("main_phase", ""))[:100],
                    main_code=str(log.get("main_code", ""))[:100],
                    sub_code=str(log.get("sub_code", ""))[:100],
                    status=str(log.get("status", ""))[:50], is_npt=bool(log.get("is_npt", False)),
                    npt_category=str(log.get("npt_category", ""))[:100],
                    activity_description=wrap_text(description),
                    contractor=str(log.get("contractor") or "")[:100],
                ))
                saved += 1
            session.flush()
            if owns_session:
                session.commit()
            return {"valid": saved, "review": _enrich_record_reviews(review_items, logs, "time_log_morning")}
        except Exception:
            if owns_session:
                session.rollback()
            logger.exception("Morning log save error")
            raise
        finally:
            if owns_session:
                session.close()


    def _normalize_date(self, value) -> dt_date:
        result = ValueNormalizer.to_date(value)
        return result


    def _safe_text(self, value, default="") -> str:
        result = ValueNormalizer.to_str(value)
        if not result or result.endswith(":"):
            return default
        return result


    @staticmethod
    def _auto_match_template(sheet_names: list) -> dict:
        """Find a company template whose sheet sections fit this workbook.

        Generic rule: a template matches when every template sheet section
        name (the part after 'sheet_<n>_') exists among the workbook's
        sheet titles. Returns None when no template matches, so imports
        fall back to heuristic detection.
        """
        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "templates",
        )
        if not os.path.isdir(templates_dir):
            return None
        available = set(sheet_names)
        best = None
        best_count = -1
        for filename in sorted(os.listdir(templates_dir)):
            if not filename.endswith(".json") or filename.startswith("_"):
                continue
            path = os.path.join(templates_dir, filename)
            try:
                with open(path, encoding="utf-8") as fh:
                    tmpl = json.load(fh)
            except (OSError, ValueError):
                continue
            if not isinstance(tmpl, dict):
                continue
            sheet_keys = [k for k in tmpl if k.startswith("sheet_")]
            if not sheet_keys:
                continue
            ok = True
            for key in sheet_keys:
                parts = key.split("_", 2)
                name = parts[2] if len(parts) > 2 else parts[1]
                # Template keys use underscores where workbook sheets use
                # spaces (e.g. sheet_2_DDR_Data <-> "DDR Data").
                normalized = name.replace("_", " ").lower()
                if normalized not in {s.lower() for s in available}:
                    ok = False
                    break
            if ok and len(sheet_keys) > best_count:
                best_count = len(sheet_keys)
                best = tmpl
        return best

    def extract_file(self, path, template=None):
        """Actual desktop Excel pipeline without presentation or persistence."""
        from openpyxl import load_workbook
        from core.excel_intelligence import ExcelIntelligence
        workbook = load_workbook(path, data_only=False, read_only=False)
        cached_workbook = load_workbook(path, data_only=True, read_only=False)
        try:
            template = template if template is not None else self._auto_match_template([ws.title for ws in workbook.worksheets])
            excel_engine = ExcelIntelligence(
                workbook,
                template or {},
                source_file=path,
                cached_workbook=cached_workbook,
            )
            rep = (
                excel_engine.extract()
                if template
                else excel_engine.extract_generic()
            )
            extracted = dict(rep.canonical_json)
            review_rows = [
                {
                    "file": Path(path).name,
                    "sheet": r.sheet,
                    "row": r.row,
                    "column": r.col,
                    "source_location": {
                        "file": Path(path).name,
                        "sheet": r.sheet,
                        "row": r.row,
                        "column": r.col,
                        "cell": r.cell,
                    },
                    "detected_table": "scalar",
                    "source_cell": r.cell,
                    "entity": r.canonical_field.split(".", 1)[0] if "." in r.canonical_field else "",
                    "mapping_method": r.source or "excel-template",
                    "classification": (
                        "mapping-conflict" if r.status == "CONFLICT"
                        else "invalid-source-token" if r.canonical_field in rep.source_tokens
                        else "missing-source-value" if r.status == "UNRESOLVED"
                        else "confidence-review"
                    ),
                    "original_value": rep.source_tokens.get(r.canonical_field, {}).get("original_value", r.value),
                    "normalized_value": rep.source_tokens.get(r.canonical_field, {}).get("normalized_value", r.value),
                    "value": rep.source_tokens.get(r.canonical_field, {}).get("normalized_value", r.value),
                    "unit": r.canonical_unit,
                    "target_field": r.canonical_field,
                    "canonical_field": r.canonical_field,
                    "confidence": r.confidence,
                    "certainty": r.certainty,
                    "status": r.status,
                    "expected_type": rep.source_tokens.get(r.canonical_field, {}).get("expected_type", r.data_type),
                    "decision": "REVIEW" if r.status != "OK" or r.canonical_field in rep.source_tokens else "ACCEPT",
                    "reason": r.reason,
                }
                for r in rep.field_results
                if r.status != "OK" or r.certainty == "LOW" or rep.source_tokens.get(r.canonical_field, {}).get("review", False)
            ]
            extracted["metadata"] = {
                "template": (template or {}).get("name", ""),
                "template_version": rep.template_version,
                "review_matrix": review_rows,
                "source_tokens": rep.source_tokens,
                "field_provenance": rep.field_provenance,
                "duplicate_mappings": rep.duplicate_mappings,
                "raw_ir": rep.raw_document.to_dict(include_cells=True) if rep.raw_document is not None else None,
            }
        finally:
            workbook.close()
            cached_workbook.close()
        return rep, extracted
