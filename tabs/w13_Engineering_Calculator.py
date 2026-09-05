# tabs/w13_Engineering_Calculator.py
# ادغام Drilling Calculator نرم‌افزار قدیمی
"""
Engineering Calculator - ادغام شده از نرم‌افزار قبلی
تمام محاسبات حفاری در یک تب مستقل
"""
import math
import itertools
import logging
import os

import pandas as pd
import numpy as np

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from core.base_tab import DrillTabBase
from core.managers import StatusBarManager, DrillingManager
from core.common_widgets import safe_replace_chart

logger = logging.getLogger(__name__)


class DrillingCalculationEngine:
    """
    Legacy calculation facade for the Engineering Calculator tab (W13).

    No engineering formula lives here any more: every method delegates to
    the canonical engines under core/ (single source of truth) and only
    converts units / maps result shapes. See ENGINEERING_ARCHITECTURE.md.
    """

    # -------- Bit hydraulics (canonical: core/hydraulics_engine.py) --------
    @staticmethod
    def calc_pump_output(liner_size: float, stroke_len: float, efficiency: float) -> float:
        """Pump output — delegates to canonical AdvancedHydraulicsEngine."""
        from core.hydraulics_engine import AdvancedHydraulicsEngine
        return AdvancedHydraulicsEngine.calc_pump_output(
            liner_size, stroke_len, efficiency)

    @staticmethod
    def calc_tfa_from_pressure(gpm: float, mw: float, delta_p: float) -> float:
        """TFA from ΔP — canonical AdvancedHydraulicsEngine.calc_tfa_from_pressure_drop."""
        from core.hydraulics_engine import AdvancedHydraulicsEngine
        if delta_p <= 0:
            return 0
        return round(AdvancedHydraulicsEngine.calc_tfa_from_pressure_drop(gpm, mw, delta_p), 4)

    @staticmethod
    def calc_bit_hhp(gpm: float, delta_p: float) -> float:
        """Bit HHP — canonical AdvancedHydraulicsEngine.calc_bit_hhp."""
        from core.hydraulics_engine import AdvancedHydraulicsEngine
        return round(AdvancedHydraulicsEngine.calc_bit_hhp(gpm, delta_p), 2)

    @staticmethod
    def calc_jet_velocity(gpm: float, nozzle_sizes: list) -> float:
        """Jet velocity — canonical AdvancedHydraulicsEngine.calc_jet_velocity.

        TFA is computed by the canonical BitEngine.calculate_tfa
        (Σ π/4·(size/32)²) — never re-implemented here.
        """
        from core.hydraulics_engine import AdvancedHydraulicsEngine
        from core.engineering.core import BitEngine
        sizes = [s for s in nozzle_sizes if s > 0]
        if not sizes or gpm <= 0:
            return 0.0
        tfa = BitEngine.calculate_tfa(sizes)
        return round(AdvancedHydraulicsEngine.calc_jet_velocity(gpm, tfa), 2)

    @staticmethod
    def calc_impact_force(gpm: float, mw: float, jet_velocity: float) -> float:
        """Impact force — canonical AdvancedHydraulicsEngine.calc_impact_force."""
        from core.hydraulics_engine import AdvancedHydraulicsEngine
        return round(AdvancedHydraulicsEngine.calc_impact_force(mw, gpm, jet_velocity), 2)

    # -------- Nozzle Optimization (canonical: AdvancedHydraulicsEngine) --------
    @staticmethod
    def optimize_nozzles(
        hhp: float, max_press: float,
        fr1: float, spp1: float, fr2: float, spp2: float,
        prev_tfa: float, mw: float, n_nozzles: int,
        model: str = "HP"
    ) -> dict:
        """Legacy wrapper — delegates to canonical
        AdvancedHydraulicsEngine.optimize_nozzles()."""
        from core.hydraulics_engine import AdvancedHydraulicsEngine
        return AdvancedHydraulicsEngine.optimize_nozzles(
            hhp=hhp, max_press=max_press, fr1=fr1, spp1=spp1, fr2=fr2,
            spp2=spp2, prev_tfa=prev_tfa, mw_ppg=mw, n_nozzles=n_nozzles,
            model=model)

    # -------- Fishing / Stuck-pipe (canonical: FishingEngine) --------
    @staticmethod
    def calc_free_point(diff_stretch: float, pipe_wt: float, pull_force: float) -> float:
        """Free point (ft) — canonical FishingEngine.free_point."""
        from core.engineering.engines.fishing import calculate_free_point
        return calculate_free_point(diff_stretch, pipe_wt, pull_force)

    @staticmethod
    def calc_string_stretch(length: float, mw: float) -> float:
        """String stretch (in) — canonical FishingEngine.string_stretch."""
        from core.engineering.engines.fishing import calculate_string_stretch
        return calculate_string_stretch(length, mw)

    @staticmethod
    def calc_adjusted_weight(od: float, id_: float) -> float:
        """Adjusted pipe weight (lb/ft) — canonical FishingEngine.adjusted_weight."""
        from core.engineering.engines.fishing import FishingEngine
        r = FishingEngine.adjusted_weight(od, id_)
        return r.value if r.success else 0.0

    @staticmethod
    def calc_buoyancy_factor(mud_weight_pcf, steel_density=490) -> float:
        """Buoyancy factor — canonical TorqueDragEngine.buoyancy_factor.

        Input is pcf; converted to ppg at this boundary (unit conversion
        only — the formula lives in the engine).
        """
        from core.engineering.engines.torque_drag import TorqueDragEngine
        if not mud_weight_pcf or mud_weight_pcf <= 0:
            return 0.0
        mw_ppg = mud_weight_pcf / 7.48
        steel_ppg = steel_density / 7.48
        try:
            return round(TorqueDragEngine.buoyancy_factor(mw_ppg, steel_ppg), 4)
        except Exception:
            return 0.0

    @staticmethod
    def calc_casing_landing_load(casing_weight_ppf, length_ft,
                                   buoyancy_factor, friction_factor=0) -> dict:
        """Casing landing-load card — arithmetic on engine outputs
        (canonical buoyancy factor is supplied by the caller); no
        engineering constants live here."""
        air_weight = casing_weight_ppf * length_ft
        buoyant_weight = air_weight * buoyancy_factor
        friction_load = buoyant_weight * friction_factor
        hook_load = buoyant_weight - friction_load

        return {
            "air_weight_lbs": round(air_weight, 0),
            "buoyant_weight_lbs": round(buoyant_weight, 0),
            "friction_load_lbs": round(friction_load, 0),
            "hook_load_lbs": round(hook_load, 0),
        }

    # -------- Well Control (canonical: WellControlEngine) --------
    @staticmethod
    def calc_kick_tolerance(frac_mw_ppg, current_mw_ppg, tvd_ft,
                             shoe_tvd_ft, annular_vol_bbl,
                             influx_gradient_psi_ft=None,
                             annular_capacity_bbl_ft=None,
                             formation_emw_ppg=None) -> dict:
        """Kick tolerance — canonical WellControlEngine.kick_tolerance.

        No invented influx gradient or annular capacity: missing inputs
        produce an error dict instead of a guessed number.
        """
        from core.engineering.engines.well_control import WellControlEngine
        r = WellControlEngine.kick_tolerance(
            mw_ppg=current_mw_ppg,
            shoe_tvd_ft=shoe_tvd_ft,
            current_tvd_ft=tvd_ft,
            frac_mw_ppg=frac_mw_ppg,
            influx_gradient_psi_ft=influx_gradient_psi_ft,
            annular_capacity_bbl_ft=annular_capacity_bbl_ft,
            formation_emw_ppg=formation_emw_ppg,
        )
        if not r.success:
            return {"error": r.error}
        return r.values

    @staticmethod
    def calc_formation_pressure(mw_pcf, tvd_ft, sidpp) -> dict:
        """Formation pressure card — canonical
        WellControlEngine.formation_pressure (pcf → ppg conversion here).

        Legacy output keys/shapes preserved. When TVD is missing the card
        returns zeroed fields (legacy behaviour) instead of guessing.
        """
        from core.engineering.engines.well_control import WellControlEngine
        mw_ppg = mw_pcf / 7.48
        r = WellControlEngine.formation_pressure(
            mw_ppg=mw_ppg, tvd_ft=tvd_ft, sidpp_psi=sidpp)
        if not r.success:
            return {
                "hydrostatic_psi": 0.0,
                "formation_pressure_psi": round(float(sidpp or 0), 0),
                "pressure_gradient_psi_ft": 0.0,
                "equivalent_mw_ppg": 0.0,
                "equivalent_mw_pcf": 0.0,
            }
        v = r.values
        return {
            "hydrostatic_psi": round(v["hydrostatic_psi"], 0),
            "formation_pressure_psi": round(v["formation_pressure_psi"], 0),
            "pressure_gradient_psi_ft": round(v["pressure_gradient_psi_ft"], 4),
            "equivalent_mw_ppg": round(v["equivalent_mw_ppg"], 2),
            "equivalent_mw_pcf": round(v["equivalent_mw_ppg"] * 7.48, 2),
        }

    # -------- Directional (canonical: TrajectoryEngine) --------
    @staticmethod
    def calc_build_rate(initial_inc, final_inc, md_interval) -> float:
        """Build rate (°/30 m) — canonical TrajectoryEngine.calculate_build_rate."""
        from core.engineering.core import TrajectoryEngine
        if md_interval <= 0:
            return 0.0
        return round(TrajectoryEngine.calculate_build_rate(
            initial_inc, final_inc, md_interval), 2)

    @staticmethod
    def calc_turn_rate(initial_azi, final_azi, md_interval) -> float:
        """Turn rate (°/30 m) — canonical TrajectoryEngine.calculate_turn_rate
        (shortest azimuth change, same wrap as the survey engine)."""
        from core.engineering.core import TrajectoryEngine
        if md_interval <= 0:
            return 0.0
        return round(TrajectoryEngine.calculate_turn_rate(
            initial_azi, final_azi, md_interval), 2)

    # -------- Fishing sizing rules (canonical: FishingEngine) --------
    @staticmethod
    def calc_fish_neck_ot(fish_od, overshot_id) -> dict:
        """Overshot sizing — canonical FishingEngine.overshot_fit."""
        from core.engineering.engines.fishing import FishingEngine
        r = FishingEngine.overshot_fit(fish_od, overshot_id)
        if not r.success:
            return {"clearance_in": 0.0, "compatible": False, "recommendation": "Check sizing"}
        return {
            "clearance_in": r.values["clearance_in"],
            "compatible": r.values["compatible"],
            "recommendation": r.values["recommendation"],
        }

    @staticmethod
    def calc_jar_operating_range(string_weight_lbs, buoyancy_factor,
                                  overpull_lbs) -> dict:
        """Jar range — canonical FishingEngine.jar_operating_range."""
        from core.engineering.engines.fishing import FishingEngine
        r = FishingEngine.jar_operating_range(
            string_weight_lbs, buoyancy_factor, overpull_lbs)
        if not r.success:
            return {"error": r.error}
        return r.values

    @staticmethod
    def calc_backoff_depth(stretch_in, pipe_weight_ppf,
                            modulus=30e6) -> float:
        """Back-off free point (ft) — canonical FishingEngine.backoff_depth."""
        from core.engineering.engines.fishing import calculate_backoff_depth
        if pipe_weight_ppf <= 0:
            return 0.0
        r = calculate_backoff_depth(stretch_in, pipe_weight_ppf)
        return round(r, 1)

    # -------- Mud (canonical: MudVolumeEngine / MudEngineering) --------
    @staticmethod
    def calc_mud_weight_increase(current_mw, target_mw, system_vol,
                                 additive_density=None) -> dict:
        """Weight-up — canonical MudVolumeEngine.weight_up (additive required)."""
        from core.engineering.engines.mud_volume import MudVolumeEngine
        r = MudVolumeEngine.weight_up(current_mw, target_mw, system_vol, additive_density)
        if not r.success:
            return {"error": r.error}
        return {
            "sacks_barite": r.values["sacks"],
            "volume_increase_bbl": r.values["volume_increase_bbl"],
            "final_volume_bbl": r.values["final_volume_bbl"],
        }

    @staticmethod
    def calc_mud_dilution(current_mw, target_mw, system_vol,
                          dilutant_mw=None) -> dict:
        """Dilution — canonical MudVolumeEngine.dilution (dilutant required)."""
        from core.engineering.engines.mud_volume import MudVolumeEngine
        r = MudVolumeEngine.dilution(current_mw, target_mw, system_vol, dilutant_mw)
        if not r.success:
            return {"error": r.error}
        return {
            "water_required_bbl": r.values["water_required_bbl"],
            "final_volume_bbl": r.values["final_volume_bbl"],
        }

    @staticmethod
    def calc_mud_mixing(mw1, vol1, mw2, vol2) -> dict:
        """Mixing — canonical MudVolumeEngine.mix."""
        from core.engineering.engines.mud_volume import MudVolumeEngine
        r = MudVolumeEngine.mix(mw1, vol1, mw2, vol2)
        if not r.success:
            return {"error": r.error}
        return {
            "final_mw_pcf": r.values["final_mw"],
            "total_volume_bbl": r.values["total_volume"],
        }

    @staticmethod
    def calc_oil_water_ratio(oil_percent, water_percent) -> dict:
        """OWR — canonical MudEngineering.oil_water_ratio."""
        from core.engineering.extended import MudEngineering
        try:
            r = MudEngineering.oil_water_ratio(oil_percent, water_percent)
        except Exception as exc:
            return {"error": str(exc)}
        return {
            "oil_ratio": r["oil_percent"],
            "water_ratio": r["water_percent"],
            "OWR": r["owr"].replace(":", "/"),
        }


