"""
Equipment Widget - ویجت تجهیزات با قابلیت‌های کامل (بازنویسی شده)
هر تب به صورت کلاس جداگانه
"""

import logging
import json
from datetime import datetime, date
from typing import Dict, Any, List, Optional

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from core.managers import StatusBarManager, TableManager, ExportManager, TableButtonManager
from core.database import DailyReport, Well
from core.base_tab import DrillTabBase

logger = logging.getLogger(__name__)


# ------------------------ Base Equipment Widget ------------------------
class DrillWidgetBase(QWidget):
    """Base class for all drill widgets with common functionality (kept for compatibility)"""
    
    def __init__(self, widget_name, db_manager=None):
        super().__init__()
        self.widget_name = widget_name
        self.db_manager = db_manager
        self.status_manager = StatusBarManager()
        self.status_manager.register_widget(widget_name, self)
        
    def save_data(self):
        return True
        
    def load_data(self):
        return True
        
    def setup_shortcuts(self):
        pass


# ------------------------ Rig Equipment Tab ------------------------
class RigEquipmentTab(QWidget):
    """تب تجهیزات ریگ"""
    
    def __init__(self, parent_widget=None, db_manager=None):
        super().__init__()
        self.parent_widget = parent_widget
        self.db_manager = db_manager
        self.table_manager = None
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        desc_label = QLabel("🏗️ Rig Equipment - Track all rig equipment with details and maintenance history")
        desc_label.setStyleSheet("font-size: 12px; color: #555; padding: 5px;")
        layout.addWidget(desc_label)
        
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Equipment", "Category", "Model", "Serial No", 
            "Status", "Last Maintenance", "Next Maintenance", "Notes"
        ])
        
        self.table_manager = TableManager(self.table, self)
        
        button_widget = self.create_buttons()
        
        layout.addWidget(self.table)
        layout.addWidget(button_widget)
        
        self.setLayout(layout)
                
    def create_buttons(self):
        widget = QWidget()
        layout = QHBoxLayout()
        
        add_btn = QPushButton("➕ Add Equipment")
        add_btn.clicked.connect(self.add_row)
        
        remove_btn = QPushButton("➖ Remove Equipment")
        remove_btn.clicked.connect(self.remove_row)
        
        save_btn = QPushButton("💾 Save")
        save_btn.clicked.connect(self.save_data)
        
        load_btn = QPushButton("📥 Load")
        load_btn.clicked.connect(self.load_data)
        
        export_btn = QPushButton("📤 Export")
        export_btn.clicked.connect(self.export_data)
        
        layout.addWidget(add_btn)
        layout.addWidget(remove_btn)
        layout.addStretch()
        layout.addWidget(save_btn)
        layout.addWidget(load_btn)
        layout.addWidget(export_btn)
        
        widget.setLayout(layout)
        return widget
           
    def add_row(self, data=None):
        if data is None:
            data = ["New Equipment", "Category", "Model", 
                   f"SN{self.table.rowCount()+1:03d}", 
                   "Operational", datetime.now().strftime("%Y-%m-%d"), 
                   "", ""]
        
        self.table_manager.add_row(data)
        
    def remove_row(self):
        self.table_manager.delete_row()
        
    def save_data(self):
        try:
            data = self.get_table_data()
            if self.parent_widget and hasattr(self.parent_widget, 'save_rig_equipment'):
                return self.parent_widget.save_rig_equipment(data)
            QMessageBox.information(self, "Success", "Rig equipment data saved")
            return True
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save: {str(e)}")
            return False
            
    def load_data(self):
        try:
            if self.parent_widget and hasattr(self.parent_widget, 'load_rig_equipment'):
                data = self.parent_widget.load_rig_equipment()
                if data:
                    self.load_table_data(data)
                    return True
            QMessageBox.information(self, "Info", "No data to load")
            return False
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load: {str(e)}")
            return False
            
    def export_data(self):
        export_manager = ExportManager(self)
        result = export_manager.export_table_with_dialog(self.table, "rig_equipment")
        if result:
            QMessageBox.information(self, "Success", f"Exported to {result}")
            
    def get_table_data(self):
        data = []
        for row in range(self.table.rowCount()):
            row_data = []
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                row_data.append(item.text() if item else "")
            data.append(row_data)
        return data
        
    def load_table_data(self, data):
        self.table.setRowCount(0)
        for row_data in data:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, value in enumerate(row_data):
                if col < self.table.columnCount():
                    item = QTableWidgetItem(str(value))
                    self.table.setItem(row, col, item)


