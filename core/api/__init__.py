"""API layer - REST and GraphQL for Intelligence Platform (P2 future)"""

from .rest_api import create_app, DrillMasterAPI

__all__ = ["create_app", "DrillMasterAPI"]
