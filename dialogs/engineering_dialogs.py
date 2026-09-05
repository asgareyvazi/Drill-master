# dialogs/engineering_dialogs.py
"""
Engineering Dialogs - دیالوگ‌های حرفه‌ای برای Engineering Calculator
شامل:
- AddPipeDialog (لوله)
- AddCasingDialog (کیسینگ)
- AddNozzleDialog (نازل)
- AddPumpDialog (پمپ)
- AddSurveyDialog (سروی)
- AddFormationDialog (سازند)
"""
import math
import logging
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

logger = logging.getLogger(__name__)


# ==================== Base Dialog ====================
class EngineeringBaseDialog(QDialog):
    """کلاس پایه برای دیالوگ‌های مهندسی"""

    def __init__(self, title, parent=None, edit_data=None):
        super().__init__(parent)
        self.result = None
        self.edit_data = edit_data
        self.setWindowTitle(title)
        self.setMinimumWidth(500)

    def _dspin(self, val, min_v=0, max_v=99999, dec=2, suffix=""):
        sp = QDoubleSpinBox()
        sp.setRange(min_v, max_v)
        sp.setDecimals(dec)
        sp.setValue(val)
        if suffix:
            sp.setSuffix(suffix)
        return sp

    def _ispin(self, val, min_v=0, max_v=9999):
        sp = QSpinBox()
        sp.setRange(min_v, max_v)
        sp.setValue(val)
        return sp

    def _header(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #2c3e50; "
            "padding: 8px; background: #ecf0f1; border-radius: 4px;"
        )
        lbl.setAlignment(Qt.AlignCenter)
        return lbl

    def _result_label(self, color="#2c3e50"):
        lbl = QLabel("--")
        lbl.setStyleSheet(
            f"font-weight: bold; color: {color}; padding: 5px; "
            f"border: 1px solid {color}; border-radius: 3px; font-size: 11px;"
        )
        lbl.setWordWrap(True)
        return lbl

    def _error_label(self):
        lbl = QLabel("")
        lbl.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 3px;")
        lbl.setWordWrap(True)
        return lbl

    def _save_cancel_buttons(self, save_text="✅ Add"):
        layout = QHBoxLayout()
        save = QPushButton(save_text if not self.edit_data else "✅ Update")
        save.setStyleSheet(
            "QPushButton { background: #27ae60; color: white; font-weight: bold; "
            "padding: 10px 20px; border-radius: 5px; border: none; font-size: 12px; }"
            "QPushButton:hover { background: #229954; }"
        )
        cancel = QPushButton("Cancel")
        cancel.setStyleSheet("padding: 10px 20px;")
        cancel.clicked.connect(self.reject)
        layout.addStretch()
        layout.addWidget(save)
        layout.addWidget(cancel)
        return layout, save

    def get_result(self):
        return self.result


