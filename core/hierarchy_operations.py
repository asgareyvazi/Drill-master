"""Hierarchy operations — delete, context menu, and tree management.

Extracted from main_window.py for maintainability. These functions operate
on the database and tree widget but are called from MainWindow.
"""

import logging
from PySide6.QtWidgets import QMessageBox, QMenu, QAction
from PySide6.QtCore import Qt

logger = logging.getLogger(__name__)


def check_delete_permission(status_manager=None) -> bool:
    """P0: Permission enforcement for all delete operations."""
    try:
        from core.permissions import permissions
        if permissions.is_viewer():
            if status_manager:
                status_manager.show_error("Hierarchy", "Viewer role is read-only: No Delete allowed")
            return False
        if not permissions.has_permission("can_delete_well") and not permissions.has_permission("can_delete_reports"):
            if status_manager:
                status_manager.show_error("Hierarchy", "Permission denied: delete requires can_delete_well or can_delete_reports")
            return False
    except Exception:
        pass
    return True


def delete_entity(db_manager, entity_type: str, entity_id: int, 
                  status_manager=None, parent=None, extra_data: dict = None) -> bool:
    """Generic delete with permission check, confirmation, audit logging.
    
    entity_type: 'company', 'project', 'well', 'section', 'report'
    Returns True if deleted successfully.
    """
    if not check_delete_permission(status_manager):
        return False
    
    labels = {
        'company': ('Company', 'this company and ALL its projects and wells'),
        'project': ('Project', 'this project and ALL its wells'),
        'well': ('Well', 'this well and ALL its reports and data'),
        'section': ('Section', 'this section and ALL its daily reports'),
        'report': ('Report', 'this daily report'),
    }
    
    label, desc = labels.get(entity_type, (entity_type, entity_type))
    
    reply = QMessageBox.question(
        parent, f"Delete {label}",
        f"Delete {desc}?\nThis cannot be undone!\n\nAtomic: all child data will be deleted in one transaction.",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No
    )
    if reply != QMessageBox.Yes:
        return False
    
    try:
        from core.database import Company, Project, Well, Section, DailyReport
        
        model_map = {
            'company': Company,
            'project': Project,
            'well': Well,
            'section': Section,
            'report': DailyReport,
        }
        
        model = model_map.get(entity_type)
        if not model:
            return False
        
        if entity_type == 'well':
            success = db_manager.delete_well(entity_id)
        elif entity_type == 'report':
            success = db_manager.delete_daily_report(entity_id)
        else:
            session = db_manager.create_session()
            try:
                obj = session.query(model).filter(model.id == entity_id).first()
                if obj:
                    name = getattr(obj, 'name', f'{label} {entity_id}')
                    session.delete(obj)
                    session.commit()
                    success = True
                    
                    # Audit log
                    try:
                        from core.permissions import permissions
                        db_manager.log_audit(
                            action="delete", entity_type=entity_type,
                            entity_id=entity_id, entity_name=str(name),
                            user_id=permissions.user_id, username=permissions.username,
                        )
                    except Exception:
                        pass
                else:
                    success = False
            except Exception as e:
                session.rollback()
                logger.error(f"Delete {entity_type} error: {e}")
                success = False
            finally:
                session.close()
        
        if success and status_manager:
            status_manager.show_success("Hierarchy", f"{label} deleted - atomic, no orphan")
        elif not success and status_manager:
            status_manager.show_error("Hierarchy", f"Failed to delete {label}")
        
        return success
        
    except Exception as e:
        logger.error(f"Delete {entity_type} error: {e}")
        if status_manager:
            status_manager.show_error("Hierarchy", f"Delete failed: {str(e)}")
        return False


def build_context_menu(item_data: dict, db_manager, parent=None) -> QMenu:
    """Build context menu for a tree item based on its type and data."""
    menu = QMenu(parent)
    item_type = item_data.get("type")
    item_id = item_data.get("id")
    
    if item_type == "company":
        act = QAction("📁 Add Project", parent)
        act.setData({"action": "add_project", "company_id": item_id})
        menu.addAction(act)
        
        del_act = QAction("🗑️ Delete Company", parent)
        del_act.setData({"action": "delete", "entity_type": "company", "entity_id": item_id})
        menu.addAction(del_act)
        
    elif item_type == "project":
        act = QAction("🛢️ Add Well", parent)
        act.setData({"action": "add_well", "project_id": item_id})
        menu.addAction(act)
        
        del_act = QAction("🗑️ Delete Project", parent)
        del_act.setData({"action": "delete", "entity_type": "project", "entity_id": item_id})
        menu.addAction(del_act)
        
    elif item_type == "well":
        act = QAction("📊 Add Section", parent)
        act.setData({"action": "add_section", "well_id": item_id})
        menu.addAction(act)
        
        del_act = QAction("🗑️ Delete Well", parent)
        del_act.setData({"action": "delete", "entity_type": "well", "entity_id": item_id})
        menu.addAction(del_act)
        
    elif item_type == "section":
        act = QAction("📅 Add Daily Report", parent)
        act.setData({"action": "add_report", "section_id": item_id})
        menu.addAction(act)
        
        act2 = QAction("📐 Open Section Data", parent)
        act2.setData({"action": "open_section", "section_id": item_id, "well_id": item_data.get("well_id")})
        menu.addAction(act2)
        
        del_act = QAction("🗑️ Delete Section", parent)
        del_act.setData({"action": "delete", "entity_type": "section", "entity_id": item_id})
        menu.addAction(del_act)
        
    elif item_type == "daily_report":
        del_act = QAction("🗑️ Delete Report", parent)
        del_act.setData({"action": "delete", "entity_type": "report", "entity_id": item_id})
        menu.addAction(del_act)
    
    menu.addSeparator()
    refresh_act = QAction("🔄 Refresh", parent)
    refresh_act.setData({"action": "refresh"})
    menu.addAction(refresh_act)
    
    return menu
