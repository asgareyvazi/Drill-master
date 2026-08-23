"""
Well Information Tab - UI and Database (Final Improved Version)
"""
import logging
from datetime import datetime

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

# Import utilities
try:
    from ui.utils import create_styled_button, show_success_message, show_error_message
except ImportError:
    def create_styled_button(text, color="#0078d4", icon=None, tooltip=""):
        btn = QPushButton(text)
        if tooltip:
            btn.setToolTip(tooltip)
        return btn

    def show_success_message(parent, message):
        QMessageBox.information(parent, "Success", message)

    def show_error_message(parent, message):
        QMessageBox.critical(parent, "Error", message)

from core.base_tab import DrillTabBase

logger = logging.getLogger(__name__)


class WellInfoTab(DrillTabBase):
    """Well Information Tab"""

    # Signals
    data_saved = Signal()
    well_deleted = Signal()
    data_changed = Signal()

    def __init__(self, db_manager, main_window):
        super().__init__("WellInfoTab", db_manager, parent=main_window)
        self.main_window = main_window
        self.current_well = None
        self.is_loading = False

        self.init_ui()
        self.setup_connections()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)

        # Well Type
        well_type_group = QGroupBox("Well Type")
        type_layout = QHBoxLayout()
        self.well_type_onshore = QRadioButton("Onshore")
        self.well_type_offshore = QRadioButton("Offshore")
        self.well_type_onshore.setChecked(True)
        type_layout.addWidget(self.well_type_onshore)
        type_layout.addWidget(self.well_type_offshore)
        well_type_group.setLayout(type_layout)
        layout.addWidget(well_type_group)

        # Basic Information Form
        form_group = QGroupBox("Basic Information")
        form_layout = QFormLayout()

        # ---- ردیف Well Name و Well Code ----
        name_code_layout = QHBoxLayout()
        name_code_layout.addWidget(QLabel("Well Name:"))
        self.well_name = QLineEdit()
        self.well_name.setPlaceholderText("Well Name")
        name_code_layout.addWidget(self.well_name)
        name_code_layout.addWidget(QLabel("Well Code:"))
        self.well_code = QLineEdit()
        self.well_code.setPlaceholderText("Unique code (e.g., XYZ-01)")
        self.well_code.setReadOnly(True)  # برای چاه‌های موجود فقط نمایشی
        name_code_layout.addWidget(self.well_code)
        form_layout.addRow(name_code_layout)

        # Project (نمایشی)
        project_layout = QHBoxLayout()
        project_layout.addWidget(QLabel("Project:"))
        self.project_label = QLabel("N/A")
        project_layout.addWidget(self.project_label)
        project_layout.addStretch()
        form_layout.addRow(project_layout)

        # Section (ComboBox )
        section_layout = QHBoxLayout()
        section_layout.addWidget(QLabel("Section:"))
        self.section_name = QComboBox()
        self.section_name.setEditable(True)  # قابل ویرایش برای اضافه کردن جدید
        self.section_name.setInsertPolicy(QComboBox.NoInsert)
        self.section_name.setMinimumWidth(200)

        # دکمه Add New Section
        self.add_section_btn = QPushButton("➕")
        self.add_section_btn.setFixedSize(30, 30)
        self.add_section_btn.setToolTip("Add New Section")
        self.add_section_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                border-radius: 15px;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
        """)
        self.add_section_btn.clicked.connect(self.add_new_section)

        section_layout.addWidget(self.section_name, 1)
        section_layout.addWidget(self.add_section_btn)
        section_layout.addStretch()
        form_layout.addRow(section_layout)


        # Row 1 - Client & Client Rep
        row1_layout = QHBoxLayout()
        self.client = QLineEdit()
        self.client.setPlaceholderText("Client")
        self.client_rep = QLineEdit()
        self.client_rep.setPlaceholderText("Client Representative")
        row1_layout.addWidget(QLabel("Client:"))
        row1_layout.addWidget(self.client)
        row1_layout.addWidget(QLabel("Client Rep:"))
        row1_layout.addWidget(self.client_rep)
        form_layout.addRow(row1_layout)

        # Row 2 - Operator
        row2_layout = QHBoxLayout()
        self.operator = QLineEdit()
        self.operator.setPlaceholderText("Operator")
        row2_layout.addWidget(QLabel("Operator:"))
        row2_layout.addWidget(self.operator)
        row2_layout.addStretch()
        form_layout.addRow(row2_layout)

        # Row 3 - Rig Name & Drilling Contractor
        row3_layout = QHBoxLayout()
        self.rig_name = QLineEdit()
        self.rig_name.setPlaceholderText("Rig Name")
        self.drilling_contractor = QLineEdit()
        self.drilling_contractor.setPlaceholderText("Drilling Contractor")
        row3_layout.addWidget(QLabel("Rig Name:"))
        row3_layout.addWidget(self.rig_name)
        row3_layout.addWidget(QLabel("Contractor:"))
        row3_layout.addWidget(self.drilling_contractor)
        form_layout.addRow(row3_layout)

        # Row 4 - Report No
        row4_layout = QHBoxLayout()
        self.report_no = QLineEdit()
        self.report_no.setPlaceholderText("Report No.")
        row4_layout.addWidget(QLabel("Report No:"))
        row4_layout.addWidget(self.report_no)
        row4_layout.addStretch()
        form_layout.addRow(row4_layout)

        # Rig Type and Well Shape
        row5_layout = QHBoxLayout()
        self.rig_type = QComboBox()
        self.rig_type.addItems(["Land", "Jackup", "SemiSub", "Platform", "Barge", "Other"])
        self.well_shape = QComboBox()
        self.well_shape.addItems(["Vertical", "Deviated", "Horizontal", "J-Shape", "S-Shape"])
        row5_layout.addWidget(QLabel("Rig Type:"))
        row5_layout.addWidget(self.rig_type)
        row5_layout.addWidget(QLabel("Well Shape:"))
        row5_layout.addWidget(self.well_shape)
        form_layout.addRow(row5_layout)

        form_group.setLayout(form_layout)
        layout.addWidget(form_group)

        # Depths and Measurements 
        depths_group = QGroupBox("Depths & Measurements")
        depths_layout = QGridLayout()

        # ردیف 0: GLE-MSL و RTE-MSL
        depths_layout.addWidget(QLabel("GLE-MSL (m):"), 0, 0)
        self.gle_msl = QDoubleSpinBox()
        self.gle_msl.setRange(-10000, 10000)
        self.gle_msl.setSuffix(" m")
        depths_layout.addWidget(self.gle_msl, 0, 1)

        depths_layout.addWidget(QLabel("RTE-MSL (m):"), 0, 2)
        self.rte_msl = QDoubleSpinBox()
        self.rte_msl.setRange(-10000, 10000)
        self.rte_msl.setSuffix(" m")
        depths_layout.addWidget(self.rte_msl, 0, 3)

        # ردیف 1: GLE-RTE و Estimated Final Depth
        depths_layout.addWidget(QLabel("GLE-RTE (m):"), 1, 0)
        self.gle_rte = QDoubleSpinBox()
        self.gle_rte.setRange(-1000, 1000)
        self.gle_rte.setSuffix(" m")
        depths_layout.addWidget(self.gle_rte, 1, 1)

        depths_layout.addWidget(QLabel("Est. Final Depth MD (m):"), 1, 2)
        self.estimated_depth = QDoubleSpinBox()
        self.estimated_depth.setRange(0, 10000)
        self.estimated_depth.setSuffix(" m")
        depths_layout.addWidget(self.estimated_depth, 1, 3)

        # ردیف 2: Derrick Height و Water Depth
        depths_layout.addWidget(QLabel("Derrick Height:"), 2, 0)
        self.derrick_height = QSpinBox()
        self.derrick_height.setRange(0, 300)
        self.derrick_height.setSuffix(" ft")
        depths_layout.addWidget(self.derrick_height, 2, 1)

        depths_layout.addWidget(QLabel("Water Depth (m):"), 2, 2)
        self.water_depth = QDoubleSpinBox()
        self.water_depth.setRange(0, 5000)
        self.water_depth.setSuffix(" m")
        depths_layout.addWidget(self.water_depth, 2, 3)

        # ردیف 3: LTA (Day) و Actual Rig Days
        depths_layout.addWidget(QLabel("LTA (Day):"), 3, 0)
        self.lta_day = QSpinBox()
        self.lta_day.setRange(0, 365)
        depths_layout.addWidget(self.lta_day, 3, 1)

        depths_layout.addWidget(QLabel("Actual Rig Days:"), 3, 2)
        self.actual_rig_days = QSpinBox()
        self.actual_rig_days.setRange(0, 365)
        depths_layout.addWidget(self.actual_rig_days, 3, 3)

        # ردیف 4: Rig Heading و KOP #1
        depths_layout.addWidget(QLabel("Rig Heading (°):"), 4, 0)
        self.rig_heading = QDoubleSpinBox()
        self.rig_heading.setRange(0, 360)
        self.rig_heading.setSuffix(" °")
        depths_layout.addWidget(self.rig_heading, 4, 1)

        depths_layout.addWidget(QLabel("KOP #1:"), 4, 2)
        self.kop1 = QDoubleSpinBox()
        self.kop1.setRange(0, 10000)
        self.kop1.setSuffix(" m")
        depths_layout.addWidget(self.kop1, 4, 3)

        # ردیف 5: KOP #2 و Formation
        depths_layout.addWidget(QLabel("KOP #2:"), 5, 0)
        self.kop2 = QDoubleSpinBox()
        self.kop2.setRange(0, 10000)
        self.kop2.setSuffix(" m")
        depths_layout.addWidget(self.kop2, 5, 1)

        depths_layout.addWidget(QLabel("Formation:"), 5, 2)
        self.formation = QLineEdit()
        depths_layout.addWidget(self.formation, 5, 3)

        depths_group.setLayout(depths_layout)
        layout.addWidget(depths_group)

        # Coordinates
        coords_group = QGroupBox("Coordinates")
        coords_layout = QGridLayout()
        coords_layout.addWidget(QLabel("Latitude:"), 0, 0)
        self.latitude = QDoubleSpinBox()
        self.latitude.setRange(-90, 90)
        self.latitude.setDecimals(6)
        coords_layout.addWidget(self.latitude, 0, 1)
        coords_layout.addWidget(QLabel("Longitude:"), 0, 2)
        self.longitude = QDoubleSpinBox()
        self.longitude.setRange(-180, 180)
        self.longitude.setDecimals(6)
        coords_layout.addWidget(self.longitude, 0, 3)
        coords_layout.addWidget(QLabel("Northing (m):"), 1, 0)
        self.northing = QDoubleSpinBox()
        self.northing.setRange(-1000000, 1000000)
        coords_layout.addWidget(self.northing, 1, 1)
        coords_layout.addWidget(QLabel("Easting (m):"), 1, 2)
        self.easting = QDoubleSpinBox()
        self.easting.setRange(-1000000, 1000000)
        coords_layout.addWidget(self.easting, 1, 3)
        coords_group.setLayout(coords_layout)
        layout.addWidget(coords_group)

        # Dates
        dates_group = QGroupBox("Dates")
        dates_layout = QGridLayout()
        dates_layout.addWidget(QLabel("Spud Date:"), 0, 0)
        self.spud_date = QDateEdit()
        self.spud_date.setCalendarPopup(True)
        self.spud_date.setDate(QDate.currentDate())
        dates_layout.addWidget(self.spud_date, 0, 1)
        dates_layout.addWidget(QLabel("Start Hole Date:"), 0, 2)
        self.start_hole_date = QDateEdit()
        self.start_hole_date.setCalendarPopup(True)
        self.start_hole_date.setDate(QDate.currentDate())
        dates_layout.addWidget(self.start_hole_date, 0, 3)
        dates_layout.addWidget(QLabel("Rig Move Date:"), 1, 0)
        self.rig_move_date = QDateEdit()
        self.rig_move_date.setCalendarPopup(True)
        self.rig_move_date.setDate(QDate.currentDate())
        dates_layout.addWidget(self.rig_move_date, 1, 1)
        dates_layout.addWidget(QLabel("Report Date:"), 1, 2)
        self.report_date = QDateEdit()
        self.report_date.setCalendarPopup(True)
        self.report_date.setDate(QDate.currentDate())
        dates_layout.addWidget(self.report_date, 1, 3)
        dates_group.setLayout(dates_layout)
        layout.addWidget(dates_group)

        # Personnel
        personnel_group = QGroupBox("Personnel")
        personnel_layout = QGridLayout()
        personnel_layout.addWidget(QLabel("Operation Manager:"), 0, 0)
        self.operation_manager = QLineEdit()
        personnel_layout.addWidget(self.operation_manager, 0, 1)
        personnel_layout.addWidget(QLabel("Superintendent:"), 0, 2)
        self.superintendent = QLineEdit()
        personnel_layout.addWidget(self.superintendent, 0, 3)
        personnel_layout.addWidget(QLabel("Supervisor (Day):"), 1, 0)
        self.supervisor_day = QLineEdit()
        personnel_layout.addWidget(self.supervisor_day, 1, 1)
        personnel_layout.addWidget(QLabel("Supervisor (Night):"), 1, 2)
        self.supervisor_night = QLineEdit()
        personnel_layout.addWidget(self.supervisor_night, 1, 3)
        personnel_layout.addWidget(QLabel("Geologist 1:"), 2, 0)
        self.geologist1 = QLineEdit()
        personnel_layout.addWidget(self.geologist1, 2, 1)
        personnel_layout.addWidget(QLabel("Geologist 2:"), 2, 2)
        self.geologist2 = QLineEdit()
        personnel_layout.addWidget(self.geologist2, 2, 3)
        personnel_layout.addWidget(QLabel("Tool Pusher (Day):"), 3, 0)
        self.tool_pusher_day = QLineEdit()
        personnel_layout.addWidget(self.tool_pusher_day, 3, 1)
        personnel_layout.addWidget(QLabel("Tool Pusher (Night):"), 3, 2)
        self.tool_pusher_night = QLineEdit()
        personnel_layout.addWidget(self.tool_pusher_night, 3, 3)
        personnel_group.setLayout(personnel_layout)
        layout.addWidget(personnel_group)

        # Objectives
        objectives_group = QGroupBox("Objectives")
        objectives_layout = QVBoxLayout()
        self.objectives = QTextEdit()
        self.objectives.setMaximumHeight(150)
        objectives_layout.addWidget(self.objectives)
        objectives_group.setLayout(objectives_layout)
        layout.addWidget(objectives_group)

        # Buttons
        button_layout = QHBoxLayout()
        self.new_well_btn = create_styled_button("🆕 New Well", color="#17a2b8")
        self.save_btn = create_styled_button("💾 Save Well Info", color="#28a745")
        self.load_btn = create_styled_button("📂 Load Well", color="#007bff")
        self.clear_btn = create_styled_button("🗑️ Clear", color="#6c757d")
        self.delete_btn = create_styled_button("🗑️ Delete Well", color="#dc3545")
        self.plan_btn = create_styled_button("📋 Well Plan", color="#9b59b6")
        self.plan_btn.clicked.connect(self.open_well_plan)

        button_layout.addWidget(self.new_well_btn)
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.load_btn)
        button_layout.addWidget(self.clear_btn)
        button_layout.addWidget(self.delete_btn)
        button_layout.addWidget(self.plan_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        container.setLayout(layout)
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def open_well_plan(self):
        """باز کردن دیالوگ برنامه حفاری برای چاه جاری"""
        if not self.current_well:
            QMessageBox.warning(self, "No Well", "Please load a well first.")
            return
        
        well_id = self.current_well['id'] if isinstance(self.current_well, dict) else self.current_well.id
        try:
            from dialogs.planning_dialog import WellPlanDialog
            dialog = WellPlanDialog(self.db, well_id, self)
            if dialog.exec():
                self.status_manager.show_success("WellInfoTab", "Well plan saved successfully!")
        except Exception as e:
            logger.error(f"Error opening planning dialog: {e}")
            if self.parent and hasattr(self.parent, 'tab_widget'):
                for i in range(self.parent.tab_widget.count()):
                    if "Planning" in self.parent.tab_widget.tabText(i):
                        self.parent.tab_widget.setCurrentIndex(i)
                        self.status_manager.show_success("WellInfoTab", "Switched to Planning tab")
                        return
            QMessageBox.information(self, "Planning", "Please use the 'Planning' tab to manage well plans.")
            
    def setup_connections(self):
        # Buttons
        self.new_well_btn.clicked.connect(self.create_new_well_dialog)
        self.save_btn.clicked.connect(lambda: self.save_data(show_popup=True))
        self.load_btn.clicked.connect(self.load_well_dialog)
        self.delete_btn.clicked.connect(self.delete_well)
        self.clear_btn.clicked.connect(self.clear_form_fields)
        
        self.section_name.currentTextChanged.connect(lambda text: self.on_section_changed(text))
        self.rig_type.currentTextChanged.connect(self.on_data_changed)
        self.well_shape.currentTextChanged.connect(self.on_data_changed)

        self.well_type_onshore.toggled.connect(self.on_data_changed)
        self.well_type_offshore.toggled.connect(self.on_data_changed)

        # Text fields
        text_fields = [
            self.well_code, self.client, self.client_rep, self.operator,
            self.well_name, self.rig_name, self.drilling_contractor,
            self.report_no, self.formation, self.operation_manager,
            self.superintendent, self.supervisor_day, self.supervisor_night,
            self.geologist1, self.geologist2, self.tool_pusher_day,
            self.tool_pusher_night
        ]
        for field in text_fields:
            field.textChanged.connect(self.on_data_changed)

        # Spin boxes
        spin_boxes = [
            self.gle_msl, self.rte_msl, self.gle_rte, self.estimated_depth,
            self.water_depth, self.derrick_height, self.lta_day, self.actual_rig_days,
            self.rig_heading, self.kop1, self.kop2, self.latitude, self.longitude,
            self.northing, self.easting
        ]
        for spin in spin_boxes:
            spin.valueChanged.connect(self.on_data_changed)

        # Dates
        self.spud_date.dateChanged.connect(self.on_data_changed)
        self.start_hole_date.dateChanged.connect(self.on_data_changed)
        self.rig_move_date.dateChanged.connect(self.on_data_changed)
        self.report_date.dateChanged.connect(self.on_data_changed)
        self.objectives.textChanged.connect(self.on_data_changed)
    
    def add_new_section(self):
        """Open dialog to create new section"""
        if not self.current_well:
            QMessageBox.warning(self, "No Well", "Please save the well first before adding sections.")
            return
        
        well_id = self.current_well['id'] if isinstance(self.current_well, dict) else self.current_well.id
        
        from dialogs.hierarchy_dialogs import NewSectionDialog
        dialog = NewSectionDialog(self.db, self, well_id)
        
        result = dialog.exec()
        
        logger.info(f"Dialog exec result: {result}, created_id: {dialog.created_id}")
        
        if result == QDialog.Accepted:
            # بارگذاری مجدد سکشن‌ها
            self.load_sections_for_well(well_id)
            
            # انتخاب سکشن جدید در کامبو
            if hasattr(dialog, 'created_id') and dialog.created_id:
                self.select_section_by_id(dialog.created_id)
                section_name = self.section_name.currentText()
                QMessageBox.information(
                    self, 
                    "Success", 
                    f"Section '{section_name}' created successfully!"
                )
            else:
                QMessageBox.warning(self, "Warning", "Section created but ID not found.")
        else:
            logger.info("Dialog was cancelled or rejected")
                
    def on_section_changed(self, *args):
        """
        ✅ FIX: هر دو منبع را handle می‌کند:
        1. DrillTabBase → SelectionManager: (section_id: int, section_data: dict)
        2. QComboBox.currentTextChanged: (text: str)
        """
        if self.is_loading:
            return

        # تشخیص نوع آرگومان
        if len(args) == 2:
            # از SelectionManager آمده: (section_id, section_data)
            section_id, section_data = args
            if section_data and isinstance(section_data, dict):
                section_name = section_data.get('name', '')
                if section_name:
                    self.section_name.blockSignals(True)
                    idx = self.section_name.findText(section_name, Qt.MatchContains)
                    if idx >= 0:
                        self.section_name.setCurrentIndex(idx)
                    self.section_name.blockSignals(False)
        elif len(args) == 1:
            pass

        self.data_changed.emit()
        
    def load_data(self):
        """Load well data into form, including all fields."""
        if not self.current_well:
            return
        try:
            self.is_loading = True
            well_id = self.current_well['id'] if isinstance(self.current_well, dict) else self.current_well.id
            well_data = self.db.get_well_by_id(well_id)
            if not well_data:
                logger.warning("Well data not found")
                return

            # ========== PROJECT NAME ==========
            if 'project_id' in well_data and well_data['project_id']:
                session = self.db.create_session()
                try:
                    from core.database import Project
                    project = session.query(Project).filter(Project.id == well_data['project_id']).first()
                    self.project_label.setText(project.name if project else "Unknown Project")
                finally:
                    session.close()
            else:
                self.project_label.setText("N/A")
            
            # ========== LOAD SECTIONS (یک بار) ==========
            self.load_sections_for_well(well_id)
            
            # ========== BASIC INFO ==========
            self.well_name.setText(well_data.get('name', ''))
            self.well_code.setText(well_data.get('code', ''))
            self.well_code.setReadOnly(True)

            # ========== WELL TYPE ==========
            well_type = well_data.get('well_type', 'Onshore')
            self.well_type_onshore.setChecked(well_type == 'Onshore')
            self.well_type_offshore.setChecked(well_type != 'Onshore')

            # ========== SELECT SECTION (بعد از بارگذاری) ==========
            if 'section_name' in well_data and well_data['section_name']:
                idx = self.section_name.findText(well_data['section_name'])
                if idx >= 0:
                    self.section_name.setCurrentIndex(idx)
                else:
                    self.section_name.setCurrentText(well_data['section_name'])
            else:
                self.section_name.setCurrentIndex(0)

            # ========== TEXT FIELDS ==========
            field_map = {
                'client': self.client,
                'client_rep': self.client_rep,
                'operator': self.operator,
                'rig_name': self.rig_name,
                'drilling_contractor': self.drilling_contractor,
                'report_no': self.report_no,
                'formation': self.formation,
                'operation_manager': self.operation_manager,
                'superintendent': self.superintendent,
                'supervisor_day': self.supervisor_day,
                'supervisor_night': self.supervisor_night,
                'geologist1': self.geologist1,
                'geologist2': self.geologist2,
                'tool_pusher_day': self.tool_pusher_day,
                'tool_pusher_night': self.tool_pusher_night,
            }
            for field_name, widget in field_map.items():
                widget.setText(str(well_data.get(field_name, '') or ''))

            # ========== COMBO BOXES ==========
            self._set_combo_by_text(self.rig_type, well_data.get('rig_type'))
            self._set_combo_by_text(self.well_shape, well_data.get('well_shape'))

            # ========== SPIN BOXES ==========
            spin_map = {
                'gle_msl': self.gle_msl,
                'rte_msl': self.rte_msl,
                'gle_rte': self.gle_rte,
                'target_depth': self.estimated_depth,
                'estimated_final_depth': self.estimated_depth, 
                'water_depth': self.water_depth,
                'derrick_height': self.derrick_height,
                'lta_day': self.lta_day,
                'actual_rig_days': self.actual_rig_days,
                'rig_heading': self.rig_heading,
                'kop1': self.kop1,
                'kop2': self.kop2,
                'latitude': self.latitude,
                'longitude': self.longitude,
                'northing': self.northing,
                'easting': self.easting,
            }
            for field_name, spin in spin_map.items():
                value = well_data.get(field_name)
                if value is not None:
                    spin.setValue(float(value))

            # ========== DATE FIELDS ==========
            date_fields = {
                'spud_date': self.spud_date,
                'start_hole_date': self.start_hole_date,
                'rig_move_date': self.rig_move_date,
                'report_date': self.report_date,
            }
            for field_name, date_edit in date_fields.items():
                val = well_data.get(field_name)
                if val:
                    try:
                        if isinstance(val, str):
                            dt = datetime.strptime(val, "%Y-%m-%d").date()
                        else:
                            dt = val
                        date_edit.setDate(QDate(dt.year, dt.month, dt.day))
                    except Exception:
                        date_edit.setDate(QDate.currentDate())
                else:
                    date_edit.setDate(QDate.currentDate())

            # ========== OBJECTIVES ==========
            self.objectives.setPlainText(well_data.get('objectives') or '')

            logger.info(f"Well data loaded successfully for well ID: {well_id}")
            
        except Exception as e:
            logger.error(f"Failed to load well data: {str(e)}")
        finally:
            self.is_loading = False

    def load_sections_for_well(self, well_id):
        """Load sections for a well into combo box (یک بار اجرا شود)"""
        self.section_name.blockSignals(True)
        self.section_name.clear()
        self.section_name.addItem("")  # آیتم خالی
        
        sections = self.db.get_sections_by_well(well_id)
        for section in sections:
            display = section['name']
            if section.get('code'):
                display += f" ({section['code']})"
            self.section_name.addItem(display, section['id'])
        
        self.section_name.blockSignals(False)
        logger.debug(f"Loaded {len(sections)} sections for well {well_id}")

    def select_section_by_id(self, section_id):
        """Select section in combo box by ID"""
        for i in range(self.section_name.count()):
            if self.section_name.itemData(i) == section_id:
                self.section_name.setCurrentIndex(i)
                break
                
    def on_data_changed(self):
        if not self.is_loading:
            self.data_changed.emit()
   
                
    # ========== Data Loading & Saving ==========
    def _set_combo_by_text(self, combo: QComboBox, text: str):
        """Set combo box value by text, safely"""
        if text:
            idx = combo.findText(str(text))
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setCurrentIndex(0)

    def get_form_data(self):
        well_type = "Onshore" if self.well_type_onshore.isChecked() else "Offshore"
        coord = f"{self.latitude.value()}, {self.longitude.value()}"

        return {
            "name": self.well_name.text().strip(),
            "code": self.well_code.text().strip(),
            "section_name": self.section_name.currentText().strip(),
            "section_id": self.section_name.currentData(),
            "well_type": well_type,
            "client": self.client.text().strip(),
            "client_rep": self.client_rep.text().strip(),
            "operator": self.operator.text().strip(),
            "rig_name": self.rig_name.text().strip(),
            "drilling_contractor": self.drilling_contractor.text().strip(),
            "report_no": self.report_no.text().strip(),
            "rig_type": self.rig_type.currentText(),
            "well_shape": self.well_shape.currentText(),
            "gle_msl": self.gle_msl.value(),
            "rte_msl": self.rte_msl.value(),
            "gle_rte": self.gle_rte.value(),
            "target_depth": self.estimated_depth.value(),
            "estimated_final_depth": self.estimated_depth.value(),
            "water_depth": self.water_depth.value(),
            "derrick_height": self.derrick_height.value(),
            "lta_day": self.lta_day.value(),
            "actual_rig_days": self.actual_rig_days.value(),
            "rig_heading": self.rig_heading.value(),
            "kop1": self.kop1.value(),
            "kop2": self.kop2.value(),
            "formation": self.formation.text().strip(),
            "coordinates": coord,
            "latitude": self.latitude.value(),
            "longitude": self.longitude.value(),
            "northing": self.northing.value(),
            "easting": self.easting.value(),
            "spud_date": self.spud_date.date().toString("yyyy-MM-dd"),
            "start_hole_date": self.start_hole_date.date().toString("yyyy-MM-dd"),
            "rig_move_date": self.rig_move_date.date().toString("yyyy-MM-dd"),
            "report_date": self.report_date.date().toString("yyyy-MM-dd"),
            "operation_manager": self.operation_manager.text().strip(),
            "superintendent": self.superintendent.text().strip(),
            "supervisor_day": self.supervisor_day.text().strip(),
            "supervisor_night": self.supervisor_night.text().strip(),
            "geologist1": self.geologist1.text().strip(),
            "geologist2": self.geologist2.text().strip(),
            "tool_pusher_day": self.tool_pusher_day.text().strip(),
            "tool_pusher_night": self.tool_pusher_night.text().strip(),
            "objectives": self.objectives.toPlainText().strip(),
        }
        
    def save_data(self, show_popup=False):
        try:
            well_data = self.get_form_data()
            from core.validators import WellValidator
            validation = WellValidator.validate(well_data)
            if not validation.is_valid:
                if show_popup:
                    show_error_message(self, validation.summary())
                return False
            if validation.warnings and show_popup:
                show_warning_message(self, validation.summary())

            if self.spud_date.date() > self.start_hole_date.date():
                if show_popup:
                    show_error_message(self, "Spud Date cannot be after Start Hole Date!")
                return False

            if self.current_well:
                well_data['id'] = self.current_well['id'] if isinstance(self.current_well, dict) else self.current_well.id

            if self.db.save_well(well_data):
                # اگر well_id نداریم (Well جدید است)، ID را بگیریم
                if not well_data.get('id'):
                    session = self.db.create_session()
                    try:
                        from core.database import Well
                        saved = session.query(Well).filter_by(name=well_data['name'], code=well_data['code']).first()
                        if saved:
                            well_data['id'] = saved.id
                            self.current_well = {'id': saved.id, 'name': saved.name}
                    finally:
                        session.close()
                
                # ========== REFRESH HIERARCHY ==========
                if self.main_window:
                    self.main_window.populate_hierarchy()
                    # Select the newly saved/updated well
                    if well_data.get('id'):
                        # استفاده از QTimer برای اجرای بعد از تکمیل refresh
                        QTimer.singleShot(100, lambda: self.main_window.select_item_in_tree("well", well_data['id']))
                
                if show_popup:
                    show_success_message(self, "Well information saved successfully!")
                
                self.data_saved.emit()

                # اطلاع به SelectionManager
                if self.main_window and well_data.get('id'):
                    self.main_window.sel_manager.select_well(well_data['id'], well_data)
                
                return True
            else:
                if show_popup:
                    show_error_message(self, "Failed to save well information!")
                return False
        except Exception as e:
            logger.error(f"Failed to save well: {str(e)}")
            if show_popup:
                show_error_message(self, f"Error: {str(e)}")
            return False
        
    def on_well_changed(self, well_id, well_data):
        """Called externally when well selection changes."""
        if well_id and well_id != (self.current_well.get('id') if self.current_well else None):
            self.load_well_by_id(well_id)

    def load_well_by_id(self, well_id):
        try:
            well_data = self.db.get_well_by_id(well_id)
            if well_data:
                self.current_well = well_data
                self.load_data()
                if self.main_window:
                    self.main_window.sel_manager.select_well(well_id, well_data)
                return True
            return False
        except Exception as e:
            logger.error(f"Error loading well {well_id}: {e}")
            return False

    def create_new_well_dialog(self):
        from dialogs.hierarchy_dialogs import NewWellDialog
        dialog = NewWellDialog(self.db, self)
        if dialog.exec() and dialog.created_id:
            self.load_well_by_id(dialog.created_id)

    def load_well_dialog(self):
        try:
            hierarchy = self.db.get_hierarchy()
            if not hierarchy:
                show_error_message(self, "No wells found in database.")
                return
            dialog = QDialog(self)
            dialog.setWindowTitle("📂 Select Well")
            dialog.setFixedSize(500, 400)
            layout = QVBoxLayout()
            layout.addWidget(QLabel("Select a well to load:"))
            list_widget = QListWidget()
            for company in hierarchy:
                for project in company.get('projects', []):
                    for well in project.get('wells', []):
                        display = f"{well['name']}"
                        if well.get('code'):
                            display += f" ({well['code']})"
                        if project.get('name'):
                            display += f" - {project['name']}"
                        item = QListWidgetItem(display)
                        item.setData(Qt.UserRole, well['id'])
                        list_widget.addItem(item)
            layout.addWidget(list_widget)
            button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)
            layout.addWidget(button_box)
            dialog.setLayout(layout)
            if dialog.exec():
                selected = list_widget.selectedItems()
                if selected:
                    well_id = selected[0].data(Qt.UserRole)
                    self.load_well_by_id(well_id)
        except Exception as e:
            logger.error(f"Error loading well dialog: {e}")
            show_error_message(self, f"Error: {str(e)}")

    def delete_well(self):
        if not self.current_well:
            return
        well_name = self.current_well.get('name', 'Unknown') if isinstance(self.current_well, dict) else getattr(self.current_well, 'name', 'Unknown')
        reply = QMessageBox.question(self, "Delete Well",
                                     f"Are you sure you want to delete well '{well_name}'?\nThis cannot be undone.",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.No:
            return
        well_id = self.current_well['id'] if isinstance(self.current_well, dict) else self.current_well.id
        if self.db.delete_well(well_id):
            if self.main_window:
                self.main_window.clear_current_well()
            self.clear_form_fields()
            self.current_well = None
            self.well_deleted.emit()
        else:
            QMessageBox.warning(self, "Error", "Failed to delete well!")

    def clear_form_fields(self):
        self.is_loading = True
        self.well_type_onshore.setChecked(True)
        self.well_name.clear()
        self.well_code.clear()
        self.well_code.setReadOnly(False)
        self.project_label.setText("N/A")
        self.section_name.clear()
        self.section_name.addItem("")
        self.section_name.setCurrentIndex(0)
        self.client.clear()
        self.client_rep.clear()
        self.operator.clear()
        self.rig_name.clear()
        self.drilling_contractor.clear()
        self.report_no.clear()
        self.formation.clear()
        self.rig_type.setCurrentIndex(0)
        self.well_shape.setCurrentIndex(0)
        for spin in [self.gle_msl, self.rte_msl, self.gle_rte, self.estimated_depth,
                     self.water_depth, self.derrick_height, self.lta_day, self.actual_rig_days,
                     self.rig_heading, self.kop1, self.kop2, self.latitude, self.longitude,
                     self.northing, self.easting]:
            spin.setValue(0)
        now = QDate.currentDate()
        self.spud_date.setDate(now)
        self.start_hole_date.setDate(now)
        self.rig_move_date.setDate(now)
        self.report_date.setDate(now)
        for field in [self.operation_manager, self.superintendent, self.supervisor_day,
                      self.supervisor_night, self.geologist1, self.geologist2,
                      self.tool_pusher_day, self.tool_pusher_night]:
            field.clear()
        self.objectives.clear()
        self.is_loading = False

    def refresh(self):
        if self.current_well:
            self.load_data()

    def cleanup(self):
        self.clear_form_fields()