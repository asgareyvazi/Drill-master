"""Optional local AI assistant for ambiguous workbook mappings."""
import json, logging, os, urllib.request, urllib.error
from pathlib import Path
from core.canonical_schema import CANONICAL_FIELDS
logger = logging.getLogger(__name__)
ALLOWED_FIELDS = CANONICAL_FIELDS
def model_catalog():
    try: return json.loads((Path(__file__).resolve().parent.parent/"config"/"ai_models.json").read_text(encoding="utf-8")).get("models",[])
    except (OSError,ValueError): return []
def get_selected_model():
    try: return json.loads((Path(__file__).resolve().parent.parent/"config"/"ai_settings.json").read_text(encoding="utf-8")).get("model", "")
    except (OSError,ValueError): return ""
def set_selected_model(model):
    if model:
        path=Path(__file__).resolve().parent.parent/"config"/"ai_settings.json"; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps({"model":model},indent=2),encoding="utf-8")
class AIImportMapper:
    def __init__(self,endpoint=None,model=None,timeout=20):
        self.endpoint=(endpoint or os.getenv("DRILLMASTER_OLLAMA_URL","http://127.0.0.1:11434")).rstrip("/"); self.model=model or os.getenv("DRILLMASTER_AI_MODEL","") or get_selected_model() or "qwen2.5-local"; self.timeout=min(max(int(os.getenv("DRILLMASTER_AI_TIMEOUT",str(max(timeout,30)))),10),45); self.last_status="disabled"
    @property
    def enabled(self): return os.getenv("DRILLMASTER_AI_IMPORT","1").lower() in {"1","true","yes","on"}
    def installed_models(self):
        try:
            with urllib.request.urlopen(f"{self.endpoint}/api/tags",timeout=2) as r: return [m.get("name") for m in json.loads(r.read().decode()).get("models",[])]
        except (OSError,urllib.error.URLError,ValueError): return []
    def available(self):
        if not self.enabled: self.last_status="disabled"; return False
        if self.model not in set(self.installed_models()): self.last_status="model-not-installed"; return False
        self.last_status="available"; return True
    def map_context(self,context,allowed_fields=None):
        if not self.available(): return []
        fields=sorted(set(allowed_fields or ALLOWED_FIELDS)&ALLOWED_FIELDS); prompt={"task":"Map workbook cells to canonical drilling fields.","rules":["Return JSON only: {proposals: []}.","Never invent values.","Keep source_sheet, source_row and source_column.","Return confidence between 0 and 1.","Use null when ambiguous."],"allowed_fields":fields,"context":context}; body=json.dumps({"model":self.model,"stream":False,"format":"json","prompt":json.dumps(prompt,ensure_ascii=False)}).encode()
        try:
            req=urllib.request.Request(f"{self.endpoint}/api/generate",data=body,headers={"Content-Type":"application/json"},method="POST")
            with urllib.request.urlopen(req,timeout=self.timeout) as response: payload=json.loads(response.read().decode())
            raw=payload.get("response","{}"); result=json.loads(raw) if isinstance(raw,str) else raw; proposals=result.get("proposals",[]) if isinstance(result,dict) else []; valid=[p for p in proposals if self._valid_proposal(p,fields)]; self.last_status=f"ok:{len(valid)}"; return valid
        except Exception as exc: self.last_status=f"error:{type(exc).__name__}"; logger.warning("Local AI import mapping unavailable: %s",exc); return []
    @staticmethod
    def _valid_proposal(p,allowed):
        if not isinstance(p,dict) or p.get("field") not in allowed or not p.get("source_sheet") or p.get("source_row") is None or p.get("value") is None: return False
        try: c=float(p.get("confidence",0))
        except (TypeError,ValueError): return False
        return 0<=c<=1
