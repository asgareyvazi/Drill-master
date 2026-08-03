"""
Hierarchy Dialogs - دیالوگ‌های ایجاد Company، Project و Well
"""

import logging
from datetime import datetime, date
from typing import Optional

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from core.database import DatabaseManager, Company, Project, Well, DailyReport, Section
from core.managers import StatusBarManager
import json

logger = logging.getLogger(__name__)


class BaseHierarchyDialog(QDialog):
    """دیالوگ پایه برای همه آیتم‌های سلسله مراتب"""

    def __init__(self, db_manager: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.setModal(True)
        self.created_id = None 
        self.result = None 

    def setup_ui(self):
        """تنظیمات اولیه UI"""
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

    def validate_required_fields(
        self, fields: dict
    ) -> tuple:
        """
        ✅ FIX: اعتبارسنجی بهتر با پیام‌های واضح‌تر.
        """
        errors = []
        for field_name, value in fields.items():
            if not value or str(value).strip() == "":
                # تبدیل نام فیلد به فرمت خواناتر
                readable_name = field_name.replace("_", " ").title()
                errors.append(f"• {readable_name} is required")

        if errors:
            return False, "\n".join(errors)
        return True, ""

    def show_error(self, message: str):
        """✅ FIX: نمایش بهتر خطا."""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("⚠️ Validation Error")
        msg.setText(message)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()

    def show_success(self, message: str):
        """✅ FIX: نمایش بهتر موفقیت."""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("✅ Success")
        msg.setText(message)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()
    
    def get_result(self):
        """دریافت نتیجه - باید در کلاس‌های فرزند override شود"""
        return self.result

class NewCompanyDialog(BaseHierarchyDialog):
    """دیالوگ ایجاد شرکت جدید"""

    def __init__(self, db_manager: DatabaseManager, parent=None):
        super().__init__(db_manager, parent)
        self.setWindowTitle("🏢 Create New Company")
        self.setFixedSize(500, 450)
        self.init_ui()

    def init_ui(self):
        """راه‌اندازی UI"""
        layout = QVBoxLayout()
        layout.setSpacing(15)

        # عنوان
        title_label = QLabel("🏢 Create New Company")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title_label)

        # فرم اطلاعات شرکت
        form_group = QGroupBox("Company Information")
        form_layout = QGridLayout()
        form_layout.setSpacing(10)

        # نام شرکت
        form_layout.addWidget(QLabel("Company Name*:"), 0, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter company name")
        form_layout.addWidget(self.name_edit, 0, 1)

        # کد شرکت
        form_layout.addWidget(QLabel("Company Code*:"), 1, 0)
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("Enter unique code")
        form_layout.addWidget(self.code_edit, 1, 1)

        # آدرس
        form_layout.addWidget(QLabel("Address:"), 2, 0)
        self.address_edit = QTextEdit()
        self.address_edit.setMaximumHeight(80)
        form_layout.addWidget(self.address_edit, 2, 1)

        # اطلاعات تماس
        form_layout.addWidget(QLabel("Contact Person:"), 3, 0)
        self.contact_edit = QLineEdit()
        self.contact_edit.setPlaceholderText("Contact person name")
        form_layout.addWidget(self.contact_edit, 3, 1)

        form_layout.addWidget(QLabel("Contact Email:"), 4, 0)
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("email@company.com")
        form_layout.addWidget(self.email_edit, 4, 1)

        form_layout.addWidget(QLabel("Contact Phone:"), 5, 0)
        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText("+1-234-567-8900")
        form_layout.addWidget(self.phone_edit, 5, 1)

        form_group.setLayout(form_layout)
        layout.addWidget(form_group)

        # دکمه‌ها
        button_layout = QHBoxLayout()

        self.create_btn = QPushButton("🏢 Create Company")
        self.create_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #3498db;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """
        )
        self.create_btn.clicked.connect(self.create_company)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #95a5a6;
                color: white;
                padding: 8px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """
        )
        self.cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(self.create_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def create_company(self):
        """ایجاد شرکت جدید"""
        try:
            # جمع‌آوری داده‌ها
            company_data = {
                "name": self.name_edit.text().strip(),
                "code": self.code_edit.text().strip(),
                "address": self.address_edit.toPlainText().strip(),
                "contact_person": self.contact_edit.text().strip(),
                "contact_email": self.email_edit.text().strip(),
                "contact_phone": self.phone_edit.text().strip(),
            }

            # اعتبارسنجی
            valid, error = self.validate_required_fields(
                {"name": company_data["name"], "code": company_data["code"]}
            )

            if not valid:
                self.show_error(error)
                return

            try:
                # بررسی وجود شرکت با همین کد
                session = self.db.create_session()
                existing = (
                    session.query(Company)
                    .filter(
                        (Company.name == company_data["name"])
                        | (Company.code == company_data["code"])
                    )
                    .first()
                )

                if existing:
                    self.show_error(
                        f"Company with name '{company_data['name']}' or code '{company_data['code']}' already exists!"
                    )
                    session.close()
                    return

                # ایجاد شرکت جدید
                new_company = Company(
                    name=company_data["name"],
                    code=company_data["code"],
                    address=company_data["address"] or None,
                    contact_person=company_data["contact_person"] or None,
                    contact_email=company_data["contact_email"] or None,
                    contact_phone=company_data["contact_phone"] or None,
                )

                session.add(new_company)
                session.commit()
                
                self.created_id = new_company.id  # استفاده از created_id از کلاس پایه
                self.result = {
                    "company_id": new_company.id,
                    "company_name": new_company.name,
                    "action": "create_company"
                }
                
                self.accept()  # بستن دیالوگ

            except Exception as e:
                logger.error(f"Error creating company: {e}")
                self.show_error(f"Error creating company: {str(e)}")
                session.rollback()
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Error in create_company: {e}")
            self.show_error(f"Error: {str(e)}")

    def get_result(self):
        """دریافت نتیجه ایجاد شرکت"""
        return self.result
        
class NewProjectDialog(BaseHierarchyDialog):
    """دیالوگ ایجاد پروژه جدید"""

    def __init__(self, db_manager: DatabaseManager, parent=None):
        super().__init__(db_manager, parent)
        self.setWindowTitle("📁 Create New Project")
        self.setFixedSize(600, 550)
        self.created_project_id = None
        self.init_ui()
        self.load_companies()

    def init_ui(self):
        """راه‌اندازی UI"""
        layout = QVBoxLayout()
        layout.setSpacing(15)

        # عنوان
        title_label = QLabel("📁 Create New Project")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title_label)

        # انتخاب شرکت
        company_group = QGroupBox("Select Company")
        company_layout = QHBoxLayout()

        company_layout.addWidget(QLabel("Company*:"))
        self.company_combo = QComboBox()
        self.company_combo.setMinimumWidth(300)
        company_layout.addWidget(self.company_combo)

        company_group.setLayout(company_layout)
        layout.addWidget(company_group)

        # فرم اطلاعات پروژه
        form_group = QGroupBox("Project Information")
        form_layout = QGridLayout()
        form_layout.setSpacing(10)

        # نام پروژه
        form_layout.addWidget(QLabel("Project Name*:"), 0, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter project name")
        form_layout.addWidget(self.name_edit, 0, 1)

        # کد پروژه
        form_layout.addWidget(QLabel("Project Code*:"), 1, 0)
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("Enter unique code")
        form_layout.addWidget(self.code_edit, 1, 1)

        # محل پروژه
        form_layout.addWidget(QLabel("Location:"), 2, 0)
        self.location_edit = QTextEdit()
        self.location_edit.setMaximumHeight(70)
        form_layout.addWidget(self.location_edit, 2, 1)

        # تاریخ‌ها
        form_layout.addWidget(QLabel("Start Date:"), 3, 0)
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(QDate.currentDate())
        form_layout.addWidget(self.start_date_edit, 3, 1)

        form_layout.addWidget(QLabel("End Date:"), 4, 0)
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(QDate.currentDate().addMonths(6))
        form_layout.addWidget(self.end_date_edit, 4, 1)

        # وضعیت
        form_layout.addWidget(QLabel("Status:"), 5, 0)
        self.status_combo = QComboBox()
        self.status_combo.addItems(
            ["Planning", "Active", "On Hold", "Completed", "Cancelled"]
        )
        form_layout.addWidget(self.status_combo, 5, 1)

        # مدیر پروژه
        form_layout.addWidget(QLabel("Project Manager:"), 6, 0)
        self.manager_edit = QLineEdit()
        self.manager_edit.setPlaceholderText("Project manager name")
        form_layout.addWidget(self.manager_edit, 6, 1)

        # بودجه
        form_layout.addWidget(QLabel("Budget ($):"), 7, 0)
        budget_layout = QHBoxLayout()
        self.budget_edit = QDoubleSpinBox()
        self.budget_edit.setRange(0, 1000000000)
        self.budget_edit.setValue(0.0)
        self.budget_edit.setPrefix("$ ")
        self.budget_edit.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.budget_edit.setMinimumWidth(150)
        budget_layout.addWidget(self.budget_edit)
        budget_layout.addStretch()
        form_layout.addLayout(budget_layout, 7, 1)

        # واحد پول
        form_layout.addWidget(QLabel("Currency:"), 8, 0)
        self.currency_combo = QComboBox()
        self.currency_combo.addItems(["USD", "EUR", "GBP", "CAD", "AUD", "IRR"])
        self.currency_combo.setCurrentText("USD")
        form_layout.addWidget(self.currency_combo, 8, 1)

        form_group.setLayout(form_layout)
        layout.addWidget(form_group)

        # دکمه‌ها
        button_layout = QHBoxLayout()

        self.create_btn = QPushButton("📁 Create Project")
        self.create_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #2ecc71;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
        """
        )
        self.create_btn.clicked.connect(self.create_project)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #95a5a6;
                color: white;
                padding: 8px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """
        )
        self.cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(self.create_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def load_companies(self):
        """بارگذاری شرکت‌ها از دیتابیس"""
        try:
            session = self.db.create_session()
            companies = session.query(Company).order_by(Company.name).all()

            self.company_combo.clear()
            for company in companies:
                self.company_combo.addItem(
                    f"{company.name} ({company.code})", company.id
                )

            session.close()
        except Exception as e:
            logger.error(f"Error loading companies: {e}")

    def create_project(self):
        """ایجاد پروژه جدید"""
        try:
            # جمع‌آوری داده‌ها
            company_id = self.company_combo.currentData()
            if not company_id:
                self.show_error("Please select a company!")
                return

            project_data = {
                "company_id": company_id,
                "name": self.name_edit.text().strip(),
                "code": self.code_edit.text().strip(),
                "location": self.location_edit.toPlainText().strip(),
                "start_date": self.start_date_edit.date().toString("yyyy-MM-dd"),
                "end_date": self.end_date_edit.date().toString("yyyy-MM-dd"),
                "status": self.status_combo.currentText(),
                "manager": self.manager_edit.text().strip(),
                "budget": self.budget_edit.value(),
                "currency": self.currency_combo.currentText(),
            }

            # اعتبارسنجی
            valid, error = self.validate_required_fields(
                {"name": project_data["name"], "code": project_data["code"]}
            )

            if not valid:
                self.show_error(error)
                return

            # اعتبارسنجی تاریخ
            start_date = QDate.fromString(project_data["start_date"], "yyyy-MM-dd")
            end_date = QDate.fromString(project_data["end_date"], "yyyy-MM-dd")
            if start_date > end_date:
                self.show_error("End date must be after start date!")
                return

            session = self.db.create_session()
            try:
                # بررسی وجود پروژه با همین کد
                existing = (
                    session.query(Project)
                    .filter(
                        (Project.name == project_data["name"])
                        | (Project.code == project_data["code"])
                    )
                    .first()
                )

                if existing:
                    self.show_error(
                        f"Project with name '{project_data['name']}' or code '{project_data['code']}' already exists!"
                    )
                    return

                # ایجاد پروژه جدید
                new_project = Project(
                    company_id=project_data["company_id"],
                    name=project_data["name"],
                    code=project_data["code"],
                    location=project_data["location"] or None,
                    start_date=datetime.strptime(
                        project_data["start_date"], "%Y-%m-%d"
                    ).date(),
                    end_date=datetime.strptime(project_data["end_date"], "%Y-%m-%d").date(),
                    status=project_data["status"],
                    manager=project_data["manager"] or None,
                    budget=project_data["budget"],
                    currency=project_data["currency"],
                )

                session.add(new_project)
                session.commit()
                
                # **اصلاح این بخش - ذخیره نتیجه**
                self.created_id = new_project.id
                self.result = {
                    "project_id": new_project.id,
                    "project_name": new_project.name,
                    "company_id": project_data["company_id"],
                    "company_name": self.company_combo.currentText(),
                    "action": "create_project"
                }

                company_name = self.company_combo.currentText()

                self.show_success(
                    f"Project '{project_data['name']}' created successfully under {company_name}!"
                )

                self.accept()

            except Exception as e:
                logger.error(f"Error creating project: {e}", exc_info=True)
                self.show_error(f"Error creating project: {str(e)}")
                session.rollback()
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Error in create_project: {e}", exc_info=True)
            self.show_error(f"Error: {str(e)}")
        
class NewWellDialog(BaseHierarchyDialog):
    """دیالوگ ایجاد چاه جدید - نسخه کامل"""

    def __init__(self, db_manager: DatabaseManager, parent=None, project_id=None):
        super().__init__(db_manager, parent)
        self.project_id = project_id
        self.setWindowTitle("🛢️ Create New Well")
        self.setMinimumSize(700, 700)
        self.init_ui()
        self.load_projects()
        if project_id:
            self.select_project_by_id(project_id)
    def init_ui(self):
        """راه‌اندازی UI"""
        # Scroll area برای فرم طولانی
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(15)

        # عنوان
        title_label = QLabel("🛢️ Create New Well")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title_label)

        # انتخاب پروژه
        project_group = QGroupBox("Select Project")
        project_layout = QHBoxLayout()

        project_layout.addWidget(QLabel("Project*:"))
        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(350)
        self.project_combo.currentIndexChanged.connect(self.on_project_changed)
        project_layout.addWidget(self.project_combo)

        project_group.setLayout(project_layout)
        layout.addWidget(project_group)

        # اطلاعات اصلی چاه
        basic_group = QGroupBox("Basic Well Information")
        basic_layout = QGridLayout()
        basic_layout.setSpacing(10)

        row = 0

        # نام چاه
        basic_layout.addWidget(QLabel("Well Name*:"), row, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter well name")
        basic_layout.addWidget(self.name_edit, row, 1)

        row += 1

        # کد چاه
        basic_layout.addWidget(QLabel("Well Code*:"), row, 0)
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("Enter unique well code")
        basic_layout.addWidget(self.code_edit, row, 1)

        row += 1

        # نوع چاه
        basic_layout.addWidget(QLabel("Well Type*:"), row, 0)
        self.type_combo = QComboBox()
        self.type_combo.addItems(
            ["", "Exploration", "Development", "Appraisal", "Injection", "Observation"]
        )
        basic_layout.addWidget(self.type_combo, row, 1)

        row += 1

        # هدف چاه
        basic_layout.addWidget(QLabel("Purpose:"), row, 0)
        self.purpose_combo = QComboBox()
        self.purpose_combo.addItems(
            [
                "",
                "Oil Production",
                "Gas Production",
                "Water Injection",
                "Gas Injection",
                "Monitoring",
            ]
        )
        basic_layout.addWidget(self.purpose_combo, row, 1)

        row += 1

        # وضعیت چاه
        basic_layout.addWidget(QLabel("Status:"), row, 0)
        self.status_combo = QComboBox()
        self.status_combo.addItems(
            ["Planning", "Drilling", "Suspended", "Completed", "Abandoned", "Producing"]
        )
        basic_layout.addWidget(self.status_combo, row, 1)

        row += 1

        # محل و مختصات
        location_group = QGroupBox("Location & Coordinates")
        location_layout = QGridLayout()

        location_layout.addWidget(QLabel("Field Name:"), 0, 0)
        self.field_edit = QLineEdit()
        location_layout.addWidget(self.field_edit, 0, 1)

        location_layout.addWidget(QLabel("Location:"), 1, 0)
        self.location_edit = QTextEdit()
        self.location_edit.setMaximumHeight(60)
        location_layout.addWidget(self.location_edit, 1, 1)

        location_layout.addWidget(QLabel("Coordinates:"), 2, 0)
        self.coords_edit = QLineEdit()
        self.coords_edit.setPlaceholderText("e.g., 28.5, -88.5")
        location_layout.addWidget(self.coords_edit, 2, 1)

        location_group.setLayout(location_layout)
        basic_layout.addWidget(location_group, row, 0, 2, 2)

        row += 2

        # اطلاعات عمقی
        depth_group = QGroupBox("Depth Information")
        depth_layout = QGridLayout()

        depth_layout.addWidget(QLabel("Elevation (m):"), 0, 0)
        self.elevation_spin = QDoubleSpinBox()
        self.elevation_spin.setRange(-1000, 10000)
        self.elevation_spin.setDecimals(2)
        depth_layout.addWidget(self.elevation_spin, 0, 1)

        depth_layout.addWidget(QLabel("Water Depth (m):"), 1, 0)
        self.water_depth_spin = QDoubleSpinBox()
        self.water_depth_spin.setRange(0, 5000)
        self.water_depth_spin.setDecimals(2)
        depth_layout.addWidget(self.water_depth_spin, 1, 1)

        depth_layout.addWidget(QLabel("Target Depth (m):"), 2, 0)
        self.target_depth_spin = QDoubleSpinBox()
        self.target_depth_spin.setRange(0, 15000)
        self.target_depth_spin.setDecimals(2)
        depth_layout.addWidget(self.target_depth_spin, 2, 1)

        depth_layout.addWidget(QLabel("Spud Date:"), 3, 0)
        self.spud_date_edit = QDateEdit()
        self.spud_date_edit.setCalendarPopup(True)
        depth_layout.addWidget(self.spud_date_edit, 3, 1)

        depth_group.setLayout(depth_layout)
        basic_layout.addWidget(depth_group, row, 0, 2, 2)

        row += 2

        # Onshore/Offshore
        basic_layout.addWidget(QLabel("Environment:"), row, 0)
        self.environment_combo = QComboBox()
        self.environment_combo.addItems(["Onshore", "Offshore"])
        self.environment_combo.currentTextChanged.connect(self.on_environment_changed)
        basic_layout.addWidget(self.environment_combo, row, 1)

        row += 1

        # Rig Information
        rig_group = QGroupBox("Rig Information")
        rig_layout = QGridLayout()

        rig_layout.addWidget(QLabel("Rig Name:"), 0, 0)
        self.rig_name_edit = QLineEdit()
        rig_layout.addWidget(self.rig_name_edit, 0, 1)

        rig_layout.addWidget(QLabel("Rig Type:"), 1, 0)
        self.rig_type_combo = QComboBox()
        self.rig_type_combo.addItems(
            ["", "Land Rig", "Jackup", "Semi-submersible", "Drillship", "Barge"]
        )
        rig_layout.addWidget(self.rig_type_combo, 1, 1)

        rig_layout.addWidget(QLabel("Drilling Contractor:"), 2, 0)
        self.contractor_edit = QLineEdit()
        rig_layout.addWidget(self.contractor_edit, 2, 1)

        rig_group.setLayout(rig_layout)
        basic_layout.addWidget(rig_group, row, 0, 2, 2)

        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)

        # اطلاعات اضافی (در Tab Widget)
        self.tabs = QTabWidget()

        # Tab 1: Personnel
        personnel_tab = QWidget()
        personnel_layout = QGridLayout()

        personnel_layout.addWidget(QLabel("Operation Manager:"), 0, 0)
        self.op_manager_edit = QLineEdit()
        personnel_layout.addWidget(self.op_manager_edit, 0, 1)

        personnel_layout.addWidget(QLabel("Superintendent:"), 1, 0)
        self.superintendent_edit = QLineEdit()
        personnel_layout.addWidget(self.superintendent_edit, 1, 1)

        personnel_layout.addWidget(QLabel("Day Supervisor:"), 2, 0)
        self.supervisor_day_edit = QLineEdit()
        personnel_layout.addWidget(self.supervisor_day_edit, 2, 1)

        personnel_layout.addWidget(QLabel("Night Supervisor:"), 3, 0)
        self.supervisor_night_edit = QLineEdit()
        personnel_layout.addWidget(self.supervisor_night_edit, 3, 1)

        personnel_tab.setLayout(personnel_layout)
        self.tabs.addTab(personnel_tab, "👥 Personnel")

        # Tab 2: Technical
        technical_tab = QWidget()
        technical_layout = QGridLayout()

        technical_layout.addWidget(QLabel("Well Shape:"), 0, 0)
        self.well_shape_combo = QComboBox()
        self.well_shape_combo.addItems(
            ["", "Vertical", "Deviated", "Horizontal", "S-shaped", "J-shaped"]
        )
        technical_layout.addWidget(self.well_shape_combo, 0, 1)

        technical_layout.addWidget(QLabel("KOP1 (m):"), 1, 0)
        self.kop1_spin = QDoubleSpinBox()
        self.kop1_spin.setRange(0, 10000)
        self.kop1_spin.setDecimals(2)
        technical_layout.addWidget(self.kop1_spin, 1, 1)

        technical_layout.addWidget(QLabel("KOP2 (m):"), 2, 0)
        self.kop2_spin = QDoubleSpinBox()
        self.kop2_spin.setRange(0, 10000)
        self.kop2_spin.setDecimals(2)
        technical_layout.addWidget(self.kop2_spin, 2, 1)

        technical_layout.addWidget(QLabel("Formation:"), 3, 0)
        self.formation_edit = QLineEdit()
        technical_layout.addWidget(self.formation_edit, 3, 1)

        technical_tab.setLayout(technical_layout)
        self.tabs.addTab(technical_tab, "🔧 Technical")

        # Tab 3: Additional Info
        additional_tab = QWidget()
        additional_layout = QGridLayout()

        additional_layout.addWidget(QLabel("Client:"), 0, 0)
        self.client_edit = QLineEdit()
        additional_layout.addWidget(self.client_edit, 0, 1)

        additional_layout.addWidget(QLabel("Client Representative:"), 1, 0)
        self.client_rep_edit = QLineEdit()
        additional_layout.addWidget(self.client_rep_edit, 1, 1)

        additional_layout.addWidget(QLabel("Operator:"), 2, 0)
        self.operator_edit = QLineEdit()
        additional_layout.addWidget(self.operator_edit, 2, 1)

        additional_layout.addWidget(QLabel("Report No.:"), 3, 0)
        self.report_no_edit = QLineEdit()
        additional_layout.addWidget(self.report_no_edit, 3, 1)

        additional_tab.setLayout(additional_layout)
        self.tabs.addTab(additional_tab, "📄 Additional")

        layout.addWidget(self.tabs)

        # اهداف و توضیحات
        objectives_group = QGroupBox("Objectives & Notes")
        objectives_layout = QVBoxLayout()

        self.objectives_edit = QTextEdit()
        self.objectives_edit.setMaximumHeight(100)
        self.objectives_edit.setPlaceholderText("Enter well objectives and notes...")
        objectives_layout.addWidget(self.objectives_edit)

        objectives_group.setLayout(objectives_layout)
        layout.addWidget(objectives_group)

        # دکمه‌ها
        button_layout = QHBoxLayout()

        self.create_btn = QPushButton("🛢️ Create Well")
        self.create_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """
        )
        self.create_btn.clicked.connect(self.create_well)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #95a5a6;
                color: white;
                padding: 10px;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """
        )
        self.cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(self.create_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)

        scroll_area.setWidget(container)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(scroll_area)

        # تنظیم پروژه اولیه اگر مشخص شده باشد
        if self.project_id:
            self.select_project_by_id(self.project_id)

    def load_projects(self):
        """بارگذاری پروژه‌ها از دیتابیس"""
        try:
            session = self.db.create_session()
            projects = session.query(Project).order_by(Project.name).all()

            self.project_combo.clear()
            
            for project in projects:
                company_name = project.company.name if project.company else "Unknown"
                display_text = f"{project.name} ({company_name})"
                self.project_combo.addItem(display_text, project.id)
                logger.debug(f"Added project: {display_text}, ID: {project.id}")

            session.close()
        except Exception as e:
            logger.error(f"Error loading projects: {e}", exc_info=True)

    def select_project_by_id(self, project_id):
        """انتخاب پروژه بر اساس ID"""
        for i in range(self.project_combo.count()):
            combo_data = self.project_combo.itemData(i)
            if combo_data == project_id:
                self.project_combo.setCurrentIndex(i)
                return
        
        logger.warning(f"Project ID {project_id} not found in combo box")

    def on_project_changed(self, index):
        """هنگام تغییر پروژه - پیشنهاد خودکار کد چاه"""
        project_id = self.project_combo.itemData(index)
        if not project_id or not hasattr(self, 'db') or not self.db:
            return
        try:
            session = self.db.create_session()
            from core.database import Project
            proj = session.query(Project).filter(Project.id == project_id).first()
            if proj and getattr(proj, 'code', None) and not self.code_edit.text():
                self.code_edit.setText(f"{proj.code}-W01")
            session.close()
        except Exception as e:
            logger.debug(f"Error suggesting well code: {e}")

    def on_environment_changed(self, environment):
        """هنگام تغییر محیط (Onshore/Offshore)"""
        if environment == "Offshore":
            self.water_depth_spin.setEnabled(True)
            self.water_depth_spin.setValue(100.0)  # مقدار پیش‌فرض
        else:
            self.water_depth_spin.setEnabled(False)
            self.water_depth_spin.setValue(0.0)

    def create_well(self):
        """ایجاد چاه جدید"""
        try:
            # جمع‌آوری داده‌ها
            project_id = self.project_combo.currentData()
            if not project_id:
                self.show_error("Please select a project!")
                return
                        
            well_data = {
                "project_id": project_id,
                "name": self.name_edit.text().strip(),
                "code": self.code_edit.text().strip(),
                "well_type": self.type_combo.currentText(),
                "purpose": self.purpose_combo.currentText(),
                "status": self.status_combo.currentText(),
                "well_type_field": self.environment_combo.currentText(),
                "field_name": self.field_edit.text().strip(),
                "location": self.location_edit.toPlainText().strip(),
                "coordinates": self.coords_edit.text().strip(),
                "elevation": self.elevation_spin.value(),
                "water_depth": self.water_depth_spin.value(),
                "target_depth": self.target_depth_spin.value(),
                "spud_date": self.spud_date_edit.date().toString("yyyy-MM-dd"),
                "rig_name": self.rig_name_edit.text().strip(),
                "rig_type": self.rig_type_combo.currentText(),
                "drilling_contractor": self.contractor_edit.text().strip(),
                "operation_manager": self.op_manager_edit.text().strip(),
                "superintendent": self.superintendent_edit.text().strip(),
                "supervisor_day": self.supervisor_day_edit.text().strip(),
                "supervisor_night": self.supervisor_night_edit.text().strip(),
                "well_shape": self.well_shape_combo.currentText(),
                "kop1": self.kop1_spin.value(),
                "kop2": self.kop2_spin.value(),
                "formation": self.formation_edit.text().strip(),
                "client": self.client_edit.text().strip(),
                "client_rep": self.client_rep_edit.text().strip(),
                "operator": self.operator_edit.text().strip(),
                "report_no": self.report_no_edit.text().strip(),
                "objectives": self.objectives_edit.toPlainText().strip(),
            }

            # اعتبارسنجی فیلدهای ضروری
            valid, error = self.validate_required_fields(
                {
                    "name": well_data["name"],
                    "code": well_data["code"],
                    "well_type": well_data["well_type"],
                }
            )

            if not valid:
                self.show_error(error)
                return

            session = self.db.create_session()
            try:
                # بررسی وجود چاه با همین کد
                existing = (
                    session.query(Well)
                    .filter(
                        (Well.name == well_data["name"]) | (Well.code == well_data["code"])
                    )
                    .first()
                )

                if existing:
                    self.show_error(
                        f"Well with name '{well_data['name']}' or code '{well_data['code']}' already exists!"
                    )
                    return

                # ایجاد چاه جدید
                new_well = Well(
                    project_id=well_data["project_id"],
                    name=well_data["name"],
                    code=well_data["code"],
                    well_type=well_data["well_type"],
                    purpose=well_data["purpose"],
                    status=well_data["status"],
                    well_type_field=well_data["well_type_field"],
                    field_name=well_data["field_name"] or None,
                    location=well_data["location"] or None,
                    coordinates=well_data["coordinates"] or None,
                    elevation=well_data["elevation"],
                    water_depth=well_data["water_depth"],
                    target_depth=well_data["target_depth"],
                    rig_name=well_data["rig_name"] or None,
                    rig_type=well_data["rig_type"] or None,
                    drilling_contractor=well_data["drilling_contractor"] or None,
                    operation_manager=well_data["operation_manager"] or None,
                    superintendent=well_data["superintendent"] or None,
                    supervisor_day=well_data["supervisor_day"] or None,
                    supervisor_night=well_data["supervisor_night"] or None,
                    well_shape=well_data["well_shape"] or None,
                    kop1=well_data["kop1"],
                    kop2=well_data["kop2"],
                    formation=well_data["formation"] or None,
                    client=well_data["client"] or None,
                    client_rep=well_data["client_rep"] or None,
                    operator=well_data["operator"] or None,
                    report_no=well_data["report_no"] or None,
                    objectives=well_data["objectives"] or None,
                )

                # تاریخ spud
                if well_data["spud_date"]:
                    new_well.spud_date = datetime.strptime(
                        well_data["spud_date"], "%Y-%m-%d"
                    ).date()

                session.add(new_well)
                session.commit()
                
                # **ذخیره نتیجه - این بخش مهم است**
                self.created_id = new_well.id
                self.result = {
                    "well_id": new_well.id,
                    "well_name": new_well.name,
                    "project_id": well_data["project_id"],
                    "project_name": self.project_combo.currentText(),
                    "action": "create_well"
                }
                
                self.show_success(
                    f"Well '{well_data['name']}' created successfully!"
                )

                self.accept()

            except Exception as e:
                logger.error(f"Error creating well: {e}", exc_info=True)
                self.show_error(f"Error creating well: {str(e)}")
                session.rollback()
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Error in create_well: {e}", exc_info=True)
            self.show_error(f"Error: {str(e)}")

    def get_result(self):
        """دریافت نتیجه - برای دیباگ"""
        return self.result

class NewSectionDialog(BaseHierarchyDialog):
    """دیالوگ ایجاد سکشن جدید با ورود دستی روزهای برنامه"""

    def __init__(self, db_manager: DatabaseManager, parent=None, well_id=None):
        super().__init__(db_manager, parent)
        self.well_id = well_id
        self.created_id = None
        self.setWindowTitle("📊 Create New Section")
        self.setFixedSize(550, 600)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)

        title_label = QLabel("📊 Create New Section")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title_label)

        form_group = QGroupBox("Section Information")
        form_layout = QGridLayout()
        form_layout.setSpacing(10)

        # نام سکشن
        form_layout.addWidget(QLabel("Section Name*:"), 0, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., Surface, Intermediate, Production")
        form_layout.addWidget(self.name_edit, 0, 1)

        # کد سکشن
        form_layout.addWidget(QLabel("Section Code:"), 1, 0)
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText('e.g., 26", 17½", 12¼"')
        form_layout.addWidget(self.code_edit, 1, 1)

        # عمق از
        form_layout.addWidget(QLabel("Depth From (m)*:"), 2, 0)
        self.depth_from_spin = QDoubleSpinBox()
        self.depth_from_spin.setRange(0, 20000)
        self.depth_from_spin.setDecimals(2)
        form_layout.addWidget(self.depth_from_spin, 2, 1)

        # عمق تا
        form_layout.addWidget(QLabel("Depth To (m)*:"), 3, 0)
        self.depth_to_spin = QDoubleSpinBox()
        self.depth_to_spin.setRange(0, 20000)
        self.depth_to_spin.setDecimals(2)
        form_layout.addWidget(self.depth_to_spin, 3, 1)

        # ========== ورود دستی روزهای برنامه ==========
        form_layout.addWidget(QLabel("Planned Days (days)*:"), 4, 0)
        self.planned_days_spin = QDoubleSpinBox()
        self.planned_days_spin.setRange(0.1, 1000)
        self.planned_days_spin.setDecimals(1)
        self.planned_days_spin.setValue(0.0)
        self.planned_days_spin.setToolTip("Enter the planned duration in days for this section")
        form_layout.addWidget(self.planned_days_spin, 4, 1)

        form_layout.addWidget(QLabel("Estimated ROP (m/day):"), 5, 0)
        self.estimated_rop_label = QLabel("0.0")
        self.estimated_rop_label.setStyleSheet("font-weight: bold; color: #3498db;")
        form_layout.addWidget(self.estimated_rop_label, 5, 1)

        # قطر اسمی
        form_layout.addWidget(QLabel("Nominal Diameter (in):"), 6, 0)
        self.diameter_spin = QDoubleSpinBox()
        self.diameter_spin.setRange(0, 100)
        self.diameter_spin.setDecimals(2)
        form_layout.addWidget(self.diameter_spin, 6, 1)

        # سایز حفاری
        form_layout.addWidget(QLabel("Hole Size (in):"), 7, 0)
        self.hole_size_spin = QDoubleSpinBox()
        self.hole_size_spin.setRange(0, 100)
        self.hole_size_spin.setDecimals(2)
        form_layout.addWidget(self.hole_size_spin, 7, 1)

        # هدف
        form_layout.addWidget(QLabel("Purpose:"), 8, 0)
        self.purpose_combo = QComboBox()
        self.purpose_combo.addItems([
            "", "Surface Casing", "Intermediate Casing", "Production Casing",
            "Liner", "Open Hole", "Side Track", "Abandonment"
        ])
        form_layout.addWidget(self.purpose_combo, 8, 1)

        # توضیحات
        form_layout.addWidget(QLabel("Description:"), 9, 0)
        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(80)
        form_layout.addWidget(self.description_edit, 9, 1)

        form_group.setLayout(form_layout)
        layout.addWidget(form_group)

        # دکمه‌ها
        button_layout = QHBoxLayout()
        self.create_btn = QPushButton("📊 Create Section")
        self.create_btn.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        self.create_btn.clicked.connect(self.create_section)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(self.create_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        self.depth_from_spin.valueChanged.connect(self.update_estimated_rop)
        self.depth_to_spin.valueChanged.connect(self.update_estimated_rop)
        self.planned_days_spin.valueChanged.connect(self.update_estimated_rop)

    def update_estimated_rop(self):
        """بروزرسانی تخمین ROP (اختیاری) بر اساس عمق و روزهای وارد شده"""
        depth_from = self.depth_from_spin.value()
        depth_to = self.depth_to_spin.value()
        days = self.planned_days_spin.value()
        if days > 0 and depth_to > depth_from:
            rop = (depth_to - depth_from) / days
            self.estimated_rop_label.setText(f"{rop:.1f}")
        else:
            self.estimated_rop_label.setText("0.0")

    def create_section(self):
        name = self.name_edit.text().strip()
        depth_from = self.depth_from_spin.value()
        depth_to = self.depth_to_spin.value()
        planned_days = self.planned_days_spin.value()

        if not name:
            QMessageBox.warning(self, "Validation Error", "Section name is required!")
            return

        if depth_from >= depth_to:
            QMessageBox.warning(self, "Validation Error", "Depth To must be greater than Depth From!")
            return

        if planned_days <= 0:
            QMessageBox.warning(self, "Validation Error", "Planned Days must be greater than zero!")
            return

        estimated_rop = (depth_to - depth_from) / planned_days if planned_days > 0 else 0

        section_data = {
            "well_id": self.well_id,
            "name": name,
            "code": self.code_edit.text().strip(),
            "depth_from": depth_from,
            "depth_to": depth_to,
            "diameter": self.diameter_spin.value(),
            "hole_size": self.hole_size_spin.value(),
            "purpose": self.purpose_combo.currentText(),
            "description": self.description_edit.toPlainText().strip(),
            "planned_days": planned_days,
            "planned_rop": estimated_rop, 
        }

        try:
            result = self.db.save_section(section_data)
            if result:
                self.created_id = result
                self.accept()
            else:
                QMessageBox.critical(self, "Error", "Failed to create section!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error creating section: {str(e)}")

class NewDailyReportDialog(BaseHierarchyDialog):
    """دیالوگ ایجاد گزارش روزانه جدید"""

    def __init__(self, db_manager: DatabaseManager, parent=None, section_id=None):
        super().__init__(db_manager, parent)
        self.section_id = section_id
        self.setWindowTitle("📅 Create New Daily Report")
        self.setFixedSize(500, 400)
        self.init_ui()
        self.load_section_info()

    def load_section_info(self):
        """بارگذاری اطلاعات سکشن برای نمایش"""
        try:
            session = self.db.create_session()
            section = (
                session.query(Section).filter(Section.id == self.section_id).first()
            )
            if section:
                well = section.well
                project = well.project

                # نمایش اطلاعات
                info_text = f"""
                <b>Section:</b> {section.name}<br>
                <b>Well:</b> {well.name}<br>
                <b>Project:</b> {project.name}
                """
                if hasattr(self, 'section_info_label'):
                    self.section_info_label.setText(info_text)

            session.close()
        except Exception as e:
            logger.error(f"Error loading section info: {e}")

    def init_ui(self):
        """راه‌اندازی UI"""
        layout = QVBoxLayout()
        layout.setSpacing(15)

        # عنوان
        title_label = QLabel("📅 Create New Daily Report")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title_label)

        # اطلاعات گزارش
        form_group = QGroupBox("Report Information")
        form_layout = QGridLayout()
        form_layout.setSpacing(10)

        # شماره گزارش (اتوماتیک)
        form_layout.addWidget(QLabel("Report Number:"), 0, 0)
        self.report_number_spin = QSpinBox()
        self.report_number_spin.setMinimum(1)
        self.report_number_spin.setMaximum(9999)
        form_layout.addWidget(self.report_number_spin, 0, 1)

        # تاریخ گزارش
        form_layout.addWidget(QLabel("Report Date*:"), 1, 0)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        form_layout.addWidget(self.date_edit, 1, 1)

        # کپی از روز قبل
        self.copy_previous_cb = QCheckBox("Copy data from previous day")
        self.copy_previous_cb.setChecked(False)
        form_layout.addWidget(self.copy_previous_cb, 2, 0, 1, 2)

        # توضیحات
        form_layout.addWidget(QLabel("Remarks:"), 3, 0)
        self.remarks_edit = QTextEdit()
        self.remarks_edit.setMaximumHeight(80)
        form_layout.addWidget(self.remarks_edit, 3, 1)

        form_group.setLayout(form_layout)
        layout.addWidget(form_group)

        # دکمه‌ها
        button_layout = QHBoxLayout()

        self.create_btn = QPushButton("📅 Create Report")
        self.create_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #1abc9c;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #16a085;
            }
        """
        )
        self.create_btn.clicked.connect(self.create_daily_report)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(self.create_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        # پر کردن شماره گزارش به صورت اتوماتیک
        self.load_next_report_number()

    def load_next_report_number(self):
        """بارگذاری شماره گزارش بعدی"""
        try:
            session = self.db.create_session()
            last_report = (
                session.query(DailyReport)
                .filter(DailyReport.section_id == self.section_id)
                .order_by(DailyReport.report_number.desc())
                .first()
            )

            if last_report:
                self.report_number_spin.setValue(last_report.report_number + 1)
            else:
                self.report_number_spin.setValue(1)

            session.close()
        except Exception as e:
            logger.error(f"Error loading next report number: {e}")

    def _copy_all_report_data(self, session, source_report_id, target_report_id):
        """
        کپی تمام داده‌های گزارش – با استفاده از .all() برای همه جداول
        (به جز جداول موجودی که منطق خاص دارند)
        """
        from core.database import (
            TimeLog24H, TimeLogMorning, DrillingParameters, MudReport,
            CementReport, CasingReport, BitReport, BHAReport, DownholeEquipment,
            FormationReport, LogisticsPersonnel, ServiceCompanyPOB, FuelWaterInventory,
            BulkMaterials, TransportLog, TransportNotes, SafetyReport, BOPComponent,
            WasteRecord, ServiceCompany, ServiceNote, MaterialRequest, EquipmentLog,
            SevenDaysLookahead, TripSheetEntry, SurveyPoint, WellboreSchematic
        )
        from datetime import date, timedelta
        import logging
        logger = logging.getLogger(__name__)

        # 1. TimeLogMorning -> TimeLog24H
        logs_morning = session.query(TimeLogMorning).filter(TimeLogMorning.report_id == source_report_id).all()
        for log in logs_morning:
            new_log = TimeLog24H(
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

        # 2. لیست جداولی که باید با .all() و حلقه کپی شوند
        tables = {
            'DrillingParameters': DrillingParameters,
            'MudReport': MudReport,
            'CementReport': CementReport,
            'CasingReport': CasingReport,
            'BitReport': BitReport,
            'BHAReport': BHAReport,
            'DownholeEquipment': DownholeEquipment,
            'FormationReport': FormationReport,
            'SafetyReport': SafetyReport,
            'WellboreSchematic': WellboreSchematic,
            'TripSheetEntry': TripSheetEntry,
            'SurveyPoint': SurveyPoint,
            'LogisticsPersonnel': LogisticsPersonnel,
            'ServiceCompanyPOB': ServiceCompanyPOB,
            'BulkMaterials': BulkMaterials,
            'TransportLog': TransportLog,
            'ServiceCompany': ServiceCompany,
            'ServiceNote': ServiceNote,
            'MaterialRequest': MaterialRequest,
            'EquipmentLog': EquipmentLog,
            'BOPComponent': BOPComponent,
            'WasteRecord': WasteRecord,
        }

        for name, model in tables.items():
            records = session.query(model).filter(model.report_id == source_report_id).all()
            for rec in records:
                # ایجاد دیکشنری از داده‌ها به جز id و report_id (برای جداول معمولی)
                if name in ('FuelWaterInventory', 'SevenDaysLookahead'):
                    continue  # این جداول جداگانه پردازش می‌شوند
                # برای سایر جداول، همه فیلدها را کپی می‌کنیم
                data = {c.name: getattr(rec, c.name) for c in model.__table__.columns
                        if c.name not in ('id', 'report_id')}
                data['report_id'] = target_report_id
                # تنظیم تاریخ برای برخی جداول
                if name == 'SafetyReport':
                    data['report_date'] = date.today()
                elif name == 'WellboreSchematic':
                    data['report_date'] = date.today()
                new_rec = model(**data)
                session.add(new_rec)

        # 3. FuelWaterInventory (فقط موجودی نهایی روز قبل به عنوان stock جدید)
        fw_records = session.query(FuelWaterInventory).filter(FuelWaterInventory.report_id == source_report_id).all()
        for fw in fw_records:
            new_fw = FuelWaterInventory(
                well_id=fw.well_id,
                section_id=fw.section_id,
                report_id=target_report_id,
                report_date=date.today(),
                fuel_type=fw.fuel_type,
                fuel_consumed=0.0,
                fuel_stock=fw.fuel_remaining or fw.fuel_stock,
                fuel_received=0.0,
                water_consumed=0.0,
                water_stock=fw.water_remaining or fw.water_stock,
                water_received=0.0,
                fuel_remaining=fw.fuel_remaining or fw.fuel_stock,
                water_remaining=fw.water_remaining or fw.water_stock,
                days_remaining_fuel=0.0,
                days_remaining_water=0.0,
                created_by=fw.created_by
            )
            session.add(new_fw)

        # 4. SevenDaysLookahead (حداکثر 7 روز اول)
        lookaheads = session.query(SevenDaysLookahead).filter(SevenDaysLookahead.report_id == source_report_id).all()
        today = date.today()
        for i, la in enumerate(lookaheads):
            if i >= 7:
                break
            new_la = SevenDaysLookahead(
                well_id=la.well_id,
                section_id=la.section_id,
                report_id=target_report_id,
                plan_date=today + timedelta(days=i),
                day_number=i+1,
                activity=la.activity,
                tools=la.tools,
                responsible=la.responsible,
                remarks=la.remarks,
                status=la.status,
                priority=la.priority,
                progress_percentage=la.progress_percentage,
                actual_start=la.actual_start,
                actual_end=la.actual_end,
                created_by=la.created_by
            )
            session.add(new_la)

        session.commit()
        

    def create_daily_report(self):
        if not self.section_id:
            self.show_error("No section selected!")
            return

        session = None
        try:
            session = self.db.create_session()
            section = session.query(Section).filter(Section.id == self.section_id).first()
            if not section:
                self.show_error("Section not found!")
                return

            report_date = self.date_edit.date().toPython()
            
            report_data = {
                "well_id": section.well_id,
                "section_id": self.section_id,
                "report_number": self.report_number_spin.value(),
                "report_date": report_date,
                "status": "Draft",
            }
            
            previous_report_id = None
            if self.copy_previous_cb.isChecked():
                previous_date = self.date_edit.date().addDays(-1).toPython()
                prev_report = session.query(DailyReport).filter(
                    DailyReport.section_id == self.section_id,
                    DailyReport.report_date == previous_date
                ).first()
                if prev_report:
                    report_data["depth_0000"] = prev_report.depth_2400 or 0
                    report_data["depth_0600"] = prev_report.depth_2400 or 0
                    report_data["rig_day"] = (prev_report.rig_day or 0) + 1
                    report_data["summary"] = prev_report.summary or ""
                    previous_report_id = prev_report.id
                else:
                    QMessageBox.information(self, "Info", "No previous report found. Creating an empty report.")
            
            session.close()
            session = None
            
            result = self.db.save_daily_report(report_data)
            
            if not result:
                self.show_error("Failed to create daily report!")
                return
            
            self.created_id = result.get("id")
            self.previous_report_id = previous_report_id  # این خط مهم است
            
            self.show_success(f"Daily Report #{result.get('report_number', 'N/A')} created successfully!")
            self.accept()
            
        except Exception as e:
            self.show_error(f"Error creating daily report: {str(e)}")
            logger.error(f"Error creating daily report: {e}")
        finally:
            if session:
                session.close()