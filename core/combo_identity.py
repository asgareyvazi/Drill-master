"""Deterministic identities for application ComboBox values.

The UI displays human-readable labels, but imported values must be resolved to
an application identity before persistence.  This module is deliberately
Qt-free so Excel, PDF, validation, persistence, and the UI use the same
contract.

DDR convention
--------------
The OEOC/DDR activity catalogue uses one-based main and sub ordinals:
``Code=2`` means the second main activity and ``Sub-Code=1`` means the first
sub-activity under that main activity.  That conversion is only enabled when
``ordinal_mode='ddr'`` (the default for the DDR activity catalogue); arbitrary
numeric values are never treated as a UI index.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata
from typing import Any, Iterable, Mapping, Optional


# Application catalogue.  These are semantic application codes, not Qt
# indices.  A workbook Activity Codes sheet can replace/extend the labels.
DEFAULT_MAIN_LABELS: dict[str, str] = {
    "1": "Rig Up/ Tear Down / Move",
    "2": "Drilling",
    "3": "Reaming",
    "4": "Coring",
    "5": "Circulate & Condition",
    "6": "Trips",
    "7": "Service/ Maintain Rig",
    "8": "Repair Rig",
    "9": "Replacing Drill Line",
    "10": "Deviation Survey",
    "11": "Logging",
    "12": "Run Casing/ Liner",
    "13": "Cementing",
    "14": "Wait on Cement",
    "15": "Rig Up/Down BOP",
    "16": "Test BOP",
    "17": "Drill Stem Test",
    "18": "Fishing",
    "19": "Specialized Directional Work",
    "20": "Operation Status (Waiting)",
    "21": "Safety",
    "22": "Perforating",
    "23": "Completion/XMT",
    "24": "Treating",
    "25": "Swabbing",
    "26": "Surface Testing",
    "27": "Well Control",
    "28": "Other",
    "29": "Subsea Operation",
}

# Aliases are labels encountered in DDR exports and workbook settings.  They
# are aliases only; the persisted identity remains ``<code> - <label>``.
MAIN_ALIASES: dict[str, tuple[str, ...]] = {
    "DRL": ("drilling",),
    "MOV": ("rig up/ tear down / move", "moving"),
    "CSG": ("run casing/ liner", "casing", "liner"),
    "COM": ("completion/xmt", "completion", "xmt"),
    "FTS": ("drill stem test", "formation testing", "testing"),
    "PIH": ("pilot hole",),
    "COR": ("coring",),
    "REE": ("re-entry", "specialized directional work"),
    "ABD": ("abandonment",),
    "LOG": ("logging",),
}


@dataclass(frozen=True)
class ComboOption:
    identity: str
    label: str
    code: str
    aliases: tuple[str, ...] = ()
    ordinal: Optional[int] = None


@dataclass(frozen=True)
class ComboResolution:
    """Lossless outcome of resolving one imported ComboBox value."""

    field: str
    source_value: Any
    identity: Optional[str]
    label: Optional[str]
    code: Optional[str]
    status: str  # ACCEPT or REVIEW_REQUIRED
    method: str  # ordinal, code, label, normalized_label, alias, unresolved, ambiguous
    reason: str
    candidates: tuple[str, ...] = ()
    source_ordinal: Optional[int] = None

    @property
    def accepted(self) -> bool:
        return self.status == "ACCEPT" and self.identity is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "source_value": self.source_value,
            "identity": self.identity,
            "label": self.label,
            "code": self.code,
            "status": self.status,
            "method": self.method,
            "reason": self.reason,
            "candidates": list(self.candidates),
            "source_ordinal": self.source_ordinal,
        }


def normalize_label(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    text = text.replace("–", "-").replace("—", "-").replace("\\", "/")
    text = re.sub(r"[\u200b\u00a0]", " ", text)
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _clean_numeric(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not re.fullmatch(r"[+-]?\d+(?:\.0+)?", text):
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError, OverflowError):
        return None


def _display_identity(code: str, label: str) -> str:
    return f"{code} - {label}"


def _code_from_identity(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if re.fullmatch(r"\d+", text):
        return text
    # Main identity is ``2 - Drilling``; a composite ``2-1`` is a Sub-Code,
    # never a main-code match.
    match = re.match(r"^\s*(\d+)\s*-\s*[A-Za-z]", text)
    return match.group(1) if match else None


def _composite(value: Any) -> Optional[tuple[int, int]]:
    text = str(value or "").strip().replace("–", "-").replace("—", "-")
    match = re.match(r"^(\d+)\s*[./-]\s*(\d+)(?:\s|$|[-])", text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


class ComboCatalog:
    """Application ComboBox catalogue with deterministic resolution."""

    def __init__(
        self,
        main_labels: Optional[Mapping[str, str]] = None,
        sub_labels: Optional[Mapping[str, str]] = None,
        *,
        aliases: Optional[Mapping[str, Iterable[str]]] = None,
    ) -> None:
        self.main_labels = dict(DEFAULT_MAIN_LABELS)
        if main_labels:
            self.main_labels.update({str(k): str(v).strip() for k, v in main_labels.items() if v not in (None, "")})
        self.sub_labels = {str(k).replace("-", ".").replace("/", "."): str(v).strip() for k, v in (sub_labels or {}).items() if v not in (None, "")}
        self.aliases = dict(MAIN_ALIASES)
        if aliases:
            self.aliases.update({str(k): tuple(str(v) for v in values) for k, values in aliases.items()})
        # MAIN_ALIASES is expressed as source-token -> target label fragments;
        # make the option-level aliases used by the resolver explicit.
        option_aliases: dict[str, list[str]] = {str(code): [] for code in self.main_labels}
        for source_alias, target_fragments in self.aliases.items():
            for code, label in self.main_labels.items():
                normalized_label = normalize_label(label)
                if any(
                    normalize_label(fragment) in normalized_label
                    or normalized_label in normalize_label(fragment)
                    for fragment in target_fragments
                ):
                    option_aliases.setdefault(str(code), []).append(str(source_alias))
        self.option_aliases = {code: tuple(values) for code, values in option_aliases.items()}

    @classmethod
    def from_activity_rows(cls, rows: Iterable[Iterable[Any]]) -> "ComboCatalog":
        """Build a catalogue from Activity Codes sheet rows.

        Expected workbook convention is ``main ordinal | sub code | label``;
        header and malformed rows are ignored, never guessed.
        """
        main: dict[str, str] = {}
        sub: dict[str, str] = {}
        for row in rows:
            values = list(row or [])
            if len(values) < 3:
                continue
            raw_main, raw_sub, raw_label = values[0], values[1], values[2]
            label = str(raw_label or "").strip()
            if not label:
                continue
            main_number = _clean_numeric(raw_main)
            if main_number is not None and raw_sub in (None, ""):
                main[str(main_number)] = label
            raw_sub_text = str(raw_sub or "").strip()
            match = re.match(r"^(\d+)\s*[-./]\s*(\d+)", raw_sub_text)
            if match:
                sub[f"{int(match.group(1))}.{int(match.group(2))}"] = label
        return cls(main, sub)

    def main_options(self) -> list[ComboOption]:
        return [
            ComboOption(_display_identity(code, label), label, code, self.option_aliases.get(code, ()), int(code))
            for code, label in sorted(self.main_labels.items(), key=lambda item: int(item[0]) if item[0].isdigit() else item[0])
        ]

    def sub_options(self, main_code: Optional[str] = None) -> list[ComboOption]:
        values = []
        for composite, label in sorted(self.sub_labels.items(), key=lambda item: tuple(int(x) for x in item[0].split("."))):
            parent, ordinal = composite.split(".", 1)
            if main_code and str(parent) != str(main_code):
                continue
            values.append(ComboOption(_display_identity(composite, label), label, composite, (), int(ordinal)))
        return values

    def _review(self, field: str, value: Any, method: str, reason: str, candidates: Iterable[str] = (), ordinal: Optional[int] = None) -> ComboResolution:
        return ComboResolution(field, value, None, None, None, "REVIEW_REQUIRED", method, reason, tuple(candidates), ordinal)

    def _accepted(self, field: str, value: Any, option: ComboOption, method: str, *, ordinal: Optional[int] = None) -> ComboResolution:
        return ComboResolution(field, value, option.identity, option.label, option.code, "ACCEPT", method, f"Resolved to application identity {option.identity!r}", (), ordinal)

    @staticmethod
    def _find(options: Iterable[ComboOption], value: Any) -> tuple[list[ComboOption], str]:
        text = str(value or "").strip()
        norm = normalize_label(text)
        exact = [option for option in options if normalize_label(option.identity) == norm]
        if exact:
            return exact, "code"
        code = _code_from_identity(text)
        if code:
            by_code = [option for option in options if option.code == code]
            if by_code:
                return by_code, "code"
        labels = [option for option in options if normalize_label(option.label) == norm]
        if labels:
            return labels, "normalized_label"
        aliases = [
            option for option in options
            if any(normalize_label(alias) == norm for alias in option.aliases)
        ]
        return aliases, "alias"

    def resolve_main(self, value: Any, *, field: str = "time_log.main_code", ordinal_mode: str = "ddr") -> ComboResolution:
        if value is None or not str(value).strip():
            return self._review(field, value, "unresolved", "Blank ComboBox value; no default item selected")
        options = self.main_options()
        ordinal = _clean_numeric(value)
        if ordinal is not None and ordinal_mode == "ddr":
            option = next((item for item in options if item.code == str(ordinal)), None)
            if option:
                return self._accepted(field, value, option, "ordinal", ordinal=ordinal)
            return self._review(field, value, "out_of_range", f"DDR main ordinal {ordinal} is outside the authoritative activity catalogue", ordinal=ordinal)
        matches, method = self._find(options, value)
        if len(matches) == 1:
            return self._accepted(field, value, matches[0], method)
        if len(matches) > 1:
            return self._review(field, value, "ambiguous", "Value matches multiple application ComboBox identities", (x.identity for x in matches))
        return self._review(field, value, "unresolved", "Value does not match a code, label, normalized label, or alias")

    def resolve_sub(self, value: Any, main: Any = None, *, field: str = "time_log.sub_code", ordinal_mode: str = "ddr") -> ComboResolution:
        if value is None or not str(value).strip():
            return self._review(field, value, "unresolved", "Blank ComboBox value; no default item selected")
        parent_resolution = self.resolve_main(main, field="time_log.main_code", ordinal_mode=ordinal_mode) if main not in (None, "") else None
        parent_code = parent_resolution.code if parent_resolution and parent_resolution.accepted else None
        composite = _composite(value)
        if composite:
            key = f"{composite[0]}.{composite[1]}"
            option = next((item for item in self.sub_options(str(composite[0])) if item.code == key), None)
            if option:
                return self._accepted(field, value, option, "code")
            return self._review(field, value, "out_of_range", f"DDR sub-code {value!r} is outside the authoritative sub-catalogue")
        ordinal = _clean_numeric(value)
        options = self.sub_options(parent_code)
        if ordinal is not None and ordinal_mode == "ddr":
            if not parent_code:
                return self._review(field, value, "unresolved", "Sub-code ordinal cannot be resolved without an authoritative main code", ordinal=ordinal)
            option = next((item for item in options if item.ordinal == ordinal), None)
            if option:
                return self._accepted(field, value, option, "ordinal", ordinal=ordinal)
            return self._review(field, value, "out_of_range", f"DDR sub-code ordinal {ordinal} is outside the main-code sub-catalogue", ordinal=ordinal)
        matches, method = self._find(options or self.sub_options(), value)
        if len(matches) == 1:
            return self._accepted(field, value, matches[0], method)
        if len(matches) > 1:
            return self._review(field, value, "ambiguous", "Value matches multiple application ComboBox identities", (x.identity for x in matches))
        return self._review(field, value, "unresolved", "Value does not match a code, label, normalized label, or alias")


DEFAULT_ACTIVITY_CATALOG = ComboCatalog(
    sub_labels={
        "1.1": "Rig Moving/Positioning", "1.2": "Rig Up", "1.3": "Rig Down", "1.6": "Skid Rig",
        "2.1": "Vertical Drilling", "2.2": "Directional Drilling (Rotating)", "2.3": "Directional Drilling (Sliding)",
        "3.1": "Reaming / Back Reaming", "3.5": "Wash Down",
        "5.1": "Hole displacement", "5.2": "Circulate/ Condition Mud",
        "6.1": "R/U & R/D Pipe Handling Equip.", "6.2": "PU/LD BHA", "6.5": "Run in Hole", "6.6": "Pull Out Of Hole", "6.8": "Wiper/ Condition Trip", "6.9": "Wear Bushing",
        "7.1": "Rig Lubricate", "8.1": "Circulating System", "9.1": "Slip & Cut of Drill Line", "10.1": "Performing Survey Operation",
        "11.1": "R/U & R/D Logging Equip.", "11.2": "Wire line logging", "12.1": "R/U & R/D Handling Equip.", "12.2": "CSG Running", "12.3": "Pulling Casing", "12.4": "CSG/Liner Integrity Test", "12.5": "Liner Running", "12.6": "Liner Tie back Operation", "12.7": "Pull out Liner hanger setting tools and L/D", "12.8": "Other Related Casing/Liner Activities", "12.9": "Nipple up/down Wellhead",
        "13.1": "Casing/ Liner Cementing", "13.2": "Plug Back", "13.3": "Squeeze CMT", "13.4": "Balance Plug", "13.5": "Other",
        "14.1": "for Casing/ Liner Cementing", "14.2": "for Cement plug", "14.4": "Other",
        "15.1": "Nipple up/down BOP", "16.1": "Pressure Test BOPs", "17.1": "Conventional DST", "18.1": "Fishing Job", "18.2": "Milling", "18.3": "Coiled Tubing Ops.", "18.4": "Work on Stuck",
        "19.1": "RIH/ POOH Side-Track equip.", "19.2": "Side-Tracking in Open Hole", "19.3": "Side-Tracking in Cased Hole", "19.4": "Other",
        "20.1": "Waiting on Client", "20.2": "Waiting on Operator Company", "20.3": "Waiting on Rig Contractor", "20.4": "Waiting on Service companies", "20.5": "Waiting on Weather", "20.6": "Waiting on Logistics/ Fuel",
        "21.1": "Pre Job Safety Meeting (PJSM)", "21.2": "Drills", "21.3": "Other HSE Related activities",
        "22.1": "Wire line Perforation", "22.2": "TCP Perforatin", "22.3": "CT Perforatin", "23.1": "Completion Trips", "24.1": "Acidizing", "25.1": "Swabbing", "26.1": "Surface Testing", "27.1": "Kill the well", "28.1": "Other", "29.1": "Run/ Retrieve Riser Equip.",
    }
)


def resolve_activity_pair(main: Any, sub: Any, *, catalog: ComboCatalog = DEFAULT_ACTIVITY_CATALOG, field_prefix: str = "time_log") -> tuple[ComboResolution, ComboResolution]:
    main_result = catalog.resolve_main(main, field=f"{field_prefix}.main_code")
    sub_result = catalog.resolve_sub(sub, main_result.identity or main, field=f"{field_prefix}.sub_code")
    return main_result, sub_result