# ==================== 1. Add Pipe Dialog ====================
class AddPipeDialog(EngineeringBaseDialog):
    """دیالوگ اضافه کردن لوله"""

    PIPE_DB = {
        "Drill Pipe": {
            '2-3/8" 6.65# E-75': {"od": 2.375, "id": 1.815, "wt": 6.65, "grade": "E-75", "conn": "NC26"},
            '2-7/8" 10.4# E-75': {"od": 2.875, "id": 2.151, "wt": 10.4, "grade": "E-75", "conn": "NC31"},
            '3-1/2" 13.3# S-135': {"od": 3.500, "id": 2.764, "wt": 13.3, "grade": "S-135", "conn": "NC38"},
            '4" 14# E-75': {"od": 4.000, "id": 3.340, "wt": 14.0, "grade": "E-75", "conn": "NC40"},
            '4-1/2" 16.6# S-135': {"od": 4.500, "id": 3.826, "wt": 16.6, "grade": "S-135", "conn": "NC46"},
            '5" 19.5# S-135': {"od": 5.000, "id": 4.276, "wt": 19.5, "grade": "S-135", "conn": "NC50"},
            '5" 25.6# S-135': {"od": 5.000, "id": 4.000, "wt": 25.6, "grade": "S-135", "conn": "NC50"},
            '5-1/2" 21.9# S-135': {"od": 5.500, "id": 4.778, "wt": 21.9, "grade": "S-135", "conn": "5-1/2 FH"},
            '5-1/2" 24.7# S-135': {"od": 5.500, "id": 4.670, "wt": 24.7, "grade": "S-135", "conn": "5-1/2 FH"},
            '5-7/8" 23.4# S-135': {"od": 5.875, "id": 5.153, "wt": 23.4, "grade": "S-135", "conn": "5-1/2 FH"},
            '6-5/8" 25.2# S-135': {"od": 6.625, "id": 5.965, "wt": 25.2, "grade": "S-135", "conn": "6-5/8 FH"},
        },
        "HWDP": {
            '3-1/2" HWDP 25.3#': {"od": 3.500, "id": 2.063, "wt": 25.3, "grade": "S-135", "conn": "NC38"},
            '4" HWDP 41#': {"od": 4.000, "id": 2.250, "wt": 41.0, "grade": "S-135", "conn": "NC40"},
            '4-1/2" HWDP 42#': {"od": 4.500, "id": 2.750, "wt": 42.0, "grade": "S-135", "conn": "NC46"},
            '5" HWDP 49.3#': {"od": 5.000, "id": 3.000, "wt": 49.3, "grade": "S-135", "conn": "NC50"},
            '5-1/2" HWDP 57#': {"od": 5.500, "id": 3.250, "wt": 57.0, "grade": "S-135", "conn": "5-1/2 FH"},
        },
        "Drill Collar": {
            '4-3/4" x 2-1/4" DC': {"od": 4.750, "id": 2.250, "wt": 46.0, "grade": "4145H", "conn": "NC38"},
            '6" x 2-1/4" DC': {"od": 6.000, "id": 2.250, "wt": 78.0, "grade": "4145H", "conn": "NC46"},
            '6-1/2" x 2-1/4" DC': {"od": 6.500, "id": 2.250, "wt": 92.0, "grade": "4145H", "conn": "NC50"},
            '6-3/4" x 2-13/16" DC': {"od": 6.750, "id": 2.813, "wt": 93.0, "grade": "4145H", "conn": "NC50"},
            '7" x 2-13/16" DC': {"od": 7.000, "id": 2.813, "wt": 101.0, "grade": "4145H", "conn": "NC50"},
            '8" x 2-13/16" DC': {"od": 8.000, "id": 2.813, "wt": 137.0, "grade": "4145H", "conn": "6-5/8 API Reg"},
            '9" x 3" DC': {"od": 9.000, "id": 3.000, "wt": 174.0, "grade": "4145H", "conn": "7-5/8 API Reg"},
            '9-1/2" x 3" DC': {"od": 9.500, "id": 3.000, "wt": 195.0, "grade": "4145H", "conn": "7-5/8 API Reg"},
            '11" x 3" DC': {"od": 11.000, "id": 3.000, "wt": 264.0, "grade": "4145H", "conn": "7-5/8 API Reg"},
        },
        "MWD/LWD": {
            '4-3/4" MWD': {"od": 4.750, "id": 1.500, "wt": 50.0, "grade": "NM", "conn": "NC38"},
            '6-3/4" MWD': {"od": 6.750, "id": 2.500, "wt": 85.0, "grade": "NM", "conn": "NC50"},
            '8" MWD': {"od": 8.000, "id": 2.500, "wt": 120.0, "grade": "NM", "conn": "6-5/8 API Reg"},
            '9-1/2" MWD': {"od": 9.500, "id": 3.000, "wt": 160.0, "grade": "NM", "conn": "7-5/8 API Reg"},
        },
        "Motor": {
            '4-3/4" Motor': {"od": 4.750, "id": 1.500, "wt": 55.0, "grade": "NM", "conn": "NC38"},
            '6-3/4" Motor': {"od": 6.750, "id": 2.000, "wt": 95.0, "grade": "NM", "conn": "NC50"},
            '8" Motor': {"od": 8.000, "id": 2.500, "wt": 130.0, "grade": "NM", "conn": "6-5/8 API Reg"},
            '9-1/2" Motor': {"od": 9.500, "id": 3.000, "wt": 180.0, "grade": "NM", "conn": "7-5/8 API Reg"},
        },
        "Stabilizer": {
            '6-1/4" Stab': {"od": 6.250, "id": 2.250, "wt": 50.0, "grade": "NM", "conn": "NC46"},
            '8-1/2" Stab': {"od": 8.500, "id": 2.813, "wt": 80.0, "grade": "NM", "conn": "NC50"},
            '12-1/4" Stab': {"od": 12.250, "id": 3.000, "wt": 120.0, "grade": "NM", "conn": "6-5/8 API Reg"},
            '17-1/2" Stab': {"od": 17.500, "id": 3.000, "wt": 180.0, "grade": "NM", "conn": "7-5/8 API Reg"},
        },
    }

    CONNECTIONS = [
        "NC26", "NC31", "NC38", "NC40", "NC46", "NC50",
        "4-1/2 IF", "4-1/2 FH", "5-1/2 FH", "6-5/8 FH",
        "4-1/2 API Reg", "6-5/8 API Reg", "7-5/8 API Reg",
        "XT-39", "XT-50", "XT-57", "HT-31", "HT-38", "HT-55", "Other"
    ]

    GRADES = ["E-75", "X-95", "G-105", "S-135", "Z-140", "V-150", "4145H", "NM"]

    def __init__(self, parent=None, edit_data=None):
        super().__init__("🔩 Drill String Component", parent, edit_data)
        self.init_ui()
        if edit_data:
            self._load_data(edit_data)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(self._header("🔩 Add Drill String Component"))

        # Type + Quick Select
        g1 = QGroupBox("Component Selection")
        f1 = QFormLayout(g1)
        self.type_combo = QComboBox()
        self.type_combo.addItems(list(self.PIPE_DB.keys()) + ["Sub", "Jar", "X-Over", "Other"])
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        f1.addRow("Type:", self.type_combo)

        self.quick_combo = QComboBox()
        self.quick_combo.addItem("-- Manual Entry --")
        self.quick_combo.currentTextChanged.connect(self._on_quick_selected)
        f1.addRow("📋 Quick Select:", self.quick_combo)
        layout.addWidget(g1)

        # Dimensions
        g2 = QGroupBox("Dimensions & Properties")
        dim = QGridLayout(g2)

        self.od = self._dspin(5.0, 0.1, 50, 3, " in")
        self.id_ = self._dspin(4.276, 0.1, 50, 3, " in")
        self.length = self._dspin(0, 0, 20000, 1, " m")
        self.weight = self._dspin(19.5, 0, 500, 1, " ppf")
        self.grade = QComboBox()
        self.grade.addItems(self.GRADES)
        self.grade.setEditable(True)
        self.conn = QComboBox()
        self.conn.addItems(self.CONNECTIONS)
        self.conn.setEditable(True)
        self.tj_od = self._dspin(0, 0, 50, 3, " in")
        self.joints = self._ispin(0, 0, 500)
        self.serial = QLineEdit()
        self.serial.setPlaceholderText("Serial No. (optional)")

        dim.addWidget(QLabel("OD:"), 0, 0)
        dim.addWidget(self.od, 0, 1)
        dim.addWidget(QLabel("ID:"), 0, 2)
        dim.addWidget(self.id_, 0, 3)
        dim.addWidget(QLabel("Length (m):"), 1, 0)
        dim.addWidget(self.length, 1, 1)
        dim.addWidget(QLabel("Weight (ppf):"), 1, 2)
        dim.addWidget(self.weight, 1, 3)
        dim.addWidget(QLabel("Grade:"), 2, 0)
        dim.addWidget(self.grade, 2, 1)
        dim.addWidget(QLabel("Connection:"), 2, 2)
        dim.addWidget(self.conn, 2, 3)
        dim.addWidget(QLabel("TJ OD:"), 3, 0)
        dim.addWidget(self.tj_od, 3, 1)
        dim.addWidget(QLabel("Joints:"), 3, 2)
        dim.addWidget(self.joints, 3, 3)
        dim.addWidget(QLabel("Serial No:"), 4, 0)
        dim.addWidget(self.serial, 4, 1, 1, 3)

        layout.addWidget(g2)

        # Calculated
        g3 = QGroupBox("📊 Calculated Properties")
        calc_layout = QGridLayout(g3)
        self.calc_cap = self._result_label("#2ecc71")
        self.calc_dis = self._result_label("#3498db")
        self.calc_wt = self._result_label("#e67e22")
        self.calc_area = self._result_label("#9b59b6")
        calc_layout.addWidget(QLabel("Capacity:"), 0, 0)
        calc_layout.addWidget(self.calc_cap, 0, 1)
        calc_layout.addWidget(QLabel("Displacement:"), 0, 2)
        calc_layout.addWidget(self.calc_dis, 0, 3)
        calc_layout.addWidget(QLabel("Total Weight:"), 1, 0)
        calc_layout.addWidget(self.calc_wt, 1, 1)
        calc_layout.addWidget(QLabel("Cross Section:"), 1, 2)
        calc_layout.addWidget(self.calc_area, 1, 3)
        layout.addWidget(g3)

        self.error = self._error_label()
        layout.addWidget(self.error)

        btns, save_btn = self._save_cancel_buttons("✅ Add to String")
        save_btn.clicked.connect(self._save)
        layout.addLayout(btns)

        # Connections
        self.od.valueChanged.connect(self._update_calc)
        self.id_.valueChanged.connect(self._update_calc)
        self.length.valueChanged.connect(self._update_calc)
        self.weight.valueChanged.connect(self._update_calc)
        self.joints.valueChanged.connect(self._joints_to_length)

        self._on_type_changed(self.type_combo.currentText())
        self._update_calc()

    def _on_type_changed(self, ptype):
        self.quick_combo.clear()
        self.quick_combo.addItem("-- Manual Entry --")
        for name in self.PIPE_DB.get(ptype, {}):
            self.quick_combo.addItem(name)

    def _on_quick_selected(self, name):
        if name == "-- Manual Entry --":
            return
        data = self.PIPE_DB.get(self.type_combo.currentText(), {}).get(name)
        if data:
            self.od.setValue(data["od"])
            self.id_.setValue(data["id"])
            self.weight.setValue(data["wt"])
            self.grade.setCurrentText(data.get("grade", ""))
            self.conn.setCurrentText(data.get("conn", ""))

    def _joints_to_length(self, n):
        if n > 0:
            avg = {"Stabilizer": 1.5, "Sub": 0.6}.get(self.type_combo.currentText(), 9.14)
            self.length.setValue(n * avg)

    def _update_calc(self):
        od = self.od.value()
        id_ = self.id_.value()
        wt = self.weight.value()
        L = self.length.value()
        L_ft = L * 3.28084
        from core.hydraulics_engine import AdvancedHydraulicsEngine as A

        if od > id_ > 0:
            cap_m = A.calc_pipe_capacity_bbl_ft(id_) * 3.28084     # bbl/m
            dis_m = A.calc_pipe_displacement_bbl_ft(od, id_) * 3.28084
            self.calc_cap.setText(f"{cap_m:.5f} bbl/m")
            self.calc_dis.setText(f"{dis_m:.5f} bbl/m")
            self.calc_area.setText(f"{math.pi/4*(od**2-id_**2):.3f} in²")
            if L > 0:
                w = wt * L_ft
                self.calc_wt.setText(f"{w:,.0f} lbs ({w/2204.6:.1f} ton)")
            else:
                self.calc_wt.setText("-- (enter length)")
            self.error.setText("")
        else:
            self.error.setText("⚠️ OD must > ID")

    def _load_data(self, d):
        idx = self.type_combo.findText(d.get('type', ''))
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.od.setValue(d.get('od', 5))
        self.id_.setValue(d.get('id', 4.276))
        self.length.setValue(d.get('length', 0))
        self.weight.setValue(d.get('weight', 19.5))
        if d.get('grade'):
            self.grade.setCurrentText(d['grade'])
        if d.get('connection'):
            self.conn.setCurrentText(d['connection'])

    def _save(self):
        errors = []
        if self.od.value() <= self.id_.value():
            errors.append("OD must > ID")
        if self.length.value() <= 0:
            errors.append("Length must > 0")
        if errors:
            self.error.setText("⚠️ " + " | ".join(errors))
            return

        self.result = {
            "type": self.type_combo.currentText(),
            "od": self.od.value(),
            "id": self.id_.value(),
            "length": self.length.value(),
            "weight": self.weight.value(),
            "grade": self.grade.currentText(),
            "connection": self.conn.currentText(),
            "tj_od": self.tj_od.value(),
            "joints": self.joints.value(),
            "serial": self.serial.text(),
        }
        self.accept()


