"""PDF table extraction with optional Camelot and safe fallback."""
import logging
logger = logging.getLogger(__name__)


def extract_tables(path, pages="all"):
    """Return tables plus parser metrics; never silently discard failures."""
    try:
        import camelot
    except ImportError:
        return {"tables": [], "engine": "unavailable", "error": "Install camelot-py for text PDF tables"}
    try:
        tables = camelot.read_pdf(str(path), pages=pages, flavor="stream")
        result = []
        for table in tables:
            result.append({"data": table.df.to_dict(orient="records"), "report": getattr(table, "parsing_report", {})})
        return {"tables": result, "engine": "camelot", "error": None}
    except Exception as exc:
        logger.error("PDF table extraction failed: %s", exc, exc_info=True)
        return {"tables": [], "engine": "camelot", "error": str(exc)}
