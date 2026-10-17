"""
conversation.py -- Conversation controller.

Orchestrates the flow using LLM tool calling:
  1. LLM identifies information from worker's speech
  2. LLM calls update_case_info tool with structured arguments
  3. ConversationController processes the tool call
  4. Case state is updated
  5. System prompt is rebuilt with case context
  6. tool.result is sent back to the LLM

This is the bridge between the voice layer and the case layer.
"""

import json

from app.agent.prompts import build_system_prompt
from app.case.state import CaseManager
from app.case.models import (
    IssueCategory, WorkerType, IndianState, SafetyLevel,
    CaseStatus, STATE_NAME_MAP,
)


def _resolve_state(state_str: str) -> IndianState:
    """
    Resolve a state string from the LLM to our IndianState enum.
    Handles exact matches, lowercase variations, and STATE_NAME_MAP lookups.
    """
    if not state_str:
        return IndianState.UNKNOWN

    # Try exact enum match first
    for s in IndianState:
        if s.value.lower() == state_str.lower():
            return s

    # Try STATE_NAME_MAP
    state_lower = state_str.lower().strip()
    if state_lower in STATE_NAME_MAP:
        return STATE_NAME_MAP[state_lower]

    return IndianState.UNKNOWN


def _resolve_issue(issue_str: str) -> IssueCategory:
    """Resolve issue string to enum."""
    for ic in IssueCategory:
        if ic.value == issue_str:
            return ic
    return IssueCategory.UNKNOWN


def _resolve_worker_type(wt_str: str) -> WorkerType:
    """Resolve worker type string to enum."""
    for wt in WorkerType:
        if wt.value == wt_str:
            return wt
    return WorkerType.UNKNOWN


class ConversationController:
    """
    Processes LLM tool calls and updates case state.

    Two entry points:
      - process_tool_call(): handles update_case_info tool calls from LLM
      - process_transcript(): logs user transcripts (no keyword extraction)
    """

    def __init__(self):
        self.case_manager = CaseManager()
        self._transcript_history = []

    def process_tool_call(self, tool_name: str, arguments: dict) -> dict:
        """
        Process a tool.call from the LLM.

        Args:
            tool_name: "update_case_info"
            arguments: dict of extracted fields from the LLM

        Returns:
            {
                "tool_result": str,           # JSON string to send back
                "changed_fields": [...],
                "new_prompt": str | None,
                "needs_prompt_update": bool,
            }
        """
        if tool_name != "update_case_info":
            return {
                "tool_result": json.dumps({"status": "error", "message": f"Unknown tool: {tool_name}"}),
                "changed_fields": [],
                "new_prompt": None,
                "needs_prompt_update": False,
            }

        confidence = arguments.get("confidence", "medium")
        updates = {}

        # ── Resolve each field from the LLM's output ─────────────
        if "issue_category" in arguments and arguments["issue_category"] != "unknown":
            issue = _resolve_issue(arguments["issue_category"])
            if issue != IssueCategory.UNKNOWN:
                updates["issue_category"] = issue

        if "worker_type" in arguments and arguments["worker_type"] != "unknown":
            wt = _resolve_worker_type(arguments["worker_type"])
            if wt != WorkerType.UNKNOWN:
                updates["worker_type"] = wt

        if "state" in arguments:
            state = _resolve_state(arguments["state"])
            if state != IndianState.UNKNOWN:
                updates["state"] = state

        # String fields — pass through directly
        for field in [
            "platform_or_employer", "amount", "payment_pending_duration",
            "incident_date", "deactivation_reason", "injury_details",
        ]:
            if field in arguments and arguments[field]:
                updates[field] = arguments[field]

        # ── Apply updates ─────────────────────────────────────────
        changed = self.case_manager.update_fields(updates)

        # ── Log for development ───────────────────────────────────
        if changed:
            print(f"\n  [case] Updated: {changed} (confidence: {confidence})")
            print(f"  [case] Status: {self.case_manager.case.status.value}")
            filled = self.case_manager.case.get_filled_fields()
            for k, v in filled.items():
                print(f"  [case]   {k}: {v}")

        # ── Build tool result ─────────────────────────────────────
        next_question = self.case_manager.get_next_question()
        result = {
            "status": "updated" if changed else "no_change",
            "fields_updated": changed,
            "case_status": self.case_manager.case.status.value,
        }
        if next_question:
            result["next_question"] = next_question
            result["instruction"] = (
                "Ask this question naturally in the worker's language. "
                "Do NOT repeat information already collected."
            )
        elif self.case_manager.is_ready_for_retrieval():
            result["instruction"] = (
                "All required information has been collected. "
                "Summarize what you know and tell the worker you will "
                "now look into their rights."
            )

        tool_result_str = json.dumps(result)

        # ── Rebuild prompt if state changed ───────────────────────
        new_prompt = None
        needs_update = False
        if changed:
            context = self.case_manager.get_case_context()
            new_prompt = build_system_prompt(context)
            needs_update = True

        return {
            "tool_result": tool_result_str,
            "changed_fields": changed,
            "new_prompt": new_prompt,
            "needs_prompt_update": needs_update,
        }

    def process_transcript(self, text: str):
        """Log user transcript for history (classification is done by LLM tools)."""
        if text and text.strip():
            self._transcript_history.append(text)
            self.case_manager.case.turn_count += 1
            if self.case_manager.case.raw_description is None:
                self.case_manager.case.raw_description = text

    def get_initial_prompt(self) -> str:
        """Get the system prompt for the initial session.update."""
        context = self.case_manager.get_case_context()
        return build_system_prompt(context)

    @property
    def case(self):
        return self.case_manager.case