# ==================== 2. Add Casing Dialog ====================
class AddCasingDialog(EngineeringBaseDialog):
    """دیالوگ اضافه کردن کیسینگ"""

    CASING_DB = {
        "Conductor": {
            '30" 310# X-52': {"od": 30.0, "id": 29.0, "wt": 310, "grade": "X-52", "burst": 2520, "collapse": 710},
            '26" 250# X-52': {"od": 26.0, "id": 25.0, "wt": 250, "grade": "X-52", "burst": 2000, "collapse": 600},
            '20" 133# K-55': {"od": 20.0, "id": 18.73, "wt": 133, "grade": "K-55", "burst": 3060, "collapse": 1500},
        },
        "Surface Casing": {
            '20" 94# K-55': {"od": 20.0, "id": 19.124, "wt": 94, "grade": "K-55", "burst": 2110, "collapse": 520},
            '18-5/8" 87.5# K-55': {"od": 18.625, "id": 17.755, "wt": 87.5, "grade": "K-55", "burst": 2740, "collapse": 1060},
            '16" 75# K-55': {"od": 16.0, "id": 15.124, "wt": 75, "grade": "K-55", "burst": 2630, "collapse": 1020},
            '13-3/8" 61# P-110': {"od": 13.375, "id": 12.415, "wt": 61, "grade": "P-110", "burst": 6070, "collapse": 4810},
            '13-3/8" 68# P-110': {"od": 13.375, "id": 12.275, "wt": 68, "grade": "P-110", "burst": 6820, "collapse": 5380},
        },
        "Intermediate Casing": {
            '9-5/8" 36# J-55': {"od": 9.625, "id": 8.921, "wt": 36, "grade": "J-55", "burst": 3520, "collapse": 2020},
            '9-5/8" 40# K-55': {"od": 9.625, "id": 8.835, "wt": 40, "grade": "K-55", "burst": 4230, "collapse": 2570},
            '9-5/8" 43.5# L-80': {"od": 9.625, "id": 8.755, "wt": 43.5, "grade": "L-80", "burst": 6330, "collapse": 4420},
            '9-5/8" 47# L-80': {"od": 9.625, "id": 8.681, "wt": 47, "grade": "L-80", "burst": 6870, "collapse": 5310},
            '9-5/8" 47# P-110': {"od": 9.625, "id": 8.681, "wt": 47, "grade": "P-110", "burst": 9440, "collapse": 7330},
            '9-5/8" 53.5# P-110': {"od": 9.625, "id": 8.535, "wt": 53.5, "grade": "P-110", "burst": 10900, "collapse": 8830},
        },
        "Production Casing": {
            '7" 23# L-80': {"od": 7.000, "id": 6.366, "wt": 23, "grade": "L-80", "burst": 5930, "collapse": 4060},
            '7" 26# L-80': {"od": 7.000, "id": 6.276, "wt": 26, "grade": "L-80", "burst": 6770, "collapse": 5410},
            '7" 29# L-80': {"od": 7.000, "id": 6.184, "wt": 29, "grade": "L-80", "burst": 7630, "collapse": 7030},
            '7" 29# P-110': {"od": 7.000, "id": 6.184, "wt": 29, "grade": "P-110", "burst": 10490, "collapse": 8160},
            '7" 32# P-110': {"od": 7.000, "id": 6.094, "wt": 32, "grade": "P-110", "burst": 11610, "collapse": 9380},
            '5-1/2" 17# L-80': {"od": 5.500, "id": 4.892, "wt": 17, "grade": "L-80", "burst": 6340, "collapse": 4500},
            '5-1/2" 20# L-80': {"od": 5.500, "id": 4.778, "wt": 20, "grade": "L-80", "burst": 7580, "collapse": 6200},
            '5-1/2" 23# P-110': {"od": 5.500, "id": 4.670, "wt": 23, "grade": "P-110", "burst": 11440, "collapse": 10000},
        },
        "Liner": {
            '7" 29# L-80 Liner': {"od": 7.000, "id": 6.184, "wt": 29, "grade": "L-80", "burst": 7630, "collapse": 7030},
            '5" 18# L-80 Liner': {"od": 5.000, "id": 4.276, "wt": 18, "grade": "L-80", "burst": 7410, "collapse": 6100},
            '4-1/2" 12.6# L-80': {"od": 4.500, "id": 3.958, "wt": 12.6, "grade": "L-80", "burst": 6720, "collapse": 5320},
        },
        "Open Hole": {},
    }

    THREAD_TYPES = [
        "BTC (Buttress)", "LTC (Long Thread)", "STC (Short Thread)",
        "Premium (VAM)", "VAM TOP", "VAM SLIJ-II",
        "Hunting SEAL-LOCK", "Tenaris Blue", "Tenaris Dopeless",
        "Hydril 563", "Grant Prideco XT", "Other"
    ]

    def __init__(self, parent=None, edit_data=None):
        super().__init__("🛢️ Casing / Wellbore Section", parent, edit_data)
        self.init_ui()
        if edit_data:
            self._load_data(edit_data)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(self._header("🛢️ Add Casing / Wellbore Section"))

        # Type + Quick Select
        g1 = QGroupBox("Section Type")
        f1 = QFormLayout(g1)
        self.type_combo = QComboBox()
        self.type_combo.addItems(list(self.CASING_DB.keys()))
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        f1.addRow("Type:", self.type_combo)

        self.quick_combo = QComboBox()
        self.quick_combo.addItem("-- Manual Entry --")
        self.quick_combo.currentTextChanged.connect(self._on_quick_selected)
        f1.addRow("📋 Quick Select:", self.quick_combo)
        layout.addWidget(g1)

        # Dimensions
        g2 = QGroupBox("Dimensions & Depth")
        dim = QGridLayout(g2)

        self.od = self._dspin(9.625, 0.1, 50, 3, " in")
        self.id_ = self._dspin(8.835, 0.1, 50, 3, " in")
        self.wt = self._dspin(47, 0, 500, 1, " ppf")
        self.from_md = self._dspin(0, 0, 20000, 1, " m")
        self.to_md = self._dspin(0, 0, 20000, 1, " m")
        self.grade = QComboBox()
        self.grade.addItems(["H-40", "J-55", "K-55", "N-80", "L-80", "C-90", "C-95", "P-110", "Q-125", "V-150"])
        self.grade.setEditable(True)
        self.thread = QComboBox()
        self.thread.addItems(self.THREAD_TYPES)
        self.thread.setEditable(True)

        dim.addWidget(QLabel("OD / Hole Size:"), 0, 0)
        dim.addWidget(self.od, 0, 1)
        dim.addWidget(QLabel("ID:"), 0, 2)
        dim.addWidget(self.id_, 0, 3)
        dim.addWidget(QLabel("Weight (ppf):"), 1, 0)
        dim.addWidget(self.wt, 1, 1)
        dim.addWidget(QLabel("Grade:"), 1, 2)
        dim.addWidget(self.grade, 1, 3)
        dim.addWidget(QLabel("From MD (m):"), 2, 0)
        dim.addWidget(self.from_md, 2, 1)
        dim.addWidget(QLabel("To MD (m):"), 2, 2)
        dim.addWidget(self.to_md, 2, 3)
        dim.addWidget(QLabel("Thread:"), 3, 0)
        dim.addWidget(self.thread, 3, 1, 1, 3)
        layout.addWidget(g2)

        # Performance
        g3 = QGroupBox("📊 Casing Performance (API)")
        perf = QGridLayout(g3)
        self.burst = self._dspin(0, 0, 30000, 0, " psi")
        self.collapse = self._dspin(0, 0, 30000, 0, " psi")
        self.tensile = self._dspin(0, 0, 5000000, 0, " lbs")
        self.drift = self._dspin(0, 0, 50, 3, " in")

        perf.addWidget(QLabel("Burst (psi):"), 0, 0)
        perf.addWidget(self.burst, 0, 1)
        perf.addWidget(QLabel("Collapse (psi):"), 0, 2)
        perf.addWidget(self.collapse, 0, 3)
        perf.addWidget(QLabel("Tensile (lbs):"), 1, 0)
        perf.addWidget(self.tensile, 1, 1)
        perf.addWidget(QLabel("Drift ID (in):"), 1, 2)
        perf.addWidget(self.drift, 1, 3)
        layout.addWidget(g3)

        # Calculated
        g4 = QGroupBox("📊 Calculated")
        cl = QGridLayout(g4)
        self.calc_cap = self._result_label("#2ecc71")
        self.calc_len = self._result_label("#3498db")
        cl.addWidget(QLabel("Capacity:"), 0, 0)
        cl.addWidget(self.calc_cap, 0, 1)
        cl.addWidget(QLabel("Length:"), 0, 2)
        cl.addWidget(self.calc_len, 0, 3)
        layout.addWidget(g4)

        self.error = self._error_label()
        layout.addWidget(self.error)

        btns, save_btn = self._save_cancel_buttons("✅ Add Section")
        save_btn.clicked.connect(self._save)
        layout.addLayout(btns)

        self.od.valueChanged.connect(self._update_calc)
        self.id_.valueChanged.connect(self._update_calc)
        self.from_md.valueChanged.connect(self._update_calc)
        self.to_md.valueChanged.connect(self._update_calc)
        self._on_type_changed(self.type_combo.currentText())
        self._update_calc()

    def _on_type_changed(self, ctype):
        self.quick_combo.clear()
        self.quick_combo.addItem("-- Manual Entry --")
        for name in self.CASING_DB.get(ctype, {}):
            self.quick_combo.addItem(name)
        is_oh = "Open" in ctype
        self.wt.setEnabled(not is_oh)
        self.grade.setEnabled(not is_oh)
        self.burst.setEnabled(not is_oh)
        self.collapse.setEnabled(not is_oh)
        if is_oh:
            self.id_.setValue(self.od.value())

    def _on_quick_selected(self, name):
        if name == "-- Manual Entry --":
            return
        data = self.CASING_DB.get(self.type_combo.currentText(), {}).get(name)
        if data:
            self.od.setValue(data["od"])
            self.id_.setValue(data["id"])
            self.wt.setValue(data["wt"])
            self.grade.setCurrentText(data.get("grade", ""))
            self.burst.setValue(data.get("burst", 0))
            self.collapse.setValue(data.get("collapse", 0))

    def _update_calc(self):
        id_ = self.id_.value()
        L = self.to_md.value() - self.from_md.value()
        if id_ > 0:
            from core.hydraulics_engine import AdvancedHydraulicsEngine as A
            cap_m = A.calc_pipe_capacity_bbl_ft(id_) * 3.28084      # bbl/m
            self.calc_cap.setText(f"{cap_m:.5f} bbl/m")
        if L > 0:
            self.calc_len.setText(f"{L:.1f} m ({L * 3.281:.0f} ft)")
        else:
            self.calc_len.setText("--")

    def _load_data(self, d):
        idx = self.type_combo.findText(d.get('type', ''))
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.od.setValue(d.get('od', 9.625))
        self.id_.setValue(d.get('id', 8.835))
        self.from_md.setValue(d.get('from', 0))
        self.to_md.setValue(d.get('to', 0))

    def _save(self):
        errors = []
        if self.to_md.value() <= self.from_md.value():
            errors.append("To MD must > From MD")
        if self.od.value() <= 0:
            errors.append("OD must > 0")
        if errors:
            self.error.setText("⚠️ " + " | ".join(errors))
            return

        self.result = {
            "type": self.type_combo.currentText(),
            "od": self.od.value(),
            "id": self.id_.value(),
            "weight": self.wt.value(),
            "from": self.from_md.value(),
            "to": self.to_md.value(),
            "grade": self.grade.currentText(),
            "thread": self.thread.currentText(),
            "burst": self.burst.value(),
            "collapse": self.collapse.value(),
            "tensile": self.tensile.value(),
            "drift": self.drift.value(),
        }
        self.accept()


