# tabs/w14_Procedure_Widget.py
"""
DWI / Operational Procedure Module
ماژول پروسیجرهای عملیاتی - فاز B
"""
import logging
import json
from datetime import datetime, date

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtPrintSupport import QPrinter, QPrintDialog

from core.base_tab import DrillTabBase
from core.database import DatabaseManager
from core.managers import StatusBarManager, ExportManager

logger = logging.getLogger(__name__)


# ==================== Procedure Types ====================
PROCEDURE_TYPES = {
    "liner_running": "🔩 Liner Running & Installation",
    "casing_running": "🛢️ Casing Running",
    "cementing": "🏗️ Primary Cementing",
    "bop_test": "🛡️ BOP Test",
    "well_kill": "⚠️ Well Kill",
    "tripping": "🔄 Tripping",
    "workover": "🔧 Workover",
    "perforation": "💥 Perforation",
    "stimulation": "⚡ Stimulation",
    "completion": "✅ Completion",
    "panda": "🐼 P&A Procedure",
    "custom": "📝 Custom Procedure",
}

PROCEDURE_STATUS_COLORS = {
    "Draft": "#f39c12",
    "Under Review": "#3498db",
    "Approved": "#27ae60",
    "Superseded": "#95a5a6",
}


# ==================== Main Widget ====================
class ProcedureWidget(DrillTabBase):
    """ویجت اصلی مدیریت پروسیجرهای عملیاتی"""

    def __init__(self, db_manager=None, parent=None):
        super().__init__("ProcedureWidget", db_manager, parent)
        self.current_well_id = None
        self.current_procedure_id = None
        self.current_procedure_data = {}
        
        self.init_ui()
        
        # ایجاد قالب‌های پیش‌فرض
        if self.db:
            self.db.create_default_procedure_templates()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # ========== پنل چپ: لیست پروسیجرها ==========
        left_panel = self._create_left_panel()
        main_layout.addWidget(left_panel, 1)

        # ========== پنل راست: ویرایش پروسیجر ==========
        self.right_panel = QStackedWidget()
        
        # صفحه خوش‌آمد
        welcome_page = self._create_welcome_page()
        self.right_panel.addWidget(welcome_page)
        
        # صفحه ویرایش
        self.editor_page = ProcedureEditorPage(self.db, self)
        self.right_panel.addWidget(self.editor_page)
        
        main_layout.addWidget(self.right_panel, 3)

    def _create_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMaximumWidth(280)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QLabel("📋 Procedures")
        header.setStyleSheet("""
            QLabel {
                font-size: 14px; font-weight: bold;
                color: #2c3e50; padding: 8px;
                background: #ecf0f1; border-radius: 4px;
                border: none;
            }
        """)
        layout.addWidget(header)

        # دکمه‌های ایجاد
        btn_layout = QVBoxLayout()
        
        new_btn = QPushButton("➕ New Procedure")
        new_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60; color: white;
                font-weight: bold; padding: 8px;
                border-radius: 4px; border: none;
            }
            QPushButton:hover { background-color: #229954; }
        """)
        new_btn.clicked.connect(self.new_procedure)
        btn_layout.addWidget(new_btn)

        from_template_btn = QPushButton("📄 From Template")
        from_template_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db; color: white;
                font-weight: bold; padding: 8px;
                border-radius: 4px; border: none;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        from_template_btn.clicked.connect(self.new_from_template)
        btn_layout.addWidget(from_template_btn)

        layout.addLayout(btn_layout)

        # فیلتر
        filter_layout = QHBoxLayout()
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("All Types")
        for key, label in PROCEDURE_TYPES.items():
            self.filter_combo.addItem(label, key)
        self.filter_combo.currentIndexChanged.connect(self.load_procedures_list)
        filter_layout.addWidget(QLabel("Filter:"))
        filter_layout.addWidget(self.filter_combo)
        layout.addLayout(filter_layout)

        # لیست پروسیجرها
        self.procedures_list = QListWidget()
        self.procedures_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd; border-radius: 4px;
                background: white;
            }
            QListWidget::item {
                padding: 8px 5px; border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background: #3498db; color: white;
            }
            QListWidget::item:hover {
                background: #ebf5fb;
            }
        """)
        self.procedures_list.itemClicked.connect(self.on_procedure_selected)
        layout.addWidget(self.procedures_list, 1)

        # دکمه‌های عملیاتی
        ops_layout = QHBoxLayout()
        
        delete_btn = QPushButton("🗑️ Delete")
        delete_btn.setStyleSheet("background-color: #e74c3c; color: white; padding: 6px; border-radius: 3px; border: none;")
        delete_btn.clicked.connect(self.delete_procedure)
        
        export_btn = QPushButton("📤 Export PDF")
        export_btn.setStyleSheet("background-color: #9b59b6; color: white; padding: 6px; border-radius: 3px; border: none;")
        export_btn.clicked.connect(self.export_to_pdf)
        
        ops_layout.addWidget(delete_btn)
        ops_layout.addWidget(export_btn)
        layout.addLayout(ops_layout)

        return panel

    def _create_welcome_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)
        
        icon = QLabel("📋")
        icon.setStyleSheet("font-size: 64px;")
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)
        
        msg = QLabel(
            "Operational Procedure Manager\n\n"
            "Create or select a procedure from the left panel.\n"
            "Use templates for quick setup."
        )
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet("font-size: 14px; color: #7f8c8d;")
        layout.addWidget(msg)
        
        quick_btn = QPushButton("➕ Create New Procedure")
        quick_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60; color: white;
                font-size: 14px; font-weight: bold;
                padding: 12px 24px; border-radius: 6px; border: none;
            }
            QPushButton:hover { background-color: #229954; }
        """)
        quick_btn.clicked.connect(self.new_procedure)
        layout.addWidget(quick_btn, alignment=Qt.AlignCenter)
        
        return page

    # ==================== Selection Manager ====================
    def on_well_changed(self, well_id, well_data):
        self.current_well_id = well_id
        self.load_procedures_list()

    def on_section_changed(self, section_id, section_data):
        pass

    # ==================== Operations ====================
    def load_procedures_list(self):
        self.procedures_list.clear()
        if not self.current_well_id or not self.db:
            return
        
        procs = self.db.get_procedures_by_well(self.current_well_id)
        
        # فیلتر
        filter_type = self.filter_combo.currentData()
        if filter_type:
            procs = [p for p in procs if p.get('procedure_type') == filter_type]
        
        for proc in procs:
            item = QListWidgetItem()
            
            status = proc.get('status', 'Draft')
            color = PROCEDURE_STATUS_COLORS.get(status, "#95a5a6")
            
            proc_type = proc.get('procedure_type', '')
            type_label = PROCEDURE_TYPES.get(proc_type, proc_type)
            
            item.setText(
                f"{'✅' if status == 'Approved' else '📝'} {proc['title']}\n"
                f"  {type_label[:30]} | {status}\n"
                f"  Rev: {proc.get('revision', 'Rev 0')}"
            )
            item.setData(Qt.UserRole, proc['id'])
            item.setForeground(QColor(color))
            self.procedures_list.addItem(item)

    def on_procedure_selected(self, item):
        proc_id = item.data(Qt.UserRole)
        if proc_id:
            self.current_procedure_id = proc_id
            self.editor_page.load_procedure(proc_id)
            self.right_panel.setCurrentIndex(1)

    def new_procedure(self):
        if not self.current_well_id:
            QMessageBox.warning(self, "No Well", "Please select a well first.")
            return
        self.editor_page.new_procedure(self.current_well_id)
        self.right_panel.setCurrentIndex(1)

    def new_from_template(self):
        if not self.current_well_id:
            QMessageBox.warning(self, "No Well", "Please select a well first.")
            return
        
        dialog = TemplateSelectionDialog(self.db, self)
        if dialog.exec():
            template = dialog.get_selected_template()
            if template:
                self.editor_page.new_from_template(self.current_well_id, template)
                self.right_panel.setCurrentIndex(1)

    def delete_procedure(self):
        if not self.current_procedure_id:
            return
        
        reply = QMessageBox.question(
            self, "Delete Procedure",
            "Are you sure you want to delete this procedure?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if self.db.delete_procedure(self.current_procedure_id):
                self.current_procedure_id = None
                self.right_panel.setCurrentIndex(0)
                self.load_procedures_list()
                self.show_success("Procedure deleted")

    def export_to_pdf(self):
        if not self.current_procedure_id:
            QMessageBox.warning(self, "No Procedure", "Please select a procedure first.")
            return
        
        proc_data = self.db.get_procedure_by_id(self.current_procedure_id)
        if not proc_data:
            return
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Procedure to PDF",
            f"procedure_{proc_data['title'].replace(' ', '_')}.pdf",
            "PDF Files (*.pdf)"
        )
        if filename:
            exporter = ProcedurePDFExporter(self.db)
            success = exporter.export(self.current_procedure_id, filename)
            if success:
                self.show_success(f"Exported to: {filename}")
                # باز کردن PDF
                import os
                os.startfile(filename) if os.name == 'nt' else None
            else:
                self.show_error("Export failed")

    def save_data(self) -> bool:
        if self.current_procedure_id and hasattr(self, 'editor_page'):
            return self.editor_page.save_procedure()
        return True

    def refresh(self):
        self.load_procedures_list()


# ==================== Editor Page ====================
class ProcedureEditorPage(QWidget):
    """صفحه ویرایش پروسیجر"""

    def __init__(self, db_manager=None, parent_widget=None):
        super().__init__()
        self.db = db_manager
        self.parent_widget = parent_widget
        self.current_proc_id = None
        self.current_well_id = None
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #ddd; background: white; }
            QTabBar::tab {
                padding: 8px 16px; font-weight: bold;
                background: #ecf0f1; color: #2c3e50;
            }
            QTabBar::tab:selected { background: #3498db; color: white; }
        """)

        # تب‌های اصلی
        self.tabs.addTab(self._create_general_tab(), "📋 General Info")
        self.tabs.addTab(self._create_checklist_tab(), "✅ Checklist")
        self.tabs.addTab(self._create_steps_tab(), "📝 Procedure Steps")
        self.tabs.addTab(self._create_pjsm_tab(), "🤝 PJSM")
        self.tabs.addTab(self._create_approval_tab(), "✍️ Approval")
        self.tabs.addTab(self._create_preview_tab(), "👁️ Preview")

        layout.addWidget(self.tabs, 1)

        # Status bar
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #27ae60; font-size: 11px; padding: 3px;")
        layout.addWidget(self.status_label)

    def _create_toolbar(self) -> QWidget:
        toolbar = QWidget()
        toolbar.setStyleSheet("background: #2c3e50; border-radius: 4px; padding: 4px;")
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(5, 3, 5, 3)

        self.title_label = QLabel("📋 New Procedure")
        self.title_label.setStyleSheet("color: white; font-size: 13px; font-weight: bold;")
        layout.addWidget(self.title_label)

        layout.addStretch()

        # Status combo
        self.status_combo = QComboBox()
        self.status_combo.addItems(["Draft", "Under Review", "Approved", "Superseded"])
        self.status_combo.setStyleSheet("""
            QComboBox { background: #34495e; color: white; padding: 4px 8px; border-radius: 3px; border: 1px solid #555; }
        """)
        layout.addWidget(QLabel("<span style='color:white'>Status:</span>"))
        layout.addWidget(self.status_combo)

        save_btn = QPushButton("💾 Save")
        save_btn.setStyleSheet("background: #27ae60; color: white; padding: 6px 14px; border-radius: 3px; font-weight: bold; border: none;")
        save_btn.clicked.connect(self.save_procedure)
        layout.addWidget(save_btn)

        print_btn = QPushButton("🖨️ Print")
        print_btn.setStyleSheet("background: #8e44ad; color: white; padding: 6px 14px; border-radius: 3px; font-weight: bold; border: none;")
        print_btn.clicked.connect(self.print_procedure)
        layout.addWidget(print_btn)

        return toolbar

    def _create_general_tab(self) -> QWidget:
        tab = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(10)

        # Header Info
        header_group = QGroupBox("📄 Document Header")
        header_layout = QGridLayout(header_group)
        header_layout.setSpacing(8)

        header_layout.addWidget(QLabel("Procedure Title*:"), 0, 0)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("e.g., 7\" Liner Running & Installation")
        header_layout.addWidget(self.title_edit, 0, 1, 1, 3)

        header_layout.addWidget(QLabel("Type*:"), 1, 0)
        self.type_combo = QComboBox()
        for key, label in PROCEDURE_TYPES.items():
            self.type_combo.addItem(label, key)
        header_layout.addWidget(self.type_combo, 1, 1)

        header_layout.addWidget(QLabel("Revision:"), 1, 2)
        self.revision_edit = QLineEdit("Rev 0")
        header_layout.addWidget(self.revision_edit, 1, 3)

        header_layout.addWidget(QLabel("Date:"), 2, 0)
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        header_layout.addWidget(self.date_edit, 2, 1)

        layout.addWidget(header_group)

        # Well Info
        well_group = QGroupBox("🛢️ Well Information (Auto-fill)")
        well_layout = QGridLayout(well_group)

        well_layout.addWidget(QLabel("Well Name:"), 0, 0)
        self.well_name_edit = QLineEdit()
        well_layout.addWidget(self.well_name_edit, 0, 1)

        well_layout.addWidget(QLabel("Rig Name:"), 0, 2)
        self.rig_name_edit = QLineEdit()
        well_layout.addWidget(self.rig_name_edit, 0, 3)

        well_layout.addWidget(QLabel("Field:"), 1, 0)
        self.field_edit = QLineEdit()
        well_layout.addWidget(self.field_edit, 1, 1)

        layout.addWidget(well_group)

        # Well Status (برای Liner)
        status_group = QGroupBox("📊 Current Well Status")
        status_layout = QGridLayout(status_group)

        status_layout.addWidget(QLabel("Current Depth (m):"), 0, 0)
        self.current_depth = QDoubleSpinBox()
        self.current_depth.setRange(0, 20000)
        self.current_depth.setDecimals(1)
        status_layout.addWidget(self.current_depth, 0, 1)

        status_layout.addWidget(QLabel("Mud Weight (pcf):"), 0, 2)
        self.mud_weight = QDoubleSpinBox()
        self.mud_weight.setRange(0, 200)
        self.mud_weight.setDecimals(1)
        status_layout.addWidget(self.mud_weight, 0, 3)

        status_layout.addWidget(QLabel("Casing Shoe (m):"), 1, 0)
        self.casing_shoe = QDoubleSpinBox()
        self.casing_shoe.setRange(0, 20000)
        status_layout.addWidget(self.casing_shoe, 1, 1)

        status_layout.addWidget(QLabel("Last Casing Size (in):"), 1, 2)
        self.last_casing = QLineEdit()
        self.last_casing.setPlaceholderText("e.g., 9 5/8\"")
        status_layout.addWidget(self.last_casing, 1, 3)

        layout.addWidget(status_group)

        # Objective
        obj_group = QGroupBox("🎯 Objective")
        obj_layout = QVBoxLayout(obj_group)
        self.objective_edit = QTextEdit()
        self.objective_edit.setMaximumHeight(100)
        self.objective_edit.setPlaceholderText(
            "e.g.,\n• 9 5/8\" x 7\" overlap 120 m\n• 7\" shoe @ 3889 m"
        )
        obj_layout.addWidget(self.objective_edit)
        layout.addWidget(obj_group)

        # HSE Focus
        hse_group = QGroupBox("⚠️ HSE Focus Points")
        hse_layout = QVBoxLayout(hse_group)
        self.hse_edit = QTextEdit()
        self.hse_edit.setMaximumHeight(150)
        self.hse_edit.setPlaceholderText(
            "• There is always time to rig up and operate safely\n"
            "• Focus on falling objects\n"
            "• Hold PJSM before each job..."
        )
        hse_layout.addWidget(self.hse_edit)
        layout.addWidget(hse_group)

        layout.addStretch()
        scroll.setWidget(content)
        
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)
        return tab

    def _create_checklist_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Toolbar
        toolbar = QHBoxLayout()
        add_btn = QPushButton("➕ Add Item")
        add_btn.clicked.connect(self.add_checklist_item)
        remove_btn = QPushButton("➖ Remove")
        remove_btn.clicked.connect(self.remove_checklist_item)
        check_all_btn = QPushButton("✅ Check All")
        check_all_btn.clicked.connect(self.check_all_items)
        uncheck_all_btn = QPushButton("⬜ Uncheck All")
        uncheck_all_btn.clicked.connect(self.uncheck_all_items)

        toolbar.addWidget(add_btn)
        toolbar.addWidget(remove_btn)
        toolbar.addWidget(check_all_btn)
        toolbar.addWidget(uncheck_all_btn)
        toolbar.addStretch()

        # Progress
        self.checklist_progress = QProgressBar()
        self.checklist_progress.setMaximumHeight(16)
        toolbar.addWidget(self.checklist_progress)
        toolbar.addWidget(QLabel("Complete"))

        layout.addLayout(toolbar)

        # جدول چک‌لیست
        self.checklist_table = QTableWidget(0, 6)
        self.checklist_table.setHorizontalHeaderLabels([
            "✅", "Category", "Item Description", "Responsible", "N/A", "Remarks"
        ])
        self.checklist_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.checklist_table.setColumnWidth(0, 40)
        self.checklist_table.setColumnWidth(1, 100)
        self.checklist_table.setColumnWidth(3, 100)
        self.checklist_table.setColumnWidth(4, 40)
        self.checklist_table.setColumnWidth(5, 150)
        self.checklist_table.setAlternatingRowColors(True)
        self.checklist_table.cellChanged.connect(self._update_checklist_progress)

        layout.addWidget(self.checklist_table)
        return tab

    def _create_steps_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Toolbar
        toolbar = QHBoxLayout()
        add_btn = QPushButton("➕ Add Step")
        add_btn.clicked.connect(self.add_step)
        remove_btn = QPushButton("➖ Remove Step")
        remove_btn.clicked.connect(self.remove_step)
        move_up_btn = QPushButton("⬆️ Up")
        move_up_btn.clicked.connect(self.move_step_up)
        move_down_btn = QPushButton("⬇️ Down")
        move_down_btn.clicked.connect(self.move_step_down)

        toolbar.addWidget(add_btn)
        toolbar.addWidget(remove_btn)
        toolbar.addWidget(move_up_btn)
        toolbar.addWidget(move_down_btn)
        toolbar.addStretch()

        # Progress
        self.steps_progress = QProgressBar()
        self.steps_progress.setMaximumHeight(16)
        toolbar.addWidget(self.steps_progress)
        toolbar.addWidget(QLabel("Done"))

        layout.addLayout(toolbar)

        # جدول مراحل
        self.steps_table = QTableWidget(0, 5)
        self.steps_table.setHorizontalHeaderLabels([
            "✅", "Step #", "Activity Description",
            "Parallel Activities / Reminders", "Caution / Warning"
        ])
        self.steps_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.steps_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.steps_table.setColumnWidth(0, 40)
        self.steps_table.setColumnWidth(1, 60)
        self.steps_table.setColumnWidth(4, 200)
        self.steps_table.setAlternatingRowColors(True)
        self.steps_table.verticalHeader().setDefaultSectionSize(80)
        self.steps_table.cellChanged.connect(self._update_steps_progress)

        layout.addWidget(self.steps_table)
        return tab

    def _create_pjsm_tab(self) -> QWidget:
        tab = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        content = QWidget()
        layout = QVBoxLayout(content)

        # Meeting Info
        meeting_group = QGroupBox("🤝 Pre-Job Safety Meeting")
        meeting_layout = QGridLayout(meeting_group)

        meeting_layout.addWidget(QLabel("Date & Time:"), 0, 0)
        self.pjsm_datetime = QDateTimeEdit(QDateTime.currentDateTime())
        self.pjsm_datetime.setCalendarPopup(True)
        meeting_layout.addWidget(self.pjsm_datetime, 0, 1)

        meeting_layout.addWidget(QLabel("Location:"), 0, 2)
        self.pjsm_location = QLineEdit()
        self.pjsm_location.setPlaceholderText("e.g., Rig Floor")
        meeting_layout.addWidget(self.pjsm_location, 0, 3)

        meeting_layout.addWidget(QLabel("Conducted by:"), 1, 0)
        self.pjsm_conductor = QLineEdit()
        meeting_layout.addWidget(self.pjsm_conductor, 1, 1)

        layout.addWidget(meeting_group)

        # Attendees
        att_group = QGroupBox("👥 Attendees")
        att_layout = QVBoxLayout(att_group)
        
        att_toolbar = QHBoxLayout()
        add_att_btn = QPushButton("➕ Add")
        add_att_btn.clicked.connect(self.add_attendee)
        remove_att_btn = QPushButton("➖ Remove")
        remove_att_btn.clicked.connect(self.remove_attendee)
        att_toolbar.addWidget(add_att_btn)
        att_toolbar.addWidget(remove_att_btn)
        att_toolbar.addStretch()
        att_layout.addLayout(att_toolbar)
        
        self.attendees_table = QTableWidget(0, 3)
        self.attendees_table.setHorizontalHeaderLabels(["Name", "Position", "Company"])
        self.attendees_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.attendees_table.setMaximumHeight(200)
        att_layout.addWidget(self.attendees_table)
        layout.addWidget(att_group)

        # Topics
        topics_group = QGroupBox("📋 Topics Discussed")
        topics_layout = QVBoxLayout(topics_group)
        self.topics_edit = QTextEdit()
        self.topics_edit.setMaximumHeight(150)
        self.topics_edit.setPlaceholderText(
            "1. Scope of work and objectives\n"
            "2. HSE requirements and risks\n"
            "3. Roles and responsibilities\n"
            "4. Emergency procedures..."
        )
        topics_layout.addWidget(self.topics_edit)
        layout.addWidget(topics_group)

        # HSE Concerns
        hse_group = QGroupBox("⚠️ HSE Concerns")
        hse_layout = QVBoxLayout(hse_group)
        self.pjsm_hse = QTextEdit()
        self.pjsm_hse.setMaximumHeight(100)
        hse_layout.addWidget(self.pjsm_hse)
        layout.addWidget(hse_group)

        # Action Items
        action_group = QGroupBox("📌 Action Items")
        action_layout = QVBoxLayout(action_group)
        self.action_items = QTextEdit()
        self.action_items.setMaximumHeight(100)
        self.action_items.setPlaceholderText("List any action items with responsible persons and deadlines...")
        action_layout.addWidget(self.action_items)
        layout.addWidget(action_group)

        layout.addStretch()
        scroll.setWidget(content)
        
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)
        return tab

    def _create_approval_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignTop)

        info = QLabel(
            "📄 Document Approval Signatures\n"
            "Complete the approval workflow before finalizing the procedure."
        )
        info.setStyleSheet("color: #666; padding: 10px; background: #f8f9fa; border-radius: 4px;")
        layout.addWidget(info)

        # Approval cards
        roles = [
            ("Prepared by", "prepared_by", "#3498db"),
            ("Checked by", "checked_by", "#f39c12"),
            ("Approved by", "approved_by", "#27ae60"),
        ]

        self.approval_widgets = {}
        for role_title, role_key, color in roles:
            card = QGroupBox(f"✍️ {role_title}")
            card.setStyleSheet(f"""
                QGroupBox {{
                    border: 2px solid {color}; border-radius: 6px;
                    margin-top: 10px; padding-top: 10px;
                }}
                QGroupBox::title {{
                    color: {color}; font-weight: bold;
                }}
            """)
            card_layout = QGridLayout(card)

            card_layout.addWidget(QLabel("Name:"), 0, 0)
            name_edit = QLineEdit()
            card_layout.addWidget(name_edit, 0, 1)

            card_layout.addWidget(QLabel("Title/Position:"), 1, 0)
            title_edit = QLineEdit()
            card_layout.addWidget(title_edit, 1, 1)

            card_layout.addWidget(QLabel("Date:"), 2, 0)
            date_edit = QDateEdit(QDate.currentDate())
            date_edit.setCalendarPopup(True)
            card_layout.addWidget(date_edit, 2, 1)

            signed_cb = QCheckBox("✅ Signed")
            signed_cb.setStyleSheet(f"color: {color}; font-weight: bold;")
            card_layout.addWidget(signed_cb, 3, 0, 1, 2)

            self.approval_widgets[role_key] = {
                'name': name_edit,
                'title': title_edit,
                'date': date_edit,
                'signed': signed_cb,
            }
            layout.addWidget(card)

        layout.addStretch()
        return tab

    def _create_preview_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        preview_toolbar = QHBoxLayout()
        refresh_btn = QPushButton("🔄 Refresh Preview")
        refresh_btn.clicked.connect(self.refresh_preview)
        refresh_btn.setStyleSheet("background: #3498db; color: white; padding: 6px; border-radius: 3px; border: none;")
        preview_toolbar.addWidget(refresh_btn)
        preview_toolbar.addStretch()
        layout.addLayout(preview_toolbar)

        self.preview_browser = QTextBrowser()
        self.preview_browser.setOpenExternalLinks(True)
        layout.addWidget(self.preview_browser)

        return tab

    # ==================== Data Operations ====================
    def new_procedure(self, well_id: int):
        self.current_proc_id = None
        self.current_well_id = well_id
        self._clear_all_fields()
        
        # Auto-fill از well data
        if self.db and well_id:
            well = self.db.get_well_by_id(well_id)
            if well:
                self.well_name_edit.setText(well.get('name', ''))
                self.rig_name_edit.setText(well.get('rig_name', ''))
                self.field_edit.setText(well.get('field_name', ''))
                self.mud_weight.setValue(float(well.get('gle_msl', 0) or 0))
        
        self.title_label.setText("📋 New Procedure")
        self.status_label.setText("")

    def new_from_template(self, well_id: int, template: dict):
        self.new_procedure(well_id)
        
        # پر کردن از قالب
        self.title_edit.setText(template.get('name', ''))
        
        # پیدا کردن نوع پروسیجر
        proc_type = template.get('procedure_type', 'custom')
        for i in range(self.type_combo.count()):
            if self.type_combo.itemData(i) == proc_type:
                self.type_combo.setCurrentIndex(i)
                break
        
        # HSE Focus
        hse_points = template.get('template_hse_json', [])
        if hse_points:
            self.hse_edit.setPlainText('\n'.join(f'• {p}' for p in hse_points))
        
        # Checklist
        checklist = template.get('template_checklist_json', [])
        self.checklist_table.setRowCount(0)
        for item in checklist:
            self._add_checklist_row(
                category=item.get('category', ''),
                description=item.get('item', ''),
                responsible=item.get('responsible', ''),
            )
        
        # Steps
        steps = template.get('template_steps_json', [])
        self.steps_table.setRowCount(0)
        for step in steps:
            self._add_step_row(
                step_number=step.get('step_number', 1),
                activity=step.get('activity', ''),
                parallel=step.get('parallel', ''),
                caution=step.get('caution', ''),
            )
        
        self.title_label.setText(f"📋 {template.get('name', 'New Procedure')}")
        self._update_checklist_progress()
        self._update_steps_progress()

    def load_procedure(self, proc_id: int):
        self.current_proc_id = proc_id
        proc = self.db.get_procedure_by_id(proc_id)
        if not proc:
            return
        
        self.current_well_id = proc['well_id']
        
        # General Info
        self.title_edit.setText(proc.get('title', ''))
        
        proc_type = proc.get('procedure_type', 'custom')
        for i in range(self.type_combo.count()):
            if self.type_combo.itemData(i) == proc_type:
                self.type_combo.setCurrentIndex(i)
                break
        
        self.revision_edit.setText(proc.get('revision', 'Rev 0'))
        
        rev_date = proc.get('revision_date')
        if rev_date:
            self.date_edit.setDate(QDate(rev_date.year, rev_date.month, rev_date.day))
        
        self.well_name_edit.setText(proc.get('well_name', ''))
        self.rig_name_edit.setText(proc.get('rig_name', ''))
        self.field_edit.setText(proc.get('field_name', ''))
        self.objective_edit.setPlainText(proc.get('objective', ''))
        self.hse_edit.setPlainText(proc.get('hse_focus', ''))
        
        status = proc.get('status', 'Draft')
        idx = self.status_combo.findText(status)
        if idx >= 0:
            self.status_combo.setCurrentIndex(idx)
        
        # Checklist
        checklist = self.db.get_checklist_items(proc_id)
        self.checklist_table.setRowCount(0)
        for item in checklist:
            self._add_checklist_row(
                category=item.get('category', ''),
                description=item.get('item_description', ''),
                responsible=item.get('responsible', ''),
                verified=item.get('verified', False),
                remarks=item.get('remarks', ''),
                item_id=item.get('id'),
            )
        
        # Steps
        steps = self.db.get_procedure_steps(proc_id)
        self.steps_table.setRowCount(0)
        for step in steps:
            self._add_step_row(
                step_number=step.get('step_number', 1),
                activity=step.get('activity_description', ''),
                parallel=step.get('parallel_activities', ''),
                caution=step.get('caution_notes', ''),
                is_completed=step.get('is_completed', False),
                step_id=step.get('id'),
            )
        
        self.title_label.setText(f"📋 {proc.get('title', '')}")
        self._update_checklist_progress()
        self._update_steps_progress()

    def save_procedure(self) -> bool:
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Validation", "Procedure title is required!")
            return False
        
        if not self.current_well_id:
            QMessageBox.warning(self, "Validation", "No well selected!")
            return False
        
        # ذخیره General Info
        proc_data = {
            "well_id": self.current_well_id,
            "title": title,
            "procedure_type": self.type_combo.currentData() or 'custom',
            "revision": self.revision_edit.text(),
            "revision_date": self.date_edit.date().toPython(),
            "well_name": self.well_name_edit.text(),
            "rig_name": self.rig_name_edit.text(),
            "field_name": self.field_edit.text(),
            "status": self.status_combo.currentText(),
            "objective": self.objective_edit.toPlainText(),
            "hse_focus": self.hse_edit.toPlainText(),
        }
        
        if self.current_proc_id:
            proc_data['id'] = self.current_proc_id
        
        # Approval data
        for role, widgets in self.approval_widgets.items():
            if role == 'prepared_by':
                proc_data['prepared_by'] = widgets['name'].text()
            elif role == 'checked_by':
                proc_data['checked_by'] = widgets['name'].text()
            elif role == 'approved_by':
                proc_data['approved_by'] = widgets['name'].text()
        
        proc_id = self.db.save_procedure(proc_data)
        if not proc_id:
            QMessageBox.critical(self, "Error", "Failed to save procedure!")
            return False
        
        self.current_proc_id = proc_id
        
        # ذخیره Checklist
        checklist_items = self._collect_checklist_items()
        self.db.save_checklist_items(proc_id, checklist_items)
        
        # ذخیره Steps
        steps = self._collect_steps()
        self.db.save_procedure_steps(proc_id, steps)
        
        # Refresh list
        if self.parent_widget:
            self.parent_widget.load_procedures_list()
        
        self.status_label.setText(f"✅ Saved at {datetime.now().strftime('%H:%M:%S')}")
        return True

    def _collect_checklist_items(self) -> list:
        items = []
        for row in range(self.checklist_table.rowCount()):
            cb = self.checklist_table.cellWidget(row, 0)
            cat_item = self.checklist_table.item(row, 1)
            desc_item = self.checklist_table.item(row, 2)
            resp_item = self.checklist_table.item(row, 3)
            na_cb = self.checklist_table.cellWidget(row, 4)
            rem_item = self.checklist_table.item(row, 5)
            
            items.append({
                "verified": cb.isChecked() if cb else False,
                "category": cat_item.text() if cat_item else "",
                "item_description": desc_item.text() if desc_item else "",
                "responsible": resp_item.text() if resp_item else "",
                "not_applicable": na_cb.isChecked() if na_cb else False,
                "remarks": rem_item.text() if rem_item else "",
            })
        return items

    def _collect_steps(self) -> list:
        steps = []
        for row in range(self.steps_table.rowCount()):
            cb = self.steps_table.cellWidget(row, 0)
            act_widget = self.steps_table.cellWidget(row, 2)
            par_widget = self.steps_table.cellWidget(row, 3)
            caut_widget = self.steps_table.cellWidget(row, 4)
            
            steps.append({
                "is_completed": cb.isChecked() if cb else False,
                "activity_description": act_widget.toPlainText() if act_widget else "",
                "parallel_activities": par_widget.toPlainText() if par_widget else "",
                "caution_notes": caut_widget.toPlainText() if caut_widget else "",
            })
        return steps

    # ==================== Checklist Methods ====================
    def add_checklist_item(self):
        self._add_checklist_row()
    
    def _add_checklist_row(self, category="", description="", responsible="",
                            verified=False, remarks="", item_id=None):
        row = self.checklist_table.rowCount()
        self.checklist_table.insertRow(row)
        
        # Checkbox
        cb = QCheckBox()
        cb.setChecked(verified)
        cb.stateChanged.connect(self._update_checklist_progress)
        if verified:
            self.checklist_table.setRowHeight(row, 30)
        cb_widget = QWidget()
        cb_layout = QHBoxLayout(cb_widget)
        cb_layout.addWidget(cb)
        cb_layout.setAlignment(Qt.AlignCenter)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        self.checklist_table.setCellWidget(row, 0, cb_widget)
        
        # Category
        cat_combo = QComboBox()
        cat_combo.addItems(["Safety", "Equipment", "Materials", "Personnel", "Procedure", "Other"])
        cat_combo.setCurrentText(category)
        self.checklist_table.setCellWidget(row, 1, cat_combo)
        
        # Description
        self.checklist_table.setItem(row, 2, QTableWidgetItem(description))
        
        # Responsible
        self.checklist_table.setItem(row, 3, QTableWidgetItem(responsible))
        
        # N/A checkbox
        na_cb = QCheckBox()
        na_widget = QWidget()
        na_layout = QHBoxLayout(na_widget)
        na_layout.addWidget(na_cb)
        na_layout.setAlignment(Qt.AlignCenter)
        na_layout.setContentsMargins(0, 0, 0, 0)
        self.checklist_table.setCellWidget(row, 4, na_widget)
        
        # Remarks
        self.checklist_table.setItem(row, 5, QTableWidgetItem(remarks))
        
        # رنگ‌بندی ردیف
        if verified:
            for col in range(self.checklist_table.columnCount()):
                item = self.checklist_table.item(row, col)
                if item:
                    item.setBackground(QColor("#d5f5e3"))
        
        self._update_checklist_progress()

    def remove_checklist_item(self):
        row = self.checklist_table.currentRow()
        if row >= 0:
            self.checklist_table.removeRow(row)
            self._update_checklist_progress()

    def check_all_items(self):
        for row in range(self.checklist_table.rowCount()):
            cb_widget = self.checklist_table.cellWidget(row, 0)
            if cb_widget:
                cb = cb_widget.findChild(QCheckBox)
                if cb:
                    cb.setChecked(True)

    def uncheck_all_items(self):
        for row in range(self.checklist_table.rowCount()):
            cb_widget = self.checklist_table.cellWidget(row, 0)
            if cb_widget:
                cb = cb_widget.findChild(QCheckBox)
                if cb:
                    cb.setChecked(False)

    def _update_checklist_progress(self):
        total = self.checklist_table.rowCount()
        if total == 0:
            self.checklist_progress.setValue(0)
            return
        
        checked = 0
        for row in range(total):
            cb_widget = self.checklist_table.cellWidget(row, 0)
            if cb_widget:
                cb = cb_widget.findChild(QCheckBox)
                if cb and cb.isChecked():
                    checked += 1
        
        pct = int(checked / total * 100)
        self.checklist_progress.setValue(pct)
        
        # رنگ‌بندی ردیف‌های تیک‌خورده
        for row in range(total):
            cb_widget = self.checklist_table.cellWidget(row, 0)
            if cb_widget:
                cb = cb_widget.findChild(QCheckBox)
                is_checked = cb.isChecked() if cb else False
                for col in range(1, self.checklist_table.columnCount()):
                    item = self.checklist_table.item(row, col)
                    if item:
                        item.setBackground(QColor("#d5f5e3") if is_checked else QColor("#ffffff"))

    # ==================== Steps Methods ====================
    def add_step(self):
        step_num = self.steps_table.rowCount() + 1
        self._add_step_row(step_number=step_num)

    def _add_step_row(self, step_number=1, activity="", parallel="", caution="",
                       is_completed=False, step_id=None):
        row = self.steps_table.rowCount()
        self.steps_table.insertRow(row)
        self.steps_table.setRowHeight(row, 80)
        
        # Checkbox
        cb = QCheckBox()
        cb.setChecked(is_completed)
        cb.stateChanged.connect(self._update_steps_progress)
        cb_widget = QWidget()
        cb_layout = QHBoxLayout(cb_widget)
        cb_layout.addWidget(cb)
        cb_layout.setAlignment(Qt.AlignCenter)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_table.setCellWidget(row, 0, cb_widget)
        
        # Step Number
        num_item = QTableWidgetItem(str(step_number))
        num_item.setTextAlignment(Qt.AlignCenter)
        num_item.setFlags(Qt.ItemIsEnabled)
        num_item.setFont(QFont("Arial", 12, QFont.Bold))
        self.steps_table.setItem(row, 1, num_item)
        
        # Activity (TextEdit)
        act_edit = QTextEdit()
        act_edit.setPlainText(activity)
        act_edit.setPlaceholderText("Enter activity description...")
        self.steps_table.setCellWidget(row, 2, act_edit)
        
        # Parallel Activities (TextEdit)
        par_edit = QTextEdit()
        par_edit.setPlainText(parallel)
        par_edit.setPlaceholderText("Parallel activities / reminders...")
        par_edit.setStyleSheet("background: #fef9e7;")
        self.steps_table.setCellWidget(row, 3, par_edit)
        
        # Caution (TextEdit)
        caut_edit = QTextEdit()
        caut_edit.setPlainText(caution)
        caut_edit.setPlaceholderText("Caution / Warning notes...")
        caut_edit.setStyleSheet("background: #fdedec;")
        self.steps_table.setCellWidget(row, 4, caut_edit)
        
        # رنگ‌بندی ردیف completed
        if is_completed:
            num_item.setBackground(QColor("#d5f5e3"))
        
        self._update_steps_progress()

    def remove_step(self):
        row = self.steps_table.currentRow()
        if row >= 0:
            self.steps_table.removeRow(row)
            self._renumber_steps()
            self._update_steps_progress()

    def move_step_up(self):
        row = self.steps_table.currentRow()
        if row > 0:
            self._swap_rows(row, row - 1)
            self.steps_table.setCurrentCell(row - 1, 1)
            self._renumber_steps()

    def move_step_down(self):
        row = self.steps_table.currentRow()
        if row < self.steps_table.rowCount() - 1:
            self._swap_rows(row, row + 1)
            self.steps_table.setCurrentCell(row + 1, 1)
            self._renumber_steps()

    def _swap_rows(self, row1, row2):
        """جابجایی دو ردیف"""
        for col in [2, 3, 4]:
            w1 = self.steps_table.cellWidget(row1, col)
            w2 = self.steps_table.cellWidget(row2, col)
            if w1 and w2:
                t1 = w1.toPlainText()
                t2 = w2.toPlainText()
                w1.setPlainText(t2)
                w2.setPlainText(t1)

    def _renumber_steps(self):
        for row in range(self.steps_table.rowCount()):
            item = self.steps_table.item(row, 1)
            if item:
                item.setText(str(row + 1))

    def _update_steps_progress(self):
        total = self.steps_table.rowCount()
        if total == 0:
            self.steps_progress.setValue(0)
            return
        
        completed = 0
        for row in range(total):
            cb_widget = self.steps_table.cellWidget(row, 0)
            if cb_widget:
                cb = cb_widget.findChild(QCheckBox)
                if cb and cb.isChecked():
                    completed += 1
        
        pct = int(completed / total * 100)
        self.steps_progress.setValue(pct)

    # ==================== PJSM Methods ====================
    def add_attendee(self):
        row = self.attendees_table.rowCount()
        self.attendees_table.insertRow(row)
        self.attendees_table.setItem(row, 0, QTableWidgetItem(""))
        self.attendees_table.setItem(row, 1, QTableWidgetItem(""))
        self.attendees_table.setItem(row, 2, QTableWidgetItem(""))

    def remove_attendee(self):
        row = self.attendees_table.currentRow()
        if row >= 0:
            self.attendees_table.removeRow(row)

    # ==================== Preview ====================
    def refresh_preview(self):
        title = self.title_edit.text()
        well_name = self.well_name_edit.text()
        rig_name = self.rig_name_edit.text()
        revision = self.revision_edit.text()
        rev_date = self.date_edit.date().toString("dd MMMM yyyy")
        status = self.status_combo.currentText()
        
        # Approval
        prepared = self.approval_widgets['prepared_by']['name'].text()
        checked = self.approval_widgets['checked_by']['name'].text()
        approved = self.approval_widgets['approved_by']['name'].text()
        
        html = f"""
        <html>
        <head>
        <style>
            body {{ font-family: Arial, sans-serif; font-size: 11pt; margin: 20px; color: #2c3e50; }}
            h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 8px; font-size: 16pt; }}
            h2 {{ color: #2980b9; font-size: 13pt; margin-top: 20px; }}
            h3 {{ color: #e67e22; font-size: 11pt; }}
            .header-table {{ width: 100%; border-collapse: collapse; margin-bottom: 15px; }}
            .header-table td {{ padding: 6px; border: 1px solid #ddd; }}
            .header-table th {{ padding: 6px; background: #3498db; color: white; border: 1px solid #ddd; }}
            .status {{ 
                display: inline-block; padding: 4px 12px; border-radius: 12px;
                font-weight: bold; font-size: 10pt;
                background: {'#27ae60' if status == 'Approved' else '#f39c12' if status == 'Draft' else '#3498db'};
                color: white;
            }}
            .checklist-table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
            .checklist-table th {{ background: #2c3e50; color: white; padding: 6px; }}
            .checklist-table td {{ padding: 5px; border: 1px solid #ddd; font-size: 10pt; }}
            .checked {{ background: #d5f5e3; }}
            .step-box {{ 
                margin: 8px 0; padding: 10px; 
                border-left: 4px solid #3498db; 
                background: #f8f9fa; border-radius: 0 4px 4px 0;
            }}
            .step-number {{ 
                font-size: 18pt; font-weight: bold; color: #3498db; 
                float: left; margin-right: 10px; min-width: 30px;
            }}
            .parallel {{ background: #fef9e7; padding: 5px; border-left: 3px solid #f39c12; margin-top: 5px; font-size: 10pt; }}
            .caution {{ background: #fdedec; padding: 5px; border-left: 3px solid #e74c3c; margin-top: 5px; font-size: 10pt; }}
            .hse-box {{ background: #fff3cd; padding: 10px; border-radius: 4px; border: 1px solid #ffc107; }}
            .approval-table {{ width: 100%; border-collapse: collapse; }}
            .approval-table td {{ padding: 10px; border: 1px solid #ddd; text-align: center; }}
            .approval-table th {{ background: #2c3e50; color: white; padding: 8px; }}
            .signature-line {{ border-bottom: 1px solid black; width: 80%; margin: 20px auto 5px; }}
            .clearfix::after {{ content: ""; display: table; clear: both; }}
        </style>
        </head>
        <body>
        
        <h1>📋 {title}</h1>
        
        <table class="header-table">
            <tr>
                <th>Document</th>
                <th>Well</th>
                <th>Rig</th>
                <th>Revision</th>
                <th>Date</th>
                <th>Status</th>
            </tr>
            <tr>
                <td>DWI - {self.type_combo.currentText()[:30]}</td>
                <td>{well_name}</td>
                <td>{rig_name}</td>
                <td>{revision}</td>
                <td>{rev_date}</td>
                <td><span class="status">{status}</span></td>
            </tr>
        </table>
        """
        
        # Objective
        obj_text = self.objective_edit.toPlainText()
        if obj_text:
            html += f"""
            <h2>🎯 Objective</h2>
            <p>{obj_text.replace(chr(10), '<br>')}</p>
            """
        
        # HSE Focus
        hse_text = self.hse_edit.toPlainText()
        if hse_text:
            html += f"""
            <h2>⚠️ HSE Focus Points</h2>
            <div class="hse-box">
            {hse_text.replace(chr(10), '<br>')}
            </div>
            """
        
        # Checklist
        total_items = self.checklist_table.rowCount()
        if total_items > 0:
            checked_items = 0
            html += """
            <h2>✅ Preparation Checklist</h2>
            <table class="checklist-table">
                <tr>
                    <th width="5%">✅</th>
                    <th width="12%">Category</th>
                    <th>Item Description</th>
                    <th width="15%">Responsible</th>
                    <th width="8%">N/A</th>
                </tr>
            """
            
            for row in range(total_items):
                cb_widget = self.checklist_table.cellWidget(row, 0)
                cb = cb_widget.findChild(QCheckBox) if cb_widget else None
                is_checked = cb.isChecked() if cb else False
                
                cat_widget = self.checklist_table.cellWidget(row, 1)
                cat = cat_widget.currentText() if cat_widget else ""
                
                desc_item = self.checklist_table.item(row, 2)
                desc = desc_item.text() if desc_item else ""
                
                resp_item = self.checklist_table.item(row, 3)
                resp = resp_item.text() if resp_item else ""
                
                na_widget = self.checklist_table.cellWidget(row, 4)
                na_cb = na_widget.findChild(QCheckBox) if na_widget else None
                is_na = na_cb.isChecked() if na_cb else False
                
                if is_checked:
                    checked_items += 1
                
                row_class = "checked" if is_checked else ""
                html += f"""
                <tr class="{row_class}">
                    <td align="center">{'✅' if is_checked else '⬜'}</td>
                    <td>{cat}</td>
                    <td>{desc}</td>
                    <td>{resp}</td>
                    <td align="center">{'N/A' if is_na else ''}</td>
                </tr>
                """
            
            html += f"""
            </table>
            <p><b>Progress: {checked_items}/{total_items} items completed</b></p>
            """
        
        # Steps
        total_steps = self.steps_table.rowCount()
        if total_steps > 0:
            html += "<h2>📝 Procedure Steps</h2>"
            
            for row in range(total_steps):
                step_num_item = self.steps_table.item(row, 1)
                step_num = step_num_item.text() if step_num_item else str(row + 1)
                
                cb_widget = self.steps_table.cellWidget(row, 0)
                cb = cb_widget.findChild(QCheckBox) if cb_widget else None
                is_done = cb.isChecked() if cb else False
                
                act_widget = self.steps_table.cellWidget(row, 2)
                activity = act_widget.toPlainText() if act_widget else ""
                
                par_widget = self.steps_table.cellWidget(row, 3)
                parallel = par_widget.toPlainText() if par_widget else ""
                
                caut_widget = self.steps_table.cellWidget(row, 4)
                caution = caut_widget.toPlainText() if caut_widget else ""
                
                done_style = "background: #d5f5e3;" if is_done else ""
                
                html += f"""
                <div class="step-box clearfix" style="{done_style}">
                    <span class="step-number">{step_num}.</span>
                    <div style="overflow: hidden;">
                        {'✅ ' if is_done else ''}<b>{activity.replace(chr(10), '<br>')}</b>
                """
                
                if parallel:
                    html += f'<div class="parallel">📌 {parallel.replace(chr(10), "<br>")}</div>'
                
                if caution:
                    html += f'<div class="caution">⚠️ {caution.replace(chr(10), "<br>")}</div>'
                
                html += "</div></div>"
        
        # Approval Section
        html += f"""
        <h2>✍️ Approval</h2>
        <table class="approval-table">
            <tr>
                <th>Prepared by</th>
                <th>Checked by</th>
                <th>Approved by</th>
            </tr>
            <tr>
                <td>
                    <b>{prepared or '____________________'}</b><br>
                    <small>{self.approval_widgets['prepared_by']['title'].text()}</small><br>
                    <div class="signature-line"></div>
                    <small>Signature / Date</small>
                </td>
                <td>
                    <b>{checked or '____________________'}</b><br>
                    <small>{self.approval_widgets['checked_by']['title'].text()}</small><br>
                    <div class="signature-line"></div>
                    <small>Signature / Date</small>
                </td>
                <td>
                    <b>{approved or '____________________'}</b><br>
                    <small>{self.approval_widgets['approved_by']['title'].text()}</small><br>
                    <div class="signature-line"></div>
                    <small>Signature / Date</small>
                </td>
            </tr>
        </table>
        
        <br><hr>
        <p style="font-size: 9pt; color: #999; text-align: center;">
            Generated by DrillMaster | {datetime.now().strftime('%Y-%m-%d %H:%M')}
        </p>
        
        </body>
        </html>
        """
        
        self.preview_browser.setHtml(html)

    def print_procedure(self):
        self.refresh_preview()
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QPrintDialog.Accepted:
            self.preview_browser.document().print_(printer)

    def _clear_all_fields(self):
        self.title_edit.clear()
        self.type_combo.setCurrentIndex(0)
        self.revision_edit.setText("Rev 0")
        self.date_edit.setDate(QDate.currentDate())
        self.well_name_edit.clear()
        self.rig_name_edit.clear()
        self.field_edit.clear()
        self.objective_edit.clear()
        self.hse_edit.clear()
        self.checklist_table.setRowCount(0)
        self.steps_table.setRowCount(0)
        self.topics_edit.clear()
        self.pjsm_hse.clear()
        self.action_items.clear()
        self.attendees_table.setRowCount(0)
        for widgets in self.approval_widgets.values():
            widgets['name'].clear()
            widgets['title'].clear()
            widgets['signed'].setChecked(False)
        self.preview_browser.clear()
        self.checklist_progress.setValue(0)
        self.steps_progress.setValue(0)


