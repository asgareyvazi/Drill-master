"""Company/template-agnostic mapping memory with revisioned JSON storage."""

import hashlib
from copy import deepcopy
import json
from pathlib import Path

from core.runtime_config import mapping_memory_path, atomic_write_json


class MappingStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else mapping_memory_path()
        self.data = self._load()

    def _load(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"mappings": {}}

    @staticmethod
    def fingerprint(snapshot):
        headers = []
        for table in snapshot.get("tables", []):
            headers.extend(str(h).strip().lower() for h in table.get("headers", []) if h)
        return hashlib.sha256("|".join(sorted(set(headers))).encode()).hexdigest()[:20]

    def get(self, fingerprint):
        return self.data.get("mappings", {}).get(fingerprint, {})

    def remember(self, fingerprint, mappings, source="user-confirmed"):
        if not fingerprint or not mappings:
            return
        candidate = deepcopy(self.data)
        entry = candidate.setdefault("mappings", {}).setdefault(
            fingerprint, {"revision": 0, "source": source, "fields": {}}
        )
        entry["revision"] += 1
        entry["source"] = source
        entry["fields"].update(deepcopy(mappings))
        atomic_write_json(self.path, candidate, ensure_ascii=False, indent=2)
        self.data = candidate
