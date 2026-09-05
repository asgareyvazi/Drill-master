# dialogs/calculator_dialog.py
"""
Drilling Calculator - ماشین حساب محاسبات حفاری
"""
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
import math


class DrillingCalculatorDialog(QDialog):
    """ماشین حساب محاسبات حفاری"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🧮 Drilling Calculator")
        self.setMinimumSize(500, 600)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        title = QLabel("🧮 Drilling Calculator")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; padding: 10px;")
        layout.addWidget(title)
        
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_hydraulics_tab(), "💧 Hydraulics")
        self.tabs.addTab(self._create_volume_tab(), "📊 Volumes")
        self.tabs.addTab(self._create_kill_sheet_tab(), "🛡️ Kill Sheet")
        self.tabs.addTab(self._create_unit_converter_tab(), "📏 Units")
        
        layout.addWidget(self.tabs)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
    
    def _create_hydraulics_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)
        layout.setSpacing(10)
        
        layout.addRow(QLabel("<b>Annular Velocity</b>"))
        
        self.flow_rate = QDoubleSpinBox()
        self.flow_rate.setRange(0, 2000)
        self.flow_rate.setSuffix(" gpm")
        self.flow_rate.setValue(500)
        layout.addRow("Flow Rate (Q):", self.flow_rate)
        
        self.hole_diameter = QDoubleSpinBox()
        self.hole_diameter.setRange(0, 50)
        self.hole_diameter.setDecimals(3)
        self.hole_diameter.setSuffix(" in")
        self.hole_diameter.setValue(8.5)
        layout.addRow("Hole Diameter (Dh):", self.hole_diameter)
        
        self.pipe_od = QDoubleSpinBox()
        self.pipe_od.setRange(0, 30)
        self.pipe_od.setDecimals(3)
        self.pipe_od.setSuffix(" in")
        self.pipe_od.setValue(5.0)
        layout.addRow("Pipe OD (Dp):", self.pipe_od)
        
        calc_av_btn = QPushButton("🔄 Calculate AV")
        calc_av_btn.clicked.connect(self._calc_annular_velocity)
        layout.addRow(calc_av_btn)
        
        self.av_result = QLabel("AV = -- ft/min")
        self.av_result.setStyleSheet("font-size: 14px; font-weight: bold; color: #27ae60; padding: 10px;")
        layout.addRow("Result:", self.av_result)
        
        # Separator
        layout.addRow(QLabel(""))
        layout.addRow(QLabel("<b>Bit Hydraulics</b>"))
        
        self.pump_pressure = QDoubleSpinBox()
        self.pump_pressure.setRange(0, 10000)
        self.pump_pressure.setSuffix(" psi")
        self.pump_pressure.setValue(3000)
        layout.addRow("Pump Pressure:", self.pump_pressure)

        self.mud_weight = QDoubleSpinBox()
        self.mud_weight.setRange(0, 25)
        self.mud_weight.setDecimals(2)
        self.mud_weight.setSuffix(" ppg")
        self.mud_weight.setValue(12.0)
        layout.addRow("Mud Weight (MW):", self.mud_weight)
        
        self.tfa_input = QDoubleSpinBox()
        self.tfa_input.setRange(0, 5)
        self.tfa_input.setDecimals(3)
        self.tfa_input.setSuffix(" in²")
        self.tfa_input.setValue(0.5)
        layout.addRow("TFA:", self.tfa_input)
        
        calc_hsi_btn = QPushButton("🔄 Calculate HSI & Impact Force")
        calc_hsi_btn.clicked.connect(self._calc_hsi)
        layout.addRow(calc_hsi_btn)
        
        self.hsi_result = QLabel("HSI = -- | IF = -- lbs")
        self.hsi_result.setStyleSheet("font-size: 14px; font-weight: bold; color: #3498db; padding: 10px;")
        layout.addRow("Result:", self.hsi_result)
        
        return tab
    
    def _create_volume_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)
        layout.setSpacing(10)
        
        layout.addRow(QLabel("<b>Annular Volume</b>"))
        
        self.vol_hole_dia = QDoubleSpinBox()
        self.vol_hole_dia.setRange(0, 50)
        self.vol_hole_dia.setDecimals(3)
        self.vol_hole_dia.setSuffix(" in")
        self.vol_hole_dia.setValue(8.5)
        layout.addRow("Hole Diameter:", self.vol_hole_dia)
        
        self.vol_pipe_od = QDoubleSpinBox()
        self.vol_pipe_od.setRange(0, 30)
        self.vol_pipe_od.setDecimals(3)
        self.vol_pipe_od.setSuffix(" in")
        self.vol_pipe_od.setValue(5.0)
        layout.addRow("Pipe OD:", self.vol_pipe_od)
        
        self.vol_length = QDoubleSpinBox()
        self.vol_length.setRange(0, 20000)
        self.vol_length.setSuffix(" m")
        self.vol_length.setValue(1000)
        layout.addRow("Length:", self.vol_length)
        
        calc_vol_btn = QPushButton("🔄 Calculate Volume")
        calc_vol_btn.clicked.connect(self._calc_annular_volume)
        layout.addRow(calc_vol_btn)
        
        self.vol_result = QLabel("Volume = -- bbl | -- m³")
        self.vol_result.setStyleSheet("font-size: 14px; font-weight: bold; color: #9b59b6; padding: 10px;")
        layout.addRow("Result:", self.vol_result)
        
        # Pipe Capacity
        layout.addRow(QLabel(""))
        layout.addRow(QLabel("<b>Pipe Capacity</b>"))
        
        self.pipe_id = QDoubleSpinBox()
        self.pipe_id.setRange(0, 30)
        self.pipe_id.setDecimals(3)
        self.pipe_id.setSuffix(" in")
        self.pipe_id.setValue(4.276)
        layout.addRow("Pipe ID:", self.pipe_id)
        
        self.pipe_length = QDoubleSpinBox()
        self.pipe_length.setRange(0, 20000)
        self.pipe_length.setSuffix(" m")
        self.pipe_length.setValue(3000)
        layout.addRow("Pipe Length:", self.pipe_length)
        
        calc_cap_btn = QPushButton("🔄 Calculate Capacity")
        calc_cap_btn.clicked.connect(self._calc_pipe_capacity)
        layout.addRow(calc_cap_btn)
        
        self.cap_result = QLabel("Capacity = -- bbl")
        self.cap_result.setStyleSheet("font-size: 14px; font-weight: bold; color: #e67e22; padding: 10px;")
        layout.addRow("Result:", self.cap_result)
        
        return tab
    
    def _create_kill_sheet_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)
        layout.setSpacing(10)
        
        layout.addRow(QLabel("<b>Kill Sheet Calculator</b>"))
        
        self.tvd = QDoubleSpinBox()
        self.tvd.setRange(0, 20000)
        self.tvd.setSuffix(" m")
        self.tvd.setValue(3000)
        layout.addRow("TVD:", self.tvd)
        
        self.current_mw = QDoubleSpinBox()
        self.current_mw.setRange(0, 200)
        self.current_mw.setDecimals(1)
        self.current_mw.setSuffix(" pcf")
        self.current_mw.setValue(75)
        layout.addRow("Current MW:", self.current_mw)
        
        self.sidpp = QDoubleSpinBox()
        self.sidpp.setRange(0, 10000)
        self.sidpp.setSuffix(" psi")
        self.sidpp.setValue(500)
        layout.addRow("SIDPP:", self.sidpp)
        
        self.sicp = QDoubleSpinBox()
        self.sicp.setRange(0, 10000)
        self.sicp.setSuffix(" psi")
        self.sicp.setValue(700)
        layout.addRow("SICP:", self.sicp)
        
        self.slow_pump_rate = QDoubleSpinBox()
        self.slow_pump_rate.setRange(0, 5000)
        self.slow_pump_rate.setSuffix(" psi")
        self.slow_pump_rate.setValue(800)
        layout.addRow("Slow Pump Rate Pressure:", self.slow_pump_rate)

        self.shoe_tvd = QDoubleSpinBox()
        self.shoe_tvd.setRange(0, 20000)
        self.shoe_tvd.setSuffix(" m")
        self.shoe_tvd.setValue(0)
        layout.addRow("Shoe TVD (0 = skip MAASP):", self.shoe_tvd)

        self.frac_grad = QDoubleSpinBox()
        self.frac_grad.setRange(0, 2)
        self.frac_grad.setDecimals(3)
        self.frac_grad.setSuffix(" psi/ft")
        self.frac_grad.setValue(0.8)
        layout.addRow("Fracture Gradient:", self.frac_grad)
        
        calc_kill_btn = QPushButton("🔄 Calculate Kill Parameters")
        calc_kill_btn.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold; padding: 8px;")
        calc_kill_btn.clicked.connect(self._calc_kill_sheet)
        layout.addRow(calc_kill_btn)
        
        self.kill_result = QTextEdit()
        self.kill_result.setReadOnly(True)
        self.kill_result.setMaximumHeight(200)
        self.kill_result.setStyleSheet("font-family: Consolas; font-size: 12px; background: #f8f9fa;")
        layout.addRow("Results:", self.kill_result)
        
        return tab
    
    def _create_unit_converter_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)
        layout.setSpacing(10)
        
        layout.addRow(QLabel("<b>Unit Converter</b>"))
        
        # Depth conversion
        layout.addRow(QLabel("<b>Depth:</b>"))
        self.meters_input = QDoubleSpinBox()
        self.meters_input.setRange(0, 99999)
        self.meters_input.setDecimals(2)
        self.meters_input.setSuffix(" m")
        self.meters_input.valueChanged.connect(self._convert_depth_m_to_ft)
        layout.addRow("Meters:", self.meters_input)
        
        self.feet_input = QDoubleSpinBox()
        self.feet_input.setRange(0, 999999)
        self.feet_input.setDecimals(2)
        self.feet_input.setSuffix(" ft")
        self.feet_input.valueChanged.connect(self._convert_depth_ft_to_m)
        layout.addRow("Feet:", self.feet_input)
        
        # Weight conversion
        layout.addRow(QLabel(""))
        layout.addRow(QLabel("<b>Mud Weight:</b>"))
        self.pcf_input = QDoubleSpinBox()
        self.pcf_input.setRange(0, 300)
        self.pcf_input.setDecimals(1)
        self.pcf_input.setSuffix(" pcf")
        self.pcf_input.valueChanged.connect(self._convert_mw_pcf)
        layout.addRow("PCF:", self.pcf_input)
        
        self.ppg_input = QDoubleSpinBox()
        self.ppg_input.setRange(0, 30)
        self.ppg_input.setDecimals(2)
        self.ppg_input.setSuffix(" ppg")
        layout.addRow("PPG:", self.ppg_input)
        
        self.sg_input = QDoubleSpinBox()
        self.sg_input.setRange(0, 5)
        self.sg_input.setDecimals(3)
        self.sg_input.setSuffix(" SG")
        layout.addRow("SG:", self.sg_input)
        
        # Pressure conversion
        layout.addRow(QLabel(""))
        layout.addRow(QLabel("<b>Pressure:</b>"))
        self.psi_input = QDoubleSpinBox()
        self.psi_input.setRange(0, 99999)
        self.psi_input.setDecimals(1)
        self.psi_input.setSuffix(" psi")
        self.psi_input.valueChanged.connect(self._convert_pressure_psi)
        layout.addRow("PSI:", self.psi_input)
        
        self.bar_input = QDoubleSpinBox()
        self.bar_input.setRange(0, 9999)
        self.bar_input.setDecimals(2)
        self.bar_input.setSuffix(" bar")
        layout.addRow("Bar:", self.bar_input)
        
        self.kpa_input = QDoubleSpinBox()
        self.kpa_input.setRange(0, 999999)
        self.kpa_input.setDecimals(1)
        self.kpa_input.setSuffix(" kPa")
        layout.addRow("kPa:", self.kpa_input)
        
        return tab
    
    # -------- Calculation Methods --------
    def _calc_annular_velocity(self):
        Q = self.flow_rate.value()
        Dh = self.hole_diameter.value()
        Dp = self.pipe_od.value()
        
        if Dh <= Dp:
            self.av_result.setText("❌ Hole diameter must be > Pipe OD")
            return

        # Canonical annular velocity (HydraulicsEngine.calculate_annular_velocity)
        from core.engineering.core import HydraulicsEngine
        av = HydraulicsEngine.calculate_annular_velocity(Q, Dh, Dp)
        self.av_result.setText(f"AV = {av:.1f} ft/min  ({av * 0.3048:.1f} m/min)")
    
    def _calc_hsi(self):
        from core.hydraulics_engine import AdvancedHydraulicsEngine
        Q = self.flow_rate.value()
        mw = self.mud_weight.value()
        TFA = self.tfa_input.value()
        bit_size = self.hole_diameter.value()

        if TFA <= 0 or Q <= 0 or mw <= 0:
            self.hsi_result.setText("❌ Invalid inputs (need Q, MW, TFA > 0)")
            return

        # Canonical bit hydraulics (ΔP from TFA, then HHP/HSI/JV/IF)
        bh = AdvancedHydraulicsEngine.calc_bit_hydraulics(Q, mw, TFA, bit_size)
        self.hsi_result.setText(
            f"Bit ΔP = {bh['bit_pressure_drop_psi']:.0f} psi | "
            f"HHP = {bh['bit_hhp']:.1f} hp | HSI = {bh['hsi']:.2f} hp/in²\n"
            f"Nozzle Vel = {bh['jet_velocity_fps']:.0f} ft/s | "
            f"IF = {bh['impact_force_lbs']:.0f} lbs"
        )
    
    def _calc_annular_volume(self):
        Dh = self.vol_hole_dia.value()
        Dp = self.vol_pipe_od.value()
        L = self.vol_length.value()
        
        if Dh <= Dp:
            self.vol_result.setText("❌ Hole diameter must be > Pipe OD")
            return
        
        L_ft = L * 3.28084
        # Canonical annular volume / capacity (AdvancedHydraulicsEngine)
        from core.hydraulics_engine import AdvancedHydraulicsEngine
        vol_bbl = AdvancedHydraulicsEngine.calc_annular_volume(Dh, Dp, L_ft)
        vol_m3 = vol_bbl * 0.158987

        # Annular capacity (bbl/ft) — canonical
        cap_bbl_ft = AdvancedHydraulicsEngine.calc_annular_capacity_bbl_ft(Dh, Dp)

        self.vol_result.setText(
            f"Volume = {vol_bbl:.1f} bbl ({vol_m3:.2f} m³)\n"
            f"Capacity = {cap_bbl_ft:.4f} bbl/ft"
        )
    
    def _calc_pipe_capacity(self):
        ID = self.pipe_id.value()
        L = self.pipe_length.value()
        
        if ID <= 0 or L <= 0:
            self.cap_result.setText("❌ Invalid inputs")
            return
        
        L_ft = L * 3.28084
        # Canonical pipe capacity (AdvancedHydraulicsEngine)
        from core.hydraulics_engine import AdvancedHydraulicsEngine
        cap = AdvancedHydraulicsEngine.calc_pipe_capacity_bbl(ID, L_ft)
        cap_per_m = cap / L if L > 0 else 0
        
        self.cap_result.setText(
            f"Capacity = {cap:.1f} bbl ({cap * 0.158987:.2f} m³)\n"
            f"Per meter = {cap_per_m:.4f} bbl/m"
        )
    
    def _calc_kill_sheet(self):
        from core.engineering.engines.well_control import WellControlEngine
        tvd = self.tvd.value()
        mw = self.current_mw.value()
        sidpp = self.sidpp.value()
        sicp = self.sicp.value()
        spr = self.slow_pump_rate.value()
        
        if tvd <= 0 or mw <= 0:
            self.kill_result.setText("❌ TVD and MW must be > 0")
            return
        
        tvd_ft = tvd * 3.28084
        mw_ppg = mw / 7.48  # pcf to ppg

        # Canonical kill MW, ICP, FCP (IWCF)
        kmw_r = WellControlEngine.kill_mw(mw_ppg, sidpp, tvd_ft)
        if not kmw_r.success:
            self.kill_result.setText(f"❌ {kmw_r.error}")
            return
        kmw_ppg = kmw_r.value
        kmw_pcf = kmw_ppg * 7.48
        icp = spr + sidpp
        fcp = spr * (kmw_ppg / mw_ppg)

        # MAASP only when the user provides a shoe TVD (no invented values)
        maasp_text = "n/a (enter Shoe TVD)"
        if self.shoe_tvd.value() > 0:
            maasp_r = WellControlEngine.maasp(
                max_allowable_mw_ppg=self.frac_grad.value() / 0.052,
                current_mw_ppg=mw_ppg,
                shoe_tvd_ft=self.shoe_tvd.value() * 3.28084,
            )
            if maasp_r.success:
                maasp_text = f"{maasp_r.value:.0f} psi"
        
        result = f"""╔══════════════════════════════════════╗
