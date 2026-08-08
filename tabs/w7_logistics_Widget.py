"""
Logistics Widget Module - Version 3.0 (بازنویسی کامل)
Manages personnel, fuel, water, transport, and logistics operations
with full database integration and SelectionManager support
"""

import os
import json
import logging
from datetime import datetime, date, time
from typing import Dict, List, Optional

from PySide6.QtCore import *
from PySide6.QtWidgets import *
from PySide6.QtGui import *

from core.managers import StatusBarManager, TableManager, ExportManager, setup_widget_with_managers
from core.database import DatabaseManager, LogisticsPersonnel, ServiceCompanyPOB, FuelWaterInventory
from core.database import BulkMaterials, TransportLog, TransportNotes
from core.base_tab import DrillTabBase

logger = logging.getLogger(__name__)


class PersonnelLogisticsTab(QWidget):
    """Tab for managing personnel, crew, and logistics"""
    
    def __init__(self, db_manager=None, current_well_id=None, current_section_id=None, current_report_id=None):
        super().__init__()
        self.db = db_manager
        self.current_well_id = current_well_id
        self.current_section_id = current_section_id
        self.current_report_id = current_report_id
        self.status_manager = StatusBarManager()
        self.init_ui()
        
    def init_ui(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        
        # Service Company POB
        pob_group = QGroupBox("Service Company POB")
        pob_layout = QVBoxLayout()
        
        self.pob_table = QTableWidget(0, 6)
        self.pob_table.setHorizontalHeaderLabels([
            "ID", "Company/Service", "Service Type", "Personnel Count", 
            "Date IN", "Date OUT"
        ])
        self.pob_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.pob_table.setColumnHidden(0, True)
        font = QFont()
        font.setPointSize(9)
        self.pob_table.setFont(font)
        self.pob_table.verticalHeader().setDefaultSectionSize(30)
        self.pob_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.pob_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.pob_table_manager = TableManager(self.pob_table, self)
        
        pob_table_scroll = QScrollArea()
        pob_table_scroll.setWidgetResizable(True)
        pob_table_scroll.setWidget(self.pob_table)
        pob_table_scroll.setMinimumHeight(200)
        pob_layout.addWidget(pob_table_scroll)
        
        pob_button_layout = QHBoxLayout()
        self.add_pob_btn = QPushButton("Add POB")
        self.remove_pob_btn = QPushButton("Remove POB")
        self.calculate_pob_btn = QPushButton("Calculate Total")
        self.save_pob_btn = QPushButton("Save to DB")
        self.load_pob_btn = QPushButton("Load from DB")
        self.export_pob_btn = QPushButton("Export")
        
        pob_button_layout.addWidget(self.add_pob_btn)
        pob_button_layout.addWidget(self.remove_pob_btn)
        pob_button_layout.addWidget(self.calculate_pob_btn)
        pob_button_layout.addWidget(self.save_pob_btn)
        pob_button_layout.addWidget(self.load_pob_btn)
        pob_button_layout.addWidget(self.export_pob_btn)
        pob_button_layout.addStretch()
        pob_layout.addLayout(pob_button_layout)
        pob_group.setLayout(pob_layout)
        main_layout.addWidget(pob_group)
        
        # Crew List Section
        crew_group = QGroupBox("Crew List")
        crew_layout = QVBoxLayout()
        
        self.crew_table = QTableWidget(0, 9)
        self.crew_table.setHorizontalHeaderLabels([
            "ID", "Name", "Position", "Company", "Arrival Date", 
            "Departure Date", "Contact", "Remarks", "Created At"
        ])
        self.crew_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.crew_table.setColumnHidden(0, True)
        self.crew_table.setColumnHidden(8, True)
        self.crew_table.setFont(font)
        self.crew_table.verticalHeader().setDefaultSectionSize(30)
        self.crew_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.crew_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.crew_table_manager = TableManager(self.crew_table, self)
        
        crew_table_scroll = QScrollArea()
        crew_table_scroll.setWidgetResizable(True)
        crew_table_scroll.setWidget(self.crew_table)
        crew_table_scroll.setMinimumHeight(250)
        crew_layout.addWidget(crew_table_scroll)
        
        crew_button_layout = QHBoxLayout()
        self.add_crew_btn = QPushButton("Add Person")
        self.remove_crew_btn = QPushButton("Remove Person")
        self.save_crew_btn = QPushButton("Save to DB")
        self.load_crew_btn = QPushButton("Load from DB")
        self.import_crew_btn = QPushButton("Import CSV")
        self.export_crew_btn = QPushButton("Export")
        
        crew_button_layout.addWidget(self.add_crew_btn)
        crew_button_layout.addWidget(self.remove_crew_btn)
        crew_button_layout.addWidget(self.save_crew_btn)
        crew_button_layout.addWidget(self.load_crew_btn)
        crew_button_layout.addWidget(self.import_crew_btn)
        crew_button_layout.addWidget(self.export_crew_btn)
        crew_button_layout.addStretch()
        crew_layout.addLayout(crew_button_layout)
        crew_group.setLayout(crew_layout)
        main_layout.addWidget(crew_group)
        
        # Transport Notes
        notes_group = QGroupBox("Transport Notes")
        notes_layout = QVBoxLayout()
        
        notes_header_layout = QHBoxLayout()
        notes_header_layout.addWidget(QLabel("Date:"))
        self.note_date = QDateEdit()
        self.note_date.setDate(QDate.currentDate())
        self.note_date.setCalendarPopup(True)
        notes_header_layout.addWidget(self.note_date)
        
        notes_header_layout.addWidget(QLabel("Title:"))
        self.note_title = QLineEdit()
        self.note_title.setPlaceholderText("Enter note title...")
        notes_header_layout.addWidget(self.note_title)
        
        notes_header_layout.addWidget(QLabel("Category:"))
        self.note_category = QComboBox()
        self.note_category.addItems(["General", "Urgent", "Instructions", "Requirements"])
        notes_header_layout.addWidget(self.note_category)
        
        notes_header_layout.addWidget(QLabel("Priority:"))
        self.note_priority = QComboBox()
        self.note_priority.addItems(["Low", "Normal", "High", "Critical"])
        notes_header_layout.addWidget(self.note_priority)
        notes_header_layout.addStretch()
        notes_layout.addLayout(notes_header_layout)
        
        self.transport_notes = QTextEdit()
        self.transport_notes.setPlaceholderText("Enter transport notes, instructions, or special requirements...")
        self.transport_notes.setMinimumHeight(150)
        self.transport_notes.setMaximumHeight(200)
        notes_layout.addWidget(self.transport_notes)
        
        notes_button_layout = QHBoxLayout()
        self.save_note_btn = QPushButton("Save Note")
        self.load_notes_btn = QPushButton("Load Notes")
        self.clear_notes_btn = QPushButton("Clear")
        self.delete_note_btn = QPushButton("Delete Note")
        
        notes_button_layout.addWidget(self.save_note_btn)
        notes_button_layout.addWidget(self.load_notes_btn)
        notes_button_layout.addWidget(self.clear_notes_btn)
        notes_button_layout.addWidget(self.delete_note_btn)
        notes_button_layout.addStretch()
        notes_layout.addLayout(notes_button_layout)
        notes_group.setLayout(notes_layout)
        main_layout.addWidget(notes_group)
        
        scroll_area.setWidget(main_widget)
        main_scroll_layout = QVBoxLayout(self)
        main_scroll_layout.addWidget(scroll_area)
        self.setLayout(main_scroll_layout)
        
        self.connect_signals()
        if self.current_well_id:
            self.load_pob_data()
            self.load_crew_data()
            self.load_notes_data()
            
    def connect_signals(self):
        self.add_pob_btn.clicked.connect(self.add_pob_row)
        self.remove_pob_btn.clicked.connect(self.remove_pob_row)
        self.calculate_pob_btn.clicked.connect(self.calculate_total_pob)
        self.save_pob_btn.clicked.connect(self.save_pob_to_db)
        self.load_pob_btn.clicked.connect(self.load_pob_data)
        self.export_pob_btn.clicked.connect(self.export_pob_data)
        
        self.add_crew_btn.clicked.connect(self.add_crew_row)
        self.remove_crew_btn.clicked.connect(self.remove_crew_row)
        self.save_crew_btn.clicked.connect(self.save_crew_to_db)
        self.load_crew_btn.clicked.connect(self.load_crew_data)
        self.import_crew_btn.clicked.connect(self.import_crew_data)
        self.export_crew_btn.clicked.connect(self.export_crew_data)
        
        self.save_note_btn.clicked.connect(self.save_transport_note)
        self.load_notes_btn.clicked.connect(self.load_notes_data)
        self.clear_notes_btn.clicked.connect(self.clear_transport_notes)
        self.delete_note_btn.clicked.connect(self.delete_selected_note)
        
    def add_pob_row(self):
        row = self.pob_table.rowCount()
        self.pob_table.insertRow(row)
        today = QDate.currentDate()
        default_values = [
            "", "New Company", "Service", "0",
            today.toString("yyyy-MM-dd"),
            today.addDays(30).toString("yyyy-MM-dd")
        ]
        for col, value in enumerate(default_values):
            item = QTableWidgetItem(str(value))
            if col in [3]:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.pob_table.setItem(row, col, item)
            
    def remove_pob_row(self):
        current_row = self.pob_table.currentRow()
        if current_row >= 0:
            id_item = self.pob_table.item(current_row, 0)
            if id_item and id_item.text():
                pob_id = int(id_item.text())
                if self.db:
                    self.db.delete_service_company_pob(pob_id)
            self.pob_table.removeRow(current_row)
            self.status_manager.show_success("PersonnelTab", "POB row removed")
            
    def calculate_total_pob(self):
        total = 0
        for row in range(self.pob_table.rowCount()):
            try:
                count_item = self.pob_table.item(row, 3)
                if count_item and count_item.text():
                    total += int(count_item.text())
            except ValueError:
                continue
        QMessageBox.information(self, "Total POB", f"Total Personnel On Board: {total}")
        
    def save_pob_to_db(self):
        if not self.current_well_id:
            QMessageBox.warning(self, "Warning", "Please select a well first.")
            return False
        if not self.db:
            return False
        try:
            saved_count = 0
            for row in range(self.pob_table.rowCount()):
                id_item = self.pob_table.item(row, 0)
                company_item = self.pob_table.item(row, 1)
                service_item = self.pob_table.item(row, 2)
                count_item = self.pob_table.item(row, 3)
                date_in_item = self.pob_table.item(row, 4)
                date_out_item = self.pob_table.item(row, 5)
                if not company_item or not company_item.text():
                    continue
                pob_data = {
                    "well_id": self.current_well_id,
                    "section_id": self.current_section_id,
                    "report_id": self.current_report_id,
                    "company_name": company_item.text(),
                    "service_type": service_item.text() if service_item else "",
                    "personnel_count": int(count_item.text()) if count_item and count_item.text() else 0,
                    "date_in": datetime.strptime(date_in_item.text(), "%Y-%m-%d").date() if date_in_item and date_in_item.text() else None,
                    "date_out": datetime.strptime(date_out_item.text(), "%Y-%m-%d").date() if date_out_item and date_out_item.text() else None,
                    "remarks": ""
                }
                if id_item and id_item.text():
                    pob_data["id"] = int(id_item.text())
                result = self.db.save_service_company_pob(pob_data)
                if result:
                    saved_count += 1
                    if not id_item or not id_item.text():
                        self.pob_table.setItem(row, 0, QTableWidgetItem(str(result)))
            self.status_manager.show_success("PersonnelTab", f"Saved {saved_count} POB records")
            return True
        except Exception as e:
            logger.error(f"Error saving POB data: {e}")
            self.status_manager.show_error("PersonnelTab", f"Save failed: {e}")
            return False
            
    def load_pob_data(self):
        if not self.current_well_id:
            return
        if not self.db:
            return
        try:
            self.pob_table.setRowCount(0)
            pob_data = self.db.get_service_company_pob(
                well_id=self.current_well_id,
                section_id=self.current_section_id,
                report_id=self.current_report_id
            )
            for item in pob_data:
                row = self.pob_table.rowCount()
                self.pob_table.insertRow(row)
                values = [
                    str(item["id"]),
                    item.get("company_name", ""),
                    item.get("service_type", ""),
                    str(item.get("personnel_count", 0)),
                    item.get("date_in", ""),
                    item.get("date_out", "")
                ]
                for col, value in enumerate(values):
                    table_item = QTableWidgetItem(str(value))
                    if col in [3]:
                        table_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.pob_table.setItem(row, col, table_item)
            self.status_manager.show_success("PersonnelTab", f"Loaded {len(pob_data)} POB records")
        except Exception as e:
            logger.error(f"Error loading POB data: {e}")
            
    def export_pob_data(self):
        export_manager = ExportManager(self)
        export_manager.export_table_with_dialog(self.pob_table, "pob_data")
        
    def add_crew_row(self):
        row = self.crew_table.rowCount()
        self.crew_table.insertRow(row)
        today = QDate.currentDate()
        default_values = [
            "", "New Person", "Position", "Company",
            today.toString("yyyy-MM-dd"),
            today.addDays(14).toString("yyyy-MM-dd"),
            "", "",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ]
        for col, value in enumerate(default_values):
            self.crew_table.setItem(row, col, QTableWidgetItem(str(value)))
            
    def remove_crew_row(self):
        current_row = self.crew_table.currentRow()
        if current_row >= 0:
            id_item = self.crew_table.item(current_row, 0)
            if id_item and id_item.text():
                personnel_id = int(id_item.text())
                if self.db:
                    self.db.delete_logistics_personnel(personnel_id)
            self.crew_table.removeRow(current_row)
            self.status_manager.show_success("PersonnelTab", "Crew row removed")
            
    def save_crew_to_db(self):
        if not self.current_well_id:
            QMessageBox.warning(self, "Warning", "Please select a well first.")
            return False
        if not self.db:
            return False
        try:
            saved_count = 0
            for row in range(self.crew_table.rowCount()):
                id_item = self.crew_table.item(row, 0)
                name_item = self.crew_table.item(row, 1)
                position_item = self.crew_table.item(row, 2)
                company_item = self.crew_table.item(row, 3)
                arrival_item = self.crew_table.item(row, 4)
                departure_item = self.crew_table.item(row, 5)
                contact_item = self.crew_table.item(row, 6)
                remarks_item = self.crew_table.item(row, 7)
                if not name_item or not name_item.text():
                    continue
                personnel_data = {
                    "well_id": self.current_well_id,
                    "section_id": self.current_section_id,
                    "report_id": self.current_report_id,
                    "name": name_item.text(),
                    "position": position_item.text() if position_item else "",
                    "company": company_item.text() if company_item else "",
                    "arrival_date": datetime.strptime(arrival_item.text(), "%Y-%m-%d").date() if arrival_item and arrival_item.text() else None,
                    "departure_date": datetime.strptime(departure_item.text(), "%Y-%m-%d").date() if departure_item and departure_item.text() else None,
                    "contact_info": contact_item.text() if contact_item else "",
                    "remarks": remarks_item.text() if remarks_item else ""
                }
                if id_item and id_item.text():
                    personnel_data["id"] = int(id_item.text())
                result = self.db.save_logistics_personnel(personnel_data)
                if result:
                    saved_count += 1
                    if not id_item or not id_item.text():
                        self.crew_table.setItem(row, 0, QTableWidgetItem(str(result)))
                    self.crew_table.setItem(row, 8, QTableWidgetItem(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            self.status_manager.show_success("PersonnelTab", f"Saved {saved_count} crew records")
            return True
        except Exception as e:
            logger.error(f"Error saving crew data: {e}")
            self.status_manager.show_error("PersonnelTab", f"Save failed: {e}")
            return False
            
    def load_crew_data(self):
        if not self.current_well_id:
            return
        if not self.db:
            return
        try:
            self.crew_table.setRowCount(0)
            crew_data = self.db.get_logistics_personnel(
                well_id=self.current_well_id,
                section_id=self.current_section_id,
                report_id=self.current_report_id
            )
            for item in crew_data:
                row = self.crew_table.rowCount()
                self.crew_table.insertRow(row)
                values = [
                    str(item["id"]),
                    item.get("name", ""),
                    item.get("position", ""),
                    item.get("company", ""),
                    item.get("arrival_date", ""),
                    item.get("departure_date", ""),
                    item.get("contact_info", ""),
                    item.get("remarks", ""),
                    item.get("created_at", "").strftime("%Y-%m-%d %H:%M:%S") if item.get("created_at") else ""
                ]
                for col, value in enumerate(values):
                    self.crew_table.setItem(row, col, QTableWidgetItem(str(value)))
            self.status_manager.show_success("PersonnelTab", f"Loaded {len(crew_data)} crew records")
        except Exception as e:
            logger.error(f"Error loading crew data: {e}")
            
    def import_crew_data(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Import Crew Data", "", "CSV Files (*.csv);;All Files (*.*)")
        if filename:
            try:
                import pandas as pd
                df = pd.read_csv(filename)
                self.crew_table.setRowCount(0)
                for _, row in df.iterrows():
                    row_data = [str(row.get(col, "")) for col in df.columns]
                    self.add_crew_row()
                    current_row = self.crew_table.rowCount() - 1
                    for col, val in enumerate(row_data):
                        if col < self.crew_table.columnCount():
                            self.crew_table.setItem(current_row, col, QTableWidgetItem(val))
                self.status_manager.show_success("PersonnelTab", f"Imported {len(df)} records")
            except Exception as e:
                QMessageBox.critical(self, "Import Error", str(e))
                
    def export_crew_data(self):
        export_manager = ExportManager(self)
        export_manager.export_table_with_dialog(self.crew_table, "crew_data")
        
    def save_transport_note(self):
        if not self.current_well_id:
            QMessageBox.warning(self, "Warning", "Please select a well first.")
            return
        if not self.db:
            return
        try:
            note_data = {
                "well_id": self.current_well_id,
                "section_id": self.current_section_id,
                "report_id": self.current_report_id,
                "note_date": self.note_date.date().toPython(),
                "title": self.note_title.text(),
                "content": self.transport_notes.toPlainText(),
                "category": self.note_category.currentText(),
                "priority": self.note_priority.currentText()
            }
            result = self.db.save_transport_note(note_data)
            if result:
                self.status_manager.show_success("PersonnelTab", "Transport note saved")
                self.clear_transport_notes()
        except Exception as e:
            logger.error(f"Error saving transport note: {e}")
            self.status_manager.show_error("PersonnelTab", f"Save failed: {e}")
            
    def load_notes_data(self):
        if not self.current_well_id:
            return
        if not self.db:
            return
        try:
            notes = self.db.get_transport_notes(
                well_id=self.current_well_id,
                note_date=self.note_date.date().toPython()
            )
            if notes:
                note = notes[0]
                self.note_title.setText(note.get("title", ""))
                self.transport_notes.setPlainText(note.get("content", ""))
                self.note_category.setCurrentText(note.get("category", "General"))
                self.note_priority.setCurrentText(note.get("priority", "Normal"))
                self.status_manager.show_success("PersonnelTab", f"Loaded note from {note['note_date']}")
            else:
                self.status_manager.show_message("PersonnelTab", "No notes found for selected date")
        except Exception as e:
            logger.error(f"Error loading notes: {e}")
            
    def clear_transport_notes(self):
        self.note_title.clear()
        self.transport_notes.clear()
        self.note_category.setCurrentIndex(0)
        self.note_priority.setCurrentIndex(1)
        
    def delete_selected_note(self):
        if not self.current_well_id:
            return
        if not self.db:
            return
        notes = self.db.get_transport_notes(
            well_id=self.current_well_id,
            section_id=self.current_section_id,
            report_id=self.current_report_id,
            note_date=self.note_date.date().toPython()
        )
        if notes:
            # delete logic would go here if db had a delete method; for now just clear
            self.clear_transport_notes()
            self.status_manager.show_success("PersonnelTab", "Note cleared")
            
    def set_current_well(self, well_id: int, section_id: int = None, report_id: int = None):
        self.current_well_id = well_id
        self.current_section_id = section_id
        self.current_report_id = report_id
        if well_id:
            self.load_pob_data()
            self.load_crew_data()
            self.load_notes_data()


class FuelWaterTab(QWidget):
    """Tab for managing fuel, water, and bulk materials"""
    
    def __init__(self, db_manager=None, current_well_id=None,
                 current_section_id=None, current_report_id=None):
        super().__init__()
        self.db = db_manager
        self.current_well_id = current_well_id
        self.current_section_id = current_section_id
        self.current_report_id = current_report_id
        self.status_manager = StatusBarManager()
        self._fuel_remaining = 0.0
        self._water_remaining = 0.0

        self.init_ui()

        if self.current_well_id:
            self.load_fuel_water_from_db()
            self.load_bulk_materials_from_db()
        
    def init_ui(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        
        # Date Selection
        date_layout = QHBoxLayout()
        date_layout.addWidget(QLabel("Report Date:"))
        self.report_date = QDateEdit()
        self.report_date.setDate(QDate.currentDate())
        self.report_date.setCalendarPopup(True)
        date_layout.addWidget(self.report_date)
        date_layout.addStretch()
        main_layout.addLayout(date_layout)
        
        # Daily Consumption Section
        consumption_group = QGroupBox("Daily Consumption & Stock")
        consumption_layout = QFormLayout()
        
        consumption_layout.addRow(QLabel("<b>Fuel (Liters)</b>"))
        self.fuel_type = QComboBox()
        self.fuel_type.addItems(["Diesel", "Gasoline", "Kerosene", "Other"])
        consumption_layout.addRow("Fuel Type:", self.fuel_type)
        
        self.fuel_consumed = QDoubleSpinBox()
        self.fuel_consumed.setRange(0, 1000000)
        self.fuel_consumed.setSuffix(" L")
        self.fuel_consumed.setValue(0)
        self.fuel_consumed.valueChanged.connect(self.calculate_remaining)
        consumption_layout.addRow("Daily Consumption:", self.fuel_consumed)
        
        self.fuel_stock = QDoubleSpinBox()
        self.fuel_stock.setRange(0, 1000000)
        self.fuel_stock.setSuffix(" L")
        self.fuel_stock.setValue(0)
        self.fuel_stock.valueChanged.connect(self.calculate_remaining)
        consumption_layout.addRow("Current Stock:", self.fuel_stock)
        
        self.fuel_received = QDoubleSpinBox()
        self.fuel_received.setRange(0, 1000000)
        self.fuel_received.setSuffix(" L")
        self.fuel_received.setValue(0)
        consumption_layout.addRow("Today's Received:", self.fuel_received)
        
        consumption_layout.addRow(QLabel("<b>Water (Liters)</b>"))
        self.water_consumed = QDoubleSpinBox()
        self.water_consumed.setRange(0, 1000000)
        self.water_consumed.setSuffix(" L")
        self.water_consumed.setValue(0)
        self.water_consumed.valueChanged.connect(self.calculate_remaining)
        consumption_layout.addRow("Daily Consumption:", self.water_consumed)
        
        self.water_stock = QDoubleSpinBox()
        self.water_stock.setRange(0, 1000000)
        self.water_stock.setSuffix(" L")
        self.water_stock.setValue(0)
        self.water_stock.valueChanged.connect(self.calculate_remaining)
        consumption_layout.addRow("Current Stock:", self.water_stock)
        
        self.water_received = QDoubleSpinBox()
        self.water_received.setRange(0, 1000000)
        self.water_received.setSuffix(" L")
        self.water_received.setValue(0)
        consumption_layout.addRow("Today's Received:", self.water_received)
        
        self.results_label = QLabel("")
        self.results_label.setStyleSheet("color: #0066cc; font-weight: bold; padding: 10px; border: 1px solid #ccc; border-radius: 5px;")
        consumption_layout.addRow("Results:", self.results_label)
        
        action_layout = QHBoxLayout()
        self.calculate_btn = QPushButton("Calculate")
        self.calculate_btn.clicked.connect(self.calculate_fuel_water)
        self.save_btn = QPushButton("Save to DB")
        self.save_btn.clicked.connect(self.save_fuel_water_to_db)
        self.load_btn = QPushButton("Load from DB")
        self.load_btn.clicked.connect(self.load_fuel_water_from_db)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_fields)
        
        action_layout.addWidget(self.calculate_btn)
        action_layout.addWidget(self.save_btn)
        action_layout.addWidget(self.load_btn)
        action_layout.addWidget(self.clear_btn)
        action_layout.addStretch()
        consumption_layout.addRow("Actions:", action_layout)
        consumption_group.setLayout(consumption_layout)
        main_layout.addWidget(consumption_group)
        
        # Bulk Materials Inventory
        bulk_group = QGroupBox("Bulk Materials Inventory")
        bulk_layout = QVBoxLayout()
        
        self.bulk_table = QTableWidget(0, 8)
        self.bulk_table.setHorizontalHeaderLabels([
            "ID", "Material", "Unit", "Initial Stock", 
            "Received", "Used", "Current Stock", "Actions"
        ])
        self.bulk_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.bulk_table.setColumnHidden(0, True)
        font = QFont()
        font.setPointSize(9)
        self.bulk_table.setFont(font)
        self.bulk_table.verticalHeader().setDefaultSectionSize(30)
        self.bulk_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.bulk_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.bulk_table_manager = TableManager(self.bulk_table, self)
        
        self.bulk_table.cellChanged.connect(self.on_bulk_cell_changed)

        bulk_table_scroll = QScrollArea()
        bulk_table_scroll.setWidgetResizable(True)
        bulk_table_scroll.setWidget(self.bulk_table)
        bulk_table_scroll.setMinimumHeight(300)
        bulk_layout.addWidget(bulk_table_scroll)
        
        bulk_button_layout = QHBoxLayout()
        self.add_bulk_btn = QPushButton("Add Item")
        self.remove_bulk_btn = QPushButton("Remove Item")
        self.calculate_bulk_btn = QPushButton("Calculate Totals")
        self.save_bulk_btn = QPushButton("Save to DB")
        self.load_bulk_btn = QPushButton("Load from DB")
        self.export_bulk_btn = QPushButton("Export")
        
        bulk_button_layout.addWidget(self.add_bulk_btn)
        bulk_button_layout.addWidget(self.remove_bulk_btn)
        bulk_button_layout.addWidget(self.calculate_bulk_btn)
        bulk_button_layout.addWidget(self.save_bulk_btn)
        bulk_button_layout.addWidget(self.load_bulk_btn)
        bulk_button_layout.addWidget(self.export_bulk_btn)
        bulk_button_layout.addStretch()
        bulk_layout.addLayout(bulk_button_layout)
        bulk_group.setLayout(bulk_layout)
        main_layout.addWidget(bulk_group)
        
        scroll_area.setWidget(main_widget)
        main_scroll_layout = QVBoxLayout(self)
        main_scroll_layout.addWidget(scroll_area)
        self.setLayout(main_scroll_layout)
        
        self.connect_signals()
        self.setup_connections() 
        if self.current_well_id:
            self.load_fuel_water_from_db()
            self.load_bulk_materials_from_db()
      
    def on_bulk_cell_changed(self, row, col):
        # ستون‌ها: 3=Initial Stock, 4=Received, 5=Used
        if col in [3, 4, 5]:
            self.update_bulk_stock_for_row(row)
        
    def update_bulk_stock_for_row(self, row):
        try:
            # بررسی وجود آیتم‌ها قبل از دسترسی
            initial_item = self.bulk_table.item(row, 3)
            received_item = self.bulk_table.item(row, 4)
            used_item = self.bulk_table.item(row, 5)
            
            if initial_item is None or received_item is None or used_item is None:
                return
            
            initial = float(initial_item.text() or 0)
            received = float(received_item.text() or 0)
            used = float(used_item.text() or 0)
            stock = initial + received - used
            
            item = QTableWidgetItem(f"{stock:.1f}")
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.bulk_table.setItem(row, 6, item)
        except Exception as e:
            logger.error(f"Error updating bulk stock: {e}")
        
    def connect_signals(self):
        self.add_bulk_btn.clicked.connect(self.add_bulk_row)
        self.remove_bulk_btn.clicked.connect(self.remove_bulk_row)
        self.calculate_bulk_btn.clicked.connect(self.calculate_bulk_totals)
        self.save_bulk_btn.clicked.connect(self.save_bulk_materials_to_db)
        self.load_bulk_btn.clicked.connect(self.load_bulk_materials_from_db)
        self.export_bulk_btn.clicked.connect(self.export_bulk_data)
        
    def calculate_remaining(self):
        try:
            fuel_consumed = self.fuel_consumed.value()
            fuel_stock = self.fuel_stock.value()
            water_consumed = self.water_consumed.value()
            water_stock = self.water_stock.value()
            
            fuel_remaining = max(0, fuel_stock - fuel_consumed)
            water_remaining = max(0, water_stock - water_consumed)
            
            fuel_days = fuel_remaining / fuel_consumed if fuel_consumed > 0 else 0
            water_days = water_remaining / water_consumed if water_consumed > 0 else 0
            
            result_text = (
                f"<b>Fuel:</b> {fuel_remaining:,.1f} L remaining ({fuel_days:.1f} days)<br>"
                f"<b>Water:</b> {water_remaining:,.1f} L remaining ({water_days:.1f} days)"
            )
            self.results_label.setText(result_text)
        except Exception as e:
            self.results_label.setText(f"Error: {str(e)}")
            
    def calculate_fuel_water(self):
        self.calculate_remaining()
        fuel_consumed = self.fuel_consumed.value()
        fuel_stock = self.fuel_stock.value()
        water_consumed = self.water_consumed.value()
        water_stock = self.water_stock.value()
        fuel_days = (fuel_stock - fuel_consumed) / fuel_consumed if fuel_consumed > 0 else 0
        water_days = (water_stock - water_consumed) / water_consumed if water_consumed > 0 else 0
        if fuel_days < 3:
            self.status_manager.show_warning("FuelWaterTab", f"Low fuel stock: {fuel_days:.1f} days remaining")
        if water_days < 3:
            self.status_manager.show_warning("FuelWaterTab", f"Low water stock: {water_days:.1f} days remaining")
        self.status_manager.show_success("FuelWaterTab", "Calculation completed")
        
    def save_fuel_water_to_db(self):
        if not self.current_well_id:
            QMessageBox.warning(self, "Warning", "Please select a well first.")
            return False
        if not self.db:
            return False

        try:
            fuel_consumed = self.fuel_consumed.value()
            fuel_stock = self.fuel_stock.value()
            water_consumed = self.water_consumed.value()
            water_stock = self.water_stock.value()

            fuel_remaining = fuel_stock + self.fuel_received.value() - fuel_consumed
            water_remaining = water_stock + self.water_received.value() - water_consumed

            inventory_data = {
                "well_id": self.current_well_id,
                "section_id": self.current_section_id,
                "report_id": self.current_report_id,
                "report_date": self.report_date.date().toPython(),
                "fuel_type": self.fuel_type.currentText(),
                "fuel_consumed": fuel_consumed,
                "fuel_stock": fuel_stock,
                "fuel_received": self.fuel_received.value(),
                "fuel_remaining": fuel_remaining,
                "water_consumed": water_consumed,
                "water_stock": water_stock,
                "water_received": self.water_received.value(),
                "water_remaining": water_remaining,
            }

            if fuel_consumed > 0:
                inventory_data["days_remaining_fuel"] = fuel_remaining / fuel_consumed
            if water_consumed > 0:
                inventory_data["days_remaining_water"] = (
                    water_remaining / water_consumed
                )

            result = self.db.save_fuel_water_inventory(inventory_data)
            if result:
                self.status_manager.show_success("FuelWaterTab", "Fuel/water data saved")
                return True
            else:
                self.status_manager.show_error(
                    "FuelWaterTab", "Failed to save fuel/water data"
                )
                return False
        except Exception as e:
            logger.error(f"Error saving fuel/water data: {e}")
            self.status_manager.show_error("FuelWaterTab", f"Save failed: {str(e)}")
            return False
            
    def load_fuel_water_from_db(self):
        if not self.current_well_id:
            return
        if not self.db:
            return
        
        try:
            # تلاش برای لود با report_id، اگر نبود با well_id و تاریخ
            inventory_data = self.db.get_fuel_water_inventory(
                well_id=self.current_well_id,
                report_date=self.report_date.date().toPython(),
                report_id=self.current_report_id
            )
            
            if inventory_data and len(inventory_data) > 0:
                data = inventory_data[0]
                self.fuel_type.setCurrentText(data.get("fuel_type", "Diesel"))
                self.fuel_consumed.setValue(data.get("fuel_consumed", 0))
                self.fuel_stock.setValue(data.get("fuel_stock", 0))
                self.fuel_received.setValue(data.get("fuel_received", 0))
                self.water_consumed.setValue(data.get("water_consumed", 0))
                self.water_stock.setValue(data.get("water_stock", 0))
                self.water_received.setValue(data.get("water_received", 0))
                self.update_fuel_remaining()
                self.update_water_remaining()
                self.status_manager.show_success("FuelWaterTab", "Fuel/water data loaded")
            else:
                self.status_manager.show_message("FuelWaterTab", "No data found for selected date")
        except Exception as e:
            logger.error(f"Error loading fuel/water data: {e}")
            self.status_manager.show_error("FuelWaterTab", f"Load failed: {str(e)}")
        
    def clear_fields(self):
        self.fuel_consumed.setValue(0)
        self.fuel_stock.setValue(0)
        self.fuel_received.setValue(0)
        self.water_consumed.setValue(0)
        self.water_stock.setValue(0)
        self.water_received.setValue(0)
        self.results_label.clear()
        self.status_manager.show_success("FuelWaterTab", "Fields cleared")
        
    def add_bulk_row(self):
        row = self.bulk_table.rowCount()
        self.bulk_table.insertRow(row)
        default_values = ["", "New Material", "kg", "0.0", "0.0", "0.0", "0.0", ""]
        for col, value in enumerate(default_values):
            item = QTableWidgetItem(str(value))
            if col in [3, 4, 5, 6]:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.bulk_table.setItem(row, col, item)
            
    def remove_bulk_row(self):
        current_row = self.bulk_table.currentRow()
        if current_row >= 0:
            id_item = self.bulk_table.item(current_row, 0)
            if id_item and id_item.text():
                session = self.db.create_session()
                try:
                    session.query(BulkMaterials).filter(BulkMaterials.id == int(id_item.text())).delete()
                    session.commit()
                except:
                    session.rollback()
                finally:
                    session.close()
            self.bulk_table.removeRow(current_row)
        
    def calculate_bulk_totals(self):
        totals = {'initial': 0.0, 'received': 0.0, 'used': 0.0, 'current': 0.0, 'count': self.bulk_table.rowCount()}
        for row in range(self.bulk_table.rowCount()):
            try:
                totals['initial'] += float(self.bulk_table.item(row, 3).text() or 0)
                totals['received'] += float(self.bulk_table.item(row, 4).text() or 0)
                totals['used'] += float(self.bulk_table.item(row, 5).text() or 0)
                totals['current'] += float(self.bulk_table.item(row, 6).text() or 0)
            except ValueError:
                continue
        msg = (f"<b>Bulk Materials Summary</b><br>"
               f"Total Items: {totals['count']}<br>"
               f"Initial Stock: {totals['initial']:,.1f}<br>"
               f"Received: {totals['received']:,.1f}<br>"
               f"Used: {totals['used']:,.1f}<br>"
               f"Current Stock: {totals['current']:,.1f}")
        QMessageBox.information(self, "Summary", msg)
        
        
    def save_bulk_materials_to_db(self):
        if not self.current_well_id:
            QMessageBox.warning(self, "Warning", "Please select a well first.")
            return False
        if not self.db:
            return False
        
        try:
            saved_count = 0
            for row in range(self.bulk_table.rowCount()):
                material_item = self.bulk_table.item(row, 1)
                if not material_item or not material_item.text().strip():
                    continue
                
                unit_item = self.bulk_table.item(row, 2)
                initial_item = self.bulk_table.item(row, 3)
                received_item = self.bulk_table.item(row, 4)
                used_item = self.bulk_table.item(row, 5)
                
                # خواندن id اگر موجود باشد
                id_item = self.bulk_table.item(row, 0)
                
                material_data = {
                    "well_id": self.current_well_id,
                    "section_id": self.current_section_id,
                    "report_id": self.current_report_id,
                    "report_date": self.report_date.date().toPython(),
                    "material_name": material_item.text().strip(),
                    "unit": unit_item.text().strip() if unit_item else "kg",
                    "initial_stock": float(initial_item.text() or 0) if initial_item else 0.0,
                    "received": float(received_item.text() or 0) if received_item else 0.0,
                    "used": float(used_item.text() or 0) if used_item else 0.0,
                }
                
                if id_item and id_item.text().strip():
                    try:
                        material_data["id"] = int(id_item.text())
                    except ValueError:
                        pass
                
                result = self.db.save_bulk_material(material_data)
                if result:
                    saved_count += 1
                    # آپدیت id در جدول
                    if not id_item or not id_item.text().strip():
                        new_id_item = QTableWidgetItem(str(result))
                        self.bulk_table.setItem(row, 0, new_id_item)
            
            self.status_manager.show_success("FuelWaterTab", f"Saved {saved_count} bulk material records")
            return True
        except Exception as e:
            logger.error(f"Error saving bulk materials: {e}")
            self.status_manager.show_error("FuelWaterTab", f"Save failed: {str(e)}")
            return False
        
    def load_bulk_materials_from_db(self):
        if not self.current_well_id:
            return
        if not self.db:
            return
        try:
            self.bulk_table.setRowCount(0)
            materials_data = self.db.get_bulk_materials(
                well_id=self.current_well_id,
                report_id=self.current_report_id,
                report_date=self.report_date.date().toPython()
            )
            for item in materials_data:
                row = self.bulk_table.rowCount()
                self.bulk_table.insertRow(row)
                values = [
                    str(item["id"]),
                    item.get("material_name", ""),
                    item.get("unit", "kg"),
                    f"{item.get('initial_stock', 0):.1f}",
                    f"{item.get('received', 0):.1f}",
                    f"{item.get('used', 0):.1f}",
                    f"{item.get('current_stock', 0):.1f}",
                    ""
                ]
                for col, value in enumerate(values):
                    table_item = QTableWidgetItem(str(value))
                    if col in [3, 4, 5, 6]:
                        table_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.bulk_table.setItem(row, col, table_item)
            self.status_manager.show_success("FuelWaterTab", f"Loaded {len(materials_data)} bulk material records")
                
        except Exception as e:
            logger.error(f"Error loading bulk materials: {e}")
            
    def export_bulk_data(self):
        export_manager = ExportManager(self)
        export_manager.export_table_with_dialog(self.bulk_table, "bulk_materials")
        
    def set_current_well(self, well_id: int, section_id: int = None, report_id: int = None):
        self.current_well_id = well_id
        self.current_section_id = section_id
        self.current_report_id = report_id
        if well_id:
            self.load_fuel_water_from_db()
            self.load_bulk_materials_from_db()

    def setup_connections(self):
        self.fuel_received.valueChanged.connect(self.update_fuel_remaining)
        self.fuel_consumed.valueChanged.connect(self.update_fuel_remaining)
        self.water_received.valueChanged.connect(self.update_water_remaining)
        self.water_consumed.valueChanged.connect(self.update_water_remaining)
        self.fuel_stock.valueChanged.connect(self.update_fuel_remaining)
        self.water_stock.valueChanged.connect(self.update_water_remaining)

    def update_fuel_remaining(self):
        """محاسبه خودکار موجودی نهایی سوخت"""
        stock = self.fuel_stock.value()
        received = self.fuel_received.value()
        consumed = self.fuel_consumed.value()
        remaining = stock + received - consumed
        # ذخیره در دیتابیس بعداً
        self._fuel_remaining = remaining
        # به‌روزرسانی نمایش
        self.update_results_display()

    def update_water_remaining(self):
        """محاسبه خودکار موجودی نهایی آب"""
        stock = self.water_stock.value()
        received = self.water_received.value()
        consumed = self.water_consumed.value()
        remaining = stock + received - consumed
        self._water_remaining = remaining
        self.update_results_display()

    def update_results_display(self):
        fuel_days = self._fuel_remaining / self.fuel_consumed.value() if self.fuel_consumed.value() > 0 else 0
        water_days = self._water_remaining / self.water_consumed.value() if self.water_consumed.value() > 0 else 0
        self.results_label.setText(
            f"<b>Fuel:</b> {self._fuel_remaining:,.1f} L remaining ({fuel_days:.1f} days)<br>"
            f"<b>Water:</b> {self._water_remaining:,.1f} L remaining ({water_days:.1f} days)"
        )


class TransportLogTab(QWidget):
    """Tab for managing boats, choppers, and transport logs"""
    
    def __init__(self, db_manager=None, current_well_id=None, current_section_id=None, current_report_id=None):
        super().__init__()
        self.db = db_manager
        self.current_well_id = current_well_id
        self.current_section_id = current_section_id
        self.current_report_id = current_report_id
        self.status_manager = StatusBarManager()
        self.init_ui()
        
    def init_ui(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setSpacing(10)
        
        filter_group = QGroupBox("Filters")
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(5)
        filter_layout.addWidget(QLabel("Log Date:"))
        self.log_date = QDateEdit()
        self.log_date.setDate(QDate.currentDate())
        self.log_date.setCalendarPopup(True)
        self.log_date.setFixedWidth(120)
        filter_layout.addWidget(self.log_date)
        filter_layout.addWidget(QLabel("Vehicle Type:"))
        self.vehicle_type_filter = QComboBox()
        self.vehicle_type_filter.addItems(["All", "Boat", "Chopper"])
        self.vehicle_type_filter.setFixedWidth(100)
        filter_layout.addWidget(self.vehicle_type_filter)
        self.filter_btn = QPushButton("Filter")
        self.filter_btn.setFixedWidth(80)
        self.filter_btn.clicked.connect(self.load_transport_logs)
        filter_layout.addWidget(self.filter_btn)
        filter_layout.addStretch()
        filter_group.setLayout(filter_layout)
        main_layout.addWidget(filter_group)
        
        logs_group = QGroupBox("Transport Logs")
        logs_layout = QVBoxLayout()
        logs_layout.setSpacing(5)
        
        self.transport_table = QTableWidget(0, 13)
        headers = [
            "ID", "Type", "Name", "Vehicle ID", "Date", 
            "Arrival", "Departure", "Duration", 
            "PAX IN", "PAX OUT", "Purpose", "Status", "Remarks"
        ]
        self.transport_table.setHorizontalHeaderLabels(headers)
        column_widths = [40, 50, 120, 80, 80, 60, 60, 60, 50, 50, 150, 70, 150]
        for col, width in enumerate(column_widths):
            self.transport_table.setColumnWidth(col, width)
        self.transport_table.setColumnHidden(0, True)
        font = QFont()
        font.setPointSize(9)
        self.transport_table.setFont(font)
        self.transport_table.verticalHeader().setDefaultSectionSize(28)
        self.transport_table.verticalHeader().setVisible(False)
        self.transport_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.transport_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.transport_table.setWordWrap(True)
        self.transport_table_manager = TableManager(self.transport_table, self)
        
        table_scroll = QScrollArea()
        table_scroll.setWidgetResizable(True)
        table_scroll.setWidget(self.transport_table)
        table_scroll.setMinimumHeight(300)
        table_scroll.setMaximumHeight(400)
        logs_layout.addWidget(table_scroll)
        
        logs_button_layout = QHBoxLayout()
        logs_button_layout.setSpacing(3)
        buttons = [
            ("Add Log", self.add_transport_log),
            ("Remove", self.remove_transport_log),
            ("Edit", self.edit_transport_log),
            ("Complete", self.mark_log_complete),
            ("Save", self.save_transport_logs_to_db),
            ("Load", self.load_transport_logs),
            ("Export", self.export_transport_data)
        ]
        for text, slot in buttons:
            btn = QPushButton(text)
            btn.setFixedWidth(80)
            btn.clicked.connect(slot)
            logs_button_layout.addWidget(btn)
        logs_button_layout.addStretch()
        logs_layout.addLayout(logs_button_layout)
        logs_group.setLayout(logs_layout)
        main_layout.addWidget(logs_group)
        
        summary_group = QGroupBox("Transport Summary")
        summary_layout = QVBoxLayout()
        summary_layout.setSpacing(5)
        self.summary_text = QTextEdit()
        self.summary_text.setMaximumHeight(100)
        self.summary_text.setReadOnly(True)
        self.summary_text.setFont(font)
        summary_layout.addWidget(self.summary_text)
        summary_button_layout = QHBoxLayout()
        summary_button_layout.setSpacing(3)
        summary_buttons = [
            ("Generate", self.generate_transport_summary),
            ("Clear", self.clear_summary),
            ("Print", self.print_summary)
        ]
        for text, slot in summary_buttons:
            btn = QPushButton(text)
            btn.setFixedWidth(80)
            btn.clicked.connect(slot)
            summary_button_layout.addWidget(btn)
        summary_button_layout.addStretch()
        summary_layout.addLayout(summary_button_layout)
        summary_group.setLayout(summary_layout)
        main_layout.addWidget(summary_group)
        
        stats_group = QGroupBox("Quick Statistics")
        stats_layout = QGridLayout()
        stats_layout.setSpacing(5)
        self.stats_labels = {}
        stats = [
            ("Total Logs:", "total_logs", 0, 0),
            ("Boats:", "boats", 0, 1),
            ("Choppers:", "choppers", 0, 2),
            ("Active:", "active", 1, 0),
            ("Completed:", "completed", 1, 1),
            ("Scheduled:", "scheduled", 1, 2)
        ]
        for label_text, key, row, col in stats:
            label = QLabel(label_text)
            value_label = QLabel("0")
            value_label.setStyleSheet("font-weight: bold; color: #0066cc;")
            value_label.setAlignment(Qt.AlignRight)
            stats_layout.addWidget(label, row, col*2)
            stats_layout.addWidget(value_label, row, col*2 + 1)
            self.stats_labels[key] = value_label
        stats_group.setLayout(stats_layout)
        main_layout.addWidget(stats_group)
        
        scroll_area.setWidget(main_widget)
        main_scroll_layout = QVBoxLayout(self)
        main_scroll_layout.setContentsMargins(2, 2, 2, 2)
        main_scroll_layout.addWidget(scroll_area)
        self.setLayout(main_scroll_layout)
        
        if self.current_well_id:
            self.load_transport_logs()
        
    def add_transport_log(self):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Transport Log")
        dialog.setMinimumWidth(400)
        layout = QVBoxLayout()
        layout.setSpacing(5)
        form_layout = QFormLayout()
        form_layout.setSpacing(3)
        form_layout.setLabelAlignment(Qt.AlignRight)
        
        vehicle_type = QComboBox()
        vehicle_type.addItems(["Boat", "Chopper"])
        form_layout.addRow("Type:", vehicle_type)
        
        vehicle_name = QLineEdit()
        vehicle_name.setPlaceholderText("e.g., Supply Boat 1")
        form_layout.addRow("Name:", vehicle_name)
        
        vehicle_id = QLineEdit()
        vehicle_id.setPlaceholderText("Optional")
        form_layout.addRow("ID:", vehicle_id)
        
        date_edit = QDateEdit()
        date_edit.setDate(self.log_date.date())
        date_edit.setCalendarPopup(True)
        form_layout.addRow("Date:", date_edit)
        
        time_layout = QHBoxLayout()
        time_layout.setSpacing(5)
        arrival_time = QTimeEdit()
        arrival_time.setTime(QTime(8, 0))
        arrival_time.setDisplayFormat("HH:mm")
        departure_time = QTimeEdit()
        departure_time.setTime(QTime(17, 0))
        departure_time.setDisplayFormat("HH:mm")
        time_layout.addWidget(QLabel("Arrival:"))
        time_layout.addWidget(arrival_time)
        time_layout.addWidget(QLabel("Departure:"))
        time_layout.addWidget(departure_time)
        time_layout.addStretch()
        form_layout.addRow("Time:", time_layout)
        
        pax_layout = QHBoxLayout()
        pax_layout.setSpacing(5)
        pax_in = QSpinBox()
        pax_in.setRange(0, 100)
        pax_in.setFixedWidth(60)
        pax_out = QSpinBox()
        pax_out.setRange(0, 100)
        pax_out.setFixedWidth(60)
        pax_layout.addWidget(QLabel("IN:"))
        pax_layout.addWidget(pax_in)
        pax_layout.addWidget(QLabel("OUT:"))
        pax_layout.addWidget(pax_out)
        pax_layout.addStretch()
        form_layout.addRow("Passengers:", pax_layout)
        
        purpose = QLineEdit()
        purpose.setPlaceholderText("e.g., Crew change")
        form_layout.addRow("Purpose:", purpose)
        
        status = QComboBox()
        status.addItems(["Scheduled", "In Progress", "Completed", "Cancelled"])
        form_layout.addRow("Status:", status)
        
        remarks = QTextEdit()
        remarks.setMaximumHeight(60)
        remarks.setPlaceholderText("Additional remarks...")
        form_layout.addRow("Remarks:", remarks)
        
        layout.addLayout(form_layout)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.setLayout(layout)
        
        if dialog.exec() == QDialog.Accepted:
            row = self.transport_table.rowCount()
            self.transport_table.insertRow(row)
            duration = arrival_time.time().msecsTo(departure_time.time()) / (1000 * 60 * 60)
            if duration < 0:
                duration += 24
            
            values = [
                "", vehicle_type.currentText(), vehicle_name.text(), vehicle_id.text(),
                date_edit.date().toString("yyyy-MM-dd"),
                arrival_time.time().toString("HH:mm"), departure_time.time().toString("HH:mm"),
                f"{duration:.1f}", str(pax_in.value()), str(pax_out.value()),
                purpose.text(), status.currentText(), remarks.toPlainText()
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col in [7, 8, 9]:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.transport_table.setItem(row, col, item)
            self.update_stats()
            self.status_manager.show_success("TransportTab", "Transport log added")
            
    def remove_transport_log(self):
        current_row = self.transport_table.currentRow()
        if current_row >= 0:
            id_item = self.transport_table.item(current_row, 0)
            if id_item and id_item.text():
                session = self.db.create_session()
                try:
                    session.query(TransportLog).filter(TransportLog.id == int(id_item.text())).delete()
                    session.commit()
                except:
                    session.rollback()
                finally:
                    session.close()
            self.transport_table.removeRow(current_row)
            self.update_stats()
            
    def edit_transport_log(self):
        current_row = self.transport_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Warning", "Please select a log to edit.")
            return
        # reuse add dialog with pre-filled data (simplified)
        self.add_transport_log()
        
    def mark_log_complete(self):
        current_row = self.transport_table.currentRow()
        if current_row >= 0:
            self.transport_table.setItem(current_row, 11, QTableWidgetItem("Completed"))
            self.update_stats()
            self.status_manager.show_success("TransportTab", "Log marked as completed")
            
    def save_transport_logs_to_db(self):
        if not self.current_well_id:
            QMessageBox.warning(self, "Warning", "Please select a well first.")
            return False
        if not self.db:
            return False
        
        session = self.db.create_session()
        try:
            # حذف رکوردهای قبلی برای این well/report
            if self.current_report_id:
                session.query(TransportLog).filter(
                    TransportLog.report_id == self.current_report_id
                ).delete()
            else:
                session.query(TransportLog).filter(
                    TransportLog.well_id == self.current_well_id,
                    TransportLog.log_date == self.log_date.date().toPython()
                ).delete()
            
            saved_count = 0
            for row in range(self.transport_table.rowCount()):
                vehicle_type_item = self.transport_table.item(row, 1)
                vehicle_name_item = self.transport_table.item(row, 2)
                
                if not vehicle_type_item or not vehicle_name_item:
                    continue
                
                # خواندن تمام ستون‌ها با چک None
                items = []
                for col in range(self.transport_table.columnCount()):
                    item = self.transport_table.item(row, col)
                    items.append(item.text().strip() if item else "")
                
                try:
                    log = TransportLog(
                        well_id=self.current_well_id,
                        section_id=self.current_section_id,
                        report_id=self.current_report_id,
                        log_date=datetime.strptime(items[4], "%Y-%m-%d").date() if items[4] else date.today(),
                        vehicle_type=items[1],
                        vehicle_name=items[2],
                        vehicle_id=items[3] if items[3] else None,
                        arrival_time=datetime.strptime(items[5], "%H:%M").time() if items[5] else None,
                        departure_time=datetime.strptime(items[6], "%H:%M").time() if items[6] else None,
                        duration=float(items[7]) if items[7] else 0.0,
                        passengers_in=int(items[8]) if items[8] else 0,
                        passengers_out=int(items[9]) if items[9] else 0,
                        purpose=items[10] if len(items) > 10 else "",
                        status=items[11] if len(items) > 11 else "Scheduled",
                        remarks=items[12] if len(items) > 12 else ""
                    )
                    session.add(log)
                    saved_count += 1
                except Exception as e:
                    logger.error(f"Row {row} parse error: {e}")
                    continue
            
            session.commit()
            self.status_manager.show_success("TransportTab", f"Saved {saved_count} transport logs")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Transport save error: {e}")
            self.status_manager.show_error("TransportTab", f"Save failed: {str(e)}")
            return False
        finally:
            session.close()
            
    def load_transport_logs(self):
        if not self.current_well_id:
            return
        try:
            logs = self.db.get_transport_logs(
                well_id=self.current_well_id,
                report_id=self.current_report_id,
                log_date=self.log_date.date().toPython()
            )
            self.transport_table.setRowCount(0)
            for log in logs:
                row = self.transport_table.rowCount()
                self.transport_table.insertRow(row)
                values = [
                    str(log['id']), log['vehicle_type'], log['vehicle_name'],
                    log.get('vehicle_id', ''), str(log['log_date']),
                    log['arrival_time'], log['departure_time'], f"{log['duration']:.1f}",
                    str(log['passengers_in']), str(log['passengers_out']),
                    log.get('purpose', ''), log.get('status', ''), log.get('remarks', '')
                ]
                for col, val in enumerate(values):
                    self.transport_table.setItem(row, col, QTableWidgetItem(str(val)))
            self.update_stats()
            self.status_manager.show_success("TransportTab", f"Loaded {len(logs)} logs")
        except Exception as e:
            logger.error(f"Error loading transport logs: {e}")
            
    def export_transport_data(self):
        export_manager = ExportManager(self)
        export_manager.export_table_with_dialog(self.transport_table, "transport_logs")
    
    def generate_transport_summary(self):
        self.update_stats()
        summary = (f"📊 TRANSPORT SUMMARY\n"
                   f"{'='*40}\n"
                   f"Total Logs: {self.stats_labels['total_logs'].text()}\n"
                   f"Boats: {self.stats_labels['boats'].text()}\n"
                   f"Choppers: {self.stats_labels['choppers'].text()}\n"
                   f"Active: {self.stats_labels['active'].text()}\n"
                   f"Completed: {self.stats_labels['completed'].text()}\n"
                   f"Scheduled: {self.stats_labels['scheduled'].text()}")
        self.summary_text.setPlainText(summary)
        
    def clear_summary(self):
        self.summary_text.clear()
        
    def print_summary(self):
        QMessageBox.information(self, "Summary", self.summary_text.toPlainText())
    
    def update_stats(self):
        total = self.transport_table.rowCount()
        boats = choppers = active = completed = scheduled = 0
        for row in range(total):
            type_item = self.transport_table.item(row, 1)
            status_item = self.transport_table.item(row, 11)
            if type_item:
                if type_item.text() == "Boat": boats += 1
                elif type_item.text() == "Chopper": choppers += 1
            if status_item:
                if status_item.text() == "In Progress": active += 1
                elif status_item.text() == "Completed": completed += 1
                elif status_item.text() == "Scheduled": scheduled += 1
        self.stats_labels['total_logs'].setText(str(total))
        self.stats_labels['boats'].setText(str(boats))
        self.stats_labels['choppers'].setText(str(choppers))
        self.stats_labels['active'].setText(str(active))
        self.stats_labels['completed'].setText(str(completed))
        self.stats_labels['scheduled'].setText(str(scheduled))
        
    def set_current_well(self, well_id: int, section_id: int = None, report_id: int = None):
        self.current_well_id = well_id
        self.current_section_id = section_id
        self.current_report_id = report_id
        if well_id:
            self.load_transport_logs()


class LogisticsWidget(DrillTabBase):
    """Main Logistics Widget with multiple tabs (نسخه بازنویسی شده)"""
    
    def __init__(self, db_manager=None, parent=None):
        super().__init__("LogisticsWidget", db_manager, parent)
        self.db = db_manager
        self.current_well_id = None
        self.current_section_id = None
        self.current_report_id = None
        self.status_manager = StatusBarManager()
        self.status_manager.register_widget(self.widget_name, self)
        
        self.personnel_tab = None
        self.fuel_water_tab = None
        self.transport_tab = None
        
        self.init_ui()
        self.setup_managers()
        
    def init_ui(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        
        well_layout = QHBoxLayout()
        well_layout.addWidget(QLabel("Current Well:"))
        self.well_label = QLabel("No well selected")
        self.well_label.setStyleSheet("font-weight: bold; color: #0066cc;")
        well_layout.addWidget(self.well_label)
        well_layout.addStretch()
        self.select_well_btn = QPushButton("Select Well")
        self.select_well_btn.clicked.connect(self.select_well)
        well_layout.addWidget(self.select_well_btn)
        self.select_well_btn.setVisible(False)
        main_layout.addLayout(well_layout)
        
        self.tab_widget = QTabWidget()
        
        self.personnel_tab = PersonnelLogisticsTab(self.db, self.current_well_id, self.current_section_id, self.current_report_id)
        self.fuel_water_tab = FuelWaterTab(self.db, self.current_well_id, self.current_section_id, self.current_report_id)
        self.transport_tab = TransportLogTab(self.db, self.current_well_id, self.current_section_id, self.current_report_id)
        
        self.tab_widget.addTab(self.personnel_tab, "👥 Personnel & Logistics")
        self.tab_widget.addTab(self.fuel_water_tab, "⛽ Fuel & Water")
        self.tab_widget.addTab(self.transport_tab, "🚤 Transport Log")
        
        main_layout.addWidget(self.tab_widget)
        
        control_layout = QHBoxLayout()
        self.save_all_btn = QPushButton("💾 Save All")
        self.load_all_btn = QPushButton("📂 Load All")
        self.clear_all_btn = QPushButton("🗑️ Clear All")
        self.export_all_btn = QPushButton("📤 Export All")
        self.print_btn = QPushButton("🖨️ Print")
        self.help_btn = QPushButton("❓ Help")
        
        control_layout.addWidget(self.save_all_btn)
        control_layout.addWidget(self.load_all_btn)
        control_layout.addWidget(self.clear_all_btn)
        control_layout.addWidget(self.export_all_btn)
        control_layout.addWidget(self.print_btn)
        control_layout.addWidget(self.help_btn)
        control_layout.addStretch()
        main_layout.addLayout(control_layout)
        
        scroll_area.setWidget(main_widget)
        main_scroll_layout = QVBoxLayout(self)
        main_scroll_layout.addWidget(scroll_area)
        self.setLayout(main_scroll_layout)
        
        self.save_all_btn.clicked.connect(self.save_all_data)
        self.load_all_btn.clicked.connect(self.load_all_data)
        self.clear_all_btn.clicked.connect(self.clear_all_data)
        self.export_all_btn.clicked.connect(self.export_all)
        self.print_btn.clicked.connect(self.print_data)
        self.help_btn.clicked.connect(self.show_help)
        
    def setup_managers(self):
        setup_widget_with_managers(
            widget=self,
            widget_name=self.widget_name,
            enable_autosave=True,
            autosave_interval=5,
            setup_shortcuts=True
        )
        logger.info(f"{self.widget_name} initialized with all managers")
        
    def select_well(self):
        # This can be replaced by SelectionManager integration
        if not self.db:
            return
        hierarchy = self.db.get_hierarchy()
        if not hierarchy:
            QMessageBox.information(self, "Information", "No wells found")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Well")
        dialog.setMinimumWidth(400)
        layout = QVBoxLayout()
        well_list = QListWidget()
        for company in hierarchy:
            for project in company.get('projects', []):
                for well in project.get('wells', []):
                    item_text = f"{well.get('name', 'Unknown')} - {well.get('code', 'No Code')}"
                    list_item = QListWidgetItem(item_text)
                    list_item.setData(Qt.UserRole, well.get('id'))
                    well_list.addItem(list_item)
        layout.addWidget(well_list)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.setLayout(layout)
        if dialog.exec() == QDialog.Accepted and well_list.currentItem():
            well_id = well_list.currentItem().data(Qt.UserRole)
            self.current_well_id = well_id
            self.well_label.setText(well_list.currentItem().text())
            self.update_tabs_well()
    
    def on_well_changed(self, well_id, well_data):
        """Override DrillTabBase"""
        self.current_well_id = well_id
        name = well_data.get("name", str(well_id)) if well_data else str(well_id)
        self.well_label.setText(f"Current Well: {name}")
        self.well_label.setStyleSheet("font-weight: bold; color: #27ae60;")
        self.update_tabs_well()

    def on_section_changed(self, section_id, section_data):
        """Keep every logistics child scoped to the selected section."""
        self.current_section_id = section_id
        self.update_tabs_well()

    def on_report_changed(self, report_id, report_info):
        """Override DrillTabBase"""
        self.current_report_id = report_id
        self.update_tabs_well()

    def update_tabs_well(self):
        """پاس دادن well_id و report_id به همه زیرتب‌ها"""
        if self.personnel_tab:
            self.personnel_tab.current_well_id = self.current_well_id
            self.personnel_tab.current_section_id = self.current_section_id
            self.personnel_tab.current_report_id = self.current_report_id
            self.personnel_tab.load_pob_data()
            self.personnel_tab.load_crew_data()
        
        if self.fuel_water_tab:
            self.fuel_water_tab.current_well_id = self.current_well_id
            self.fuel_water_tab.current_section_id = self.current_section_id
            self.fuel_water_tab.current_report_id = self.current_report_id
            self.fuel_water_tab.load_fuel_water_from_db()
            self.fuel_water_tab.load_bulk_materials_from_db()
        
        if self.transport_tab:
            self.transport_tab.current_well_id = self.current_well_id
            self.transport_tab.current_section_id = self.current_section_id
            self.transport_tab.current_report_id = self.current_report_id
            self.transport_tab.load_transport_logs()
        
    def save_all_data(self):
        success = True
        if self.personnel_tab:
            if not self.personnel_tab.save_pob_to_db(): success = False
            if not self.personnel_tab.save_crew_to_db(): success = False
        if self.fuel_water_tab:
            if not self.fuel_water_tab.save_fuel_water_to_db(): success = False
            if not self.fuel_water_tab.save_bulk_materials_to_db(): success = False
        if self.transport_tab:
            if not self.transport_tab.save_transport_logs_to_db(): success = False
        if success:
            self.show_success("All logistics data saved")
        else:
            self.show_error("Some data failed to save")
        return success
    
    def load_all_data(self):
        if not self.current_well_id:
            QMessageBox.warning(self, "Warning", "Please select a well first")
            return False
        if self.personnel_tab:
            self.personnel_tab.load_pob_data()
            self.personnel_tab.load_crew_data()
            self.personnel_tab.load_notes_data()
        if self.fuel_water_tab:
            self.fuel_water_tab.load_fuel_water_from_db()
            self.fuel_water_tab.load_bulk_materials_from_db()
        if self.transport_tab:
            self.transport_tab.load_transport_logs()
        self.show_success("All data loaded")
        return True
    
    def clear_all_data(self):
        reply = QMessageBox.question(self, "Clear All Data", "Are you sure?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            if self.personnel_tab:
                self.personnel_tab.pob_table.setRowCount(0)
                self.personnel_tab.crew_table.setRowCount(0)
                self.personnel_tab.clear_transport_notes()
            if self.fuel_water_tab:
                self.fuel_water_tab.clear_fields()
                self.fuel_water_tab.bulk_table.setRowCount(0)
            if self.transport_tab:
                self.transport_tab.transport_table.setRowCount(0)
                self.transport_tab.clear_summary()
            self.show_success("All data cleared")
    
    def export_all(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_manager = ExportManager(self)
        if self.personnel_tab and self.personnel_tab.pob_table.rowCount() > 0:
            export_manager.export_table_with_dialog(self.personnel_tab.pob_table, f"pob_{timestamp}")
        if self.fuel_water_tab and self.fuel_water_tab.bulk_table.rowCount() > 0:
            export_manager.export_table_with_dialog(self.fuel_water_tab.bulk_table, f"bulk_{timestamp}")
        if self.transport_tab and self.transport_tab.transport_table.rowCount() > 0:
            export_manager.export_table_with_dialog(self.transport_tab.transport_table, f"transport_{timestamp}")
        self.show_success("Export completed")
    
    def print_data(self):
        """چاپ یا ذخیره گزارش کامل لجستیک به صورت PDF / HTML"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Print / Export Logistics Report",
            f"Logistics_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            "PDF Files (*.pdf);;HTML Files (*.html)"
        )
        if not file_path:
            return

        try:
            html = "<html><head><style>"
            html += "body { font-family: Arial, sans-serif; font-size: 10pt; margin: 20px; color: #2c3e50; }"
            html += "h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px; }"
            html += "h2 { color: #2980b9; margin-top: 15px; }"
            html += "table { width: 100%; border-collapse: collapse; margin-top: 8px; margin-bottom: 15px; }"
            html += "th, td { border: 1px solid #bdc3c7; padding: 6px; text-align: left; font-size: 9pt; }"
            html += "th { background-color: #3498db; color: white; }"
            html += "</style></head><body>"
            html += f"<h1>📦 Logistics & Operations Report ({datetime.now().strftime('%Y-%m-%d %H:%M')})</h1>"

            # Summary Section
            summary_txt = self.summary_text.toPlainText() if hasattr(self, 'summary_text') else ""
            if summary_txt:
                html += f"<h2>Logistics Summary</h2><p>{summary_txt.replace(chr(10), '<br>')}</p>"

            # Personnel Table
            if hasattr(self, 'personnel_tab') and self.personnel_tab and hasattr(self.personnel_tab, 'pob_table'):
                html += "<h2>👥 Personnel On Board (POB)</h2>"
                html += self._table_to_html_str(self.personnel_tab.pob_table)

            # Bulk Table
            if hasattr(self, 'fuel_water_tab') and self.fuel_water_tab and hasattr(self.fuel_water_tab, 'bulk_table'):
                html += "<h2>⛽ Bulk Materials & Fuel/Water</h2>"
                html += self._table_to_html_str(self.fuel_water_tab.bulk_table)

            # Transport Table
            if hasattr(self, 'transport_tab') and self.transport_tab and hasattr(self.transport_tab, 'transport_table'):
                html += "<h2>🚁 Transport & Logistics Movements</h2>"
                html += self._table_to_html_str(self.transport_tab.transport_table)

            html += "<hr><p style='text-align: center; color: #7f8c8d; font-size: 8pt;'>Generated by NMD Software</p>"
            html += "</body></html>"

            ext = os.path.splitext(file_path)[1].lower()
            if ext == ".html":
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(html)
            else:
                from PySide6.QtGui import QTextDocument
                from PySide6.QtPrintSupport import QPrinter
                doc = QTextDocument()
                doc.setHtml(html)
                printer = QPrinter(QPrinter.HighResolution)
                printer.setOutputFormat(QPrinter.PdfFormat)
                printer.setOutputFileName(file_path)
                doc.print_(printer)

            self.show_success(f"Logistics report printed/saved to {os.path.basename(file_path)}")
            QMessageBox.information(self, "Success", f"Logistics report exported to:\n{file_path}")
        except Exception as e:
            logger.error(f"Error printing logistics report: {e}")
            self.show_error(f"Print error: {str(e)}")

    def _table_to_html_str(self, table):
        if not table or table.rowCount() == 0:
            return "<p><i>No data available.</i></p>"
        html = "<table><thead><tr>"
        for col in range(table.columnCount()):
            hdr = table.horizontalHeaderItem(col)
            txt = hdr.text() if hdr else f"Col {col+1}"
            html += f"<th>{txt}</th>"
        html += "</tr></thead><tbody>"
        for row in range(table.rowCount()):
            html += "<tr>"
            for col in range(table.columnCount()):
                item = table.item(row, col)
                val = item.text() if item else ""
                html += f"<td>{val}</td>"
            html += "</tr>"
        html += "</tbody></table>"
        return html
    
    def show_help(self):
        QMessageBox.information(
            self,
            "Logistics Module Help",
            "📦 Logistics & Operations Management Module:\n\n"
            "1. 👥 Personnel (POB):\n"
            "   • Record daily personnel counts by company and shift.\n"
            "   • Automatically calculates Total POB on board.\n\n"
            "2. ⛽ Fuel & Water (Bulk Management):\n"
            "   • Track inventory of diesel fuel, drill water, and potable water.\n"
            "   • Record received and consumed quantities automatically.\n\n"
            "3. 🚁 Transport & Logistics:\n"
            "   • Log chopper flights, supply boats, and ground shipments.\n"
            "   • Record passenger and cargo manifests.\n\n"
            "4. 📊 Export & Print:\n"
            "   • Export all tables to Excel or print full HTML/PDF logistics summary."
        )
    
    def save_data(self):
        return self.save_all_data()
    
    def refresh(self):
        self.load_all_data()