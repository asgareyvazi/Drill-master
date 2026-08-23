# dialogs/excel_import_dialog.py
"""
Excel Import Dialog v2.0 - Smart + Template + Batch
====================================================
- Smart auto-detect with review
- Anchor-based template import
- Batch import with progress and logging
- Targeted refresh after import
- Full code resolution for time logs
"""

import os
import re
import json
import logging
from datetime import date as dt_date, time as dt_time, datetime as dt_datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QFileDialog, QComboBox, QLineEdit, QMessageBox,
    QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QWidget, QSplitter, QProgressBar, QApplication,
    QInputDialog, QRadioButton, QDialogButtonBox,
)
from PySide6.QtCore import Signal, Qt, QTimer, QDir
from PySide6.QtGui import QColor

from core.text_utils import wrap_text
from core.import_quality import ImportValidator, find_duplicates
from core.ai_import_mapper import AIImportMapper, model_catalog, get_selected_model, set_selected_model
from dialogs.smart_template_dialog import (
    SmartTemplateDialog, ValueNormalizer, FIELD_LABELS,
)

logger = logging.getLogger(__name__)

ALL_EXPECTED_FIELDS = list(FIELD_LABELS.keys())


class ExcelImportDialog(QDialog):
    """
    Main entry point for Excel Import:
    - Smart Import (auto-detect + builder)
    - Batch Import (multiple files)
    - Template Import (saved templates)
    """

    import_completed = Signal(list)

    def __init__(self, db_manager, well_id: int, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.well_id = well_id
        self.setWindowTitle("📊 Excel Import System v2.0")
        self.setMinimumSize(550, 450)
        self.setModal(True)
        self._init_ui()

    # ================================================================
    # UI
    # ================================================================
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Header
        header = QLabel("📊 Excel Import System v2.0")
        header.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #2c3e50; "
            "padding: 10px; background: #ecf0f1; border-radius: 5px;"
        )
        layout.addWidget(header)

        # ===== Unified Import =====
        import_group = QGroupBox("🚀 Universal Import")
        il = QVBoxLayout(import_group)
        il.addWidget(QLabel(
            "Select one or more Excel/PDF reports. The importer normalizes the file, "
            "detects tables, uses the workbook catalog and asks the selected local AI "
            "only for ambiguous mappings."
        ))
        ai_row = QHBoxLayout()
        ai_row.addWidget(QLabel("AI model:"))
        self.ai_model_combo = QComboBox()
        installed = set(AIImportMapper().installed_models())
        entries = list(model_catalog())
        known = {entry.get("model", entry.get("name", "")) for entry in entries}
        entries.extend({"model": model, "label": model, "description": "Installed Ollama model"} for model in installed if model not in known)
        for entry in entries:
            model = entry.get("model", entry.get("name", ""))
            mark = "✓" if model in installed else "—"
            self.ai_model_combo.addItem(f"{mark} {entry.get('label', model)}", model)
        selected = os.getenv("DRILLMASTER_AI_MODEL", "") or get_selected_model() or (sorted(installed)[0] if installed else "")
        selected_index = self.ai_model_combo.findData(selected)
        if selected_index >= 0:
            self.ai_model_combo.setCurrentIndex(selected_index)
            set_selected_model(selected)
            os.environ["DRILLMASTER_AI_MODEL"] = selected
        self.ai_model_combo.currentIndexChanged.connect(self._select_ai_model)
        ai_row.addWidget(self.ai_model_combo, 1)
        il.addLayout(ai_row)
        import_btn = QPushButton("📥 Import Report(s)")
        import_btn.setStyleSheet(
            "background: #27ae60; color: white; padding: 14px; "
            "font-weight: bold; border-radius: 5px; font-size: 14px;"
        )
        import_btn.clicked.connect(self._unified_import)
        il.addWidget(import_btn)
        self.import_status = QLabel("No file selected")
        il.addWidget(self.import_status)
        layout.addWidget(import_group)

        # Cancel
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

    # ================================================================
    # Template Loading
    # ================================================================
    def _select_ai_model(self, index):
        model = self.ai_model_combo.itemData(index) if hasattr(self, "ai_model_combo") else None
        if model:
            os.environ["DRILLMASTER_AI_MODEL"] = model
            os.environ["DRILLMASTER_AI_IMPORT"] = "1"
            set_selected_model(model)

    def _unified_import(self):
        """The only import entry point: single file or batch, Excel or PDF."""
        files, _ = QFileDialog.getOpenFileNames(
            self, "Import Report(s)", "", "Reports (*.xlsx *.xls *.xlsm *.csv *.pdf)"
        )
        if not files:
            return
        results = []
        for number, source in enumerate(files, 1):
            self.import_status.setText(f"Processing {number}/{len(files)}: {os.path.basename(source)}")
            QApplication.processEvents()
            try:
                path = source
                if source.lower().endswith(".pdf"):
                    from pathlib import Path
                    from core.document_import import pdf_to_xlsx
                    clean = Path(os.path.join(QDir.tempPath(), Path(source).stem + "_pdf_import.xlsx"))
                    pdf_to_xlsx(source, clean)
                    path = str(clean)
                elif source.lower().endswith(".csv"):
                    from pathlib import Path
                    from core.document_import import csv_to_xlsx
                    clean = Path(os.path.join(QDir.tempPath(), Path(source).stem + "_csv_import.xlsx"))
                    csv_to_xlsx(source, clean)
                    path = str(clean)
                elif source.lower().endswith(".xls"):
                    raise ValueError("Legacy .xls requires conversion to .xlsx before import")
                dialog = SmartTemplateDialog(self.db, self.well_id, None, preload_file=path)
                QApplication.processEvents()
                dialog._smart_auto_detect()
                dialog._remember_mappings()
                extracted = dialog._build_final_data_from_assignments()
                if not any(extracted.get(key) for key in ("well_info", "daily_report", "mud_report", "drilling_params", "time_logs_24h")):
                    raise ValueError("No report data was detected")
                results.append(self._do_import(extracted, refresh_ui=False))
                dialog.deleteLater()
            except Exception as exc:
                logger.error("Universal import failed for %s: %s", source, exc, exc_info=True)
                results.append({"failed": 1, "imported": 0, "details": [f"❌ {os.path.basename(source)}: {exc}"]})
        self.import_completed.emit(results)
        self.accept()

    def _resolve_import_well(self, well_info):
        """Resolve the workbook well instead of forcing every file into the selected well."""
        from core.database import Well, Project
        name = self._safe_text((well_info or {}).get("name"), "")
        code = self._safe_text((well_info or {}).get("code"), "")
        if not name and not code:
            return self.well_id
        session = self.db.create_session()
        try:
            query = session.query(Well)
            existing = query.filter(Well.code == code).first() if code else None
            if not existing:
                existing = query.filter(Well.name == name).first() if name else None
            if existing:
                self.well_id = existing.id
                return existing.id
            fallback = session.get(Well, self.well_id) if self.well_id else None
            project_id = fallback.project_id if fallback else session.query(Project.id).order_by(Project.id).first()
            project_id = project_id[0] if isinstance(project_id, tuple) else project_id
            if not project_id:
                raise ValueError("Cannot create imported well: no project exists")
            values = {k: v for k, v in (well_info or {}).items() if hasattr(Well, k) and k != "id"}
            values.update({"project_id": project_id, "name": name or code})
            if code:
                values["code"] = code
            well = Well(**values)
            session.add(well)
            session.commit()
            self.well_id = well.id
            return well.id
        finally:
            session.close()

    def _do_import(
        self, extracted: dict, refresh_ui: bool = True
    ) -> dict:
        """Core import logic - saves extracted data to database"""
        results = {
            "imported": 0,
            "failed": 0,
            "details": [],
            "well_id": self.well_id,
            "report_id": None,
            "section_id": None,
            "import_report": None,
        }
        session = None
        report_id = None
        created_new_report = False

        try:
            from core.database import Section, DailyReport

            # Validate before touching the database.  A bad optional row is
            # reported and skipped; a bad base report stops this import.
            report_data = extracted.get("daily_report", {})
            quality = ImportValidator.validate_rows(
                [report_data], "daily_report", "Daily Report"
            )
            time_logs = extracted.get("time_logs_24h", []) or []
            log_quality = ImportValidator.validate_rows(
                time_logs, "time_log", "Time Logs 24H"
            )
            # Rows without a time range are separators/continuation rows, not
            # real activities. Report them, but never send them to the DB.
            valid_time_logs = [
                row for row in time_logs
                if isinstance(row, dict) and row.get("time_from") not in (None, "") and row.get("time_to") not in (None, "")
            ]
            invalid_time_rows = len(time_logs) - len(valid_time_logs)
            extracted["time_logs_24h"] = valid_time_logs
            duplicate_indexes = set(find_duplicates(time_logs, "time_log"))
            for index in sorted(duplicate_indexes, reverse=True):
                del time_logs[index]
                log_quality.skipped += 1
            quality.total += log_quality.total
            quality.failed += log_quality.failed
            quality.issues.extend(log_quality.issues)
            results["import_report"] = quality.as_dict()
            results["import_report"]["review"].extend((extracted.get("metadata") or {}).get("review_matrix", []))
            if quality.errors and not report_data.get("report_date"):
                results["failed"] += 1
                results["details"].append("❌ Import stopped: invalid Daily Report")
                return results
            if duplicate_indexes:
                results["details"].append(
                    f"⚠️ Skipped {len(duplicate_indexes)} duplicate time-log rows"
                )

            # ===== 1. Well Info =====
            wi = extracted.get("well_info", {})
            if not self.well_id or wi.get("name") or wi.get("code"):
                self._resolve_import_well(wi)
                results["well_id"] = self.well_id
            if wi:
                wi_save = dict(wi)
                wi_save["id"] = self.well_id
                if self.db.save_well(wi_save):
                    results["details"].append(
                        f"✅ Well Info: {len(wi)} fields"
                    )

            # ===== 2. Section =====
            section_name = self._safe_text(
                wi.get("section_name"), "Imported Section"
            )
            section_id = None

            session = self.db.create_session()
            try:
                existing = session.query(Section).filter(
                    Section.well_id == self.well_id,
                    Section.name == section_name,
                ).first()

                if existing:
                    section_id = existing.id
                else:
                    # Never attach an import to an arbitrary first section.
                    # If identity cannot be established, create a clearly
                    # named section and report it for review.
                    dr_data = extracted.get("daily_report", {})
                    depth_from = ValueNormalizer.to_float(dr_data.get("depth_0000"))
                    depth_to = ValueNormalizer.to_float(dr_data.get("depth_2400"))
                    new_section = Section(
                        well_id=self.well_id,
                        name=section_name,
                        code=self._safe_text(wi.get("section_code"), ""),
                        depth_from=depth_from if depth_from is not None else 0.0,
                        depth_to=depth_to if depth_to is not None else 0.0,
                    )
                    session.add(new_section)
                    session.flush()
                    section_id = new_section.id
                    results["details"].append(
                        f"✅ Section '{section_name}' created (not matched to an existing section)"
                    )

                session.commit()
            finally:
                session.close()
                session = None

            if not section_id:
                results["failed"] += 1
                results["details"].append("❌ No valid section")
                return results

            results["section_id"] = section_id

            # ===== 3. Daily Report =====
            dr = dict(extracted.get("daily_report", {}))
            dr["well_id"] = self.well_id
            dr["section_id"] = section_id
            raw_report_date = dr.get("report_date") or wi.get("report_date")
            if raw_report_date in (None, ""):
                results["failed"] += 1
                results["details"].append("❌ Import stopped: report date is missing")
                return results
            dr["report_date"] = self._normalize_date(raw_report_date)
            dr.setdefault("status", "Draft")

            # report_number
            supplied_report_number = ValueNormalizer.to_int(dr.get("report_number"))
            report_num = self._ensure_report_number(dr, section_id)
            dr["report_number"] = report_num
            dr["report_number_source"] = "imported" if supplied_report_number else "generated"

            # rig_day
            if not dr.get("rig_day"):
                dr["rig_day"] = report_num
            else:
                dr["rig_day"] = (
                    ValueNormalizer.to_int(dr["rig_day"])
                    or report_num
                )

            # depth fields
            for depth_field in [
                "depth_0000", "depth_0600", "depth_2400"
            ]:
                parsed_depth = ValueNormalizer.to_float(dr.get(depth_field))
                # Missing depth is unknown, not zero. Preserve NULL so
                # monitoring and reports do not show a fabricated depth.
                dr[depth_field] = parsed_depth

            # Track whether this import owns the report. If a newly-created
            # report later fails in a child table, the import can be rolled
            # back without touching an existing user's report.
            created_new_report = not bool(dr.get("id"))
            saved = self.db.save_daily_report(dr)
            report_id = None

            if saved and saved.get("id"):
                report_id = saved["id"]
                results["report_id"] = report_id
                results["imported"] += 1
                results["details"].append(
                    f"✅ Report #{saved.get('report_number', '?')}"
                )
            else:
                report_id = self._create_fallback_report(
                    dr, section_id, report_num, results
                )

            if not report_id:
                results["details"].append(
                    "❌ Could not create Daily Report"
                )
                results["failed"] += 1
                return results

            results["report_id"] = report_id

            # ===== 4. Mud Report =====
            mud_data = extracted.get("mud_report", {}) or {}
            # Embedded DDRs often store chemical inventory in the same Mud
            # sheet. Feed it to MudReportTab as chemicals, not only Bulk.
            if not mud_data.get("chemicals_json") and extracted.get("bulk_materials"):
                import json
                mud_data["chemicals_json"] = json.dumps([
                    {"product": item.get("material_name", ""), "product_type": "", "received": item.get("received", 0), "used": item.get("used", 0), "stock": item.get("current_stock", item.get("initial_stock", 0)), "unit": item.get("unit", "")}
                    for item in extracted.get("bulk_materials", []) if item.get("material_name")
                ], ensure_ascii=False)
            self._save_mud_report(
                mud_data,
                report_id, dr["report_date"],
            )

            # ===== 5. Drilling Params =====
            self._save_drilling_params(
                extracted.get("drilling_params", {}),
                report_id, dr["report_date"],
            )

            # ===== 6. Time Logs =====
            if extracted.get("time_logs_24h"):
                self._save_time_logs(
                    report_id,
                    extracted["time_logs_24h"],
                )
                results["details"].append(
                    f"✅ Time logs: "
                    f"{len(extracted['time_logs_24h'])} entries"
                )

            if extracted.get("time_logs_morning"):
                self._save_morning_logs(
                    report_id,
                    extracted["time_logs_morning"],
                )
                results["details"].append(
                    f"✅ Morning logs: "
                    f"{len(extracted['time_logs_morning'])} entries"
                )

            # ===== 7. Multi-Tab Import (Surveys, POB, Casing/Cement, Bit/BHA, Logistics, Safety, Cost) =====
            if hasattr(self.db, 'save_imported_multi_tab_data'):
                multi_res = self.db.save_imported_multi_tab_data(
                    self.well_id, report_id, extracted
                )
                for k, count in multi_res.items():
                    if k == "failed":
                        results["failed"] += int(count or 0)
                    elif count > 0:
                        results["details"].append(f"✅ {k}: {count} records imported")

            if results["failed"] and created_new_report and report_id:
                self.db.delete_daily_report(report_id)
                results["details"].append(
                    "↩️ Import rolled back: no partial report was kept"
                )
                results["imported"] = 0
                return results
            return results

        except Exception as e:
            results["failed"] = 1
            results["details"].append(f"❌ Error: {str(e)}")
            logger.error(f"Import error: {e}", exc_info=True)
            if session:
                try:
                    session.rollback()
                except Exception:
                    pass
            if created_new_report and report_id:
                try:
                    self.db.delete_daily_report(report_id)
                    results["details"].append(
                        "↩️ Import rolled back after failure"
                    )
                except Exception:
                    logger.error("Import rollback cleanup failed", exc_info=True)
            return results
        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass

    # ================================================================
    # Helper Methods
    # ================================================================
    def _ensure_report_number(
        self, dr: dict, section_id: int
    ) -> int:
        """Ensure valid report number"""
        if dr.get("report_number"):
            num = ValueNormalizer.to_int(dr["report_number"])
            if num and num > 0:
                return num

        from core.database import DailyReport
        session = self.db.create_session()
        try:
            last = session.query(DailyReport).filter(
                DailyReport.section_id == section_id,
            ).order_by(
                DailyReport.report_number.desc()
            ).first()
            return (last.report_number + 1) if last else 1
        finally:
            session.close()

    def _create_fallback_report(
        self,
        dr: dict,
        section_id: int,
        report_num: int,
        results: dict,
    ) -> int:
        """Create fallback report if normal save fails"""
        from core.database import DailyReport

        session = self.db.create_session()
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
                    depth_0000=dr.get("depth_0000", 0.0),
                    depth_0600=dr.get("depth_0600", 0.0),
                    depth_2400=dr.get("depth_2400", 0.0),
                    summary=dr.get("summary", ""),
                )
                session.add(existing)
                session.commit()
                results["details"].append(
                    f"⚠️ Fallback report #{report_num}"
                )

            report_id = existing.id
            results["report_id"] = report_id
            return report_id

        except Exception as e:
            logger.error(f"Fallback report error: {e}")
            return None
        finally:
            session.close()

    def _save_mud_report(
        self,
        mr: dict,
        report_id: int,
        report_date,
    ):
        """Save mud report data"""
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
        ]
        for field in float_fields:
            if field in mr_save:
                mr_save[field] = ValueNormalizer.to_float(
                    mr_save[field]
                )

        try:
            self.db.save_mud_report(mr_save)
        except Exception as e:
            logger.error(f"Mud report save error: {e}")

    def _save_drilling_params(
        self,
        dp: dict,
        report_id: int,
        report_date,
    ):
        """Save drilling parameters"""
        if not dp:
            return

        dp_save = dict(dp)
        dp_save.update({
            "well_id": self.well_id,
            "report_id": report_id,
            "report_date": report_date,
        })

        float_fields = [
            'bit_size', 'depth_in', 'depth_out', 'avg_rop',
            'wob_max', 'rpm_max', 'torque_max',
            'pump_pressure_max', 'tfa', 'hours_on_bottom',
        ]
        for field in float_fields:
            if field in dp_save:
                dp_save[field] = ValueNormalizer.to_float(
                    dp_save[field]
                )

        try:
            self.db.save_drilling_parameters(dp_save)
        except Exception as e:
            logger.error(f"Drilling params save error: {e}")

    def _save_time_logs(self, report_id: int, logs: list):
        """Save 24h time logs"""
        session = self.db.create_session()
        try:
            from core.database import TimeLog24H

            session.query(TimeLog24H).filter(
                TimeLog24H.report_id == report_id,
            ).delete()

            saved = 0
            for log in logs:
                time_from = ValueNormalizer.to_time(
                    log.get("time_from")
                )
                if time_from is None:
                    continue

                tlog = TimeLog24H(
                    report_id=report_id,
                    time_from=time_from,
                    time_to=(
                        ValueNormalizer.to_time(log.get("time_to"))
                        or dt_time(0, 0)
                    ),
                    duration=float(log.get("duration", 0) or 0),
                    main_phase=str(
                        log.get("main_phase", "")
                    )[:100],
                    main_code=str(
                        log.get("main_code", "")
                    )[:100],
                    sub_code=str(
                        log.get("sub_code", "")
                    )[:100],
                    status=str(log.get("status", ""))[:50],
                    is_npt=bool(log.get("is_npt", False)),
                    npt_category=str(
                        log.get("npt_category", "")
                    )[:100],
                    activity_description=wrap_text(
                        str(log.get("activity_description", ""))
                    ),
                    contractor=str(
                        log.get("contractor", "")
                    )[:100],
                )
                session.add(tlog)
                saved += 1

            session.commit()
            logger.info(f"Saved {saved} time logs")

        except Exception as e:
            session.rollback()
            logger.error(f"Time log save error: {e}")
        finally:
            session.close()

    def _save_morning_logs(self, report_id: int, logs: list):
        """Save morning time logs"""
        session = self.db.create_session()
        try:
            from core.database import TimeLogMorning

            session.query(TimeLogMorning).filter(
                TimeLogMorning.report_id == report_id,
            ).delete()

            saved = 0
            for log in logs:
                time_from = ValueNormalizer.to_time(
                    log.get("time_from")
                )
                if time_from is None:
                    continue

                tlog = TimeLogMorning(
                    report_id=report_id,
                    time_from=time_from,
                    time_to=(
                        ValueNormalizer.to_time(log.get("time_to"))
                        or dt_time(0, 0)
                    ),
                    duration=float(log.get("duration", 0) or 0),
                    main_phase=str(
                        log.get("main_phase", "")
                    )[:100],
                    main_code=str(
                        log.get("main_code", "")
                    )[:100],
                    sub_code=str(
                        log.get("sub_code", "")
                    )[:100],
                    status=str(log.get("status", ""))[:50],
                    is_npt=bool(log.get("is_npt", False)),
                    npt_category=str(
                        log.get("npt_category", "")
                    )[:100],
                    activity_description=wrap_text(
                        str(log.get("activity_description", ""))
                    ),
                    contractor=str(
                        log.get("contractor", "")
                    )[:100],
                )
                session.add(tlog)
                saved += 1

            session.commit()
            logger.info(f"Saved {saved} morning logs")

        except Exception as e:
            session.rollback()
            logger.error(f"Morning log save error: {e}")
        finally:
            session.close()

    # ================================================================
    # Value Helpers
    # ================================================================
    def _normalize_date(self, value) -> dt_date:
        """Convert value to Python date"""
        result = ValueNormalizer.to_date(value)
        return result

    def _safe_text(self, value, default="") -> str:
        result = ValueNormalizer.to_str(value)
        if not result or result.endswith(":"):
            return default
        return result