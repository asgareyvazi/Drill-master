"""Optional local AI assistant for ambiguous workbook mappings.
The model proposes mappings only; validation and review remain authoritative.
"""
import json, logging, os, urllib.request, urllib.error
logger = logging.getLogger(__name__)
ALLOWED_FIELDS = {"well_info.name","well_info.field_name","well_info.well_type","well_info.rig_name","well_info.drilling_contractor","well_info.report_date","daily_report.report_date","daily_report.report_number","daily_report.depth_0000","daily_report.depth_0600","daily_report.depth_2400","daily_report.summary","mud_report.mud_type","mud_report.mw","mud_report.pv","mud_report.yp","mud_report.ph","mud_report.temperature","mud_report.solid_percent","drilling_params.bit_no","drilling_params.bit_size","drilling_params.bit_type","drilling_params.depth_in","drilling_params.depth_out","drilling_params.avg_rop","time_log.main_code","time_log.sub_code","time_log.contractor","survey.md","survey.inc","survey.azi","survey.tvd","bulk_material.material_name","bulk_material.received","bulk_material.used"}
class AIImportMapper:
    def __init__(self, endpoint=None, model=None, timeout=20):
        self.endpoint=(endpoint or os.getenv("DRILLMASTER_OLLAMA_URL","http://127.0.0.1:11434")).rstrip("/")
        self.model=model or os.getenv("DRILLMASTER_AI_MODEL","qwen2.5:7b-instruct")
        self.timeout=int(os.getenv("DRILLMASTER_AI_TIMEOUT",str(max(timeout,120))))
        self.last_status="disabled"
    @property
    def enabled(self): return os.getenv("DRILLMASTER_AI_IMPORT","0").lower() in {"1","true","yes","on"}
    def available(self):
        if not self.enabled: self.last_status="disabled"; return False
        try:
            req=urllib.request.Request(f"{self.endpoint}/api/tags",method="GET")
            with urllib.request.urlopen(req,timeout=2) as response:
                data=json.loads(response.read().decode("utf-8"))
                names={m.get("name") for m in data.get("models",[])}
                if self.model not in names:
                    self.last_status="model-not-installed"; return False
                self.last_status="available"; return response.status==200
        except (OSError,urllib.error.URLError): self.last_status="unreachable"; return False
        except Exception: self.last_status="unavailable"; return False
    def map_context(self, context, allowed_fields=None):
        if not self.available(): return []
        fields=sorted(set(allowed_fields or ALLOWED_FIELDS)&ALLOWED_FIELDS)
        prompt={"task":"Map workbook cells to canonical drilling fields.","rules":["Return JSON only: {proposals: []}.","Never invent values.","Keep source_sheet, source_row and source_column.","Return confidence between 0 and 1.","Use null when ambiguous."],"allowed_fields":fields,"context":context}
        body=json.dumps({"model":self.model,"stream":False,"format":"json","prompt":json.dumps(prompt,ensure_ascii=False)}).encode()
        try:
            req=urllib.request.Request(f"{self.endpoint}/api/generate",data=body,headers={"Content-Type":"application/json"},method="POST")
            with urllib.request.urlopen(req,timeout=self.timeout) as response: payload=json.loads(response.read().decode("utf-8"))
            raw=payload.get("response","{}"); result=json.loads(raw) if isinstance(raw,str) else raw
            proposals=result.get("proposals",[]) if isinstance(result,dict) else []
            valid=[p for p in proposals if self._valid_proposal(p,fields)]; self.last_status=f"ok:{len(valid)}"; return valid
        except Exception as exc:
            self.last_status=f"error:{type(exc).__name__}"; logger.warning("Local AI import mapping unavailable: %s",exc); return []
    @staticmethod
    def _valid_proposal(p,allowed):
        if not isinstance(p,dict) or p.get("field") not in allowed or not p.get("source_sheet") or p.get("source_row") is None or p.get("value") is None: return False
        try: confidence=float(p.get("confidence",0))
        except (TypeError,ValueError): return False
        return 0<=confidence<=1
