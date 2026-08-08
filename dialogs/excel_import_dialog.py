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
from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import QColor

from core.text_utils import wrap_text
from core.import_quality import ImportValidator, find_duplicates
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

        # ===== Smart Import =====
        smart_group = QGroupBox("🚀 Smart Import & Builder")
        sl = QVBoxLayout(smart_group)
        sl.addWidget(QLabel(
            "Open Excel, auto-detect fields with AI engine, "
            "review and fix in builder."
        ))

        smart_btn = QPushButton("📂 Open Excel & Auto-Detect")
        smart_btn.setStyleSheet(
            "background: #27ae60; color: white; padding: 12px; "
            "font-weight: bold; border-radius: 5px; font-size: 13px;"
        )
        smart_btn.clicked.connect(self._smart_import)
        sl.addWidget(smart_btn)

        profile_btn = QPushButton("🏢 OEOC Profile Import (fast)")
        profile_btn.setToolTip("Use the strict DDR Remark / DDR Data profile, then run the same validation and save pipeline")
        profile_btn.clicked.connect(self._profile_import)
        sl.addWidget(profile_btn)
        layout.addWidget(smart_group)

        # ===== Batch Import =====
        batch_group = QGroupBox("📦 Batch Import (Multiple Files)")
        bl = QVBoxLayout(batch_group)
        bl.addWidget(QLabel(
            "Process multiple Excel files at once using "
            "Smart Detection or a saved Template."
        ))

        batch_btn = QPushButton("📦 Batch Import")
        batch_btn.setStyleSheet(
            "background: #e67e22; color: white; padding: 10px; "
            "font-weight: bold; border-radius: 5px; font-size: 12px;"
        )
        batch_btn.clicked.connect(self._batch_import)
        bl.addWidget(batch_btn)
        layout.addWidget(batch_group)

        # ===== Template Import =====
        tmpl_group = QGroupBox("📥 Quick Import with Saved Template")
        tl = QVBoxLayout(tmpl_group)

        th = QHBoxLayout()
        th.addWidget(QLabel("Template:"))
        self.template_combo = QComboBox()
        self._load_templates()
        th.addWidget(self.template_combo, 1)
        tl.addLayout(th)

        file_layout = QHBoxLayout()
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("Select Excel file...")
        browse_btn = QPushButton("📂")
        browse_btn.setFixedWidth(40)
        browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(self.file_input, 1)
        file_layout.addWidget(browse_btn)
        tl.addLayout(file_layout)

        tmpl_btn = QPushButton("⚡ Quick Import with Template")
        tmpl_btn.setStyleSheet(
            "background: #9b59b6; color: white; padding: 10px; "
            "font-weight: bold; border-radius: 5px; font-size: 12px;"
        )
        tmpl_btn.clicked.connect(self._import_with_template)
        tl.addWidget(tmpl_btn)
        layout.addWidget(tmpl_group)

        # Cancel
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

    # ================================================================
    # Template Loading
    # ================================================================
    def _load_templates(self):
        self.template_combo.clear()
        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "templates",
        )

        if not os.path.exists(templates_dir):
            os.makedirs(templates_dir, exist_ok=True)
            self.template_combo.addItem(
                "No templates yet — create one first"
            )
            return

        found = False
        for fname in sorted(os.listdir(templates_dir)):
            if not fname.endswith(".json"):
                continue
            if fname.startswith("_"):
                continue

            path = os.path.join(templates_dir, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                field_count = 0
                assigns = data.get("assignments", {})
                if isinstance(assigns, dict):
                    field_count = len(assigns)

                name = data.get("name", fname)
                version = data.get("version", "1.0")

                self.template_combo.addItem(
                    f"{name} ({field_count} fields, v{version})",
                    path,
                )
                found = True

            except Exception as e:
                logger.error(f"Error loading template {path}: {e}")

        if not found:
            self.template_combo.addItem(
                "No templates yet — create one first"
            )

    def _browse_file(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, "Select Excel", "",
            "Excel Files (*.xlsx *.xls)",
        )
        if fp:
            self.file_input.setText(fp)

    # ================================================================
    # Smart Import
    # ================================================================
    def _smart_import(self):
        """Open SmartTemplateDialog for interactive import"""
        dialog = SmartTemplateDialog(self.db, self.well_id, self)
        dialog.import_completed.connect(self._on_smart_completed)
        dialog.exec()

    def _on_smart_completed(self, extracted: dict):
        """After smart import, save to database"""
        results = self._do_import(extracted, refresh_ui=False)
        self.import_completed.emit([results])
        self.accept()

    def _profile_import(self):
        """Run the strict profile engine through the common import pipeline.

        Previously ProfileImportEngine was dead code: the UI only opened
        SmartTemplateDialog. Keeping its extraction but sharing _do_import
        guarantees identical validation, duplicate handling and refresh.
        """
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select OEOC DDR Excel", "", "Excel Files (*.xlsx *.xls)"
        )
        if not filepath:
            return
        try:
            from core.profile_import_engine import ProfileImportEngine
            extracted = ProfileImportEngine(self.db).analyze_and_extract(filepath)
            results = self._do_import(extracted, refresh_ui=False)
            self.import_completed.emit([results])
            self.accept()
        except ImportError as exc:
            QMessageBox.warning(self, "Missing Excel dependency", f"Install openpyxl first:\n{exc}")
        except ValueError as exc:
            # A custom workbook is not a profile failure; guide the user to
            # Smart Import instead of emitting an alarming traceback.
            logger.info("Profile not applicable: %s", exc)
            QMessageBox.information(self, "Use Smart Import", str(exc))
        except Exception as exc:
            logger.error("Profile import failed: %s", exc, exc_info=True)
            QMessageBox.critical(self, "Profile Import Failed", str(exc))

    # ================================================================
    # Template Import
    # ================================================================
    def _import_with_template(self):
        template_path = self.template_combo.currentData()
        filepath = self.file_input.text()

        if not template_path or not os.path.exists(str(template_path)):
            QMessageBox.warning(
                self, "No Template", "Select a valid template."
            )
            return

        if not filepath or not os.path.exists(filepath):
            QMessageBox.warning(
                self, "No File", "Select a valid Excel file."
            )
            return

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template = json.load(f)

            # Open in builder for review
            dialog = SmartTemplateDialog(
                self.db, self.well_id, self,
                preload_file=filepath,
            )
            QApplication.processEvents()

            # Apply template after file is loaded
            dialog._apply_template(template)
            dialog.import_completed.connect(self._on_smart_completed)
            dialog.exec()

        except Exception as e:
            logger.error(f"Template import error: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    # ================================================================
    # Batch Import
    # ================================================================
    def _batch_import(self):
        """Batch import multiple files"""
        filepaths, _ = QFileDialog.getOpenFileNames(
            self, "Select Excel Files", "",
            "Excel Files (*.xlsx *.xls)",
        )
        if not filepaths:
            return

        count = len(filepaths)

        # ===== Method selection dialog =====
        method_dialog = QDialog(self)
        method_dialog.setWindowTitle("📦 Batch Import Method")
        method_dialog.setMinimumWidth(400)
        ml = QVBoxLayout(method_dialog)
        ml.addWidget(QLabel(f"<b>{count} files selected</b>"))
        ml.addWidget(QLabel(
            "Choose how to process each file:"
        ))

        self._batch_method = "smart"

        smart_radio = QRadioButton(
            "🤖 Smart Auto-Detect (recommended)"
        )
        smart_radio.setChecked(True)
        smart_radio.toggled.connect(
            lambda c: setattr(self, '_batch_method', 'smart')
            if c else None
        )
        ml.addWidget(smart_radio)

        tmpl_radio = QRadioButton("📄 Use Saved Template")
        tmpl_radio.toggled.connect(
            lambda c: setattr(self, '_batch_method', 'template')
            if c else None
        )
        ml.addWidget(tmpl_radio)

        tmpl_layout = QHBoxLayout()
        tmpl_layout.addWidget(QLabel("  Template:"))
        self._batch_template_combo = QComboBox()
        self._batch_template_combo.setEnabled(False)

        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "templates",
        )
        if os.path.exists(templates_dir):
            for f in sorted(os.listdir(templates_dir)):
                if f.endswith('.json') and not f.startswith('_'):
                    self._batch_template_combo.addItem(
                        f, os.path.join(templates_dir, f)
                    )
        tmpl_layout.addWidget(self._batch_template_combo, 1)
        ml.addLayout(tmpl_layout)

        tmpl_radio.toggled.connect(
            self._batch_template_combo.setEnabled
        )

        btn_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(method_dialog.accept)
        btn_box.rejected.connect(method_dialog.reject)
        ml.addWidget(btn_box)

        if method_dialog.exec() != QDialog.Accepted:
            return

        # ===== Load template if needed =====
        tmpl = None
        if self._batch_method == "template":
            tmpl_path = self._batch_template_combo.currentData()
            if not tmpl_path or not os.path.exists(tmpl_path):
                QMessageBox.warning(
                    self, "No Template",
                    "Select a valid template.",
                )
                return
            try:
                with open(tmpl_path, 'r', encoding='utf-8') as f:
                    tmpl = json.load(f)
            except Exception as e:
                QMessageBox.critical(
                    self, "Template Error",
                    f"Cannot load template:\n{e}",
                )
                return

        # ===== Progress dialog =====
        progress = QDialog(self)
        progress.setWindowTitle("📦 Batch Progress")
        progress.setFixedSize(600, 400)
        pl = QVBoxLayout(progress)

        method_label = (
            "Smart Auto-Detect"
            if self._batch_method == "smart"
            else "Template-Based"
        )
        pl.addWidget(QLabel(
            f"<b>Processing {count} files ({method_label})</b>"
        ))

        pbar = QProgressBar()
        pbar.setRange(0, count)
        pl.addWidget(pbar)

        log = QTextEdit()
        log.setReadOnly(True)
        log.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 10px;"
        )
        pl.addWidget(log)

        progress.show()
        QApplication.processEvents()

        # ===== Process files =====
        all_results = []
        success_count = 0
        fail_count = 0
        last_report_id = None
        last_section_id = None

        for i, fp in enumerate(filepaths):
            filename = os.path.basename(fp)
            log.append(f"\n🔄 [{i+1}/{count}] {filename}")
            QApplication.processEvents()

            dialog = None
            try:
                if self._batch_method == "smart":
                    # Smart: load file then auto-detect
                    dialog = SmartTemplateDialog(
                        self.db, self.well_id, None,
                        preload_file=fp,
                    )
                    QApplication.processEvents()

                    if not dialog.assignments:
                        dialog._smart_auto_detect()

                    if not dialog.assignments:
                        raise Exception(
                            "Smart detection found no fields"
                        )

                    log.append(
                        f"  🧠 Detected: "
                        f"{len(dialog.assignments)} fields"
                    )

                else:
                    # Template: load file first, then apply template
                    dialog = SmartTemplateDialog(
                        self.db, self.well_id, None,
                        preload_file=fp,
                    )
                    QApplication.processEvents()

                    if not dialog.cell_cache:
                        raise Exception("Failed to load Excel file")

                    dialog._apply_template(tmpl)
                    QApplication.processEvents()

                    if not dialog.assignments:
                        raise Exception(
                            "Template could not be applied"
                        )

                    log.append(
                        f"  📄 Template: "
                        f"{len(dialog.assignments)} fields"
                    )

                # Build and validate data
                extracted = dialog._build_final_data_from_assignments()
                has_data = any([
                    extracted.get("well_info"),
                    extracted.get("daily_report"),
                    extracted.get("mud_report"),
                    extracted.get("drilling_params"),
                ])

                if not extracted or not has_data:
                    raise Exception("No data extracted")

                # Cleanup dialog
                dialog.deleteLater()
                dialog = None

                # Save to database
                res = self._do_import(extracted, refresh_ui=False)
                all_results.append(res)

                if res.get("report_id"):
                    last_report_id = res["report_id"]
                if res.get("section_id"):
                    last_section_id = res["section_id"]

                imported = res.get('imported', 0)
                if imported > 0:
                    success_count += 1
                    log.append(f"  ✅ Imported: {imported}")
                    for detail in res.get('details', []):
                        log.append(f"     {detail}")
                else:
                    fail_count += 1
                    log.append("  ⚠️ No data imported")
                    for detail in res.get('details', []):
                        log.append(f"     {detail}")

            except Exception as e:
                fail_count += 1
                log.append(f"  ❌ Error: {str(e)}")
                logger.error(
                    f"Batch error for {filename}: {e}",
                    exc_info=True,
                )

                if dialog is not None:
                    try:
                        dialog.deleteLater()
                    except Exception:
                        pass
                    dialog = None

            pbar.setValue(i + 1)
            QApplication.processEvents()

        # ===== Summary =====
        log.append(f"\n{'='*55}")
        log.append(f"📊 BATCH COMPLETE:")
        log.append(f"   ✅ Success: {success_count}/{count}")
        log.append(f"   ❌ Failed:  {fail_count}/{count}")
        if last_report_id:
            log.append(f"   📅 Last Report ID: {last_report_id}")
        log.append(f"{'='*55}")
        QApplication.processEvents()

        # Add close button
        close_btn = QPushButton("✅ Close & Apply")
        close_btn.setStyleSheet(
            "background: #27ae60; color: white; padding: 10px 20px; "
            "font-weight: bold; border-radius: 4px; border: none; "
            "font-size: 12px;"
        )
        close_btn.clicked.connect(progress.accept)
        pl.addWidget(close_btn)

        progress.exec()

        # Emit results
        self.import_completed.emit(all_results)
        self.accept()

    # ================================================================
    # Database Import Logic
    # ================================================================
    def _do_import(
        self, extracted: dict, refresh_ui: bool = True
    ) -> dict:
        """Core import logic - saves extracted data to database"""
        results = {
            "imported": 0,
            "failed": 0,
            "details": [],
            "report_id": None,
            "section_id": None,
            "import_report": None,
        }
        session = None

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
            duplicate_indexes = set(find_duplicates(time_logs, "time_log"))
            for index in sorted(duplicate_indexes, reverse=True):
                del time_logs[index]
                log_quality.skipped += 1
            quality.total += log_quality.total
            quality.failed += log_quality.failed
            quality.issues.extend(log_quality.issues)
            results["import_report"] = quality.as_dict()
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
                    any_section = session.query(Section).filter(
                        Section.well_id == self.well_id,
                    ).first()

                    if any_section:
                        section_id = any_section.id
                    else:
                        dr_data = extracted.get("daily_report", {})
                        new_section = Section(
                            well_id=self.well_id,
                            name=section_name,
                            depth_from=ValueNormalizer.to_float(
                                dr_data.get("depth_0000")
                            ) or 0.0,
                            depth_to=ValueNormalizer.to_float(
                                dr_data.get("depth_2400")
                            ) or 0.0,
                        )
                        session.add(new_section)
                        session.flush()
                        section_id = new_section.id
                        results["details"].append(
                            f"✅ Section '{section_name}' created"
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
            dr["report_date"] = self._normalize_date(
                dr.get("report_date")
            )
            dr.setdefault("status", "Draft")

            # report_number
            report_num = self._ensure_report_number(
                dr, section_id
            )
            dr["report_number"] = report_num

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
                dr[depth_field] = (
                    ValueNormalizer.to_float(dr.get(depth_field))
                    or 0.0
                )

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
            self._save_mud_report(
                extracted.get("mud_report", {}),
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
        return result if result else dt_date.today()

    def _safe_text(self, value, default="") -> str:
        result = ValueNormalizer.to_str(value)
        if not result or result.endswith(":"):
            return default
        return result