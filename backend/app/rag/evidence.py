"""
evidence.py -- LegalEvidence assembly.

Takes validated, reranked retrieval results and gaps/conflicts,
and assembles the final LegalEvidence object that the LLM receives.

This is the last step before the agent — the controlled interface.
"""

from app.rag.models import (
    LegalEvidence, EvidenceFinding, RetrievalCoverage,
)


class EvidenceAssembler:
    """
    Assembles LegalEvidence from validated findings, gaps, and conflicts.

    Determines coverage level and builds prompt-ready context.
    """

    @staticmethod
    def assemble(
        findings: list[EvidenceFinding],
        gaps: list[dict],
        conflicts: list[dict],
        limitations: list[str],
        worker_type: str = "",
        issue: str = "",
        state: str = None,
        jurisdiction: str = "central",
    ) -> LegalEvidence:
        """
        Assemble the final LegalEvidence object.

        This is what the LLM receives — not raw Qdrant records.
        """
        # ── Determine coverage ───────────────────────────────────
        gap_keywords = [
            "not_found", "no verified", "gap", "unconfirmed",
            "insufficient_verified",
        ]
        findings_describe_gaps = findings and all(
            any(
                kw in (f.evidence_text.lower() + f.legal_status.lower())
                for kw in gap_keywords
            )
            for f in findings[:2]
        )

        # Determine coverage — findings take priority.
        # Conflicts are additive notes, NOT a reason to hide findings.
        if findings and not findings_describe_gaps:
            if gaps:
                coverage = RetrievalCoverage.PARTIAL
            else:
                coverage = RetrievalCoverage.FULL
        elif gaps and (not findings or findings_describe_gaps):
            coverage = RetrievalCoverage.GAP
        elif conflicts and not findings:
            # Only mark CONFLICT if we have NO usable findings
            coverage = RetrievalCoverage.CONFLICT
        else:
            coverage = RetrievalCoverage.NONE

        # ── Add state limitation ─────────────────────────────────
        all_limitations = list(limitations)  # copy
        if state and state.lower() not in ("central", "unknown", ""):
            all_limitations.insert(0,
                f"This information is from Central Government sources only. "
                f"State-specific ({state}) laws may also apply."
            )

        # Standard disclaimer
        disclaimer = (
            "WorkerSaathi is not a lawyer. This information is for "
            "guidance only. Consult a legal professional for specific advice."
        )
        if disclaimer not in all_limitations:
            all_limitations.append(disclaimer)

        # ── Build LegalEvidence ──────────────────────────────────
        return LegalEvidence(
            issue=issue,
            jurisdiction=jurisdiction,
            worker_type=worker_type,
            coverage=coverage,
            evidence=findings,
            gaps=[g.get("gap", g.get("description", "")) for g in gaps],
            conflicts=[c.get("description", "") for c in conflicts],
            limitations=all_limitations,
        )