# ------------------------ Inventory Tab ------------------------
class InventoryTab(QWidget):
    """تب موجودی"""
    
    def __init__(self, parent_widget=None, db_manager=None):
        super().__init__()
        self.parent_widget = parent_widget
        self.db_manager = db_manager
        self.table_manager = None
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        desc_label = QLabel("📦 Inventory Management - Track materials, chemicals, and supplies with stock levels")
        desc_label.setStyleSheet("font-size: 12px; color: #555; padding: 5px;")
        layout.addWidget(desc_label)
        
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "Item", "Category", "Opening Stock", "Received", 
            "Used", "Remaining", "Unit", "Min Level", "Max Level"
        ])
        
        self.table_manager = TableManager(self.table, self)
        
        self.table.cellChanged.connect(self.on_inventory_cell_changed)
        
        button_widget = self.create_buttons()
        
        layout.addWidget(self.table)
        layout.addWidget(button_widget)
        
        self.setLayout(layout)
        
    def on_inventory_cell_changed(self, row, col):
        # ستون‌ها: 2=Opening, 3=Received, 4=Used
        if col in [2, 3, 4]:
            self.calculate_inventory()
            
    def create_buttons(self):
        widget = QWidget()
        layout = QHBoxLayout()
        
        add_btn = QPushButton("➕ Add Item")
        add_btn.clicked.connect(self.add_row)
        
        remove_btn = QPushButton("➖ Remove Item")
        remove_btn.clicked.connect(self.remove_row)
        
        save_btn = QPushButton("💾 Save")
        save_btn.clicked.connect(self.save_data)
        
        load_btn = QPushButton("📥 Load")
        load_btn.clicked.connect(self.load_data)
        
        export_btn = QPushButton("📤 Export")
        export_btn.clicked.connect(self.export_data)
        
        layout.addWidget(add_btn)
        layout.addWidget(remove_btn)
        layout.addStretch()
        layout.addWidget(save_btn)
        layout.addWidget(load_btn)
        layout.addWidget(export_btn)
        
        widget.setLayout(layout)
        return widget
                      
    def add_row(self, data=None):
        if data is None:
            data = ["New Item", "Category", 0, 0, 0, 0, "pcs", 10, 100]
        
        self.table_manager.add_row(data)
        
    def remove_row(self):
        self.table_manager.delete_row()
        

    def calculate_inventory(self):
        try:
            for row in range(self.table.rowCount()):
                try:
                    opening_item = self.table.item(row, 2)
                    received_item = self.table.item(row, 3)
                    used_item = self.table.item(row, 4)

                    if opening_item and received_item and used_item:
                        opening = float(opening_item.text() or 0)
                        received = float(received_item.text() or 0)
                        used = float(used_item.text() or 0)
                        remaining = opening + received - used

                        remaining_item = self.table.item(row, 5)
                        if not remaining_item:
                            remaining_item = QTableWidgetItem()
                            self.table.setItem(row, 5, remaining_item)

                        remaining_item.setText(f"{remaining:.2f}")
                        remaining_item.setTextAlignment(
                            Qt.AlignRight | Qt.AlignVCenter
                        )

                        min_item = self.table.item(row, 7)
                        max_item = self.table.item(row, 8)

                        if min_item and max_item:
                            try:
                                min_level = float(min_item.text() or 0)
                                max_level = float(max_item.text() or 0)
                                if remaining < min_level:
                                    remaining_item.setBackground(
                                        QColor(255, 200, 200)
                                    )
                                elif remaining > max_level:
                                    remaining_item.setBackground(
                                        QColor(255, 255, 200)
                                    )
                                else:
                                    remaining_item.setBackground(
                                        QColor(200, 255, 200)
                                    )
                            except ValueError:
                                pass
                except ValueError:
                    continue

        except Exception as e:
            logger.error(f"Calculation failed: {str(e)}")
            
    def save_data(self):
        try:
            data = self.get_table_data()
            if self.parent_widget and hasattr(self.parent_widget, 'save_inventory'):
                return self.parent_widget.save_inventory(data)
            QMessageBox.information(self, "Success", "Inventory data saved")
            return True
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save: {str(e)}")
            return False
            
    def load_data(self):
        try:
            if self.parent_widget and hasattr(self.parent_widget, 'load_inventory'):
                data = self.parent_widget.load_inventory()
                if data:
                    self.load_table_data(data)
                    return True
            
            return False
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load: {str(e)}")
            return False
            
    def export_data(self):
        export_manager = ExportManager(self)
        result = export_manager.export_table_with_dialog(self.table, "inventory")
        if result:
            QMessageBox.information(self, "Success", f"Exported to {result}")
            
    def get_table_data(self):
        data = []
        for row in range(self.table.rowCount()):
            row_data = []
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                row_data.append(item.text() if item else "")
            data.append(row_data)
        return data
        
    def load_table_data(self, data):
        self.table.setRowCount(0)
        for row_data in data:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, value in enumerate(row_data):
                if col < self.table.columnCount():
                    item = QTableWidgetItem(str(value))
                    self.table.setItem(row, col, item)


