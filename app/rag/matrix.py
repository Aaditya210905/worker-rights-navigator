"""
matrix.py -- Rights Matrix: deterministic legal source routing.

Given (worker_type, state, issue) → returns the relevant source_ids.
No LLM involved — this is pure data lookup.

The matrix is auto-generated from sources.json by the pipeline,
but can also be manually curated for precision.
"""

import json
from pathlib import Path
from typing import Optional

from app.rag.sources import SourceRegistry


class RightsMatrix:
    """
    Routes a worker's case to the relevant legal sources.

    Two modes:
      1. Dynamic: query the SourceRegistry directly (always up-to-date)
      2. Static: load from pre-built rights_matrix.json (fast, cacheable)
    """

    def __init__(self, registry: Optional[SourceRegistry] = None):
        self._registry = registry
        self._static_matrix = {}  # loaded from JSON

    def load_from_json(self, filepath: str):
        """Load a pre-built matrix from JSON."""
        with open(filepath, "r", encoding="utf-8") as f:
            self._static_matrix = json.load(f)

    def save_to_json(self, filepath: str):
        """Save the current matrix to JSON."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self._static_matrix, f, indent=2, ensure_ascii=False)

    def build_from_registry(self, registry: SourceRegistry):
        """
        Auto-generate the rights matrix from the source registry.

        Creates a lookup table:
            key = "worker_type|state|issue"
            value = [source_ids]
        """
        self._registry = registry
        matrix = {}

        worker_types = [
            "gig_worker", "construction_worker",
            "domestic_worker", "factory_worker", "other",
        ]
        issues = [
            "unpaid_wages", "workplace_injury",
            "platform_deactivation", "welfare", "registration",
        ]

        # Get all unique states
        states = registry.get_states_covered()
        # Also add a "Central" entry for central-only queries
        states_plus = ["Central"] + states

        for wt in worker_types:
            for state in states_plus:
                for issue in issues:
                    results = registry.query(
                        worker_type=wt,
                        state=state if state != "Central" else None,
                        issue=issue,
                        include_central=True,
                    )
                    if results:
                        key = f"{wt}|{state}|{issue}"
                        matrix[key] = [
                            {
                                "source_id": s.source_id,
                                "title": s.title,
                                "source_type": s.source_type.value,
                                "jurisdiction": s.jurisdiction.value,
                                "source_url": s.source_url,
                            }
                            for s in results
                        ]

        self._static_matrix = matrix

    def lookup(
        self,
        worker_type: str,
        state: str = None,
        issue: str = None,
    ) -> list[dict]:
        """
        Look up relevant sources for a case.

        Uses the registry directly if available, otherwise falls back
        to the static matrix.
        """
        # Prefer dynamic lookup from registry
        if self._registry:
            results = self._registry.query(
                worker_type=worker_type,
                state=state,
                issue=issue,
            )
            return [
                {
                    "source_id": s.source_id,
                    "title": s.title,
                    "source_type": s.source_type.value,
                    "jurisdiction": s.jurisdiction.value,
                    "source_url": s.source_url,
                    "authority": s.authority,
                    "status": s.status.value,
                }
                for s in results
            ]

        # Fall back to static matrix
        key = f"{worker_type}|{state or 'Central'}|{issue or 'all'}"
        return self._static_matrix.get(key, [])

    def get_matrix_stats(self) -> dict:
        """Return stats about the matrix."""
        return {
            "total_entries": len(self._static_matrix),
            "unique_sources": len(set(
                s["source_id"]
                for entries in self._static_matrix.values()
                for s in entries
            )),
        }
