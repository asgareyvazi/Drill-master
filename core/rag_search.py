"""
RAG Historical DDR Search - Professional Intelligence Feature (P2)

Implements:
- RAG (Retrieval Augmented Generation) over historical DDRs
- Search: Operations Summary, Depth Progress, Time Breakdown, NPT, Mud Summary, etc.
- AI reasons over validated numerical results, not invents

Architecture:
- Vector store from validated reports (not raw Excel)
- Embeddings from summary + time logs + drilling params
- Retrieval with evidence: Source Reports, Date Range, Metrics, Confidence, Reason
- AI explains/interprets, deterministic engines calculate

Future models:
- Qwen → general mapping
- Gemma → comparison and review
- Qwen-VL → PDF vision
- Table Transformer → table structure
"""

from typing import List, Dict, Any, Optional
import logging
import re

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
                            "confidence": 0.75,  # placeholder, future will use embedding similarity
                            "reason": f"Matched query '{query}' in {r.get('type')}",
                        },
                        "retrieval_method": "DB LIKE search (future: vector embeddings)",
                    }
                )

            return enriched

        except Exception as exc:
            logger.error(f"Historical search failed: {exc}", exc_info=True)
            return []

    def rag_query(self, question: str, well_id: int = None) -> Dict[str, Any]:
        """RAG query: retrieve relevant DDRs and generate answer with evidence.

        This is where AI would reason over validated results.

        Flow:
        1. Retrieve relevant reports via search
        2. Collect validated numerical data (depth, ROP, NPT, mud, etc.)
        3. Call engineering engines for calculations if needed (via ai_tools)
        4. Generate answer with evidence and confidence

        Never invent engineering formulas - use deterministic engines.
        """
        retrieved = self.search(question, well_id=well_id, limit=5)

        if not retrieved:
            return {
                "answer": "No relevant historical DDRs found",
                "evidence": [],
                "confidence": 0.0,
                "method": "RAG - retrieval over validated reports",
            }

        # For now, simple answer with evidence
        # Future: call LLM with retrieved context (limited, not entire workbook)

        # Example evidence collection
        evidence_summary = []
        for item in retrieved:
            evidence_summary.append(
                {
                    "source_report": item.get("id"),
                    "title": item.get("title", ""),
                    "type": item.get("type", ""),
                    "confidence": item.get("evidence", {}).get("confidence", 0.75),
                }
            )

        return {
            "answer": f"Found {len(retrieved)} relevant historical reports for '{question}' - see evidence",
            "evidence": evidence_summary,
            "retrieved": retrieved,
            "confidence": 0.7,
            "method": "RAG Historical DDR Search - validated data only",
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