# ==================== UI TAB ====================
class EngineeringCalculatorTab(DrillTabBase):
    """
    تب ماشین حساب مهندسی - ادغام شده از نرم‌افزار قبلی
    """

    def __init__(self, db_manager=None, parent=None):
        super().__init__("EngineeringCalculatorTab", db_manager, parent)
        self.engine = DrillingCalculationEngine()
        self.current_well_id = None
        self._drill_pipe_df = None
        self.init_ui()
        self._load_drill_pipe_db()

    def _load_drill_pipe_db(self):
        """بارگذاری دیتابیس DrillPipe از فایل Excel"""
        possible_paths = [
            "DrillPipe.xlsx",
            "data/DrillPipe.xlsx",
            "resources/DrillPipe.xlsx",
            os.path.join(os.path.dirname(__file__), "DrillPipe.xlsx"),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                try:
                    self._drill_pipe_df = pd.read_excel(path, sheet_name="Aa", engine="openpyxl")
                    logger.info(f"DrillPipe.xlsx loaded from {path}")
                    return
                except Exception as e:
                    logger.warning(f"Could not load DrillPipe.xlsx: {e}")
        logger.warning("DrillPipe.xlsx not found - table will be empty")

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Header
        header = QLabel("⚙️ Drilling Engineering Calculator")
        header.setStyleSheet("""
            QLabel {
                font-size: 16px; font-weight: bold;
                color: #ecf0f1; padding: 8px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2c3e50, stop:1 #34495e);
                border-radius: 5px;
                border: none;
            }
        """)
        main_layout.addWidget(header)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { background: #2a2d44; border: 1px solid #444; }
            QTabBar::tab {
                background: #2e3250; color: white;
                padding: 8px 16px; font-size: 11px; font-weight: bold;
            }
            QTabBar::tab:selected { background: #3498db; }
            QTabBar::tab:hover { background: #41476e; }
        """)

        self.tabs.addTab(self._create_volume_tab(), "📊 Volume")
        self.tabs.addTab(self._create_hydraulics_tab(), "💧 Hydraulics")
        self.tabs.addTab(self._create_bit_tab(), "🔵 Bit Hydraulics")
        self.tabs.addTab(self._create_weight_tab(), "⚖️ Weight")
        self.tabs.addTab(self._create_stuck_tab(), "🔴 Stuck Pipe")
        self.tabs.addTab(self._create_mud_tab(), "🧪 Mud")
        self.tabs.addTab(self._create_casing_cement_tab(), "🛢️ CSG/CMT")
        self.tabs.addTab(self._create_well_control_tab(), "🛡️ Well Control")
        self.tabs.addTab(self._create_directional_tab(), "🧭 Directional")
        self.tabs.addTab(self._create_fishing_tab(), "🎣 Fishing")
        self.tabs.addTab(self._create_dp_table_tab(), "📋 DP Database")


        main_layout.addWidget(self.tabs)

    # ==================== Tab Creators ====================

    def _create_volume_tab(self) -> QWidget:
        """تب حجم - حرفه‌ای با دیالوگ"""
        self.vol_pumps = []
        self.vol_pipes = []
        self.vol_casings = []

        tab, container, layout = self._make_scroll_tab()

        inner_tabs = QTabWidget()
        layout.addWidget(inner_tabs)

        # ===== Sub-tab 1: Quick Capacity/Displacement =====
        cap_tab = QWidget()
        cap_layout = QVBoxLayout(cap_tab)

        g1 = QGroupBox("🔩 Quick Pipe Capacity & Displacement")
        f1 = QFormLayout(g1)

        self.v_od = self._make_dspin(5.0, 0, 200, 3, " in")
        self.v_id = self._make_dspin(4.276, 0, 200, 3, " in")
        self.v_length = self._make_dspin(1000, 0, 20000, 1, " m")

        f1.addRow("OD:", self.v_od)
        f1.addRow("ID:", self.v_id)
        f1.addRow("Length:", self.v_length)

        # Quick select button
        quick_btn = QPushButton("📋 Select from Database")
        quick_btn.setStyleSheet("background: #3498db; color: white; padding: 5px; border-radius: 3px; border: none;")
        quick_btn.clicked.connect(self._vol_quick_select_pipe)
        f1.addRow(quick_btn)

        self.v_cap = self._result_label("#2ecc71")
        self.v_dis = self._result_label("#3498db")
        self.v_vol = self._result_label("#e67e22")
        self.v_weight = self._result_label("#9b59b6")

        f1.addRow("Capacity:", self.v_cap)
        f1.addRow("Displacement:", self.v_dis)
        f1.addRow("Volume:", self.v_vol)
        f1.addRow("Metal Volume:", self.v_weight)

        cap_layout.addWidget(g1)

        # Annular
        g2 = QGroupBox("🌊 Annular Capacity")
        f2 = QFormLayout(g2)
        self.v_hole = self._make_dspin(8.5, 0, 50, 3, " in")
        self.v_pipe_od = self._make_dspin(5.0, 0, 50, 3, " in")
        self.v_ann_len = self._make_dspin(1000, 0, 20000, 1, " m")
        f2.addRow("Hole/CSG ID:", self.v_hole)
        f2.addRow("Pipe OD:", self.v_pipe_od)
        f2.addRow("Length:", self.v_ann_len)

        self.v_ann_cap = self._result_label("#1abc9c")
        self.v_ann_vol = self._result_label("#e74c3c")
        f2.addRow("Ann. Capacity:", self.v_ann_cap)
        f2.addRow("Ann. Volume:", self.v_ann_vol)

        cap_layout.addWidget(g2)
        cap_layout.addStretch()

        # Auto-calculate connections
        for w in [self.v_od, self.v_id, self.v_length]:
            w.valueChanged.connect(self._vol_update_quick)
        for w in [self.v_hole, self.v_pipe_od, self.v_ann_len]:
            w.valueChanged.connect(self._vol_update_annular)

        self._vol_update_quick()
        self._vol_update_annular()

        inner_tabs.addTab(cap_tab, "🔩 Quick Calc")

        # ===== Sub-tab 2: Full Well Volume (with dialogs) =====
        wv_tab = QWidget()
        wv_layout = QVBoxLayout(wv_tab)

        # Splitter
        wv_splitter = QSplitter(Qt.Horizontal)

        # LEFT: Input
        wv_left = QWidget()
        wv_left.setMaximumWidth(480)
        wv_ll = QVBoxLayout(wv_left)
        wv_ll.setSpacing(4)

        # --- Pumps ---
        gp = QGroupBox("💧 Mud Pumps")
        gp_lay = QVBoxLayout(gp)
        gp_btns = QHBoxLayout()
        add_p = QPushButton("➕ Add Pump")
        add_p.setStyleSheet("background: #27ae60; color: white; padding: 4px 10px; border-radius: 3px; border: none;")
        add_p.clicked.connect(self._vol_add_pump)
        edit_p = QPushButton("✏️")
        edit_p.setFixedWidth(30)
        edit_p.clicked.connect(self._vol_edit_pump)
        rem_p = QPushButton("🗑️")
        rem_p.setFixedWidth(30)
        rem_p.clicked.connect(self._vol_rem_pump)
        gp_btns.addWidget(add_p)
        gp_btns.addWidget(edit_p)
        gp_btns.addWidget(rem_p)
        gp_btns.addStretch()
        gp_lay.addLayout(gp_btns)

        self.vol_pump_table = QTableWidget(0, 5)
        self.vol_pump_table.setHorizontalHeaderLabels(["Name", "Liner", "SPM", "Output(bbl/stk)", "GPM"])
        self.vol_pump_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.vol_pump_table.setMaximumHeight(90)
        self.vol_pump_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.vol_pump_table.setSelectionBehavior(QTableWidget.SelectRows)
        gp_lay.addWidget(self.vol_pump_table)

        self.vol_total_gpm = QLabel("Total: 0 gpm")
        self.vol_total_gpm.setStyleSheet("font-weight: bold; color: #3498db; padding: 2px;")
        gp_lay.addWidget(self.vol_total_gpm)
        wv_ll.addWidget(gp)

        # --- Drill String ---
        gds = QGroupBox("🔩 Drill String")
        gds_lay = QVBoxLayout(gds)
        ds_btns = QHBoxLayout()
        add_ds = QPushButton("➕ Add Component")
        add_ds.setStyleSheet("background: #27ae60; color: white; padding: 4px 10px; border-radius: 3px; border: none;")
        add_ds.clicked.connect(self._vol_add_pipe)
        edit_ds = QPushButton("✏️")
        edit_ds.setFixedWidth(30)
        edit_ds.clicked.connect(self._vol_edit_pipe)
        rem_ds = QPushButton("🗑️")
        rem_ds.setFixedWidth(30)
        rem_ds.clicked.connect(self._vol_rem_pipe)
        ds_btns.addWidget(add_ds)
        ds_btns.addWidget(edit_ds)
        ds_btns.addWidget(rem_ds)
        ds_btns.addStretch()
        gds_lay.addLayout(ds_btns)

        self.vol_pipe_table = QTableWidget(0, 5)
        self.vol_pipe_table.setHorizontalHeaderLabels(["Type", "OD", "ID", "Length(m)", "Cap(bbl)"])
        self.vol_pipe_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.vol_pipe_table.setMaximumHeight(140)
        self.vol_pipe_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.vol_pipe_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.vol_pipe_table.doubleClicked.connect(self._vol_edit_pipe)
        gds_lay.addWidget(self.vol_pipe_table)
        wv_ll.addWidget(gds)

        # --- Casing/Wellbore ---
        gcsg = QGroupBox("🛢️ Casing / Wellbore")
        gcsg_lay = QVBoxLayout(gcsg)
        csg_btns = QHBoxLayout()
        add_csg = QPushButton("➕ Add Section")
        add_csg.setStyleSheet("background: #27ae60; color: white; padding: 4px 10px; border-radius: 3px; border: none;")
        add_csg.clicked.connect(self._vol_add_casing)
        edit_csg = QPushButton("✏️")
        edit_csg.setFixedWidth(30)
        edit_csg.clicked.connect(self._vol_edit_casing)
        rem_csg = QPushButton("🗑️")
        rem_csg.setFixedWidth(30)
        rem_csg.clicked.connect(self._vol_rem_casing)
        csg_btns.addWidget(add_csg)
        csg_btns.addWidget(edit_csg)
        csg_btns.addWidget(rem_csg)
        csg_btns.addStretch()
        gcsg_lay.addLayout(csg_btns)

        self.vol_csg_table = QTableWidget(0, 5)
        self.vol_csg_table.setHorizontalHeaderLabels(["Type", "OD/Hole", "ID", "From(m)", "To(m)"])
        self.vol_csg_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.vol_csg_table.setMaximumHeight(120)
        self.vol_csg_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.vol_csg_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.vol_csg_table.doubleClicked.connect(self._vol_edit_casing)
        gcsg_lay.addWidget(self.vol_csg_table)
        wv_ll.addWidget(gcsg)

        # --- Well Data ---
        gwd = QGroupBox("📏 Well Data")
        wd_f = QFormLayout(gwd)
        self.vol_depth = self._make_dspin(3000, 0, 20000, 0, " m")
        self.vol_loss = self._make_dspin(0, 0, 1000, 1, " bbl/hr")
        wd_f.addRow("Bit Depth:", self.vol_depth)
        wd_f.addRow("Loss Rate:", self.vol_loss)
        wv_ll.addWidget(gwd)

        # Calculate button
        calc_btn = QPushButton("🔄 Calculate Well Volumes")
        calc_btn.setStyleSheet("background: #e74c3c; color: white; font-weight: bold; padding: 10px; border-radius: 5px; border: none; font-size: 13px;")
        calc_btn.clicked.connect(self._vol_calculate)
        wv_ll.addWidget(calc_btn)
        wv_ll.addStretch()

        wv_splitter.addWidget(wv_left)

        # RIGHT: Results
        wv_right = QWidget()
        wv_rl = QVBoxLayout(wv_right)

        # KPI Cards
        cards = QWidget()
        cl = QHBoxLayout(cards)
        cl.setContentsMargins(0, 0, 0, 0)
        self.vol_card_string = self._make_card("String Vol", "0", "bbl", "#3498db")
        self.vol_card_annular = self._make_card("Annular Vol", "0", "bbl", "#e67e22")
        self.vol_card_total = self._make_card("Total Vol", "0", "bbl", "#27ae60")
        self.vol_card_lag = self._make_card("Lag Time", "0", "min", "#9b59b6")
        cl.addWidget(self.vol_card_string)
        cl.addWidget(self.vol_card_annular)
        cl.addWidget(self.vol_card_total)
        cl.addWidget(self.vol_card_lag)
        wv_rl.addWidget(cards)

        # Results detail
        self.vol_results = QTextEdit()
        self.vol_results.setReadOnly(True)
        self.vol_results.setStyleSheet("background: #1e1e2e; color: #ecf0f1; font-family: Consolas; font-size: 12px;")
        wv_rl.addWidget(self.vol_results)

        wv_splitter.addWidget(wv_right)
        wv_splitter.setSizes([420, 500])
        wv_layout.addWidget(wv_splitter)

        inner_tabs.addTab(wv_tab, "🛢️ Well Volumes")

        return tab
        
    # ========== Volume - Quick Calc ==========

    def _result_label(self, color="#2c3e50"):
        lbl = QLabel("--")
        lbl.setStyleSheet(
            f"font-weight: bold; color: {color}; padding: 5px; "
            f"border: 1px solid {color}; border-radius: 3px; font-size: 11px;"
        )
        return lbl

    def _vol_quick_select_pipe(self):
        """انتخاب سریع لوله از دیتابیس"""
        from dialogs.engineering_dialogs import AddPipeDialog
        dlg = AddPipeDialog(self)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                self.v_od.setValue(data['od'])
                self.v_id.setValue(data['id'])
                if data.get('length', 0) > 0:
                    self.v_length.setValue(data['length'])

    def _vol_update_quick(self):
        """آپدیت محاسبات سریع"""
        od = self.v_od.value()
        id_ = self.v_id.value()
        L = self.v_length.value()
        from core.hydraulics_engine import AdvancedHydraulicsEngine as A

        if od > id_ > 0:
            cap_ft = A.calc_pipe_capacity_bbl_ft(id_)
            dis_ft = A.calc_pipe_displacement_bbl_ft(od, id_)
            cap = cap_ft * 3.28084      # bbl/m  (unit conversion of canonical bbl/ft)
            dis = dis_ft * 3.28084      # bbl/m
            self.v_cap.setText(f"{cap:.5f} bbl/m  |  {cap_ft:.5f} bbl/ft")
            self.v_dis.setText(f"{dis:.5f} bbl/m  |  {dis_ft:.5f} bbl/ft")
            if L > 0:
                vol = cap * L
                metal = dis * L
                self.v_vol.setText(f"{vol:.2f} bbl  (for {L:.0f} m)")
                self.v_weight.setText(f"{metal:.2f} bbl  (metal displacement)")
            else:
                self.v_vol.setText("-- (enter length)")
                self.v_weight.setText("--")
        else:
            self.v_cap.setText("❌ OD must > ID")
            self.v_dis.setText("")

    def _vol_update_annular(self):
        """آپدیت محاسبات آنولوس"""
        hole = self.v_hole.value()
        pipe = self.v_pipe_od.value()
        L = self.v_ann_len.value()
        from core.hydraulics_engine import AdvancedHydraulicsEngine as A

        if hole > pipe > 0:
            ann_cap_ft = A.calc_annular_capacity_bbl_ft(hole, pipe)
            ann_cap = ann_cap_ft * 3.28084   # bbl/m
            self.v_ann_cap.setText(f"{ann_cap:.5f} bbl/m  |  {ann_cap_ft:.5f} bbl/ft")
            if L > 0:
                ann_vol = ann_cap * L
                self.v_ann_vol.setText(f"{ann_vol:.2f} bbl  (for {L:.0f} m)")
            else:
                self.v_ann_vol.setText("-- (enter length)")
        else:
            self.v_ann_cap.setText("❌ Hole must > Pipe OD")

    # ========== Volume - Pump Dialog ==========

    def _vol_add_pump(self):
        from dialogs.engineering_dialogs import AddPumpDialog
        dlg = AddPumpDialog(self)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                self.vol_pumps.append(data)
                self._vol_refresh_pump_table()

    def _vol_edit_pump(self):
        row = self.vol_pump_table.currentRow()
        if 0 <= row < len(self.vol_pumps):
            from dialogs.engineering_dialogs import AddPumpDialog
            dlg = AddPumpDialog(self, edit_data=self.vol_pumps[row])
            if dlg.exec():
                data = dlg.get_result()
                if data:
                    self.vol_pumps[row] = data
                    self._vol_refresh_pump_table()

    def _vol_rem_pump(self):
        row = self.vol_pump_table.currentRow()
        if 0 <= row < len(self.vol_pumps):
            self.vol_pumps.pop(row)
            self._vol_refresh_pump_table()

    def _vol_refresh_pump_table(self):
        self.vol_pump_table.setRowCount(0)
        total_gpm = 0
        for p in self.vol_pumps:
            row = self.vol_pump_table.rowCount()
            self.vol_pump_table.insertRow(row)
            output = p.get('output_bbl_stk', 0)
            spm = p.get('spm', 0)
            gpm = output * spm * 42
            total_gpm += gpm

            self.vol_pump_table.setItem(row, 0, QTableWidgetItem(p.get('name', '')))
            self.vol_pump_table.setItem(row, 1, QTableWidgetItem(f"{p.get('liner', 0):.1f}\""))
            self.vol_pump_table.setItem(row, 2, QTableWidgetItem(f"{spm:.0f}"))
            self.vol_pump_table.setItem(row, 3, QTableWidgetItem(f"{output:.5f}"))
            gi = QTableWidgetItem(f"{gpm:.1f}")
            gi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.vol_pump_table.setItem(row, 4, gi)

        self.vol_total_gpm.setText(f"Total Flow Rate: {total_gpm:.1f} gpm")

    # ========== Volume - Pipe Dialog ==========

    def _vol_add_pipe(self):
        from dialogs.engineering_dialogs import AddPipeDialog
        dlg = AddPipeDialog(self)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                self.vol_pipes.append(data)
                self._vol_refresh_pipe_table()

    def _vol_edit_pipe(self):
        row = self.vol_pipe_table.currentRow()
        if 0 <= row < len(self.vol_pipes):
            from dialogs.engineering_dialogs import AddPipeDialog
            dlg = AddPipeDialog(self, edit_data=self.vol_pipes[row])
            if dlg.exec():
                data = dlg.get_result()
                if data:
                    self.vol_pipes[row] = data
                    self._vol_refresh_pipe_table()

    def _vol_rem_pipe(self):
        row = self.vol_pipe_table.currentRow()
        if 0 <= row < len(self.vol_pipes):
            self.vol_pipes.pop(row)
            self._vol_refresh_pipe_table()

    def _vol_refresh_pipe_table(self):
        self.vol_pipe_table.setRowCount(0)
        from core.hydraulics_engine import AdvancedHydraulicsEngine as A
        for p in self.vol_pipes:
            row = self.vol_pipe_table.rowCount()
            self.vol_pipe_table.insertRow(row)
            id_ = p.get('id', 0)
            L = p.get('length', 0)
            cap_bbl = (A.calc_pipe_capacity_bbl_ft(id_) * (L * 3.28084)
                       if id_ > 0 and L > 0 else 0)

            self.vol_pipe_table.setItem(row, 0, QTableWidgetItem(p.get('type', '')))
            self.vol_pipe_table.setItem(row, 1, QTableWidgetItem(f"{p.get('od', 0):.3f}\""))
            self.vol_pipe_table.setItem(row, 2, QTableWidgetItem(f"{id_:.3f}\""))
            self.vol_pipe_table.setItem(row, 3, QTableWidgetItem(f"{L:.1f}"))
            ci = QTableWidgetItem(f"{cap_bbl:.2f}")
            ci.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.vol_pipe_table.setItem(row, 4, ci)

    # ========== Volume - Casing Dialog ==========

    def _vol_add_casing(self):
        from dialogs.engineering_dialogs import AddCasingDialog
        dlg = AddCasingDialog(self)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                self.vol_casings.append(data)
                self._vol_refresh_csg_table()

    def _vol_edit_casing(self):
        row = self.vol_csg_table.currentRow()
        if 0 <= row < len(self.vol_casings):
            from dialogs.engineering_dialogs import AddCasingDialog
            dlg = AddCasingDialog(self, edit_data=self.vol_casings[row])
            if dlg.exec():
                data = dlg.get_result()
                if data:
                    self.vol_casings[row] = data
                    self._vol_refresh_csg_table()

    def _vol_rem_casing(self):
        row = self.vol_csg_table.currentRow()
        if 0 <= row < len(self.vol_casings):
            self.vol_casings.pop(row)
            self._vol_refresh_csg_table()

    def _vol_refresh_csg_table(self):
        self.vol_csg_table.setRowCount(0)
        for c in self.vol_casings:
            row = self.vol_csg_table.rowCount()
            self.vol_csg_table.insertRow(row)
            self.vol_csg_table.setItem(row, 0, QTableWidgetItem(c.get('type', '')))
            self.vol_csg_table.setItem(row, 1, QTableWidgetItem(f"{c.get('od', 0):.3f}\""))
            self.vol_csg_table.setItem(row, 2, QTableWidgetItem(f"{c.get('id', 0):.3f}\""))
            self.vol_csg_table.setItem(row, 3, QTableWidgetItem(f"{c.get('from', 0):.1f}"))
            self.vol_csg_table.setItem(row, 4, QTableWidgetItem(f"{c.get('to', 0):.1f}"))

    # ========== Volume - Calculate ==========

    def _vol_calculate(self):
        """محاسبه حجم‌های چاه"""
        from core.hydraulics_engine import AdvancedHydraulicsEngine as A
        bit_depth = self.vol_depth.value()
        loss_rate = self.vol_loss.value()

        # Flow rate
        total_gpm = sum(
            p.get('output_bbl_stk', 0) * p.get('spm', 0) * 42
            for p in self.vol_pumps
        )

        # String volumes
        total_string = 0
        string_details = []
        for p in self.vol_pipes:
            id_ = p.get('id', 0)
            L = p.get('length', 0)
            vol = (A.calc_pipe_capacity_bbl_ft(id_) * (L * 3.28084)
                   if id_ > 0 and L > 0 else 0)
            total_string += vol
            string_details.append((p.get('type', ''), vol))

        # Annular volumes
        total_annular = 0
        annular_details = []

        for p in self.vol_pipes:
            pipe_od = p.get('od', 0)
            pipe_len = p.get('length', 0)

            for c in self.vol_casings:
                csg_id = c.get('id', 0)
                csg_from = c.get('from', 0)
                csg_to = c.get('to', 0)

                if csg_id <= pipe_od or pipe_len <= 0:
                    continue

                # Overlap calculation
                overlap_len = min(pipe_len, csg_to - csg_from)
                if overlap_len <= 0:
                    continue

                ann_vol = (A.calc_annular_capacity_bbl_ft(csg_id, pipe_od)
                           * (overlap_len * 3.28084))
                total_annular += ann_vol
                annular_details.append((
                    f"{p.get('type', '')} in {c.get('type', '')}",
                    ann_vol
                ))

        total_vol = total_string + total_annular

        # Lag time + bottoms-up strokes — canonical (AdvancedHydraulicsEngine)
        lag_time = A.calc_lag_time(total_annular, total_gpm)

        total_output = sum(p.get('output_bbl_stk', 0) for p in self.vol_pumps)
        bu_strokes = A.calc_bottoms_up_strokes(total_annular, total_output)

        # Cards
        self._update_card(self.vol_card_string, f"{total_string:.1f}", "bbl")
        self._update_card(self.vol_card_annular, f"{total_annular:.1f}", "bbl")
        self._update_card(self.vol_card_total, f"{total_vol:.1f}", "bbl")
        self._update_card(self.vol_card_lag, f"{lag_time:.1f}", "min")

        # Detailed results
        text = "╔═══════════════════════════════════════════╗\n"
        text += "║         WELL VOLUME CALCULATIONS          ║\n"
        text += "╠═══════════════════════════════════════════╣\n\n"

        # Pump info
        text += "💧 PUMP OUTPUT:\n"
        for p in self.vol_pumps:
            output = p.get('output_bbl_stk', 0)
            spm = p.get('spm', 0)
            gpm = output * spm * 42
            text += f"  {p.get('name', 'Pump')}: {output:.5f} bbl/stk × {spm:.0f} spm = {gpm:.1f} gpm\n"
        text += f"  TOTAL FLOW RATE: {total_gpm:.1f} gpm\n\n"

        # String volumes
        text += "🔩 STRING VOLUMES (Inside pipe):\n"
        for name, vol in string_details:
            text += f"  {name:<25} {vol:>8.2f} bbl\n"
        text += f"  {'TOTAL STRING:':<25} {total_string:>8.2f} bbl\n\n"

        # Annular volumes
        text += "🌊 ANNULAR VOLUMES:\n"
        for name, vol in annular_details:
            text += f"  {name:<35} {vol:>8.2f} bbl\n"
        text += f"  {'TOTAL ANNULAR:':<35} {total_annular:>8.2f} bbl\n\n"

        # Totals
        text += "═══════════════════════════════════════════\n"
        text += f"  {'TOTAL WELL VOLUME:':<25} {total_vol:>8.2f} bbl\n"
        text += f"  {'Lag Time:':<25} {lag_time:>8.1f} min\n"
        text += f"  {'Bottoms Up Strokes:':<25} {bu_strokes:>8.0f} stk\n"

        if loss_rate > 0:
            text += f"\n  ⚠️ Loss Rate: {loss_rate:.1f} bbl/hr\n"

        text += "\n╚═══════════════════════════════════════════╝"

        self.vol_results.setText(text)
        
    def _create_hydraulics_tab(self) -> QWidget:
        """تب هیدرولیک پیشرفته با دیالوگ‌ها"""
        from core.hydraulics_engine import (
            AdvancedHydraulicsEngine, PipeSegment, CasingSection,
            BitNozzle, MudProperties, SurfaceEquipment, WellProfile
        )

        self.adv_engine = AdvancedHydraulicsEngine()
        self.hy_result = None
        self.hy_pumps = []  # لیست پمپ‌ها

        tab, container, layout = self._make_scroll_tab()

        # Toolbar
        tb = QWidget()
        tb.setStyleSheet("background: #34495e; border-radius: 4px;")
        tb.setMaximumHeight(40)
        tb_lay = QHBoxLayout(tb)
        tb_lay.setContentsMargins(8, 3, 8, 3)

        self.hy_model = QComboBox()
        self.hy_model.addItems(["Bingham Plastic", "Power Law", "Herschel-Bulkley"])
        self.hy_model.setStyleSheet("background: #2c3e50; color: white; padding: 4px; border-radius: 3px;")
        tb_lay.addWidget(QLabel("<span style='color:#bdc3c7'>Model:</span>"))
        tb_lay.addWidget(self.hy_model)
        tb_lay.addStretch()

        for text, icon, slot, color in [
            ("🔄 Calculate", "", "_hy_run_calc", "#27ae60"),
            ("📉 Surge/Swab", "", "_hy_surge_dialog", "#9b59b6"),
            ("📤 Export", "", "_hy_export", "#3498db"),
            ("🖨️ Print", "", "_hy_print", "#e67e22"),
        ]:
            btn = QPushButton(text)
            btn.setStyleSheet(f"background: {color}; color: white; font-weight: bold; padding: 5px 12px; border-radius: 3px; border: none;")
            btn.clicked.connect(getattr(self, slot))
            tb_lay.addWidget(btn)

        layout.addWidget(tb)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)

        # ========== LEFT: Inputs ==========
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMaximumWidth(500)
        left_w = QWidget()
        ll = QVBoxLayout(left_w)
        ll.setSpacing(5)

        # --- Pumps ---
        g_pump = QGroupBox("💧 Mud Pumps")
        pump_lay = QVBoxLayout(g_pump)
        pump_btns = QHBoxLayout()
        add_pump = QPushButton("➕ Add Pump")
        add_pump.setStyleSheet("background: #27ae60; color: white; padding: 4px 10px; border-radius: 3px; border: none;")
        add_pump.clicked.connect(self._hy_add_pump_dialog)
        edit_pump = QPushButton("✏️ Edit")
        edit_pump.clicked.connect(self._hy_edit_pump)
        rem_pump = QPushButton("🗑️")
        rem_pump.setFixedWidth(30)
        rem_pump.clicked.connect(self._hy_rem_pump)
        pump_btns.addWidget(add_pump)
        pump_btns.addWidget(edit_pump)
        pump_btns.addWidget(rem_pump)
        pump_btns.addStretch()

        self.hy_pump_table = QTableWidget(0, 5)
        self.hy_pump_table.setHorizontalHeaderLabels(["Name", "Liner(in)", "SPM", "Output", "GPM"])
        self.hy_pump_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hy_pump_table.setMaximumHeight(100)
        self.hy_pump_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.hy_pump_table.setSelectionBehavior(QTableWidget.SelectRows)

        self.hy_total_gpm_label = QLabel("Total Flow Rate: 0 gpm")
        self.hy_total_gpm_label.setStyleSheet("font-weight: bold; color: #3498db; padding: 3px;")

        pump_lay.addLayout(pump_btns)
        pump_lay.addWidget(self.hy_pump_table)
        pump_lay.addWidget(self.hy_total_gpm_label)
        ll.addWidget(g_pump)

        # --- Mud Properties ---
        g_mud = QGroupBox("🧪 Mud Properties")
        mud_f = QFormLayout(g_mud)
        self.hy_mw = self._make_dspin(90, 0, 200, 1, " pcf")
        self.hy_pv = self._make_dspin(15, 0, 200, 1, " cp")
        self.hy_yp = self._make_dspin(11, 0, 200, 1)
        self.hy_t600 = self._make_dspin(45, 0, 500, 0)
        self.hy_t300 = self._make_dspin(25, 0, 500, 0)
        self.hy_t6 = self._make_dspin(4, 0, 100, 0)
        self.hy_t3 = self._make_dspin(3, 0, 100, 0)
        mud_f.addRow("MW (pcf):", self.hy_mw)
        mud_f.addRow("PV (cp):", self.hy_pv)
        mud_f.addRow("YP:", self.hy_yp)
        mud_f.addRow("θ600:", self.hy_t600)
        mud_f.addRow("θ300:", self.hy_t300)
        mud_f.addRow("θ6:", self.hy_t6)
        mud_f.addRow("θ3:", self.hy_t3)
        ll.addWidget(g_mud)

        # --- Surface Equipment ---
        g_surf = QGroupBox("🏗️ Surface Equipment")
        sf = QFormLayout(g_surf)
        self.hy_sp_l = self._make_dspin(50, 0, 200, 0, " m")
        self.hy_sp_id = self._make_dspin(3.5, 0, 10, 2, " in")
        self.hy_hose_l = self._make_dspin(30, 0, 200, 0, " m")
        self.hy_hose_id = self._make_dspin(4.0, 0, 10, 2, " in")
        sf.addRow("Standpipe Len:", self.hy_sp_l)
        sf.addRow("Standpipe ID:", self.hy_sp_id)
        sf.addRow("Hose Len:", self.hy_hose_l)
        sf.addRow("Hose ID:", self.hy_hose_id)
        ll.addWidget(g_surf)

        # --- Drill String (with dialog) ---
        g_ds = QGroupBox("🔩 Drill String")
        ds_lay = QVBoxLayout(g_ds)
        ds_btns = QHBoxLayout()
        add_pipe = QPushButton("➕ Add Component")
        add_pipe.setStyleSheet("background: #27ae60; color: white; padding: 4px 10px; border-radius: 3px; border: none;")
        add_pipe.clicked.connect(self._hy_add_pipe_dialog)
        edit_pipe = QPushButton("✏️ Edit")
        edit_pipe.clicked.connect(self._hy_edit_pipe)
        rem_pipe = QPushButton("🗑️")
        rem_pipe.setFixedWidth(30)
        rem_pipe.clicked.connect(self._hy_rem_pipe)
        ds_btns.addWidget(add_pipe)
        ds_btns.addWidget(edit_pipe)
        ds_btns.addWidget(rem_pipe)
        ds_btns.addStretch()
        ds_lay.addLayout(ds_btns)

        self.hy_pipe_table = QTableWidget(0, 5)
        self.hy_pipe_table.setHorizontalHeaderLabels(["Type", "OD (in)", "ID (in)", "Len (m)", "Wt (ppf)"])
        self.hy_pipe_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hy_pipe_table.setMaximumHeight(160)
        self.hy_pipe_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.hy_pipe_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.hy_pipe_table.doubleClicked.connect(self._hy_edit_pipe)
        ds_lay.addWidget(self.hy_pipe_table)
        ll.addWidget(g_ds)

        # --- Casing / Wellbore (with dialog) ---
        g_csg = QGroupBox("🛢️ Casing / Wellbore")
        csg_lay = QVBoxLayout(g_csg)
        csg_btns = QHBoxLayout()
        add_csg = QPushButton("➕ Add Section")
        add_csg.setStyleSheet("background: #27ae60; color: white; padding: 4px 10px; border-radius: 3px; border: none;")
        add_csg.clicked.connect(self._hy_add_casing_dialog)
        edit_csg = QPushButton("✏️ Edit")
        edit_csg.clicked.connect(self._hy_edit_casing)
        rem_csg = QPushButton("🗑️")
        rem_csg.setFixedWidth(30)
        rem_csg.clicked.connect(self._hy_rem_csg)
        csg_btns.addWidget(add_csg)
        csg_btns.addWidget(edit_csg)
        csg_btns.addWidget(rem_csg)
        csg_btns.addStretch()
        csg_lay.addLayout(csg_btns)

        self.hy_csg_table = QTableWidget(0, 5)
        self.hy_csg_table.setHorizontalHeaderLabels(["Type", "OD/Hole", "ID", "From(m)", "To(m)"])
        self.hy_csg_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hy_csg_table.setMaximumHeight(140)
        self.hy_csg_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.hy_csg_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.hy_csg_table.doubleClicked.connect(self._hy_edit_casing)
        csg_lay.addWidget(self.hy_csg_table)
        ll.addWidget(g_csg)

        # --- Nozzles (with dialog) ---
        g_nzl = QGroupBox("🔵 Bit Nozzles")
        nzl_lay = QVBoxLayout(g_nzl)
        nzl_btns = QHBoxLayout()
        add_nzl = QPushButton("➕ Add Nozzle")
        add_nzl.setStyleSheet("background: #27ae60; color: white; padding: 4px 10px; border-radius: 3px; border: none;")
        add_nzl.clicked.connect(self._hy_add_nozzle_dialog)
        rem_nzl = QPushButton("🗑️")
        rem_nzl.setFixedWidth(30)
        rem_nzl.clicked.connect(self._hy_rem_nzl)
        nzl_btns.addWidget(add_nzl)
        nzl_btns.addWidget(rem_nzl)
        nzl_btns.addStretch()
        self.hy_tfa_label = QLabel("TFA: 0.0000 in²")
        self.hy_tfa_label.setStyleSheet("font-weight: bold; color: #e67e22;")
        nzl_btns.addWidget(self.hy_tfa_label)
        nzl_lay.addLayout(nzl_btns)

        self.hy_nzl_table = QTableWidget(0, 4)
        self.hy_nzl_table.setHorizontalHeaderLabels(["#", "Size", "Qty", "Area (in²)"])
        self.hy_nzl_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hy_nzl_table.setMaximumHeight(100)
        self.hy_nzl_table.setEditTriggers(QTableWidget.NoEditTriggers)
        nzl_lay.addWidget(self.hy_nzl_table)
        ll.addWidget(g_nzl)

        # --- Well Profile ---
        g_wp = QGroupBox("📐 Well Profile")
        wp_f = QFormLayout(g_wp)
        self.hy_wt = QComboBox()
        self.hy_wt.addItems(["Vertical", "Directional", "Horizontal", "S-Shape"])
        self.hy_kop = self._make_dspin(0, 0, 20000, 0, " m")
        self.hy_eob = self._make_dspin(0, 0, 20000, 0, " m")
        self.hy_inc = self._make_dspin(0, 0, 90, 1, " °")
        self.hy_br = self._make_dspin(2, 0, 15, 2, " °/30m")
        self.hy_bit_dep = self._make_dspin(3000, 0, 20000, 1, " m")
        wp_f.addRow("Well Type:", self.hy_wt)
        wp_f.addRow("KOP:", self.hy_kop)
        wp_f.addRow("EOB:", self.hy_eob)
        wp_f.addRow("Max Inc:", self.hy_inc)
        wp_f.addRow("Build Rate:", self.hy_br)
        wp_f.addRow("Bit Depth:", self.hy_bit_dep)
        ll.addWidget(g_wp)

        ll.addStretch()
        left_scroll.setWidget(left_w)
        splitter.addWidget(left_scroll)

        # ========== RIGHT: Results ==========
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_w = QWidget()
        rl = QVBoxLayout(right_w)
        rl.setSpacing(5)

        # KPI Cards
        cards = QWidget()
        cl = QHBoxLayout(cards)
        cl.setContentsMargins(0, 0, 0, 0)
        self.hy_card_spp = self._make_card("SPP", "0", "psi", "#e74c3c")
        self.hy_card_ecd = self._make_card("ECD@Bit", "0.0", "ppg", "#3498db")
        self.hy_card_bhp = self._make_card("Bit HP%", "0", "%", "#27ae60")
        self.hy_card_hsi = self._make_card("HSI", "0.0", "hp/in²", "#f39c12")
        cl.addWidget(self.hy_card_spp)
        cl.addWidget(self.hy_card_ecd)
        cl.addWidget(self.hy_card_bhp)
        cl.addWidget(self.hy_card_hsi)
        rl.addWidget(cards)

        # Pressure Table
        g_press = QGroupBox("📊 Pressure Breakdown")
        pl = QVBoxLayout(g_press)
        self.hy_press_t = QTableWidget(0, 3)
        self.hy_press_t.setHorizontalHeaderLabels(["Component", "ΔP (psi)", "% Total"])
        self.hy_press_t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hy_press_t.setEditTriggers(QTableWidget.NoEditTriggers)
        self.hy_press_t.setAlternatingRowColors(True)
        self.hy_press_t.setMaximumHeight(220)
        pl.addWidget(self.hy_press_t)
        rl.addWidget(g_press)

        # AV + Regime
        g_av = QGroupBox("🌊 Annular Velocity & Flow Regime")
        avl = QVBoxLayout(g_av)
        self.hy_av_t = QTableWidget(0, 4)
        self.hy_av_t.setHorizontalHeaderLabels(["Section", "AV (ft/min)", "Regime", "Status"])
        self.hy_av_t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hy_av_t.setEditTriggers(QTableWidget.NoEditTriggers)
        self.hy_av_t.setMaximumHeight(160)
        avl.addWidget(self.hy_av_t)
        rl.addWidget(g_av)

        # Critical Flow Rate (deepest annulus)
        g_qc = QGroupBox("⚡ Critical Flow Rate (Annulus)")
        qcl = QVBoxLayout(g_qc)
        self.hy_qc_lbl = QLabel("Run Calculate to evaluate laminar→turbulent limit.")
        self.hy_qc_lbl.setWordWrap(True)
        self.hy_qc_lbl.setStyleSheet("font-size: 12px; padding: 8px; background: #f8f9fa; border-radius: 4px;")
        qcl.addWidget(self.hy_qc_lbl)
        rl.addWidget(g_qc)

        # ECD Chart
        g_ecd = QGroupBox("📈 ECD vs Depth")
        ecl = QVBoxLayout(g_ecd)
        self.hy_ecd_w = QWidget()
        self.hy_ecd_w.setMinimumHeight(250)
        ecl.addWidget(self.hy_ecd_w)
        rl.addWidget(g_ecd)

        # Bit Results
        g_bit = QGroupBox("🔵 Bit Hydraulics")
        bl = QVBoxLayout(g_bit)
        self.hy_bit_lbl = QLabel("")
        self.hy_bit_lbl.setWordWrap(True)
        self.hy_bit_lbl.setStyleSheet("font-size: 12px; padding: 8px; background: #f8f9fa; border-radius: 4px;")
        bl.addWidget(self.hy_bit_lbl)
        rl.addWidget(g_bit)

        # Warnings
        self.hy_warn = QLabel("")
        self.hy_warn.setWordWrap(True)
        self.hy_warn.setStyleSheet("color: #e74c3c; font-size: 11px;")
        rl.addWidget(self.hy_warn)

        rl.addStretch()
        right_scroll.setWidget(right_w)
        splitter.addWidget(right_scroll)

        splitter.setSizes([420, 600])
        layout.addWidget(splitter)
        return tab

    # ========== Pump Methods (Dialog) ==========

    def _hy_add_pump_dialog(self):
        from dialogs.engineering_dialogs import AddPumpDialog
        dlg = AddPumpDialog(self)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                self.hy_pumps.append(data)
                self._hy_refresh_pump_table()

    def _hy_edit_pump(self):
        row = self.hy_pump_table.currentRow()
        if row < 0 or row >= len(self.hy_pumps):
            return
        from dialogs.engineering_dialogs import AddPumpDialog
        dlg = AddPumpDialog(self, edit_data=self.hy_pumps[row])
        if dlg.exec():
            data = dlg.get_result()
            if data:
                self.hy_pumps[row] = data
                self._hy_refresh_pump_table()

    def _hy_rem_pump(self):
        row = self.hy_pump_table.currentRow()
        if 0 <= row < len(self.hy_pumps):
            self.hy_pumps.pop(row)
            self._hy_refresh_pump_table()

    def _hy_refresh_pump_table(self):
        self.hy_pump_table.setRowCount(0)
        total_gpm = 0
        for p in self.hy_pumps:
            row = self.hy_pump_table.rowCount()
            self.hy_pump_table.insertRow(row)
            output = p.get('output_bbl_stk', 0)
            spm = p.get('spm', 0)
            gpm = output * spm * 42

            self.hy_pump_table.setItem(row, 0, QTableWidgetItem(p.get('name', '')))
            self.hy_pump_table.setItem(row, 1, QTableWidgetItem(f"{p.get('liner', 0):.1f}"))
            self.hy_pump_table.setItem(row, 2, QTableWidgetItem(f"{spm:.0f}"))
            self.hy_pump_table.setItem(row, 3, QTableWidgetItem(f"{output:.5f}"))
            self.hy_pump_table.setItem(row, 4, QTableWidgetItem(f"{gpm:.1f}"))
            total_gpm += gpm

        self.hy_total_gpm_label.setText(f"Total Flow Rate: {total_gpm:.1f} gpm")

    # ========== Pipe Methods (Dialog) ==========

    def _hy_add_pipe_dialog(self):
        from dialogs.engineering_dialogs import AddPipeDialog
        dlg = AddPipeDialog(self)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                self._hy_insert_pipe_row(data)

    def _hy_edit_pipe(self):
        row = self.hy_pipe_table.currentRow()
        if row < 0:
            return
        # جمع‌آوری داده فعلی
        edit_data = {
            'type': self.hy_pipe_table.item(row, 0).text() if self.hy_pipe_table.item(row, 0) else "",
            'od': float(self.hy_pipe_table.item(row, 1).text()) if self.hy_pipe_table.item(row, 1) else 5,
            'id': float(self.hy_pipe_table.item(row, 2).text()) if self.hy_pipe_table.item(row, 2) else 4.276,
            'length': float(self.hy_pipe_table.item(row, 3).text()) if self.hy_pipe_table.item(row, 3) else 0,
            'weight': float(self.hy_pipe_table.item(row, 4).text()) if self.hy_pipe_table.item(row, 4) else 19.5,
        }
        from dialogs.engineering_dialogs import AddPipeDialog
        dlg = AddPipeDialog(self, edit_data=edit_data)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                self.hy_pipe_table.removeRow(row)
                self._hy_insert_pipe_row(data, row)

    def _hy_insert_pipe_row(self, data, position=-1):
        row = self.hy_pipe_table.rowCount() if position == -1 else position
        self.hy_pipe_table.insertRow(row)
        self.hy_pipe_table.setItem(row, 0, QTableWidgetItem(data.get('type', '')))
        self.hy_pipe_table.setItem(row, 1, QTableWidgetItem(f"{data.get('od', 0):.3f}"))
        self.hy_pipe_table.setItem(row, 2, QTableWidgetItem(f"{data.get('id', 0):.3f}"))
        self.hy_pipe_table.setItem(row, 3, QTableWidgetItem(f"{data.get('length', 0):.1f}"))
        self.hy_pipe_table.setItem(row, 4, QTableWidgetItem(f"{data.get('weight', 0):.1f}"))

    def _hy_rem_pipe(self):
        row = self.hy_pipe_table.currentRow()
        if row >= 0:
            self.hy_pipe_table.removeRow(row)

    # ========== Casing Methods (Dialog) ==========

    def _hy_add_casing_dialog(self):
        from dialogs.engineering_dialogs import AddCasingDialog
        dlg = AddCasingDialog(self)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                self._hy_insert_csg_row(data)

    def _hy_edit_casing(self):
        row = self.hy_csg_table.currentRow()
        if row < 0:
            return
        edit_data = {
            'type': self.hy_csg_table.item(row, 0).text() if self.hy_csg_table.item(row, 0) else "",
            'od': float(self.hy_csg_table.item(row, 1).text()) if self.hy_csg_table.item(row, 1) else 9.625,
            'id': float(self.hy_csg_table.item(row, 2).text()) if self.hy_csg_table.item(row, 2) else 8.835,
            'from': float(self.hy_csg_table.item(row, 3).text()) if self.hy_csg_table.item(row, 3) else 0,
            'to': float(self.hy_csg_table.item(row, 4).text()) if self.hy_csg_table.item(row, 4) else 0,
        }
        from dialogs.engineering_dialogs import AddCasingDialog
        dlg = AddCasingDialog(self, edit_data=edit_data)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                self.hy_csg_table.removeRow(row)
                self._hy_insert_csg_row(data, row)

    def _hy_insert_csg_row(self, data, position=-1):
        row = self.hy_csg_table.rowCount() if position == -1 else position
        self.hy_csg_table.insertRow(row)
        self.hy_csg_table.setItem(row, 0, QTableWidgetItem(data.get('type', '')))
        self.hy_csg_table.setItem(row, 1, QTableWidgetItem(f"{data.get('od', 0):.3f}"))
        self.hy_csg_table.setItem(row, 2, QTableWidgetItem(f"{data.get('id', 0):.3f}"))
        self.hy_csg_table.setItem(row, 3, QTableWidgetItem(f"{data.get('from', 0):.1f}"))
        self.hy_csg_table.setItem(row, 4, QTableWidgetItem(f"{data.get('to', 0):.1f}"))

    def _hy_rem_csg(self):
        row = self.hy_csg_table.currentRow()
        if row >= 0:
            self.hy_csg_table.removeRow(row)

    # ========== Nozzle Methods (Dialog) ==========

    def _hy_add_nozzle_dialog(self):
        from dialogs.engineering_dialogs import AddNozzleDialog
        dlg = AddNozzleDialog(self)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                self._hy_insert_nzl_row(data)
                self._hy_update_tfa()

    def _hy_insert_nzl_row(self, data):
        row = self.hy_nzl_table.rowCount()
        self.hy_nzl_table.insertRow(row)
        size = data.get('size', 16)
        qty = data.get('qty', 1)
        area = math.pi / 4 * (size / 32.0) ** 2 * qty

        self.hy_nzl_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.hy_nzl_table.setItem(row, 1, QTableWidgetItem(f"{size}/32\""))
        self.hy_nzl_table.setItem(row, 2, QTableWidgetItem(str(qty)))
        ai = QTableWidgetItem(f"{area:.4f}")
        ai.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.hy_nzl_table.setItem(row, 3, ai)

    def _hy_rem_nzl(self):
        row = self.hy_nzl_table.currentRow()
        if row >= 0:
            self.hy_nzl_table.removeRow(row)
            # Renumber
            for i in range(self.hy_nzl_table.rowCount()):
                self.hy_nzl_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self._hy_update_tfa()

    def _hy_update_tfa(self):
        total = 0
        for row in range(self.hy_nzl_table.rowCount()):
            item = self.hy_nzl_table.item(row, 3)
            if item:
                try:
                    total += float(item.text())
                except:
                    pass
        self.hy_tfa_label.setText(f"TFA: {total:.4f} in²")
  
    # ========== Collect & Calculate ==========

    def _hy_get_total_gpm(self):
        """محاسبه GPM کل از جدول پمپ‌ها"""
        total = 0
        for p in self.hy_pumps:
            output = p.get('output_bbl_stk', 0)
            spm = p.get('spm', 0)
            total += output * spm * 42
        return total

    def _hy_collect(self):
        """جمع‌آوری داده از UI برای engine"""
        from core.hydraulics_engine import (
            PipeSegment, CasingSection, BitNozzle,
            MudProperties, SurfaceEquipment, WellProfile
        )
        e = self.adv_engine

        # Flow rate from pumps
        total_gpm = self._hy_get_total_gpm()
        e.flow_rate_gpm = total_gpm if total_gpm > 0 else 250  # fallback
        e.bit_depth_m = self.hy_bit_dep.value()

        e.model = {0: "bingham", 1: "power_law", 2: "herschel_bulkley"}.get(
            self.hy_model.currentIndex(), "bingham"
        )

        e.mud = MudProperties(
            mw_pcf=self.hy_mw.value(), pv=self.hy_pv.value(), yp=self.hy_yp.value(),
            theta600=self.hy_t600.value(), theta300=self.hy_t300.value(),
            theta6=self.hy_t6.value(), theta3=self.hy_t3.value(),
        )

        e.surface_equipment = SurfaceEquipment(
            standpipe_length_m=self.hy_sp_l.value(), standpipe_id_inch=self.hy_sp_id.value(),
            hose_length_m=self.hy_hose_l.value(), hose_id_inch=self.hy_hose_id.value(),
        )

        # Pipes from table
        e.pipe_segments = []
        for row in range(self.hy_pipe_table.rowCount()):
            try:
                ptype = self.hy_pipe_table.item(row, 0).text()
                od = float(self.hy_pipe_table.item(row, 1).text())
                id_ = float(self.hy_pipe_table.item(row, 2).text())
                length = float(self.hy_pipe_table.item(row, 3).text())
                wt = float(self.hy_pipe_table.item(row, 4).text())
                if length > 0 and od > 0 and id_ > 0:
                    e.pipe_segments.append(PipeSegment(
                        name=f"{ptype} ({od:.3f}\")", pipe_type=ptype,
                        od=od, id=id_, length=length, weight_ppf=wt
                    ))
            except:
                continue

        # Casings from table
        e.casing_sections = []
        for row in range(self.hy_csg_table.rowCount()):
            try:
                ctype = self.hy_csg_table.item(row, 0).text()
                od = float(self.hy_csg_table.item(row, 1).text())
                id_ = float(self.hy_csg_table.item(row, 2).text())
                fr = float(self.hy_csg_table.item(row, 3).text())
                to = float(self.hy_csg_table.item(row, 4).text())
                if to > fr:
                    st = "open_hole" if "Open" in ctype else "casing"
                    e.casing_sections.append(CasingSection(
                        name=ctype, section_type=st, od=od, id=id_,
                        top_md=fr, bottom_md=to
                    ))
            except:
                continue

        # Nozzles from table
        e.nozzles = []
        for row in range(self.hy_nzl_table.rowCount()):
            try:
                size_text = self.hy_nzl_table.item(row, 1).text()
                size = int(size_text.split('/')[0])
                qty = int(self.hy_nzl_table.item(row, 2).text())
                e.nozzles.append(BitNozzle(size_32nds=size, quantity=qty))
            except:
                continue

        # Well Profile
        wt = {0: "vertical", 1: "directional", 2: "horizontal", 3: "s_shape"}
        e.well_profile = WellProfile(
            well_type=wt.get(self.hy_wt.currentIndex(), "vertical"),
            kop_md=self.hy_kop.value(), eob_md=self.hy_eob.value(),
            eob_inc=self.hy_inc.value(), build_rate=self.hy_br.value(),
        )

    def _hy_run_calc(self):
        """اجرای محاسبات"""
        try:
            self._hy_collect()
            r = self.adv_engine.calculate()
            self.hy_result = r
            self._hy_display(r)
        except Exception as ex:
            logger.error(f"Hydraulics calc error: {ex}")
            QMessageBox.critical(self, "Error", f"Calculation failed:\n{str(ex)}")

    def _hy_display(self, r):
        """نمایش نتایج"""
        # Cards
        self._update_card(self.hy_card_spp, f"{r.total_loss_psi:.0f}", "psi")
        self._update_card(self.hy_card_ecd, f"{r.ecd_at_bit_ppg:.2f}", "ppg")
        self._update_card(self.hy_card_bhp, f"{r.percent_bit_hp:.0f}", "%")
        self._update_card(self.hy_card_hsi, f"{r.hsi:.2f}", "hp/in²")

        # Pressure Table
        self.hy_press_t.setRowCount(0)
        t = r.total_loss_psi if r.total_loss_psi > 0 else 1
        entries = [("Surface Equipment", r.surface_loss_psi)]
        entries += [(n, l) for n, l in r.pipe_losses]
        entries += [(n, l) for n, l in r.annulus_losses]
        entries.append(("Bit Nozzles", r.bit_loss_psi))
        entries.append(("═══ TOTAL ═══", r.total_loss_psi))

        for name, loss in entries:
            row = self.hy_press_t.rowCount()
            self.hy_press_t.insertRow(row)
            self.hy_press_t.setItem(row, 0, QTableWidgetItem(name))
            li = QTableWidgetItem(f"{loss:.1f}")
            li.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.hy_press_t.setItem(row, 1, li)
            pi = QTableWidgetItem(f"{loss/t*100:.1f}%")
            pi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.hy_press_t.setItem(row, 2, pi)
            if "TOTAL" in name:
                for c in range(3):
                    it = self.hy_press_t.item(row, c)
                    if it:
                        f = it.font(); f.setBold(True); it.setFont(f)
                        it.setBackground(QColor("#d5f5e3"))

        # AV Table
        self.hy_av_t.setRowCount(0)
        for name, av in r.annular_velocities:
            row = self.hy_av_t.rowCount()
            self.hy_av_t.insertRow(row)
            self.hy_av_t.setItem(row, 0, QTableWidgetItem(name))
            ai = QTableWidgetItem(f"{av:.0f}")
            ai.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.hy_av_t.setItem(row, 1, ai)
            regime = ""
            for rn, rt in r.flow_regimes_annulus:
                if rn == name:
                    regime = rt
                    break
            self.hy_av_t.setItem(row, 2, QTableWidgetItem(regime))
            si = QTableWidgetItem("✅ OK" if av >= 100 else "⚠️ Low")
            si.setForeground(QColor("#27ae60" if av >= 100 else "#e74c3c"))
            self.hy_av_t.setItem(row, 3, si)

        # Critical flow rate
        if getattr(r, "critical_flow_rate_gpm", 0) > 0:
            q_running = r.flow_rate_gpm
            status = ("🟢 Turbulent" if q_running >= r.critical_flow_rate_gpm
                      else "🟡 Laminar")
            self.hy_qc_lbl.setText(
                f"<b>Section:</b> {r.critical_section}<br>"
                f"<b>Vc:</b> {r.critical_velocity_ft_min:.0f} ft/min | "
                f"<b>Qc:</b> {r.critical_flow_rate_gpm:.0f} gpm<br>"
                f"<b>Current Q:</b> {q_running:.0f} gpm → {status}"
            )
        else:
            self.hy_qc_lbl.setText("No annular section available for Qc.")

        # Bit
        self.hy_bit_lbl.setText(
            f"<b>TFA:</b> {r.tfa_in2:.4f} in² | "
            f"<b>ΔP:</b> {r.bit_loss_psi:.0f} psi | "
            f"<b>HHP:</b> {r.bit_hhp:.1f} hp | "
            f"<b>HSI:</b> {r.hsi:.2f} hp/in²<br>"
            f"<b>Jet Vel:</b> {r.jet_velocity_fps:.0f} ft/s | "
            f"<b>IF:</b> {r.impact_force_lbs:.0f} lbs | "
            f"<b>Bit HP%:</b> {r.percent_bit_hp:.1f}%"
        )

        # ECD Chart
        self._draw_ecd(r.ecd_profile)

        # Warnings
        self.hy_warn.setText("⚠️ " + "\n⚠️ ".join(r.warnings) if r.warnings else "")

    def _draw_ecd(self, profile):
        """رسم نمودار ECD"""
        if not profile:
            return
        try:
            import matplotlib
            matplotlib.use('Qt5Agg')
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

            depths = [p[0] for p in profile]
            ecds = [p[1] for p in profile]

            fig, ax = plt.subplots(figsize=(5, 3), facecolor='#f8f9fa')
            ax.set_facecolor('#f8f9fa')
            ax.plot(ecds, depths, 'b-o', lw=2, ms=3, label='ECD')
            mw_ppg = self.hy_mw.value() / 7.48
            ax.axvline(x=mw_ppg, color='green', ls='--', lw=1, label=f'MW={mw_ppg:.2f}')
            ax.set_xlabel("ECD (ppg)")
            ax.set_ylabel("Depth (m)")
            ax.set_title("ECD vs Depth", fontweight='bold')
            ax.invert_yaxis()
            ax.grid(True, alpha=0.3)
            ax.legend(fontsize=7)
            fig.tight_layout()

            canvas = FigureCanvas(fig)
            safe_replace_chart(self.hy_ecd_w, canvas)
            plt.close(fig)
        except Exception as e:
            logger.error(f"ECD chart: {e}")

    # ========== Surge/Swab Dialog ==========

    def _hy_surge_dialog(self):
        """دیالوگ Surge/Swab"""
        self._hy_collect()
        dlg = QDialog(self)
        dlg.setWindowTitle("📉 Surge / Swab Calculator")
        dlg.setMinimumSize(500, 400)
        lay = QVBoxLayout(dlg)

        form = QFormLayout()
        speed = self._make_dspin(90, 0, 300, 0, " ft/min")
        op = QComboBox()
        op.addItems(["POOH (Swab)", "RIH (Surge)"])
        ps = QComboBox()
        ps.addItems(["Open Pipe", "Closed Pipe"])
        form.addRow("Trip Speed:", speed)
        form.addRow("Operation:", op)
        form.addRow("Pipe Status:", ps)
        lay.addLayout(form)

        rt = QTextEdit()
        rt.setReadOnly(True)
        rt.setStyleSheet("font-family: Consolas; font-size: 11px;")
        lay.addWidget(rt)

        def calc():
            r = self.adv_engine.calc_surge_swab(
                trip_speed_fpm=speed.value(),
                operation="POOH" if op.currentIndex() == 0 else "RIH",
                pipe_open=ps.currentIndex() == 0
            )
            txt = f"═══ {r['type']} Analysis ═══\n"
            txt += f"Speed: {r['trip_speed_fpm']} ft/min | Pipe: {r['pipe_status']}\n\n"
            txt += f"Total ΔP: {r['total_pressure_psi']:.1f} psi\n"
            txt += f"Equiv MW: {r['equiv_mw_ppg']:.3f} ppg ({r['equiv_mw_pcf']:.2f} pcf)\n"
            txt += f"Original MW: {self.adv_engine.mud.mw_ppg:.3f} ppg\n\n"
            for s in r.get('segments', []):
                txt += f"  {s['segment']}: {s['pressure_psi']:.2f} psi\n"
            rt.setText(txt)

        b = QPushButton("🔄 Calculate")
        b.setStyleSheet("background: #27ae60; color: white; font-weight: bold; padding: 8px; border-radius: 4px; border: none;")
        b.clicked.connect(calc)
        lay.addWidget(b)
        dlg.exec()

    # ========== Export & Print ==========

    def _hy_export(self):
        """اکسپورت نتایج"""
        if not self.hy_result:
            QMessageBox.warning(self, "No Data", "Run calculation first.")
            return
        from datetime import datetime
        fn, _ = QFileDialog.getSaveFileName(
            self, "Export", f"hydraulics_{datetime.now().strftime('%Y%m%d')}.csv", "CSV (*.csv)"
        )
        if not fn:
            return
        import csv
        r = self.hy_result
        t = r.total_loss_psi if r.total_loss_psi > 0 else 1
        with open(fn, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(["Component", "ΔP (psi)", "% Total"])
            w.writerow(["Surface", f"{r.surface_loss_psi:.1f}", f"{r.surface_loss_psi/t*100:.1f}%"])
            for n, l in r.pipe_losses:
                w.writerow([f"Pipe: {n}", f"{l:.1f}", f"{l/t*100:.1f}%"])
            for n, l in r.annulus_losses:
                w.writerow([f"Ann: {n}", f"{l:.1f}", f"{l/t*100:.1f}%"])
            w.writerow(["Bit", f"{r.bit_loss_psi:.1f}", f"{r.bit_loss_psi/t*100:.1f}%"])
            w.writerow(["TOTAL", f"{r.total_loss_psi:.1f}", "100%"])
            w.writerow([])
            w.writerow(["Depth(m)", "ECD(ppg)"])
            for d, e in r.ecd_profile:
                w.writerow([f"{d:.1f}", f"{e:.3f}"])
        self.show_success(f"Exported: {fn}")

    def _hy_print(self):
        """چاپ نتایج"""
        if not self.hy_result:
            QMessageBox.warning(self, "No Data", "Run calculation first.")
            return
        from PySide6.QtPrintSupport import QPrinter, QPrintDialog
        from PySide6.QtGui import QTextDocument
        r = self.hy_result
        html = f"""
        <h2>Hydraulics Report</h2>
        <p>Model: {self.hy_model.currentText()} | MW: {self.hy_mw.value():.1f} pcf</p>
        <p><b>Total SPP: {r.total_loss_psi:.0f} psi</b> | ECD: {r.ecd_at_bit_ppg:.3f} ppg | HSI: {r.hsi:.2f}</p>
        <h3>Pressure Breakdown</h3>
        <table border="1" cellpadding="4"><tr><th>Component</th><th>ΔP (psi)</th></tr>
        <tr><td>Surface</td><td>{r.surface_loss_psi:.1f}</td></tr>
        """
        for n, l in r.pipe_losses:
            html += f"<tr><td>Pipe: {n}</td><td>{l:.1f}</td></tr>"
        for n, l in r.annulus_losses:
            html += f"<tr><td>Ann: {n}</td><td>{l:.1f}</td></tr>"
        html += f"""
        <tr><td>Bit</td><td>{r.bit_loss_psi:.1f}</td></tr>
        <tr><td><b>TOTAL</b></td><td><b>{r.total_loss_psi:.1f}</b></td></tr>
        </table>
        """
        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() == QPrintDialog.Accepted:
            doc = QTextDocument()
            doc.setHtml(html)
            doc.print_(printer)
 
    def _make_card(self, title, value, unit, color):
        """ساخت KPI Card"""
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {color}15; border-left: 4px solid {color}; "
            f"border-radius: 4px; padding: 5px; margin: 2px; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(5, 3, 5, 3)
        layout.setSpacing(2)

        t = QLabel(title)
        t.setStyleSheet("font-size: 10px; color: #7f8c8d; font-weight: bold;")
        layout.addWidget(t)

        v = QLabel(f"<b>{value}</b> {unit}")
        v.setStyleSheet(f"font-size: 16px; color: {color};")
        layout.addWidget(v)

        card.value_label = v
        return card

    def _update_card(self, card, value, unit=""):
        """آپدیت مقدار KPI Card"""
        if hasattr(card, 'value_label'):
            card.value_label.setText(f"<b>{value}</b> {unit}")
            

    def _create_bit_tab(self) -> QWidget:
        """تب Bit Hydraulics - حرفه‌ای با دیالوگ نازل"""
        self.bit_nozzles = []  # لیست نازل‌ها

        tab, container, layout = self._make_scroll_tab()

        inner_tabs = QTabWidget()
        layout.addWidget(inner_tabs)

        # ===== Sub-tab 1: Bit Hydraulics =====
        bh_tab = QWidget()
        bh_layout = QVBoxLayout(bh_tab)

        # Nozzle Management
        g_nzl = QGroupBox("🔵 Bit Nozzle Configuration")
        nzl_lay = QVBoxLayout(g_nzl)
        nzl_btns = QHBoxLayout()

        add_nzl = QPushButton("➕ Add Nozzle")
        add_nzl.setStyleSheet("background: #27ae60; color: white; padding: 4px 10px; border-radius: 3px; border: none;")
        add_nzl.clicked.connect(self._bit_add_nozzle)
        rem_nzl = QPushButton("🗑️ Remove")
        rem_nzl.clicked.connect(self._bit_rem_nozzle)
        clear_nzl = QPushButton("🧹 Clear All")
        clear_nzl.clicked.connect(self._bit_clear_nozzles)
        nzl_btns.addWidget(add_nzl)
        nzl_btns.addWidget(rem_nzl)
        nzl_btns.addWidget(clear_nzl)
        nzl_btns.addStretch()
        nzl_lay.addLayout(nzl_btns)

        self.bit_nzl_table = QTableWidget(0, 4)
        self.bit_nzl_table.setHorizontalHeaderLabels(["#", "Size (1/32\")", "Qty", "Area (in²)"])
        self.bit_nzl_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.bit_nzl_table.setMaximumHeight(120)
        self.bit_nzl_table.setEditTriggers(QTableWidget.NoEditTriggers)
        nzl_lay.addWidget(self.bit_nzl_table)

        # TFA Summary
        tfa_layout = QHBoxLayout()
        self.bit_tfa_label = QLabel("TFA: 0.0000 in²")
        self.bit_tfa_label.setStyleSheet("font-weight: bold; color: #e67e22; font-size: 13px; padding: 3px;")
        self.bit_nzl_summary = QLabel("")
        self.bit_nzl_summary.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        tfa_layout.addWidget(self.bit_tfa_label)
        tfa_layout.addWidget(self.bit_nzl_summary)
        tfa_layout.addStretch()
        nzl_lay.addLayout(tfa_layout)
        bh_layout.addWidget(g_nzl)

        # Input Parameters
        g_input = QGroupBox("📊 Input Parameters")
        input_form = QFormLayout(g_input)

        self.bit_gpm = self._make_dspin(250, 0, 5000, 0, " gpm")
        self.bit_mw = self._make_dspin(90, 0, 200, 1, " pcf")
        self.bit_od = self._make_dspin(8.5, 0, 50, 3, " in")
        self.bit_wob = self._make_dspin(25, 0, 200, 1, " klbf")
        self.bit_rpm = self._make_dspin(120, 0, 400, 0, " rpm")
        self.bit_tq = self._make_dspin(8000, 0, 80000, 0, " ft-lbf")
        self.bit_rop = self._make_dspin(30, 0, 500, 1, " ft/hr")

        input_form.addRow("Flow Rate:", self.bit_gpm)
        input_form.addRow("Mud Weight:", self.bit_mw)
        input_form.addRow("Bit Size:", self.bit_od)
        input_form.addRow("WOB:", self.bit_wob)
        input_form.addRow("RPM:", self.bit_rpm)
        input_form.addRow("Torque:", self.bit_tq)
        input_form.addRow("ROP:", self.bit_rop)

        calc_btn = QPushButton("🔄 Calculate Bit Hydraulics")
        calc_btn.setStyleSheet("background: #e74c3c; color: white; font-weight: bold; padding: 8px; border-radius: 4px; border: none;")
        calc_btn.clicked.connect(self._bit_calculate)
        input_form.addRow(calc_btn)

        bh_layout.addWidget(g_input)

        # Results
        g_results = QGroupBox("📊 Results")
        res_layout = QGridLayout(g_results)

        self.bit_res_dp = self._result_label("#e74c3c")
        self.bit_res_hhp = self._result_label("#27ae60")
        self.bit_res_hsi = self._result_label("#3498db")
        self.bit_res_jv = self._result_label("#9b59b6")
        self.bit_res_if = self._result_label("#e67e22")
        self.bit_res_pct = self._result_label("#1abc9c")
        self.bit_res_mse = self._result_label("#8e44ad")

        res_layout.addWidget(QLabel("Bit ΔP:"), 0, 0)
        res_layout.addWidget(self.bit_res_dp, 0, 1)
        res_layout.addWidget(QLabel("Bit HHP:"), 0, 2)
        res_layout.addWidget(self.bit_res_hhp, 0, 3)
        res_layout.addWidget(QLabel("HSI:"), 1, 0)
        res_layout.addWidget(self.bit_res_hsi, 1, 1)
        res_layout.addWidget(QLabel("Jet Velocity:"), 1, 2)
        res_layout.addWidget(self.bit_res_jv, 1, 3)
        res_layout.addWidget(QLabel("Impact Force:"), 2, 0)
        res_layout.addWidget(self.bit_res_if, 2, 1)
        res_layout.addWidget(QLabel("Nozzle Vel:"), 2, 2)
        res_layout.addWidget(self.bit_res_pct, 2, 3)
        res_layout.addWidget(QLabel("MSE (Teale):"), 3, 0)
        res_layout.addWidget(self.bit_res_mse, 3, 1)

        bh_layout.addWidget(g_results)

        self.bit_reco = QLabel("")
        self.bit_reco.setWordWrap(True)
        self.bit_reco.setStyleSheet(
            "font-size: 12px; padding: 8px; background: #fef9e7; "
            "border: 1px solid #f1c40f; border-radius: 4px;")
        bh_layout.addWidget(self.bit_reco)

        # Bit Economics — Cost per Foot (Bourgoyne)
        g_econ = QGroupBox("💰 Bit Economics — Cost per Foot")
        econ_form = QFormLayout(g_econ)
        self.bit_rig_day = self._make_dspin(40000, 0, 1000000, 0, " $/day")
        self.bit_trip_h = self._make_dspin(6, 0, 100, 1, " hr")
        self.bit_rot_h = self._make_dspin(20, 0, 500, 1, " hr")
        self.bit_cost = self._make_dspin(2000, 0, 100000, 0, " $")
        self.bit_footage = self._make_dspin(500, 1, 100000, 0, " ft")
        econ_form.addRow("Rig cost:", self.bit_rig_day)
        econ_form.addRow("Trip time:", self.bit_trip_h)
        econ_form.addRow("Rotating time:", self.bit_rot_h)
        econ_form.addRow("Bit cost:", self.bit_cost)
        econ_form.addRow("Footage:", self.bit_footage)
        econ_btn = QPushButton("🔄 C/ft = (C_rig×T_trip + C_bit) / footage")
        econ_btn.setStyleSheet("background: #1abc9c; color: white; font-weight: bold; padding: 6px; border-radius: 4px; border: none;")
        econ_btn.clicked.connect(self._bit_cost_per_foot)
        econ_form.addRow(econ_btn)
        self.bit_econ_res = self._result_label("#1abc9c")
        econ_form.addRow("Cost per foot:", self.bit_econ_res)
        bh_layout.addWidget(g_econ)

        bh_layout.addStretch()
        inner_tabs.addTab(bh_tab, "🔵 Bit Hydraulics")

        # ===== Sub-tab 2: Nozzle Optimization =====
        opt_tab = QWidget()
        opt_layout = QVBoxLayout(opt_tab)

        g_opt = QGroupBox("🌀 Nozzle Optimization")
        opt_form = QFormLayout(g_opt)

        self.opt_hhp = self._make_dspin(1000, 0, 50000, 0, " HP")
        self.opt_max_press = self._make_dspin(3500, 0, 15000, 0, " psi")
        self.opt_fr1 = self._make_dspin(250, 0, 5000, 0, " gpm")
        self.opt_spp1 = self._make_dspin(3000, 0, 15000, 0, " psi")
        self.opt_fr2 = self._make_dspin(200, 0, 5000, 0, " gpm")
        self.opt_spp2 = self._make_dspin(2500, 0, 15000, 0, " psi")
        self.opt_tfa = self._make_dspin(0.5, 0, 10, 4, " in²")
        self.opt_mw = self._make_dspin(12, 0, 25, 2, " ppg")
        self.opt_n_nzl = QSpinBox()
        self.opt_n_nzl.setRange(1, 8)
        self.opt_n_nzl.setValue(3)

        model_layout = QHBoxLayout()
        self.opt_hp_model = QRadioButton("Max Bit HP")
        self.opt_if_model = QRadioButton("Max Impact Force")
        self.opt_hp_model.setChecked(True)
        model_layout.addWidget(self.opt_hp_model)
        model_layout.addWidget(self.opt_if_model)

        opt_form.addRow("Available HHP:", self.opt_hhp)
        opt_form.addRow("Max Pump Press:", self.opt_max_press)
        opt_form.addRow("Flow Rate #1:", self.opt_fr1)
        opt_form.addRow("SPP #1:", self.opt_spp1)
        opt_form.addRow("Flow Rate #2:", self.opt_fr2)
        opt_form.addRow("SPP #2:", self.opt_spp2)
        opt_form.addRow("Current TFA:", self.opt_tfa)
        opt_form.addRow("Mud Weight:", self.opt_mw)
        opt_form.addRow("No. of Nozzles:", self.opt_n_nzl)
        opt_form.addRow("Model:", model_layout)

        opt_calc = QPushButton("🌀 Optimize Nozzles")
        opt_calc.setStyleSheet("background: #9b59b6; color: white; font-weight: bold; padding: 10px; border-radius: 5px; border: none;")
        opt_calc.clicked.connect(self._bit_optimize)
        opt_form.addRow(opt_calc)

        self.opt_results = QTextEdit()
        self.opt_results.setReadOnly(True)
        self.opt_results.setMinimumHeight(180)
        self.opt_results.setStyleSheet("background: #1e1e2e; color: #ecf0f1; font-family: Consolas; font-size: 12px;")
        opt_form.addRow("Results:", self.opt_results)

        opt_layout.addWidget(g_opt)
        opt_layout.addStretch()
        inner_tabs.addTab(opt_tab, "🌀 Nozzle Optimization")

        # ===== Sub-tab 3: TFA Calculator =====
        tfa_tab = QWidget()
        tfa_layout = QVBoxLayout(tfa_tab)

        g_tfa = QGroupBox("🔵 TFA from Pressure Drop")
        tfa_form = QFormLayout(g_tfa)
        self.tfa_gpm = self._make_dspin(250, 0, 5000, 0, " gpm")
        self.tfa_mw = self._make_dspin(12, 0, 25, 2, " ppg")
        self.tfa_dp = self._make_dspin(1000, 0, 10000, 0, " psi")
        tfa_form.addRow("Flow Rate:", self.tfa_gpm)
        tfa_form.addRow("Mud Weight:", self.tfa_mw)
        tfa_form.addRow("Bit ΔP:", self.tfa_dp)

        tfa_calc = QPushButton("🔄 Calculate TFA")
        tfa_calc.clicked.connect(self._bit_calc_tfa)
        tfa_form.addRow(tfa_calc)

        self.tfa_result = self._result_label("#e67e22")
        tfa_form.addRow("Required TFA:", self.tfa_result)

        tfa_layout.addWidget(g_tfa)
        tfa_layout.addStretch()
        inner_tabs.addTab(tfa_tab, "📐 TFA Calculator")

        return tab
  
    # ========== Bit - Nozzle Management ==========

    def _bit_cost_per_foot(self):
        from core.engineering.engines.bit_performance import BitPerformanceEngine
        r = BitPerformanceEngine.cost_per_foot(
            rig_cost_per_day=self.bit_rig_day.value(),
            trip_hours=self.bit_trip_h.value(),
            bit_cost=self.bit_cost.value(),
            footage=self.bit_footage.value(),
            rotating_hours=self.bit_rot_h.value(),
        )
        if r.success:
            v = r.values
            self.bit_econ_res.setText(
                f"${v['cost_per_ft']:.2f}/ft  (total ${v['total_cost']:,.0f}, "
                f"rig ${v['rig_cost_per_hr']:.0f}/hr)")
        else:
            self.bit_econ_res.setText(f"⚠️ {r.error}")

    def _bit_add_nozzle(self):
        from dialogs.engineering_dialogs import AddNozzleDialog
        dlg = AddNozzleDialog(self)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                self.bit_nozzles.append(data)
                self._bit_refresh_nozzles()

    def _bit_rem_nozzle(self):
        row = self.bit_nzl_table.currentRow()
        if 0 <= row < len(self.bit_nozzles):
            self.bit_nozzles.pop(row)
            self._bit_refresh_nozzles()

    def _bit_clear_nozzles(self):
        self.bit_nozzles.clear()
        self._bit_refresh_nozzles()

    def _bit_refresh_nozzles(self):
        self.bit_nzl_table.setRowCount(0)
        total_tfa = 0
        nzl_summary_parts = []

        for i, n in enumerate(self.bit_nozzles):
            row = self.bit_nzl_table.rowCount()
            self.bit_nzl_table.insertRow(row)
            size = n.get('size', 16)
            qty = n.get('qty', 1)
            area = math.pi / 4 * (size / 32.0) ** 2 * qty
            total_tfa += area

            self.bit_nzl_table.setItem(row, 0, QTableWidgetItem(str(i + 1)))
            self.bit_nzl_table.setItem(row, 1, QTableWidgetItem(f"{size}/32\""))
            self.bit_nzl_table.setItem(row, 2, QTableWidgetItem(str(qty)))
            ai = QTableWidgetItem(f"{area:.4f}")
            ai.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.bit_nzl_table.setItem(row, 3, ai)

            nzl_summary_parts.append(f"{qty}×{size}")

        self.bit_tfa_label.setText(f"TFA: {total_tfa:.4f} in²")
        if nzl_summary_parts:
            self.bit_nzl_summary.setText(f"({' + '.join(nzl_summary_parts)}) /32\"")
        else:
            self.bit_nzl_summary.setText("")

    # ========== Bit - Calculate ==========

    def _bit_calculate(self):
        from core.hydraulics_engine import AdvancedHydraulicsEngine
        gpm = self.bit_gpm.value()
        mw_pcf = self.bit_mw.value()
        mw_ppg = mw_pcf / 7.48
        bit_od = self.bit_od.value()

        # TFA from nozzles (canonical BitEngine.calculate_tfa)
        from core.engineering.core import BitEngine
        try:
            sizes = []
            for n in self.bit_nozzles:
                size = n.get('size', 16)
                qty = n.get('qty', 1)
                sizes.extend([size] * qty)
            tfa = BitEngine.calculate_tfa(sizes)
        except Exception:
            tfa = 0

        if tfa <= 0:
            self.bit_res_dp.setText("❌ Add nozzles first")
            self.bit_reco.setText("")
            return

        bh = AdvancedHydraulicsEngine.calc_bit_hydraulics(gpm, mw_ppg, tfa, bit_od)
        self.bit_res_dp.setText(f"{bh['bit_pressure_drop_psi']:.0f} psi")
        self.bit_res_hhp.setText(f"{bh['bit_hhp']:.1f} HP")
        self.bit_res_hsi.setText(f"{bh['hsi']:.2f} hp/in²")
        self.bit_res_jv.setText(f"{bh['jet_velocity_fps']:.0f} ft/s")
        self.bit_res_if.setText(f"{bh['impact_force_lbs']:.0f} lbs")
        total_nzl_count = sum(n.get('qty', 1) for n in self.bit_nozzles)
        self.bit_res_pct.setText(
            f"{bh['jet_velocity_fps']:.0f} ft/s ({total_nzl_count} nozzles)")

        from core.engineering.engines.mse import MSEEngine
        mse = MSEEngine.calculate(
            wob_lbf=self.bit_wob.value() * 1000.0,
            rpm=self.bit_rpm.value(),
            torque_ft_lbf=self.bit_tq.value(),
            rop_ft_hr=self.bit_rop.value(),
            bit_diameter_in=bit_od,
        )
        if mse.success:
            self.bit_res_mse.setText(f"{mse.value:,.0f} psi")
        else:
            self.bit_res_mse.setText(f"❌ {mse.error}")

        # Engineering recommendation (grounded field ranges; no invented inputs)
        reco = []
        hsi = bh['hsi']
        jv = bh['jet_velocity_fps']
        if hsi < 2.0:
            reco.append(f"HSI {hsi:.2f} hp/in² is low (< 2.0) — weak bottom-hole "
                        "cleaning; reduce TFA (smaller nozzles) or increase flow.")
        elif hsi <= 7.0:
            reco.append(f"HSI {hsi:.2f} hp/in² is in the typical 2–7 hp/in² range.")
        else:
            reco.append(f"HSI {hsi:.2f} hp/in² is high (> 7.0) — possible "
                        "bit/formation erosion; increase TFA.")
        if jv < 300:
            reco.append(f"Jet velocity {jv:.0f} ft/s is below 300 ft/s — "
                        "marginal bit cleaning; reduce TFA.")
        elif jv > 450:
            reco.append(f"Jet velocity {jv:.0f} ft/s exceeds 450 ft/s — "
                        "erosion risk; increase TFA.")
        else:
            reco.append(f"Jet velocity {jv:.0f} ft/s is in the 300–450 ft/s target band.")
        reco.append("Use the 🌀 Nozzle Optimization sub-tab to pick the optimum "
                    "TFA (Max Bit HP vs Max Impact Force) for the available HHP.")
        self.bit_reco.setText("💡 " + " ".join(reco))

    # ========== Bit - Nozzle Optimization ==========

    def _bit_optimize(self):
        model = "HP" if self.opt_hp_model.isChecked() else "IF"
        result = self.engine.optimize_nozzles(
            hhp=self.opt_hhp.value(),
            max_press=self.opt_max_press.value(),
            fr1=self.opt_fr1.value(),
            spp1=self.opt_spp1.value(),
            fr2=self.opt_fr2.value(),
            spp2=self.opt_spp2.value(),
            prev_tfa=self.opt_tfa.value(),
            mw=self.opt_mw.value(),
            n_nozzles=self.opt_n_nzl.value(),
            model=model,
        )

        nozzles = result.get("selected_nozzles", [])
        combo_str = " + ".join(f"{s}/32\"" for s in nozzles)

        text = "╔═══════════════════════════════════════════╗\n"
        text += "║       NOZZLE OPTIMIZATION RESULTS         ║\n"
        text += "╠═══════════════════════════════════════════╣\n"
        text += f"║ Model:              {model} Model\n"
        text += f"║ Max Flow Rate:      {result['max_flow_rate_gpm']:.1f} gpm\n"
        text += f"║ Optimal Flow Rate:  {result['optimal_flow_rate_gpm']:.1f} gpm\n"
        text += f"║ Target TFA:         {result['optimal_tfa_in2']:.4f} in²\n"
        text += f"╠═══════════════════════════════════════════╣\n"
        text += f"║ SELECTED NOZZLES:\n"
        text += f"║   {combo_str}\n"
        text += f"║ Actual TFA:         {result['actual_tfa_in2']:.4f} in²\n"
        text += f"║ TFA Error:          {result['tfa_error']:.4f} in²\n"
        text += "╚═══════════════════════════════════════════╝"

        self.opt_results.setText(text)

    # ========== Bit - TFA from ΔP ==========

    def _bit_calc_tfa(self):
        tfa = self.engine.calc_tfa_from_pressure(
            gpm=self.tfa_gpm.value(),
            mw=self.tfa_mw.value(),
            delta_p=self.tfa_dp.value(),
        )
        self.tfa_result.setText(f"{tfa:.4f} in²")
        
    def _create_weight_tab(self) -> QWidget:
        """تب وزن - حرفه‌ای با دیالوگ"""
        self.wt_pipes = []

        tab, container, layout = self._make_scroll_tab()

        # Drill String
        g_ds = QGroupBox("🔩 Drill String Components")
        ds_lay = QVBoxLayout(g_ds)
        ds_btns = QHBoxLayout()
        add_btn = QPushButton("➕ Add Component")
        add_btn.setStyleSheet("background: #27ae60; color: white; padding: 4px 10px; border-radius: 3px; border: none;")
        add_btn.clicked.connect(self._wt_add_pipe)
        edit_btn = QPushButton("✏️ Edit")
        edit_btn.clicked.connect(self._wt_edit_pipe)
        rem_btn = QPushButton("🗑️")
        rem_btn.setFixedWidth(30)
        rem_btn.clicked.connect(self._wt_rem_pipe)
        ds_btns.addWidget(add_btn)
        ds_btns.addWidget(edit_btn)
        ds_btns.addWidget(rem_btn)
        ds_btns.addStretch()
        ds_lay.addLayout(ds_btns)

        self.wt_pipe_table = QTableWidget(0, 6)
        self.wt_pipe_table.setHorizontalHeaderLabels(["Type", "OD", "ID", "Length(m)", "Wt(ppf)", "Total(lbs)"])
        self.wt_pipe_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.wt_pipe_table.setMaximumHeight(180)
        self.wt_pipe_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.wt_pipe_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.wt_pipe_table.doubleClicked.connect(self._wt_edit_pipe)
        ds_lay.addWidget(self.wt_pipe_table)
        layout.addWidget(g_ds)

        # Parameters
        g_params = QGroupBox("⚙️ Parameters")
        pf = QFormLayout(g_params)
        self.wt_tds = self._make_dspin(58, 0, 500, 1, " klbs")
        self.wt_mw = self._make_dspin(90, 0, 200, 1, " pcf")
        self.wt_inc = self._make_dspin(0, 0, 90, 1, " °")
        self.wt_friction = self._make_dspin(0, 0, 1, 3)
        pf.addRow("TDS/Block Wt:", self.wt_tds)
        pf.addRow("Mud Weight:", self.wt_mw)
        pf.addRow("Inclination:", self.wt_inc)
        pf.addRow("Friction Factor:", self.wt_friction)
        self.wt_hole = self._make_dspin(8.5, 0, 30, 3, " in")
        self.wt_wob = self._make_dspin(0, 0, 200, 1, " klbf")
        pf.addRow("Hole ID (T&D buckling):", self.wt_hole)
        pf.addRow("WOB (T&D):", self.wt_wob)

        calc_btn = QPushButton("🔄 Calculate Hook Load")
        calc_btn.setStyleSheet("background: #3498db; color: white; font-weight: bold; padding: 8px; border-radius: 4px; border: none;")
        calc_btn.clicked.connect(self._wt_calculate)
        pf.addRow(calc_btn)
        layout.addWidget(g_params)

        # Results
        g_res = QGroupBox("📊 Results")
        res_grid = QGridLayout(g_res)

        self.wt_air = self._result_label("#e74c3c")
        self.wt_mud = self._result_label("#3498db")
        self.wt_hl = self._result_label("#27ae60")
        self.wt_buoy = self._result_label("#9b59b6")
        self.wt_pickup = self._result_label("#e67e22")
        self.wt_slackoff = self._result_label("#1abc9c")

        res_grid.addWidget(QLabel("String Wt (Air):"), 0, 0)
        res_grid.addWidget(self.wt_air, 0, 1)
        res_grid.addWidget(QLabel("String Wt (Mud):"), 0, 2)
        res_grid.addWidget(self.wt_mud, 0, 3)
        res_grid.addWidget(QLabel("Hook Load:"), 1, 0)
        res_grid.addWidget(self.wt_hl, 1, 1)
        res_grid.addWidget(QLabel("Buoyancy Factor:"), 1, 2)
        res_grid.addWidget(self.wt_buoy, 1, 3)
        res_grid.addWidget(QLabel("Pick-Up Wt:"), 2, 0)
        res_grid.addWidget(self.wt_pickup, 2, 1)
        res_grid.addWidget(QLabel("Slack-Off Wt:"), 2, 2)
        res_grid.addWidget(self.wt_slackoff, 2, 3)
        self.wt_td = self._result_label("#8e44ad")
        res_grid.addWidget(QLabel("T&D screening:"), 3, 0)
        res_grid.addWidget(self.wt_td, 3, 1, 1, 3)

        layout.addWidget(g_res)
        layout.addStretch()
        return tab

    # ========== Weight Methods ==========

    def _wt_add_pipe(self):
        from dialogs.engineering_dialogs import AddPipeDialog
        dlg = AddPipeDialog(self)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                self.wt_pipes.append(data)
                self._wt_refresh_table()

    def _wt_edit_pipe(self):
        row = self.wt_pipe_table.currentRow()
        if 0 <= row < len(self.wt_pipes):
            from dialogs.engineering_dialogs import AddPipeDialog
            dlg = AddPipeDialog(self, edit_data=self.wt_pipes[row])
            if dlg.exec():
                data = dlg.get_result()
                if data:
                    self.wt_pipes[row] = data
                    self._wt_refresh_table()

    def _wt_rem_pipe(self):
        row = self.wt_pipe_table.currentRow()
        if 0 <= row < len(self.wt_pipes):
            self.wt_pipes.pop(row)
            self._wt_refresh_table()

    def _wt_refresh_table(self):
        self.wt_pipe_table.setRowCount(0)
        for p in self.wt_pipes:
            row = self.wt_pipe_table.rowCount()
            self.wt_pipe_table.insertRow(row)
            wt_ppf = p.get('weight', 0)
            L_ft = p.get('length', 0) * 3.28084
            total_lbs = wt_ppf * L_ft

            self.wt_pipe_table.setItem(row, 0, QTableWidgetItem(p.get('type', '')))
            self.wt_pipe_table.setItem(row, 1, QTableWidgetItem(f"{p.get('od', 0):.3f}\""))
            self.wt_pipe_table.setItem(row, 2, QTableWidgetItem(f"{p.get('id', 0):.3f}\""))
            self.wt_pipe_table.setItem(row, 3, QTableWidgetItem(f"{p.get('length', 0):.1f}"))
            self.wt_pipe_table.setItem(row, 4, QTableWidgetItem(f"{wt_ppf:.1f}"))
            ti = QTableWidgetItem(f"{total_lbs:,.0f}")
            ti.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.wt_pipe_table.setItem(row, 5, ti)

    def _wt_calculate(self):
        mw = self.wt_mw.value()
        inc = self.wt_inc.value()
        tds = self.wt_tds.value()
        ff = self.wt_friction.value()
        inc_rad = math.radians(inc)

        # Total weight in air
        total_lbs = 0
        for p in self.wt_pipes:
            wt = p.get('weight', 0)
            L_ft = p.get('length', 0) * 3.28084
            total_lbs += wt * L_ft

        # Buoyancy factor
        bf = 1 - (mw / 489.5)

        # String weight
        wt_air_klbs = total_lbs * math.cos(inc_rad) / 1000
        wt_mud_klbs = wt_air_klbs * bf

        # Hook load
        hook_load = wt_mud_klbs + tds

        # Pick-up & Slack-off (with friction)
        drag = wt_mud_klbs * ff * math.sin(inc_rad)
        pickup = hook_load + drag
        slackoff = hook_load - drag

        self.wt_air.setText(f"{wt_air_klbs:.1f} Klbs ({total_lbs:,.0f} lbs)")
        self.wt_mud.setText(f"{wt_mud_klbs:.1f} Klbs")
        self.wt_hl.setText(f"{hook_load:.1f} Klbs")
        self.wt_buoy.setText(f"{bf:.4f}")
        self.wt_pickup.setText(f"{pickup:.1f} Klbs (w/ friction)")
        self.wt_slackoff.setText(f"{slackoff:.1f} Klbs (w/ friction)")

        # Canonical T&D screening (Johancsik). Vertical if no surveys.
        self._wt_run_td()

    def _wt_run_td(self):
        from core.engineering.engines.torque_drag import TorqueDragEngine
        if not self.wt_pipes:
            self.wt_td.setText("--")
            return
        string = []
        for p in self.wt_pipes:
            string.append({
                "name": p.get("type") or "pipe",
                "od": p.get("od"),
                "id": p.get("id"),
                "length": p.get("length"),
                "weight": p.get("weight"),
            })
        surveys = []
        if getattr(self, "dd_surveys", None):
            surveys = [
                {"md": s.get("md", 0), "inc": s.get("inc", 0), "azi": s.get("azi", 0)}
                for s in self.dd_surveys
            ]
        else:
            total_m = sum(p.get("length", 0) or 0 for p in self.wt_pipes)
            inc = self.wt_inc.value()
            surveys = [
                {"md": 0.0, "inc": inc, "azi": 0.0},
                {"md": max(total_m, 1.0), "inc": inc, "azi": 0.0},
            ]
        r = TorqueDragEngine.calculate(
            surveys,
            string,
            mud_density_ppg=self.wt_mw.value() / 7.48,
            friction_factor=self.wt_friction.value(),
            wob_klbf=self.wt_wob.value(),
            wellbore_id_in=self.wt_hole.value() or None,
        )
        if not r.success:
            self.wt_td.setText(f"❌ {r.error}")
            return
        v = r.values
        buck = "buckling" if v.get("buckling", {}).get("any") else "no buckling flag"
        np = v.get("neutral_point_md_m")
        np_s = f"{np:.0f} m" if np is not None else "n/a"
        self.wt_td.setText(
            f"PU {v['hookload_pickup']:.1f} / SO {v['hookload_slackoff']:.1f} / "
            f"ROT {v['hookload_rotating']:.1f} klbf | "
            f"TQ {v['surface_torque_rotating_ft_lbf']:.0f} ft-lbf | "
            f"stretch {v.get('stretch_rotating_in')} in | "
            f"twist {v.get('twist_rotating_deg')}° | NP {np_s} | {buck}  [SCREENING]"
        )
        
    def _create_stuck_tab(self) -> QWidget:
        tab, container, layout = self._make_scroll_tab()

        # Free Point
        g1 = QGroupBox("Free Point (Differential Sticking)")
        f1 = QFormLayout(g1)
        self.stk_diff = self._make_dspin(500, 0, 5000, 0, " psi")
        self.stk_wt = self._make_dspin(22, 0, 500, 2, " lb/ft")
        self.stk_pull = self._make_dspin(100000, 0, 2000000, 0, " lbs")
        f1.addRow("Differential Stretch:", self.stk_diff)
        f1.addRow("Pipe Weight:", self.stk_wt)
        f1.addRow("Pull Force:", self.stk_pull)
        self.stk_free_point = QLabel("Free Point = --")
        self.stk_free_point.setStyleSheet("font-weight: bold; color: #e74c3c; padding: 5px; border: 1px solid #e74c3c; border-radius: 3px;")
        f1.addRow(self.stk_free_point)
        for w in [self.stk_diff, self.stk_wt, self.stk_pull]:
            w.valueChanged.connect(self._update_stuck)
        layout.addWidget(g1)

        # String Stretch
        g2 = QGroupBox("String Stretch")
        f2 = QFormLayout(g2)
        self.stk_len = self._make_dspin(1000, 0, 20000, 0, " m")
        self.stk_mw = self._make_dspin(90, 0, 200, 1, " pcf")
        f2.addRow("String Length:", self.stk_len)
        f2.addRow("Mud Weight:", self.stk_mw)
        self.stk_stretch = QLabel("Stretch = --")
        self.stk_stretch.setStyleSheet("font-weight: bold; color: #f39c12; padding: 5px; border: 1px solid #f39c12; border-radius: 3px;")
        f2.addRow(self.stk_stretch)
        for w in [self.stk_len, self.stk_mw]:
            w.valueChanged.connect(self._update_stuck)
        layout.addWidget(g2)

        # Adjusted Weight
        g3 = QGroupBox("Adjusted Pipe Weight")
        f3 = QFormLayout(g3)
        self.stk_pipe_od = self._make_dspin(5.0, 0, 30, 3, " in")
        self.stk_pipe_id = self._make_dspin(4.276, 0, 30, 3, " in")
        f3.addRow("Pipe OD:", self.stk_pipe_od)
        f3.addRow("Pipe ID:", self.stk_pipe_id)
        self.stk_adj_wt = QLabel("Adjusted Weight = --")
        self.stk_adj_wt.setStyleSheet("font-weight: bold; color: #2ecc71; padding: 5px; border: 1px solid #2ecc71; border-radius: 3px;")
        f3.addRow(self.stk_adj_wt)
        for w in [self.stk_pipe_od, self.stk_pipe_id]:
            w.valueChanged.connect(self._update_stuck)
        layout.addWidget(g3)

        layout.addStretch()
        return tab
        
    def _create_mud_tab(self) -> QWidget:
        """تب Mud - حرفه‌ای"""
        tab, container, layout = self._make_scroll_tab()

        inner_tabs = QTabWidget()
        layout.addWidget(inner_tabs)

        # ===== Weight Up / Dilution / Mix =====
        wdm_tab = QWidget()
        wdm_layout = QVBoxLayout(wdm_tab)

        g1 = QGroupBox("⬆️ Weight Up (Barite Addition)")
        f1 = QFormLayout(g1)
        self.mud_wu_cur = self._make_dspin(80, 0, 200, 1, " pcf")
        self.mud_wu_tar = self._make_dspin(90, 0, 200, 1, " pcf")
        self.mud_wu_vol = self._make_dspin(500, 0, 10000, 0, " bbl")
        self.mud_wu_additive = QComboBox()
        self.mud_wu_additive.addItems(["Barite (1470 pcf)", "Calcium Carbonate (170 pcf)", "Hematite (320 pcf)"])
        f1.addRow("Current MW:", self.mud_wu_cur)
        f1.addRow("Target MW:", self.mud_wu_tar)
        f1.addRow("System Volume:", self.mud_wu_vol)
        f1.addRow("Additive:", self.mud_wu_additive)
        b1 = QPushButton("🔄 Calculate")
        b1.setStyleSheet("background: #27ae60; color: white; padding: 6px; border-radius: 3px; border: none;")
        b1.clicked.connect(self._mud_wu)
        f1.addRow(b1)
        self.mud_wu_res = self._result_label("#27ae60")
        f1.addRow(self.mud_wu_res)
        wdm_layout.addWidget(g1)

        g2 = QGroupBox("⬇️ Dilution (Water Addition)")
        f2 = QFormLayout(g2)
        self.mud_dil_cur = self._make_dspin(90, 0, 200, 1, " pcf")
        self.mud_dil_tar = self._make_dspin(80, 0, 200, 1, " pcf")
        self.mud_dil_vol = self._make_dspin(500, 0, 10000, 0, " bbl")
        f2.addRow("Current MW:", self.mud_dil_cur)
        f2.addRow("Target MW:", self.mud_dil_tar)
        f2.addRow("System Volume:", self.mud_dil_vol)
        b2 = QPushButton("🔄 Calculate")
        b2.setStyleSheet("background: #3498db; color: white; padding: 6px; border-radius: 3px; border: none;")
        b2.clicked.connect(self._mud_dil)
        f2.addRow(b2)
        self.mud_dil_res = self._result_label("#3498db")
        f2.addRow(self.mud_dil_res)
        wdm_layout.addWidget(g2)

        g3 = QGroupBox("🔄 Mud Mixing")
        f3 = QFormLayout(g3)
        self.mud_m1_mw = self._make_dspin(80, 0, 200, 1, " pcf")
        self.mud_m1_vol = self._make_dspin(300, 0, 10000, 0, " bbl")
        self.mud_m2_mw = self._make_dspin(100, 0, 200, 1, " pcf")
        self.mud_m2_vol = self._make_dspin(200, 0, 10000, 0, " bbl")
        f3.addRow("Mud 1 MW:", self.mud_m1_mw)
        f3.addRow("Mud 1 Vol:", self.mud_m1_vol)
        f3.addRow("Mud 2 MW:", self.mud_m2_mw)
        f3.addRow("Mud 2 Vol:", self.mud_m2_vol)
        b3 = QPushButton("🔄 Mix")
        b3.setStyleSheet("background: #9b59b6; color: white; padding: 6px; border-radius: 3px; border: none;")
        b3.clicked.connect(self._mud_mix)
        f3.addRow(b3)
        self.mud_mix_res = self._result_label("#9b59b6")
        f3.addRow(self.mud_mix_res)
        wdm_layout.addWidget(g3)

        wdm_layout.addStretch()
        inner_tabs.addTab(wdm_tab, "⬆️⬇️ Weight/Dilution/Mix")

        # ===== Rheology =====
        rh_tab = QWidget()
        rh_layout = QVBoxLayout(rh_tab)

        g4 = QGroupBox("🧪 Rheology Calculator")
        f4 = QFormLayout(g4)
        self.rh_t600 = self._make_dspin(45, 0, 500, 0)
        self.rh_t300 = self._make_dspin(25, 0, 500, 0)
        self.rh_t200 = self._make_dspin(18, 0, 500, 0)
        self.rh_t100 = self._make_dspin(12, 0, 500, 0)
        self.rh_t6 = self._make_dspin(4, 0, 100, 0)
        self.rh_t3 = self._make_dspin(3, 0, 100, 0)
        self.rh_gel10s = self._make_dspin(5, 0, 100, 0)
        self.rh_gel10m = self._make_dspin(12, 0, 100, 0)
        self.rh_mw = self._make_dspin(90, 0, 200, 1, " pcf")

        f4.addRow("θ600:", self.rh_t600)
        f4.addRow("θ300:", self.rh_t300)
        f4.addRow("θ200:", self.rh_t200)
        f4.addRow("θ100:", self.rh_t100)
        f4.addRow("θ6:", self.rh_t6)
        f4.addRow("θ3:", self.rh_t3)
        f4.addRow("Gel 10s:", self.rh_gel10s)
        f4.addRow("Gel 10m:", self.rh_gel10m)
        f4.addRow("MW:", self.rh_mw)

        rh_calc = QPushButton("🔄 Calculate Rheology")
        rh_calc.setStyleSheet("background: #e67e22; color: white; font-weight: bold; padding: 8px; border-radius: 4px; border: none;")
        rh_calc.clicked.connect(self._mud_rheo)
        f4.addRow(rh_calc)

        self.rh_result = QTextEdit()
        self.rh_result.setReadOnly(True)
        self.rh_result.setMinimumHeight(250)
        self.rh_result.setStyleSheet("font-family: Consolas; font-size: 11px; background: #1e1e2e; color: #ecf0f1;")
        f4.addRow(self.rh_result)

        rh_layout.addWidget(g4)
        rh_layout.addStretch()
        inner_tabs.addTab(rh_tab, "🧪 Rheology")

        # ===== OWR =====
        owr_tab = QWidget()
        owr_layout = QVBoxLayout(owr_tab)

        g5 = QGroupBox("🛢️ Oil/Water Ratio & Solids")
        f5 = QFormLayout(g5)
        self.mud_oil = self._make_dspin(70, 0, 100, 1, " %")
        self.mud_water = self._make_dspin(30, 0, 100, 1, " %")
        f5.addRow("Oil %:", self.mud_oil)
        f5.addRow("Water %:", self.mud_water)
        self.mud_owr_res = self._result_label("#e67e22")
        f5.addRow("OWR:", self.mud_owr_res)
        self.mud_oil.valueChanged.connect(self._mud_owr)
        self.mud_water.valueChanged.connect(self._mud_owr)

        owr_layout.addWidget(g5)
        owr_layout.addStretch()
        inner_tabs.addTab(owr_tab, "🛢️ OWR")

        # ===== Mud Lab (MBT / LSRYP / Excess Lime / Slug) =====
        ml_tab = QWidget()
        ml_layout = QVBoxLayout(ml_tab)

        g6 = QGroupBox("🧪 MBT — Bentonite Equivalent (API RP 13B-1)")
        f6 = QFormLayout(g6)
        self.ml_mb_ml = self._make_dspin(5, 0, 50, 1, " mL")
        self.ml_sample_ml = self._make_dspin(2, 0.5, 10, 1, " mL")
        f6.addRow("Methylene blue used:", self.ml_mb_ml)
        f6.addRow("Mud sample volume:", self.ml_sample_ml)
        b6 = QPushButton("🔄 MBT = 5 × V_MB / V_sample")
        b6.setStyleSheet("background: #16a085; color: white; font-weight: bold; padding: 6px; border-radius: 4px; border: none;")
        b6.clicked.connect(self._mud_lab)
        f6.addRow(b6)
        self.ml_mbt_res = self._result_label("#16a085")
        f6.addRow("Bentonite equiv:", self.ml_mbt_res)
        ml_layout.addWidget(g6)

        g7 = QGroupBox("📉 LSRYP (Low-Shear-Rate Yield Point)")
        f7 = QFormLayout(g7)
        self.ml_th3 = self._make_dspin(6, 0, 100, 1, "")
        self.ml_th6 = self._make_dspin(4, 0, 100, 1, "")
        f7.addRow("θ3 reading:", self.ml_th3)
        f7.addRow("θ6 reading:", self.ml_th6)
        self.ml_lsryp_res = self._result_label("#8e44ad")
        f7.addRow("LSRYP = 2·θ3 − θ6:", self.ml_lsryp_res)
        self.ml_th3.valueChanged.connect(self._mud_lab_lsryp)
        self.ml_th6.valueChanged.connect(self._mud_lab_lsryp)
        ml_layout.addWidget(g7)

        g8 = QGroupBox("🕯️ Excess Lime (OBM/SBM, from POM)")
        f8 = QFormLayout(g8)
        self.ml_pom = self._make_dspin(2.5, 0, 20, 2, " mL")
        f8.addRow("POM (mL 0.1N H₂SO₄):", self.ml_pom)
        self.ml_lime_res = self._result_label("#d35400")
        f8.addRow("Excess lime = 1.295·POM:", self.ml_lime_res)
        self.ml_pom.valueChanged.connect(self._mud_lab_lime)
        ml_layout.addWidget(g8)

        g9 = QGroupBox("🧱 Weighted Slug — Dry Pipe Length")
        f9 = QFormLayout(g9)
        self.ml_slug_vol = self._make_dspin(20, 0, 200, 0, " bbl")
        self.ml_slug_mw = self._make_dspin(12.5, 8, 25, 1, " ppg")
        self.ml_mud_mw = self._make_dspin(10, 8, 25, 1, " ppg")
        self.ml_pipe_cap = self._make_dspin(0.01776, 0.005, 0.1, 5, " bbl/ft")
        f9.addRow("Slug volume:", self.ml_slug_vol)
        f9.addRow("Slug MW:", self.ml_slug_mw)
        f9.addRow("Mud MW:", self.ml_mud_mw)
        f9.addRow("Pipe capacity:", self.ml_pipe_cap)
        b9 = QPushButton("🔄 Slug Dry Length")
        b9.setStyleSheet("background: #2980b9; color: white; font-weight: bold; padding: 6px; border-radius: 4px; border: none;")
        b9.clicked.connect(self._mud_lab_slug)
        f9.addRow(b9)
        self.ml_slug_res = self._result_label("#2980b9")
        f9.addRow("Dry pipe:", self.ml_slug_res)
        ml_layout.addWidget(g9)

        g10 = QGroupBox("🦠 Corrosion Rate (Weight-Loss Coupon, API RP 13B-1)")
        f10 = QFormLayout(g10)
        self.ml_cr_w = self._make_dspin(100, 0, 10000, 1, " mg")
        self.ml_cr_a = self._make_dspin(3.0, 0.1, 100, 2, " in²")
        self.ml_cr_t = self._make_dspin(168, 1, 10000, 0, " hr")
        self.ml_cr_d = self._make_dspin(7.86, 2, 20, 2, " g/cm³")
        f10.addRow("Coupon weight loss:", self.ml_cr_w)
        f10.addRow("Coupon area:", self.ml_cr_a)
        f10.addRow("Exposure time:", self.ml_cr_t)
        f10.addRow("Coupon density:", self.ml_cr_d)
        b10 = QPushButton("🔄 mpy = 534·W/(A·T·D)")
        b10.setStyleSheet("background: #c0392b; color: white; font-weight: bold; padding: 6px; border-radius: 4px; border: none;")
        b10.clicked.connect(self._mud_lab_corrosion)
        f10.addRow(b10)
        self.ml_cr_res = self._result_label("#c0392b")
        f10.addRow("Corrosion rate:", self.ml_cr_res)
        ml_layout.addWidget(g10)

        ml_layout.addStretch()
        inner_tabs.addTab(ml_tab, "🧪 Mud Lab")

        return tab

    # ========== Mud Methods ==========

    def _mud_wu(self):
        additive_densities = {"Barite": 1470, "Calcium Carbonate": 170, "Hematite": 320}
        selected = self.mud_wu_additive.currentText()
        density = 1470
        for name, d in additive_densities.items():
            if name in selected:
                density = d
                break

        r = self.engine.calc_mud_weight_increase(
            self.mud_wu_cur.value(), self.mud_wu_tar.value(),
            self.mud_wu_vol.value(), density
        )
        if "error" in r:
            self.mud_wu_res.setText(f"❌ {r['error']}")
        else:
            self.mud_wu_res.setText(
                f"Additive: {r['sacks_barite']:.0f} sacks\n"
                f"Volume Increase: {r['volume_increase_bbl']:.1f} bbl\n"
                f"Final Volume: {r['final_volume_bbl']:.1f} bbl"
            )

    def _mud_dil(self):
        r = self.engine.calc_mud_dilution(
            self.mud_dil_cur.value(), self.mud_dil_tar.value(), self.mud_dil_vol.value(),
            62.4,
        )
        if "error" in r:
            self.mud_dil_res.setText(f"❌ {r['error']}")
        else:
            self.mud_dil_res.setText(
                f"Water Required: {r['water_required_bbl']:.1f} bbl\n"
                f"Final Volume: {r['final_volume_bbl']:.1f} bbl"
            )

    def _mud_mix(self):
        r = self.engine.calc_mud_mixing(
            self.mud_m1_mw.value(), self.mud_m1_vol.value(),
            self.mud_m2_mw.value(), self.mud_m2_vol.value()
        )
        if "error" in r:
            self.mud_mix_res.setText(f"❌ {r['error']}")
        else:
            ppg = r['final_mw_pcf'] / 7.48
            self.mud_mix_res.setText(
                f"Final MW: {r['final_mw_pcf']:.1f} pcf ({ppg:.2f} ppg)\n"
                f"Total Volume: {r['total_volume_bbl']:.1f} bbl"
            )

    def _mud_rheo(self):
        t600 = self.rh_t600.value()
        t300 = self.rh_t300.value()
        t200 = self.rh_t200.value()
        t100 = self.rh_t100.value()
        t6 = self.rh_t6.value()
        t3 = self.rh_t3.value()
        gel10s = self.rh_gel10s.value()
        gel10m = self.rh_gel10m.value()
        mw = self.rh_mw.value()
        mw_ppg = mw / 7.48

        # Bingham
        pv = t600 - t300
        yp = t300 - pv

        # Power Law
        if t300 > 0 and t600 > 0:
            n = 3.32 * math.log10(t600 / t300)
            k = t300 / (511 ** n) * 511
        else:
            n = 1.0
            k = 1.0

        # Herschel-Bulkley
        tau_y = max(0, 2 * t3 - t6)

        # Effective viscosity
        eff_vis = pv + 5 * yp if pv > 0 else 0

        text = f"""╔═══════════════════════════════════════════╗
    ║          RHEOLOGY ANALYSIS                ║
    ╠═══════════════════════════════════════════╣
    ║ Mud Weight: {mw:.1f} pcf ({mw_ppg:.2f} ppg)
    ╠═══════════════════════════════════════════╣
    ║ FANN READINGS:
    ║   θ600: {t600}  │  θ300: {t300}
    ║   θ200: {t200}  │  θ100: {t100}
    ║   θ6:   {t6}    │  θ3:   {t3}
    ║   Gel 10s: {gel10s}  │  Gel 10m: {gel10m}
    ╠═══════════════════════════════════════════╣
    ║ BINGHAM PLASTIC MODEL:
    ║   PV:  {pv:.1f} cp
    ║   YP:  {yp:.1f} lb/100ft²
    ║   PV/YP Ratio: {pv/yp:.2f}
    ╠═══════════════════════════════════════════╣
    ║ POWER LAW MODEL:
    ║   n (flow behavior):    {n:.4f}
    ║   K (consistency):      {k:.4f}
    ╠═══════════════════════════════════════════╣
    ║ HERSCHEL-BULKLEY MODEL:
    ║   τ₀ (yield stress):    {tau_y:.1f}
    ╠═══════════════════════════════════════════╣
    ║ ANALYSIS:
    ║   Effective Viscosity:  {eff_vis:.1f} cp
    ║   {'✅ Good PV/YP ratio' if 0.5 < pv/yp < 2 else '⚠️ Check PV/YP ratio'}
    ║   {'✅ Good gel strength' if gel10m/gel10s < 3 else '⚠️ Progressive gels - check mud'}
    ╚═══════════════════════════════════════════╝""" if yp > 0 else "⚠️ Invalid readings (YP must > 0)"

        self.rh_result.setText(text)

    def _mud_lab(self):
        """MBT bentonite equivalent — canonical MudEngineering.mbt_bentonite_equiv."""
        from core.engineering.extended import MudEngineering
        try:
            res = MudEngineering.mbt_bentonite_equiv(
                self.ml_mb_ml.value(), self.ml_sample_ml.value())
            self.ml_mbt_res.setText(
                f"{res['mbt_lb_per_bbl']:.1f} lb/bbl bentonite equiv")
        except Exception as ex:
            self.ml_mbt_res.setText(f"⚠️ {ex}")

    def _mud_lab_lsryp(self):
        from core.engineering.extended import MudEngineering
        res = MudEngineering.lsryp(self.ml_th3.value(), self.ml_th6.value())
        warn = f" — ⚠️ {res['warning']}" if res.get("warning") else ""
        self.ml_lsryp_res.setText(
            f"{res['lsryp_lb_per_100ft2']:.2f} lb/100ft²{warn}")

    def _mud_lab_lime(self):
        from core.engineering.extended import MudEngineering
        try:
            res = MudEngineering.excess_lime_obm(self.ml_pom.value())
            self.ml_lime_res.setText(
                f"{res['excess_lime_lb_per_bbl']:.2f} lb/bbl")
        except Exception as ex:
            self.ml_lime_res.setText(f"⚠️ {ex}")

    def _mud_lab_corrosion(self):
        from core.engineering.extended import MudEngineering
        try:
            res = MudEngineering.corrosion_rate(
                self.ml_cr_w.value(), self.ml_cr_a.value(),
                self.ml_cr_t.value(), self.ml_cr_d.value())
            self.ml_cr_res.setText(
                f"{res['corrosion_rate_mpy']:.2f} mpy  "
                f"({res['corrosion_rate_lb_ft2_yr']:.4f} lb/ft²/yr) — "
                f"{res['severity']}")
        except Exception as ex:
            self.ml_cr_res.setText(f"⚠️ {ex}")

    def _mud_lab_slug(self):
        from core.engineering.extended import MudEngineering
        try:
            res = MudEngineering.slug_dry_length(
                self.ml_slug_vol.value(), self.ml_slug_mw.value(),
                self.ml_mud_mw.value(), self.ml_pipe_cap.value())
            self.ml_slug_res.setText(
                f"{res['dry_pipe_length_ft']:.0f} ft dry pipe "
                f"(ΔP gain {res['hydrostatic_gain_psi']:.0f} psi)")
        except Exception as ex:
            self.ml_slug_res.setText(f"⚠️ {ex}")

    def _mud_owr(self):
        r = self.engine.calc_oil_water_ratio(self.mud_oil.value(), self.mud_water.value())
        if "error" not in r:
            self.mud_owr_res.setText(f"OWR = {r['OWR']}")
            
    # ==================== Casing/Cement Tab ====================
    def _create_casing_cement_tab(self) -> QWidget:
        """تب CSG/CMT - حرفه‌ای با دیالوگ"""
        tab, container, layout = self._make_scroll_tab()

        inner_tabs = QTabWidget()
        layout.addWidget(inner_tabs)

        # ===== Casing Strength =====
        cs_tab = QWidget()
        cs_layout = QVBoxLayout(cs_tab)

        g1 = QGroupBox("💪 Casing Strength (select from database)")
        g1_lay = QVBoxLayout(g1)

        select_btn = QPushButton("📋 Select Casing from API 5CT Database")
        select_btn.setStyleSheet("background: #3498db; color: white; font-weight: bold; padding: 8px; border-radius: 4px; border: none;")
        select_btn.clicked.connect(self._csg_select_from_db)
        g1_lay.addWidget(select_btn)

        csg_form = QFormLayout()
        self.csg_od = self._make_dspin(9.625, 0, 50, 3, " in")
        self.csg_wt_ppf = self._make_dspin(47, 0, 500, 1, " ppf")
        self.csg_id_calc = self._make_dspin(8.681, 0, 50, 3, " in")
        self.csg_yield = self._make_dspin(80000, 0, 200000, 0, " psi")
        self.csg_wall = self._make_dspin(0.472, 0, 2, 3, " in")

        csg_form.addRow("OD:", self.csg_od)
        csg_form.addRow("Weight:", self.csg_wt_ppf)
        csg_form.addRow("ID:", self.csg_id_calc)
        csg_form.addRow("Yield Strength:", self.csg_yield)
        csg_form.addRow("Wall Thickness:", self.csg_wall)
        self.csg_axial = self._make_dspin(0, -2e6, 2e6, 0, " lbf")
        self.csg_pi = self._make_dspin(0, 0, 20000, 0, " psi")
        self.csg_pe = self._make_dspin(0, 0, 20000, 0, " psi")
        self.csg_conn_burst = self._make_dspin(0, 0, 20000, 0, " psi")
        self.csg_conn_coll = self._make_dspin(0, 0, 20000, 0, " psi")
        self.csg_conn_tens = self._make_dspin(0, 0, 2e6, 0, " lbf")
        csg_form.addRow("Axial tension (opt):", self.csg_axial)
        csg_form.addRow("Internal P (opt):", self.csg_pi)
        csg_form.addRow("External P (opt):", self.csg_pe)
        csg_form.addRow("Connection burst (0=omit):", self.csg_conn_burst)
        csg_form.addRow("Connection collapse (0=omit):", self.csg_conn_coll)
        csg_form.addRow("Connection tension (0=omit):", self.csg_conn_tens)

        calc_csg = QPushButton("🔄 Calculate Casing Strength")
        calc_csg.setStyleSheet("background: #e74c3c; color: white; font-weight: bold; padding: 8px; border-radius: 4px; border: none;")
        calc_csg.clicked.connect(self._csg_calc_strength)
        csg_form.addRow(calc_csg)

        g1_lay.addLayout(csg_form)

        self.csg_burst_res = self._result_label("#e74c3c")
        self.csg_collapse_res = self._result_label("#f39c12")
        self.csg_tensile_res = self._result_label("#3498db")
        self.csg_combined_res = self._result_label("#8e44ad")
        self.csg_vme_res = self._result_label("#16a085")
        g1_lay.addWidget(QLabel("Burst Pressure:"))
        g1_lay.addWidget(self.csg_burst_res)
        g1_lay.addWidget(QLabel("Collapse Pressure:"))
        g1_lay.addWidget(self.csg_collapse_res)
        g1_lay.addWidget(QLabel("Tensile Strength:"))
        g1_lay.addWidget(self.csg_tensile_res)
        g1_lay.addWidget(QLabel("Combined collapse (fyax + Pi):"))
        g1_lay.addWidget(self.csg_combined_res)
        g1_lay.addWidget(QLabel("VME / SF:"))
        g1_lay.addWidget(self.csg_vme_res)

        cs_layout.addWidget(g1)
        cs_layout.addStretch()
        inner_tabs.addTab(cs_tab, "💪 Casing Strength")

        # ===== Cement Volume =====
        cv_tab = QWidget()
        cv_layout = QVBoxLayout(cv_tab)

        g2 = QGroupBox("🧱 Cement Volume Calculator")
        f2 = QFormLayout(g2)
        self.cmt_hole = self._make_dspin(12.25, 0, 50, 3, " in")
        self.cmt_csg = self._make_dspin(9.625, 0, 50, 3, " in")
        self.cmt_len = self._make_dspin(3000, 0, 60000, 0, " ft")
        self.cmt_excess = self._make_dspin(50, 0, 200, 0, " %")
        self.cmt_csg_id = self._make_dspin(8.681, 0, 50, 3, " in")
        self.cmt_shoe_track = self._make_dspin(60, 0, 200, 0, " ft")

        f2.addRow("Hole Size:", self.cmt_hole)
        f2.addRow("Casing OD:", self.cmt_csg)
        f2.addRow("Cement Length:", self.cmt_len)
        f2.addRow("Excess %:", self.cmt_excess)
        f2.addRow("Casing ID:", self.cmt_csg_id)
        f2.addRow("Shoe Track:", self.cmt_shoe_track)
        self.cmt_yield = self._make_dspin(0, 0, 5, 3, " ft³/sk")
        self.cmt_dens = self._make_dspin(0, 0, 25, 2, " ppg")
        self.cmt_spacer_len = self._make_dspin(0, 0, 5000, 0, " ft")
        self.cmt_spacer_mw = self._make_dspin(0, 0, 25, 2, " ppg")
        self.cmt_lead_len = self._make_dspin(0, 0, 20000, 0, " ft")
        self.cmt_lead_mw = self._make_dspin(0, 0, 25, 2, " ppg")
        self.cmt_tail_len = self._make_dspin(0, 0, 20000, 0, " ft")
        self.cmt_tail_mw = self._make_dspin(0, 0, 25, 2, " ppg")
        self.cmt_shoe_tvd = self._make_dspin(0, 0, 60000, 0, " ft")
        self.cmt_pump = self._make_dspin(0, 0, 50, 2, " bbl/min")
        self.cmt_pore = self._make_dspin(0, 0, 25, 2, " ppg")
        f2.addRow("Slurry yield (0=omit sacks):", self.cmt_yield)
        f2.addRow("Slurry density:", self.cmt_dens)
        f2.addRow("Spacer length:", self.cmt_spacer_len)
        f2.addRow("Spacer MW:", self.cmt_spacer_mw)
        f2.addRow("Lead length:", self.cmt_lead_len)
        f2.addRow("Lead MW:", self.cmt_lead_mw)
        f2.addRow("Tail length:", self.cmt_tail_len)
        f2.addRow("Tail MW:", self.cmt_tail_mw)
        f2.addRow("Shoe TVD (hydrostatic):", self.cmt_shoe_tvd)
        f2.addRow("Pump rate:", self.cmt_pump)
        f2.addRow("Pore EMW:", self.cmt_pore)

        cmt_calc = QPushButton("🔄 Calculate Cement Volumes")
        cmt_calc.setStyleSheet("background: #e67e22; color: white; font-weight: bold; padding: 8px; border-radius: 4px; border: none;")
        cmt_calc.clicked.connect(self._csg_calc_cement)
        f2.addRow(cmt_calc)

        self.cmt_result = QTextEdit()
        self.cmt_result.setReadOnly(True)
        self.cmt_result.setMinimumHeight(200)
        self.cmt_result.setStyleSheet("font-family: Consolas; font-size: 11px; background: #1e1e2e; color: #ecf0f1;")
        f2.addRow(self.cmt_result)

        cv_layout.addWidget(g2)
        cv_layout.addStretch()
        inner_tabs.addTab(cv_tab, "🧱 Cement Volume")

        # ===== Buoyancy =====
        bf_tab = QWidget()
        bf_layout = QVBoxLayout(bf_tab)

        g3 = QGroupBox("🌊 Buoyancy & Landing Load")
        f3 = QFormLayout(g3)
        self.bf_mw = self._make_dspin(90, 0, 200, 1, " pcf")
        self.bf_csg_wt = self._make_dspin(47, 0, 500, 1, " ppf")
        self.bf_csg_len = self._make_dspin(10000, 0, 60000, 0, " ft")
        self.bf_friction = self._make_dspin(0, 0, 0.5, 3)
        f3.addRow("Mud Weight:", self.bf_mw)
        f3.addRow("Casing Weight:", self.bf_csg_wt)
        f3.addRow("Casing Length:", self.bf_csg_len)
        f3.addRow("Friction Factor:", self.bf_friction)

        bf_calc = QPushButton("🔄 Calculate")
        bf_calc.clicked.connect(self._csg_calc_landing)
        f3.addRow(bf_calc)

        self.bf_result = self._result_label("#1abc9c")
        f3.addRow("Results:", self.bf_result)

        bf_layout.addWidget(g3)
        bf_layout.addStretch()
        inner_tabs.addTab(bf_tab, "🌊 Buoyancy")

        return tab

    # ========== Casing/Cement Methods ==========

    def _csg_select_from_db(self):
        from dialogs.engineering_dialogs import AddCasingDialog
        dlg = AddCasingDialog(self)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                self.csg_od.setValue(data.get('od', 0))
                self.csg_id_calc.setValue(data.get('id', 0))
                self.csg_wt_ppf.setValue(data.get('weight', 0))
                od = data.get('od', 0)
                id_ = data.get('id', 0)
                if od > 0 and id_ > 0:
                    self.csg_wall.setValue((od - id_) / 2)
                if data.get('burst'):
                    self.csg_burst_res.setText(f"{data['burst']:.0f} psi (from API)")
                if data.get('collapse'):
                    self.csg_collapse_res.setText(f"{data['collapse']:.0f} psi (from API)")

    def _csg_calc_strength(self):
        from core.engineering.engines.casing import CasingEngine
        axial = self.csg_axial.value() or None
        pi = self.csg_pi.value() or None
        pe = self.csg_pe.value() or None
        r = CasingEngine.evaluate(
            od_in=self.csg_od.value(),
            id_in=self.csg_id_calc.value(),
            wall_in=self.csg_wall.value(),
            yield_psi=self.csg_yield.value(),
            internal_pressure_psi=pi,
            external_pressure_psi=pe,
            axial_tension_lbf=axial,
            connection_burst_psi=self.csg_conn_burst.value() or None,
            connection_collapse_psi=self.csg_conn_coll.value() or None,
            connection_tension_lbf=self.csg_conn_tens.value() or None,
        )
        if not r.success:
            self.csg_burst_res.setText(f"❌ {r.error}")
            self.csg_collapse_res.setText("")
            self.csg_tensile_res.setText("")
            self.csg_combined_res.setText("")
            self.csg_vme_res.setText("")
            return
        v = r.values
        self.csg_burst_res.setText(
            f"{v['burst_rating_psi']:,.0f} psi  (govern {v['governing_burst_psi']:,.0f})"
        )
        self.csg_collapse_res.setText(
            f"{v['collapse_rating_psi']:,.0f} psi  [{v.get('regime','')}]"
        )
        self.csg_tensile_res.setText(
            f"{v['pipe_body_yield_lbf']:,.0f} lbs ({v['pipe_body_yield_klbf']:,.0f} Klbs)"
        )
        fy = v.get("fyax_psi")
        comb = v.get("collapse_combined_psi")
        self.csg_combined_res.setText(
            f"{comb:,.0f} psi  fyax={fy:,.0f} psi" if comb is not None else "--"
        )
        bits = []
        if v.get("vme_psi") is not None:
            bits.append(f"VME {v['vme_psi']:,.0f} psi (u={v.get('vme_utilization', 0):.3f})")
        if v.get("burst_sf") is not None:
            bits.append(f"burst SF {v['burst_sf']}")
        if v.get("collapse_sf") is not None:
            bits.append(f"collapse SF {v['collapse_sf']}")
        if v.get("tension_sf") is not None:
            bits.append(f"tension SF {v['tension_sf']}")
        warn = "; ".join(r.warnings[:2]) if r.warnings else "PARTIAL pipe-body"
        self.csg_vme_res.setText((" | ".join(bits) + "\n" + warn) if bits else warn)

    def _csg_calc_cement(self):
        from core.engineering.engines.cement import CementEngine
        dens = self.cmt_dens.value() or None
        yield_v = self.cmt_yield.value() or None
        spacer_len = self.cmt_spacer_len.value() or None
        spacer_mw = self.cmt_spacer_mw.value() or None
        lead_len = self.cmt_lead_len.value() or None
        lead_mw = self.cmt_lead_mw.value() or None
        tail_len = self.cmt_tail_len.value() or None
        tail_mw = self.cmt_tail_mw.value() or None
        shoe_tvd = self.cmt_shoe_tvd.value() or None
        pump = self.cmt_pump.value() or None
        pore = self.cmt_pore.value() or None
        r = CementEngine.job_volumes(
            hole_size_in=self.cmt_hole.value(),
            casing_od_in=self.cmt_csg.value(),
            open_hole_length_ft=self.cmt_len.value(),
            excess_pct=self.cmt_excess.value(),
            casing_id_in=self.cmt_csg_id.value() or None,
            shoe_track_ft=self.cmt_shoe_track.value(),
            slurry_density_ppg=dens,
            yield_ft3_sk=yield_v,
            spacer_length_ft=spacer_len,
            spacer_density_ppg=spacer_mw,
            lead_length_ft=lead_len,
            lead_density_ppg=lead_mw,
            tail_length_ft=tail_len,
            tail_density_ppg=tail_mw,
            tvd_column_ft=shoe_tvd,
            shoe_tvd_ft=shoe_tvd,
            tail_tvd_ft=shoe_tvd if tail_mw else None,
            pump_rate_bbl_min=pump,
            pore_emw_ppg=pore,
        )
        if not r.success:
            self.cmt_result.setText(f"❌ {r.error}")
            return
        v = r.values
        sacks = v.get("sacks")
        sacks_s = f"{sacks:.0f}" if sacks is not None else "n/a (need yield)"
        hpsi = v.get("hydrostatic_psi")
        h_s = f"{hpsi:.0f} psi" if hpsi is not None else "n/a"
        pt = v.get("pump_time_min")
        pt_s = f"{pt:.1f} min" if pt is not None else "n/a"
        lead = v.get("lead") or {}
        tail = v.get("tail") or {}
        text = (
            "CEMENT JOB VOLUME / HYDROSTATIC WORKSHEET\n"
            f"Annulus: {v['annular_volume_bbl']:.2f} bbl ({v['annular_volume_cuft']:.1f} cuft)\n"
            f"With {v['excess_pct']}% excess: {v['annular_with_excess_bbl']:.2f} bbl\n"
            f"Shoe track: {v['shoe_track_volume_bbl']:.2f} bbl\n"
            f"Spacer: {v['spacer_volume_bbl']:.2f} bbl\n"
            f"Slurry: {v['slurry_volume_bbl']:.2f} bbl  sacks: {sacks_s}\n"
            f"Displacement: {v.get('displacement_volume_bbl') or 0:.2f} bbl\n"
            f"Total pump: {v['total_pump_bbl']:.2f} bbl  time: {pt_s}\n"
            f"Hydrostatic: {h_s}\n"
            f"Lead: {lead.get('slurry_bbl', '--')} bbl  Tail: {tail.get('slurry_bbl', '--')} bbl\n"
            "NOT laboratory cement design (no UCA / thickening time / gas migration)."
        )
        self.cmt_result.setText(text)

    def _csg_calc_landing(self):
        bf = self.engine.calc_buoyancy_factor(self.bf_mw.value())
        r = self.engine.calc_casing_landing_load(
            self.bf_csg_wt.value(), self.bf_csg_len.value(),
            bf, self.bf_friction.value()
        )
        self.bf_result.setText(
            f"Buoyancy Factor: {bf:.4f}\n"
            f"Air Weight: {r['air_weight_lbs']:,.0f} lbs\n"
            f"Buoyant Weight: {r['buoyant_weight_lbs']:,.0f} lbs\n"
            f"Hook Load: {r['hook_load_lbs']:,.0f} lbs ({r['hook_load_lbs']/1000:,.0f} Klbs)"
        )
        
    # ==================== Well Control Tab ====================
    def _create_well_control_tab(self) -> QWidget:
        """تب Well Control - حرفه‌ای"""
        self.wc_pipes = []
        tab, container, layout = self._make_scroll_tab()

        inner_tabs = QTabWidget()
        layout.addWidget(inner_tabs)

        # ===== Kill Sheet =====
        ks_tab = QWidget()
        ks_scroll = QScrollArea()
        ks_scroll.setWidgetResizable(True)
        ks_container = QWidget()
        ks_layout = QVBoxLayout(ks_container)

        # Well Info
        g_well = QGroupBox("🛢️ Well Information")
        wf = QFormLayout(g_well)
        self.wc_well_type = QComboBox()
        self.wc_well_type.addItems(["Vertical", "Directional", "Horizontal"])
        self.wc_tvd = self._make_dspin(3000, 0, 20000, 0, " m")
        self.wc_md = self._make_dspin(3200, 0, 20000, 0, " m")
        self.wc_shoe_tvd = self._make_dspin(2000, 0, 20000, 0, " m")
        self.wc_shoe_md = self._make_dspin(2050, 0, 20000, 0, " m")
        self.wc_hole_size = self._make_dspin(8.5, 0, 50, 3, " in")
        self.wc_last_csg = self._make_dspin(9.625, 0, 50, 3, " in OD")
        self.wc_last_csg_id = self._make_dspin(8.835, 0, 50, 3, " in ID")
        wf.addRow("Well Type:", self.wc_well_type)
        wf.addRow("TVD:", self.wc_tvd)
        wf.addRow("MD (Bit Depth):", self.wc_md)
        wf.addRow("Shoe TVD:", self.wc_shoe_tvd)
        wf.addRow("Shoe MD:", self.wc_shoe_md)
        wf.addRow("Hole Size:", self.wc_hole_size)
        wf.addRow("Last CSG OD:", self.wc_last_csg)
        wf.addRow("Last CSG ID:", self.wc_last_csg_id)
        ks_layout.addWidget(g_well)

        # Drill String
        g_ds = QGroupBox("🔩 Drill String")
        ds_lay = QVBoxLayout(g_ds)
        ds_btns = QHBoxLayout()
        add_ds = QPushButton("➕ Add Component")
        add_ds.setStyleSheet("background: #27ae60; color: white; padding: 4px 10px; border-radius: 3px; border: none;")
        add_ds.clicked.connect(self._wc_add_pipe)
        edit_ds = QPushButton("✏️")
        edit_ds.setFixedWidth(30)
        edit_ds.clicked.connect(self._wc_edit_pipe)
        rem_ds = QPushButton("🗑️")
        rem_ds.setFixedWidth(30)
        rem_ds.clicked.connect(self._wc_rem_pipe)
        ds_btns.addWidget(add_ds)
        ds_btns.addWidget(edit_ds)
        ds_btns.addWidget(rem_ds)
        ds_btns.addStretch()
        ds_lay.addLayout(ds_btns)

        self.wc_pipe_table = QTableWidget(0, 6)
        self.wc_pipe_table.setHorizontalHeaderLabels(["Type", "OD", "ID", "Len(m)", "Cap(bbl/m)", "Vol(bbl)"])
        self.wc_pipe_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.wc_pipe_table.setMaximumHeight(140)
        self.wc_pipe_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.wc_pipe_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.wc_pipe_table.doubleClicked.connect(self._wc_edit_pipe)
        ds_lay.addWidget(self.wc_pipe_table)

        self.wc_string_summary = QLabel("String: 0 bbl | Annular: 0 bbl")
        self.wc_string_summary.setStyleSheet("font-weight: bold; color: #3498db; padding: 3px;")
        ds_lay.addWidget(self.wc_string_summary)
        ks_layout.addWidget(g_ds)

        # Mud & Kick Data
        g_mud = QGroupBox("🧪 Mud & Kick Data")
        mf = QFormLayout(g_mud)
        self.wc_mw = self._make_dspin(90, 0, 200, 1, " pcf")
        self.wc_frac = self._make_dspin(0.8, 0, 2, 3, " psi/ft")
        self.wc_sidpp = self._make_dspin(500, 0, 10000, 0, " psi")
        self.wc_sicp = self._make_dspin(700, 0, 10000, 0, " psi")
        self.wc_pit_gain = self._make_dspin(10, 0, 500, 0, " bbl")
        mf.addRow("Current MW:", self.wc_mw)
        mf.addRow("Frac Gradient:", self.wc_frac)
        mf.addRow("SIDPP:", self.wc_sidpp)
        mf.addRow("SICP:", self.wc_sicp)
        mf.addRow("Pit Gain:", self.wc_pit_gain)
        ks_layout.addWidget(g_mud)

        # Pump Data
        g_pump = QGroupBox("💧 Pump & SCR Data")
        pf = QFormLayout(g_pump)
        self.wc_scr1 = self._make_dspin(800, 0, 5000, 0, " psi @ SCR")
        self.wc_scr1_spm = self._make_dspin(30, 0, 200, 0, " spm")
        self.wc_scr2 = self._make_dspin(600, 0, 5000, 0, " psi @ SCR")
        self.wc_scr2_spm = self._make_dspin(25, 0, 200, 0, " spm")
        self.wc_pump_output = self._make_dspin(0.09, 0, 1, 5, " bbl/stk")
        pf.addRow("SCR #1 Pressure:", self.wc_scr1)
        pf.addRow("SCR #1 SPM:", self.wc_scr1_spm)
        pf.addRow("SCR #2 Pressure:", self.wc_scr2)
        pf.addRow("SCR #2 SPM:", self.wc_scr2_spm)
        pf.addRow("Pump Output:", self.wc_pump_output)
        ks_layout.addWidget(g_pump)

        # Method
        g_method = QGroupBox("⚙️ Kill Method")
        ml = QHBoxLayout(g_method)
        self.wc_driller = QRadioButton("Driller's Method")
        self.wc_ww = QRadioButton("Wait & Weight")
        self.wc_driller.setChecked(True)
        ml.addWidget(self.wc_driller)
        ml.addWidget(self.wc_ww)
        ks_layout.addWidget(g_method)

        # Calculate
        calc_btn = QPushButton("🛡️ Calculate Complete Kill Sheet")
        calc_btn.setStyleSheet("background: #e74c3c; color: white; font-weight: bold; padding: 12px; border-radius: 5px; border: none; font-size: 14px;")
        calc_btn.clicked.connect(self._wc_calc_kill)
        ks_layout.addWidget(calc_btn)

        # Results
        self.wc_result = QTextEdit()
        self.wc_result.setReadOnly(True)
        self.wc_result.setMinimumHeight(400)
        self.wc_result.setStyleSheet("font-family: Consolas; font-size: 11px; background: #1e1e2e; color: #ecf0f1;")
        ks_layout.addWidget(self.wc_result)

        ks_scroll.setWidget(ks_container)
        ks_tab_layout = QVBoxLayout(ks_tab)
        ks_tab_layout.setContentsMargins(0, 0, 0, 0)
        ks_tab_layout.addWidget(ks_scroll)
        inner_tabs.addTab(ks_tab, "🛡️ Kill Sheet")

        # ===== Choke Schedule =====
        cs_tab = QWidget()
        cs_layout = QVBoxLayout(cs_tab)

        g_cs = QGroupBox("📋 Choke Pressure Schedule")
        cs_form = QFormLayout(g_cs)
        self.cs_icp = self._make_dspin(1200, 0, 10000, 0, " psi")
        self.cs_fcp = self._make_dspin(800, 0, 10000, 0, " psi")
        self.cs_strokes = self._make_dspin(1500, 0, 10000, 0, " strokes")
        self.cs_intervals = QSpinBox()
        self.cs_intervals.setRange(5, 20)
        self.cs_intervals.setValue(10)
        cs_form.addRow("ICP:", self.cs_icp)
        cs_form.addRow("FCP:", self.cs_fcp)
        cs_form.addRow("Strokes to Bit:", self.cs_strokes)
        cs_form.addRow("Intervals:", self.cs_intervals)

        cs_calc = QPushButton("🔄 Generate Schedule")
        cs_calc.setStyleSheet("background: #3498db; color: white; font-weight: bold; padding: 8px; border-radius: 4px; border: none;")
        cs_calc.clicked.connect(self._wc_calc_choke)
        cs_form.addRow(cs_calc)
        cs_layout.addWidget(g_cs)

        self.cs_table = QTableWidget(0, 4)
        self.cs_table.setHorizontalHeaderLabels(["Strokes", "Pressure (psi)", "% Complete", "Cum. Volume (bbl)"])
        self.cs_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.cs_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.cs_table.setAlternatingRowColors(True)
        cs_layout.addWidget(self.cs_table)

        inner_tabs.addTab(cs_tab, "📋 Choke Schedule")

        # ===== Hydrostatic & FP =====
        hp_tab = QWidget()
        hp_layout = QVBoxLayout(hp_tab)

        g_hp = QGroupBox("📊 Hydrostatic & Formation Pressure")
        hp_form = QFormLayout(g_hp)
        self.hp_mw = self._make_dspin(90, 0, 200, 1, " pcf")
        self.hp_tvd = self._make_dspin(3000, 0, 20000, 0, " m")
        self.hp_sidpp = self._make_dspin(0, 0, 10000, 0, " psi")
        hp_form.addRow("Mud Weight:", self.hp_mw)
        hp_form.addRow("TVD:", self.hp_tvd)
        hp_form.addRow("SIDPP:", self.hp_sidpp)

        hp_calc = QPushButton("🔄 Calculate")
        hp_calc.clicked.connect(self._wc_calc_hp)
        hp_form.addRow(hp_calc)

        self.hp_result = QTextEdit()
        self.hp_result.setReadOnly(True)
        self.hp_result.setMaximumHeight(200)
        self.hp_result.setStyleSheet("font-family: Consolas; background: #f8f9fa;")
        hp_form.addRow(self.hp_result)
        hp_layout.addWidget(g_hp)
        hp_layout.addStretch()
        inner_tabs.addTab(hp_tab, "📊 HP & FP")

        # ===== Kick Tolerance =====
        kt_tab = QWidget()
        kt_layout = QVBoxLayout(kt_tab)

        g_kt = QGroupBox("🔄 Kick Tolerance")
        kt_form = QFormLayout(g_kt)
        self.kt_frac = self._make_dspin(13.5, 0, 25, 2, " ppg")
        self.kt_mw = self._make_dspin(10.0, 0, 25, 2, " ppg")
        self.kt_tvd = self._make_dspin(10000, 0, 60000, 0, " ft")
        self.kt_shoe = self._make_dspin(8000, 0, 60000, 0, " ft")
        self.kt_influx_g = self._make_dspin(0.1, 0, 1, 3, " psi/ft")
        self.kt_ann_cap = self._make_dspin(0.0459, 0, 5, 4, " bbl/ft")
        self.kt_form_emw = self._make_dspin(0, 0, 25, 2, " ppg")
        kt_form.addRow("Frac MW:", self.kt_frac)
        kt_form.addRow("Current MW:", self.kt_mw)
        kt_form.addRow("TVD:", self.kt_tvd)
        kt_form.addRow("Shoe TVD:", self.kt_shoe)
        kt_form.addRow("Influx gradient:", self.kt_influx_g)
        kt_form.addRow("Ann. cap DP/OH:", self.kt_ann_cap)
        kt_form.addRow("Formation EMW (0=omit):", self.kt_form_emw)

        kt_calc = QPushButton("🔄 Calculate")
        kt_calc.clicked.connect(self._wc_calc_kt)
        kt_form.addRow(kt_calc)

        self.kt_result = self._result_label("#9b59b6")
        kt_form.addRow("Result:", self.kt_result)

        g_tm = QGroupBox("Trip Margin")
        tm_form = QFormLayout(g_tm)
        self.tm_mw = self._make_dspin(12.0, 0, 25, 2, " ppg")
        self.tm_form = self._make_dspin(11.5, 0, 25, 2, " ppg")
        self.tm_tvd = self._make_dspin(10000, 0, 60000, 0, " ft")
        self.tm_swab = self._make_dspin(0, 0, 5000, 0, " psi")
        tm_form.addRow("Current MW:", self.tm_mw)
        tm_form.addRow("Pore EMW:", self.tm_form)
        tm_form.addRow("TVD:", self.tm_tvd)
        tm_form.addRow("Swab pressure (opt):", self.tm_swab)
        tm_calc = QPushButton("🔄 Calculate Trip Margin")
        tm_calc.clicked.connect(self._wc_calc_trip_margin)
        tm_form.addRow(tm_calc)
        self.tm_result = self._result_label("#16a085")
        tm_form.addRow("Result:", self.tm_result)

        kt_layout.addWidget(g_kt)
        kt_layout.addWidget(g_tm)
        kt_layout.addStretch()
        inner_tabs.addTab(kt_tab, "🔄 Kick Tolerance")

        # ===== Pore Pressure & Fracture Gradient =====
        pp_tab = QWidget()
        pp_layout = QVBoxLayout(pp_tab)

        g_ef = QGroupBox("⛰️ Eaton Fracture Gradient (1969)")
        ef_form = QFormLayout(g_ef)
        self.pp_obg = self._make_dspin(0.95, 0.5, 2.0, 3, " psi/ft")
        self.pp_ppg_grad = self._make_dspin(0.52, 0.2, 1.5, 3, " psi/ft")
        self.pp_nu = self._make_dspin(0.25, 0.1, 0.49, 2, "")
        ef_form.addRow("Overburden gradient:", self.pp_obg)
        ef_form.addRow("Pore pressure gradient:", self.pp_ppg_grad)
        ef_form.addRow("Poisson's ratio:", self.pp_nu)
        ef_calc = QPushButton("🔄 FG = (ν/(1−ν))·(OBG−PPG) + PPG")
        ef_calc.setStyleSheet("background: #8e44ad; color: white; font-weight: bold; padding: 6px; border-radius: 4px; border: none;")
        ef_calc.clicked.connect(self._wc_calc_eaton)
        ef_form.addRow(ef_calc)
        self.pp_eaton_res = self._result_label("#8e44ad")
        ef_form.addRow("Fracture gradient:", self.pp_eaton_res)
        pp_layout.addWidget(g_ef)

        g_if = QGroupBox("💨 Influx Type (SICP / SIDPP / Pit Gain)")
        if_form = QFormLayout(g_if)
        self.pp_sicp = self._make_dspin(300, 0, 10000, 0, " psi")
        self.pp_sidpp = self._make_dspin(200, 0, 10000, 0, " psi")
        self.pp_ann_cap = self._make_dspin(0.0459, 0, 5, 4, " bbl/ft")
        self.pp_gain = self._make_dspin(10, 0, 500, 0, " bbl")
        if_form.addRow("SICP:", self.pp_sicp)
        if_form.addRow("SIDPP:", self.pp_sidpp)
        if_form.addRow("Annular capacity (open hole):", self.pp_ann_cap)
        if_form.addRow("Pit gain:", self.pp_gain)
        if_calc = QPushButton("🔄 Classify Influx")
        if_calc.setStyleSheet("background: #c0392b; color: white; font-weight: bold; padding: 6px; border-radius: 4px; border: none;")
        if_calc.clicked.connect(self._wc_calc_influx_type)
        if_form.addRow(if_calc)
        self.pp_influx_res = self._result_label("#c0392b")
        if_form.addRow("Influx:", self.pp_influx_res)
        pp_layout.addWidget(g_if)

        g_de = QGroupBox("📈 d-Exponent & dc (Pore-Pressure Trend)")
        de_form = QFormLayout(g_de)
        self.pp_rop = self._make_dspin(30, 0, 500, 1, " ft/hr")
        self.pp_rpm = self._make_dspin(80, 0, 300, 0, " rpm")
        self.pp_wob = self._make_dspin(25000, 0, 150000, 0, " lbf")
        self.pp_bit = self._make_dspin(8.5, 3, 26, 2, " in")
        self.pp_mw = self._make_dspin(12.0, 0, 25, 2, " ppg")
        self.pp_mw_n = self._make_dspin(8.6, 0, 25, 2, " ppg")
        de_form.addRow("ROP:", self.pp_rop)
        de_form.addRow("RPM:", self.pp_rpm)
        de_form.addRow("WOB:", self.pp_wob)
        de_form.addRow("Bit size:", self.pp_bit)
        de_form.addRow("Actual MW:", self.pp_mw)
        de_form.addRow("Normal MW:", self.pp_mw_n)
        de_calc = QPushButton("🔄 d = log10(ROP/60·RPM) / log10(12·WOB/1000·D)")
        de_calc.setStyleSheet("background: #2c3e50; color: white; font-weight: bold; padding: 6px; border-radius: 4px; border: none;")
        de_calc.clicked.connect(self._wc_calc_d_exp)
        de_form.addRow(de_calc)
        self.pp_d_res = self._result_label("#2c3e50")
        de_form.addRow("d / dc:", self.pp_d_res)
        pp_layout.addWidget(g_de)

        pp_layout.addStretch()
        inner_tabs.addTab(pp_tab, "📈 Pore Press & FG")

        return tab

    def _wc_add_pipe(self):
        from dialogs.engineering_dialogs import AddPipeDialog
        dlg = AddPipeDialog(self)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                self.wc_pipes.append(data)
                self._wc_refresh_pipe_table()

    def _wc_edit_pipe(self):
        row = self.wc_pipe_table.currentRow()
        if 0 <= row < len(self.wc_pipes):
            from dialogs.engineering_dialogs import AddPipeDialog
            dlg = AddPipeDialog(self, edit_data=self.wc_pipes[row])
            if dlg.exec():
                data = dlg.get_result()
                if data:
                    self.wc_pipes[row] = data
                    self._wc_refresh_pipe_table()

    def _wc_rem_pipe(self):
        row = self.wc_pipe_table.currentRow()
        if 0 <= row < len(self.wc_pipes):
            self.wc_pipes.pop(row)
            self._wc_refresh_pipe_table()

    def _wc_refresh_pipe_table(self):
        from core.hydraulics_engine import AdvancedHydraulicsEngine as A
        self.wc_pipe_table.setRowCount(0)
        total_string = 0
        total_ann = 0
        csg_id = self.wc_last_csg_id.value()
        hole = self.wc_hole_size.value()

        for p in self.wc_pipes:
            row = self.wc_pipe_table.rowCount()
            self.wc_pipe_table.insertRow(row)
            od = p.get('od', 0)
            id_ = p.get('id', 0)
            L = p.get('length', 0)
            cap = A.calc_pipe_capacity_bbl_ft(id_) * 3.28084   # bbl/m
            vol = cap * L

            total_string += vol

            self.wc_pipe_table.setItem(row, 0, QTableWidgetItem(p.get('type', '')))
            self.wc_pipe_table.setItem(row, 1, QTableWidgetItem(f"{od:.3f}\""))
            self.wc_pipe_table.setItem(row, 2, QTableWidgetItem(f"{id_:.3f}\""))
            self.wc_pipe_table.setItem(row, 3, QTableWidgetItem(f"{L:.1f}"))
            self.wc_pipe_table.setItem(row, 4, QTableWidgetItem(f"{cap:.5f}"))
            vi = QTableWidgetItem(f"{vol:.2f}")
            vi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.wc_pipe_table.setItem(row, 5, vi)

            # Annular volume (simplified)
            ann_id = csg_id if L < self.wc_shoe_md.value() else hole
            if ann_id > od:
                ann_vol = (A.calc_annular_capacity_bbl_ft(ann_id, od)
                           * 3.28084 * L)
                total_ann += ann_vol

        self.wc_string_summary.setText(
            f"String: {total_string:.2f} bbl | Annular: {total_ann:.2f} bbl | "
            f"Total: {total_string + total_ann:.2f} bbl"
        )
    
    # ========== Well Control Methods ==========

    def _wc_calc_kill(self):
        from core.hydraulics_engine import AdvancedHydraulicsEngine as A
        tvd_ft = self.wc_tvd.value() * 3.28084
        md_ft = self.wc_md.value() * 3.28084
        shoe_tvd_ft = self.wc_shoe_tvd.value() * 3.28084
        mw_pcf = self.wc_mw.value()
        mw_ppg = mw_pcf / 7.48
        sidpp = self.wc_sidpp.value()
        sicp = self.wc_sicp.value()
        frac_grad = self.wc_frac.value()
        pit_gain = self.wc_pit_gain.value()
        scr1 = self.wc_scr1.value()
        scr1_spm = self.wc_scr1_spm.value()
        scr2 = self.wc_scr2.value()
        scr2_spm = self.wc_scr2_spm.value()
        pump_output = self.wc_pump_output.value()
        hole = self.wc_hole_size.value()
        csg_id = self.wc_last_csg_id.value()
        method = "Driller's" if self.wc_driller.isChecked() else "Wait & Weight"

        # String volumes — canonical capacity (bbl/ft) × length in ft
        total_string_vol = 0
        total_ann_vol = 0
        string_detail = []
        ann_detail = []

        for p in self.wc_pipes:
            od = p.get('od', 0)
            id_ = p.get('id', 0)
            L = p.get('length', 0)
            ptype = p.get('type', '')

            cap = A.calc_pipe_capacity_bbl_ft(id_) * (L * 3.28084)
            total_string_vol += cap
            string_detail.append((ptype, L, cap))

            # Annular (simplified: assume in csg if above shoe, OH if below)
            shoe_m = self.wc_shoe_md.value()
            if L > 0:
                ann_id_val = csg_id  # simplified
                if ann_id_val > od:
                    ann = (A.calc_annular_capacity_bbl_ft(ann_id_val, od)
                           * (L * 3.28084))
                    total_ann_vol += ann
                    ann_detail.append((f"{ptype} in CSG", L, ann))

        # Kill calculations — canonical WellControlEngine
        from core.engineering.engines.well_control import WellControlEngine as WC
        kmw_r = WC.kill_mw(mw_ppg, sidpp, tvd_ft)
        kmw_ppg = kmw_r.value if kmw_r.success else mw_ppg
        kmw_pcf = kmw_ppg * 7.48
        icp = scr1 + sidpp
        fcp = scr1 * (kmw_ppg / mw_ppg) if mw_ppg > 0 else scr1
        maasp_r = WC.maasp(
            max_allowable_mw_ppg=frac_grad / 0.052 if frac_grad else None,
            current_mw_ppg=mw_ppg,
            shoe_tvd_ft=shoe_tvd_ft,
        )
        maasp = maasp_r.value if maasp_r.success else 0

        # Strokes
        stk_to_bit = total_string_vol / pump_output if pump_output > 0 else 0
        stk_annular = total_ann_vol / pump_output if pump_output > 0 else 0
        stk_total = stk_to_bit + stk_annular

        # Kick height / type — canonical WellControlEngine.kick_volume
        # (height = pit gain / annular capacity; influx gradient from
        # SICP−SIDPP over the influx height; type by gradient cut-offs)
        kick_type = "n/a (enter pit gain + drill string)"
        kick_height = 0.0
        kick_note = ""
        last_pipe_od = self.wc_pipes[-1].get('od', 5) if self.wc_pipes else 5
        ann_cap_ft = A.calc_annular_capacity_bbl_ft(hole, last_pipe_od)
        if pit_gain > 0 and ann_cap_ft > 0:
            kv = WC.kick_volume(
                pit_gain_bbl=pit_gain,
                annular_capacity_bbl_ft=ann_cap_ft,
                mw_ppg=mw_ppg,
                sidpp_psi=sidpp,
                sicp_psi=sicp,
            )
            if kv.success:
                kick_height = kv.values.get("kick_height_ft") or 0.0
                kind = kv.values.get("kick_type")
                kick_type = {
                    "gas": "Gas Kick",
                    "oil": "Oil Kick",
                    "oil_or_condensate": "Oil Kick",
                    "salt_water": "Salt Water Kick",
                    "saltwater": "Salt Water Kick",
                }.get(kind, "Unknown")
                if kv.warnings:
                    kick_note = " ⚠ " + "; ".join(kv.warnings)[:80]

        # Choke schedule
        schedule = []
        intervals = 10
        if stk_to_bit > 0:
            step = stk_to_bit / intervals
            dp = (icp - fcp) / intervals
            for i in range(intervals + 1):
                strokes = round(i * step)
                pressure = round(icp - i * dp, 1)
                schedule.append((strokes, pressure, round(i / intervals * 100)))

        # Build report
        text = f"""╔═════════════════════════════════════════════════════════╗
    ║                    KILL SHEET                           ║
    ║              {method} Method                       ║
    ╠═════════════════════════════════════════════════════════╣
    ║ WELL DATA:
    ║   Well Type:      {self.wc_well_type.currentText()}
    ║   TVD:            {self.wc_tvd.value():.0f} m ({tvd_ft:.0f} ft)
    ║   MD:             {self.wc_md.value():.0f} m ({md_ft:.0f} ft)
    ║   Shoe TVD:       {self.wc_shoe_tvd.value():.0f} m ({shoe_tvd_ft:.0f} ft)
    ║   Hole Size:      {hole:.3f}" 
    ║   Last CSG:       {self.wc_last_csg.value():.3f}" OD / {csg_id:.3f}" ID
    ╠═════════════════════════════════════════════════════════╣
    ║ DRILL STRING VOLUMES:"""

        for name, length, vol in string_detail:
            text += f"\n║   {name:<25} {length:>8.1f} m → {vol:>8.2f} bbl"

        text += f"""
    ║   {'─' * 50}
    ║   {'TOTAL STRING:':<25} {'':<8} → {total_string_vol:>8.2f} bbl
    ╠═════════════════════════════════════════════════════════╣
    ║ ANNULAR VOLUMES:"""

        for name, length, vol in ann_detail:
            text += f"\n║   {name:<25} {length:>8.1f} m → {vol:>8.2f} bbl"

        text += f"""
    ║   {'─' * 50}
    ║   {'TOTAL ANNULAR:':<25} {'':<8} → {total_ann_vol:>8.2f} bbl
    ║   {'TOTAL WELL:':<25} {'':<8} → {total_string_vol + total_ann_vol:>8.2f} bbl
    ╠═════════════════════════════════════════════════════════╣
    ║ MUD & KICK DATA:
    ║   Current MW:     {mw_pcf:.1f} pcf ({mw_ppg:.2f} ppg)
    ║   SIDPP:          {sidpp:.0f} psi
    ║   SICP:           {sicp:.0f} psi
    ║   Pit Gain:       {pit_gain:.0f} bbl
    ║   Kick Type:      {kick_type}
    ║   Kick Height:    {kick_height:.0f} ft (estimated){kick_note}
    ║   Frac Gradient:  {frac_grad:.4f} psi/ft
    ╠═════════════════════════════════════════════════════════╣
    ║ PUMP DATA:
    ║   SCR #1:         {scr1:.0f} psi @ {scr1_spm:.0f} spm
    ║   SCR #2:         {scr2:.0f} psi @ {scr2_spm:.0f} spm
    ║   Pump Output:    {pump_output:.5f} bbl/stk
    ╠═════════════════════════════════════════════════════════╣
    ║ KILL PARAMETERS:
    ║   ┌─────────────────────────────────────────────┐
    ║   │ Kill MW:        {kmw_pcf:.1f} pcf ({kmw_ppg:.2f} ppg)      │
    ║   │ MW Increase:    {kmw_pcf - mw_pcf:.1f} pcf ({kmw_ppg - mw_ppg:.2f} ppg)     │
    ║   │ ICP:            {icp:.0f} psi                          │
    ║   │ FCP:            {fcp:.0f} psi                          │
    ║   │ MAASP:          {maasp:.0f} psi                         │
    ║   └─────────────────────────────────────────────┘
    ╠═════════════════════════════════════════════════════════╣
    ║ STROKES:
    ║   Surface → Bit:       {stk_to_bit:.0f} strokes
    ║   Bit → Surface:       {stk_annular:.0f} strokes
    ║   Total Circulation:   {stk_total:.0f} strokes
    ╠═════════════════════════════════════════════════════════╣"""

        if method == "Driller's":
            text += f"""
    ║ DRILLER'S METHOD PROCEDURE:
    ║ ──────────────────────────
    ║ 1st CIRCULATION (circulate kick out):
    ║   • Use CURRENT mud weight: {mw_ppg:.2f} ppg
    ║   • Hold SIDPP constant at: {sidpp:.0f} psi
    ║   • Starting choke pressure: {icp:.0f} psi (ICP)
    ║   • Continue until kick is circulated out
    ║   • Total strokes: {stk_total:.0f}
    ║
    ║ 2nd CIRCULATION (circulate kill mud):
    ║   • Weight up mud to: {kmw_ppg:.2f} ppg ({kmw_pcf:.1f} pcf)
    ║   • Start at ICP: {icp:.0f} psi
    ║   • Reduce to FCP: {fcp:.0f} psi over {stk_to_bit:.0f} strokes
    ║   • Hold FCP constant for remaining {stk_annular:.0f} strokes"""
        else:
            text += f"""
    ║ WAIT & WEIGHT METHOD PROCEDURE:
    ║ ───────────────────────────────
    ║ • Weight up mud to: {kmw_ppg:.2f} ppg BEFORE circulating
    ║ • Start pumping at ICP: {icp:.0f} psi
    ║ • Reduce to FCP: {fcp:.0f} psi over {stk_to_bit:.0f} strokes
    ║ • Hold FCP at {fcp:.0f} psi for remaining {stk_annular:.0f} strokes
    ║ • Kill in ONE circulation"""

        text += f"""
    ╠═════════════════════════════════════════════════════════╣
    ║ CHOKE PRESSURE SCHEDULE (Surface → Bit):
    ║ ─────────────────────────────────────────
    ║  Strokes    │  Choke Press (psi)  │  % Complete
    ║ ────────────│─────────────────────│─────────────"""

        for strokes, pressure, pct in schedule:
            marker = " ◄── START" if pct == 0 else " ◄── END (FCP)" if pct == 100 else ""
            text += f"\n║  {strokes:>8}   │  {pressure:>8.0f}            │  {pct:>4}%{marker}"

        text += f"""
    ╠═════════════════════════════════════════════════════════╣
    ║ SAFETY CHECKS:
    ║   {'✅' if maasp > 500 else '⚠️'} MAASP: {maasp:.0f} psi {'(adequate)' if maasp > 500 else '(LOW - CAUTION!)'}
    ║   {'⚠️ GAS KICK - Monitor gas migration rate' if kick_type == 'Gas Kick' else '✅ ' + kick_type}
    ║   {'⚠️ Directional well - TVD ≠ MD' if self.wc_well_type.currentText() != 'Vertical' else '✅ Vertical well'}
    ║   {'⚠️ Pit gain > 20 bbl - large kick!' if pit_gain > 20 else '✅ Pit gain acceptable'}
    ╠═════════════════════════════════════════════════════════╣
    ║ NOTES:
    ║   • Record all pressures and volumes during kill
    ║   • Monitor pit levels continuously
    ║   • Do NOT exceed MAASP of {maasp:.0f} psi
    ║   • If gas migration observed, use Volumetric Method
    ╚═════════════════════════════════════════════════════════╝"""

        self.wc_result.setText(text)

    def _wc_calc_choke(self):
        icp = self.cs_icp.value()
        fcp = self.cs_fcp.value()
        stk = int(self.cs_strokes.value())
        intervals = self.cs_intervals.value()

        self.cs_table.setRowCount(0)
        if stk <= 0 or intervals <= 0:
            return

        step = stk / intervals
        dp = (icp - fcp) / intervals

        for i in range(intervals + 1):
            row = self.cs_table.rowCount()
            self.cs_table.insertRow(row)
            strokes = round(i * step)
            pressure = round(icp - i * dp, 1)
            pct = round(i / intervals * 100)

            self.cs_table.setItem(row, 0, QTableWidgetItem(str(strokes)))
            pi = QTableWidgetItem(f"{pressure:.0f}")
            pi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.cs_table.setItem(row, 1, pi)
            self.cs_table.setItem(row, 2, QTableWidgetItem(f"{pct}%"))
            self.cs_table.setItem(row, 3, QTableWidgetItem(""))

            # Color coding
            if i == 0:
                for c in range(4):
                    it = self.cs_table.item(row, c)
                    if it:
                        it.setBackground(QColor("#fadbd8"))
            elif i == intervals:
                for c in range(4):
                    it = self.cs_table.item(row, c)
                    if it:
                        it.setBackground(QColor("#d5f5e3"))

    def _wc_calc_eaton(self):
        from core.engineering.engines.well_control import WellControlEngine
        r = WellControlEngine.eaton_fracture_gradient(
            self.pp_obg.value(), self.pp_ppg_grad.value(), self.pp_nu.value())
        if r.success:
            fg = r.values["fracture_gradient_psi_ft"]
            self.pp_eaton_res.setText(
                f"{fg:.4f} psi/ft  ≡  {fg / 0.052:.2f} ppg EMW")
        else:
            self.pp_eaton_res.setText(f"⚠️ {r.error}")

    def _wc_calc_influx_type(self):
        from core.engineering.engines.well_control import WellControlEngine
        r = WellControlEngine.influx_type(
            self.pp_sicp.value(), self.pp_sidpp.value(),
            self.pp_ann_cap.value(), self.pp_gain.value())
        if r.success:
            v = r.values
            self.pp_influx_res.setText(
                f"{v['influx_type'].title()} — gradient {v['influx_gradient_psi_ft']:.3f} psi/ft, "
                f"height {v['influx_height_ft']:.0f} ft")
        else:
            self.pp_influx_res.setText(f"⚠️ {r.error}")

    def _wc_calc_d_exp(self):
        from core.engineering.engines.bit_performance import BitPerformanceEngine
        r = BitPerformanceEngine.d_exponent_corrected(
            self.pp_rop.value(), self.pp_rpm.value(), self.pp_wob.value(),
            self.pp_bit.value(), mw_ppg=self.pp_mw.value(),
            normal_mw_ppg=self.pp_mw_n.value())
        if r.success:
            v = r.values
            self.pp_d_res.setText(
                f"d = {v['d_exponent']:.4f}   dc = {v['d_exponent_corrected']:.4f}"
                + ("  ⚠️ decreasing trend → abnormal pressure" if v["d_exponent_corrected"] < 1.0 else ""))
        else:
            self.pp_d_res.setText(f"⚠️ {r.error}")

    def _wc_calc_hp(self):
        mw_pcf = self.hp_mw.value()
        tvd_ft = self.hp_tvd.value() * 3.28084
        sidpp = self.hp_sidpp.value()
        r = self.engine.calc_formation_pressure(mw_pcf, tvd_ft, sidpp)

        text = f"Hydrostatic Pressure: {r['hydrostatic_psi']:.0f} psi\n"
        text += f"Formation Pressure:   {r['formation_pressure_psi']:.0f} psi\n"
        text += f"Pressure Gradient:    {r['pressure_gradient_psi_ft']:.4f} psi/ft\n"
        text += f"Equivalent MW:        {r['equivalent_mw_ppg']:.2f} ppg ({r['equivalent_mw_pcf']:.1f} pcf)"
        self.hp_result.setText(text)

    def _wc_calc_kt(self):
        form = self.kt_form_emw.value() or None
        r = self.engine.calc_kick_tolerance(
            self.kt_frac.value(), self.kt_mw.value(),
            self.kt_tvd.value(), self.kt_shoe.value(), None,
            influx_gradient_psi_ft=self.kt_influx_g.value(),
            annular_capacity_bbl_ft=self.kt_ann_cap.value() or None,
            formation_emw_ppg=form,
        )
        if "error" in r:
            self.kt_result.setText(f"❌ {r['error']}")
            return
        kt = r.get("kick_tolerance_bbl")
        self.kt_result.setText(
            f"MAASP: {r.get('maasp_psi', 0):.0f} psi\n"
            f"Kick intensity: {r.get('kick_intensity_ppg')}\n"
            f"Max height: {r.get('max_kick_height_ft', 0):.1f} ft\n"
            f"Kick tolerance: {kt if kt is not None else 'n/a (need capacity)'} bbl"
        )

    def _wc_calc_trip_margin(self):
        from core.engineering.engines.well_control import WellControlEngine
        swab = self.tm_swab.value() or None
        r = WellControlEngine.trip_margin(
            mw_ppg=self.tm_mw.value(),
            formation_emw_ppg=self.tm_form.value(),
            tvd_ft=self.tm_tvd.value(),
            swab_pressure_psi=swab,
        )
        if not r.success:
            self.tm_result.setText(f"❌ {r.error}")
            return
        v = r.values
        extra = ""
        if v.get("adequate") is False:
            extra = "\n⚠️ below required"
        self.tm_result.setText(
            f"Trip margin: {v['trip_margin_ppg']:.3f} ppg\n"
            f"({v.get('trip_margin_psi') or 0:.0f} psi){extra}"
        )
        
   # ==================== Directional Tab ====================

    def _create_directional_tab(self) -> QWidget:
        """تب Directional - حرفه‌ای با دیالوگ سروی"""
        self.dd_surveys = []

        tab, container, layout = self._make_scroll_tab()

        inner_tabs = QTabWidget()
        layout.addWidget(inner_tabs)

        # ===== Multi-Survey =====
        sv_tab = QWidget()
        sv_layout = QVBoxLayout(sv_tab)

        g1 = QGroupBox("📐 Survey Points (Minimum Curvature)")
        g1_lay = QVBoxLayout(g1)
        sv_btns = QHBoxLayout()

        add_sv = QPushButton("➕ Add Survey Point")
        add_sv.setStyleSheet("background: #27ae60; color: white; padding: 4px 10px; border-radius: 3px; border: none;")
        add_sv.clicked.connect(self._dd_add_survey)
        edit_sv = QPushButton("✏️ Edit")
        edit_sv.clicked.connect(self._dd_edit_survey)
        rem_sv = QPushButton("🗑️")
        rem_sv.setFixedWidth(30)
        rem_sv.clicked.connect(self._dd_rem_survey)
        clear_sv = QPushButton("🧹 Clear")
        clear_sv.clicked.connect(self._dd_clear_surveys)

        sv_btns.addWidget(add_sv)
        sv_btns.addWidget(edit_sv)
        sv_btns.addWidget(rem_sv)
        sv_btns.addWidget(clear_sv)
        sv_btns.addStretch()
        g1_lay.addLayout(sv_btns)

        self.dd_table = QTableWidget(0, 8)
        self.dd_table.setHorizontalHeaderLabels([
            "#", "MD (m)", "Inc (°)", "Azi (°)", "TVD (m)", "North (m)", "East (m)", "DLS (°/30m)"
        ])
        self.dd_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.dd_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.dd_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.dd_table.doubleClicked.connect(self._dd_edit_survey)
        g1_lay.addWidget(self.dd_table)

        # Summary
        self.dd_summary = QLabel("")
        self.dd_summary.setStyleSheet("font-weight: bold; color: #2c3e50; padding: 5px; background: #ecf0f1; border-radius: 3px;")
        g1_lay.addWidget(self.dd_summary)

        sv_layout.addWidget(g1)
        sv_layout.addStretch()
        inner_tabs.addTab(sv_tab, "📐 Multi-Survey")

        # ===== Build/Turn Rate =====
        br_tab = QWidget()
        br_layout = QVBoxLayout(br_tab)

        g2 = QGroupBox("📈 Build & Turn Rate Calculator")
        f2 = QFormLayout(g2)
        self.dd_init_inc = self._make_dspin(5, 0, 180, 2, " °")
        self.dd_final_inc = self._make_dspin(30, 0, 180, 2, " °")
        self.dd_init_azi = self._make_dspin(45, 0, 360, 1, " °")
        self.dd_final_azi = self._make_dspin(45, 0, 360, 1, " °")
        self.dd_interval = self._make_dspin(300, 0, 20000, 0, " m")

        f2.addRow("Initial Inc:", self.dd_init_inc)
        f2.addRow("Final Inc:", self.dd_final_inc)
        f2.addRow("Initial Azi:", self.dd_init_azi)
        f2.addRow("Final Azi:", self.dd_final_azi)
        f2.addRow("MD Interval:", self.dd_interval)

        calc_br = QPushButton("🔄 Calculate")
        calc_br.clicked.connect(self._dd_calc_rates)
        f2.addRow(calc_br)

        self.dd_rates = self._result_label("#9b59b6")
        f2.addRow("Results:", self.dd_rates)

        br_layout.addWidget(g2)
        br_layout.addStretch()
        inner_tabs.addTab(br_tab, "📈 Build/Turn Rate")

        return tab

    # ========== Directional Methods ==========

    def _dd_add_survey(self):
        """اضافه کردن نقطه سروی با دیالوگ"""
        from dialogs.engineering_dialogs import AddSurveyDialog

        # آخرین نقطه رو به عنوان prev بفرست
        prev = None
        if self.dd_surveys:
            prev = self.dd_surveys[-1]

        dlg = AddSurveyDialog(self, prev_survey=prev)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                self.dd_surveys.append(data)
                self._dd_refresh_table()

    def _dd_edit_survey(self):
        row = self.dd_table.currentRow()
        if 0 <= row < len(self.dd_surveys):
            from dialogs.engineering_dialogs import AddSurveyDialog
            prev = self.dd_surveys[row - 1] if row > 0 else None
            dlg = AddSurveyDialog(self, edit_data=self.dd_surveys[row], prev_survey=prev)
            if dlg.exec():
                data = dlg.get_result()
                if data:
                    self.dd_surveys[row] = data
                    # Recalculate all subsequent points
                    self._dd_recalculate_from(row)
                    self._dd_refresh_table()

    def _dd_rem_survey(self):
        row = self.dd_table.currentRow()
        if 0 <= row < len(self.dd_surveys):
            self.dd_surveys.pop(row)
            if row > 0:
                self._dd_recalculate_from(row)
            self._dd_refresh_table()

    def _dd_clear_surveys(self):
        self.dd_surveys.clear()
        self._dd_refresh_table()

    def _dd_recalculate_from(self, start_row):
        """Recompute the whole survey with canonical Minimum Curvature."""
        from core.engineering.core import TrajectoryEngine
        surveys = [
            {"md": s.get("md", 0), "inc": s.get("inc", 0), "azi": s.get("azi", 0)}
            for s in self.dd_surveys
        ]
        if not surveys:
            return
        try:
            pts = TrajectoryEngine.calculate(surveys)
        except Exception:
            return
        for i, p in enumerate(pts):
            if i < len(self.dd_surveys):
                self.dd_surveys[i]["tvd"] = p.tvd
                self.dd_surveys[i]["north"] = p.north
                self.dd_surveys[i]["east"] = p.east
                self.dd_surveys[i]["dls"] = p.dls

    def _dd_refresh_table(self):
        self.dd_table.setRowCount(0)
        for i, s in enumerate(self.dd_surveys):
            row = self.dd_table.rowCount()
            self.dd_table.insertRow(row)

            self.dd_table.setItem(row, 0, QTableWidgetItem(str(i + 1)))
            self.dd_table.setItem(row, 1, QTableWidgetItem(f"{s.get('md', 0):.2f}"))
            self.dd_table.setItem(row, 2, QTableWidgetItem(f"{s.get('inc', 0):.2f}"))
            self.dd_table.setItem(row, 3, QTableWidgetItem(f"{s.get('azi', 0):.2f}"))

            for col, key in [(4, 'tvd'), (5, 'north'), (6, 'east'), (7, 'dls')]:
                val = s.get(key, 0)
                item = QTableWidgetItem(f"{val:.2f}")
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item.setBackground(QColor(220, 255, 220))
                self.dd_table.setItem(row, col, item)

        # Summary
        if self.dd_surveys:
            last = self.dd_surveys[-1]
            n = last.get('north', 0)
            e = last.get('east', 0)
            hd = math.sqrt(n**2 + e**2)
            self.dd_summary.setText(
                f"📌 Final: TVD={last.get('tvd', 0):.1f}m | "
                f"North={n:.1f}m | East={e:.1f}m | "
                f"HD={hd:.1f}m | Points: {len(self.dd_surveys)}"
            )
        else:
            self.dd_summary.setText("")

    def _dd_calc_rates(self):
        br = self.engine.calc_build_rate(
            self.dd_init_inc.value(), self.dd_final_inc.value(), self.dd_interval.value()
        )
        tr = self.engine.calc_turn_rate(
            self.dd_init_azi.value(), self.dd_final_azi.value(), self.dd_interval.value()
        )
        self.dd_rates.setText(
            f"Build Rate: {br:.2f} °/30m\n"
            f"Turn Rate: {tr:.2f} °/30m\n"
            f"Overall DLS: {math.sqrt(br**2 + tr**2):.2f} °/30m"
        )
        
    # ==================== Fishing Tab ====================
    def _create_fishing_tab(self) -> QWidget:
        tab, container, layout = self._make_scroll_tab()

        g1 = QGroupBox("🎣 Overshot / Grapple Sizing")
        f1 = QFormLayout(g1)
        self.fish_od = self._make_dspin(5.0, 0, 30, 3, " in")
        self.fish_os_id = self._make_dspin(5.3, 0, 30, 3, " in")
        f1.addRow("Fish OD:", self.fish_od)
        f1.addRow("Overshot Catch ID:", self.fish_os_id)
        self.fish_result = QLabel("Clearance = -- in")
        self.fish_result.setStyleSheet("font-weight: bold; color: #e67e22; padding: 5px; border: 1px solid #e67e22; border-radius: 3px;")
        f1.addRow(self.fish_result)
        self.fish_od.valueChanged.connect(self._calc_fish_sizing)
        self.fish_os_id.valueChanged.connect(self._calc_fish_sizing)
        layout.addWidget(g1)

        g2 = QGroupBox("⚡ Jar Operating Range")
        f2 = QFormLayout(g2)
        self.jar_string_wt = self._make_dspin(200000, 0, 2000000, 0, " lbs")
        self.jar_bf = self._make_dspin(0.85, 0, 1, 3)
        self.jar_overpull = self._make_dspin(50000, 0, 500000, 0, " lbs")
        f2.addRow("String Weight:", self.jar_string_wt)
        f2.addRow("Buoyancy Factor:", self.jar_bf)
        f2.addRow("Overpull:", self.jar_overpull)
        calc_jar_btn = QPushButton("🔄 Calculate")
        calc_jar_btn.clicked.connect(self._calc_jar_range)
        f2.addRow(calc_jar_btn)
        self.jar_result = QLabel("Jar Setting = -- lbs")
        self.jar_result.setStyleSheet("font-weight: bold; color: #2ecc71; padding: 5px; border: 1px solid #2ecc71; border-radius: 3px;")
        f2.addRow(self.jar_result)
        layout.addWidget(g2)

        g3 = QGroupBox("🔧 Back-off Depth")
        f3 = QFormLayout(g3)
        self.bo_stretch = self._make_dspin(2.5, 0, 100, 2, " in")
        self.bo_pipe_wt = self._make_dspin(22, 0, 500, 1, " ppf")
        f3.addRow("Measured Stretch:", self.bo_stretch)
        f3.addRow("Pipe Weight:", self.bo_pipe_wt)
        self.bo_result = QLabel("Free Point = -- ft")
        self.bo_result.setStyleSheet("font-weight: bold; color: #e74c3c; padding: 5px; border: 1px solid #e74c3c; border-radius: 3px;")
        f3.addRow(self.bo_result)
        self.bo_stretch.valueChanged.connect(self._calc_backoff)
        self.bo_pipe_wt.valueChanged.connect(self._calc_backoff)
        layout.addWidget(g3)

        layout.addStretch()
        return tab
        
    # ==================== Calculation Slots ====================

    def _make_dspin(self, val, min_v=0, max_v=100000, dec=1, suffix="") -> QDoubleSpinBox:
        """ساخت سریع QDoubleSpinBox"""
        sp = QDoubleSpinBox()
        sp.setRange(min_v, max_v)
        sp.setDecimals(dec)
        sp.setValue(val)
        if suffix:
            sp.setSuffix(suffix)
        return sp

    def _update_stuck(self):
        fp = self.engine.calc_free_point(
            self.stk_diff.value(), self.stk_wt.value(), self.stk_pull.value()
        )
        self.stk_free_point.setText(f"Free Point = {fp:.1f} ft ({fp/3.281:.1f} m)")
        
        stretch = self.engine.calc_string_stretch(self.stk_len.value(), self.stk_mw.value())
        self.stk_stretch.setText(f"String Stretch = {stretch:.2f} in")
        
        adj_wt = self.engine.calc_adjusted_weight(self.stk_pipe_od.value(), self.stk_pipe_id.value())
        self.stk_adj_wt.setText(f"Adjusted Weight = {adj_wt:.2f} lb/ft")

    def _browse_drillpipe_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open DrillPipe Database", "", "Excel Files (*.xlsx *.xls)"
        )
        if filename:
            try:
                self._drill_pipe_df = pd.read_excel(filename, engine="openpyxl")
                QMessageBox.information(self, "Success", f"Loaded {len(self._drill_pipe_df)} rows")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load: {str(e)}")


    def _calc_fish_sizing(self):
        result = self.engine.calc_fish_neck_ot(self.fish_od.value(), self.fish_os_id.value())
        status = "✅ OK" if result['compatible'] else "❌ Check sizing"
        self.fish_result.setText(
            f"Clearance = {result['clearance_in']:.3f} in | {status}"
        )

    def _calc_jar_range(self):
        result = self.engine.calc_jar_operating_range(
            self.jar_string_wt.value(), self.jar_bf.value(), self.jar_overpull.value()
        )
        self.jar_result.setText(
            f"Buoyant Wt = {result['buoyant_weight_lbs']:,.0f} lbs\n"
            f"Upward Force = {result['upward_force_lbs']:,.0f} lbs\n"
            f"Recommended Jar = {result['recommended_jar_setting_lbs']:,.0f} lbs"
        )

    def _calc_backoff(self):
        fp = self.engine.calc_backoff_depth(
            self.bo_stretch.value(), self.bo_pipe_wt.value()
        )
        self.bo_result.setText(f"Free Point = {fp:.0f} ft ({fp/3.281:.0f} m)")
        
    # ==================== DrillTabBase Overrides ====================
    def on_well_changed(self, well_id, well_data):
        self.current_well_id = well_id

    def save_data(self) -> bool:
        return True

    def refresh(self):
        try:
            if hasattr(self, 'v_od') and hasattr(self, 'v_id'):
                self._vol_update_quick()
        except Exception:
            pass
        
        try:
            if hasattr(self, 'v_hole') and hasattr(self, 'v_pipe_od'):
                self._vol_update_annular()
        except Exception:
            pass
        

    def _make_scroll_tab(self):
        """Create a tab with scroll area and vertical layout"""
        tab = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)
        layout.setContentsMargins(8, 8, 8, 8)

        scroll.setWidget(container)

        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

        return tab, container, layout

    def _create_dp_table_tab(self) -> QWidget:
        """تب جدول Drill Pipe از فایل Excel"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        header = QLabel("📋 Drill Pipe Specifications Database")
        header.setStyleSheet("font-weight: bold; color: #ecf0f1; padding: 5px;")
        layout.addWidget(header)

        if self._drill_pipe_df is not None:
            table = QTableView()
            model = PandasTableModel(self._drill_pipe_df)
            table.setModel(model)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            layout.addWidget(table)
        else:
            msg = QLabel(
                "⚠️ DrillPipe.xlsx not found!\n\n"
                "Place DrillPipe.xlsx in one of these locations:\n"
                "• DrillPipe.xlsx (root)\n"
                "• data/DrillPipe.xlsx\n"
                "• resources/DrillPipe.xlsx"
            )
            msg.setAlignment(Qt.AlignCenter)
            msg.setStyleSheet("color: #e74c3c; font-size: 13px; padding: 30px;")
            layout.addWidget(msg)

            load_btn = QPushButton("📂 Browse for DrillPipe.xlsx")
            load_btn.clicked.connect(self._browse_drillpipe_file)
            layout.addWidget(load_btn, alignment=Qt.AlignCenter)

        return tab
    
# ==================== Pandas Table Model ====================
class PandasTableModel(QAbstractTableModel):
    """مدل جدول برای نمایش DataFrame"""

    def __init__(self, data: pd.DataFrame):
        super().__init__()
        self._data = data

    def rowCount(self, parent=None):
        return self._data.shape[0]

    def columnCount(self, parent=None):
        return self._data.shape[1]

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and index.isValid():
            return str(self._data.iloc[index.row(), index.column()])
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self._data.columns[section])
            elif orientation == Qt.Vertical:
                return str(self._data.index[section])
        return None