# ------------------------ Drill Pipe Tab ------------------------
class DrillPipeTab(QWidget):
    """تب مشخصات لوله حفاری"""
    
    def __init__(self, parent_widget=None, db_manager=None):
        super().__init__()
        self.parent_widget = parent_widget
        self.db_manager = db_manager
        self.table_manager = None
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        desc_label = QLabel("🔩 Drill Pipe Specifications - Detailed specs for all drill pipe in inventory")
        desc_label.setStyleSheet("font-size: 12px; color: #555; padding: 5px;")
        layout.addWidget(desc_label)
        
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "Size & Weight", "Connection", "ID (in)", "Grade", 
            "TJ OD/ID", "Length (ft)", "Quantity", "Condition", 
            "Last Inspection", "Remarks"
        ])
        
        self.table_manager = TableManager(self.table, self)
        
        button_widget = self.create_buttons()
        
        layout.addWidget(self.table)
        layout.addWidget(button_widget)
        
        self.setLayout(layout)
                
    def create_buttons(self):
        widget = QWidget()
        layout = QHBoxLayout()
        
        add_btn = QPushButton("➕ Add Pipe")
        add_btn.clicked.connect(self.add_row)
        
        remove_btn = QPushButton("➖ Remove Pipe")
        remove_btn.clicked.connect(self.remove_row)
        
        save_btn = QPushButton("💾 Save")
        save_btn.clicked.connect(self.save_data)
        
        load_btn = QPushButton("📥 Load")
        load_btn.clicked.connect(self.load_data)
        
        export_btn = QPushButton("📤 Export")
        export_btn.clicked.connect(self.export_data)
        
        layout.addWidget(add_btn)
        layout.addWidget(remove_btn)
        layout.addStretch()
        layout.addWidget(save_btn)
        layout.addWidget(load_btn)
        layout.addWidget(export_btn)
        
        widget.setLayout(layout)
        return widget
                        
    def add_row(self, data=None):
        if data is None:
            data = ['5" 19.5#', "NC50", "4.276", "G-105", 
                   "6.5/4.0", "30", "100", "New", 
                   datetime.now().strftime("%Y-%m-%d"), ""]
        
        self.table_manager.add_row(data)
        
    def remove_row(self):
        self.table_manager.delete_row()
        
    def save_data(self):
        try:
            data = self.get_table_data()
            if self.parent_widget and hasattr(self.parent_widget, 'save_drill_pipe'):
                return self.parent_widget.save_drill_pipe(data)
            QMessageBox.information(self, "Success", "Drill pipe data saved")
            return True
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save: {str(e)}")
            return False
            
    def load_data(self):
        try:
            if self.parent_widget and hasattr(self.parent_widget, 'load_drill_pipe'):
                data = self.parent_widget.load_drill_pipe()
                if data:
                    self.load_table_data(data)
                    return True
            QMessageBox.information(self, "Info", "No data to load")
            return False
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load: {str(e)}")
            return False
            
    def export_data(self):
        export_manager = ExportManager(self)
        result = export_manager.export_table_with_dialog(self.table, "drill_pipe")
        if result:
            QMessageBox.information(self, "Success", f"Exported to {result}")
            
    def get_table_data(self):
        data = []
        for row in range(self.table.rowCount()):
            row_data = []
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                row_data.append(item.text() if item else "")
            data.append(row_data)
        return data
        
    def load_table_data(self, data):
        self.table.setRowCount(0)
        for row_data in data:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, value in enumerate(row_data):
                if col < self.table.columnCount():
                    item = QTableWidgetItem(str(value))
                    self.table.setItem(row, col, item)


