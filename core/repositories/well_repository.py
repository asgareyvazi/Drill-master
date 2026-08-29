"""Well, Project, Company, Section repositories."""

from .base import BaseRepository
from core.database import Well, Project, Company, Section
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class WellRepository(BaseRepository):
    def get_by_name_or_code(self, name: str = "", code: str = "") -> Optional[Dict]:
        with self.db.session_scope() as session:
            q = session.query(Well)
            if code:
                existing = q.filter(Well.code == code).first()
                if existing:
                    return {c.name: getattr(existing, c.name) for c in Well.__table__.columns}
            if name:
                existing = session.query(Well).filter(Well.name == name).first()
                if existing:
                    return {c.name: getattr(existing, c.name) for c in Well.__table__.columns}
            return None

    def resolve_identity(self, well_info: Dict) -> int:
        """Universal Import: Well, Well Name, Well Number, Well ID, نام چاه → well.name"""
        name_keys = ["name", "well_name", "well", "well_number", "well_id", "well_id_text", "نام چاه", "well_designation"]
        code_keys = ["code", "well_code"]

        name = ""
        for k in name_keys:
            v = (well_info or {}).get(k)
            if v and str(v).strip():
                name = str(v).strip()
                break

        code = ""
        for k in code_keys:
            v = (well_info or {}).get(k)
            if v and str(v).strip():
                code = str(v).strip()
                break

        if not name and not code:
            return None

        existing = self.get_by_name_or_code(name, code)
        if existing:
            return existing["id"]

        # Create new well if project exists
        with self.db.session_scope() as session:
            from core.database import Project
            fallback_id = well_info.get("project_id")
            if not fallback_id:
                proj = session.query(Project.id).order_by(Project.id).first()
                fallback_id = proj[0] if proj else None
            if not fallback_id:
                raise ValueError("Cannot create well: no project exists")
            valid_keys = {c.name for c in Well.__table__.columns}
            values = {k: v for k, v in (well_info or {}).items() if k in valid_keys and k != "id"}
            values.update({"project_id": fallback_id, "name": name or code})
            if code:
                values["code"] = code
            well = Well(**values)
            session.add(well)
            session.flush()
            return well.id


class CompanyRepository(BaseRepository):
    def all(self) -> List[Dict]:
        return self.get_list(Company)


class ProjectRepository(BaseRepository):
    def all(self) -> List[Dict]:
        return self.get_list(Project)


class SectionRepository(BaseRepository):
    def get_by_well(self, well_id: int) -> List[Dict]:
        return self.get_list(Section, {"well_id": well_id})

    def resolve_identity(self, well_id: int, section_name: str, depth_from=None, depth_to=None) -> int:
        """Resolve section by name + depth range, not just name."""
        with self.db.session_scope() as session:
            q = session.query(Section).filter(Section.well_id == well_id, Section.name == section_name)
            existing = q.first()
            if existing:
                return existing.id
            # Create clearly named section if not matched
            new_sec = Section(
                well_id=well_id,
                name=section_name or "Imported Section",
                depth_from=float(depth_from) if depth_from not in (None, "") else 0.0,
                depth_to=float(depth_to) if depth_to not in (None, "") else 0.0,
            )
            session.add(new_sec)
            session.flush()
            return new_sec.id
