# dialogs/drilling_report_dialogs.py
"""
Drilling Report Dialogs
دیالوگ‌های حرفه‌ای برای Bit Record, BHA, Casing Tally
"""
import math
import logging
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

logger = logging.getLogger(__name__)


# ==================== Bit Record Dialog ====================
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
        self.bit_size = QDoubleSpinBox()
        self.bit_size.setRange(0, 50)
        self.bit_size.setDecimals(3)
        self.bit_size.setValue(8.5)
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
        self.tfa = QDoubleSpinBox()
        self.tfa.setRange(0, 5)
        self.tfa.setDecimals(4)
        self.tfa.setSuffix(" in²")
        nzl_layout.addRow("Jets:", self.jets)
        nzl_layout.addRow("TFA:", self.tfa)
        main.addWidget(g_nzl)

        # Depth & Performance
        g2 = QGroupBox("📏 Depth & Performance")
        f2 = QGridLayout(g2)

        self.depth_in = QDoubleSpinBox()
        self.depth_in.setRange(0, 20000)
        self.depth_in.setSuffix(" m")
        self.depth_out = QDoubleSpinBox()
        self.depth_out.setRange(0, 20000)
        self.depth_out.setSuffix(" m")
        self.metres_drilled = QLabel("0.0 m")
        self.metres_drilled.setStyleSheet("font-weight: bold; color: #27ae60;")

        self.hours = QDoubleSpinBox()
        self.hours.setRange(0, 5000)
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

        self.wob_min = QDoubleSpinBox()
        self.wob_min.setRange(0, 100)
        self.wob_min.setSuffix(" klb")
        self.wob_max = QDoubleSpinBox()
        self.wob_max.setRange(0, 100)
        self.wob_max.setSuffix(" klb")

        self.rpm_min = QDoubleSpinBox()
        self.rpm_min.setRange(0, 500)
        self.rpm_max = QDoubleSpinBox()
        self.rpm_max.setRange(0, 500)

        self.spp_min = QDoubleSpinBox()
        self.spp_min.setRange(0, 10000)
        self.spp_min.setSuffix(" psi")
        self.spp_max = QDoubleSpinBox()
        self.spp_max.setRange(0, 10000)
        self.spp_max.setSuffix(" psi")

        self.flow_min = QDoubleSpinBox()
        self.flow_min.setRange(0, 5000)
        self.flow_min.setSuffix(" gpm")
        self.flow_max = QDoubleSpinBox()
        self.flow_max.setRange(0, 5000)
        self.flow_max.setSuffix(" gpm")

        self.torque_min = QDoubleSpinBox()
        self.torque_min.setRange(0, 100)
        self.torque_min.setSuffix(" klb.ft")
        self.torque_max = QDoubleSpinBox()
        self.torque_max.setRange(0, 100)
        self.torque_max.setSuffix(" klb.ft")

        self.mw = QDoubleSpinBox()
        self.mw.setRange(0, 200)
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
        hrs = self.hours.value()
        if hrs > 0 and drilled > 0:
            rop = drilled / hrs
            self.rop.setText(f"{rop:.2f} m/hr")
        else:
            self.rop.setText("0.0 m/hr")

    def _load(self, data):
        self.bit_no.setText(str(data.get('Bit No', '')))
        self.bit_size.setValue(float(data.get('Size (in)', data.get('bit_size', 8.5)) or 8.5))
        idx = self.bit_type.findText(str(data.get('Type', data.get('bit_type', ''))))
        if idx >= 0:
            self.bit_type.setCurrentIndex(idx)
        self.depth_in.setValue(float(data.get('Depth In (m)', data.get('depth_in', 0)) or 0))
        self.depth_out.setValue(float(data.get('Depth Out (m)', data.get('depth_out', 0)) or 0))
        self.hours.setValue(float(data.get('Hours', data.get('hours_on_bottom', 0)) or 0))
        self.wob_min.setValue(float(data.get('WOB Min (klb)', 0) or 0))
        self.wob_max.setValue(float(data.get('WOB Max (klb)', 0) or 0))
        self.rpm_min.setValue(float(data.get('Rot. Min', 0) or 0))
        self.rpm_max.setValue(float(data.get('Rot. Max', 0) or 0))

    def _save(self):
        drilled = max(0, self.depth_out.value() - self.depth_in.value())
        hrs = self.hours.value()
        rop = drilled / hrs if hrs > 0 else 0

        # Dull grade string
        dull_parts = []
        for key, combo in self.dull_widgets.items():
            dull_parts.append(combo.currentText())
        dull_grade = "/".join(dull_parts)

        self.result = {
            "Bit No": self.bit_no.text(),
            "Size (in)": str(self.bit_size.value()),
            "Manufacture": self.manufacturer.currentText(),
            "BHA No": self.bha_no.text(),
            "Type": self.bit_type.currentText(),
            "IADC Code": self.iadc_code.currentText(),
            "Serial No": self.serial_no.text(),
            "Jets": self.jets.text(),
            "CMT": "New" if not self.edit_data else "Rerun",
            "Depth In (m)": str(self.depth_in.value()),
            "Depth Out (m)": str(self.depth_out.value()),
            "Formation": "",
            "Metres Drilled": str(round(drilled, 1)),
            "Hours": str(self.hours.value()),
            "ROP (m/hr)": str(round(rop, 2)),
            "WOB Min (klb)": str(self.wob_min.value()),
            "WOB Max (klb)": str(self.wob_max.value()),
            "Rot. Min": str(self.rpm_min.value()),
            "Rot. Max": str(self.rpm_max.value()),
            "SPP Min (psi)": str(self.spp_min.value()),
            "SPP Max (psi)": str(self.spp_max.value()),
            "FR Min": str(self.flow_min.value()),
            "FR Max": str(self.flow_max.value()),
            "TQ Min (klb.ft)": str(self.torque_min.value()),
            "TQ Max (klb.ft)": str(self.torque_max.value()),
            "MW (pcf)": str(self.mw.value()),
            "TFA (in²)": str(self.tfa.value()),
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

        self.od = QDoubleSpinBox()
        self.od.setRange(0, 50)
        self.od.setDecimals(3)
        self.od.setSuffix(" in")
        self.od.setValue(6.75)
        f1.addRow("OD:", self.od)

        self.id_ = QDoubleSpinBox()
        self.id_.setRange(0, 50)
        self.id_.setDecimals(3)
        self.id_.setSuffix(" in")
        self.id_.setValue(2.813)
        f1.addRow("ID:", self.id_)

        self.length = QDoubleSpinBox()
        self.length.setRange(0, 100)
        self.length.setDecimals(2)
        self.length.setSuffix(" m")
        f1.addRow("Length:", self.length)

        self.serial = QLineEdit()
        self.serial.setPlaceholderText("Serial number")
        f1.addRow("Serial No:", self.serial)

        self.weight = QDoubleSpinBox()
        self.weight.setRange(0, 10000)
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

        self.torque = QDoubleSpinBox()
        self.torque.setRange(0, 200000)
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
            self.od.setValue(float(data.get('OD (in)', 0) or 0))
            self.id_.setValue(float(data.get('ID (in)', 0) or 0))
            self.length.setValue(float(data.get('Length (m)', 0) or 0))
            self.serial.setText(str(data.get('Serial No', '')))
            self.weight.setValue(float(data.get('Weight (kg)', 0) or 0))
            self.remarks.setText(str(data.get('Remarks', '')))

    def _save(self):
        self.result = {
            "Tool Type": self.tool_type.currentText(),
            "Description": self.description.text(),
            "OD (in)": str(self.od.value()),
            "ID (in)": str(self.id_.value()),
            "Length (m)": str(self.length.value()),
            "Serial No": self.serial.text(),
            "Weight (kg)": str(self.weight.value()),
            "Connection Type": f"{self.connection_top.currentText()} / {self.connection_bot.currentText()}",
            "Make-up Torque (ft-lb)": str(self.torque.value()),
            "Remarks": self.remarks.text(),
        }
        self.accept()

    def get_result(self):
        return self.result