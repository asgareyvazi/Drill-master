"""Deterministic, well-scoped keyword retrieval with typed source evidence.

This module does not implement embeddings, vector search, an LLM call, numeric
validation, or a calibrated relevance probability. Those are not inferred from
a database substring match. Engineering calculations belong to canonical tools.
"""

from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class HistoricalDDRSearch:
    """Search over historical DDRs with evidence."""

    def __init__(self, db_manager):
        self.db = db_manager

    def search(self, query: str, well_id: int = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Search historical reports.

        For now uses DB search_all, future will use vector embeddings.

        Returns results with evidence for AI interpretation.
        """
        if not query or len(query.strip()) < 2:
            return []

        # Use existing search
        try:
            results = self.db.search_all(query, well_id=well_id, limit=limit)

            # Enrich with evidence
            enriched = []
            for r in results:
                enriched.append(
                    {
                        **r,
                        "evidence": {
                            "source": r.get("type", "unknown"),
                            "id": r.get("id"),
                            "title": r.get("title", ""),
                            "confidence": None,  # substring matches are not calibrated probabilities
                            "reason": f"Matched query '{query}' in {r.get('type')}",
                        },
                        "retrieval_method": "DB literal substring search",
                    }
                )

            return enriched

        except Exception as exc:
            logger.error(f"Historical search failed: {exc}", exc_info=True)
            raise

    def rag_query(self, question: str, well_id: int = None) -> Dict[str, Any]:
        """Return typed retrieval evidence, not generated/validated numerical facts."""
        if not question or len(question.strip()) < 2:
            return {"status": "invalid-query", "answer": "Enter at least two characters",
                    "evidence": [], "confidence": None, "method": "DB literal substring search"}
        try:
            retrieved = self.search(question, well_id=well_id, limit=5)
        except Exception:
            return {"status": "failed", "answer": "Historical search failed; results unavailable",
                    "evidence": [], "confidence": None, "method": "DB literal substring search"}

        if not retrieved:
            return {
                "status": "no-matches",
                "answer": "No keyword matches found",
                "evidence": [],
                "confidence": None,
                "method": "DB literal substring search",
            }

        # For now, simple answer with evidence
        # Future: call LLM with retrieved context (limited, not entire workbook)

        # Example evidence collection
        evidence_summary = []
        for item in retrieved:
            evidence_summary.append(
                {
                    "source_report": item.get("id") if item.get("type") == "report" else item.get("report_id"),
                    "source_entity_id": item.get("id"),
                    "title": item.get("title", ""),
                    "type": item.get("type", ""),
                    "confidence": item.get("evidence", {}).get("confidence"),
                }
            )

        return {
            "status": "matched",
            "answer": f"Found {len(retrieved)} keyword matches for '{question}' - see typed source evidence",
            "evidence": evidence_summary,
            "retrieved": retrieved,
            "confidence": None,
            "method": "DB literal substring search; semantic/numeric validation not performed",
            "future": "Vector embeddings + Qwen/Gemma for explanation over validated numerical results",
            "safety": "AI explains, deterministic engines calculate - never invent formulas",
        }

    def find_similar_operations(self, current_report_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """Find similar operations to current report.

        Useful for Operations Intelligence: compare current ROP/NPT/Mud with historical.
        """
        try:
            report = self.db.get_daily_report_by_id(current_report_id)
            if not report:
                return []

            well_id = report.get("well_id")

            # Get current params
            params = self.db.get_drilling_parameters(report_id=current_report_id) or {}

            # Search for similar depth or formation
            formation = report.get("formation", "") or ""

            similar = []
            if formation:
                similar = self.search(formation, well_id=well_id, limit=limit)

            return similar

        except Exception as exc:
            logger.error(f"Similar operations search failed: {exc}", exc_info=True)
            return []