# ------------------------ Solid Control Tab ------------------------
class SolidControlTab(QWidget):
    """تب کنترل جامدات"""
    
    def __init__(self, parent_widget=None, db_manager=None):
        super().__init__()
        self.parent_widget = parent_widget
        self.db_manager = db_manager
        self.table_manager = None
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        desc_label = QLabel("🔄 Solid Control Equipment - Monitor shakers, centrifuges, and other solid control equipment")
        desc_label.setStyleSheet("font-size: 12px; color: #555; padding: 5px;")
        layout.addWidget(desc_label)
        
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "Equipment", "Type", "Feed (bbl/hr)", "Hours Operated", 
            "Loss (bbl)", "Size/# Cones", "U.F (%)", "O.F (%)", 
            "Daily Hours", "Cumulative Hours"
        ])
        
        self.table_manager = TableManager(self.table, self)
        
        button_widget = self.create_buttons()
        
        layout.addWidget(self.table)
        layout.addWidget(button_widget)
        
        self.setLayout(layout)
                
    def create_buttons(self):
        widget = QWidget()
        layout = QHBoxLayout()
        
        add_btn = QPushButton("➕ Add Equipment")
        add_btn.clicked.connect(self.add_row)
        
        remove_btn = QPushButton("➖ Remove Equipment")
        remove_btn.clicked.connect(self.remove_row)
        
        save_btn = QPushButton("💾 Save")
        save_btn.clicked.connect(self.save_data)
        
        load_btn = QPushButton("📥 Load")
        load_btn.clicked.connect(self.load_data)
        
        export_btn = QPushButton("📤 Export")
        export_btn.clicked.connect(self.export_data)
        
        layout.addWidget(add_btn)
        layout.addWidget(remove_btn)
        layout.addStretch()
        layout.addWidget(save_btn)
        layout.addWidget(load_btn)
        layout.addWidget(export_btn)
        
        widget.setLayout(layout)
        return widget
        
    def add_row(self, data=None):
        if data is None:
            data = ["New Equipment", "Type", "500", "24", "10", 
                   "4 Cones", "80", "20", "24", "1200"]
        
        self.table_manager.add_row(data)
        
    def remove_row(self):
        self.table_manager.delete_row()
        
    def save_data(self):
        try:
            data = self.get_table_data()
            if self.parent_widget and hasattr(self.parent_widget, 'save_solid_control'):
                return self.parent_widget.save_solid_control(data)
            QMessageBox.information(self, "Success", "Solid control data saved")
            return True
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save: {str(e)}")
            return False
            
    def load_data(self):
        try:
            if self.parent_widget and hasattr(self.parent_widget, 'load_solid_control'):
                data = self.parent_widget.load_solid_control()
                if data:
                    self.load_table_data(data)
                    return True
            QMessageBox.information(self, "Info", "No data to load")
            return False
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load: {str(e)}")
            return False
            
    def export_data(self):
        export_manager = ExportManager(self)
        result = export_manager.export_table_with_dialog(self.table, "solid_control")
        if result:
            QMessageBox.information(self, "Success", f"Exported to {result}")
            
    def get_table_data(self):
        data = []
        for row in range(self.table.rowCount()):
            row_data = []
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                row_data.append(item.text() if item else "")
            data.append(row_data)
        return data
        
    def load_table_data(self, data):
        self.table.setRowCount(0)
        for row_data in data:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, value in enumerate(row_data):
                if col < self.table.columnCount():
                    item = QTableWidgetItem(str(value))
                    self.table.setItem(row, col, item)


