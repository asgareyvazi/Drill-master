"""Repository layer - splits DatabaseManager God Object into focused repositories."""

from .base import BaseRepository
from .well_repository import WellRepository, CompanyRepository, ProjectRepository, SectionRepository
from .report_repository import ReportRepository, SurveyRepository, BHARepository, BitRepository
from .logistics_repository import BulkRepository, EquipmentRepository, LogisticsRepository, FuelRepository
from .safety_repository import SafetyRepository, BOPRepository
from .service_repository import ServiceRepository
from .cost_repository import CostRepository
from .audit_repository import AuditRepository

__all__ = [
    "BaseRepository",
    "WellRepository",
    "CompanyRepository",
    "ProjectRepository",
    "SectionRepository",
    "ReportRepository",
    "SurveyRepository",
    "BHARepository",
    "BitRepository",
    "BulkRepository",
    "EquipmentRepository",
    "LogisticsRepository",
    "FuelRepository",
    "SafetyRepository",
    "BOPRepository",
    "ServiceRepository",
    "CostRepository",
    "AuditRepository",
]
