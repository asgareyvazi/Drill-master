# tabs/w16_Cost_Management.py
"""
Cost Management Module
مدیریت هزینه عملیات حفاری
"""
import logging
from datetime import datetime, date
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from core.base_tab import DrillTabBase
from core.managers import ExportManager
from core.common_widgets import safe_replace_chart
from core.cost_semantics import (
    canonical_variance, allocate_npt_cost, summarize_afe, cost_records_to_afe_rows,
    COST_TYPE_BUDGET,
)

logger = logging.getLogger(__name__)


class CostManagementWidget(DrillTabBase):
    """تب مدیریت هزینه"""

    def __init__(self, db_manager=None, parent=None):
        super().__init__("CostManagementWidget", db_manager, parent)
        self.current_well_id = None
        self.cost_items = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)

        header = QLabel("💰 Cost Management & Tracking")
        header.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #ecf0f1; padding: 8px; border: none; "
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2c3e50,stop:1 #34495e); border-radius: 5px;"
        )
        layout.addWidget(header)

        scope = QLabel("Scope: Whole-Well Aggregate — costs sum across all wellbores/sidetracks")
        scope.setStyleSheet(
            "font-size: 11px; color: #bdc3c7; padding: 2px 8px; border: none;"
        )
        layout.addWidget(scope)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_afe_tab(), "📋 AFE")
        self.tabs.addTab(self._create_daily_cost_tab(), "📅 Daily Cost")
        self.tabs.addTab(self._create_npt_cost_tab(), "⏱️ NPT Cost")
        self.tabs.addTab(self._create_summary_tab(), "📊 Summary")
        layout.addWidget(self.tabs)

    # ===== AFE Tab =====
    def _create_afe_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # AFE Header
        g_header = QGroupBox("📋 Authorization for Expenditure")
        hf = QFormLayout(g_header)

        self.afe_number = QLineEdit()
        self.afe_number.setPlaceholderText("AFE-2024-001")
        # Total Budget is DERIVED (read-only): it mirrors the sum of the
        # persisted planned costs in the breakdown below. It is not a separate
        # editable field that silently vanishes on save.
        self.afe_total = QLabel("$ 0")
        self.afe_total.setStyleSheet("font-weight: bold; color: #2c3e50;")
        self.afe_currency = QComboBox()
        # Leading blank represents UNKNOWN currency — never silently assume USD.
        self.afe_currency.addItems(["— (unspecified)", "USD", "EUR", "GBP", "IRR"])
        # Planned Days is a NON-PERSISTENT reference here. Its authoritative
        # home is the Planning tab (WellPlan.planned_total_days); this widget
        # only mirrors it and never writes it, so the label says so plainly.
        self.afe_days = QSpinBox()
        self.afe_days.setRange(0, 999)
        self.afe_days.setSuffix(" days")
        # Reference mirror of WellPlan.planned_total_days — not editable here so
        # the UI cannot imply this widget owns/persists planned days.
        self.afe_days.setReadOnly(True)
        self.afe_days.setButtonSymbols(QAbstractSpinBox.NoButtons)

        hf.addRow("AFE Number:", self.afe_number)
        hf.addRow("Total Planned (auto):", self.afe_total)
        hf.addRow("Currency:", self.afe_currency)
        hf.addRow("Planned Days (reference — set in Planning):", self.afe_days)
        layout.addWidget(g_header)

        # Cost Categories
        g_cat = QGroupBox("📊 Cost Breakdown by Category")
        cat_layout = QVBoxLayout(g_cat)

        cat_btns = QHBoxLayout()
        add_cat = QPushButton("➕ Add Category")
        add_cat.setStyleSheet("background: #27ae60; color: white; padding: 4px 10px; border-radius: 3px; border: none;")
        add_cat.clicked.connect(self._add_cost_category)
        rem_cat = QPushButton("🗑️ Remove")
        rem_cat.clicked.connect(self._rem_cost_category)
        save_afe = QPushButton("💾 Save AFE")
        save_afe.setStyleSheet("background: #2980b9; color: white; padding: 4px 10px; border-radius: 3px; border: none; font-weight: bold;")
        save_afe.clicked.connect(self.save_data)
        reload_afe = QPushButton("🔄 Reload")
        reload_afe.clicked.connect(self._load_afe_from_db)
        cat_btns.addWidget(add_cat)
        cat_btns.addWidget(rem_cat)
        cat_btns.addWidget(save_afe)
        cat_btns.addWidget(reload_afe)
        cat_btns.addStretch()
        cat_layout.addLayout(cat_btns)

        self.afe_table = QTableWidget(0, 5)
        self.afe_table.setHorizontalHeaderLabels(["Category", "Planned ($)", "Actual ($)", "Variance ($)", "% Used"])
        self.afe_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.afe_table.setAlternatingRowColors(True)
        cat_layout.addWidget(self.afe_table)

        # Default categories
        default_cats = [
            ("Rig & Equipment", 500000), ("Drilling Services", 300000),
            ("Mud & Chemicals", 200000), ("Cementing", 150000),
            ("Casing & Tubulars", 400000), ("Logging & MWD", 180000),
            ("Bits & Tools", 120000), ("Well Control", 50000),
            ("Logistics & Transport", 100000), ("Personnel", 80000),
            ("Contingency (10%)", 208000),
        ]
        for cat, planned in default_cats:
            self._insert_afe_row(cat, planned, 0)

        # Totals
        self.afe_total_label = QLabel("")
        self.afe_total_label.setStyleSheet("font-weight: bold; color: #2c3e50; padding: 5px; background: #ecf0f1; border-radius: 3px;")
        cat_layout.addWidget(self.afe_total_label)
        self._update_afe_totals()

        layout.addWidget(g_cat)
        return tab

    def _insert_afe_row(self, category, planned, actual):
        row = self.afe_table.rowCount()
        self.afe_table.insertRow(row)
        self.afe_table.setItem(row, 0, QTableWidgetItem(category))

        planned_spin = QDoubleSpinBox()
        planned_spin.setRange(0, 999999999)
        planned_spin.setPrefix("$ ")
        planned_spin.setDecimals(0)
        planned_spin.setValue(planned)
        planned_spin.valueChanged.connect(self._update_afe_totals)
        self.afe_table.setCellWidget(row, 1, planned_spin)

        actual_spin = QDoubleSpinBox()
        actual_spin.setRange(0, 999999999)
        actual_spin.setPrefix("$ ")
        actual_spin.setDecimals(0)
        actual_spin.setValue(actual)
        actual_spin.valueChanged.connect(self._update_afe_totals)
        self.afe_table.setCellWidget(row, 2, actual_spin)

        var_item = QTableWidgetItem(f"$ {planned - actual:,.0f}")
        var_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.afe_table.setItem(row, 3, var_item)

        pct_item = QTableWidgetItem(f"{actual/planned*100:.0f}%" if planned > 0 else "0%")
        pct_item.setTextAlignment(Qt.AlignCenter)
        self.afe_table.setItem(row, 4, pct_item)

    def _add_cost_category(self):
        name, ok = QInputDialog.getText(self, "Add Category", "Category name:")
        if ok and name:
            self._insert_afe_row(name, 0, 0)

    def _rem_cost_category(self):
        row = self.afe_table.currentRow()
        if row >= 0:
            self.afe_table.removeRow(row)
            self._update_afe_totals()

    def _update_afe_totals(self):
        total_planned = 0
        total_actual = 0
        for row in range(self.afe_table.rowCount()):
            pw = self.afe_table.cellWidget(row, 1)
            aw = self.afe_table.cellWidget(row, 2)
            planned = pw.value() if pw else 0
            actual = aw.value() if aw else 0
            total_planned += planned
            total_actual += actual
            variance = planned - actual

            vi = self.afe_table.item(row, 3)
            if not vi:
                vi = QTableWidgetItem()
                self.afe_table.setItem(row, 3, vi)
            vi.setText(f"$ {variance:,.0f}")
            vi.setForeground(QColor("#27ae60" if variance >= 0 else "#e74c3c"))

            pi = self.afe_table.item(row, 4)
            if not pi:
                pi = QTableWidgetItem()
                self.afe_table.setItem(row, 4, pi)
            pct = actual / planned * 100 if planned > 0 else 0
            pi.setText(f"{pct:.0f}%")
            if pct > 100:
                pi.setForeground(QColor("#e74c3c"))

        variance = total_planned - total_actual
        self.afe_total_label.setText(
            f"💰 TOTAL → Planned: ${total_planned:,.0f} | Actual: ${total_actual:,.0f} | "
            f"Variance: ${variance:,.0f} ({'+' if variance >= 0 else ''}{variance/total_planned*100:.1f}%)" if total_planned > 0 else ""
        )
        # Keep the derived header "Total Planned" in sync with the breakdown.
        self.afe_total.setText(f"$ {total_planned:,.0f}")

    # ===== Daily Cost Tab =====
    def _create_daily_cost_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        g1 = QGroupBox("📅 Daily Cost Parameters")
        f1 = QFormLayout(g1)

        self.rig_rate = QDoubleSpinBox()
        self.rig_rate.setRange(0, 999999)
        self.rig_rate.setPrefix("$ ")
        self.rig_rate.setValue(0)
        self.rig_rate.setSuffix(" /day")

        self.spread_rate = QDoubleSpinBox()
        self.spread_rate.setRange(0, 999999)
        self.spread_rate.setPrefix("$ ")
        self.spread_rate.setValue(0)
        self.spread_rate.setSuffix(" /day")

        self.total_daily = QLabel("$ 0 /day")
        self.total_daily.setStyleSheet("font-weight: bold; color: #e74c3c; font-size: 14px;")

        assume = QLabel(
            "⚠️ Day-rate figures below are planning ASSUMPTIONS you enter — they "
            "are NOT actual recorded cost. Actual cost comes from the AFE tab "
            "(persisted) and reports."
        )
        assume.setWordWrap(True)
        assume.setStyleSheet("color: #b9770e; font-size: 10px; background: #fef9e7; padding: 4px; border-radius: 3px;")

        f1.addRow("Rig Day Rate:", self.rig_rate)
        f1.addRow("Spread Cost:", self.spread_rate)
        f1.addRow("Total Daily:", self.total_daily)
        f1.addRow(assume)

        self.rig_rate.valueChanged.connect(self._update_daily_total)
        self.spread_rate.valueChanged.connect(self._update_daily_total)

        layout.addWidget(g1)

        # Cost tracking
        g2 = QGroupBox("📊 Cost Tracking")
        g2_layout = QVBoxLayout(g2)

        calc_btn = QPushButton("🔄 Calculate from Well Data")
        calc_btn.setStyleSheet("background: #3498db; color: white; font-weight: bold; padding: 8px; border-radius: 4px; border: none;")
        calc_btn.clicked.connect(self._calc_from_well)
        g2_layout.addWidget(calc_btn)

        self.cost_result = QTextEdit()
        self.cost_result.setReadOnly(True)
        self.cost_result.setMinimumHeight(300)
        self.cost_result.setStyleSheet("font-family: Consolas; font-size: 11px; background: #1e1e2e; color: #ecf0f1;")
        g2_layout.addWidget(self.cost_result)

        layout.addWidget(g2)
        return tab

    def _update_daily_total(self):
        total = self.rig_rate.value() + self.spread_rate.value()
        self.total_daily.setText(f"$ {total:,.0f} /day")

    def _calc_from_well(self):
        if not self.current_well_id or not self.db:
            self.cost_result.setText("❌ Select a well first")
            return

        reports = self.db.get_daily_reports_by_well(self.current_well_id)
        total_days = len(reports)
        daily_rate = self.rig_rate.value() + self.spread_rate.value()

        npt_hrs = 0
        npt_list = self.db.get_npt_reports(well_id=self.current_well_id) if hasattr(self.db, 'get_npt_reports') else []
        npt_hrs = sum(n.get('duration_hours', 0) for n in npt_list)
        npt_days = npt_hrs / 24
        pt_days = total_days - npt_days

        total_cost = total_days * daily_rate
        npt_cost = npt_days * daily_rate
        pt_cost = pt_days * daily_rate

        # Percentages are only meaningful when a non-zero rate is entered;
        # guard against division by zero when both day-rates are left at 0.
        pt_pct = (pt_cost / total_cost * 100) if total_cost else 0
        npt_pct = (npt_cost / total_cost * 100) if total_cost else 0

        # Cost per meter
        max_depth = 0
        if reports:
            max_depth = max(r.get('depth_2400', 0) or 0 for r in reports)
        cpm = total_cost / max_depth if max_depth > 0 else 0
        cpf = cpm / 3.28084 if max_depth > 0 else 0

        text = f"""╔═══════════════════════════════════════════════╗
║     WELL COST PROJECTION (day-rate assumption) ║
║     NOT actual recorded cost — see AFE/Summary ║
╠═══════════════════════════════════════════════╣
║ PARAMETERS (assumed):
║   Rig Day Rate:     $ {self.rig_rate.value():,.0f}
║   Spread Cost:      $ {self.spread_rate.value():,.0f}
║   Total Daily:      $ {daily_rate:,.0f}
╠═══════════════════════════════════════════════╣
║ WELL DATA:
║   Total Rig Days:   {total_days}
║   Productive Days:  {pt_days:.1f}
║   NPT Days:         {npt_days:.1f} ({npt_hrs:.1f} hrs)
║   Final Depth:      {max_depth:.1f} m
╠═══════════════════════════════════════════════╣
║ COST BREAKDOWN:
║   Total Cost:       $ {total_cost:,.0f}
║   Productive Cost:  $ {pt_cost:,.0f} ({pt_pct:.0f}%)
║   NPT Cost:         $ {npt_cost:,.0f} ({npt_pct:.0f}%)
╠═══════════════════════════════════════════════╣
║ EFFICIENCY:
║   Cost per Meter:   $ {cpm:,.0f} /m
║   Cost per Foot:    $ {cpf:,.0f} /ft
║   Avg Cost per Day: $ {daily_rate:,.0f}
╚═══════════════════════════════════════════════╝""" if total_days > 0 else "No daily reports found for this well."

        self.cost_result.setText(text)

    # ===== NPT Cost Tab =====
    def _create_npt_cost_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        calc_btn = QPushButton("🔄 Analyze NPT Cost from Well Data")
        calc_btn.setStyleSheet("background: #e74c3c; color: white; font-weight: bold; padding: 8px; border-radius: 4px; border: none;")
        calc_btn.clicked.connect(self._calc_npt_cost)
        layout.addWidget(calc_btn)

        self.npt_cost_table = QTableWidget(0, 4)
        self.npt_cost_table.setHorizontalHeaderLabels(["NPT Category", "Hours", "Cost ($)", "% of Total NPT"])
        self.npt_cost_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.npt_cost_table.setAlternatingRowColors(True)
        self.npt_cost_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.npt_cost_table)

        self.npt_cost_summary = QLabel("")
        self.npt_cost_summary.setStyleSheet("font-weight: bold; color: #e74c3c; padding: 5px; background: #fadbd8; border-radius: 3px;")
        layout.addWidget(self.npt_cost_summary)

        return tab

    def _calc_npt_cost(self):
        if not self.current_well_id or not self.db:
            return

        # NPT cost is an allocation of the well's STORED ACTUAL cost across NPT
        # time (canonical model, matching the report engine). It is only known
        # when actual cost AND total recorded time exist — otherwise "unknown",
        # never a synthetic rig-rate product.
        from core.operations_intelligence import OperationsIntelligenceService
        kpis = OperationsIntelligenceService(self.db).analyze_well(
            self.current_well_id).get("kpis", {})
        actual_cost = kpis.get("total_cost")
        well_total_hours = (kpis.get("npt_hours") or 0) + (kpis.get("productive_hours") or 0)

        npt_list = self.db.get_npt_reports(well_id=self.current_well_id) if hasattr(self.db, 'get_npt_reports') else []

        # Group by category
        categories = {}
        for n in npt_list:
            cat = n.get('npt_category', 'Unknown')
            hrs = n.get('duration_hours', 0)
            categories[cat] = categories.get(cat, 0) + hrs

        total_npt = sum(categories.values())
        total_npt_cost = allocate_npt_cost(actual_cost, total_npt, well_total_hours or None)

        def money(v):
            return f"$ {v:,.0f}" if v is not None else "$ —"

        self.npt_cost_table.setRowCount(0)
        sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)

        for cat, hrs in sorted_cats:
            row = self.npt_cost_table.rowCount()
            self.npt_cost_table.insertRow(row)
            cost = allocate_npt_cost(actual_cost, hrs, well_total_hours or None)
            pct = hrs / total_npt * 100 if total_npt > 0 else 0

            self.npt_cost_table.setItem(row, 0, QTableWidgetItem(cat))
            hi = QTableWidgetItem(f"{hrs:.1f}")
            hi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.npt_cost_table.setItem(row, 1, hi)
            ci = QTableWidgetItem(money(cost))
            ci.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.npt_cost_table.setItem(row, 2, ci)
            self.npt_cost_table.setItem(row, 3, QTableWidgetItem(f"{pct:.1f}%"))

        cost_note = (
            money(total_npt_cost) if actual_cost is not None
            else "$ — (no actual cost recorded)"
        )
        self.npt_cost_summary.setText(
            f"⏱️ Total NPT: {total_npt:.1f} hrs ({total_npt/24:.1f} days) | "
            f"💰 Total NPT Cost: {cost_note}"
        )

    # ===== Summary Tab =====
    def _create_summary_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        calc_btn = QPushButton("📊 Generate Cost Summary")
        calc_btn.setStyleSheet("background: #9b59b6; color: white; font-weight: bold; padding: 8px; border-radius: 4px; border: none;")
        calc_btn.clicked.connect(self._generate_summary)
        layout.addWidget(calc_btn)

        # KPI Cards
        cards = QWidget()
        cl = QHBoxLayout(cards)
        cl.setContentsMargins(0, 0, 0, 0)

        self.card_total = self._make_card("Total Actual Cost", "$ —", "", "#e74c3c")
        self.card_daily = self._make_card("Actual Cost/Day", "$ —", "", "#3498db")
        self.card_meter = self._make_card("Actual Cost/Meter", "$ —", "", "#27ae60")
        self.card_npt = self._make_card("NPT Cost (allocated)", "$ —", "", "#f39c12")

        cl.addWidget(self.card_total)
        cl.addWidget(self.card_daily)
        cl.addWidget(self.card_meter)
        cl.addWidget(self.card_npt)
        layout.addWidget(cards)

        # Chart
        self.cost_chart = QWidget()
        self.cost_chart.setMinimumHeight(300)
        layout.addWidget(self.cost_chart)

        # Export
        export_btn = QPushButton("📤 Export Cost Report")
        export_btn.clicked.connect(self._export_cost)
        layout.addWidget(export_btn)

        return tab

    def _make_card(self, title, value, unit, color):
        card = QFrame()
        card.setStyleSheet(f"QFrame {{ background: {color}15; border-left: 4px solid {color}; border-radius: 4px; padding: 5px; margin: 2px; }}")
        ly = QVBoxLayout(card)
        ly.setContentsMargins(5, 3, 5, 3)
        t = QLabel(title)
        t.setStyleSheet("font-size: 10px; color: #7f8c8d; font-weight: bold;")
        ly.addWidget(t)
        v = QLabel(f"<b>{value}</b> {unit}")
        v.setStyleSheet(f"font-size: 16px; color: {color};")
        ly.addWidget(v)
        card.value_label = v
        return card

    def _generate_summary(self):
        if not self.current_well_id or not self.db:
            return

        # AUTHORITATIVE cost KPIs come from persisted CostRecord actuals, NOT a
        # synthetic rig-day rate. Unknown stays unknown ($ —), never a fake 0.
        # Total actual cost is read directly from the cost summary so it is
        # available even for a well that has cost lines but no daily reports;
        # depth-dependent metrics come from the canonical KPI service.
        from core.operations_intelligence import OperationsIntelligenceService
        summary = self.db.get_cost_summary(self.current_well_id)
        actual_vals = [r.get("actual") for r in summary if r.get("actual") is not None]
        total_cost = sum(float(v) for v in actual_vals) if actual_vals else None
        kpis = OperationsIntelligenceService(self.db).analyze_well(
            self.current_well_id).get("kpis", {})
        cpm = kpis.get("cost_per_meter")
        npt_hours = kpis.get("npt_hours")
        total_hours = (npt_hours or 0) + (kpis.get("productive_hours") or 0)
        npt_cost = allocate_npt_cost(total_cost, npt_hours, total_hours or None)
        rig_days = kpis.get("rig_days") or 0
        daily_actual = (total_cost / rig_days) if (total_cost is not None and rig_days) else None

        def money(v):
            return f"<b>$ {v:,.0f}</b>" if v is not None else "<b>$ —</b>"

        self.card_total.value_label.setText(money(total_cost))
        self.card_daily.value_label.setText(money(daily_actual))
        self.card_meter.value_label.setText(money(cpm))
        self.card_npt.value_label.setText(money(npt_cost))

        reports = self.db.get_daily_reports_by_well(self.current_well_id)
        # The chart projects the user-entered day-rate ASSUMPTION over rig days;
        # it is explicitly a projection, distinct from the actual-cost KPIs above.
        self._draw_cost_chart(reports, self.rig_rate.value() + self.spread_rate.value())

    def _draw_cost_chart(self, reports, daily_rate):
        if not reports:
            return
        try:
            import matplotlib
            matplotlib.use('Qt5Agg')
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

            days = list(range(1, len(reports) + 1))
            cum_cost = [d * daily_rate for d in days]
            depths = [r.get('depth_2400', 0) or 0 for r in reports]

            fig, ax1 = plt.subplots(figsize=(8, 4), facecolor='#f8f9fa')
            ax1.set_facecolor('#f8f9fa')

            ax1.plot(days, [c/1000 for c in cum_cost], 'r-o', lw=2, ms=3, label='Cost ($K)')
            ax1.set_xlabel("Rig Day")
            ax1.set_ylabel("Cumulative Cost ($K)", color='r')
            ax1.tick_params(axis='y', labelcolor='r')

            ax2 = ax1.twinx()
            ax2.plot(days, depths, 'b-s', lw=2, ms=3, label='Depth (m)')
            ax2.set_ylabel("Depth (m)", color='b')
            ax2.tick_params(axis='y', labelcolor='b')
            ax2.invert_yaxis()

            ax1.set_title("Cost vs Depth", fontweight='bold')
            ax1.grid(True, alpha=0.3)
            fig.tight_layout()

            canvas = FigureCanvas(fig)
            safe_replace_chart(self.cost_chart, canvas)
            plt.close(fig)
        except Exception as e:
            logger.error(f"Cost chart error: {e}")

    def _export_cost(self):
        ExportManager(self).export_table_with_dialog(self.afe_table, "cost_report")

    # ===== Persistence (canonical CostRecord truth) =====
    def _selected_currency(self):
        """Return the chosen currency code, or None when left unspecified (§9)."""
        text = self.afe_currency.currentText().strip()
        if not text or text.startswith("—"):
            return None
        return text

    def _read_afe_rows(self):
        """Read AFE worksheet rows from the table as plain dicts."""
        rows = []
        for row in range(self.afe_table.rowCount()):
            cat_item = self.afe_table.item(row, 0)
            category = cat_item.text().strip() if cat_item else ""
            pw = self.afe_table.cellWidget(row, 1)
            aw = self.afe_table.cellWidget(row, 2)
            rows.append({
                "category": category,
                "planned_cost": pw.value() if pw else None,
                "actual_cost": aw.value() if aw else None,
            })
        return rows

    def save_data(self):
        from core.save_outcome import SaveOutcome, SaveIssue
        # Enforce the standard permission contract before mutating.
        try:
            from core.permissions import permissions
            if permissions.is_viewer():
                self.show_warning("Viewer role is read-only: No Save allowed")
                return False
            if not permissions.has_permission("can_edit_reports"):
                self.show_warning("You do not have permission to edit reports")
                return False
            user_id = getattr(permissions, "user_id", None)
        except Exception:
            user_id = None

        if not self.current_well_id or not self.db:
            # No well selected: nothing was persisted. Report this HONESTLY as
            # a blocked context, never as a silent success (§2.4). Save All
            # reads last_save_outcome and will surface the real disposition.
            outcome = SaveOutcome(issues=[SaveIssue(
                "Cost (AFE)",
                "No well is selected; the AFE worksheet was not saved.",
                status="REVIEW_REQUIRED", code="CONTEXT_BLOCKED",
                corrective_action="Select a well, then save the AFE worksheet again.")])
            self.last_save_outcome = outcome
            self.show_warning("Select a well before saving the AFE worksheet")
            return outcome

        rows = [r for r in self._read_afe_rows() if r["category"]]
        try:
            saved = self.db.save_afe_worksheet(
                self.current_well_id, rows,
                afe_number=self.afe_number.text().strip() or None,
                currency=self._selected_currency(),
                user_id=user_id,
            )
            outcome = SaveOutcome(saved=saved)
            self.last_save_outcome = outcome
            self.show_success(f"Saved {saved} AFE cost line(s)")
            return outcome
        except Exception as e:
            logger.error(f"AFE save failed: {e}")
            outcome = SaveOutcome(issues=[SaveIssue(
                "Cost (AFE)", str(e), status="SYSTEM_ERROR",
                exception_type=type(e).__name__)])
            self.last_save_outcome = outcome
            self.show_error(f"AFE save failed: {e}")
            return outcome

    def _load_afe_from_db(self):
        """Reload the AFE worksheet from persisted CostRecord budget lines."""
        if not self.current_well_id or not self.db:
            return
        try:
            records = self.db.get_cost_records(self.current_well_id)
        except Exception as e:
            logger.error(f"AFE load failed: {e}")
            return
        self._mirror_planned_days()
        rows = cost_records_to_afe_rows(records)
        if not rows:
            # No persisted AFE yet — keep the current (default) worksheet.
            self._update_afe_totals()
            return
        self.afe_table.setRowCount(0)
        for r in rows:
            self._insert_afe_row(r["category"], r["planned_cost"] or 0,
                                 r["actual_cost"] or 0)
        self._update_afe_totals()

    def _mirror_planned_days(self):
        """Reflect the authoritative WellPlan planned days (read-only mirror)."""
        if not self.current_well_id or not self.db:
            return
        try:
            days = self.db.get_planned_total_days(self.current_well_id)
        except Exception:
            days = None
        self.afe_days.setValue(int(days) if days else 0)

    # ===== DrillTabBase =====
    def on_well_changed(self, well_id, well_data):
        self.current_well_id = well_id
        self.refresh()

    def refresh(self):
        self._load_afe_from_db()
        self._update_afe_totals()
        self._generate_summary()