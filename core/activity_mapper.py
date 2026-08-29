"""Canonical Activity Registry — company/template-aware activity code mapping.

Maps company-specific time log codes to a universal canonical activity model.

Flow:
    Company Code + Description + Template/Profile + Context
        → Canonical Activity
            → Activity Category
            → NPT Classification

Design:
- Single source of truth for canonical activities
- Company mappings stored separately (not hardcoded)
- Confidence-based resolution
- Original code preserved as provenance
- Integrates with existing TimeLogValidator (does NOT replace it)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)


# ==================== Canonical Activity Model ====================

@dataclass(frozen=True)
class CanonicalActivity:
    """A canonical drilling activity definition."""
    canonical_id: str          # e.g., "DRILLING"
    name: str                  # e.g., "Drilling"
    category: str              # e.g., "Operations"
    is_npt: bool = False       # Is this a Non-Productive Time activity?
    npt_category: str = ""     # NPT category if applicable
    description: str = ""      # Human-readable description


# THE canonical activity registry — single source of truth
CANONICAL_ACTIVITIES = {
    "DRILLING": CanonicalActivity(
        "DRILLING", "Drilling", "Operations",
        description="Drilling ahead with rotary or slide",
    ),
    "CONNECTION": CanonicalActivity(
        "CONNECTION", "Connection", "Operations",
        description="Making a drill pipe connection",
    ),
    "CIRCULATION": CanonicalActivity(
        "CIRCULATION", "Circulation", "Operations",
        description="Circulating and conditioning mud",
    ),
    "TRIPPING_IN": CanonicalActivity(
        "TRIPPING_IN", "Tripping In", "Trips",
        description="Running drill string in hole",
    ),
    "TRIPPING_OUT": CanonicalActivity(
        "TRIPPING_OUT", "Tripping Out", "Trips",
        description="Pulling drill string out of hole",
    ),
    "REAMING": CanonicalActivity(
        "REAMING", "Reaming", "Operations",
        description="Reaming/opening hole",
    ),
    "BACKREAMING": CanonicalActivity(
        "BACKREAMING", "Backreaming", "Operations",
        description="Reaming while pulling out of hole",
    ),
    "WIPER_TRIP": CanonicalActivity(
        "WIPER_TRIP", "Wiper Trip", "Trips",
        description="Short trip to condition hole",
    ),
    "CASING": CanonicalActivity(
        "CASING", "Casing Running", "Casing",
        description="Running casing/liner",
    ),
    "CEMENTING": CanonicalActivity(
        "CEMENTING", "Cementing", "Cementing",
        description="Cement job operations",
    ),
    "WAIT_ON_CEMENT": CanonicalActivity(
        "WAIT_ON_CEMENT", "Wait on Cement", "Waiting",
        is_npt=False,
        description="Waiting on cement to set",
    ),
    "LOGGING": CanonicalActivity(
        "LOGGING", "Logging", "Logging",
        description="Wireline or LWD logging operations",
    ),
    "FISHING": CanonicalActivity(
        "FISHING", "Fishing", "Operations",
        description="Fishing operations",
    ),
    "MILLING": CanonicalActivity(
        "MILLING", "Milling", "Operations",
        description="Milling operations",
    ),
    "WELL_CONTROL": CanonicalActivity(
        "WELL_CONTROL", "Well Control", "Safety",
        is_npt=True, npt_category="Well Control",
        description="Well control operations (kill, SCR, FIT/LOT, flow check)",
    ),
    "BOP_TEST": CanonicalActivity(
        "BOP_TEST", "BOP Test", "Safety",
        description="BOP pressure/function test",
    ),
    "BOP_INSTALL": CanonicalActivity(
        "BOP_INSTALL", "BOP Install/Remove", "Safety",
        description="Rig up/down BOP",
    ),
    "SURVEY": CanonicalActivity(
        "SURVEY", "Deviation Survey", "Operations",
        description="MWD/Gyro survey operations",
    ),
    "RIG_MAINTENANCE": CanonicalActivity(
        "RIG_MAINTENANCE", "Rig Maintenance", "Rig",
        description="Scheduled rig maintenance",
    ),
    "RIG_REPAIR": CanonicalActivity(
        "RIG_REPAIR", "Rig Repair", "NPT",
        is_npt=True, npt_category="Rig Equipment",
        description="Unplanned rig equipment repair",
    ),
    "WAIT_ON_WEATHER": CanonicalActivity(
        "WAIT_ON_WEATHER", "Wait on Weather", "NPT",
        is_npt=True, npt_category="Weather",
        description="Waiting due to weather conditions",
    ),
    "WAIT_ON_EQUIPMENT": CanonicalActivity(
        "WAIT_ON_EQUIPMENT", "Wait on Equipment", "NPT",
        is_npt=True, npt_category="Equipment",
        description="Waiting for equipment delivery/repair",
    ),
    "WAIT_ON_LOGISTICS": CanonicalActivity(
        "WAIT_ON_LOGISTICS", "Wait on Logistics", "NPT",
        is_npt=True, npt_category="Logistics",
        description="Waiting for logistics (fuel, supplies, crew change)",
    ),
    "WAIT_ON_CLIENT": CanonicalActivity(
        "WAIT_ON_CLIENT", "Wait on Client", "NPT",
        is_npt=True, npt_category="NPT-Client",
        description="Waiting on client decision/instructions",
    ),
    "WAIT_ON_OPERATOR": CanonicalActivity(
        "WAIT_ON_OPERATOR", "Wait on Operator", "NPT",
        is_npt=True, npt_category="NPT-Operator",
        description="Waiting on operator company",
    ),
    "SAFETY": CanonicalActivity(
        "SAFETY", "Safety/HSE", "Safety",
        description="Safety meetings, drills, HSE activities",
    ),
    "PERFORATING": CanonicalActivity(
        "PERFORATING", "Perforating", "Completion",
        description="Perforating operations",
    ),
    "COMPLETION": CanonicalActivity(
        "COMPLETION", "Completion", "Completion",
        description="Completion operations",
    ),
    "TREATING": CanonicalActivity(
        "TREATING", "Treating", "Operations",
        description="Acidizing, N2 lifting, treating",
    ),
    "TESTING": CanonicalActivity(
        "TESTING", "Testing", "Operations",
        description="DST, surface testing, clean-up",
    ),
    "DIRECTIONAL": CanonicalActivity(
        "DIRECTIONAL", "Directional Work", "Operations",
        description="Side-tracking, whipstock, directional work",
    ),
    "DRILL_LINE": CanonicalActivity(
        "DRILL_LINE", "Drill Line", "Rig",
        description="Slip and cut drill line",
    ),
    "OTHER": CanonicalActivity(
        "OTHER", "Other", "Other",
        description="Other activities not classified above",
    ),
}


# ==================== Company Mapping ====================

@dataclass
class ActivityMappingResult:
    """Result of mapping a company code to a canonical activity."""
    source_code: str           # Original company code (e.g., "DRL")
    source_description: str    # Original description (e.g., "Drilling")
    canonical_id: str          # Canonical ID (e.g., "DRILLING")
    canonical_name: str        # Canonical name (e.g., "Drilling")
    category: str              # Category (e.g., "Operations")
    is_npt: bool               # Is NPT?
    npt_category: str          # NPT category
    confidence: float          # 0.0 to 1.0
    method: str                # "exact", "description", "fuzzy", "unresolved"
    reason: str                # Human-readable explanation

    def to_dict(self) -> dict:
        return {
            "source_code": self.source_code,
            "source_description": self.source_description,
            "canonical_id": self.canonical_id,
            "canonical_name": self.canonical_name,
            "category": self.category,
            "is_npt": self.is_npt,
            "npt_category": self.npt_category,
            "confidence": round(self.confidence, 2),
            "method": self.method,
            "reason": self.reason,
        }


# ==================== Known Company Code Patterns ====================

# These are NOT hardcoded company-specific branches.
# They are common patterns found across the industry.
# Company-specific mappings are loaded from template/profile.

KNOWN_CODE_PATTERNS = {
    # Numeric codes (common in Middle East/NOC reports)
    "1": ("RIG_UP", "Rig up/down/move"),
    "2": ("DRILLING", "Drilling"),
    "3": ("REAMING", "Reaming"),
    "4": ("CORING", "Coring"),
    "5": ("CIRCULATION", "Circulate & Condition"),
    "6": ("TRIPPING_IN", "Trips"),
    "7": ("RIG_MAINTENANCE", "Service/Maintain Rig"),
    "8": ("RIG_REPAIR", "Repair Rig"),
    "9": ("DRILL_LINE", "Replacing Drill Line"),
    "10": ("SURVEY", "Deviation Survey"),
    "11": ("LOGGING", "Logging"),
    "12": ("CASING", "Run Casing/Liner"),
    "13": ("CEMENTING", "Cementing"),
    "14": ("WAIT_ON_CEMENT", "Wait on Cement"),
    "15": ("BOP_INSTALL", "Rig Up/Down BOP"),
    "16": ("BOP_TEST", "Test BOP"),
    "17": ("TESTING", "Drill Stem Test"),
    "18": ("FISHING", "Fishing"),
    "19": ("DIRECTIONAL", "Specialized Directional Work"),
    "20": ("WAIT_ON_EQUIPMENT", "Operation Status (Waiting)"),
    "21": ("SAFETY", "Safety"),
    "22": ("PERFORATING", "Perforating"),
    "23": ("COMPLETION", "Completion/XMT"),
    "24": ("TREATING", "Treating"),
    "25": ("OTHER", "Swabbing"),
    "26": ("TESTING", "Surface Testing"),
    "27": ("WELL_CONTROL", "Well Control"),
    "28": ("OTHER", "Other"),
    "29": ("OTHER", "Subsea Operation"),
    
    # Sub-codes (common)
    "2-1": ("DRILLING", "Drilling ahead"),
    "2-2": ("DRILLING", "Drilling with parameters"),
    "3-1": ("REAMING", "Reaming"),
    "5-1": ("CIRCULATION", "Circulate"),
    "6-1": ("TRIPPING_IN", "Rig up handling equipment"),
    "6-2": ("TRIPPING_IN", "Pick up/make up BHA"),
    "6-5": ("TRIPPING_IN", "Run in Hole"),
    "6-6": ("TRIPPING_OUT", "Pull Out of Hole"),
    "6-8": ("WIPER_TRIP", "Wiper/Condition Trip"),
    "12-1": ("CASING", "Casing Running"),
    "13-1": ("CEMENTING", "Casing/Liner Cementing"),
    "14-1": ("WAIT_ON_CEMENT", "WOC for Casing/Liner"),
    "15-1": ("BOP_INSTALL", "Nipple up/down BOP"),
    "16-1": ("BOP_TEST", "Pressure Test BOPs"),
    "20-1": ("WAIT_ON_CLIENT", "Waiting on Client"),
    "20-2": ("WAIT_ON_OPERATOR", "Waiting on Operator"),
    "20-3": ("WAIT_ON_EQUIPMENT", "Waiting on Rig Contractor"),
    "20-4": ("WAIT_ON_EQUIPMENT", "Waiting on Service Companies"),
    "20-5": ("WAIT_ON_WEATHER", "Waiting on Weather"),
    "20-6": ("WAIT_ON_LOGISTICS", "Waiting on Logistics/Fuel"),
    "21-1": ("SAFETY", "Pre Job Safety Meeting"),
    "21-2": ("SAFETY", "Safety Drills"),
    "27-1": ("WELL_CONTROL", "Kill the well"),
    "27-2": ("WELL_CONTROL", "Take SCR"),
    "27-3": ("WELL_CONTROL", "FIT/LOT"),
    "27-4": ("WELL_CONTROL", "Flow Check"),
    "27-5": ("WELL_CONTROL", "Strip In/Out"),
    
    # Alphabetic codes (common in international companies)
    "DRL": ("DRILLING", "Drilling"),
    "CIR": ("CIRCULATION", "Circulation"),
    "TRP": ("TRIPPING", "Tripping"),
    "POOH": ("TRIPPING_OUT", "Pull Out of Hole"),
    "RIH": ("TRIPPING_IN", "Run in Hole"),
    "RMG": ("REAMING", "Reaming"),
    "CSG": ("CASING", "Casing"),
    "CMT": ("CEMENTING", "Cementing"),
    "WOC": ("WAIT_ON_CEMENT", "Wait on Cement"),
    "LOG": ("LOGGING", "Logging"),
    "FISH": ("FISHING", "Fishing"),
    "BOP": ("BOP_INSTALL", "BOP Operations"),
    "SUR": ("SURVEY", "Survey"),
    "NPT": ("OTHER", "Non-Productive Time"),
    "SAF": ("SAFETY", "Safety"),
    "MNT": ("RIG_MAINTENANCE", "Maintenance"),
    "RPR": ("RIG_REPAIR", "Repair"),
}


# ==================== Activity Mapper ====================

class ActivityMapper:
    """Company/template-aware activity code mapper.
    
    Resolution order:
    1. Learned/user-approved mapping (from MappingStore)
    2. Exact code match in KNOWN_CODE_PATTERNS
    3. Description-based matching
    4. Fuzzy description matching
    5. Mark as UNRESOLVED
    """

    def __init__(self, mapping_store=None):
        self._mapping_store = mapping_store
        self._learned_mappings = {}  # (company, code) -> canonical_id

    def map_activity(self, code: str, description: str = "",
                     company: str = "", template: str = "") -> ActivityMappingResult:
        """Map a company activity code to a canonical activity.
        
        Args:
            code: Company-specific code (e.g., "DRL", "2", "6-2")
            description: Activity description (e.g., "Drilling 17-1/2\" HS")
            company: Company name for context
            template: Template version for context
            
        Returns:
            ActivityMappingResult with canonical mapping and confidence
        """
        code = str(code).strip()
        description = str(description).strip()
        
        if not code and not description:
            return ActivityMappingResult(
                source_code="", source_description="",
                canonical_id="OTHER", canonical_name="Other",
                category="Other", is_npt=False, npt_category="",
                confidence=0.0, method="unresolved",
                reason="No code or description provided",
            )

        # Strategy 1: Learned mapping
        learned_key = (company.lower(), code.lower())
        if learned_key in self._learned_mappings:
            canonical_id = self._learned_mappings[learned_key]
            activity = CANONICAL_ACTIVITIES.get(canonical_id)
            if activity:
                return ActivityMappingResult(
                    source_code=code, source_description=description,
                    canonical_id=canonical_id, canonical_name=activity.name,
                    category=activity.category, is_npt=activity.is_npt,
                    npt_category=activity.npt_category,
                    confidence=0.98, method="learned",
                    reason=f"Learned mapping: {company}/{code} → {canonical_id}",
                )

        # Strategy 2: Exact code match
        code_lower = code.lower().strip()
        for pattern_code, (canonical_id, pattern_desc) in KNOWN_CODE_PATTERNS.items():
            if code_lower == pattern_code.lower():
                activity = CANONICAL_ACTIVITIES.get(canonical_id)
                if activity:
                    # Verify with description if available
                    desc_boost = 0.0
                    if description:
                        desc_lower = description.lower()
                        if any(kw in desc_lower for kw in activity.name.lower().split()):
                            desc_boost = 0.05
                    
                    return ActivityMappingResult(
                        source_code=code, source_description=description,
                        canonical_id=canonical_id, canonical_name=activity.name,
                        category=activity.category, is_npt=activity.is_npt,
                        npt_category=activity.npt_category,
                        confidence=min(0.95 + desc_boost, 1.0), method="exact",
                        reason=f"Exact code match: '{code}' → {canonical_id}",
                    )

        # Strategy 3: Description-based matching
        if description:
            result = self._match_by_description(description)
            if result:
                return ActivityMappingResult(
                    source_code=code, source_description=description,
                    canonical_id=result.canonical_id, canonical_name=result.name,
                    category=result.category, is_npt=result.is_npt,
                    npt_category=result.npt_category,
                    confidence=0.80, method="description",
                    reason=f"Description match: '{description}' → {result.canonical_id}",
                )

        # Strategy 4: Fuzzy description matching
        if description:
            result = self._fuzzy_match(description)
            if result:
                canonical_id, score = result
                activity = CANONICAL_ACTIVITIES.get(canonical_id)
                if activity:
                    return ActivityMappingResult(
                        source_code=code, source_description=description,
                        canonical_id=canonical_id, canonical_name=activity.name,
                        category=activity.category, is_npt=activity.is_npt,
                        npt_category=activity.npt_category,
                        confidence=score * 0.7, method="fuzzy",
                        reason=f"Fuzzy match ({score:.0%}): '{description}' → {canonical_id}",
                    )

        # Strategy 5: UNRESOLVED
        return ActivityMappingResult(
            source_code=code, source_description=description,
            canonical_id="OTHER", canonical_name="Other",
            category="Other", is_npt=False, npt_category="",
            confidence=0.0, method="unresolved",
            reason=f"No match for code='{code}', description='{description[:50]}'",
        )

    def _match_by_description(self, description: str) -> Optional[CanonicalActivity]:
        """Match by keyword analysis of description."""
        desc = description.lower()
        
        # Keyword → canonical ID mapping
        keyword_rules = [
            (["drilling", "drill ahead", "drilling ahead", "on bottom"], "DRILLING"),
            (["connection", "making connection", "m/u", "break out"], "CONNECTION"),
            (["circulat", "condition mud", "hi-vis", "pill", "sweep"], "CIRCULATION"),
            (["pooh", "pull out", "tripping out", "l/d"], "TRIPPING_OUT"),
            (["rih", "run in", "tripping in", "run drill string"], "TRIPPING_IN"),
            (["reaming", "ream", "open hole"], "REAMING"),
            (["backream", "back ream"], "BACKREAMING"),
            (["wiper trip", "wiper", "condition trip"], "WIPER_TRIP"),
            (["casing", "run casing", "running casing"], "CASING"),
            (["cement", "pump cement", "cementing"], "CEMENTING"),
            (["wait on cement", "woc"], "WAIT_ON_CEMENT"),
            (["logging", "log run", "wireline", "lwd"], "LOGGING"),
            (["fishing", "fish"], "FISHING"),
            (["milling", "mill"], "MILLING"),
            (["kill", "well control", "scr", "flow check", "fit", "lot"], "WELL_CONTROL"),
            (["bop test", "pressure test bop", "test bop"], "BOP_TEST"),
            (["bop", "nipple up", "nipple down"], "BOP_INSTALL"),
            (["survey", "mwd survey", "deviation survey"], "SURVEY"),
            (["maintenance", "lubricate", "scheduled"], "RIG_MAINTENANCE"),
            (["repair", "breakdown", "fix"], "RIG_REPAIR"),
            (["weather", "storm", "wind"], "WAIT_ON_WEATHER"),
            (["safety", "pjsm", "drill", "hse"], "SAFETY"),
            (["perforat", "perforating"], "PERFORATING"),
        ]
        
        for keywords, canonical_id in keyword_rules:
            for kw in keywords:
                if kw in desc:
                    return CANONICAL_ACTIVITIES.get(canonical_id)
        
        return None

    def _fuzzy_match(self, description: str) -> Optional[Tuple[str, float]]:
        """Fuzzy match against canonical activity names."""
        from difflib import SequenceMatcher
        desc = description.lower().strip()
        
        best_id = None
        best_score = 0.0
        
        for canonical_id, activity in CANONICAL_ACTIVITIES.items():
            # Match against activity name
            ratio = SequenceMatcher(None, desc, activity.name.lower()).ratio()
            if ratio > best_score:
                best_score = ratio
                best_id = canonical_id
            
            # Match against description
            ratio = SequenceMatcher(None, desc, activity.description.lower()).ratio()
            if ratio > best_score:
                best_score = ratio
                best_id = canonical_id
        
        if best_score >= 0.6:
            return best_id, best_score
        return None

    def learn_mapping(self, code: str, canonical_id: str, company: str = ""):
        """Store a user-approved mapping for future use."""
        key = (company.lower(), code.lower())
        self._learned_mappings[key] = canonical_id
        logger.info(f"Learned mapping: {company}/{code} → {canonical_id}")

    def get_all_activities(self) -> Dict[str, CanonicalActivity]:
        """Return all canonical activities."""
        return dict(CANONICAL_ACTIVITIES)
