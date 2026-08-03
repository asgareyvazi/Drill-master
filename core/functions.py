# core/functions.py
"""
Core Functions - Centralized helper functions
بازنویسی شده: حذف متدهای بلااستفاده، نگه‌داشتن فقط موارد لازم
"""
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class CentralFunctions:
    """Centralized validation and helper functions"""

    def __init__(self, db_manager=None):
        self.db_manager = db_manager

    def validate_well_data(self, data: Dict) -> Dict[str, str]:
        """Validate well information data"""
        errors = {}
        required_fields = ["name", "project_id", "well_type"]
        for field in required_fields:
            if not data.get(field):
                errors[field] = f"{field.replace('_', ' ').title()} is required"

        numeric_fields = ["target_depth", "elevation", "water_depth"]
        for field in numeric_fields:
            if field in data and data[field]:
                try:
                    float(data[field])
                except (ValueError, TypeError):
                    errors[field] = f"{field.replace('_', ' ').title()} must be a number"
        return errors

    def validate_mud_data(self, data: Dict) -> Dict[str, str]:
        """Validate mud report data"""
        errors = {}
        if not data.get('mud_type'):
            errors['mud_type'] = "Mud type is required"

        numeric_fields = ['mw', 'pv', 'yp', 'ph']
        for field in numeric_fields:
            value = data.get(field)
            if value is not None:
                try:
                    float(value)
                except (ValueError, TypeError):
                    errors[field] = f"{field.upper()} must be a number"
        return errors

    def validate_drilling_data(self, data: Dict) -> Dict[str, str]:
        """Validate drilling parameters"""
        errors = {}
        required_fields = ['bit_no', 'bit_size', 'depth_in', 'depth_out']
        for field in required_fields:
            if not str(data.get(field, '')).strip():
                errors[field] = f"{field.replace('_', ' ').title()} is required"

        numeric_fields = ['bit_size', 'depth_in', 'depth_out', 'wob_min', 'wob_max',
                          'rpm_min', 'rpm_max', 'torque_min', 'torque_max']
        for field in numeric_fields:
            value = data.get(field)
            if value is not None and str(value).strip():
                try:
                    float(value)
                except (ValueError, TypeError):
                    errors[field] = f"{field.replace('_', ' ').title()} must be a number"

        depth_in = data.get('depth_in')
        depth_out = data.get('depth_out')
        if depth_in and depth_out:
            try:
                if float(depth_in) >= float(depth_out):
                    errors['depth'] = "Depth Out must be greater than Depth In"
            except (ValueError, TypeError):
                pass
        return errors

    def validate_date_range(self, start_date, end_date) -> str:
        """Validate date range"""
        if start_date and end_date and start_date > end_date:
            return "Start date must be before end date"
        return ""

    def get_well_name(self, well_id: int) -> str:
        """Get well name by ID"""
        if self.db_manager and well_id:
            well = self.db_manager.get_well_by_id(well_id)
            return well.get("name", "Unknown") if well else "Unknown"
        return "None"