# ------------------------ Main Equipment Widget ------------------------
class EquipmentWidget(DrillTabBase):
    """ویجت اصلی تجهیزات که تب‌ها را مدیریت می‌کند"""
    
    def __init__(self, db_manager=None, parent=None):
        super().__init__("EquipmentWidget", db_manager, parent)
        self.db = db_manager
        self.current_well = None
        self.current_report_id = None
        self.equipment_data = {}
        self.tabs = {}
        self.init_ui()
        self.setup_shortcuts()
        self.load_data()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        header_widget = self.create_header_widget()
        main_layout.addWidget(header_widget)
        
        self.tab_widget = QTabWidget()
        self.create_tabs()
        main_layout.addWidget(self.tab_widget)
        
        button_widget = self.create_button_widget()
        main_layout.addWidget(button_widget)
        
        QTimer.singleShot(200, self.populate_wells)
        
    def create_header_widget(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)

        well_label = QLabel("Well:")
        self.well_combo = QComboBox()
        self.well_combo.setMinimumWidth(200)
        self.well_combo.currentIndexChanged.connect(
            self._on_well_combo_index_changed
        )

        layout.addWidget(well_label)
        layout.addWidget(self.well_combo)
        layout.addStretch()

        return widget
        
    def create_tabs(self):
        self.rig_tab = RigEquipmentTab(parent_widget=self, db_manager=self.db)
        self.inventory_tab = InventoryTab(parent_widget=self, db_manager=self.db)
        self.pipe_tab = DrillPipeTab(parent_widget=self, db_manager=self.db)
        self.solid_tab = SolidControlTab(parent_widget=self, db_manager=self.db)
        
        self.tab_widget.addTab(self.rig_tab, "🏗️ Rig Equipment")
        self.tab_widget.addTab(self.inventory_tab, "📦 Inventory")
        self.tab_widget.addTab(self.pipe_tab, "🔩 Drill Pipe")
        self.tab_widget.addTab(self.solid_tab, "🔄 Solid Control")
        
        self.tabs = {
            'rig': self.rig_tab,
            'inventory': self.inventory_tab,
            'pipe': self.pipe_tab,
            'solid': self.solid_tab
        }
        
    def create_button_widget(self):
        widget = QWidget()
        layout = QHBoxLayout()
        
        refresh_btn = QPushButton("🔄 Refresh Data")
        refresh_btn.clicked.connect(self.refresh_data)
        
        clear_btn = QPushButton("🗑️ Clear All")
        clear_btn.clicked.connect(self.clear_all_data)
        
        save_all_btn = QPushButton("💾 Save All")
        save_all_btn.clicked.connect(self.save_all_data)
        
        layout.addWidget(refresh_btn)
        layout.addWidget(save_all_btn)
        layout.addStretch()
        layout.addWidget(clear_btn)
        
        widget.setLayout(layout)
        return widget

    # ==================== Event Handlers ====================
    def on_well_changed(self, well_id, well_data):
        """Override - sync combo + load data"""
        self.current_well = well_id
        
        # Sync combo
        self.well_combo.blockSignals(True)
        for i in range(self.well_combo.count()):
            if self.well_combo.itemData(i) == well_id:
                self.well_combo.setCurrentIndex(i)
                break
        self.well_combo.blockSignals(False)
        
        self.load_all_data()

    def on_report_changed(self, report_id, report_info):
        self.current_report_id = report_id
        self.load_all_data()

    # متمرکز برای کامبو چاه داخلی
    def _on_well_combo_index_changed(self, index):
        if index >= 0:
            well_id = self.well_combo.currentData()
            if well_id and well_id != self.current_well:
                self.current_well = well_id
                self.load_all_data()

    # ==================== Save/Load Methods ====================
    def save_rig_equipment(self, data):
        self.equipment_data['rig_equipment'] = data
        return True

    def load_rig_equipment(self):
        return self.equipment_data.get('rig_equipment', None)

    def save_inventory(self, data):
        self.equipment_data['inventory'] = data
        return True

    def load_inventory(self):
        return self.equipment_data.get('inventory', None)

    def save_drill_pipe(self, data):
        self.equipment_data['drill_pipe'] = data
        return True

    def load_drill_pipe(self):
        return self.equipment_data.get('drill_pipe', None)

    def save_solid_control(self, data):
        self.equipment_data['solid_control'] = data
        return True

    def load_solid_control(self):
        return self.equipment_data.get('solid_control', None)

    def save_all_data(self):
        """ذخیره تمام تب‌ها در equipment_logs"""
        if not self.current_well:
            self.show_message("No well selected", 3000)
            return False

        if not self.db:
            return False

        saved_total = 0

        # ===== 1. Rig Equipment =====
        rig_data = self.rig_tab.get_table_data()
        for row_data in rig_data:
            if not row_data or not row_data[0].strip():
                continue
            log_data = {
                "well_id": self.current_well,
                "report_id": self.current_report_id,
                "equipment_type": "Rig Equipment",
                "equipment_name": row_data[0] if len(row_data) > 0 else "",
                "equipment_id": row_data[3] if len(row_data) > 3 else "",
                "manufacturer": row_data[2] if len(row_data) > 2 else "",
                "serial_number": row_data[3] if len(row_data) > 3 else "",
                "status": row_data[4] if len(row_data) > 4 else "Operational",
                "service_date": row_data[5] if len(row_data) > 5 else None,
                "notes": row_data[7] if len(row_data) > 7 else "",
            }
            try:
                if self.db.save_equipment_log(log_data):
                    saved_total += 1
            except Exception as e:
                logger.error(f"Save rig equipment error: {e}")

        # ===== 2. Inventory =====
        inv_data = self.inventory_tab.get_table_data()
        for row_data in inv_data:
            if not row_data or not row_data[0].strip():
                continue
            log_data = {
                "well_id": self.current_well,
                "report_id": self.current_report_id,
                "equipment_type": "Inventory",
                "equipment_name": row_data[0] if len(row_data) > 0 else "",
                "equipment_id": row_data[1] if len(row_data) > 1 else "",
                "status": "Active",
                "hours_worked": 0,
                "notes": (
                    f"Stock:{row_data[2]}|Recv:{row_data[3]}|"
                    f"Used:{row_data[4]}|Rem:{row_data[5]}|"
                    f"Unit:{row_data[6]}"
                    if len(row_data) > 6 else ""
                ),
            }
            try:
                if self.db.save_equipment_log(log_data):
                    saved_total += 1
            except Exception as e:
                logger.error(f"Save inventory error: {e}")

        # ===== 3. Drill Pipe =====
        pipe_data = self.pipe_tab.get_table_data()
        for row_data in pipe_data:
            if not row_data or not row_data[0].strip():
                continue
            log_data = {
                "well_id": self.current_well,
                "report_id": self.current_report_id,
                "equipment_type": "Drill Pipe",
                "equipment_name": row_data[0] if len(row_data) > 0 else "",
                "equipment_id": row_data[1] if len(row_data) > 1 else "",
                "manufacturer": row_data[3] if len(row_data) > 3 else "",
                "serial_number": "",
                "status": row_data[7] if len(row_data) > 7 else "New",
                "notes": (
                    f"ID:{row_data[2]}|Grade:{row_data[3]}|"
                    f"TJ:{row_data[4]}|Len:{row_data[5]}|"
                    f"Qty:{row_data[6]}"
                    if len(row_data) > 6 else ""
                ),
            }
            try:
                if self.db.save_equipment_log(log_data):
                    saved_total += 1
            except Exception as e:
                logger.error(f"Save drill pipe error: {e}")

        # ===== 4. Solid Control =====
        solid_data = self.solid_tab.get_table_data()
        for row_data in solid_data:
            if not row_data or not row_data[0].strip():
                continue
            log_data = {
                "well_id": self.current_well,
                "report_id": self.current_report_id,
                "equipment_type": "Solid Control",
                "equipment_name": row_data[0] if len(row_data) > 0 else "",
                "equipment_id": row_data[1] if len(row_data) > 1 else "",
                "hours_worked": (
                    float(row_data[3]) if len(row_data) > 3
                    and row_data[3] else 0
                ),
                "status": "Operational",
                "notes": (
                    f"Feed:{row_data[2]}|Loss:{row_data[4]}|"
                    f"Size:{row_data[5]}|UF:{row_data[6]}|"
                    f"OF:{row_data[7]}"
                    if len(row_data) > 7 else ""
                ),
            }
            try:
                if self.db.save_equipment_log(log_data):
                    saved_total += 1
            except Exception as e:
                logger.error(f"Save solid control error: {e}")

        if saved_total > 0:
            self.show_success(f"Saved {saved_total} equipment records")
            return True
        else:
            self.show_message("No data to save", 3000)
            return False

    def load_all_data(self):
        """بارگذاری از equipment_logs"""
        if not self.current_well or not self.db:
            return

        try:
            # Always clear before loading; otherwise changing to a well with
            # no records leaves the previous well's rows on screen.
            for child in (self.rig_tab, self.inventory_tab, self.pipe_tab, self.solid_tab):
                if hasattr(child, "table"):
                    child.table.setRowCount(0)
            # ===== Rig Equipment =====
            rig_logs = self.db.get_equipment_logs(
                well_id=self.current_well,
                equipment_type="Rig Equipment",
                report_id=self.current_report_id if self.current_report_id else None,
            )
            if rig_logs:
                data = []
                for log in rig_logs:
                    data.append([
                        log.get("equipment_name", ""),
                        "Rig Equipment",
                        log.get("manufacturer", ""),
                        log.get("serial_number", ""),
                        log.get("status", ""),
                        str(log.get("service_date", "")),
                        "",
                        log.get("notes", ""),
                    ])
                self.rig_tab.load_table_data(data)

            # ===== Inventory =====
            inv_logs = self.db.get_equipment_logs(
                well_id=self.current_well,
                equipment_type="Inventory",
            )
            if inv_logs:
                data = []
                for log in inv_logs:
                    notes = log.get("notes", "")
                    parts = {}
                    if notes:
                        for part in notes.split("|"):
                            if ":" in part:
                                k, v = part.split(":", 1)
                                parts[k.strip()] = v.strip()
                    data.append([
                        log.get("equipment_name", ""),
                        log.get("equipment_id", ""),
                        parts.get("Stock", "0"),
                        parts.get("Recv", "0"),
                        parts.get("Used", "0"),
                        parts.get("Rem", "0"),
                        parts.get("Unit", "pcs"),
                        "0",
                        "100",
                    ])
                self.inventory_tab.load_table_data(data)

            # ===== Drill Pipe =====
            pipe_logs = self.db.get_equipment_logs(
                well_id=self.current_well,
                equipment_type="Drill Pipe",
            )
            if pipe_logs:
                data = []
                for log in pipe_logs:
                    notes = log.get("notes", "")
                    parts = {}
                    if notes:
                        for part in notes.split("|"):
                            if ":" in part:
                                k, v = part.split(":", 1)
                                parts[k.strip()] = v.strip()
                    data.append([
                        log.get("equipment_name", ""),
                        log.get("equipment_id", ""),
                        parts.get("ID", ""),
                        parts.get("Grade", ""),
                        parts.get("TJ", ""),
                        parts.get("Len", ""),
                        parts.get("Qty", ""),
                        log.get("status", ""),
                        str(log.get("service_date", "")),
                        "",
                    ])
                self.pipe_tab.load_table_data(data)

            # ===== Solid Control =====
            solid_logs = self.db.get_equipment_logs(
                well_id=self.current_well,
                equipment_type="Solid Control",
            )
            if solid_logs:
                data = []
                for log in solid_logs:
                    notes = log.get("notes", "")
                    parts = {}
                    if notes:
                        for part in notes.split("|"):
                            if ":" in part:
                                k, v = part.split(":", 1)
                                parts[k.strip()] = v.strip()
                    data.append([
                        log.get("equipment_name", ""),
                        log.get("equipment_id", ""),
                        parts.get("Feed", "0"),
                        str(log.get("hours_worked", 0)),
                        parts.get("Loss", "0"),
                        parts.get("Size", ""),
                        parts.get("UF", "0"),
                        parts.get("OF", "0"),
                        "0",
                        "0",
                    ])
                self.solid_tab.load_table_data(data)

        except Exception as e:
            logger.error(f"Load equipment data error: {e}")
            

    def refresh_data(self):
        self.populate_wells()
        self.load_all_data()

    def clear_all_data(self):
        reply = QMessageBox.question(self, "Clear All", "Are you sure?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            for tab in self.tabs.values():
                if hasattr(tab, 'table'):
                    tab.table.setRowCount(0)
            self.equipment_data = {}
            self.show_message("All tables cleared")

    def populate_wells(self):
        if self.db:
            self.well_combo.clear()
            hierarchy = self.db.get_hierarchy()
            for company in hierarchy:
                for project in company.get('projects', []):
                    for well in project.get('wells', []):
                        self.well_combo.addItem(f"{well['name']} ({project['name']})", well['id'])

    def save_data(self):
        """Used by AutoSaveManager"""
        return self.save_all_data()

    def setup_shortcuts(self):
        shortcuts = {
            "Ctrl+S": self.save_all_data,
            "F5": self.refresh_data,
            "Ctrl+Shift+C": self.clear_all_data,
        }
        for key, slot in shortcuts.items():
            QShortcut(QKeySequence(key), self).activated.connect(slot)