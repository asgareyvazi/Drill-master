# dialogs/drilling_report_dialogs.py
"""
Drilling Report Dialogs
دیالوگ‌های حرفه‌ای برای Bit Record, BHA, Casing Tally
"""
import logging
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

logger = logging.getLogger(__name__)


# ==================== Bit Record Dialog ====================
def _not_recorded(spin):
    """Give a measurement spin box an explicit "not recorded" state.

    These dialogs previously started at 0 (and bit size at a fabricated 8.5 in),
    so an absent measurement was saved as a measured zero. The minimum now carries
    the sentinel and reads back as ``None``.
    """
    spin.setMinimum(-1)
    spin.setSpecialValueText("Not recorded")
    return spin


def _spin_value(spin):
    """Sentinel-aware read: a value at the minimum means "not recorded"."""
    return None if spin.value() <= spin.minimum() else spin.value()


def _spin_text(spin):
    """Text for persistence: an unrecorded measurement is blank, never "0.0"."""
    value = _spin_value(spin)
    return "" if value is None else str(value)


class AddBitRecordDialog(QDialog):
    """دیالوگ اضافه کردن رکورد مته"""

    BIT_TYPES = ["PDC", "Tricone", "Impregnated", "Diamond", "Hybrid", "Bi-Center"]
    
    MANUFACTURERS = [
        "Smith Bits (Schlumberger)", "Hughes Christensen (Baker Hughes)",
        "Security DBS (Halliburton)", "Reed Hycalog", "Varel International",
        "National Oilwell Varco", "Ulterra", "Other"
    ]

    IADC_CODES = {
        "PDC": ["M222", "M323", "M333", "M423", "M433", "M443", "M523", "M533"],
        "Tricone": ["111", "117", "211", "217", "311", "317", "411", "417", "511", "517"],
    }

    PULL_REASONS = [
        "TD Reached", "Bit Worn", "Change BHA", "Lost Nozzle",
        "Broken Teeth/Cutters", "Under Gauge", "Plugged Nozzle",
        "Low ROP", "Formation Change", "Directional Requirements",
        "Coring", "Fishing", "Other"
    ]

    DULL_GRADES = {
        "Inner Rows (I)": ["0","1","2","3","4","5","6","7","8"],
        "Outer Rows (O)": ["0","1","2","3","4","5","6","7","8"],
        "Dull Char (D)": ["BT","CT","ER","FC","HC","JD","LC","NR","OC","PB","PN","RO","SD","SS","TR","WO","WT"],
        "Location (L)": ["N","M","G","A","H","C","T"],
        "Bearing/Seal (B)": ["0","1","2","3","4","5","6","7","8","E","F","N","X"],
        "Gauge (G)": ["I","1","2","3","4","5","6","7","8","O"],
    }

    def __init__(self, parent=None, edit_data=None, bit_number=1):
        super().__init__(parent)
        self.result = None
        self.edit_data = edit_data
        self.setWindowTitle("🧱 Bit Record" if not edit_data else "🧱 Edit Bit Record")
        self.setMinimumWidth(600)
        self.setMinimumHeight(600)
        self.bit_number = bit_number
        self.init_ui()
        if edit_data:
            self._load(edit_data)

    def init_ui(self):
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        main = QVBoxLayout(content)

        # Bit Info
        g1 = QGroupBox("🧱 Bit Information")
        f1 = QFormLayout(g1)

        self.bit_no = QLineEdit(str(self.bit_number))
        self.bit_size = _not_recorded(QDoubleSpinBox())
        self.bit_size.setMaximum(50)
        self.bit_size.setDecimals(3)
        self.bit_size.setValue(-1)
        self.bit_size.setSuffix(" in")

        self.bit_type = QComboBox()
        self.bit_type.addItems(self.BIT_TYPES)
        self.bit_type.currentTextChanged.connect(self._on_type_changed)

        self.manufacturer = QComboBox()
        self.manufacturer.addItems(self.MANUFACTURERS)
        self.manufacturer.setEditable(True)

        self.iadc_code = QComboBox()
        self.iadc_code.setEditable(True)
        self._on_type_changed(self.bit_type.currentText())

        self.serial_no = QLineEdit()
        self.serial_no.setPlaceholderText("Serial number")

        self.bha_no = QLineEdit()
        self.bha_no.setPlaceholderText("BHA Run #")

        f1.addRow("Bit No:", self.bit_no)
        f1.addRow("Bit Size:", self.bit_size)
        f1.addRow("Bit Type:", self.bit_type)
        f1.addRow("Manufacturer:", self.manufacturer)
        f1.addRow("IADC Code:", self.iadc_code)
        f1.addRow("Serial No:", self.serial_no)
        f1.addRow("BHA No:", self.bha_no)
        main.addWidget(g1)

        # Nozzles
        g_nzl = QGroupBox("🔵 Nozzles")
        nzl_layout = QFormLayout(g_nzl)
        self.jets = QLineEdit()
        self.jets.setPlaceholderText("e.g., 3x16 or 16-16-14")
        self.tfa = _not_recorded(QDoubleSpinBox())
        self.tfa.setMaximum(5)
        self.tfa.setDecimals(4)
        self.tfa.setValue(-1)
        self.tfa.setSuffix(" in²")
        nzl_layout.addRow("Jets:", self.jets)
        nzl_layout.addRow("TFA:", self.tfa)
        main.addWidget(g_nzl)

        # Depth & Performance
        g2 = QGroupBox("📏 Depth & Performance")
        f2 = QGridLayout(g2)

        self.depth_in = _not_recorded(QDoubleSpinBox())
        self.depth_in.setMaximum(20000)
        self.depth_in.setValue(-1)
        self.depth_in.setSuffix(" m")
        self.depth_out = _not_recorded(QDoubleSpinBox())
        self.depth_out.setMaximum(20000)
        self.depth_out.setValue(-1)
        self.depth_out.setSuffix(" m")
        self.metres_drilled = QLabel("0.0 m")
        self.metres_drilled.setStyleSheet("font-weight: bold; color: #27ae60;")

        self.hours = _not_recorded(QDoubleSpinBox())
        self.hours.setMaximum(5000)
        self.hours.setValue(-1)
        self.hours.setDecimals(1)
        self.hours.setSuffix(" hrs")
        self.rop = QLabel("0.0 m/hr")
        self.rop.setStyleSheet("font-weight: bold; color: #3498db;")

        f2.addWidget(QLabel("Depth In:"), 0, 0)
        f2.addWidget(self.depth_in, 0, 1)
        f2.addWidget(QLabel("Depth Out:"), 0, 2)
        f2.addWidget(self.depth_out, 0, 3)
        f2.addWidget(QLabel("Metres Drilled:"), 1, 0)
        f2.addWidget(self.metres_drilled, 1, 1)
        f2.addWidget(QLabel("Hours:"), 1, 2)
        f2.addWidget(self.hours, 1, 3)
        f2.addWidget(QLabel("Avg ROP:"), 2, 0)
        f2.addWidget(self.rop, 2, 1, 1, 3)

        self.depth_in.valueChanged.connect(self._calc)
        self.depth_out.valueChanged.connect(self._calc)
        self.hours.valueChanged.connect(self._calc)

        main.addWidget(g2)

        # Operating Parameters
        g3 = QGroupBox("⚙️ Operating Parameters")
        f3 = QGridLayout(g3)

        self.wob_min = _not_recorded(QDoubleSpinBox())
        self.wob_min.setMaximum(100)
        self.wob_min.setValue(-1)
        self.wob_min.setSuffix(" klb")
        self.wob_max = _not_recorded(QDoubleSpinBox())
        self.wob_max.setMaximum(100)
        self.wob_max.setValue(-1)
        self.wob_max.setSuffix(" klb")

        self.rpm_min = _not_recorded(QDoubleSpinBox())
        self.rpm_min.setMaximum(500)
        self.rpm_min.setValue(-1)
        self.rpm_max = _not_recorded(QDoubleSpinBox())
        self.rpm_max.setMaximum(500)
        self.rpm_max.setValue(-1)

        self.spp_min = _not_recorded(QDoubleSpinBox())
        self.spp_min.setMaximum(10000)
        self.spp_min.setValue(-1)
        self.spp_min.setSuffix(" psi")
        self.spp_max = _not_recorded(QDoubleSpinBox())
        self.spp_max.setMaximum(10000)
        self.spp_max.setValue(-1)
        self.spp_max.setSuffix(" psi")

        self.flow_min = _not_recorded(QDoubleSpinBox())
        self.flow_min.setMaximum(5000)
        self.flow_min.setValue(-1)
        self.flow_min.setSuffix(" gpm")
        self.flow_max = _not_recorded(QDoubleSpinBox())
        self.flow_max.setMaximum(5000)
        self.flow_max.setValue(-1)
        self.flow_max.setSuffix(" gpm")

        self.torque_min = _not_recorded(QDoubleSpinBox())
        self.torque_min.setMaximum(100)
        self.torque_min.setValue(-1)
        self.torque_min.setSuffix(" klb.ft")
        self.torque_max = _not_recorded(QDoubleSpinBox())
        self.torque_max.setMaximum(100)
        self.torque_max.setValue(-1)
        self.torque_max.setSuffix(" klb.ft")

        self.mw = _not_recorded(QDoubleSpinBox())
        self.mw.setMaximum(200)
        self.mw.setValue(-1)
        self.mw.setSuffix(" pcf")

        f3.addWidget(QLabel(""), 0, 0)
        f3.addWidget(QLabel("Min"), 0, 1)
        f3.addWidget(QLabel("Max"), 0, 2)
        f3.addWidget(QLabel("WOB:"), 1, 0)
        f3.addWidget(self.wob_min, 1, 1)
        f3.addWidget(self.wob_max, 1, 2)
        f3.addWidget(QLabel("RPM:"), 2, 0)
        f3.addWidget(self.rpm_min, 2, 1)
        f3.addWidget(self.rpm_max, 2, 2)
        f3.addWidget(QLabel("SPP:"), 3, 0)
        f3.addWidget(self.spp_min, 3, 1)
        f3.addWidget(self.spp_max, 3, 2)
        f3.addWidget(QLabel("Flow Rate:"), 4, 0)
        f3.addWidget(self.flow_min, 4, 1)
        f3.addWidget(self.flow_max, 4, 2)
        f3.addWidget(QLabel("Torque:"), 5, 0)
        f3.addWidget(self.torque_min, 5, 1)
        f3.addWidget(self.torque_max, 5, 2)
        f3.addWidget(QLabel("MW:"), 6, 0)
        f3.addWidget(self.mw, 6, 1)

        main.addWidget(g3)

        # Dull Grading
        g4 = QGroupBox("📊 Dull Grading (IADC)")
        f4 = QGridLayout(g4)

        self.dull_widgets = {}
        dull_labels = ["Inner(I)", "Outer(O)", "Dull Char(D)", "Location(L)", "Bearing(B)", "Gauge(G)"]
        for i, (label, (key, options)) in enumerate(zip(dull_labels, self.DULL_GRADES.items())):
            f4.addWidget(QLabel(label + ":"), i // 3, (i % 3) * 2)
            combo = QComboBox()
            combo.addItems(options)
            combo.setEditable(True)
            f4.addWidget(combo, i // 3, (i % 3) * 2 + 1)
            self.dull_widgets[key] = combo

        main.addWidget(g4)

        # Reason Pulled
        g5 = QGroupBox("📝 Reason Pulled & Remarks")
        f5 = QFormLayout(g5)
        self.reason = QComboBox()
        self.reason.addItems(self.PULL_REASONS)
        self.reason.setEditable(True)
        self.remarks = QTextEdit()
        self.remarks.setMaximumHeight(60)
        self.remarks.setPlaceholderText("Additional remarks...")
        f5.addRow("Reason Pulled:", self.reason)
        f5.addRow("Remarks:", self.remarks)
        main.addWidget(g5)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("✅ Add Bit Record" if not self.edit_data else "✅ Update")
        save_btn.setStyleSheet("background: #27ae60; color: white; font-weight: bold; padding: 10px 20px; border-radius: 5px; border: none;")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _on_type_changed(self, bit_type):
        self.iadc_code.clear()
        codes = self.IADC_CODES.get(bit_type, self.IADC_CODES.get("PDC", []))
        self.iadc_code.addItems(codes)

    def _calc(self):
        drilled = self.depth_out.value() - self.depth_in.value()
        self.metres_drilled.setText(f"{max(0, drilled):.1f} m")
        hrs = _spin_value(self.hours)
        depth_in, depth_out = _spin_value(self.depth_in), _spin_value(self.depth_out)
        drilled = (depth_out - depth_in) if depth_in is not None and depth_out is not None else None
        if hrs and drilled is not None and drilled > 0:
            self.rop.setText(f"{drilled / hrs:.2f} m/hr")
        else:
            # No measured zero: the calculation is unavailable, not 0.0 m/hr.
            self.rop.setText("— m/hr")

    @staticmethod
    def _loaded(spin, *values):
        """Load the first present measurement; an absent one stays "not recorded"."""
        for value in values:
            if value not in (None, ""):
                try:
                    spin.setValue(float(value))
                except (TypeError, ValueError):
                    spin.setValue(-1)
                return
        spin.setValue(-1)

    def _load(self, data):
        self.bit_no.setText(str(data.get('Bit No', '')))
        self._loaded(self.bit_size, data.get('Size (in)'), data.get('bit_size'))
        idx = self.bit_type.findText(str(data.get('Type', data.get('bit_type', ''))))
        if idx >= 0:
            self.bit_type.setCurrentIndex(idx)
        self._loaded(self.depth_in, data.get('Depth In (m)'), data.get('depth_in'))
        self._loaded(self.depth_out, data.get('Depth Out (m)'), data.get('depth_out'))
        self._loaded(self.hours, data.get('Hours'), data.get('hours_on_bottom'))
        self._loaded(self.wob_min, data.get('WOB Min (klb)'))
        self._loaded(self.wob_max, data.get('WOB Max (klb)'))
        self._loaded(self.rpm_min, data.get('Rot. Min'))
        self._loaded(self.rpm_max, data.get('Rot. Max'))
        self._loaded(self.spp_min, data.get('SPP Min (psi)'))
        self._loaded(self.spp_max, data.get('SPP Max (psi)'))
        self._loaded(self.flow_min, data.get('FR Min'))
        self._loaded(self.flow_max, data.get('FR Max'))
        self._loaded(self.torque_min, data.get('TQ Min (klb.ft)'))
        self._loaded(self.torque_max, data.get('TQ Max (klb.ft)'))
        self._loaded(self.mw, data.get('MW (pcf)'))
        self._loaded(self.tfa, data.get('TFA (in²)'))

    def _save(self):
        depth_in, depth_out, hrs = (_spin_value(self.depth_in),
                                    _spin_value(self.depth_out),
                                    _spin_value(self.hours))
        # A drilled interval or ROP cannot be computed from an unrecorded term.
        drilled = (max(0.0, depth_out - depth_in)
                   if depth_in is not None and depth_out is not None else None)
        rop = (drilled / hrs) if (drilled is not None and hrs) else None

        # Dull grade string
        dull_parts = []
        for key, combo in self.dull_widgets.items():
            dull_parts.append(combo.currentText())
        dull_grade = "/".join(dull_parts)

        self.result = {
            "Bit No": self.bit_no.text(),
            "Size (in)": _spin_text(self.bit_size),
            "Manufacture": self.manufacturer.currentText(),
            "BHA No": self.bha_no.text(),
            "Type": self.bit_type.currentText(),
            "IADC Code": self.iadc_code.currentText(),
            "Serial No": self.serial_no.text(),
            "Jets": self.jets.text(),
            "CMT": "New" if not self.edit_data else "Rerun",
            "Depth In (m)": _spin_text(self.depth_in),
            "Depth Out (m)": _spin_text(self.depth_out),
            "Formation": "",
            "Metres Drilled": "" if drilled is None else str(round(drilled, 1)),
            "Hours": _spin_text(self.hours),
            "ROP (m/hr)": "" if rop is None else str(round(rop, 2)),
            "WOB Min (klb)": _spin_text(self.wob_min),
            "WOB Max (klb)": _spin_text(self.wob_max),
            "Rot. Min": _spin_text(self.rpm_min),
            "Rot. Max": _spin_text(self.rpm_max),
            "SPP Min (psi)": _spin_text(self.spp_min),
            "SPP Max (psi)": _spin_text(self.spp_max),
            "FR Min": _spin_text(self.flow_min),
            "FR Max": _spin_text(self.flow_max),
            "TQ Min (klb.ft)": _spin_text(self.torque_min),
            "TQ Max (klb.ft)": _spin_text(self.torque_max),
            "MW (pcf)": _spin_text(self.mw),
            "TFA (in²)": _spin_text(self.tfa),
            "Dull Grade": dull_grade,
            "Reason Pulled": self.reason.currentText(),
            "Remarks": self.remarks.toPlainText(),
        }
        self.accept()

    def get_result(self):
        return self.result


# ==================== BHA Component Dialog ====================
class AddBHAComponentDialog(QDialog):
    """دیالوگ اضافه کردن کامپوننت BHA"""

    TOOL_TYPES = [
        "Bit", "Sub (Bit Sub)", "Motor (PDM)", "MWD", "LWD", "RSS",
        "Stabilizer (Near Bit)", "Stabilizer (String)",
        "Drill Collar", "HWDP", "Jar (Hydraulic)", "Jar (Mechanical)",
        "Shock Sub", "Float Sub", "X-Over Sub", "Non-Mag Collar",
        "Reamer", "Hole Opener", "Under Reamer",
        "Circulating Sub", "Safety Joint", "Fishing Neck",
    ]

    def __init__(self, parent=None, edit_data=None):
        super().__init__(parent)
        self.result = None
        self.edit_data = edit_data
        self.setWindowTitle("🔧 BHA Component")
        self.setMinimumWidth(500)
        self.init_ui()
        if edit_data:
            self._load(edit_data)

    def init_ui(self):
        layout = QVBoxLayout(self)

        g1 = QGroupBox("🔧 Component Details")
        f1 = QFormLayout(g1)

        self.tool_type = QComboBox()
        self.tool_type.addItems(self.TOOL_TYPES)
        self.tool_type.setEditable(True)
        f1.addRow("Tool Type:", self.tool_type)

        self.description = QLineEdit()
        self.description.setPlaceholderText("e.g., 6-3/4\" PDM Motor 1.15° Bend")
        f1.addRow("Description:", self.description)

        self.od = _not_recorded(QDoubleSpinBox())
        self.od.setMaximum(50)
        self.od.setValue(-1)
        self.od.setDecimals(3)
        self.od.setSuffix(" in")
        f1.addRow("OD:", self.od)

        self.id_ = _not_recorded(QDoubleSpinBox())
        self.id_.setMaximum(50)
        self.id_.setValue(-1)
        self.id_.setDecimals(3)
        self.id_.setSuffix(" in")
        f1.addRow("ID:", self.id_)

        self.length = _not_recorded(QDoubleSpinBox())
        self.length.setMaximum(100)
        self.length.setValue(-1)
        self.length.setDecimals(2)
        self.length.setSuffix(" m")
        f1.addRow("Length:", self.length)

        self.serial = QLineEdit()
        self.serial.setPlaceholderText("Serial number")
        f1.addRow("Serial No:", self.serial)

        self.weight = _not_recorded(QDoubleSpinBox())
        self.weight.setMaximum(10000)
        self.weight.setValue(-1)
        self.weight.setSuffix(" kg")
        f1.addRow("Weight:", self.weight)

        self.connection_top = QComboBox()
        self.connection_top.addItems([
            "NC38", "NC40", "NC46", "NC50", "4-1/2 IF",
            "4-1/2 FH", "5-1/2 FH", "6-5/8 FH",
            "6-5/8 API Reg", "7-5/8 API Reg", "Other"
        ])
        self.connection_top.setEditable(True)
        f1.addRow("Connection (Top):", self.connection_top)

        self.connection_bot = QComboBox()
        self.connection_bot.addItems([
            "NC38", "NC40", "NC46", "NC50", "4-1/2 IF",
            "4-1/2 FH", "5-1/2 FH", "6-5/8 FH",
            "6-5/8 API Reg", "7-5/8 API Reg", "Other"
        ])
        self.connection_bot.setEditable(True)
        f1.addRow("Connection (Bottom):", self.connection_bot)

        self.torque = _not_recorded(QDoubleSpinBox())
        self.torque.setMaximum(200000)
        self.torque.setValue(-1)
        self.torque.setSuffix(" ft-lb")
        f1.addRow("MU Torque:", self.torque)

        self.remarks = QLineEdit()
        self.remarks.setPlaceholderText("Notes...")
        f1.addRow("Remarks:", self.remarks)

        layout.addWidget(g1)

        # Buttons
        btn = QHBoxLayout()
        save = QPushButton("✅ Add" if not self.edit_data else "✅ Update")
        save.setStyleSheet("background: #27ae60; color: white; font-weight: bold; padding: 8px 20px; border-radius: 4px; border: none;")
        save.clicked.connect(self._save)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn.addStretch()
        btn.addWidget(save)
        btn.addWidget(cancel)
        layout.addLayout(btn)

    def _load(self, data):
        if isinstance(data, dict):
            idx = self.tool_type.findText(data.get('Tool Type', ''))
            if idx >= 0:
                self.tool_type.setCurrentIndex(idx)
            else:
                self.tool_type.setCurrentText(data.get('Tool Type', ''))
            self.description.setText(str(data.get("Component Name") or data.get("Description") or ""))
            self._loaded(self.od, data.get('OD (in)'))
            self._loaded(self.id_, data.get('ID (in)'))
            self._loaded(self.length, data.get('Length (m)'))
            self.serial.setText(str(data.get('Serial No', '')))
            self._loaded(self.weight, data.get('Weight (kg)'))
            self._loaded(self.torque, data.get('Make-up Torque (ft-lb)'))
            self.remarks.setText(str(data.get('Remarks', '')))

    def _save(self):
        self.result = {
            "Tool Type": self.tool_type.currentText(),
            "Component Name": self.description.text(),
            "OD (in)": _spin_text(self.od),
            "ID (in)": _spin_text(self.id_),
            "Length (m)": _spin_text(self.length),
            "Serial No": self.serial.text(),
            "Weight (kg)": _spin_text(self.weight),
            "Connection Type": f"{self.connection_top.currentText()} / {self.connection_bot.currentText()}",
            "Make-up Torque (ft-lb)": _spin_text(self.torque),
            "Remarks": self.remarks.text(),
        }
        self.accept()

    def get_result(self):
        return self.result