# ==================== Template Selection Dialog ====================
class TemplateSelectionDialog(QDialog):
    """دیالوگ انتخاب قالب"""

    def __init__(self, db_manager=None, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.selected_template = None
        self.setWindowTitle("📄 Select Procedure Template")
        self.setMinimumSize(600, 400)
        self.init_ui()
        self.load_templates()

    def init_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel("Select a template to create your procedure:")
        header.setStyleSheet("font-size: 13px; color: #2c3e50; padding: 5px;")
        layout.addWidget(header)

        # Type filter
        filter_layout = QHBoxLayout()
        self.type_filter = QComboBox()
        self.type_filter.addItem("All Types")
        for key, label in PROCEDURE_TYPES.items():
            self.type_filter.addItem(label, key)
        self.type_filter.currentIndexChanged.connect(self.load_templates)
        filter_layout.addWidget(QLabel("Filter:"))
        filter_layout.addWidget(self.type_filter)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Template list
        self.template_list = QListWidget()
        self.template_list.setStyleSheet("""
            QListWidget::item { padding: 12px; border-bottom: 1px solid #eee; }
            QListWidget::item:selected { background: #3498db; color: white; }
        """)
        self.template_list.itemClicked.connect(self._on_template_clicked)
        self.template_list.itemDoubleClicked.connect(self._on_template_double_clicked)
        layout.addWidget(self.template_list)

        # Description
        self.desc_label = QLabel("Select a template to see description.")
        self.desc_label.setStyleSheet("color: #666; padding: 5px; background: #f8f9fa; border-radius: 3px;")
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)

        # Buttons
        btn_layout = QHBoxLayout()
        use_btn = QPushButton("✅ Use This Template")
        use_btn.setStyleSheet("background: #27ae60; color: white; font-weight: bold; padding: 8px 16px; border-radius: 4px; border: none;")
        use_btn.clicked.connect(self.accept)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(use_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def load_templates(self):
        self.template_list.clear()
        if not self.db:
            return
        
        filter_type = self.type_filter.currentData()
        templates = self.db.get_procedure_templates(filter_type)
        
        for t in templates:
            steps_count = len(t.get('template_steps_json') or [])
            checklist_count = len(t.get('template_checklist_json') or [])
            
            item = QListWidgetItem(
                f"📋 {t['name']}\n"
                f"  Type: {PROCEDURE_TYPES.get(t['procedure_type'], t['procedure_type'])}\n"
                f"  Steps: {steps_count} | Checklist: {checklist_count} items"
            )
            item.setData(Qt.UserRole, t)
            self.template_list.addItem(item)

    def _on_template_clicked(self, item):
        template = item.data(Qt.UserRole)
        if template:
            self.selected_template = template
            self.desc_label.setText(template.get('description', 'No description available.'))

    def _on_template_double_clicked(self, item):
        self._on_template_clicked(item)
        self.accept()

    def get_selected_template(self):
        if self.template_list.currentItem():
            return self.template_list.currentItem().data(Qt.UserRole)
        return self.selected_template


# ==================== PDF Exporter ====================
class ProcedurePDFExporter:
    """اکسپورت پروسیجر به PDF"""

    def __init__(self, db_manager):
        self.db = db_manager

    def export(self, proc_id: int, filename: str) -> bool:
        try:
            proc = self.db.get_procedure_by_id(proc_id)
            if not proc:
                return False
            
            steps = self.db.get_procedure_steps(proc_id)
            checklist = self.db.get_checklist_items(proc_id)
            
            # ساخت HTML برای PDF
            html = self._build_html(proc, steps, checklist)
            
            # تبدیل به PDF
            try:
                from PySide6.QtWebEngineWidgets import QWebEngineView
                from PySide6.QtCore import QUrl
                
                # روش 1: از QTextDocument
                from PySide6.QtGui import QTextDocument
                from PySide6.QtPrintSupport import QPrinter
                
                printer = QPrinter(QPrinter.HighResolution)
                printer.setOutputFormat(QPrinter.PdfFormat)
                printer.setOutputFileName(filename)
                printer.setPageSize(QPrinter.A4)
                
                doc = QTextDocument()
                doc.setHtml(html)
                doc.print_(printer)
                return True
                
            except Exception as e:
                # روش 2: reportlab fallback
                return self._export_with_reportlab(proc, steps, checklist, filename)
                
        except Exception as e:
            logger.error(f"PDF export error: {e}")
            return False

    def _export_with_reportlab(self, proc, steps, checklist, filename):
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import cm
            from reportlab.lib import colors

            doc = SimpleDocTemplate(filename, pagesize=A4,
                                     leftMargin=2*cm, rightMargin=2*cm,
                                     topMargin=2*cm, bottomMargin=2*cm)
            styles = getSampleStyleSheet()
            elements = []

            # Title
            title_style = ParagraphStyle('Title', parent=styles['Title'],
                                          fontSize=16, textColor=colors.HexColor('#2c3e50'))
            elements.append(Paragraph(proc.get('title', ''), title_style))
            elements.append(Spacer(1, 0.5*cm))

            # Header table
            header_data = [
                ['Well:', proc.get('well_name', ''),
                 'Rig:', proc.get('rig_name', ''),
                 'Revision:', proc.get('revision', '')],
                ['Status:', proc.get('status', ''),
                 'Date:', str(proc.get('revision_date', '')),
                 'Field:', proc.get('field_name', '')],
            ]
            t = Table(header_data, colWidths=[2*cm, 4*cm, 1.5*cm, 4*cm, 2*cm, 3*cm])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('FONTSIZE', (0,0), (-1,-1), 8),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 0.5*cm))

            # Objective
            if proc.get('objective'):
                elements.append(Paragraph('Objective', styles['Heading2']))
                elements.append(Paragraph(proc['objective'].replace('\n', '<br/>'), styles['Normal']))
                elements.append(Spacer(1, 0.3*cm))

            # Checklist
            if checklist:
                elements.append(Paragraph('Preparation Checklist', styles['Heading2']))
                cl_data = [['✅', 'Category', 'Item Description', 'Responsible']]
                for item in checklist:
                    cl_data.append([
                        '✅' if item.get('verified') else '⬜',
                        item.get('category', ''),
                        item.get('item_description', '')[:80],
                        item.get('responsible', ''),
                    ])
                cl_t = Table(cl_data, colWidths=[1*cm, 2.5*cm, 10*cm, 3*cm])
                cl_t.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#3498db')),
                    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                    ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
                    ('FONTSIZE', (0,0), (-1,-1), 8),
                    ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8f9fa')]),
                ]))
                elements.append(cl_t)
                elements.append(Spacer(1, 0.5*cm))

            # Steps
            if steps:
                elements.append(Paragraph('Procedure Steps', styles['Heading2']))
                for step in steps:
                    step_num = step.get('step_number', 1)
                    activity = step.get('activity_description', '')
                    parallel = step.get('parallel_activities', '')
                    caution = step.get('caution_notes', '')
                    
                    step_data = [[
                        Paragraph(f'<b>{step_num}.</b>', styles['Normal']),
                        Paragraph(f'<b>{activity}</b>', styles['Normal']),
                    ]]
                    if parallel:
                        step_data.append(['', Paragraph(f'📌 {parallel}', styles['Normal'])])
                    if caution:
                        step_data.append(['', Paragraph(f'⚠️ {caution}', styles['Normal'])])
                    
                    step_t = Table(step_data, colWidths=[1.5*cm, 15*cm])
                    step_t.setStyle(TableStyle([
                        ('VALIGN', (0,0), (-1,-1), 'TOP'),
                        ('LEFTPADDING', (0,0), (-1,-1), 4),
                    ]))
                    elements.append(step_t)
                    elements.append(Spacer(1, 0.2*cm))

            # Approval
            elements.append(Spacer(1, 1*cm))
            elements.append(Paragraph('Document Approval', styles['Heading2']))
            approval_data = [
                ['Prepared by', 'Checked by', 'Approved by'],
                [proc.get('prepared_by', '____________________'),
                 proc.get('checked_by', '____________________'),
                 proc.get('approved_by', '____________________')],
                ['Signature: ________________',
                 'Signature: ________________',
                 'Signature: ________________'],
            ]
            app_t = Table(approval_data, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
            app_t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('ROWHEIGHT', (0,1), (-1,-1), 40),
            ]))
            elements.append(app_t)

            doc.build(elements)
            return True
            
        except ImportError:
            logger.error("reportlab not installed for PDF export")
            return False
        except Exception as e:
            logger.error(f"reportlab PDF error: {e}")
            return False

    def _build_html(self, proc, steps, checklist) -> str:
        """HTML ساده برای QTextDocument"""
        title = proc.get('title', '')
        html = f"<h1>{title}</h1>"
        html += f"<p>Well: {proc.get('well_name', '')} | Rig: {proc.get('rig_name', '')} | {proc.get('revision', '')}</p>"
        
        if proc.get('objective'):
            html += f"<h2>Objective</h2><p>{proc['objective'].replace(chr(10), '<br>')}</p>"
        
        if checklist:
            html += "<h2>Checklist</h2><ul>"
            for item in checklist:
                check = "✅" if item.get('verified') else "⬜"
                html += f"<li>{check} {item.get('item_description', '')}</li>"
            html += "</ul>"
        
        if steps:
            html += "<h2>Procedure Steps</h2>"
            for step in steps:
                html += f"<p><b>{step.get('step_number')}. {step.get('activity_description', '')}</b></p>"
                if step.get('parallel_activities'):
                    html += f"<p>📌 {step.get('parallel_activities', '')}</p>"
                if step.get('caution_notes'):
                    html += f"<p>⚠️ {step.get('caution_notes', '')}</p>"
        
        html += f"<h2>Approval</h2>"
        html += f"<p>Prepared by: {proc.get('prepared_by', '')}</p>"
        html += f"<p>Checked by: {proc.get('checked_by', '')}</p>"
        html += f"<p>Approved by: {proc.get('approved_by', '')}</p>"
        
        return html