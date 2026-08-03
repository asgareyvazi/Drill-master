# dial  ogs/daily_report_dialogs.py
"""
Daily Report Dialogs - دیالوگ‌های حرفه‌ای گزارش روزانه
"""
import math
from datetime import time
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *


class AddActivityDialog(QDialog):
    """دیالوگ اضافه کردن فعالیت به Time Log"""

    MAIN_PHASES = [
        "MOV - Moving/Positioning",
        "DRL - Drilling",
        "LOG - Logging",
        "CSG - Casing/Liner",
        "COM - Completion",
        "FTS - Formation Testing",
        "COR - Coring",
        "ABD - Abandonment",
        "WOC - Wait on Cement",
        "OTH - Other",
    ]

    ACTIVITY_CODES = {
        "Rig Up/ Tear Down / Move": [
            "Rig Moving/Positioning", "Rig Up", "Rig Down", "Tear Out", "Rig Skid",
        ],
        "Drilling": [
            "Vertical Drilling", "Directional Drilling (Rotating)",
            "Directional Drilling (Sliding)",
        ],
        "Reaming": [
            "Reaming / Back Reaming", "Wash Down",
            "Under reaming/ Hole Opening", "Drill Out Cement/ Shoe track",
        ],
        "Circulate & Condition": [
            "Hole displacement", "Circulate/ Condition Mud",
            "Loss control", "Coiled Tubing Ops.",
        ],
        "Trips": [
            "R/U & R/D Pipe Handling Equip.", "PU/LD BHA",
            "Pick up Drill Pipe", "Lay Down Drill Pipe",
            "Run in Hole", "Pull Out Of Hole",
            "POOH with Pumping", "Wiper/ Condition Trip", "Wear Bushing",
        ],
        "Run Casing/ Liner": [
            "R/U & R/D Handling Equip.", "CSG Running", "Liner Running",
            "Liner Tie back", "Nipple up/down Wellhead",
            "CSG/Liner Integrity Test",
        ],
        "Cementing": [
            "Casing/Liner Cementing", "Plug Back", "Squeeze CMT",
            "Balance Plug",
        ],
        "Wait on Cement": ["for Casing/Liner", "for Cement plug"],
        "Rig Up/Down BOP": ["Nipple up/down BOP", "Test BOP", "Pressure Test BOPs"],
        "Well Control": [
            "Kill the well", "Take S.C.R", "FIT/LOT", "Flow Check",
            "Strip In/Out",
        ],
        "Logging": [
            "R/U & R/D Logging Equip.", "Wire line logging",
            "TLC Logging", "CT Logging",
        ],
        "Fishing": ["Fishing Job", "Milling", "Work on Stuck"],
        "Safety": ["Pre Job Safety Meeting (PJSM)", "Drills"],
        "Service/ Maintain Rig": ["Rig Lubricate"],
        "Repair Rig": [
            "Circulating System", "Power System", "Hoisting System",
            "Rotating System", "Well Control System", "Other",
        ],
        "Deviation Survey": ["Performing Survey Operation"],
        "Other": ["Other"],
    }

    NPT_CODES = {
        "T-FISH": "Fishing",
        "T-STUCK PIPE": "Stuck Pipe",
        "T-WELL CONTROL": "Well Control",
        "T-HOLE CONDITION": "Hole Condition",
        "F-DRILL STRING": "Drill String Failure",
        "F-CASING": "Casing Failure",
        "W-MATERIAL": "Waiting for Material",
        "W-SERVICE EQUIPMENT": "Waiting for Service Equipment",
        "W-WEATHER": "Waiting on Weather",
        "W-STOP OPERATION": "Stop Operation",
        "RR-TDS": "TDS Repair",
        "RR-PUMP": "Pump Repair",
        "RR-SHAKER": "Shaker Repair",
    }

    CONTRACTORS = [
        "Operator", "Drilling Contractor", "Mud Company",
        "Cementing", "Wireline", "Directional",
        "MWD/LWD", "Casing Crew", "Other",
    ]

    def __init__(self, parent=None, edit_data=None, prev_time="08:00"):
        super().__init__(parent)
        self.result = None
        self.edit_data = edit_data
        self.prev_time = prev_time
        self.setWindowTitle("📝 Add Activity" if not edit_data else "📝 Edit Activity")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.init_ui()
        if edit_data:
            self._load(edit_data)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Header
        header = QLabel("📝 Daily Report Activity Entry")
        header.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #2c3e50; "
            "padding: 8px; background: #ecf0f1; border-radius: 4px;"
        )
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Time
        g_time = QGroupBox("🕐 Time")
        time_layout = QHBoxLayout(g_time)

        time_layout.addWidget(QLabel("From:"))
        self.time_from_h = QSpinBox()
        self.time_from_h.setRange(0, 24)
        self.time_from_h.setValue(8)
        self.time_from_m = QSpinBox()
        self.time_from_m.setRange(0, 59)
        self.time_from_m.setValue(0)
        time_layout.addWidget(self.time_from_h)
        time_layout.addWidget(QLabel(":"))
        time_layout.addWidget(self.time_from_m)

        time_layout.addWidget(QLabel("  To:"))
        self.time_to_h = QSpinBox()
        self.time_to_h.setRange(0, 24)
        self.time_to_h.setValue(16)
        self.time_to_m = QSpinBox()
        self.time_to_m.setRange(0, 59)
        self.time_to_m.setValue(0)
        time_layout.addWidget(self.time_to_h)
        time_layout.addWidget(QLabel(":"))
        time_layout.addWidget(self.time_to_m)

        time_layout.addWidget(QLabel("  Duration:"))
        self.duration_label = QLabel("8.00 hrs")
        self.duration_label.setStyleSheet("font-weight: bold; color: #27ae60; font-size: 13px;")
        time_layout.addWidget(self.duration_label)
        time_layout.addStretch()

        for w in [self.time_from_h, self.time_from_m, self.time_to_h, self.time_to_m]:
            w.valueChanged.connect(self._update_duration)

        # Set from prev_time
        try:
            parts = self.prev_time.split(":")
            self.time_from_h.setValue(int(parts[0]))
            self.time_from_m.setValue(int(parts[1]) if len(parts) > 1 else 0)
        except:
            pass

        layout.addWidget(g_time)

        # Activity Classification
        g_act = QGroupBox("📊 Activity Classification")
        act_layout = QFormLayout(g_act)

        self.phase_combo = QComboBox()
        self.phase_combo.addItems(self.MAIN_PHASES)
        act_layout.addRow("Main Phase:", self.phase_combo)

        self.is_npt = QCheckBox("⚠️ This is NPT (Non-Productive Time)")
        self.is_npt.setStyleSheet("font-weight: bold; color: #e74c3c;")
        self.is_npt.stateChanged.connect(self._on_npt_changed)
        act_layout.addRow(self.is_npt)

        # Normal activity codes
        self.code_combo = QComboBox()
        for category in self.ACTIVITY_CODES:
            self.code_combo.addItem(f"── {category} ──")
            for sub in self.ACTIVITY_CODES[category]:
                self.code_combo.addItem(f"    {sub}")
        self.code_combo.currentTextChanged.connect(self._on_code_changed)
        act_layout.addRow("Activity Code:", self.code_combo)

        # NPT codes (hidden by default)
        self.npt_code_combo = QComboBox()
        for code, desc in self.NPT_CODES.items():
            self.npt_code_combo.addItem(f"{code} - {desc}", code)
        self.npt_code_combo.setVisible(False)
        self.npt_label = QLabel("NPT Code:")
        self.npt_label.setVisible(False)
        act_layout.addRow(self.npt_label, self.npt_code_combo)

        # Sub code
        self.sub_code = QComboBox()
        self.sub_code.setEditable(True)
        act_layout.addRow("Sub Code:", self.sub_code)

        # Contractor (for NPT)
        self.contractor_combo = QComboBox()
        self.contractor_combo.addItems(self.CONTRACTORS)
        self.contractor_combo.setEditable(True)
        self.contractor_combo.setVisible(False)
        self.contractor_label = QLabel("Responsible:")
        self.contractor_label.setVisible(False)
        act_layout.addRow(self.contractor_label, self.contractor_combo)

        # Status
        self.status_combo = QComboBox()
        self.status_combo.addItems(["Normal", "Delayed", "Completed", "In Progress", "On Hold"])
        act_layout.addRow("Status:", self.status_combo)

        layout.addWidget(g_act)

        # Description
        g_desc = QGroupBox("📝 Activity Description")
        desc_layout = QVBoxLayout(g_desc)

        self.description = QTextEdit()
        self.description.setMaximumHeight(100)
        self.description.setPlaceholderText(
            "Describe the activity in detail...\n"
            "e.g., Drilling 8-1/2\" section from 2500m to 2530m.\n"
            "ROP: 15 m/hr, WOB: 12-15 klbs, RPM: 120-140"
        )
        desc_layout.addWidget(self.description)

        # Quick descriptions
        quick_layout = QHBoxLayout()
        for text in ["Drilling ahead", "Circulating", "POOH", "RIH", "Connection"]:
            btn = QPushButton(text)
            btn.setStyleSheet("padding: 3px 8px; font-size: 10px;")
            btn.clicked.connect(lambda checked, t=text: self.description.insertPlainText(t + ". "))
            quick_layout.addWidget(btn)
        quick_layout.addStretch()
        desc_layout.addLayout(quick_layout)

        layout.addWidget(g_desc)

        # Error
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        layout.addWidget(self.error_label)

        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("✅ Add Activity" if not self.edit_data else "✅ Update")
        save_btn.setStyleSheet(
            "QPushButton { background: #27ae60; color: white; font-weight: bold; "
            "padding: 10px 24px; border-radius: 5px; border: none; font-size: 13px; }"
            "QPushButton:hover { background: #229954; }"
        )
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self._update_duration()

    def _on_npt_changed(self, state):
        is_npt = state == Qt.Checked
        self.npt_code_combo.setVisible(is_npt)
        self.npt_label.setVisible(is_npt)
        self.contractor_combo.setVisible(is_npt)
        self.contractor_label.setVisible(is_npt)
        self.code_combo.setVisible(not is_npt)

    def _on_code_changed(self, text):
        clean = text.strip().replace("── ", "").replace(" ──", "").strip()
        if clean in self.ACTIVITY_CODES:
            self.sub_code.clear()
            self.sub_code.addItems(self.ACTIVITY_CODES[clean])

    def _update_duration(self):
        from_sec = self.time_from_h.value() * 3600 + self.time_from_m.value() * 60
        to_sec = self.time_to_h.value() * 3600 + self.time_to_m.value() * 60
        if self.time_to_h.value() == 24:
            to_sec = 24 * 3600
        diff = to_sec - from_sec
        if diff < 0:
            diff += 24 * 3600
        hours = diff / 3600
        self.duration_label.setText(f"{hours:.2f} hrs")
        if hours <= 0:
            self.duration_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        else:
            self.duration_label.setStyleSheet("font-weight: bold; color: #27ae60; font-size: 13px;")

    def _load(self, data):
        """بارگذاری داده‌ها در دیالوگ Edit."""
        # Time From
        if data.get('time_from'):
            try:
                parts = str(data['time_from']).split(":")
                self.time_from_h.setValue(int(parts[0]))
                self.time_from_m.setValue(int(parts[1]) if len(parts) > 1 else 0)
            except (ValueError, IndexError):
                pass

        # Time To
        if data.get('time_to'):
            try:
                parts = str(data['time_to']).split(":")
                self.time_to_h.setValue(int(parts[0]))
                self.time_to_m.setValue(int(parts[1]) if len(parts) > 1 else 0)
            except (ValueError, IndexError):
                pass

        # NPT
        if data.get('is_npt'):
            self.is_npt.setChecked(True)

        # Description
        if data.get('description') or data.get('activity_description'):
            self.description.setPlainText(
                data.get('description') or data.get('activity_description', '')
            )

        if data.get('main_phase'):
            idx = self.phase_combo.findText(data['main_phase'], Qt.MatchContains)
            if idx >= 0:
                self.phase_combo.setCurrentIndex(idx)

        if data.get('status'):
            idx = self.status_combo.findText(data['status'])
            if idx >= 0:
                self.status_combo.setCurrentIndex(idx)

        if data.get('main_code'):
            if data.get('is_npt'):
                idx = self.npt_code_combo.findData(data['main_code'])
                if idx >= 0:
                    self.npt_code_combo.setCurrentIndex(idx)
            else:
                # پاک کردن فضاها
                clean_code = data['main_code'].strip()
                idx = self.code_combo.findText(clean_code, Qt.MatchContains)
                if idx >= 0:
                    self.code_combo.setCurrentIndex(idx)

    def _save(self):
        """ذخیره داده‌های دیالوگ."""
        # Validate
        from_sec = self.time_from_h.value() * 3600 + self.time_from_m.value() * 60
        to_sec = self.time_to_h.value() * 3600 + self.time_to_m.value() * 60
        if self.time_to_h.value() == 24:
            to_sec = 24 * 3600
        diff = to_sec - from_sec
        if diff < 0:
            diff += 24 * 3600
        if diff <= 0:
            self.error_label.setText("⚠️ Duration must be > 0")
            return

        from_str = (
            f"{self.time_from_h.value():02d}:{self.time_from_m.value():02d}"
        )
        to_str = (
            "24:00" if self.time_to_h.value() == 24
            else f"{self.time_to_h.value():02d}:{self.time_to_m.value():02d}"
        )

        if self.is_npt.isChecked():
            main_code = self.npt_code_combo.currentData() or ""
        else:
            main_code = self.code_combo.currentText().strip()
            # حذف prefix های category separator
            if main_code.startswith("──") or main_code.startswith("    "):
                main_code = ""

        self.result = {
            "time_from": from_str,
            "time_to": to_str,
            "duration": round(diff / 3600, 2),
            "main_phase": self.phase_combo.currentText(),
            "main_code": main_code,
            "sub_code": self.sub_code.currentText(),
            "status": self.status_combo.currentText(),
            "is_npt": self.is_npt.isChecked(),
            "contractor": (
                self.contractor_combo.currentText()
                if self.is_npt.isChecked() else ""
            ),
            "description": self.description.toPlainText(),
        }
        self.accept()

    def get_result(self):
        return self.result
     