# ==================== 3. Add Nozzle Dialog ====================
class AddNozzleDialog(EngineeringBaseDialog):
    """دیالوگ اضافه کردن نازل"""

    STANDARD_SIZES = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 24, 26, 28, 30, 32]

    def __init__(self, parent=None, edit_data=None):
        super().__init__("🔵 Bit Nozzle", parent, edit_data)
        self.init_ui()
        if edit_data:
            self._load_data(edit_data)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(self._header("🔵 Add Bit Nozzle"))

        g1 = QGroupBox("Nozzle Configuration")
        f1 = QFormLayout(g1)

        self.size = QComboBox()
        for s in self.STANDARD_SIZES:
            self.size.addItem(f"{s}/32\" ({s/32:.3f}\")", s)
        self.size.setCurrentIndex(10)  # 16/32
        self.size.currentIndexChanged.connect(self._update_calc)
        f1.addRow("Nozzle Size:", self.size)

        self.qty = self._ispin(1, 1, 10)
        self.qty.valueChanged.connect(self._update_calc)
        f1.addRow("Quantity:", self.qty)

        layout.addWidget(g1)

        # Calculated
        g2 = QGroupBox("📊 Calculated")
        cl = QFormLayout(g2)
        self.calc_area_single = self._result_label("#3498db")
        self.calc_area_total = self._result_label("#27ae60")
        self.calc_diameter = self._result_label("#9b59b6")
        cl.addRow("Single Nozzle Area:", self.calc_area_single)
        cl.addRow("Total Area (this row):", self.calc_area_total)
        cl.addRow("Diameter:", self.calc_diameter)
        layout.addWidget(g2)

        self.error = self._error_label()
        layout.addWidget(self.error)

        btns, save_btn = self._save_cancel_buttons("✅ Add Nozzle")
        save_btn.clicked.connect(self._save)
        layout.addLayout(btns)

        self._update_calc()

    def _update_calc(self):
        size_32 = self.size.currentData() or 16
        qty = self.qty.value()
        d = size_32 / 32.0
        area_single = math.pi / 4 * d**2
        area_total = area_single * qty
        self.calc_diameter.setText(f"{d:.4f} in")
        self.calc_area_single.setText(f"{area_single:.4f} in²")
        self.calc_area_total.setText(f"{area_total:.4f} in² ({qty} nozzles)")

    def _load_data(self, d):
        s = d.get('size', 16)
        idx = self.size.findData(s)
        if idx >= 0:
            self.size.setCurrentIndex(idx)
        self.qty.setValue(d.get('qty', 1))

    def _save(self):
        self.result = {
            "size": self.size.currentData() or 16,
            "qty": self.qty.value(),
        }
        self.accept()