║         KILL SHEET CALCULATIONS       ║
╠══════════════════════════════════════╣
║ TVD:              {tvd:.1f} m ({tvd_ft:.0f} ft)
║ Current MW:       {mw:.1f} pcf ({mw_ppg:.2f} ppg)
║ SIDPP:            {sidpp:.0f} psi
║ SICP:             {sicp:.0f} psi
║ Slow Pump Rate:   {spr:.0f} psi
╠══════════════════════════════════════╣
║ RESULTS:
║ Kill Mud Weight:  {kmw_pcf:.1f} pcf ({kmw_ppg:.2f} ppg)
║ MW Increase:      {kmw_pcf - mw:.1f} pcf
║ ICP:              {icp:.0f} psi
║ FCP:              {fcp:.0f} psi
║ MAASP:            {maasp_text}
╠══════════════════════════════════════╣
║ Method: Driller's Method
║ Step 1: Circulate with current MW
║         Pressure: {icp:.0f} psi (ICP)
║ Step 2: Weight up to {kmw_ppg:.2f} ppg
║ Step 3: Circulate with kill MW
║         Pressure: {fcp:.0f} psi (FCP)
╚══════════════════════════════════════╝"""
        
        self.kill_result.setText(result)
    
    # -------- Unit Converters --------
    def _convert_depth_m_to_ft(self):
        m = self.meters_input.value()
        self.feet_input.blockSignals(True)
        self.feet_input.setValue(m * 3.28084)
        self.feet_input.blockSignals(False)
    
    def _convert_depth_ft_to_m(self):
        ft = self.feet_input.value()
        self.meters_input.blockSignals(True)
        self.meters_input.setValue(ft / 3.28084)
        self.meters_input.blockSignals(False)
    
    def _convert_mw_pcf(self):
        pcf = self.pcf_input.value()
        self.ppg_input.blockSignals(True)
        self.sg_input.blockSignals(True)
        self.ppg_input.setValue(pcf / 7.48052)
        self.sg_input.setValue(pcf / 62.428)
        self.ppg_input.blockSignals(False)
        self.sg_input.blockSignals(False)
    
    def _convert_pressure_psi(self):
        psi = self.psi_input.value()
        self.bar_input.blockSignals(True)
        self.kpa_input.blockSignals(True)
        self.bar_input.setValue(psi * 0.0689476)
        self.kpa_input.setValue(psi * 6.89476)
        self.bar_input.blockSignals(False)
        self.kpa_input.blockSignals(False)