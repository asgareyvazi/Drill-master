# tabs/w11_Export.py
"""
Export Center - مرکز تمام خروجی‌ها
"""
import os
import logging
from datetime import datetime

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from core.base_tab import DrillTabBase

logger = logging.getLogger(__name__)
# ==================== Main Export Widget ====================
class ExportWidget(DrillTabBase):
    """Export Center حرفه‌ای - مرکز تمام خروجی‌ها"""

    def __init__(self, db_manager=None, parent=None):
        super().__init__("ExportWidget", db_manager, parent)
        self.db = db_manager
        self._current_well_id = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabBar::tab {
                padding: 10px 18px; font-size: 11pt; font-weight: bold;
            }
            QTabBar::tab:selected {
                background: #2c3e50; color: white; border-radius: 4px;
            }
            QTabBar::tab:!selected { background: #ecf0f1; color: #555; }
        """)

        self.tab_widget.addTab(self._create_ddr_tab(), "📅 Daily Report")
        self.tab_widget.addTab(self._create_eowr_tab(), "📑 End of Well")
        self.tab_widget.addTab(self._create_npt_tab(), "⏱️ NPT Report")
        self.tab_widget.addTab(self._create_cost_tab(), "💰 Cost Report")
        self.tab_widget.addTab(self._create_plan_tab(), "📋 Drilling Plan")
        self.tab_widget.addTab(self._create_batch_tab(), "📦 Batch Export")

        layout.addWidget(self.tab_widget)

    # ==================== Well Selection Header ====================
    def _well_header(self, title, color="#2c3e50"):
        """هدر مشترک برای همه تب‌ها"""
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 5)

        lbl = QLabel(title)
        lbl.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {color}; "
            f"padding: 6px; background: {color}15; "
            f"border-left: 4px solid {color}; border-radius: 3px;"
        )
        hl.addWidget(lbl)

        hl.addWidget(QLabel("Well:"))
        combo = QComboBox()
        combo.setMinimumWidth(250)
        hl.addWidget(combo)

        refresh = QPushButton("🔄")
        refresh.setFixedWidth(30)
        refresh.clicked.connect(lambda: self._load_wells_into(combo))
        hl.addWidget(refresh)
        hl.addStretch()

        self._load_wells_into(combo)
        return header, combo

    def _load_wells_into(self, combo):
        combo.clear()
        if self.db:
            h = self.db.get_hierarchy()
            for c in h:
                for p in c.get("projects", []):
                    for w in p.get("wells", []):
                        combo.addItem(f"{w['name']} ({p['name']})", w["id"])
            current_id = self.sel_manager.current_well_id
            if current_id is not None:
                index = combo.findData(current_id)
                if index >= 0:
                    combo.setCurrentIndex(index)

    def _format_selector(self):
        """ساخت انتخابگر فرمت"""
        w = QWidget()
        hl = QHBoxLayout(w)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(QLabel("Format:"))
        combo = QComboBox()
        combo.addItems(["PDF", "HTML", "Excel"])
        hl.addWidget(combo)
        hl.addStretch()
        return w, combo

    def _watermark_input(self):
        w = QWidget()
        hl = QHBoxLayout(w)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(QLabel("Watermark:"))
        inp = QLineEdit()
        inp.setPlaceholderText("Draft / Confidential / Final")
        inp.setMaximumWidth(200)
        hl.addWidget(inp)
        hl.addStretch()
        return w, inp

    # ==================== 1. DDR Tab ====================
    def _create_ddr_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        header, self.ddr_well = self._well_header(
            "📅 Daily Drilling Report Export", "#3498db"
        )
        layout.addWidget(header)

        # Report selector
        rl = QHBoxLayout()
        rl.addWidget(QLabel("Report:"))
        self.ddr_report_combo = QComboBox()
        self.ddr_report_combo.setMinimumWidth(300)
        rl.addWidget(self.ddr_report_combo)
        load_btn = QPushButton("📂 Load Reports")
        load_btn.clicked.connect(self._load_ddr_reports)
        rl.addWidget(load_btn)
        rl.addStretch()
        layout.addLayout(rl)

        fmt_w, self.ddr_fmt = self._format_selector()
        layout.addWidget(fmt_w)

        wm_w, self.ddr_watermark = self._watermark_input()
        layout.addWidget(wm_w)

        # Preview
        self.ddr_preview = QTextEdit()
        self.ddr_preview.setReadOnly(True)
        self.ddr_preview.setMaximumHeight(150)
        self.ddr_preview.setStyleSheet(
            "font-size: 9px; background: #f9f9f9;"
        )
        layout.addWidget(QLabel("Preview:"))
        layout.addWidget(self.ddr_preview)

        # Buttons
        bl = QHBoxLayout()
        preview_btn = QPushButton("👁️ Preview")
        preview_btn.clicked.connect(self._preview_ddr)
        bl.addWidget(preview_btn)
        export_btn = QPushButton("🚀 Export DDR")
        export_btn.setStyleSheet(
            "background: #3498db; color: white; font-weight: bold; "
            "padding: 10px 20px; border-radius: 4px; border: none; "
            "font-size: 12px;"
        )
        export_btn.clicked.connect(self._export_ddr)
        bl.addWidget(export_btn)
        bl.addStretch()
        layout.addLayout(bl)

        self.ddr_status = QLabel("Select a well and report")
        self.ddr_status.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(self.ddr_status)
        layout.addStretch()

        self.ddr_well.currentIndexChanged.connect(self._load_ddr_reports)
        return tab

    def _load_ddr_reports(self):
        self.ddr_report_combo.clear()
        well_id = self.ddr_well.currentData()
        if not well_id or not self.db:
            return
        reports = self.db.get_daily_reports_by_well(well_id)
        for r in reports:
            self.ddr_report_combo.addItem(
                f"#{r.get('report_number','')} - {r.get('report_date','')}",
                r["id"]
            )

    def _preview_ddr(self):
        rid = self.ddr_report_combo.currentData()
        if not rid:
            return
        r = self.db.get_daily_report_by_id(rid)
        if r:
            self.ddr_preview.setPlainText(
                f"Report #{r.get('report_number','')} | "
                f"Date: {r.get('report_date','')} | "
                f"Day: {r.get('rig_day','')} | "
                f"Depth: {r.get('depth_2400',0)} m\n"
                f"Status: {r.get('status','')}\n"
                f"Summary: {(r.get('summary','') or '')[:200]}"
            )

    def _export_ddr(self):
        rid = self.ddr_report_combo.currentData()
        if not rid:
            QMessageBox.warning(self, "Warning", "Select a report.")
            return
        fmt = self.ddr_fmt.currentText().lower()
        ext = {"pdf": ".pdf", "html": ".html", "excel": ".xlsx"}.get(fmt, ".pdf")
        fn, _ = QFileDialog.getSaveFileName(
            self, "Export DDR",
            f"DDR_{datetime.now().strftime('%Y%m%d')}{ext}",
            f"Files (*{ext})"
        )
        if not fn:
            return
        from core.report_engine import DDRReportEngine
        engine = DDRReportEngine(self.db)
        engine.branding.watermark = self.ddr_watermark.text()
        if engine.generate(rid, fn, fmt):
            self.ddr_status.setText(f"✅ Exported: {fn}")
            if os.name == 'nt':
                os.startfile(fn)
        else:
            self.ddr_status.setText("❌ Export failed")

    # ==================== 2. EOWR Tab ====================
    def _create_eowr_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        header, self.eowr_well = self._well_header(
            "📑 End of Well Report", "#27ae60"
        )
        layout.addWidget(header)

        fmt_w, self.eowr_fmt = self._format_selector()
        layout.addWidget(fmt_w)

        wm_w, self.eowr_watermark = self._watermark_input()
        layout.addWidget(wm_w)

        export_btn = QPushButton("🚀 Generate EOWR")
        export_btn.setStyleSheet(
            "background: #27ae60; color: white; font-weight: bold; "
            "padding: 10px 20px; border-radius: 4px; border: none; "
            "font-size: 12px;"
        )
        export_btn.clicked.connect(self._export_eowr)
        layout.addWidget(export_btn)

        self.eowr_status = QLabel("Select a well")
        self.eowr_status.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(self.eowr_status)
        layout.addStretch()
        return tab

    def _export_eowr(self):
        wid = self.eowr_well.currentData()
        if not wid:
            QMessageBox.warning(self, "Warning", "Select a well.")
            return
        fmt = self.eowr_fmt.currentText().lower()
        ext = {"pdf": ".pdf", "html": ".html", "excel": ".xlsx"}.get(fmt, ".pdf")
        fn, _ = QFileDialog.getSaveFileName(
            self, "Export EOWR",
            f"EOWR_{datetime.now().strftime('%Y%m%d')}{ext}",
            f"Files (*{ext})"
        )
        if not fn:
            return
        from core.report_engine import EOWRReportEngine
        engine = EOWRReportEngine(self.db)
        engine.branding.watermark = self.eowr_watermark.text()
        self.eowr_status.setText("🔄 Generating...")
        QApplication.processEvents()
        if engine.generate(wid, fn, fmt):
            self.eowr_status.setText(f"✅ Exported: {fn}")
            if os.name == 'nt':
                os.startfile(fn)
        else:
            self.eowr_status.setText("❌ Export failed")

    # ==================== 3. NPT Tab ====================
    def _create_npt_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        header, self.npt_well = self._well_header(
            "⏱️ NPT Summary Report", "#e74c3c"
        )
        layout.addWidget(header)

        # Date range
        dr = QHBoxLayout()
        dr.addWidget(QLabel("From:"))
        self.npt_from = QDateEdit()
        self.npt_from.setCalendarPopup(True)
        self.npt_from.setDate(QDate.currentDate().addDays(-90))
        dr.addWidget(self.npt_from)
        dr.addWidget(QLabel("To:"))
        self.npt_to = QDateEdit()
        self.npt_to.setCalendarPopup(True)
        self.npt_to.setDate(QDate.currentDate())
        dr.addWidget(self.npt_to)
        dr.addStretch()
        layout.addLayout(dr)

        fmt_w, self.npt_fmt = self._format_selector()
        layout.addWidget(fmt_w)

        export_btn = QPushButton("🚀 Generate NPT Report")
        export_btn.setStyleSheet(
            "background: #e74c3c; color: white; font-weight: bold; "
            "padding: 10px 20px; border-radius: 4px; border: none; "
            "font-size: 12px;"
        )
        export_btn.clicked.connect(self._export_npt)
        layout.addWidget(export_btn)

        self.npt_status = QLabel("Select a well and date range")
        self.npt_status.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(self.npt_status)
        layout.addStretch()
        return tab

    def _export_npt(self):
        wid = self.npt_well.currentData()
        if not wid:
            QMessageBox.warning(self, "Warning", "Select a well.")
            return
        fmt = self.npt_fmt.currentText().lower()
        ext = {"pdf": ".pdf", "html": ".html", "excel": ".xlsx"}.get(fmt, ".pdf")
        fn, _ = QFileDialog.getSaveFileName(
            self, "Export NPT Report",
            f"NPT_{datetime.now().strftime('%Y%m%d')}{ext}",
            f"Files (*{ext})"
        )
        if not fn:
            return
        from core.report_engine import NPTReportEngine
        engine = NPTReportEngine(self.db)
        self.npt_status.setText("🔄 Generating...")
        QApplication.processEvents()
        if engine.generate(
            wid, fn, fmt,
            self.npt_from.date().toPython(),
            self.npt_to.date().toPython()
        ):
            self.npt_status.setText(f"✅ Exported: {fn}")
            if os.name == 'nt':
                os.startfile(fn)
        else:
            self.npt_status.setText("❌ Export failed")

    # ==================== 4. Cost Tab ====================
    def _create_cost_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        header, self.cost_well = self._well_header(
            "💰 Cost Analysis Report", "#f39c12"
        )
        layout.addWidget(header)

        # Rates
        rl = QHBoxLayout()
        rl.addWidget(QLabel("Rig Rate ($/day):"))
        self.cost_rig_rate = QDoubleSpinBox()
        self.cost_rig_rate.setRange(0, 999999)
        self.cost_rig_rate.setValue(45000)
        self.cost_rig_rate.setPrefix("$ ")
        rl.addWidget(self.cost_rig_rate)
        rl.addWidget(QLabel("Spread ($/day):"))
        self.cost_spread = QDoubleSpinBox()
        self.cost_spread.setRange(0, 999999)
        self.cost_spread.setValue(15000)
        self.cost_spread.setPrefix("$ ")
        rl.addWidget(self.cost_spread)
        rl.addStretch()
        layout.addLayout(rl)

        fmt_w, self.cost_fmt = self._format_selector()
        layout.addWidget(fmt_w)

        export_btn = QPushButton("🚀 Generate Cost Report")
        export_btn.setStyleSheet(
            "background: #f39c12; color: white; font-weight: bold; "
            "padding: 10px 20px; border-radius: 4px; border: none; "
            "font-size: 12px;"
        )
        export_btn.clicked.connect(self._export_cost)
        layout.addWidget(export_btn)

        self.cost_status = QLabel("Select a well")
        self.cost_status.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(self.cost_status)
        layout.addStretch()
        return tab

    def _export_cost(self):
        wid = self.cost_well.currentData()
        if not wid:
            QMessageBox.warning(self, "Warning", "Select a well.")
            return
        fmt = self.cost_fmt.currentText().lower()
        ext = {"pdf": ".pdf", "html": ".html", "excel": ".xlsx"}.get(fmt, ".pdf")
        fn, _ = QFileDialog.getSaveFileName(
            self, "Export Cost Report",
            f"Cost_{datetime.now().strftime('%Y%m%d')}{ext}",
            f"Files (*{ext})"
        )
        if not fn:
            return
        from core.report_engine import CostReportEngine
        engine = CostReportEngine(self.db)
        self.cost_status.setText("🔄 Generating...")
        QApplication.processEvents()
        if engine.generate(
            wid, fn, fmt,
            self.cost_rig_rate.value(),
            self.cost_spread.value()
        ):
            self.cost_status.setText(f"✅ Exported: {fn}")
            if os.name == 'nt':
                os.startfile(fn)
        else:
            self.cost_status.setText("❌ Export failed")

    # ==================== 5. Plan Tab ====================
    def _create_plan_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        header, self.plan_well = self._well_header(
            "📋 Drilling Plan Report", "#9b59b6"
        )
        layout.addWidget(header)

        fmt_w, self.plan_fmt = self._format_selector()
        layout.addWidget(fmt_w)

        export_btn = QPushButton("🚀 Generate Plan Report")
        export_btn.setStyleSheet(
            "background: #9b59b6; color: white; font-weight: bold; "
            "padding: 10px 20px; border-radius: 4px; border: none; "
            "font-size: 12px;"
        )
        export_btn.clicked.connect(self._export_plan)
        layout.addWidget(export_btn)

        self.plan_status = QLabel("Select a well with a saved plan")
        self.plan_status.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(self.plan_status)
        layout.addStretch()
        return tab

    def _export_plan(self):
        wid = self.plan_well.currentData()
        if not wid:
            QMessageBox.warning(self, "Warning", "Select a well.")
            return
        fmt = self.plan_fmt.currentText().lower()
        ext = {"pdf": ".pdf", "html": ".html", "excel": ".xlsx"}.get(fmt, ".pdf")
        fn, _ = QFileDialog.getSaveFileName(
            self, "Export Plan Report",
            f"Plan_{datetime.now().strftime('%Y%m%d')}{ext}",
            f"Files (*{ext})"
        )
        if not fn:
            return
        from core.report_engine import PlanReportEngine
        engine = PlanReportEngine(self.db)
        self.plan_status.setText("🔄 Generating...")
        QApplication.processEvents()
        if engine.generate(wid, fn, fmt):
            self.plan_status.setText(f"✅ Exported: {fn}")
            if os.name == 'nt':
                os.startfile(fn)
        else:
            self.plan_status.setText("❌ Export failed")

    # ==================== 6. Batch Tab ====================
    def _create_batch_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        header, self.batch_well = self._well_header(
            "📦 Batch Export - All Reports", "#2c3e50"
        )
        layout.addWidget(header)

        # Checkboxes
        cb_layout = QHBoxLayout()
        self.batch_ddr = QCheckBox("📅 All DDRs")
        self.batch_ddr.setChecked(True)
        self.batch_eowr = QCheckBox("📑 EOWR")
        self.batch_eowr.setChecked(True)
        self.batch_npt = QCheckBox("⏱️ NPT")
        self.batch_npt.setChecked(True)
        self.batch_cost = QCheckBox("💰 Cost")
        self.batch_cost.setChecked(True)
        self.batch_plan = QCheckBox("📋 Plan")
        self.batch_plan.setChecked(True)
        for cb in [self.batch_ddr, self.batch_eowr, self.batch_npt,
                    self.batch_cost, self.batch_plan]:
            cb_layout.addWidget(cb)
        cb_layout.addStretch()
        layout.addLayout(cb_layout)

        fmt_w, self.batch_fmt = self._format_selector()
        layout.addWidget(fmt_w)

        export_btn = QPushButton("🚀 Export All Selected")
        export_btn.setStyleSheet(
            "background: #2c3e50; color: white; font-weight: bold; "
            "padding: 10px 20px; border-radius: 4px; border: none; "
            "font-size: 12px;"
        )
        export_btn.clicked.connect(self._export_batch)
        layout.addWidget(export_btn)

        self.batch_log = QTextEdit()
        self.batch_log.setReadOnly(True)
        self.batch_log.setMaximumHeight(200)
        self.batch_log.setStyleSheet(
            "font-family: Consolas; font-size: 10px; "
            "background: #1e1e2e; color: #ecf0f1;"
        )
        layout.addWidget(self.batch_log)
        layout.addStretch()
        return tab

    def _export_batch(self):
        wid = self.batch_well.currentData()
        if not wid:
            QMessageBox.warning(self, "Warning", "Select a well.")
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder"
        )
        if not folder:
            return

        fmt = self.batch_fmt.currentText().lower()
        ext = {"pdf": ".pdf", "html": ".html", "excel": ".xlsx"}.get(fmt, ".pdf")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        self.batch_log.clear()
        self.batch_log.append(f"📦 Batch Export Started: {ts}")
        QApplication.processEvents()

        count = 0

        if self.batch_eowr.isChecked():
            fn = os.path.join(folder, f"EOWR_{ts}{ext}")
            from core.report_engine import EOWRReportEngine
            if EOWRReportEngine(self.db).generate(wid, fn, fmt):
                self.batch_log.append(f"✅ EOWR: {fn}")
                count += 1
            else:
                self.batch_log.append("❌ EOWR failed")
            QApplication.processEvents()

        if self.batch_npt.isChecked():
            fn = os.path.join(folder, f"NPT_{ts}{ext}")
            from core.report_engine import NPTReportEngine
            if NPTReportEngine(self.db).generate(wid, fn, fmt):
                self.batch_log.append(f"✅ NPT: {fn}")
                count += 1
            else:
                self.batch_log.append("❌ NPT failed")
            QApplication.processEvents()

        if self.batch_cost.isChecked():
            fn = os.path.join(folder, f"Cost_{ts}{ext}")
            from core.report_engine import CostReportEngine
            if CostReportEngine(self.db).generate(wid, fn, fmt):
                self.batch_log.append(f"✅ Cost: {fn}")
                count += 1
            else:
                self.batch_log.append("❌ Cost failed")
            QApplication.processEvents()

        if self.batch_plan.isChecked():
            fn = os.path.join(folder, f"Plan_{ts}{ext}")
            from core.report_engine import PlanReportEngine
            if PlanReportEngine(self.db).generate(wid, fn, fmt):
                self.batch_log.append(f"✅ Plan: {fn}")
                count += 1
            else:
                self.batch_log.append("❌ Plan failed")
            QApplication.processEvents()

        if self.batch_ddr.isChecked():
            reports = self.db.get_daily_reports_by_well(wid)
            for r in reports:
                fn = os.path.join(
                    folder,
                    f"DDR_{r.get('report_number','')}_"
                    f"{r.get('report_date','')}{ext}"
                )
                from core.report_engine import DDRReportEngine
                if DDRReportEngine(self.db).generate(r["id"], fn, fmt):
                    count += 1
                QApplication.processEvents()
            self.batch_log.append(
                f"✅ DDRs: {len(reports)} reports exported"
            )

        self.batch_log.append(f"\n📊 Done: {count} files exported to {folder}")

        if os.name == 'nt':
            os.startfile(folder)

    # ==================== DrillTabBase ====================
    def on_well_changed(self, well_id, well_data):
        self._current_well_id = well_id
        # Sync all combos
        for combo in [self.ddr_well, self.eowr_well, self.npt_well,
                       self.cost_well, self.plan_well, self.batch_well]:
            combo.blockSignals(True)
            for i in range(combo.count()):
                if combo.itemData(i) == well_id:
                    combo.setCurrentIndex(i)
                    break
            combo.blockSignals(False)
        # Load DDR reports
        self._load_ddr_reports()

    def on_report_changed(self, report_id, report_data):
        """Keep export center aligned with the globally selected report."""
        for i in range(self.ddr_report_combo.count()):
            if self.ddr_report_combo.itemData(i) == report_id:
                self.ddr_report_combo.blockSignals(True)
                self.ddr_report_combo.setCurrentIndex(i)
                self.ddr_report_combo.blockSignals(False)
                self._preview_ddr()
                break

    def set_current_well(self, well_id, well_data=None):
        """Sync همه combo ها و load reports"""
        self._current_well_id = well_id

        # ✅ Sync تمام well combo ها
        combos = [
            self.ddr_well, self.eowr_well, self.npt_well,
            self.cost_well, self.plan_well, self.batch_well
        ]
        for combo in combos:
            combo.blockSignals(True)

            # اگر well در لیست نیست، refresh کن
            found = False
            for i in range(combo.count()):
                if combo.itemData(i) == well_id:
                    combo.setCurrentIndex(i)
                    found = True
                    break

            if not found:
                # ✅ Reload wells
                self._load_wells_into(combo)
                for i in range(combo.count()):
                    if combo.itemData(i) == well_id:
                        combo.setCurrentIndex(i)
                        break

            combo.blockSignals(False)

        # Load DDR reports
        self._load_ddr_reports()

    def save_data(self):
        return True

    def refresh(self):
        for combo in [self.ddr_well, self.eowr_well, self.npt_well,
                       self.cost_well, self.plan_well, self.batch_well]:
            self._load_wells_into(combo)