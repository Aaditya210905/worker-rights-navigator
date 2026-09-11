"""
orchestrator.py -- Backend orchestrator for WorkerSaathi.

Receives tool calls from the voice agent, validates them,
executes the appropriate backend operation, and returns
structured results.

The LLM cannot directly access the database, Qdrant, or
filesystem. It only gets controlled tool results.

Tool call lifecycle:
  LLM -> tool.call -> Orchestrator -> validate -> execute -> format -> tool.result
"""

import json
from pathlib import Path
from typing import Optional

from app.agent.prompts import build_system_prompt
from app.agent.tool_registry import TOOL_PERMISSIONS
from app.case.state import CaseManager
from app.case.models import (
    IssueCategory, WorkerType, IndianState, SafetyLevel,
    CaseStatus, STATE_NAME_MAP,
)
from app.db.database import db
from app.evidence.action_planner import ActionPlanner


# ── Error codes ──────────────────────────────────────────────────────────────

class ToolError:
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    TOOL_NOT_ALLOWED = "TOOL_NOT_ALLOWED"
    RAG_UNAVAILABLE = "RAG_UNAVAILABLE"
    NO_EVIDENCE_FOUND = "NO_EVIDENCE_FOUND"
    CASE_INCOMPLETE = "CASE_INCOMPLETE"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"


