"""
Daily Report Tab - گزارش روزانه با استفاده از توابع مرکزی (بازنویسی کامل)
"""

import logging
from datetime import datetime, date, time, timedelta
import os
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtPrintSupport import QPrinter, QPrintDialog

from PySide6.QtGui import QTextOption

from core.base_tab import DrillTabBase
from dialogs.hierarchy_dialogs import NewDailyReportDialog

import textwrap

from core.managers import (
    StatusBarManager,
    AutoSaveManager,
    TableButtonManager,
    ExportManager,
)
from core.database import DatabaseManager, Well, DailyReport, TimeLog24H, TimeLogMorning
from core.selection_manager import SelectionManager

from core.text_utils import wrap_text, wrap_html

logger = logging.getLogger(__name__)

from core.time_utils import TimeLineEdit, DrillTime

class DailyReportWidget(DrillTabBase):
    """تب گزارش روزانه با استفاده از توابع مرکزی"""

    def __init__(self, db_manager: DatabaseManager, parent=None):
        super().__init__("DailyReportWidget", db_manager, parent)
        self.db_manager = db_manager
        self.db = db_manager
        self.parent_window = parent
        self.status_manager.register_widget("DailyReport", self)
        
        # متغیرهای حالت
        self.current_well = None
        self.current_section = None
        self.current_report = None 
        self.current_report_id = None
        self.current_section_id = None
        self.current_daily_report_id = None
        self.current_tab_data = {}
        
        
        self.export_manager = ExportManager(self)
        
        # دیکشنری کدهای فعالیت (کامل و بدون تغییر)
        self.main_codes_dict = {
            "Rig Up/ Tear Down / Move ": [
                "Rig Moving/Positioning",
                "Rig Up",
                "Rig Down",
                "Tear Out",
                "Rig Skid",
            ],
            "Drilling ": [
                "Vertical Drilling",
                "Directional Drilling (Rotating)",
                "Directional Drilling (Sliding)",
            ],
            "Reaming": [
                "Reaming / Back Reaming",
                "Wash Down",
                "Under reaming/ Hole Opening/ Hole Enlargement",
                "Drill Out Cement/ Shoe track",
            ],
            "Coring": [
                "Trip in for Coring",
                "Trip out for Coring",
                "Coring Operation",
                "Core Recovery",
            ],
            "Circulate & Condition": [
                "Hole displacement",
                "Circulate/ Condition Mud",
                "Coiled Tubing Ops.",
                "Loss control",
            ],
            "Trips": [
                "R/U & R/D Pipe Handling Equip.",
                "PU/LD BHA",
                "Pick up Drill Pipe",
                "Lay Down Drill Pipe",
                "Run in Hole",
                "Pull Out Of Hole",
                "POOH with Pumping",
                "Wiper/ Condition Trip",
                "Wear Bushing",
            ],
            "Service/ Maintain Rig": ["Rig Lubricate"],
            "Repair Rig": [
                "Circulating System",
                "Power System",
                "Hoisting System",
                "Rotating System",
                "Well Control System",
                "Other",
            ],
            "Replacing Drill Line": ["Slip & Cut of Drill Line"],
            "Deviation Survey": ["Performing Survey Operation"],
            "Logging": [
                "R/U & R/D Logging Equip.",
                "Wire line logging",
                "TLC Logging",
                "CT Logging",
            ],
            "Run Casing/ Liner": [
                "R/U & R/D Handling Equip.",
                "CSG Running",
                "Pulling Casing",
                "CSG/Liner Integrity Test",
                "Liner Running",
                "Liner Tie back Operation",
                "Pull out Liner hanger setting tools and L/D",
                "Other Related Casing/Liner Activities",
                "Nipple up/down Wellhead",
            ],
            "Cementing": [
                "Casing/ Liner Cementing",
                "Plug Back",
                "Squeeze CMT",
                "Balance Plug",
                "Other",
            ],
            "Wait on Cement": ["for Casing/ Liner", "for Cement plug", "Other"],
            "Rig Up/Down BOP": ["Nipple up/down BOP", "Test BOP", "Pressure Test BOPs"],
            "Drill Stem Test": ["Conventional DST", "Full Bore DST", "Dry test"],
            "Fishing": [
                "Fishing Job",
                "Milling",
                "Coiled Tubing Ops.",
                "Work on Stuck",
            ],
            "Specialized Directional Work": [
                "RIH/ POOH Side-Track equip.",
                "Side-Tracking in Open Hole",
                "Side-Tracking in Cased Hole",
                "Other",
            ],
            "Operation Status (Waiting)": [
                "Waiting on Client",
                "Waiting on Operator Company",
                "Waiting on Rig Contractor",
                "Waiting on Service companies",
                "Waiting on Weather",
                "Waiting on Logistics/ Fuel",
            ],
            "Safety": ["Pre Job Safety Meeting (PJSM)", "Drills", "Other"],
            "Perforating": ["Wire line Perforation", "TCP Perforatin", "CT Perforatin"],
            "Completion/XMT": [
                "Completion Trips",
                "Completion Test",
                "Fluid displacement",
                "Slick line jobs",
                "Coiled Tubing Ops.",
                "Nipple up/down XMT",
                "XMT Test",
            ],
            "Treating": ["Acidizing", "N2 Lifting", "Coiled Tubing Ops."],
            "Swabbing": ["Swabbing"],
            "Surface Testing": ["Surface Testing", "Clean Up"],
            "Well Control": [
                "Kill the well",
                "Take S.C.R",
                "FIT/ LOT",
                "Flow Check",
                "Strip In / Out",
                "Coiled Tubing Ops.",
            ],
            "Other": ["Other"],
            "Subsea Operation": ["Run/ Retrieve Riser Equip.", "Subsea Installation"],
        }
        
        self.NPT_CODES = {
            # T = Trouble
            "T-FISH": "Fishing Operations",
            "T-STUCK": "Stuck Pipe",
            "T-KICK": "Kick / Well Control",
            "T-LOST-CIRC": "Lost Circulation",
            "T-TIGHT-HOLE": "Tight Hole / Pack-off",
            "T-FLOW CASE": "Flow Case / Well Control",
            "T-HOLE CONDITION": "Hole Condition",
            "T-BOP": "BOP Equipment Problem",
            "T-SHALLOW-GAS": "Shallow Gas",
            "T-H2S": "H2S Encounter",
            "T-CASING": "Casing/Cementing Problem",
            "T-SLOUGHING": "Sloughing/Caving",
            "T-WELL CONTROL": "Well Control (General)",
            "T-JUNK": "Junk in Hole",
            "T-SIDETRACK": "Sidetrack Required",

            # F = Failure
            "F-BIT": "Bit Failure",
            "F-BHA": "BHA Component Failure",
            "F-DRILL STRING": "Drill String Failure",
            "F-TDS": "Top Drive Failure",
            "F-PUMP": "Mud Pump Failure",
            "F-POWER": "Power System Failure",
            "F-HOIST": "Hoisting System Failure",
            "F-ROT": "Rotating System Failure",
            "F-CIRC": "Circulating System Failure",
            "F-MWD": "MWD/LWD Tool Failure",
            "F-MOTOR": "Downhole Motor Failure",
            "F-CASING": "Casing Running Equipment",
            "F-EVALUATION": "Evaluation Failure",
            "F-HOLE CONDITION": "Hole Condition Failure",
            "F-SOLID-CTRL": "Solid Control Equipment",
            "F-IBOP": "IBOP/Float Failure",

            # W = Waiting
            "W-CLIENT": "Waiting on Client Decision",
            "W-MATERIAL": "Waiting on Material/Parts",
            "W-SERVICE EQUIPMENT": "Waiting for Service Equipment",
            "W-SERVICE QUALITY": "Service Quality Issue",
            "W-WEATHER": "Waiting on Weather",
            "W-PERMIT": "Waiting on Permit",
            "W-LOGISTICS": "Waiting on Logistics",
            "W-FUEL": "Waiting on Fuel",
            "W-STOP OPERATION": "Stop Operation",
            "W-FORCE MAJOR": "Force Majeure (General)",
            "W-FORCE MAJEURE- 2ND WAR": "Force Majeure - War",
            "W-CREW": "Waiting on Crew/Personnel",

            # RR = Rig Repair
            "RR-TDS": "Top Drive Repair",
            "RR-PUMP": "Mud Pump Repair",
            "RR-SHAKER": "Shaker/Solid Control Repair",
            "RR-EAZY TORQUE": "Easy Torque Repair",
            "RR-KELLY HOSE": "Kelly Hose/Swivel Repair",
            "RR-POWER TONG": "Power Tong Repair",
            "RR-IBOP": "IBOP Repair",
            "RR-CRANE": "Crane/Lifting Equipment",
            "RR-GENERATOR": "Generator/Power Repair",
            "RR-OTHER": "Other Rig Repair",
        }
        
        self.init_ui()
        self.setup_connections()
        self.setup_managers()
  
    # -------- رابط کاربری (بدون تغییر) --------
    def init_ui(self):
        """راه‌اندازی رابط کاربری (بدون کامبوهای شرکت، پروژه، چاه و سکشن)"""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # ========== Header Section ==========
        header_group = QGroupBox("📋 Report Header")
        header_layout = QGridLayout()
        header_layout.setSpacing(10)

        # ردیف 0 - Report Date و Report Number
        header_layout.addWidget(QLabel("📅 Report Date:"), 0, 0)
        self.report_date = QDateEdit()
        self.report_date.setDate(QDate.currentDate())
        self.report_date.setCalendarPopup(True)
        self.report_date.setDisplayFormat("yyyy-MM-dd")
        header_layout.addWidget(self.report_date, 0, 1)

        header_layout.addWidget(QLabel("🔢 Report No.:"), 0, 2)
        self.report_number = QSpinBox()
        self.report_number.setRange(1, 9999)
        self.report_number.setValue(1)
        self.report_number.setReadOnly(True)
        self.report_number.setStyleSheet("QSpinBox { background-color: #f0f0f0; color: #555; }")
        header_layout.addWidget(self.report_number, 0, 3)

        # ردیف 1 - Rig Day و Status
        header_layout.addWidget(QLabel("🔢 Rig Day:"), 1, 0)
        self.rig_day = QSpinBox()
        self.rig_day.setRange(1, 365)
        self.rig_day.setValue(1)
        self.rig_day.setReadOnly(True)
        self.rig_day.setStyleSheet("QSpinBox { background-color: #f0f0f0; color: #555; }")
        header_layout.addWidget(self.rig_day, 1, 1)

        header_layout.addWidget(QLabel("📊 Status:"), 1, 2)
        self.status_combo = QComboBox()
        self.status_combo.addItems(["Draft", "Submitted", "Approved"])
        header_layout.addWidget(self.status_combo, 1, 3)

        # ردیف 2 - Depth measurements
        header_layout.addWidget(QLabel("📏 Depth @ 00:00 (m):"), 2, 0)
        self.depth_0000 = QDoubleSpinBox()
        self.depth_0000.setRange(0, 20000)
        self.depth_0000.setDecimals(2)
        self.depth_0000.setSuffix(" m")
        header_layout.addWidget(self.depth_0000, 2, 1)

        header_layout.addWidget(QLabel("📏 Depth @ 06:00 (m):"), 2, 2)
        self.depth_0600 = QDoubleSpinBox()
        self.depth_0600.setRange(0, 20000)
        self.depth_0600.setDecimals(2)
        self.depth_0600.setSuffix(" m")
        header_layout.addWidget(self.depth_0600, 2, 3)

        # ردیف 3 - Depth at 24:00
        header_layout.addWidget(QLabel("📏 Depth @ 24:00 (m):"), 3, 0)
        self.depth_2400 = QDoubleSpinBox()
        self.depth_2400.setRange(0, 20000)
        self.depth_2400.setDecimals(2)
        self.depth_2400.setSuffix(" m")
        header_layout.addWidget(self.depth_2400, 3, 1)

        header_group.setLayout(header_layout)
        main_layout.addWidget(header_group)
        
        # ========== Time Log Tabs ==========
        self.time_log_tabs = QTabWidget()

        # 24 Hours Tab
        self.time_24_tab = QWidget()
        self.time_24_layout = QVBoxLayout(self.time_24_tab)
        self.time_24_layout.setContentsMargins(5, 5, 5, 5)
        self.time_24_layout.setSpacing(10)

        title_24_label = QLabel("<h3>🕒 Rig Activity in Last 24 Hours</h3>")
        title_24_label.setFixedHeight(40)
        title_24_label.setAlignment(Qt.AlignCenter)
        self.time_24_layout.addWidget(title_24_label)

        self.time_24_table = QTableWidget(0, 9)
        self.setup_time_log_table(self.time_24_table)
        self.time_24_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.time_24_table.setMinimumHeight(400)
        self.time_24_table.horizontalHeader().setStretchLastSection(True)
        self.time_24_table.verticalHeader().setDefaultSectionSize(30)
        self.time_24_layout.addWidget(self.time_24_table, 1)

        btn_24_layout = QHBoxLayout()
        add_24_btn = QPushButton("➕ Add Row")
        remove_24_btn = QPushButton("➖ Remove Row")
        export_24_btn = QPushButton("📤 Export")

        add_24_btn.clicked.connect(lambda: self.add_time_log_row(self.time_24_table))
        remove_24_btn.clicked.connect(lambda: self.remove_time_log_row(self.time_24_table))
        export_24_btn.clicked.connect(lambda: self.export_manager.export_table_with_dialog(
            self.time_24_table, "24h_time_log"
        ))

        btn_24_layout.addWidget(add_24_btn)
        btn_24_layout.addWidget(remove_24_btn)
        btn_24_layout.addWidget(export_24_btn)
        btn_24_layout.addStretch()

        self.time_24_layout.addLayout(btn_24_layout)

        add_24_dialog_btn = QPushButton("📝 Add Activity")
        add_24_dialog_btn.setStyleSheet(
            "background: #9b59b6; color: white; padding: 4px 10px; "
            "border-radius: 3px; border: none; font-weight: bold;"
        )
        add_24_dialog_btn.setToolTip("Add activity with professional dialog")
        add_24_dialog_btn.clicked.connect(lambda: self._add_activity_dialog(self.time_24_table))
        btn_24_layout.addWidget(add_24_dialog_btn)



        # Morning Tour Tab
        self.morning_tab = QWidget()
        self.morning_layout = QVBoxLayout(self.morning_tab)

        morning_title = QLabel("<h3>☀️ Rig Activity in Morning Tour</h3>")
        morning_title.setAlignment(Qt.AlignCenter)
        self.morning_layout.addWidget(morning_title)

        self.morning_table = QTableWidget(0, 9)
        self.setup_time_log_table(self.morning_table)
        self.morning_layout.addWidget(self.morning_table)

        btn_morning_layout = QHBoxLayout()
        add_morning_btn = QPushButton("➕ Add Row")
        remove_morning_btn = QPushButton("➖ Remove Row")

        export_morning_btn = QPushButton("📤 Export")

        add_morning_btn.clicked.connect(lambda: self.add_time_log_row(self.morning_table))
        remove_morning_btn.clicked.connect(lambda: self.remove_time_log_row(self.morning_table))
        export_morning_btn.clicked.connect(lambda: self.export_manager.export_table_with_dialog(
            self.morning_table, "morning_time_log"
        ))

        btn_morning_layout.addWidget(add_morning_btn)
        btn_morning_layout.addWidget(remove_morning_btn)
        btn_morning_layout.addWidget(export_morning_btn)
        btn_morning_layout.addStretch()

        self.morning_layout.addLayout(btn_morning_layout)
        
        add_morning_dialog_btn = QPushButton("📝 Add Activity")
        add_morning_dialog_btn.setStyleSheet(
            "background: #9b59b6; color: white; padding: 4px 10px; "
            "border-radius: 3px; border: none; font-weight: bold;"
        )
        add_morning_dialog_btn.clicked.connect(lambda: self._add_activity_dialog(self.morning_table))
        btn_morning_layout.addWidget(add_morning_dialog_btn)

        self.time_log_tabs.addTab(self.time_24_tab, "🕒 24 Hours")
        self.time_log_tabs.addTab(self.morning_tab, "☀️ Morning Tour")

        main_layout.addWidget(self.time_log_tabs)
        
        # ========== Summary Section ==========
        summary_group = QGroupBox("📝 Daily Summary")
        summary_layout = QVBoxLayout()
        
        self.summary_text = QTextEdit()
        self.summary_text.setMaximumHeight(150)
        self.summary_text.setWordWrapMode(QTextOption.WordWrap)
        self.summary_text.setLineWrapMode(QTextEdit.WidgetWidth)
        self.summary_text.setPlaceholderText("Enter daily activities summary, observations, notes...")
        summary_layout.addWidget(self.summary_text)
        
        self.char_counter = QLabel("0/2000 characters")
        self.char_counter.setAlignment(Qt.AlignRight)
        self.char_counter.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        summary_layout.addWidget(self.char_counter)
        
        self.summary_text.textChanged.connect(self.update_char_counter)
        
        summary_group.setLayout(summary_layout)
        main_layout.addWidget(summary_group)

        # ========== Action Buttons ==========
        button_layout = QHBoxLayout()
        
        self.create_report_btn = QPushButton("📅 Create Daily Report")
        self.create_report_btn.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        self.create_report_btn.clicked.connect(self.create_daily_report_for_current_section)
        self.create_report_btn.setEnabled(False)
        button_layout.addWidget(self.create_report_btn)
    
        self.save_btn = QPushButton("💾 Save Report")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        self.save_btn.clicked.connect(self.save_report)
        
        self.load_btn = QPushButton("📂 Load Report")
        self.load_btn.clicked.connect(self.load_report_dialog)
        
        self.new_btn = QPushButton("🆕 New Report")
        self.new_btn.clicked.connect(self.new_report)
        
        
        self.print_btn = QPushButton("🖨️ Print")
        self.print_btn.clicked.connect(self.print_report)
        
        export_pdf_btn = QPushButton("📄 Export PDF")
        export_pdf_btn.setStyleSheet(
            "background: #e74c3c; color: white; padding: 4px 10px; "
            "border-radius: 3px; border: none; font-weight: bold;"
        )
        export_pdf_btn.clicked.connect(self._export_ddr_pdf)
        
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.load_btn)
        button_layout.addWidget(self.new_btn)
        button_layout.addWidget(self.print_btn)
        button_layout.addWidget(export_pdf_btn)
        button_layout.addStretch()
        



        main_layout.addLayout(button_layout)

        # ========== Statistics ==========
        stats_layout = QHBoxLayout()
        
        self.total_time_label = QLabel("Total Time: 0.0h")
        self.total_npt_label = QLabel("NPT Time: 0.0h")
        self.productivity_label = QLabel("Productivity: 100%")
        
        for label in [self.total_time_label, self.total_npt_label, self.productivity_label]:
            label.setStyleSheet("""
                QLabel {
                    background-color: #f8f9fa;
                    border: 1px solid #dee2e6;
                    border-radius: 4px;
                    padding: 5px 10px;
                    font-weight: bold;
                }
            """)
            stats_layout.addWidget(label)
        
        stats_layout.addStretch()
        main_layout.addLayout(stats_layout)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidget(central_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.NoFrame)

        main_container_layout = QVBoxLayout(self)
        main_container_layout.addWidget(scroll_area)
        self.setLayout(main_container_layout)

        # برچسب نمایش چاه و سکشن فعلی (اختیاری)
        self.current_info_label = QLabel("")
        self.current_info_label.setAlignment(Qt.AlignRight)
        self.current_info_label.setStyleSheet("color: #7f8c8d; font-size: 10px;")

        button_layout.insertWidget(0, self.current_info_label)
        self.current_info_label.hide() 

    def setup_managers(self):
        self.auto_save_manager = AutoSaveManager()
        self.auto_save_manager.enable_for_widget(
            "DailyReportWidget", self, interval_minutes=10
        )

    def setup_connections(self):
        # اتصال فقط به تغییر تاریخ برای محاسبه شماره گزارش
        self.report_date.dateChanged.connect(self.on_date_changed)
    
    def on_well_changed(self, well_id, well_data):
        """وقتی چاهی از طریق SelectionManager انتخاب می‌شود."""
        self.current_well = well_data
        self.current_well_id = well_id
        if well_data:
            self.current_info_label.setText(f"Well: {well_data.get('name', '')}")
            self.current_info_label.show()
            
            # محاسبه شماره گزارش و روز ریگ
            self.calculate_report_number_from_spud_date()
            self.auto_calculate_rig_day()
            
            # ========== انتخاب خودکار اولین سکشن ==========
            if self.db_manager and well_id:
                sections = self.db_manager.get_sections_by_well(well_id)
                if sections:
                    first_section = sections[0]
                    # انتخاب سکشن از طریق SelectionManager (این باعث فراخوانی on_section_changed می‌شود)
                    self.sel_manager.select_section(first_section['id'], first_section)
                    self.create_report_btn.setEnabled(True)
                else:
                    # اگر هیچ سکشنی وجود ندارد، از کاربر بپرسیم که آیا می‌خواهد یکی ایجاد کند
                    reply = QMessageBox.question(
                        self, "No Section",
                        "This well has no sections. Would you like to create one now?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if reply == QMessageBox.Yes:
                        from dialogs.hierarchy_dialogs import NewSectionDialog
                        dialog = NewSectionDialog(self.db_manager, self, well_id)
                        if dialog.exec():
                            # بارگذاری مجدد سکشن‌ها و انتخاب اولین
                            sections = self.db_manager.get_sections_by_well(well_id)
                            if sections:
                                self.sel_manager.select_section(sections[0]['id'], sections[0])
                                self.create_report_btn.setEnabled(True)
                            else:
                                self.create_report_btn.setEnabled(False)
                        else:
                            self.create_report_btn.setEnabled(False)
                    else:
                        self.create_report_btn.setEnabled(False)
            else:
                self.create_report_btn.setEnabled(True)
        else:
            self.current_info_label.hide()
            self.create_report_btn.setEnabled(False)
        
    def on_section_changed(self, section_id, section_data):
        """وقتی سکشنی انتخاب می‌شود."""
        if not section_id or section_id == self.current_section_id:
            return  # اگه تغییر نکرده، کاری نکن
        
        self.current_section_id = section_id
        self.current_section = section_data
        
        if section_data:
            well_name = ""
            if self.current_well and isinstance(self.current_well, dict):
                well_name = self.current_well.get('name', '')
            section_name = section_data.get('name', '') if isinstance(section_data, dict) else ''
            self.current_info_label.setText(f"Well: {well_name} | Section: {section_name}")
            self.current_info_label.show()
            
            # بارگذاری گزارش‌های این سکشن
            self.load_reports_for_section(section_id)
            self.create_report_btn.setEnabled(True)
        else:
            self.create_report_btn.setEnabled(False)

    def on_report_changed(self, report_id, report_info):
        """بارگذاری گزارش مشخص از SelectionManager."""
        if report_id and report_id != self.current_report_id:
            self.load_report_by_id(report_id)

    def calculate_report_number_from_spud_date(self):
        if not self.current_well_id:
            return
        try:
            session = self.db_manager.create_session()
            try:
                well = session.query(Well).filter(Well.id == self.current_well_id).first()
                if well and well.spud_date:
                    report_date = self.report_date.date().toPython()
                    spud_date = well.spud_date
                    if report_date >= spud_date:
                        existing_count = session.query(DailyReport).filter(
                            DailyReport.well_id == self.current_well_id,
                            DailyReport.report_date <= report_date
                        ).count()
                        
                        if existing_count > 0:
                            self.report_number.setValue(existing_count + 1)
                        else:
                            delta_days = (report_date - spud_date).days
                            self.report_number.setValue(max(1, delta_days + 1))
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Error calculating report number: {e}")

    def auto_calculate_rig_day(self):
        """محاسبه روز ریگ بر اساس اولین گزارش یا اسپاد"""
        if not self.current_well_id:
            return
        # اگر سکشن انتخاب شده باشد، بر اساس سکشن محاسبه می‌کنیم
        section_id = self.current_section_id
        if section_id:
            self.calculate_rig_day_for_section(section_id)
        else:
            self.calculate_rig_day_for_well(self.current_well_id)

    def calculate_rig_day_for_section(self, section_id):
        try:
            session = self.db_manager.create_session()
            try:
                report_date = self.report_date.date().toPython()
                existing_report = session.query(DailyReport).filter(
                    DailyReport.section_id == section_id,
                    DailyReport.report_date == report_date
                ).first()
                if existing_report:
                    self.rig_day.setValue(existing_report.rig_day or 1)
                else:
                    last_report = session.query(DailyReport).filter(
                        DailyReport.section_id == section_id
                    ).order_by(DailyReport.report_date.desc()).first()
                    if last_report:
                        self.rig_day.setValue((last_report.rig_day or 0) + 1)
                    else:
                        self.rig_day.setValue(1)
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Error calculating rig day for section: {e}")

    def calculate_rig_day_for_well(self, well_id):
        try:
            session = self.db_manager.create_session()
            try:
                report_date = self.report_date.date().toPython()
                existing_report = session.query(DailyReport).filter(
                    DailyReport.well_id == well_id,
                    DailyReport.report_date == report_date
                ).first()
                if existing_report:
                    self.rig_day.setValue(existing_report.rig_day or 1)
                else:
                    last_report = session.query(DailyReport).filter(
                        DailyReport.well_id == well_id
                    ).order_by(DailyReport.report_date.desc()).first()
                    if last_report:
                        self.rig_day.setValue((last_report.rig_day or 0) + 1)
                    else:
                        self.rig_day.setValue(1)
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Error calculating rig day for well: {e}")

    def load_reports_for_section(self, section_id):
        """بارگذاری آخرین گزارش سکشن (اختیاری)"""
        if not section_id or section_id == -1:
            return
        try:
            reports = self.db_manager.get_daily_reports_by_section(section_id)
            if reports:
                latest_report = reports[0]
                self.load_report_by_id(latest_report["id"])
        except Exception as e:
            logger.error(f"Error loading reports: {e}")

    def on_date_changed(self):
        """هنگام تغییر تاریخ، شماره گزارش و روز ریگ را به‌روز می‌کنیم"""
        if self.current_well_id:
            self.calculate_report_number_from_spud_date()
            self.auto_calculate_rig_day()
        self.status_manager.show_message("DailyReport", f"Report date: {self.report_date.date().toString('yyyy-MM-dd')}", 1500)

    def setup_time_log_table(self, table):
        table.setColumnCount(10)
        table.setHorizontalHeaderLabels([
            "🕐 From", "🕒 To", "⏱️ Duration", 
            "📊 Main Phase", "🏷️ Main Code", "🏷️ Sub Code",
            "📈 Status", "⚠️ NPT", "🏢 Contractor", "📝 Description"
        ])

        # ستون‌های ثابت
        table.setColumnWidth(0, 80)
        table.setColumnWidth(1, 80)
        table.setColumnWidth(2, 80)
        table.setColumnWidth(3, 120)
        table.setColumnWidth(4, 150)
        table.setColumnWidth(5, 150)
        table.setColumnWidth(6, 100)
        table.setColumnWidth(7, 60)
        table.setColumnWidth(8, 120)

        # Description بزرگ ولی کنترل‌شده
        table.setColumnWidth(9, 420)

        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setWordWrap(True)

        table.verticalHeader().setDefaultSectionSize(30)
        table.verticalHeader().setMinimumSectionSize(30)
        table.verticalHeader().setMaximumSectionSize(120)

        # اگر عرض ستون description عوض شد، دوباره ارتفاع‌ها محاسبه شوند
        table.horizontalHeader().sectionResized.connect(
            lambda *_: self._adjust_all_row_heights(table)
        )

        
    # ========== Time Log Helpers ==========
    def add_time_log_row(self, table, log_data=None):
        row = table.rowCount()
        table.insertRow(row)

        # ستون 0: زمان شروع
        from_time = TimeLineEdit()
        if log_data and hasattr(log_data, 'time_from'):
            if hasattr(log_data.time_from, 'hour'):
                # اگر زمان از نوع time است
                if log_data.time_from.hour == 0 and log_data.time_from.minute == 0:
                    from_time.set_time(0, 0, is_2400=True)
                else:
                    from_time.set_time(log_data.time_from.hour, log_data.time_from.minute)
            elif isinstance(log_data.time_from, str):
                if log_data.time_from == "24:00":
                    from_time.set_time(0, 0, is_2400=True)
                else:
                    try:
                        parts = log_data.time_from.split(':')
                        hour = int(parts[0])
                        minute = int(parts[1]) if len(parts) > 1 else 0
                        from_time.set_time(hour, minute)
                    except:
                        from_time.set_time(8, 0)
        else:
            from_time.set_time(8, 0)
        
        from_time.timeChanged.connect(lambda: self.calculate_row_duration(table, row))
        table.setCellWidget(row, 0, from_time)

        # ستون 1: زمان پایان
        to_time = TimeLineEdit()
        if log_data and hasattr(log_data, 'time_to'):
            if hasattr(log_data.time_to, 'hour'):
                if log_data.time_to.hour == 0 and log_data.time_to.minute == 0:
                    to_time.set_time(0, 0, is_2400=True)
                else:
                    to_time.set_time(log_data.time_to.hour, log_data.time_to.minute)
            elif isinstance(log_data.time_to, str):
                if log_data.time_to == "24:00":
                    to_time.set_time(0, 0, is_2400=True)
                else:
                    try:
                        parts = log_data.time_to.split(':')
                        hour = int(parts[0])
                        minute = int(parts[1]) if len(parts) > 1 else 0
                        to_time.set_time(hour, minute)
                    except:
                        to_time.set_time(16, 0)
        else:
            to_time.set_time(16, 0)
        
        to_time.timeChanged.connect(lambda: self.calculate_row_duration(table, row))
        table.setCellWidget(row, 1, to_time)

        # ستون 2: دیرکرد
        duration_label = QLabel("0.00")
        duration_label.setAlignment(Qt.AlignCenter)
        table.setCellWidget(row, 2, duration_label)

        # ستون 3: فاز اصلی
        main_phase_combo = QComboBox()
        phases = [
            "MOV - Moving", "DRL - Drilling", "LOG - Logging", 
            "CSG - Casing/Liner", "COM - Completion", "FTS - Formation Testing",
            "PIH - Pilot Hole", "COR - Coring", "REE - Re-Entry", "ABD - Abandonment"
        ]
        main_phase_combo.addItems(phases)
        if log_data and hasattr(log_data, 'main_phase'):
            index = main_phase_combo.findText(log_data.main_phase, Qt.MatchContains)
            if index >= 0:
                main_phase_combo.setCurrentIndex(index)
        table.setCellWidget(row, 3, main_phase_combo)

        # ستون 4: QStackedWidget برای دو کامبو (عادی و NPT)
        stacked = QStackedWidget()
        normal_code_combo = QComboBox()
        normal_code_combo.addItems(list(self.main_codes_dict.keys()))
        npt_code_combo = QComboBox()
        npt_code_combo.addItems(list(self.NPT_CODES.keys()))

        is_npt = False
        if log_data and hasattr(log_data, 'is_npt'):
            is_npt = log_data.is_npt
        stored_main_code = ""
        if log_data and hasattr(log_data, 'main_code'):
            stored_main_code = str(log_data.main_code or "")
            target_combo = npt_code_combo if is_npt else normal_code_combo
            idx = self._find_code_index(target_combo, stored_main_code)
            if idx >= 0:
                target_combo.setCurrentIndex(idx)

        stacked.addWidget(normal_code_combo)
        stacked.addWidget(npt_code_combo)
        stacked.setCurrentIndex(1 if is_npt else 0)
        table.setCellWidget(row, 4, stacked)

        # ستون 5: زیرکد
        sub_code_combo = QComboBox()
        if is_npt:
            self._update_sub_codes_for_npt(sub_code_combo, npt_code_combo.currentText())
        else:
            self._update_sub_codes_normal(sub_code_combo, normal_code_combo.currentText())
        if log_data and hasattr(log_data, 'sub_code'):
            self._select_code_value(sub_code_combo, str(log_data.sub_code or ""))
        table.setCellWidget(row, 5, sub_code_combo)

        # اتصالات
        normal_code_combo.currentTextChanged.connect(
            lambda text, sc=sub_code_combo: self._update_sub_codes_normal(sc, text))
        npt_code_combo.currentTextChanged.connect(
            lambda text, sc=sub_code_combo: self._update_sub_codes_for_npt(sc, text))

        # ستون 6: وضعیت
        status_combo = QComboBox()
        status_combo.addItems(["Normal", "Delayed", "Completed", "In Progress", "On Hold"])
        if log_data and hasattr(log_data, 'status'):
            index = status_combo.findText(log_data.status)
            if index >= 0:
                status_combo.setCurrentIndex(index)
        table.setCellWidget(row, 6, status_combo)

        # ستون 7: چک‌باکس NPT
        npt_checkbox = QCheckBox()
        npt_checkbox.setChecked(is_npt)
        npt_checkbox.stateChanged.connect(
            lambda state, r=row: self._on_npt_checkbox_changed(table, r, state))
        table.setCellWidget(row, 7, npt_checkbox)

        # ستون 8: Contractor
        contractor_widget = QWidget()
        contractor_layout = QHBoxLayout(contractor_widget)
        contractor_layout.setContentsMargins(0, 0, 0, 0)

        contractor_combo = QComboBox()
        contractor_combo.setEditable(True)
        contractor_combo.addItems([
            "", "TDDC", "PDF Co.", "MSD Co.", "Vira Co.",
            "Mehran", "mapsa co.", "OEOC", "NIDC", "Other"
        ])

        # ✅ اگر از import آمده و contractor دارد
        if log_data and hasattr(log_data, 'contractor') and log_data.contractor:
            contractor_text = str(log_data.contractor).strip()
            if contractor_text:
                # اگر در لیست نیست اضافه کن
                idx = contractor_combo.findText(contractor_text)
                if idx >= 0:
                    contractor_combo.setCurrentIndex(idx)
                else:
                    contractor_combo.addItem(contractor_text)
                    contractor_combo.setCurrentText(contractor_text)
            else:
                contractor_combo.setCurrentIndex(0)  # خالی
        else:
            contractor_combo.setCurrentIndex(0)  # خالی

        contractor_combo.setEnabled(is_npt)
        contractor_combo.setVisible(is_npt)

        contractor_layout.addWidget(contractor_combo)
        table.setCellWidget(row, 8, contractor_widget)

        # ستون 9: توضیحات (با Wrap)
        desc_edit = QTextEdit()
        desc_edit.setMinimumHeight(28)
        desc_edit.setMaximumHeight(110)
        desc_edit.setPlaceholderText("Enter activity description...")
        desc_edit.setWordWrapMode(QTextOption.WordWrap)
        desc_edit.setLineWrapMode(QTextEdit.WidgetWidth)
        desc_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        desc_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        desc_edit.setStyleSheet("""
            QTextEdit {
                border: none;
                background: transparent;
                font-size: 11px;
                padding: 2px;
            }
        """)

        if log_data and hasattr(log_data, 'activity_description'):
            desc_edit.setPlainText(str(log_data.activity_description or ""))

        desc_edit.textChanged.connect(
            lambda r=row, t=table, d=desc_edit: self._adjust_row_height(t, r, d)
        )
        table.setCellWidget(row, 9, desc_edit)

        QTimer.singleShot(50, lambda: self._adjust_row_height(table, row, desc_edit))
        
        # محاسبه اولیه دیرکرد
        self.calculate_row_duration(table, row)

        if is_npt:
            self.highlight_npt_row(table, row, 2)
        
    def _adjust_row_height(self, table, row, text_edit):
        """ارتفاع ردیف بر اساس wrap واقعی متن در عرض ستون"""
        try:
            if row >= table.rowCount():
                return

            col = 9  # Description column
            available_width = max(80, table.columnWidth(col) - 12)

            doc = text_edit.document()
            doc.setTextWidth(available_width)

            doc_height = doc.size().height()

            min_height = 30
            max_height = 120
            desired_height = max(min_height, min(max_height, int(doc_height) + 8))

            table.setRowHeight(row, desired_height)

        except Exception:
            pass
            
            
    def _adjust_all_row_heights(self, table):
        """تنظیم ارتفاع همه ردیف‌ها بر اساس Description"""
        try:
            for row in range(table.rowCount()):
                desc_widget = table.cellWidget(row, 9)
                if desc_widget and isinstance(desc_widget, QTextEdit):
                    self._adjust_row_height(table, row, desc_widget)
        except Exception:
            pass
                
    def _add_contractor_if_new(self, combo):
        """اگر کاربر نام شرکت جدیدی تایپ کرد، به لیست اضافه کن"""
        text = combo.currentText().strip()
        if text and combo.findText(text) == -1:
            combo.addItem(text)
            self.status_manager.show_message("DailyReport", f"New contractor '{text}' added", 2000)
            
    @staticmethod
    def _code_variants(value):
        text = str(value or "").strip()
        # Stored imports may be "2 - Drilling" while UI uses "Drilling".
        variants = [text]
        if " - " in text:
            variants.append(text.split(" - ", 1)[1].strip())
        return [v.lower().strip() for v in variants if v]

    def _find_code_index(self, combo, stored_value):
        wanted = self._code_variants(stored_value)
        for index in range(combo.count()):
            candidate = self._code_variants(combo.itemText(index))
            if any(a == b or a in b or b in a for a in wanted for b in candidate):
                return index
        return -1

    def _select_code_value(self, combo, stored_value):
        index = self._find_code_index(combo, stored_value)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif stored_value:
            # Preserve an imported code not present in the local catalogue;
            # silently replacing it with the first item is data corruption.
            combo.setEditable(True)
            combo.setCurrentText(str(stored_value))

    def _update_sub_codes_normal(self, sub_combo, main_code):
        """به‌روزرسانی زیرکدها برای فعالیت عادی"""
        sub_combo.clear()
        if main_code in self.main_codes_dict:
            sub_combo.addItems(self.main_codes_dict[main_code])
        sub_combo.setEditable(True)

    def _update_sub_codes_for_npt(self, sub_combo, npt_code):
        """به‌روزرسانی زیرکدها برای NPT"""
        sub_combo.clear()
        desc = self.NPT_CODES.get(npt_code, "")
        if desc:
            sub_combo.addItem(desc)
        sub_combo.addItem("")
        sub_combo.setEditable(True)

    def _on_npt_checkbox_changed(self, table, row, state):
        is_npt = (state == 2)
        stacked = table.cellWidget(row, 4)
        if stacked:
            stacked.setCurrentIndex(1 if is_npt else 0)

        # نمایش/مخفی کردن کامبوی Contractor
        contractor_widget = table.cellWidget(row, 8)
        if contractor_widget:
            contractor_combo = contractor_widget.findChild(QComboBox)
            if contractor_combo:
                contractor_combo.setEnabled(is_npt)
                contractor_combo.setVisible(is_npt)

        self.highlight_npt_row(table, row, 2 if is_npt else 0)
        self.update_statistics()
    
    def calculate_row_duration(self, table, row):
        from_widget = table.cellWidget(row, 0)
        to_widget = table.cellWidget(row, 1)
        duration_widget = table.cellWidget(row, 2)
        
        if from_widget and to_widget and duration_widget:
            # دریافت زمان‌ها از TimeLineEdit
            from_hour, from_minute, from_is_2400 = from_widget.get_time()
            to_hour, to_minute, to_is_2400 = to_widget.get_time()
            
            # تبدیل به ثانیه
            if from_is_2400:
                from_seconds = 24 * 3600
            else:
                from_seconds = from_hour * 3600 + from_minute * 60
            
            if to_is_2400:
                to_seconds = 24 * 3600
            else:
                to_seconds = to_hour * 3600 + to_minute * 60
            
            # محاسبه اختلاف
            diff_seconds = to_seconds - from_seconds
            if diff_seconds < 0:
                diff_seconds += 24 * 3600
            
            hours = diff_seconds / 3600.0
            duration_widget.setText(f"{hours:.2f}")
        
    def calculate_all_durations(self, table):
        for row in range(table.rowCount()):
            self.calculate_row_duration(table, row)
        self.update_statistics()
        self.status_manager.show_success("DailyReport", "Durations calculated")

    def remove_time_log_row(self, table):
        current_row = table.currentRow()
        if current_row >= 0:
            table.removeRow(current_row)
            self.update_statistics()
            self.status_manager.show_message("DailyReport", "Row removed", 2000)

    def highlight_npt_row(self, table, row, state):
        is_npt = (state == 2)
        for col in range(table.columnCount()):
            widget = table.cellWidget(row, col)
            if widget:
                if is_npt:
                    widget.setStyleSheet("background-color: #ffcccc;")
                else:
                    widget.setStyleSheet("")
        self.update_statistics()

    # ========== Core Operations ==========
    def _collect_report_data(
        self,
        well_id: int,
        section_id: int
    ) -> dict:
        """جمع‌آوری داده‌های فرم برای ذخیره"""
        report_data = {
            "well_id": well_id,
            "section_id": section_id,
            "report_date": self.report_date.date().toPython(),
            "report_number": self.report_number.value(),
            "rig_day": self.rig_day.value(),
            "depth_0000": self.depth_0000.value(),
            "depth_0600": self.depth_0600.value(),
            "depth_2400": self.depth_2400.value(),
            "summary": self.summary_text.toPlainText(),
            "status": self.status_combo.currentText(),
            "created_by": (
                self.parent_window.user['id']
                if hasattr(self.parent_window, 'user')
                else None
            ),
        }

        if self.current_report and self.current_report.get("id"):
            report_data["id"] = self.current_report["id"]

        return report_data

    def _build_header_snapshot(self, well_id: int) -> dict:
        """ساخت snapshot از اطلاعات چاه"""
        if not well_id or not self.db_manager:
            return {}
        well = self.db_manager.get_well_by_id(well_id)
        if not well:
            return {}
        return {
            "well_name": well.get("name", ""),
            "rig_name": well.get("rig_name", ""),
            "operator": well.get("operator", ""),
            "client": well.get("client", ""),
            "field_name": well.get("field_name", ""),
            "supervisor_day": well.get("supervisor_day", ""),
            "supervisor_night": well.get("supervisor_night", ""),
            "geologist1": well.get("geologist1", ""),
            "tool_pusher_day": well.get("tool_pusher_day", ""),
            "formation": well.get("formation", ""),
            "section_name": well.get("section_name", ""),
            "drilling_contractor": well.get("drilling_contractor", ""),
        }

    def _validate_save_preconditions(
        self,
        well_id: int,
        section_id: int
    ) -> tuple[bool, str]:
        """
        بررسی شرایط ذخیره
        Returns: (is_valid, error_message)
        """
        if not well_id:
            return False, "Please select a well first"

        if not section_id or section_id == -1:
            return False, "No section selected. Please create a section first."

        sections = self.db_manager.get_sections_by_well(well_id)
        valid_ids = [s['id'] for s in sections]

        if section_id not in valid_ids:
            if valid_ids:
                return True, f"Section corrected to {valid_ids[0]}"
            return False, "No sections exist. Create a section first."

        return True, ""

    def _refresh_after_save(self, result: dict) -> None:
        """به‌روزرسانی UI بعد از ذخیره موفق"""
        if self.parent_window and hasattr(
            self.parent_window, 'populate_hierarchy'
        ):
            self.parent_window.populate_hierarchy()
            if result.get('id'):
                QTimer.singleShot(
                    100,
                    lambda: self.parent_window.select_item_in_tree(
                        "daily_report", result['id']
                    )
                )

    def save_report(self) -> bool:
        """ذخیره گزارش روزانه - نسخه refactor شده"""
        try:
            well_id = self.current_well_id
            section_id = self.current_section_id

            # fallback از گزارش جاری
            if not well_id and self.current_report:
                well_id = self.current_report.get("well_id")
            if (not section_id or section_id == -1) and self.current_report:
                section_id = self.current_report.get("section_id")

            # Validation
            is_valid, message = self._validate_save_preconditions(
                well_id, section_id
            )
            if not is_valid:
                self.status_manager.show_error("DailyReport", message)
                return False

            # اگر section_id نیاز به تصحیح داشت
            if "corrected" in message:
                sections = self.db_manager.get_sections_by_well(well_id)
                section_id = sections[0]['id']
                self.current_section_id = section_id

            # جمع‌آوری داده
            report_data = self._collect_report_data(well_id, section_id)
            report_data["header_snapshot"] = self._build_header_snapshot(
                well_id
            )

            # Validation با validators
            from core.validators import DailyReportValidator
            validation = DailyReportValidator.validate(report_data)
            if not validation.is_valid:
                reply = QMessageBox.warning(
                    self, "⚠️ Validation Issues",
                    f"Issues:\n\n{validation.summary()}\n\nSave anyway?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return False

            # ذخیره
            result = self.db_manager.save_daily_report(report_data)
            if not result:
                self.status_manager.show_error(
                    "DailyReport", "Failed to save report"
                )
                return False

            # به‌روزرسانی state
            report_id = result["id"]
            self.current_report_id = report_id
            self.current_report = result
            self.current_daily_report_id = report_id

            # ذخیره time logs
            self.save_time_logs_to_db(report_id)

            # ذخیره تب‌های دیگر
            self._save_related_tabs()

            # refresh UI
            self._refresh_after_save(result)

            self.status_manager.show_success(
                "DailyReport",
                f"Report #{result['report_number']} saved!"
            )
            return True

        except Exception as e:
            logger.error(f"Save report error: {e}", exc_info=True)
            self.status_manager.show_error(
                "DailyReport", f"Error: {str(e)}"
            )
            return False

    def _save_related_tabs(self) -> None:
        """ذخیره داده‌های تب‌های مرتبط"""
        if not self.parent_window:
            return

        tab_saves = [
            ('drilling_report_tab', 'save_all_tabs'),
            ('downhole_tab', 'save_all_data_to_db'),
            ('equipment_widget', 'save_all_data'),
            ('logistics_widget', 'save_all_data'),
            ('safety_widget', 'save_data'),
            ('services_widget', 'save_data'),
            ('trajectory_widget', 'save_data'),
        ]

        for attr_name, method_name in tab_saves:
            tab = getattr(self.parent_window, attr_name, None)
            if tab and hasattr(tab, method_name):
                try:
                    getattr(tab, method_name)()
                except Exception as e:
                    logger.error(
                        f"Error saving {attr_name}.{method_name}: {e}"
                    )
                    
    def save_time_logs_to_db(self, report_id):
        session = self.db_manager.create_session()
        try:
            session.query(TimeLog24H).filter_by(report_id=report_id).delete()
            session.query(TimeLogMorning).filter_by(report_id=report_id).delete()
            
            for row in range(self.time_24_table.rowCount()):
                log = self._extract_time_log_row(self.time_24_table, row)
                if log:
                    session.add(TimeLog24H(
                        report_id=report_id,
                        time_from=log["time_from"],
                        time_to=log["time_to"],
                        duration=log["duration"],
                        main_phase=log["main_phase"],
                        main_code=log["main_code"],
                        sub_code=log["sub_code"],
                        status=log["status"],
                        is_npt=log["is_npt"],
                        activity_description=log["activity_description"],
                        contractor=log.get("contractor", "")
                    ))
            
            for row in range(self.morning_table.rowCount()):
                log = self._extract_time_log_row(self.morning_table, row)
                if log:
                    session.add(TimeLogMorning(
                        report_id=report_id,
                        time_from=log["time_from"],
                        time_to=log["time_to"],
                        duration=log["duration"],
                        main_phase=log["main_phase"],
                        main_code=log["main_code"],
                        sub_code=log["sub_code"],
                        status=log["status"],
                        is_npt=log["is_npt"],
                        activity_description=log["activity_description"],
                        contractor=log.get("contractor", "")
                    ))
            
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Time log save error: {e}")
        finally:
            session.close()

    def _extract_time_log_row(self, table, row):
        try:
            from_widget = table.cellWidget(row, 0)
            to_widget = table.cellWidget(row, 1)
            duration_widget = table.cellWidget(row, 2)

            if not from_widget or not to_widget:
                return None

            # ✅ خواندن duration
            duration = 0.0
            if duration_widget and isinstance(
                duration_widget, QLabel
            ):
                try:
                    duration = float(duration_widget.text())
                except (ValueError, TypeError):
                    pass

            # ✅ خواندن time_from - امن
            from_python_time = time(0, 0)
            if hasattr(from_widget, 'get_time'):
                try:
                    hour, minute, is_2400 = from_widget.get_time()
                    if is_2400:
                        from_python_time = time(0, 0)
                    else:
                        from_python_time = time(hour, minute)
                except Exception:
                    pass

            # ✅ خواندن time_to - امن
            to_python_time = time(0, 0)
            if hasattr(to_widget, 'get_time'):
                try:
                    hour, minute, is_2400 = to_widget.get_time()
                    if is_2400:
                        to_python_time = time(0, 0)
                    else:
                        to_python_time = time(hour, minute)
                except Exception:
                    pass

            # ✅ محاسبه duration اگر صفر بود
            if duration == 0.0:
                from_dt = DrillTime(
                    from_python_time.hour,
                    from_python_time.minute
                )
                to_dt = DrillTime(
                    to_python_time.hour,
                    to_python_time.minute
                )
                duration = to_dt - from_dt

            # ✅ Main Code از stacked widget
            stacked = table.cellWidget(row, 4)
            main_code = ""
            if stacked and isinstance(stacked, QStackedWidget):
                current = stacked.currentWidget()
                if isinstance(current, QComboBox):
                    main_code = current.currentText()

            npt_checkbox = table.cellWidget(row, 7)
            is_npt = (
                npt_checkbox.isChecked()
                if npt_checkbox else False
            )

            # ✅ Contractor
            contractor = ""
            contractor_widget = table.cellWidget(row, 8)
            if contractor_widget:
                contractor_combo = contractor_widget.findChild(
                    QComboBox
                )
                if contractor_combo:
                    contractor = contractor_combo.currentText()

            # ✅ Description
            desc_edit = table.cellWidget(row, 9)
            description = ""
            if desc_edit and isinstance(desc_edit, QTextEdit):
                description = desc_edit.toPlainText()
            elif desc_edit and isinstance(desc_edit, QLineEdit):
                description = desc_edit.text()

            return {
                "time_from": from_python_time,
                "time_to": to_python_time,
                "duration": duration,
                "main_phase": (
                    table.cellWidget(row, 3).currentText()
                    if table.cellWidget(row, 3) else ""
                ),
                "main_code": main_code,
                "sub_code": (
                    table.cellWidget(row, 5).currentText()
                    if table.cellWidget(row, 5) else ""
                ),
                "status": (
                    table.cellWidget(row, 6).currentText()
                    if table.cellWidget(row, 6) else ""
                ),
                "is_npt": is_npt,
                "contractor": contractor,
                "activity_description": description
            }
        except Exception as e:
            logger.error(f"Row extraction error at row {row}: {e}")
            return None
            
    def _calculate_duration_with_2400(self, from_time: DrillTime, to_time: DrillTime) -> float:
        """محاسبه دیرکرد با پشتیبانی از 24:00"""
        return to_time - from_time
        
    def load_report_dialog(self):
        well_id = self.current_well_id
        section_id = self.current_section_id

        if not well_id:
            self.status_manager.show_error("DailyReport", "Please select a well first")
            return
        if not section_id or section_id == -1:
            self.status_manager.show_error("DailyReport", "Please select a section first")
            return

        try:
            reports = self.db_manager.get_daily_reports_by_section(section_id)
            if not reports:
                self.status_manager.show_message("DailyReport", "No reports found for this section")
                return
            
            dialog = QDialog(self)
            dialog.setWindowTitle("📂 Load Report")
            dialog.setFixedSize(600, 400)
            layout = QVBoxLayout()
            
            table = QTableWidget(len(reports), 4)
            table.setHorizontalHeaderLabels(["Date", "Report #", "Rig Day", "Status"])
            table.setSelectionBehavior(QTableWidget.SelectRows)
            table.setSelectionMode(QTableWidget.SingleSelection)
            
            for i, report in enumerate(reports):
                date_str = str(report.get("report_date", ""))
                table.setItem(i, 0, QTableWidgetItem(date_str))
                table.setItem(i, 1, QTableWidgetItem(str(report.get("report_number", ""))))
                table.setItem(i, 2, QTableWidgetItem(str(report.get("rig_day", ""))))
                table.setItem(i, 3, QTableWidgetItem(report.get("status", "")))
                # ذخیره ID در اولین ستون
                table.item(i, 0).setData(Qt.UserRole, report["id"])
            
            table.resizeColumnsToContents()
            table.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(table)
            
            button_layout = QHBoxLayout()
            load_btn = QPushButton("📥 Load Selected")
            cancel_btn = QPushButton("❌ Cancel")
            
            load_btn.clicked.connect(lambda: self._load_selected_report_from_dialog(dialog, table))
            cancel_btn.clicked.connect(dialog.reject)
            
            button_layout.addWidget(load_btn)
            button_layout.addWidget(cancel_btn)
            button_layout.addStretch()
            layout.addLayout(button_layout)
            
            dialog.setLayout(layout)
            dialog.exec()
            
        except Exception as e:
            logger.error(f"Error loading reports dialog: {e}")
            self.status_manager.show_error("DailyReport", f"Error: {str(e)[:100]}")

    def _load_selected_report_from_dialog(self, dialog, table):
        selected_items = table.selectedItems()
        if not selected_items:
            self.status_manager.show_error("DailyReport", "Please select a report")
            return
        report_id = selected_items[0].data(Qt.UserRole)
        if report_id:
            self.load_report_by_id(report_id)
            dialog.accept()
            self.status_manager.show_success("DailyReport", "Report loaded")

    def load_report_by_id(self, report_id):
        self.current_report_id = report_id
        self.current_daily_report_id = report_id
        
        try:
            report_data = self.db_manager.get_daily_report_by_id(report_id)
            if not report_data:
                self.status_manager.show_error("DailyReport", "Report not found")
                return

            self.current_report = report_data
            self.current_well_id = report_data.get("well_id")
            self.current_section_id = report_data.get("section_id")

            self.report_date.setDate(report_data["report_date"])
            self.report_number.setValue(report_data.get("report_number", 1))
            self.rig_day.setValue(report_data.get("rig_day", 1))
            self.depth_0000.setValue(report_data.get("depth_0000", 0))
            self.depth_0600.setValue(report_data.get("depth_0600", 0))
            self.depth_2400.setValue(report_data.get("depth_2400", 0))
            import textwrap
            raw_summary = report_data.get("summary", "") or ""
            if len(raw_summary) > 150:
                lines = textwrap.wrap(raw_summary, width=150, break_long_words=False, break_on_hyphens=False)
                self.summary_text.setPlainText("\n".join(lines))
            else:
                self.summary_text.setPlainText(report_data.get("summary", "") or "")
            idx = self.status_combo.findText(report_data.get("status", "Draft"))
            if idx >= 0:
                self.status_combo.setCurrentIndex(idx)

            well_id = report_data.get("well_id")
            section_id = report_data.get("section_id")


            self.load_time_logs(report_id, self.time_24_table, is_morning=False)
            self.load_time_logs(report_id, self.morning_table, is_morning=True)

            self.status_manager.show_success("DailyReport", f"Report #{report_data.get('report_number', '')} loaded")
        except Exception as e:
            logger.error(f"Load report error: {e}")
            self.status_manager.show_error("DailyReport", f"Error loading report: {str(e)[:100]}")

    def load_time_logs(self, report_id, table, is_morning=False):
        table.setRowCount(0)
        session = self.db_manager.create_session()
        try:
            if is_morning:
                logs = session.query(TimeLogMorning).filter_by(report_id=report_id).all()
            else:
                logs = session.query(TimeLog24H).filter_by(report_id=report_id).all()
            for log in logs:
                self.add_time_log_row(table, log)
            QTimer.singleShot(100, lambda: self._adjust_all_row_heights(table))
        except Exception as e:
            logger.error(f"Error loading time logs: {e}")
        finally:
            session.close()


    def create_daily_report_for_current_section(self):
        section_id = self.current_section_id
        if not section_id or section_id == -1:
            self.status_manager.show_error("DailyReport", "Please select a section first")
            return

        try:
            from dialogs.hierarchy_dialogs import NewDailyReportDialog
            dialog = NewDailyReportDialog(self.db_manager, self.parent_window, section_id)
            if dialog.exec():
                created_id = getattr(dialog, 'created_id', None)
                if created_id:
                    # ✅ FIX: اکنون copy data واقعاً فراخوانی می‌شود
                    if hasattr(dialog, 'copy_previous_cb') and dialog.copy_previous_cb.isChecked():
                        previous_id = getattr(dialog, 'previous_report_id', None)
                        if previous_id:
                            try:
                                session = self.db_manager.create_session()
                                dialog._copy_all_report_data(
                                    session, previous_id, created_id
                                )
                                session.close()
                                self.status_manager.show_success(
                                    "DailyReport", "Data copied from previous report"
                                )
                            except Exception as copy_err:
                                logger.error(f"Copy error: {copy_err}")
                                self.status_manager.show_warning(
                                    "DailyReport",
                                    "Could not copy all data from previous report"
                                )

                    # به‌روزرسانی SelectionManager
                    self.sel_manager.select_report(
                        created_id,
                        {"report_id": created_id, "section_id": section_id}
                    )

                    # به‌روزرسانی درخت
                    if hasattr(self.parent_window, 'populate_hierarchy'):
                        self.parent_window.populate_hierarchy()

                    # لود گزارش جدید
                    self.load_report_by_id(created_id)

                    self.status_manager.show_success(
                        "DailyReport", "Daily report created and loaded"
                    )
                else:
                    self.status_manager.show_error(
                        "DailyReport", "Failed to create report: no ID returned"
                    )
        except Exception as e:
            logger.error(f"Error creating daily report: {e}")
            self.status_manager.show_error("DailyReport", f"Error: {str(e)}")
                

    def populate_from_report(self, source_report_id: int):
        """
        پر کردن فرم از یک گزارش منبع (بدون تغییر current_report_id)
        برای کپی کردن از روز قبل در حین ایجاد گزارش جدید
        """
        session = self.db_manager.create_session()
        try:
            source = session.query(DailyReport).filter(DailyReport.id == source_report_id).first()
            if not source:
                return False
            
            # پر کردن فیلدهای هدر (عمق‌ها، خلاصه، روز ریگ)
            self.depth_0000.setValue(source.depth_2400 or 0)
            self.depth_0600.setValue(source.depth_2400 or 0)
            self.depth_2400.setValue(source.depth_2400 or 0)  # اختیاری
            self.summary_text.setPlainText(source.summary or "")
            # روز ریگ را یک روز افزایش می‌دهیم (چون روز جدید است)
            self.rig_day.setValue((source.rig_day or 0) + 1)
            
            # کپی Time Logs
            self.time_24_table.setRowCount(0)
            logs_24 = session.query(TimeLog24H).filter(TimeLog24H.report_id == source.id).all()
            for log in logs_24:
                self.add_time_log_row(self.time_24_table, log)
            
            self.morning_table.setRowCount(0)
            logs_morning = session.query(TimeLogMorning).filter(TimeLogMorning.report_id == source.id).all()
            for log in logs_morning:
                self.add_time_log_row(self.morning_table, log)
            
            self.update_statistics()
            return True
        except Exception as e:
            logger.error(f"Error in populate_from_report: {e}")
            return False
        finally:
            session.close()

    def copy_data_from_report(self, source_report_id: int, target_report_id: int) -> bool:
        """
        کپی تمام داده‌های مرتبط با یک گزارش روزانه به گزارش دیگر.
        شامل: TimeLog24H, TimeLogMorning, DrillingParameters, MudReport,
        CementReport, CasingReport, BitReport, BHAReport, DownholeEquipment,
        FormationReport, SafetyReport, WellboreSchematic, و ...
        """
        session = self.db.create_session()
        try:
            from core.database import (
                TimeLog24H, TimeLogMorning, DrillingParameters, MudReport,
                CementReport, CasingReport, BitReport, BHAReport, DownholeEquipment,
                FormationReport, SafetyReport, WellboreSchematic,
                TripSheetEntry, SurveyPoint, LogisticsPersonnel, ServiceCompanyPOB,
                FuelWaterInventory, BulkMaterials, TransportLog, TransportNotes,
                ServiceCompany, ServiceNote, MaterialRequest, EquipmentLog,
                SevenDaysLookahead, NPTReport
            )
            import logging
            logger = logging.getLogger(__name__)

            # لیست مدل‌هایی که باید کپی شوند (به جز TimeLogها که جداگانه)
            models_to_copy = [
                (DrillingParameters, 'report_id'),
                (MudReport, 'report_id'),
                (CementReport, 'report_id'),
                (CasingReport, 'report_id'),
                (BitReport, 'report_id'),
                (BHAReport, 'report_id'),
                (DownholeEquipment, 'report_id'),
                (FormationReport, 'report_id'),
                (SafetyReport, 'report_id'),
                (WellboreSchematic, 'report_id'),
                (TripSheetEntry, 'report_id'),
                (SurveyPoint, 'report_id'),
                (LogisticsPersonnel, 'report_id'),
                (ServiceCompanyPOB, 'report_id'),
                (FuelWaterInventory, 'report_id'),
                (BulkMaterials, 'report_id'),
                (TransportLog, 'report_id'),
                (TransportNotes, 'report_id'),
                (ServiceCompany, 'report_id'),
                (ServiceNote, 'report_id'),
                (MaterialRequest, 'report_id'),
                (EquipmentLog, 'report_id'),
                (SevenDaysLookahead, 'report_id'),
                (NPTReport, 'report_id'),
            ]

            session.query(TimeLog24H).filter(TimeLog24H.report_id == target_report_id).delete()
            session.query(TimeLogMorning).filter(TimeLogMorning.report_id == target_report_id).delete()

            # فقط کپی TimeLogMorning از منبع به TimeLog24H در هدف
            logs_morning = session.query(TimeLogMorning).filter(TimeLogMorning.report_id == source_report_id).all()
            for log in logs_morning:
                new_log = TimeLog24H(   # تبدیل به 24 Hours
                    report_id=target_report_id,
                    time_from=log.time_from,
                    time_to=log.time_to,
                    duration=log.duration,
                    main_phase=log.main_phase,
                    main_code=log.main_code,
                    sub_code=log.sub_code,
                    status=log.status,
                    is_npt=log.is_npt,
                    activity_description=log.activity_description,
                    contractor=log.contractor
                )
                session.add(new_log)


            # 2. کپی سایر مدل‌ها
            for model, fk_field in models_to_copy:
                # حذف رکوردهای قبلی target (در صورت نیاز – برای جلوگیری از تکرار)
                session.query(model).filter(getattr(model, fk_field) == target_report_id).delete()
                # دریافت رکوردهای source
                source_records = session.query(model).filter(getattr(model, fk_field) == source_report_id).all()
                for rec in source_records:
                    # ایجاد دیکشنری از تمام فیلدها به جز id و report_id
                    data = {}
                    for column in model.__table__.columns:
                        if column.name not in ('id', fk_field):
                            data[column.name] = getattr(rec, column.name)
                    data[fk_field] = target_report_id
                    # ایجاد نمونه جدید
                    new_rec = model(**data)
                    session.add(new_rec)

            session.commit()
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"Error copying report data: {e}")
            return False
        finally:
            session.close() 
    # -------- متدهای کمکی برای سازگاری با سایر تب‌ها --------
    def set_current_report(self, report_id):
        """برای سازگاری با فراخوانی‌های خارجی."""
        self.load_report_by_id(report_id)

    def set_current_daily_report(self, daily_report_id):
        """برای سازگاری با سایر بخش‌ها."""
        self.current_daily_report_id = daily_report_id
        self.load_report_by_id(daily_report_id)

    def get_current_report_info(self):
        if self.current_daily_report_id:
            return {
                'id': self.current_daily_report_id,
                'report_number': self.report_number.value(),
                'report_date': self.report_date.date().toString('yyyy-MM-dd'),
                'well': self.current_well.get('name', '') if self.current_well else '',
                'section': self.current_section.get('name', '') if self.current_section else ''
            }
        return None

    def validate_tab_ownership(self):
        """اعتبارسنجی مالکیت تب‌ها با دیلی ریپورت جاری."""
        if self.current_report and self.current_well:
            rep_well_id = self.current_report.get('well_id')
            curr_well_id = self.current_well.get('id') if isinstance(self.current_well, dict) else getattr(self.current_well, 'id', None)
            if rep_well_id and curr_well_id and rep_well_id != curr_well_id:
                logger.warning(f"Report well_id ({rep_well_id}) does not match active well ({curr_well_id})")
                return False
        return True

    # -------- سایر متدهای کمکی (بدون تغییر) --------
    def update_statistics(self):
        try:
            total_time = 0.0
            total_npt = 0.0
            for row in range(self.time_24_table.rowCount()):
                duration_widget = self.time_24_table.cellWidget(row, 2)
                npt_widget = self.time_24_table.cellWidget(row, 7)
                if duration_widget and npt_widget:
                    try:
                        duration = float(duration_widget.text())
                        total_time += duration
                        if npt_widget.isChecked():
                            total_npt += duration
                    except:
                        pass
            self.total_time_label.setText(f"Total Time: {total_time:.1f}h")
            self.total_npt_label.setText(f"NPT Time: {total_npt:.1f}h")
            if total_time > 0:
                productivity = ((total_time - total_npt) / total_time) * 100
                self.productivity_label.setText(f"Productivity: {productivity:.1f}%")
                if productivity >= 90:
                    color = "#27ae60"
                elif productivity >= 70:
                    color = "#f39c12"
                else:
                    color = "#e74c3c"
                self.productivity_label.setStyleSheet(f"""
                    QLabel {{
                        background-color: {color};
                        color: white;
                        border: 1px solid {color};
                        border-radius: 4px;
                        padding: 5px 10px;
                        font-weight: bold;
                    }}
                """)
        except Exception as e:
            logger.error(f"Error updating statistics: {e}")

    def update_char_counter(self):
        text = self.summary_text.toPlainText()
        char_count = len(text)
        self.char_counter.setText(f"{char_count}/2000 characters")
        if char_count > 1900:
            self.char_counter.setStyleSheet("color: #e74c3c; font-size: 10px;")
        elif char_count > 1500:
            self.char_counter.setStyleSheet("color: #f39c12; font-size: 10px;")
        else:
            self.char_counter.setStyleSheet("color: #7f8c8d; font-size: 10px;")

    def calculate_depth_gained(self):
        depth_start = self.depth_0000.value()
        depth_end = self.depth_2400.value()
        if depth_end >= depth_start:
            gained = depth_end - depth_start
            self.status_manager.show_message("DailyReport", f"📈 Depth gained today: {gained:.2f} meters", 3000)
        else:
            self.status_manager.show_error("DailyReport", "End depth must be greater than start depth")

    def copy_previous_day(self, source_report_id=None):
        well_id = self.current_well_id
        section_id = self.current_section_id

        if not well_id or not section_id:
            self.show_error("Well or section not selected")
            return

        current_date = self.report_date.date().toPython()
        previous_date = current_date - timedelta(days=1)

        session = self.db.create_session()
        try:
            if source_report_id is None:
                prev_report = session.query(DailyReport).filter(
                    DailyReport.well_id == well_id,
                    DailyReport.section_id == section_id,
                    DailyReport.report_date == previous_date
                ).first()
            else:
                prev_report = session.query(DailyReport).filter(
                    DailyReport.id == source_report_id
                ).first()

            if not prev_report:
                self.show_message("No previous report found", 3000)
                return

            # 1. ابتدا گزارش جدید (فعلی) را ذخیره کن
            if not self.current_report_id:
                # اگر گزارش جدید هنوز ذخیره نشده، یک رکورد خالی ایجاد کن
                self.save_report()
            if not self.current_report_id:
                return

            new_report_id = self.current_report_id

            # 2. داده‌های گزارش قبلی را مستقیماً در session کپی کن (بدون load)
            self.copy_data_from_report(prev_report.id, new_report_id)

            # 3. مجدداً گزارش جدید را از دیتابیس بارگذاری کن تا داده‌های کپی شده نمایش داده شوند
            self.load_report_by_id(new_report_id)

            self.show_success(f"Copied data from Report #{prev_report.report_number}")

        except Exception as e:
            session.rollback()
            logger.error(f"Copy error: {e}")
            self.show_error(f"Copy failed: {str(e)}")
        finally:
            session.close()
            
    def new_report(self):
        """پاک کردن فرم برای گزارش جدید"""
        self.current_report = None
        self.current_report_id = None
        self.current_daily_report_id = None
        self.report_date.setDate(QDate.currentDate())
        self.report_number.setValue(1)
        self.rig_day.setValue(1)
        self.depth_0000.setValue(0)
        self.depth_0600.setValue(0)
        self.depth_2400.setValue(0)
        self.summary_text.clear()
        self.status_combo.setCurrentText("Draft")
        self.time_24_table.setRowCount(0)
        self.morning_table.setRowCount(0)
        # اضافه کردن یک ردیف خالی
        self.add_time_log_row(self.time_24_table)
        self.add_time_log_row(self.morning_table)
        self.status_manager.show_success("DailyReport", "📝 New report ready")

    def print_report(self):
        if not self.current_report:
            self.status_manager.show_error("DailyReport", "No report to print")
            return
        try:
            printer = QPrinter()
            dialog = QPrintDialog(printer, self)
            if dialog.exec():
                html = self.create_print_html()
                from PySide6.QtGui import QTextDocument
                document = QTextDocument()
                document.setHtml(html)
                document.print_(printer)
                self.status_manager.show_success("DailyReport", "🖨️ Report sent to printer")
        except Exception as e:
            logger.error(f"Error printing: {e}")
            self.status_manager.show_error("DailyReport", f"Print error: {str(e)[:100]}")

    def create_print_html(self):
        well_name = 'Unknown'
        if self.current_well:
            if isinstance(self.current_well, dict):
                well_name = self.current_well.get('name', 'Unknown')
            elif hasattr(self.current_well, 'name'):
                well_name = self.current_well.name

        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial; margin: 20px; }}
                h1 {{ color: #2c3e50; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <h1>Daily Drilling Report</h1>
            <p><strong>Well:</strong> {well_name}</p>
            <p><strong>Date:</strong> {self.report_date.date().toString('yyyy-MM-dd')}</p>
            <p><strong>Report #:</strong> {self.report_number.value()}</p>
            <p><strong>Rig Day:</strong> {self.rig_day.value()}</p>
            <p><strong>Depth @ 00:00:</strong> {self.depth_0000.value()} m</p>
            <p><strong>Depth @ 06:00:</strong> {self.depth_0600.value()} m</p>
            <p><strong>Depth @ 24:00:</strong> {self.depth_2400.value()} m</p>
            <h2>Summary</h2>
            <p>{self.summary_text.toPlainText()}</p>
        </body>
        </html>
        """
        return html

    def on_tab_changed(self, index):
        tab_names = ["24 Hours", "Morning Tour"]
        if 0 <= index < len(tab_names):
            self.status_manager.show_message("DailyReport", f"Viewing: {tab_names[index]}", 1000)

    def save_data(self):
        if not self.current_well:
            self.status_manager.show_message("DailyReportWidget", "No well selected", 2000)
            return False
        return self.save_report()

    def submit_report(self):
        if not self.current_report_id:
            self.show_warning("Select a report first")
            return False
        try:
            ok = self.db_manager.set_report_status(self.current_report_id, "Submitted")
            if ok:
                self.db_manager.create_report_revision(self.current_report_id, "Submitted")
                self.load_report_by_id(self.current_report_id)
                self.show_success("Report submitted for review")
            return bool(ok)
        except Exception as exc:
            logger.error("Submit report failed: %s", exc, exc_info=True)
            self.show_error(str(exc))
            return False

    def approve_report(self, comment=""):
        if not self.current_report_id:
            self.show_warning("Select a report first")
            return False
        try:
            ok = self.db_manager.set_report_status(self.current_report_id, "Approved", comment=comment)
            if ok:
                self.db_manager.create_report_revision(self.current_report_id, "Approved", comment)
                self.load_report_by_id(self.current_report_id)
                self.show_success("Report approved")
            return bool(ok)
        except Exception as exc:
            logger.error("Approve report failed: %s", exc, exc_info=True)
            self.show_error(str(exc))
            return False

    def reject_report(self, comment=""):
        if not self.current_report_id:
            self.show_warning("Select a report first")
            return False
        if not comment.strip():
            self.show_warning("A rejection comment is required")
            return False
        try:
            ok = self.db_manager.set_report_status(self.current_report_id, "Rejected", comment=comment)
            if ok:
                self.db_manager.create_report_revision(self.current_report_id, "Rejected", comment)
                self.load_report_by_id(self.current_report_id)
                self.show_warning("Report rejected")
            return bool(ok)
        except Exception as exc:
            logger.error("Reject report failed: %s", exc, exc_info=True)
            self.show_error(str(exc))
            return False

    def refresh(self):
        if self.current_report_id:
            self.load_report_by_id(self.current_report_id)
        self.status_manager.show_success("DailyReport", "Data refreshed")

    def _add_activity_dialog(self, table):
        """اضافه کردن فعالیت با دیالوگ حرفه‌ای"""
        from dialogs.daily_report_dialogs import AddActivityDialog

        # آخرین زمان
        prev_time = "06:00"
        if table.rowCount() > 0:
            last_row = table.rowCount() - 1
            to_widget = table.cellWidget(last_row, 1)
            if to_widget and hasattr(to_widget, 'get_display_string'):
                prev_time = to_widget.get_display_string()
            elif to_widget and hasattr(to_widget, 'get_time'):
                h, m, is24 = to_widget.get_time()
                prev_time = "24:00" if is24 else f"{h:02d}:{m:02d}"

        dlg = AddActivityDialog(self, prev_time=prev_time)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                # ساخت یک شبه‌آبجکت برای add_time_log_row
                class LogData:
                    pass
                log = LogData()
                
                # Parse time strings
                from_parts = data['time_from'].split(':')
                to_parts = data['time_to'].split(':')
                
                log.time_from = data['time_from']
                log.time_to = data['time_to']
                log.duration = data['duration']
                log.main_phase = data['main_phase']
                log.main_code = data['main_code']
                log.sub_code = data['sub_code']
                log.status = data['status']
                log.is_npt = data['is_npt']
                log.contractor = data.get('contractor', '')
                log.activity_description = data['description']

                self.add_time_log_row(table, log)
                self.update_statistics()
                self.show_message(f"Activity added: {data['main_code'][:30]}")

    def _export_ddr_pdf(self):
        """اکسپورت DDR حرفه‌ای"""
        if not self.current_report_id:
            if not self.save_report():
                return

        well_name = ""
        if self.current_well and isinstance(self.current_well, dict):
            well_name = self.current_well.get('name', 'Unknown')

        rd = self.report_date.date().toString('yyyy-MM-dd')

        filename, selected_filter = QFileDialog.getSaveFileName(
            self, "Export DDR",
            f"DDR_{well_name}_{rd}.pdf",
            "PDF (*.pdf);;HTML (*.html);;Excel (*.xlsx)"
        )
        if not filename:
            return

        try:
            from core.report_engine import DDRReportEngine

            engine = DDRReportEngine(self.db_manager)

            if "html" in selected_filter.lower():
                fmt = "html"
            elif "xlsx" in selected_filter.lower():
                fmt = "excel"
            else:
                fmt = "pdf"

            success = engine.generate(
                self.current_report_id, filename, format=fmt
            )

            if success:
                self.status_manager.show_success(
                    "DailyReport", f"DDR exported: {filename}"
                )
                if os.name == 'nt':
                    os.startfile(filename)
            else:
                self.status_manager.show_error(
                    "DailyReport", "Export failed"
                )

        except Exception as e:
            logger.error(f"DDR export error: {e}")
            self.status_manager.show_error(
                "DailyReport", f"Export error: {str(e)}"
            )
    def _export_ddr_html(self, filename):
        """Fallback: اکسپورت HTML"""
        try:
            well_name = ""
            if self.current_well and isinstance(self.current_well, dict):
                well_name = self.current_well.get('name', 'Unknown')

            html = f"""<html><head><style>
            body {{ font-family: Arial; font-size: 10pt; margin: 20px; }}
            h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; }}
            table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
            th {{ background: #2c3e50; color: white; padding: 5px; }}
            td {{ border: 1px solid #ddd; padding: 4px; }}
            </style></head><body>
            <h1>Daily Drilling Report</h1>
            <p>Well: {well_name} | Date: {self.report_date.date().toString('yyyy-MM-dd')} | 
            Report #: {self.report_number.value()} | Rig Day: {self.rig_day.value()}</p>
            <h2>Depth Summary</h2>
            <p>00:00: {self.depth_0000.value():.1f}m | 06:00: {self.depth_0600.value():.1f}m | 
            24:00: {self.depth_2400.value():.1f}m | Progress: {self.depth_2400.value() - self.depth_0000.value():.1f}m</p>
            <h2>Operations</h2>
            <table><tr><th>From</th><th>To</th><th>Hrs</th><th>Phase</th><th>Code</th><th>NPT</th><th>Description</th></tr>
            """

            for row in range(self.time_24_table.rowCount()):
                from_w = self.time_24_table.cellWidget(row, 0)
                to_w = self.time_24_table.cellWidget(row, 1)
                dur_w = self.time_24_table.cellWidget(row, 2)
                phase_w = self.time_24_table.cellWidget(row, 3)
                npt_w = self.time_24_table.cellWidget(row, 7)
                desc_w = self.time_24_table.cellWidget(row, 9)

                time_from = from_w.get_display_string() if from_w and hasattr(from_w, 'get_display_string') else ""
                time_to = to_w.get_display_string() if to_w and hasattr(to_w, 'get_display_string') else ""
                duration = dur_w.text() if dur_w and isinstance(dur_w, QLabel) else ""
                phase = phase_w.currentText() if phase_w and isinstance(phase_w, QComboBox) else ""
                is_npt = npt_w.isChecked() if npt_w and isinstance(npt_w, QCheckBox) else False
                desc = desc_w.toPlainText() if desc_w and hasattr(desc_w, 'toPlainText') else ""

                npt_style = "background: #fadbd8;" if is_npt else ""
                html += f'<tr style="{npt_style}"><td>{time_from}</td><td>{time_to}</td>'
                html += f'<td>{duration}</td><td>{phase}</td><td></td>'
                html += f'<td>{"⚠️" if is_npt else ""}</td><td>{desc}</td></tr>'

            html += f"""</table>
            <h2>Summary</h2>
            <p>{self.summary_text.toPlainText()}</p>
            <hr><p style="color:#999; font-size:8pt;">Generated by DrillMaster</p>
            </body></html>"""

            with open(filename, 'w', encoding='utf-8') as f:
                f.write(html)

            self.status_manager.show_success("DailyReport", f"HTML exported: {filename}")
            import os
            if os.name == 'nt':
                os.startfile(filename)

        except Exception as e:
            logger.error(f"HTML export error: {e}")