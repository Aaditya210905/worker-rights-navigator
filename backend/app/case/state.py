"""
state.py -- CaseManager: create, update, and query case state.

The CaseManager owns the authoritative case state.
The LLM conversation may reference it, but this module
is the single source of truth.
"""

from app.case.models import (
    CaseState, CaseStatus, WorkerType, IssueCategory,
    IndianState, SafetyLevel,
)
from app.case.fields import (
    get_missing_fields, get_next_question, has_required_fields,
    SAFETY_FIRST_QUESTION,
)
from app.db.database import db
import json


class CaseManager:
    """
    Manages a single worker case throughout the conversation.

    Responsibilities:
      - Create and hold the CaseState
      - Apply structured field updates
      - Advance the case status state machine
      - Determine the next question to ask
    """

    def __init__(self):
        self.case = CaseState()
        self._safety_asked = False
        self._sync_to_db()

    def _sync_to_db(self):
        """Sync current state to the database."""
        def _to_val(x, default=""):
            if x is None:
                return default
            return x.value if hasattr(x, "value") else str(x)

        db.upsert_case(
            case_id=self.case.case_id,
            worker_type=_to_val(self.case.worker_type, "unknown"),
            issue_category=_to_val(self.case.issue_category, "unknown"),
            status=_to_val(self.case.status, "new"),
            state=_to_val(self.case.state, "Unknown"),
            created_at=self.case.created_at
        )

    def update_field(self, field: str, value) -> bool:
        """
        Update a single case field. Returns True if the field changed.

        Validates that the field exists and the value is acceptable.
        """
        if not hasattr(self.case, field):
            return False

        # Normalize string values to corresponding enums if applicable
        if isinstance(value, str):
            try:
                if field == "status":
                    value = CaseStatus(value)
                elif field == "worker_type":
                    value = WorkerType(value)
                elif field == "issue_category":
                    value = IssueCategory(value)
                elif field == "state":
                    value = IndianState(value)
            except ValueError:
                pass

        old_value = getattr(self.case, field)
        if old_value == value:
            return False

        setattr(self.case, field, value)
        
        # Log event and sync
        db.log_event(
            case_id=self.case.case_id,
            event_type="field_updated",
            field=field,
            value=value.value if hasattr(value, "value") else value,
            source="worker_statement"
        )
        self._advance_status()
        self._sync_to_db()
        return True

    def update_fields(self, updates: dict) -> list:
        """
        Apply multiple field updates at once.
        Returns list of field names that actually changed.
        """
        changed = []
        for field, value in updates.items():
            if self.update_field(field, value):
                changed.append(field)
        return changed

    def get_next_question(self) -> str | None:
        """
        Determine the single most important question to ask next.

        Safety-first: for injury cases, ask about immediate safety
        before collecting more details.
        """
        # Safety-first for injury cases
        if (
            self.case.issue_category == IssueCategory.WORKPLACE_INJURY
            and not self._safety_asked
        ):
            self._safety_asked = True
            self.case.status = CaseStatus.SAFETY_CHECK
            return SAFETY_FIRST_QUESTION

        filled = self.case.get_filled_fields()
        return get_next_question(self.case.issue_category, filled)

    def is_ready_for_retrieval(self) -> bool:
        """Check if we have enough information for legal RAG."""
        filled = self.case.get_filled_fields()
        return has_required_fields(self.case.issue_category, filled)

    def get_missing_fields(self) -> list:
        """Get all missing fields with their questions."""
        filled = self.case.get_filled_fields()
        return get_missing_fields(self.case.issue_category, filled)

    def get_case_context(self) -> str:
        """
        Build a context string for injecting into the system prompt.
        Tells the LLM what we know and what to ask next.
        """
        lines = []

        # What we know
        filled = self.case.get_filled_fields()
        if filled:
            lines.append("INFORMATION COLLECTED SO FAR:")
            for k, v in filled.items():
                label = k.replace("_", " ").title()
                lines.append(f"  - {label}: {v}")
        else:
            lines.append("NO INFORMATION COLLECTED YET.")

        # What to ask next
        next_q = self.get_next_question()
        if next_q:
            lines.append(f"\nNEXT QUESTION TO ASK: {next_q}")
            lines.append(
                "Ask this question naturally. Do NOT repeat information "
                "the worker has already provided."
            )
        else:
            if self.is_ready_for_retrieval():
                lines.append(
                    "\nALL REQUIRED INFORMATION COLLECTED. "
                    "Summarize what you know and tell the worker "
                    "you will now check their rights."
                )
            else:
                lines.append(
                    "\nNo specific question needed. "
                    "Continue listening to the worker."
                )

        # Case status
        lines.append(f"\nCASE STATUS: {self.case.status.value}")

        return "\n".join(lines)

    def _advance_status(self):
        """Advance the case status based on what we know."""
        if self.case.status == CaseStatus.NEW:
            self.case.status = CaseStatus.LISTENING

        if (
            self.case.issue_category != IssueCategory.UNKNOWN
            and self.case.status in (CaseStatus.NEW, CaseStatus.LISTENING)
        ):
            self.case.status = CaseStatus.CLASSIFIED

        if (
            self.case.status == CaseStatus.CLASSIFIED
            and len(self.case.get_filled_fields()) > 2
        ):
            self.case.status = CaseStatus.COLLECTING_INFORMATION

        if self.is_ready_for_retrieval():
            if self.case.status in (CaseStatus.CLASSIFIED, CaseStatus.COLLECTING_INFORMATION):
                self.case.status = CaseStatus.RETRIEVING_RIGHTS