# ==================== 4. Add Pump Dialog ====================
class AddPumpDialog(EngineeringBaseDialog):
    """دیالوگ اضافه کردن پمپ"""

    PUMP_DB = {
        "National 12-P-160": {"type": "Triplex", "hp": 1600, "max_spm": 120, "max_press": 5000, "liner_range": "5.5-7.5"},
        "NOV 14-P-220": {"type": "Triplex", "hp": 2200, "max_spm": 120, "max_press": 7500, "liner_range": "5.0-7.5"},
        "Gardner Denver PZ-11": {"type": "Triplex", "hp": 1600, "max_spm": 140, "max_press": 5000, "liner_range": "5.5-7.0"},
        "Gardner Denver PZ-9": {"type": "Triplex", "hp": 1300, "max_spm": 140, "max_press": 5000, "liner_range": "5.0-6.5"},
        "Ideco T-1600": {"type": "Triplex", "hp": 1600, "max_spm": 120, "max_press": 5000, "liner_range": "5.5-7.0"},
        "Continental Emsco FB-1600": {"type": "Triplex", "hp": 1600, "max_spm": 130, "max_press": 5000, "liner_range": "5.0-7.5"},
        "Custom Pump": {"type": "Triplex", "hp": 0, "max_spm": 0, "max_press": 0, "liner_range": ""},
    }

    def __init__(self, parent=None, edit_data=None):
        super().__init__("💧 Mud Pump", parent, edit_data)
        self.init_ui()
        if edit_data:
            self._load_data(edit_data)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(self._header("💧 Add Mud Pump"))

        g1 = QGroupBox("Pump Selection")
        f1 = QFormLayout(g1)
        self.pump_select = QComboBox()
        self.pump_select.addItems(list(self.PUMP_DB.keys()))
        self.pump_select.currentTextChanged.connect(self._on_pump_selected)
        f1.addRow("Pump Model:", self.pump_select)

        self.pump_name = QLineEdit()
        self.pump_name.setPlaceholderText("Pump #1, Pump #2, etc.")
        f1.addRow("Name/Label:", self.pump_name)
        layout.addWidget(g1)

        g2 = QGroupBox("Pump Parameters")
        f2 = QFormLayout(g2)
        self.pump_type = QComboBox()
        self.pump_type.addItems(["Triplex", "Duplex"])
        f2.addRow("Type:", self.pump_type)

        self.hp = self._dspin(1600, 0, 5000, 0, " HP")
        self.liner = self._dspin(7.0, 3, 15, 1, " in")
        self.rod = self._dspin(3.0, 0, 10, 1, " in")  # duplex piston-rod
        self.stroke = self._dspin(12, 6, 20, 1, " in")
        self.eff = self._dspin(0.95, 0.5, 1.0, 3)
        self.spm = self._dspin(0, 0, 200, 0, " spm")
        self.max_press = self._dspin(5000, 0, 15000, 0, " psi")

        f2.addRow("Horsepower:", self.hp)
        f2.addRow("Liner Size:", self.liner)
        f2.addRow("Rod Size (duplex):", self.rod)
        f2.addRow("Stroke Length:", self.stroke)
        f2.addRow("Efficiency:", self.eff)
        f2.addRow("Operating SPM:", self.spm)
        f2.addRow("Max Pressure:", self.max_press)
        layout.addWidget(g2)

        def _toggle_rod(typ):
            self.rod.setEnabled(typ == "Duplex")
        self.pump_type.currentTextChanged.connect(_toggle_rod)
        _toggle_rod(self.pump_type.currentText())

        g3 = QGroupBox("📊 Calculated Output")
        cl = QFormLayout(g3)
        self.calc_output = self._result_label("#27ae60")
        self.calc_gpm = self._result_label("#3498db")
        cl.addRow("Output (bbl/stk):", self.calc_output)
        cl.addRow("Flow Rate (gpm):", self.calc_gpm)
        layout.addWidget(g3)

        self.error = self._error_label()
        layout.addWidget(self.error)

        btns, save_btn = self._save_cancel_buttons("✅ Add Pump")
        save_btn.clicked.connect(self._save)
        layout.addLayout(btns)

        self.liner.valueChanged.connect(self._update_calc)
        self.stroke.valueChanged.connect(self._update_calc)
        self.eff.valueChanged.connect(self._update_calc)
        self.spm.valueChanged.connect(self._update_calc)

        self._on_pump_selected(self.pump_select.currentText())
        self._update_calc()

    def _on_pump_selected(self, name):
        d = self.PUMP_DB.get(name, {})
        if d.get('hp'):
            self.hp.setValue(d['hp'])
        if d.get('max_press'):
            self.max_press.setValue(d['max_press'])
        if d.get('max_spm'):
            self.spm.setMaximum(d['max_spm'])
        self.pump_type.setCurrentText(d.get('type', 'Triplex'))

    def _pump_output_bbl_stk(self):
        """Canonical pump output — triplex or duplex (single formula source)."""
        from core.hydraulics_engine import AdvancedHydraulicsEngine
        liner = self.liner.value()
        stroke = self.stroke.value()
        eff = self.eff.value()
        if self.pump_type.currentText() == "Duplex":
            return AdvancedHydraulicsEngine.calc_pump_output_duplex(
                liner, self.rod.value(), stroke, eff
            )
        return AdvancedHydraulicsEngine.calc_pump_output(liner, stroke, eff)

    def _update_calc(self):
        spm = self.spm.value()
        output = self._pump_output_bbl_stk()
        self.calc_output.setText(f"{output:.5f} bbl/stk")
        if spm > 0:
            gpm = output * spm * 42
            self.calc_gpm.setText(f"{gpm:.1f} gpm")
        else:
            self.calc_gpm.setText("-- (enter SPM)")

    def _load_data(self, d):
        self.pump_name.setText(d.get('name', ''))
        self.pump_type.setCurrentText(d.get('type', 'Triplex'))
        self.liner.setValue(d.get('liner', 7))
        self.rod.setValue(d.get('rod', 3))
        self.stroke.setValue(d.get('stroke', 12))
        self.eff.setValue(d.get('efficiency', 0.95))
        self.spm.setValue(d.get('spm', 0))

    def _save(self):
        if self.liner.value() <= 0:
            self.error.setText("⚠️ Liner size must > 0")
            return
        output = self._pump_output_bbl_stk()
        self.result = {
            "name": self.pump_name.text() or f"Pump {self.liner.value()}\"",
            "model": self.pump_select.currentText(),
            "type": self.pump_type.currentText(),
            "hp": self.hp.value(),
            "liner": self.liner.value(),
            "rod": self.rod.value(),
            "stroke": self.stroke.value(),
            "efficiency": self.eff.value(),
            "spm": self.spm.value(),
            "max_pressure": self.max_press.value(),
            "output_bbl_stk": round(output, 5),
        }
        self.accept()


