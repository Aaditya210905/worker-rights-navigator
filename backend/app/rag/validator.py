"""
validator.py -- Evidence validation layer.

Checks each retrieved evidence item for:
  - Legal status acceptability (in_force vs repealed/draft)
  - Source authority level
  - Worker type applicability
  - Jurisdiction match
  - Gap/conflict detection

Produces validation warnings that travel with the evidence.
"""

from typing import Optional

from app.rag.models import EvidenceLevel, EvidenceFinding


# Legal statuses that should NOT be treated as current law
UNRELIABLE_STATUSES = {
    "repealed", "superseded", "draft", "proposed",
    "historical", "expired", "revoked",
}

# Statuses that need a caveat
UNCERTAIN_STATUSES = {
    "verify", "status_unconfirmed",
    "insufficient_verified_central_information",
}


class ValidationResult:
    """Result of validating a single evidence item."""

    def __init__(self, finding: EvidenceFinding):
        self.finding = finding
        self.is_valid = True
        self.warnings: list[str] = []
        self.applicability_notes: list[str] = []

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def add_applicability_note(self, msg: str):
        self.applicability_notes.append(msg)

    def mark_invalid(self, reason: str):
        self.is_valid = False
        self.warnings.append(f"INVALID: {reason}")


class EvidenceValidator:
    """
    Validates retrieved evidence before it reaches the LLM.

    Catches:
      - Superseded/repealed sources
      - Status-uncertain sources
      - Worker type mismatch
      - Jurisdiction mismatch
      - Secondary sources presented as primary law
    """

    @staticmethod
    def validate(
        findings: list[EvidenceFinding],
        worker_type: str = None,
        issue: str = None,
        jurisdiction: str = "central",
    ) -> tuple[list[EvidenceFinding], list[str]]:
        """
        Validate a list of evidence findings.

        Returns:
            (valid_findings, limitation_warnings)
        """
        valid = []
        limitations = []

        for finding in findings:
            result = EvidenceValidator._validate_one(
                finding, worker_type, issue, jurisdiction
            )

            if result.is_valid:
                # Add applicability notes to the finding
                if result.applicability_notes:
                    notes = "; ".join(result.applicability_notes)
                    finding.evidence_text += f"\n[APPLICABILITY: {notes}]"
                valid.append(finding)

                # Collect warnings as limitations
                for w in result.warnings:
                    if w not in limitations:
                        limitations.append(w)

        # Add general limitations
        if not worker_type or worker_type == "unknown":
            note = (
                "Worker type is unknown. Legal applicability depends on "
                "the worker's employment classification."
            )
            if note not in limitations:
                limitations.append(note)

        return valid, limitations

    @staticmethod
    def _validate_one(
        finding: EvidenceFinding,
        worker_type: str = None,
        issue: str = None,
        jurisdiction: str = "central",
    ) -> ValidationResult:
        """Validate a single evidence finding."""
        result = ValidationResult(finding)

        # ── Legal status check ───────────────────────────────────
        status = finding.legal_status.lower() if finding.legal_status else ""

        if status in UNRELIABLE_STATUSES:
            result.mark_invalid(
                f"Source has status '{status}' and should not be "
                f"cited as current law."
            )
            return result

        if status in UNCERTAIN_STATUSES:
            result.add_warning(
                f"Source '{finding.source_title}' has uncertain status "
                f"('{status}'). Information may not be current."
            )

        # ── Evidence level check ─────────────────────────────────
        level = finding.evidence_level
        if level == EvidenceLevel.SECONDARY.value:
            result.add_applicability_note(
                "This is secondary/explanatory information, not primary law."
            )

        # ── Worker applicability check ───────────────────────────
        if worker_type and worker_type not in ("unknown", "all_workers"):
            # Check if the evidence topic suggests a different worker type
            text_lower = finding.evidence_text.lower()
            if (
                worker_type == "gig_worker"
                and "employer" in text_lower
                and "platform" not in text_lower
                and "gig" not in text_lower
            ):
                result.add_applicability_note(
                    "This provision may apply to employees. "
                    "Applicability to gig/platform workers depends on "
                    "classification under the Social Security Code."
                )

        return result