class Orchestrator:
    """
    Backend orchestrator.

    Validates and executes tool calls from the voice agent.
    Owns the CaseManager and provides controlled access to
    the RAG system.

    Usage:
        orch = Orchestrator()
        result = orch.handle_tool_call("retrieve_rights", {"query": "..."})
    """

    def __init__(self):
        self.case_manager = CaseManager()
        self._transcript_history = []
        self._retriever = None  # Lazy-loaded
        self._last_evidence = None  # Cache for generate_evidence

    def handle_tool_call(self, tool_name: str, arguments: dict) -> dict:
        """
        Process a tool call from the voice agent.

        Args:
            tool_name: name of the tool
            arguments: dict of arguments from the LLM

        Returns:
            {
                "tool_result": str,         # JSON string for tool.result
                "needs_prompt_update": bool,
                "new_prompt": str | None,
                "changed_fields": list,
            }
        """
        # ── Permission check ─────────────────────────────────────
        status = self.case_manager.case.status.value
        allowed = TOOL_PERMISSIONS.get(tool_name, [])

        if tool_name not in TOOL_PERMISSIONS:
            return self._error_result(
                ToolError.UNKNOWN_TOOL,
                f"Unknown tool: {tool_name}"
            )

        if status not in allowed:
            return self._error_result(
                ToolError.TOOL_NOT_ALLOWED,
                f"Tool '{tool_name}' not available in status '{status}'. "
                f"Allowed: {allowed}"
            )

        # ── Dispatch ─────────────────────────────────────────────
        handlers = {
            "update_case_info": self._handle_update_case,
            "retrieve_rights": self._handle_retrieve_rights,
            "generate_evidence": self._handle_generate_evidence,
            "draft_message": self._handle_draft_message,
            "escalate_safety": self._handle_escalate_safety,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return self._error_result(
                ToolError.UNKNOWN_TOOL,
                f"No handler for tool: {tool_name}"
            )

        try:
            return handler(arguments)
        except Exception as e:
            print(f"  [orchestrator] Error in {tool_name}: {e}")
            return self._error_result(
                ToolError.TOOL_TIMEOUT,
                f"Tool execution failed: {str(e)}"
            )

    # ── Tool 1: update_case_info ─────────────────────────────────────────────

    def _handle_update_case(self, arguments: dict) -> dict:
        """Extract and save case fields from worker speech."""
        confidence = arguments.get("confidence", "medium")
        updates = {}

        # Resolve enums
        if "issue_category" in arguments and arguments["issue_category"] != "unknown":
            issue = self._resolve_issue(arguments["issue_category"])
            if issue != IssueCategory.UNKNOWN:
                updates["issue_category"] = issue

        if "worker_type" in arguments and arguments["worker_type"] != "unknown":
            wt = self._resolve_worker_type(arguments["worker_type"])
            if wt != WorkerType.UNKNOWN:
                updates["worker_type"] = wt

        if "state" in arguments:
            state = self._resolve_state(arguments["state"])
            if state != IndianState.UNKNOWN:
                updates["state"] = state

        # String fields
        for field in [
            "platform_or_employer", "amount", "payment_pending_duration",
            "incident_date", "deactivation_reason", "injury_details",
        ]:
            if field in arguments and arguments[field]:
                updates[field] = arguments[field]

        # Apply
        changed = self.case_manager.update_fields(updates)

        if changed:
            print(f"\n  [case] Updated: {changed} (confidence: {confidence})")
            print(f"  [case] Status: {self.case_manager.case.status.value}")
            filled = self.case_manager.case.get_filled_fields()
            for k, v in filled.items():
                print(f"  [case]   {k}: {v}")

        # Build result
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
                "All required information collected. Tell the worker you "
                "will now check their rights. Then call retrieve_rights."
            )

        return self._success_result(result, changed)

    # ── Tool 2: retrieve_rights ──────────────────────────────────────────────

    def _handle_retrieve_rights(self, arguments: dict) -> dict:
        """Search the Central legal knowledge base."""
        query = arguments.get("query", "")

        # Lazy-load the retriever
        retriever = self._get_retriever()
        if retriever is None:
            return self._error_result(
                ToolError.RAG_UNAVAILABLE,
                "Legal knowledge service is temporarily unavailable. "
                "Tell the worker you cannot verify legal information right now."
            )

        # Use case state for structured retrieval
        case = self.case_manager.case
        worker_type = case.worker_type.value if case.worker_type else "unknown"
        issue = case.issue_category.value if case.issue_category else None
        state = case.state.value if case.state and case.state != IndianState.UNKNOWN else None

        evidence = retriever.retrieve(
            query=query,
            worker_type=worker_type,
            state=state,
            issue=issue,
            raw_description=case.raw_description,
        )

        # Cache for generate_evidence
        self._last_evidence = evidence

        # Update case status
        self.case_manager.update_field("status", CaseStatus.RIGHTS_VERIFIED)

        # Build prompt context with evidence
        prompt_context = evidence.to_prompt_context()

        result = {
            "status": "success",
            "legal_evidence": prompt_context,
            "coverage": evidence.coverage.value,
            "instruction": self._get_evidence_instruction(evidence),
        }

        return self._success_result(result, [], evidence_prompt=prompt_context)

    # ── Tool 3: generate_evidence ────────────────────────────────────────────

    def _handle_generate_evidence(self, arguments: dict) -> dict:
        """Build structured evidence package."""
        purpose = arguments.get("purpose", "reference")
        case = self.case_manager.case
        filled = case.get_filled_fields()

        if len(filled) < 2:
            return self._error_result(
                ToolError.CASE_INCOMPLETE,
                "Not enough case information. Continue collecting details."
            )

        # Build action plan
        action_plan_steps = ActionPlanner.generate_plan(case, self._last_evidence)
        db.save_action_plan(case.case_id, action_plan_steps)

        # Build package distinguishing facts vs claims
        package = {
            "purpose": purpose,
            "case_id": case.case_id,
            "created_at": getattr(case, 'created_at', ''),
            "worker_summary": {},
            "claims": {},
            "legal_facts": "",
            "action_plan": action_plan_steps,
            "missing_fields": self.case_manager.get_missing_fields()
        }

        # Worker info (claims)
        if case.worker_type:
            package["worker_summary"]["worker_type"] = case.worker_type.value
        if case.state and case.state != IndianState.UNKNOWN:
            package["worker_summary"]["state"] = case.state.value
        if case.platform_or_employer:
            package["claims"]["employer"] = case.platform_or_employer

        # Incident claims
        if case.issue_category:
            package["claims"]["issue"] = case.issue_category.value
        if case.amount:
            package["claims"]["amount_claimed"] = case.amount
        if case.payment_pending_duration:
            package["claims"]["pending_since"] = case.payment_pending_duration
        if case.incident_date:
            package["claims"]["incident_date"] = case.incident_date
        if case.injury_details:
            package["claims"]["injury_details"] = case.injury_details
        if case.deactivation_reason:
            package["claims"]["deactivation_reason"] = case.deactivation_reason
        if case.raw_description:
            package["claims"]["worker_statement"] = case.raw_description

        # Legal evidence (verified facts)
        if self._last_evidence:
            package["legal_facts"] = self._last_evidence.to_prompt_context()

        # Update case status
        self.case_manager.update_field("status", CaseStatus.EVIDENCE_GENERATED)

        result = {
            "status": "success",
            "evidence_package": json.dumps(package, ensure_ascii=False, indent=2),
            "instruction": (
                "Share this evidence package with the worker. "
                "Explain each section clearly. Emphasize the Action Plan steps. "
                "Ask if they want to draft a follow-up message to their employer."
            ),
        }

        return self._success_result(result, [])

    # ── Tool 4: draft_message ────────────────────────────────────────────────

    def _handle_draft_message(self, arguments: dict) -> dict:
        """Draft a follow-up message for the worker."""
        recipient = arguments.get("recipient", "employer")
        tone = arguments.get("tone", "formal")
        case = self.case_manager.case

        # Build message context for the LLM
        parts = []
        parts.append(f"Recipient: {recipient}")
        parts.append(f"Tone: {tone}")

        if case.issue_category:
            parts.append(f"Issue: {case.issue_category.value.replace('_', ' ')}")
        if case.amount:
            parts.append(f"Amount: Rs. {case.amount}")
        if case.payment_pending_duration:
            parts.append(f"Pending since: {case.payment_pending_duration}")
        if case.incident_date:
            parts.append(f"Incident date: {case.incident_date}")

        result = {
            "status": "success",
            "message_context": "\n".join(parts),
            "instruction": (
                f"Draft a {tone} message to {recipient} about the worker's "
                f"issue. Use the case details provided. Keep it professional. "
                f"Write in the language the worker is using. "
                f"Present it as a DRAFT and ask if they want changes. "
                f"DO NOT include Aadhaar, bank details, OTP, UPI PIN, or passwords."
            ),
        }

        return self._success_result(result, [])

    # ── Tool 5: escalate_safety ──────────────────────────────────────────────

    def _handle_escalate_safety(self, arguments: dict) -> dict:
        """Handle safety escalation — highest priority."""
        danger_type = arguments.get("danger_type", "other_emergency")
        description = arguments.get("description", "")

        print(f"\n  [SAFETY] ESCALATION: {danger_type}")
        if description:
            print(f"  [SAFETY] Details: {description}")

        # Update case status
        self.case_manager.update_field("status", CaseStatus.SAFETY_ESCALATION)
        self.case_manager.update_field("safety_level", SafetyLevel.CRITICAL)

        # Build verified safety response
        safety_info = self._get_safety_response(danger_type)

        result = {
            "status": "safety_escalation",
            "danger_type": danger_type,
            "safety_response": safety_info,
            "instruction": (
                "SAFETY IS THE TOP PRIORITY. Follow these steps:\n"
                "1. Ask if the worker is safe RIGHT NOW.\n"
                "2. If in immediate danger, tell them to call 112.\n"
                "3. Share the relevant helpline numbers below.\n"
                "4. Do NOT discuss legal rights until safety is confirmed.\n"
                "5. Speak calmly and reassuringly."
            ),
        }

        return self._success_result(result, [], is_safety=True)

    # ── Helper methods ───────────────────────────────────────────────────────

    def _get_retriever(self):
        """Lazy-load the RAG retriever."""
        if self._retriever is not None:
            return self._retriever

        try:
            from app.rag.loader import ResearchLoader
            from app.rag.chunker import chunk_documents
            from app.rag.embeddings import EmbeddingClient
            from app.rag.qdrant_store import QdrantStore
            from app.rag.retriever import HybridRetriever

            project_root = Path(__file__).resolve().parent.parent.parent
            research_dir = project_root / "knowledge" / "workersaathi" / "json"
            qdrant_path = project_root / "data" / "qdrant"

            if not research_dir.exists():
                print("  [orchestrator] Research data not found")
                return None

            loader = ResearchLoader(str(research_dir))
            loader.load()
            docs = loader.to_rag_documents()
            chunks = chunk_documents(docs)

            embedder = EmbeddingClient()
            qdrant = QdrantStore(path=str(qdrant_path))

            self._retriever = HybridRetriever(
                qdrant=qdrant,
                embedder=embedder,
                documents=chunks,
                gaps=loader.gaps,
                conflicts=loader.conflicts,
            )
            print("  [orchestrator] RAG retriever loaded")
            return self._retriever

        except Exception as e:
            print(f"  [orchestrator] Failed to load retriever: {e}")
            return None

    def _get_evidence_instruction(self, evidence) -> str:
        """Build instruction based on evidence coverage."""
        from app.rag.models import RetrievalCoverage

        if evidence.coverage == RetrievalCoverage.FULL:
            return (
                "Legal evidence found. Present the key findings to the worker "
                "in simple language. Cite the source. Mention limitations."
            )
        elif evidence.coverage == RetrievalCoverage.PARTIAL:
            return (
                "Some evidence found but there are known gaps. Present what "
                "was found and clearly state what information is missing."
            )
        elif evidence.coverage == RetrievalCoverage.GAP:
            return (
                "No verified Central Government information found for this "
                "specific issue. Tell the worker honestly. Do NOT invent "
                "legal rights or procedures."
            )
        elif evidence.coverage == RetrievalCoverage.CONFLICT:
            return (
                "CONFLICTING information found in official sources. "
                "Tell the worker about the conflict. Do NOT choose one side. "
                "Recommend consulting a legal professional."
            )
        else:
            return (
                "No relevant evidence found. Tell the worker you could not "
                "find verified information. Suggest consulting a labour "
                "office or legal aid center."
            )

    def _get_safety_response(self, danger_type: str) -> str:
        """Return verified emergency information."""
        lines = []
        lines.append("EMERGENCY HELPLINES:")
        lines.append("  - Emergency (Police/Fire/Ambulance): 112")
        lines.append("  - Police: 100")
        lines.append("  - Ambulance: 108")
        lines.append("  - Women Helpline: 1091 / 181")
        lines.append("  - Child Helpline (Childline): 1098")
        lines.append("  - Anti-Trafficking: 1800-419-8588 (toll-free)")

        if danger_type in ("child_labour", "trafficking"):
            lines.append("")
            lines.append("SPECIFIC:")
            lines.append("  - National Commission for Protection of Child Rights: 1800-121-0260")
            lines.append("  - Anti-Human Trafficking Unit: Contact local police or 112")

        if danger_type in ("immediate_physical_danger", "workplace_trapped"):
            lines.append("")
            lines.append("SPECIFIC:")
            lines.append("  - NDRF (National Disaster Response Force): 011-24363260")
            lines.append("  - Fire Brigade: 101")

        lines.append("")
        lines.append("IMPORTANT: These are verified government helpline numbers.")
        lines.append("Do NOT share any numbers not listed above.")

        return "\n".join(lines)

    def _resolve_state(self, state_str: str) -> IndianState:
        if not state_str:
            return IndianState.UNKNOWN
        for s in IndianState:
            if s.value.lower() == state_str.lower():
                return s
        state_lower = state_str.lower().strip()
        if state_lower in STATE_NAME_MAP:
            return STATE_NAME_MAP[state_lower]
        return IndianState.UNKNOWN

    def _resolve_issue(self, issue_str: str) -> IssueCategory:
        for ic in IssueCategory:
            if ic.value == issue_str:
                return ic
        return IssueCategory.UNKNOWN

    def _resolve_worker_type(self, wt_str: str) -> WorkerType:
        for wt in WorkerType:
            if wt.value == wt_str:
                return wt
        return WorkerType.UNKNOWN

    def _success_result(
        self, result: dict, changed: list,
        evidence_prompt: str = None, is_safety: bool = False,
    ) -> dict:
        """Build a success response."""
        # Rebuild prompt with case context + evidence
        context = self.case_manager.get_case_context()
        if evidence_prompt:
            context += f"\n\n--- LEGAL EVIDENCE ---\n{evidence_prompt}"

        new_prompt = build_system_prompt(context)

        return {
            "tool_result": json.dumps(result, ensure_ascii=False),
            "changed_fields": changed,
            "new_prompt": new_prompt,
            "needs_prompt_update": bool(changed) or evidence_prompt is not None or is_safety,
        }

    def _error_result(self, code: str, message: str) -> dict:
        result = {
            "status": "error",
            "error_code": code,
            "message": message,
        }
        return {
            "tool_result": json.dumps(result),
            "changed_fields": [],
            "new_prompt": None,
            "needs_prompt_update": False,
        }

    def process_transcript(self, text: str):
        """Log user transcript."""
        if text and text.strip():
            self._transcript_history.append(text)
            self.case_manager.case.turn_count += 1
            if self.case_manager.case.raw_description is None:
                self.case_manager.case.raw_description = text

    def get_initial_prompt(self) -> str:
        """Get the system prompt for initial session."""
        context = self.case_manager.get_case_context()
        return build_system_prompt(context)

    @property
    def case(self):
        return self.case_manager.case