# ==================== 5. Add Survey Dialog ====================
class AddSurveyDialog(EngineeringBaseDialog):
    """دیالوگ اضافه کردن نقطه سروی"""

    TOOLS = ["MWD", "Gyro", "Multi-Shot", "Single-Shot", "Calculated", "Other"]

    def __init__(self, parent=None, edit_data=None, prev_survey=None):
        super().__init__("📐 Survey Point", parent, edit_data)
        self.prev_survey = prev_survey  # نقطه قبلی برای محاسبه خودکار
        self.init_ui()
        if edit_data:
            self._load_data(edit_data)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(self._header("📐 Add Survey Point"))

        g1 = QGroupBox("Survey Input")
        f1 = QFormLayout(g1)

        self.md = self._dspin(0, 0, 20000, 2, " m")
        self.inc = self._dspin(0, 0, 180, 2, " °")
        self.azi = self._dspin(0, 0, 360, 2, " °")
        self.tool = QComboBox()
        self.tool.addItems(self.TOOLS)
        self.remarks = QLineEdit()
        self.remarks.setPlaceholderText("Remarks (optional)")

        f1.addRow("MD (m):", self.md)
        f1.addRow("Inclination (°):", self.inc)
        f1.addRow("Azimuth (°):", self.azi)
        f1.addRow("Survey Tool:", self.tool)
        f1.addRow("Remarks:", self.remarks)
        layout.addWidget(g1)

        # Calculated (if previous survey exists)
        g2 = QGroupBox("📊 Calculated (Min Curvature)")
        cl = QFormLayout(g2)
        self.calc_tvd = self._result_label("#3498db")
        self.calc_north = self._result_label("#27ae60")
        self.calc_east = self._result_label("#e67e22")
        self.calc_dls = self._result_label("#e74c3c")
        self.calc_hd = self._result_label("#9b59b6")

        cl.addRow("TVD:", self.calc_tvd)
        cl.addRow("North:", self.calc_north)
        cl.addRow("East:", self.calc_east)
        cl.addRow("DLS:", self.calc_dls)
        cl.addRow("HD:", self.calc_hd)
        layout.addWidget(g2)

        if self.prev_survey:
            prev_info = QLabel(
                f"📌 Previous: MD={self.prev_survey.get('md', 0):.1f}m, "
                f"Inc={self.prev_survey.get('inc', 0):.1f}°, "
                f"Azi={self.prev_survey.get('azi', 0):.1f}°"
            )
            prev_info.setStyleSheet("color: #666; font-size: 10px; padding: 3px;")
            layout.addWidget(prev_info)

        self.error = self._error_label()
        layout.addWidget(self.error)

        btns, save_btn = self._save_cancel_buttons("✅ Add Survey Point")
        save_btn.clicked.connect(self._save)
        layout.addLayout(btns)

        self.md.valueChanged.connect(self._update_calc)
        self.inc.valueChanged.connect(self._update_calc)
        self.azi.valueChanged.connect(self._update_calc)

    def _update_calc(self):
        if not self.prev_survey:
            self.calc_tvd.setText(f"{self.md.value():.2f} m (surface)")
            self.calc_north.setText("0.00 m")
            self.calc_east.setText("0.00 m")
            self.calc_dls.setText("0.00 °/30m")
            self.calc_hd.setText("0.00 m")
            return

        prev = self.prev_survey
        md1 = prev.get('md', 0)
        inc1 = prev.get('inc', 0)
        azi1 = prev.get('azi', 0)
        md2 = self.md.value()
        inc2 = self.inc.value()
        azi2 = self.azi.value()

        if md2 <= md1:
            self.error.setText("⚠️ MD must > previous MD")
            return
        self.error.setText("")

        # Min Curvature
        delta_md = md2 - md1
        inc1_r = math.radians(inc1)
        inc2_r = math.radians(inc2)
        azi1_r = math.radians(azi1)
        azi2_r = math.radians(azi2)

        cos_beta = (math.sin(inc1_r) * math.sin(inc2_r) * math.cos(azi2_r - azi1_r) +
                    math.cos(inc1_r) * math.cos(inc2_r))
        cos_beta = max(-1.0, min(1.0, cos_beta))
        beta = math.acos(cos_beta)
        rf = 1.0 if abs(beta) < 1e-10 else 2.0 / beta * math.tan(beta / 2.0)

        d_tvd = 0.5 * delta_md * (math.cos(inc1_r) + math.cos(inc2_r)) * rf
        d_n = 0.5 * delta_md * (math.sin(inc1_r) * math.cos(azi1_r) + math.sin(inc2_r) * math.cos(azi2_r)) * rf
        d_e = 0.5 * delta_md * (math.sin(inc1_r) * math.sin(azi1_r) + math.sin(inc2_r) * math.sin(azi2_r)) * rf
        dls = (beta * 180 / math.pi) / delta_md * 30 if delta_md > 0 else 0

        tvd = prev.get('tvd', 0) + d_tvd
        north = prev.get('north', 0) + d_n
        east = prev.get('east', 0) + d_e
        hd = math.sqrt(north**2 + east**2)

        self.calc_tvd.setText(f"{tvd:.2f} m (ΔTVD={d_tvd:.2f})")
        self.calc_north.setText(f"{north:.2f} m (ΔN={d_n:.2f})")
        self.calc_east.setText(f"{east:.2f} m (ΔE={d_e:.2f})")
        self.calc_dls.setText(f"{dls:.2f} °/30m")
        self.calc_hd.setText(f"{hd:.2f} m")

    def _load_data(self, d):
        self.md.setValue(d.get('md', 0))
        self.inc.setValue(d.get('inc', 0))
        self.azi.setValue(d.get('azi', 0))
        idx = self.tool.findText(d.get('tool', 'MWD'))
        if idx >= 0:
            self.tool.setCurrentIndex(idx)

    def _save(self):
        if self.prev_survey and self.md.value() <= self.prev_survey.get('md', 0):
            self.error.setText("⚠️ MD must > previous survey MD")
            return

        # Collect calculated values
        tvd = north = east = dls = hd = 0
        lbl = self.calc_tvd.text()
        try:
            tvd = float(lbl.split(' ')[0])
        except:
            tvd = self.md.value()

        try:
            north = float(self.calc_north.text().split(' ')[0])
            east = float(self.calc_east.text().split(' ')[0])
            dls = float(self.calc_dls.text().split(' ')[0])
            hd = float(self.calc_hd.text().split(' ')[0])
        except:
            pass

        self.result = {
            "md": self.md.value(),
            "inc": self.inc.value(),
            "azi": self.azi.value(),
            "tvd": tvd,
            "north": north,
            "east": east,
            "dls": dls,
            "hd": hd,
            "tool": self.tool.currentText(),
            "remarks": self.remarks.text(),
        }
        self.accept()


