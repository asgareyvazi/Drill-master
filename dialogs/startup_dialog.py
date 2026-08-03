"""
Startup Dialog - اولین صفحه هنگام اجرای برنامه
"""

import logging
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from core.database import DatabaseManager
from dialogs.hierarchy_dialogs import NewCompanyDialog, NewProjectDialog, NewWellDialog

logger = logging.getLogger(__name__)


class StartupDialog(QDialog):
    """دیالوگ شروع برنامه - انتخاب پروژه/چاه یا ایجاد جدید"""
    
    def __init__(self, db_manager: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.selected_well_id = None
        self.selected_project_id = None
        self.action = None  # 'load_well', 'load_project', 'create_company', 'create_project', 'create_well'
        
        self.setWindowTitle("DrillMaster - Welcome")
        self.setFixedSize(800, 600)
        self.setStyleSheet("""
            QDialog {
                background-color: #f8f9fa;
            }
            QLabel {
                color: #2c3e50;
            }
        """)
        
        self.init_ui()
        self.load_recent_data()
        
    def init_ui(self):
        """راه‌اندازی UI"""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(20)
        
        # Header با لوگو و عنوان
        header_layout = QHBoxLayout()
        
        # لوگو
        logo_label = QLabel("🛢️")
        logo_label.setStyleSheet("font-size: 48px;")
        header_layout.addWidget(logo_label)
        
        # عنوان
        title_layout = QVBoxLayout()
        
        title_label = QLabel("DrillMaster")
        title_label.setStyleSheet("font-size: 32px; font-weight: bold; color: #3498db;")
        title_layout.addWidget(title_label)
        
        subtitle_label = QLabel("Drilling Operations Management System")
        subtitle_label.setStyleSheet("font-size: 14px; color: #7f8c8d;")
        title_layout.addWidget(subtitle_label)
        
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        
        main_layout.addLayout(header_layout)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("background-color: #bdc3c7;")
        main_layout.addWidget(separator)
        
        # Tab Widget برای گزینه‌های مختلف
        self.tabs = QTabWidget()
        
        # Tab 1: Recent Projects/Wells
        recent_tab = self.create_recent_tab()
        self.tabs.addTab(recent_tab, "📂 Recent")
        
        # Tab 2: Create New
        create_tab = self.create_new_tab()
        self.tabs.addTab(create_tab, "➕ Create New")
        
        # Tab 3: Quick Start
        quick_tab = self.create_quick_tab()
        self.tabs.addTab(quick_tab, "⚡ Quick Start")
        
        main_layout.addWidget(self.tabs)
        
        # دکمه‌های پایین
        button_layout = QHBoxLayout()
        
        self.exit_btn = QPushButton("🚪 Exit")
        self.exit_btn.setMinimumWidth(100)
        self.exit_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.exit_btn)
        
        button_layout.addStretch()
        
        self.proceed_btn = QPushButton("🚀 Start DrillMaster")
        self.proceed_btn.setMinimumWidth(150)
        self.proceed_btn.setEnabled(False)
        self.proceed_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
            QPushButton:hover:enabled {
                background-color: #27ae60;
            }
        """)
        self.proceed_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.proceed_btn)
        
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
        
    def create_recent_tab(self):
        """ایجاد تب Recent"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # عنوان
        title_label = QLabel("📋 Recently Opened Projects & Wells")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title_label)
        
        # جدول پروژه‌های اخیر
        projects_label = QLabel("📁 Recent Projects")
        projects_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #3498db;")
        layout.addWidget(projects_label)
        
        self.projects_table = QTableWidget()
        self.projects_table.setColumnCount(4)
        self.projects_table.setHorizontalHeaderLabels(["Project", "Company", "Wells", "Last Accessed"])
        self.projects_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.projects_table.setMinimumHeight(150)
        self.projects_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.projects_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.projects_table.itemSelectionChanged.connect(self.on_project_selected)
        layout.addWidget(self.projects_table)
        
        # جدول چاه‌های اخیر
        wells_label = QLabel("🛢️ Recent Wells")
        wells_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #e74c3c;")
        layout.addWidget(wells_label)
        
        self.wells_table = QTableWidget()
        self.wells_table.setColumnCount(5)
        self.wells_table.setHorizontalHeaderLabels(["Well", "Project", "Company", "Type", "Last Accessed"])
        self.wells_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.wells_table.setMinimumHeight(200)
        self.wells_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.wells_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.wells_table.itemSelectionChanged.connect(self.on_well_selected)
        layout.addWidget(self.wells_table)
        
        # دکمه Refresh
        refresh_btn = QPushButton("🔄 Refresh List")
        refresh_btn.clicked.connect(self.load_recent_data)
        layout.addWidget(refresh_btn, alignment=Qt.AlignRight)
        
        tab.setLayout(layout)
        return tab
        
    def create_new_tab(self):
        """ایجاد تب Create New"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(20)
        
        # عنوان
        title_label = QLabel("🏗️ Create New")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # توضیح
        desc_label = QLabel("Choose what you want to create:")
        desc_label.setStyleSheet("font-size: 14px; color: #7f8c8d;")
        desc_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_label)
        
        # Grid Layout برای دکمه‌ها
        grid_layout = QGridLayout()
        grid_layout.setSpacing(15)
        
        # دکمه Company
        company_btn = QPushButton("🏢 New Company")
        company_btn.setMinimumHeight(80)
        company_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 8px;
                padding: 15px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        company_btn.clicked.connect(self.create_company)
        grid_layout.addWidget(company_btn, 0, 0)
        
        # دکمه Project
        project_btn = QPushButton("📁 New Project")
        project_btn.setMinimumHeight(80)
        project_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 8px;
                padding: 15px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
        """)
        project_btn.clicked.connect(self.create_project)
        grid_layout.addWidget(project_btn, 0, 1)
        
        # دکمه Well
        well_btn = QPushButton("🛢️ New Well")
        well_btn.setMinimumHeight(80)
        well_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 8px;
                padding: 15px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        well_btn.clicked.connect(self.create_well)
        grid_layout.addWidget(well_btn, 1, 0)
        
        # دکمه Complete Hierarchy
        complete_btn = QPushButton("📊 Complete Project")
        complete_btn.setMinimumHeight(80)
        complete_btn.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 8px;
                padding: 15px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        complete_btn.clicked.connect(self.create_complete_hierarchy)
        grid_layout.addWidget(complete_btn, 1, 1)
        
        layout.addLayout(grid_layout)
        
        # توضیح راهنما
        help_label = QLabel(
            "💡 Tip: Start by creating a Company, then add Projects, and finally add Wells to projects.\n"
            "Or use 'Complete Project' to create all three at once."
        )
        help_label.setStyleSheet("""
            QLabel {
                background-color: #f1c40f;
                color: #2c3e50;
                padding: 10px;
                border-radius: 5px;
                font-size: 13px;
            }
        """)
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        tab.setLayout(layout)
        return tab
        
    def create_quick_tab(self):
        """ایجاد تب Quick Start"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(20)
        
        # عنوان
        title_label = QLabel("⚡ Quick Start Templates")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # توضیح
        desc_label = QLabel("Start quickly with pre-configured templates:")
        desc_label.setStyleSheet("font-size: 14px; color: #7f8c8d;")
        desc_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_label)
        
        # لیست Template‌ها
        self.template_list = QListWidget()
        self.template_list.setMinimumHeight(250)
        
        templates = [
            {
                "name": "🏗️ Offshore Exploration Project",
                "description": "Complete setup for offshore exploration drilling",
                "icon": "🌊",
                "type": "offshore_exploration"
            },
            {
                "name": "🏔️ Onshore Development Project",
                "description": "Template for onshore development drilling",
                "icon": "⛰️",
                "type": "onshore_development"
            },
            {
                "name": "🔄 Workover Project",
                "description": "Setup for workover and re-entry operations",
                "icon": "🔧",
                "type": "workover"
            },
            {
                "name": "📊 Training Project",
                "description": "Sample project for training purposes",
                "icon": "🎓",
                "type": "training"
            }
        ]
        
        for template in templates:
            item = QListWidgetItem(f"{template['icon']} {template['name']}")
            item.setData(Qt.UserRole, template)
            item.setToolTip(template["description"])
            self.template_list.addItem(item)
            
        layout.addWidget(self.template_list)
        
        # دکمه‌ها
        btn_layout = QHBoxLayout()
        
        info_btn = QPushButton("ℹ️ Template Details")
        info_btn.clicked.connect(self.show_template_details)
        btn_layout.addWidget(info_btn)
        
        btn_layout.addStretch()
        
        use_template_btn = QPushButton("🚀 Use This Template")
        use_template_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
        """)
        use_template_btn.clicked.connect(self.use_template)
        btn_layout.addWidget(use_template_btn)
        
        layout.addLayout(btn_layout)
        
        tab.setLayout(layout)
        return tab
        
    def load_recent_data(self):
        """بارگذاری داده‌های اخیر"""
        try:
            # بارگذاری پروژه‌های اخیر
            session = self.db.create_session()
            
            # پروژه‌ها (10 مورد آخر)
            from core.database import Project, Company, Well
            from sqlalchemy import desc
            
            projects = session.query(Project).join(Company).order_by(
                desc(Project.updated_at)
            ).limit(10).all()
            
            self.projects_table.setRowCount(len(projects))
            for row, project in enumerate(projects):
                # تعداد چاه‌ها
                well_count = session.query(Well).filter(Well.project_id == project.id).count()
                
                self.projects_table.setItem(row, 0, QTableWidgetItem(project.name))
                self.projects_table.setItem(row, 1, QTableWidgetItem(project.company.name))
                self.projects_table.setItem(row, 2, QTableWidgetItem(str(well_count)))
                self.projects_table.setItem(row, 3, QTableWidgetItem(
                    project.updated_at.strftime("%Y-%m-%d") if project.updated_at else ""
                ))
                
                # ذخیره ID در data
                self.projects_table.item(row, 0).setData(Qt.UserRole, {
                    "type": "project",
                    "id": project.id
                })
                
            # چاه‌های اخیر (10 مورد آخر)
            wells = session.query(Well).join(Project).join(Company).order_by(
                desc(Well.updated_at)
            ).limit(10).all()
            
            self.wells_table.setRowCount(len(wells))
            for row, well in enumerate(wells):
                self.wells_table.setItem(row, 0, QTableWidgetItem(well.name))
                self.wells_table.setItem(row, 1, QTableWidgetItem(well.project.name))
                self.wells_table.setItem(row, 2, QTableWidgetItem(well.project.company.name))
                self.wells_table.setItem(row, 3, QTableWidgetItem(well.well_type or ""))
                self.wells_table.setItem(row, 4, QTableWidgetItem(
                    well.updated_at.strftime("%Y-%m-%d") if well.updated_at else ""
                ))
                
                # ذخیره ID در data
                self.wells_table.item(row, 0).setData(Qt.UserRole, {
                    "type": "well",
                    "id": well.id
                })
                
            session.close()
            
        except Exception as e:
            logger.error(f"Error loading recent data: {e}")
            
    def on_project_selected(self):
        """هنگام انتخاب پروژه"""
        selected_items = self.projects_table.selectedItems()
        if selected_items:
            item = selected_items[0]
            data = item.data(Qt.UserRole)
            if data and data["type"] == "project":
                self.selected_project_id = data["id"]
                self.selected_well_id = None
                self.action = "load_project"
                self.proceed_btn.setEnabled(True)
                self.proceed_btn.setText(f"📁 Load Project")
                
    def on_well_selected(self):
        """هنگام انتخاب چاه"""
        selected_items = self.wells_table.selectedItems()
        if selected_items:
            item = selected_items[0]
            data = item.data(Qt.UserRole)
            if data and data["type"] == "well":
                self.selected_well_id = data["id"]
                self.selected_project_id = None
                self.action = "load_well"
                self.proceed_btn.setEnabled(True)
                self.proceed_btn.setText(f"🛢️ Load Well")
                
    def create_company(self):
        """ایجاد شرکت جدید"""
        try:
            dialog = NewCompanyDialog(self.db, self)
            if dialog.exec():
                self.load_recent_data()
                self.tabs.setCurrentIndex(0)  # برو به تب Recent
                
        except Exception as e:
            logger.error(f"Error creating company: {e}")
            QMessageBox.critical(self, "Error", f"Failed to create company: {str(e)}")
            
    def create_well(self):
        """ایجاد چاه جدید و بارگذاری خودکار"""
        try:
            dialog = NewWellDialog(self.db, self)
            if dialog.exec():
                # دریافت ID چاه ساخته شده
                if hasattr(dialog, 'created_id') and dialog.created_id:
                    well_id = dialog.created_id
                elif hasattr(dialog, 'get_result'):
                    result = dialog.get_result()
                    well_id = result.get('well_id') if result else None
                else:
                    well_id = None
                
                if well_id:
                    # بستن دیالوگ Startup و ارسال نتیجه
                    self.selected_well_id = well_id
                    self.action = "load_well"
                    self.accept()  # بستن دیالوگ و رفتن به MainWindow
                else:
                    self.status_message("Well created but could not retrieve ID. Please open manually.")
                    
        except Exception as e:
            logger.error(f"Error creating well: {e}")
            QMessageBox.critical(self, "Error", f"Failed to create well: {str(e)}")

    def create_project(self):
        """ایجاد پروژه جدید و سپس چاه برای آن"""
        try:
            dialog = NewProjectDialog(self.db, self)
            if dialog.exec():
                result = dialog.get_result()
                if result and result.get('project_id'):
                    project_id = result['project_id']
                    
                    # بعد از ایجاد پروژه، دیالوگ ساخت چاه باز کن
                    well_dialog = NewWellDialog(self.db, self, project_id)
                    if well_dialog.exec():
                        well_result = well_dialog.get_result()
                        if well_result and well_result.get('well_id'):
                            self.selected_well_id = well_result['well_id']
                            self.action = "load_well"
                            self.accept()
                        else:
                            self.status_message("Project created but well creation failed.")
                    else:
                        # اگر کاربر چاه نساخت، فقط پروژه را لود کن
                        self.selected_project_id = project_id
                        self.action = "load_project"
                        self.accept()
                else:
                    self.status_message("Project creation failed.")
                    
        except Exception as e:
            logger.error(f"Error creating project: {e}")
            QMessageBox.critical(self, "Error", f"Failed to create project: {str(e)}")
            
    def create_complete_hierarchy(self):
        """ایجاد سلسله مراتب کامل - اصلاح شده"""
        try:
            company_id = None
            project_id = None
            well_id = None

            # 1. ایجاد شرکت
            company_dialog = NewCompanyDialog(self.db, self)
            if not company_dialog.exec():
                return  # کاربر کنسل کرد

            company_result = company_dialog.get_result()
            if not company_result or "company_id" not in company_result:
                QMessageBox.warning(self, "Warning", "Company creation failed.")
                return
            company_id = company_result["company_id"]

            # 2. ایجاد پروژه
            project_dialog = NewProjectDialog(self.db, self)
            for i in range(project_dialog.company_combo.count()):
                if project_dialog.company_combo.itemData(i) == company_id:
                    project_dialog.company_combo.setCurrentIndex(i)
                    break

            if not project_dialog.exec():
                return  # کاربر کنسل کرد

            project_result = project_dialog.get_result()
            if not project_result or "project_id" not in project_result:
                QMessageBox.warning(self, "Warning", "Project creation failed.")
                return
            project_id = project_result["project_id"]

            # 3. ایجاد چاه
            well_dialog = NewWellDialog(self.db, self, project_id)
            if not well_dialog.exec():
                return  # کاربر کنسل کرد

            well_result = well_dialog.get_result()
            if not well_result or "well_id" not in well_result:
                QMessageBox.warning(self, "Warning", "Well creation failed.")
                return
            well_id = well_result["well_id"]

            # نتیجه نهایی
            self.selected_well_id = well_id
            self.action = "load_well"
            self.proceed_btn.setEnabled(True)
            self.proceed_btn.setText(f"🛢️ Load Well")
            self.status_message("Complete hierarchy created successfully!")
            self.load_recent_data()
            self.tabs.setCurrentIndex(0)

        except Exception as e:
            logger.error(f"Error creating complete hierarchy: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to create hierarchy: {str(e)}")
    
    def show_template_details(self):
        """نمایش جزئیات template"""
        selected_items = self.template_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "Template", "Please select a template first.")
            return
            
        item = selected_items[0]
        template = item.data(Qt.UserRole)
        
        details = f"""
        <h3>{template['name']}</h3>
        <p>{template['description']}</p>
        
        <h4>Includes:</h4>
        <ul>
        <li>Pre-configured company structure</li>
        <li>Project with standard phases</li>
        <li>Sample well with typical parameters</li>
        <li>Standard reports and forms</li>
        <li>Predefined drilling parameters</li>
        </ul>
        
        <p><b>Note:</b> You can modify everything after creation.</p>
        """
        
        QMessageBox.information(self, "Template Details", details)
        
    def use_template(self):
        """استفاده از template"""
        selected_items = self.template_list.selectedItems()
        if not selected_items:
            return
            
        item = selected_items[0]
        template = item.data(Qt.UserRole)
        
        reply = QMessageBox.question(
            self,
            "Use Template",
            f"Do you want to create a new project using '{template['name']}' template?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                session = self.db.create_session()
                
                # ایمپورت کلاس‌های مورد نیاز
                from core.database import Company, Project, Well
                
                # ایجاد شرکت
                company = session.query(Company).filter(
                    Company.name.ilike(f"%{template['type']}%")
                ).first()
                
                if not company:
                    company = Company(
                        name=f"Template Company - {template['type']}",
                        code=f"TEMP_{template['type'].upper()}",
                        contact_person="Template Admin"
                    )
                    session.add(company)
                    session.flush()
                
                # ایجاد پروژه
                project = Project(
                    company_id=company.id,
                    name=f"{template['name']} Project",
                    code=f"{template['type'].upper()}_001",
                    status="Planning",
                    manager="Project Manager"
                )
                session.add(project)
                session.flush()
                
                # ایجاد چاه
                well = Well(
                    project_id=project.id,
                    name=f"{template['name']} Well",
                    code=f"{template['type'].upper()}_WELL_001",
                    well_type="Exploration" if "exploration" in template['type'] else "Development",
                    status="Planning"
                )
                session.add(well)
                session.commit()
                
                self.selected_well_id = well.id
                self.action = "load_well"
                self.proceed_btn.setEnabled(True)
                self.proceed_btn.setText(f"🛢️ Load Well")
                
                self.status_message(f"Template '{template['name']}' created successfully!")
                self.load_recent_data()
                self.tabs.setCurrentIndex(0)  # برو به تب Recent
                
            except Exception as e:
                logger.error(f"Error creating template: {e}")
                QMessageBox.critical(self, "Error", f"Failed to create template: {str(e)}")
                session.rollback()
            finally:
                try:
                    session.close()
                except:
                    pass
                    
    def status_message(self, message):
        """نمایش پیام status"""
        # نمایش پیام در یک MessageBox کوچک
        QMessageBox.information(self, "Status", message)
        
    def get_result(self):
        """دریافت نتیجه"""
        if self.action:
            result = {"action": self.action}
            if self.selected_well_id:
                result["well_id"] = self.selected_well_id
            if self.selected_project_id:
                result["project_id"] = self.selected_project_id
            return result
        return None