# ==================== 6. Add Formation Dialog ====================
class AddFormationDialog(EngineeringBaseDialog):
    """دیالوگ اضافه کردن سازند"""

    LITHOLOGIES = [
        "Shale", "Sandstone", "Limestone", "Dolomite",
        "Siltstone", "Marl", "Anhydrite", "Gypsum",
        "Salt", "Coal", "Conglomerate", "Claystone",
        "Chalk", "Granite", "Basalt", "Chert", "Other"
    ]

    AGES = [
        "Quaternary", "Neogene", "Paleogene",
        "Cretaceous", "Jurassic", "Triassic",
        "Permian", "Carboniferous", "Devonian",
        "Silurian", "Ordovician", "Cambrian",
        "Precambrian", "Unknown"
    ]

    COLORS_MAP = {
        "Shale": "#808080", "Sandstone": "#FFD700",
        "Limestone": "#87CEEB", "Dolomite": "#DEB887",
        "Siltstone": "#A0522D", "Marl": "#BDB76B",
        "Anhydrite": "#E0E0E0", "Gypsum": "#F5F5DC",
        "Salt": "#FFFFFF", "Coal": "#2F4F4F",
        "Conglomerate": "#CD853F", "Claystone": "#696969",
    }

    def __init__(self, parent=None, edit_data=None):
        super().__init__("🏔️ Formation Layer", parent, edit_data)
        self.selected_color = "#8B4513"
        self.init_ui()
        if edit_data:
            self._load_data(edit_data)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(self._header("🏔️ Add Formation Layer"))

        g1 = QGroupBox("Formation Information")
        f1 = QFormLayout(g1)

        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g., Gachsaran, Asmari, Pabdeh")
        f1.addRow("Formation Name:", self.name)

        self.lithology = QComboBox()
        self.lithology.addItems(self.LITHOLOGIES)
        self.lithology.setEditable(True)
        self.lithology.currentTextChanged.connect(self._on_lithology_changed)
        f1.addRow("Lithology:", self.lithology)

        self.age = QComboBox()
        self.age.addItems(self.AGES)
        self.age.setEditable(True)
        f1.addRow("Geological Age:", self.age)

        layout.addWidget(g1)

        g2 = QGroupBox("Depth Range")
        f2 = QFormLayout(g2)
        self.top_md = self._dspin(0, 0, 20000, 1, " m MD")
        self.base_md = self._dspin(100, 0, 20000, 1, " m MD")
        self.top_tvd = self._dspin(0, 0, 20000, 1, " m TVD")
        f2.addRow("Top MD:", self.top_md)
        f2.addRow("Base MD:", self.base_md)
        f2.addRow("Top TVD:", self.top_tvd)
        layout.addWidget(g2)

        g3 = QGroupBox("Properties")
        f3 = QFormLayout(g3)

        # Color
        color_layout = QHBoxLayout()
        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(40, 25)
        self.color_btn.setStyleSheet(f"background-color: {self.selected_color}; border: 1px solid #999; border-radius: 3px;")
        self.color_btn.clicked.connect(self._choose_color)
        self.color_label = QLabel(self.selected_color)
        color_layout.addWidget(self.color_btn)
        color_layout.addWidget(self.color_label)
        color_layout.addStretch()
        f3.addRow("Color:", color_layout)

        self.pore_pressure = self._dspin(0, 0, 30, 2, " ppg")
        self.frac_gradient = self._dspin(0, 0, 30, 2, " ppg")
        f3.addRow("Pore Pressure:", self.pore_pressure)
        f3.addRow("Frac Gradient:", self.frac_gradient)

        self.description = QTextEdit()
        self.description.setMaximumHeight(60)
        self.description.setPlaceholderText("Description, observations, shows...")
        f3.addRow("Description:", self.description)
        layout.addWidget(g3)

        # Calculated
        g4 = QGroupBox("📊 Calculated")
        cl = QFormLayout(g4)
        self.calc_thickness = self._result_label("#e67e22")
        cl.addRow("Thickness:", self.calc_thickness)
        layout.addWidget(g4)

        self.top_md.valueChanged.connect(self._update_calc)
        self.base_md.valueChanged.connect(self._update_calc)

        self.error = self._error_label()
        layout.addWidget(self.error)

        btns, save_btn = self._save_cancel_buttons("✅ Add Formation")
        save_btn.clicked.connect(self._save)
        layout.addLayout(btns)

        self._update_calc()

    def _on_lithology_changed(self, lith):
        color = self.COLORS_MAP.get(lith)
        if color:
            self.selected_color = color
            self.color_btn.setStyleSheet(f"background-color: {color}; border: 1px solid #999; border-radius: 3px;")
            self.color_label.setText(color)

    def _choose_color(self):
        color = QColorDialog.getColor(QColor(self.selected_color), self)
        if color.isValid():
            self.selected_color = color.name()
            self.color_btn.setStyleSheet(f"background-color: {self.selected_color}; border: 1px solid #999; border-radius: 3px;")
            self.color_label.setText(self.selected_color)

    def _update_calc(self):
        thickness = self.base_md.value() - self.top_md.value()
        if thickness > 0:
            self.calc_thickness.setText(f"{thickness:.1f} m ({thickness * 3.281:.0f} ft)")
        else:
            self.calc_thickness.setText("❌ Base must > Top")

    def _load_data(self, d):
        self.name.setText(d.get('name', ''))
        idx = self.lithology.findText(d.get('lithology', ''))
        if idx >= 0:
            self.lithology.setCurrentIndex(idx)
        self.top_md.setValue(d.get('top', 0))
        self.base_md.setValue(d.get('base', 100))
        if d.get('color'):
            self.selected_color = d['color']
            self.color_btn.setStyleSheet(f"background-color: {d['color']}; border: 1px solid #999; border-radius: 3px;")

    def _save(self):
        errors = []
        if not self.name.text().strip():
            errors.append("Formation name required")
        if self.base_md.value() <= self.top_md.value():
            errors.append("Base MD must > Top MD")
        if errors:
            self.error.setText("⚠️ " + " | ".join(errors))
            return

        self.result = {
            "name": self.name.text().strip(),
            "lithology": self.lithology.currentText(),
            "age": self.age.currentText(),
            "top": self.top_md.value(),
            "base": self.base_md.value(),
            "top_tvd": self.top_tvd.value(),
            "thickness": self.base_md.value() - self.top_md.value(),
            "color": self.selected_color,
            "pore_pressure": self.pore_pressure.value(),
            "frac_gradient": self.frac_gradient.value(),
            "description": self.description.toPlainText(),
        }
        self.accept()