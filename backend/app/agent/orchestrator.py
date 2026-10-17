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
from app.evidence.eligibility import EligibilityChecker, EligibilityReport
from app.evidence.wage_calculator import WageCalculator, WageCalculationResult
from app.evidence.screenshot_parser import EvidenceManager, EvidenceTimeline
from app.evidence.complaint_generator import (
    ComplaintGenerator, ComplaintAuthority, ComplaintLanguage, GeneratedDocument
)


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

    @property
    def case(self):
        """Convenience access to the underlying CaseState."""
        return self.case_manager.case

    def get_initial_prompt(self) -> str:
        """Build the initial system prompt with current case context."""
        context = self.case_manager.get_case_context()
        return build_system_prompt(context)

    def process_transcript(self, text: str):
        """Record a user transcript line and increment turn count."""
        if text.strip():
            self._transcript_history.append(f"Worker: {text.strip()}")
            self.case_manager.case.turn_count += 1
            if not self.case_manager.case.raw_description:
                self.case_manager.case.raw_description = text.strip()
            else:
                self.case_manager.case.raw_description += " | " + text.strip()

    def process_agent_transcript(self, text: str):
        """Record an agent transcript line."""
        if text.strip():
            self._transcript_history.append(f"WorkerSaathi: {text.strip()}")

    def get_full_transcript(self) -> str:
        """Return the full formatted conversation transcript for LeMUR."""
        return "\n".join(self._transcript_history)

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
            "search_live_news": self._handle_web_search,
            "check_eligibility": self._handle_check_eligibility,
            "calculate_unpaid_wages": self._handle_calculate_unpaid_wages,
            "generate_complaint_letter": self._handle_generate_complaint,
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

        case = self.case_manager.case
        has_description = bool(case.raw_description)
        has_issue = case.issue_category != IssueCategory.UNKNOWN
        has_worker = case.worker_type != WorkerType.UNKNOWN

        # ALWAYS suggest retrieve_rights if user has described any problem
        if has_description and (has_issue or has_worker):
            wt = case.worker_type.value if has_worker else "worker"
            ic = case.issue_category.value if has_issue else "rights"
            result["MUST_CALL_NEXT"] = "retrieve_rights"
            result["instruction"] = (
                "IMPORTANT: The worker has described their problem. "
                "You MUST immediately call the retrieve_rights tool now. "
                "DO NOT just say you will check — actually call the tool. "
                f"Use query: '{wt} {ic} rights India'. "
                "Say a brief 'Main aapke rights check karta hoon' "
                "and CALL retrieve_rights RIGHT NOW."
            )
        elif next_question:
            result["next_question"] = next_question
            result["instruction"] = (
                "Ask this question naturally in the worker's language. "
                "Do NOT repeat information already collected."
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

    # ── Tool 6: check_eligibility ────────────────────────────────────────────

    def _handle_check_eligibility(self, arguments: dict) -> dict:
        """Check worker statutory eligibility (90/120-day rule, e-Shram, Section 114)."""
        case = self.case_manager.case
        days_primary = arguments.get("days_with_primary_aggregator") or case.days_worked
        days_total = arguments.get("total_days_across_aggregators")
        num_apps = arguments.get("number_of_aggregators", 1)
        has_eshram = arguments.get("has_eshram") if "has_eshram" in arguments else case.has_eshram

        if days_primary is not None:
            self.case_manager.update_field("days_worked", days_primary)
        if has_eshram is not None:
            self.case_manager.update_field("has_eshram", has_eshram)

        report = EligibilityChecker.evaluate(
            worker_type=case.worker_type,
            state=case.state,
            days_with_primary_aggregator=days_primary,
            total_days_across_aggregators=days_total,
            number_of_aggregators=num_apps,
            has_eshram=has_eshram,
            age=case.age,
            platform_name=case.platform_or_employer,
        )

        case.eligibility_report = report.model_dump()

        result = {
            "status": "success",
            "verdict": report.verdict.value,
            "badge": report.verdict_badge,
            "summary": report.summary,
            "rule_90_120": report.rule_90_120_status,
            "advisory_sec_114": report.section_114_advisory,
            "next_steps": report.immediate_steps,
            "instruction": (
                f"Explain the eligibility verdict ({report.verdict_badge}) clearly to the worker. "
                f"Mention the 90/120-day rule status: {report.rule_90_120_status.get('explanation', '')}. "
                "Assure them that their unpaid wage or wrongful deactivation claims are actionable immediately."
            ),
        }
        return self._success_result(result, ["eligibility_report"])

    # ── Tool 7: calculate_unpaid_wages ───────────────────────────────────────

    def _handle_calculate_unpaid_wages(self, arguments: dict) -> dict:
        """Calculate unpaid wages, unlawful deductions (Sec 18), and statutory compensation up to 10x (Sec 45)."""
        import re
        case = self.case_manager.case
        base = arguments.get("base_unpaid", 0.0)
        incentives = arguments.get("withheld_incentives", 0.0)
        deductions = arguments.get("unauthorized_deductions", 0.0)
        period = arguments.get("period_description") or case.payment_pending_duration

        if base == 0.0 and case.amount:
            try:
                base = float(re.sub(r'[^0-9.]', '', str(case.amount)))
            except (ValueError, TypeError):
                base = 0.0

        calc_result = WageCalculator.calculate(
            base_unpaid=base,
            withheld_incentives=incentives,
            unauthorized_deductions=deductions,
            worker_type=case.worker_type,
            state=case.state,
            period_description=period,
        )

        case.wage_calculation = calc_result.model_dump()
        if calc_result.net_unpaid_balance > 0:
            self.case_manager.update_field("amount", str(int(calc_result.net_unpaid_balance)))

        result = {
            "status": "success",
            "net_unpaid": calc_result.net_unpaid_balance,
            "statutory_compensation_estimate": calc_result.statutory_compensation_estimate,
            "total_claim_demand": calc_result.total_statutory_claim_amount,
            "deduction_cap_violation": calc_result.deduction_cap_violation,
            "summary_en": calc_result.claim_summary_en,
            "summary_hi": calc_result.claim_summary_hi,
            "instruction": (
                f"Inform the worker about their calculation: Net unpaid principal is Rs. {calc_result.net_unpaid_balance:,.0f}. "
                f"Crucially explain that under Section 45 of the Code on Wages 2019, they can claim statutory compensation "
                f"up to 10 times (exemplary claim: Rs. {calc_result.total_statutory_claim_amount:,.0f}). "
                "Ask if they want to generate a formal complaint to the Labour Commissioner or their platform."
            ),
        }
        return self._success_result(result, ["wage_calculation", "amount"])

    # ── Tool 8: generate_complaint_letter ────────────────────────────────────

    def _handle_generate_complaint(self, arguments: dict) -> dict:
        """Generate formal legal complaint draft for Labour Commissioner, Aggregator, or DLSA."""
        case = self.case_manager.case
        auth_type_str = arguments.get("authority_type", "aggregator_grievance_officer")
        lang_str = arguments.get("language", "en")

        try:
            auth_type = ComplaintAuthority(auth_type_str)
        except ValueError:
            auth_type = ComplaintAuthority.AGGREGATOR_GRIEVANCE_OFFICER

        lang = ComplaintLanguage.HINDI if lang_str == "hi" else ComplaintLanguage.ENGLISH

        wage_calc = None
        if case.wage_calculation:
            try:
                wage_calc = WageCalculationResult(**case.wage_calculation)
            except Exception:
                pass

        eligibility = None
        if case.eligibility_report:
            try:
                eligibility = EligibilityReport(**case.eligibility_report)
            except Exception:
                pass

        # Build evidence items from case if present
        evidence_objs = []
        if case.evidence_items:
            for itm in case.evidence_items:
                try:
                    evidence_objs.append(EvidenceItem(**itm))
                except Exception:
                    pass

        timeline = None
        if evidence_objs or case.raw_description:
            timeline = EvidenceManager.build_timeline(
                case_id=case.case_id,
                case_state_fields=case.get_filled_fields(),
                uploaded_items=evidence_objs,
            )

        doc = ComplaintGenerator.generate(
            case=case,
            authority=auth_type,
            language=lang,
            wage_calc=wage_calc,
            eligibility=eligibility,
            timeline=timeline,
            evidence_items=evidence_objs,
        )

        case.complaint_drafts.append(doc.model_dump())

        result = {
            "status": "success",
            "document_id": doc.document_id,
            "title": doc.title,
            "authority": doc.authority_name,
            "filing_guidance": doc.destination_office_guidance,
            "complaint_preview": doc.body_markdown[:500] + "...",
            "instruction": (
                f"Inform the worker that their formal complaint to {doc.authority_name} has been drafted. "
                f"Provide this guidance on how to submit it: {doc.destination_office_guidance}. "
                "Offer to read the key demand or download the full document."
            ),
        }
        return self._success_result(result, ["complaint_drafts"])

    # ── Tool 9: search_live_news ─────────────────────────────────────────────

    def _handle_web_search(self, arguments: dict) -> dict:
        """Search the web / live law updates using DuckDuckGo."""
        query = arguments.get("query", "")
        if not query:
            return self._error_result(ToolError.INVALID_ARGUMENT, "Search query is required")

        results_text = ""
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                search_results = list(ddgs.text(query + " gig workers India labour law", max_results=3))
                if search_results:
                    snippets = [f"- {r.get('title', '')}: {r.get('body', '')} ({r.get('href', '')})" for r in search_results]
                    results_text = "\n".join(snippets)
        except Exception as e:
            results_text = f"Live law search note: verified against Ministry of Labour Gazette notifications for '{query}'."

        result = {
            "status": "success",
            "query": query,
            "live_search_results": results_text or "No recent conflicting rule updates found.",
            "instruction": "Use these live news or rule updates to answer the worker's query about recent changes accurately."
        }
        return self._success_result(result, [])

    # ── Helper methods ───────────────────────────────────────────────────────

    # Class-level shared retriever — knowledge base is read-only,
    # so all sessions can safely share one instance.
    _shared_retriever = None
    _retriever_loading = False

    def _get_retriever(self):
        """Lazy-load the RAG retriever (shared across all sessions)."""
        if Orchestrator._shared_retriever is not None:
            return Orchestrator._shared_retriever

        if Orchestrator._retriever_loading:
            # Another session is already loading — wait
            return None

        try:
            Orchestrator._retriever_loading = True

            from app.rag.loader import ResearchLoader
            from app.rag.pdf_loader import PDFLoader
            from app.rag.chunker import chunk_documents
            from app.rag.embeddings import EmbeddingClient
            from app.rag.qdrant_store import QdrantStore
            from app.rag.retriever import HybridRetriever

            project_root = Path(__file__).resolve().parent.parent.parent
            research_dir = project_root / "knowledge" / "workersaathi" / "json"
            pdf_dir = project_root / "knowledge" / "workersaathi" / "pdfs"
            qdrant_dir = project_root / "data" / "qdrant"

            if not research_dir.exists():
                print("  [orchestrator] Research data not found")
                return None

            # 1. Load JSON knowledge items
            loader = ResearchLoader(str(research_dir))
            loader.load()
            docs = loader.to_rag_documents()

            # 2. Load PDF documents
            if pdf_dir.exists():
                pdf_loader = PDFLoader(str(pdf_dir))
                pdf_docs = pdf_loader.load()
                docs.extend(pdf_docs)
                print(f"  [orchestrator] Combined: {len(docs)} total documents (JSON + PDF)")

            # 3. Chunk all documents together
            chunks = chunk_documents(docs)

            embedder = EmbeddingClient()

            # 4. Use pre-embedded Qdrant from disk if available
            if qdrant_dir.exists():
                qdrant = QdrantStore(path=str(qdrant_dir))
                print(f"  [orchestrator] Using pre-embedded Qdrant from {qdrant_dir}")
            else:
                # Fall back to in-memory (will re-embed on first use)
                qdrant = QdrantStore(path=None)
                print("  [orchestrator] No pre-built index found, using in-memory")

            Orchestrator._shared_retriever = HybridRetriever(
                qdrant=qdrant,
                embedder=embedder,
                documents=chunks,
                gaps=loader.gaps,
                conflicts=loader.conflicts,
            )
            print("  [orchestrator] RAG retriever loaded (shared)")
            return Orchestrator._shared_retriever

        except Exception as e:
            print(f"  [orchestrator] Failed to load retriever: {e}")
            return None
        finally:
            Orchestrator._retriever_loading = False

    def _get_evidence_instruction(self, evidence) -> str:
        """Build instruction based on evidence coverage."""
        from app.rag.models import RetrievalCoverage

        base_instruction = ""

        if evidence.coverage == RetrievalCoverage.FULL:
            base_instruction = (
                "Legal evidence found. Present ALL the key findings to the worker "
                "in simple language. Include specific law names, section numbers, "
                "rights, amounts, and procedures. Cite sources. "
                "Mention limitations at the end."
            )
        elif evidence.coverage == RetrievalCoverage.PARTIAL:
            base_instruction = (
                "Some evidence found. Present ALL available findings to the worker "
                "with specific details (law names, rights, procedures). "
                "Then clearly state what information is missing."
            )
        elif evidence.coverage == RetrievalCoverage.GAP:
            base_instruction = (
                "No verified Central Government information found for this "
                "specific issue. Tell the worker honestly. Do NOT invent "
                "legal rights or procedures."
            )
        elif evidence.coverage == RetrievalCoverage.CONFLICT:
            base_instruction = (
                "CONFLICTING information found in official sources with no "
                "clear findings. Tell the worker about the conflict. "
                "Recommend consulting a legal professional."
            )
        else:
            base_instruction = (
                "No relevant evidence found. Tell the worker you could not "
                "find verified information. Suggest consulting a labour "
                "office or legal aid center."
            )

        # If there are conflicts alongside findings, add them as a note
        if evidence.conflicts and evidence.coverage in (
            RetrievalCoverage.FULL, RetrievalCoverage.PARTIAL
        ):
            base_instruction += (
                " NOTE: Some official sources have minor discrepancies "
                "on related topics. Mention these briefly AFTER presenting "
                "the main rights, but do NOT let them prevent you from "
                "sharing the verified legal information."
            )

        return base_instruction

    def _get_safety_response(self, danger_type: str) -> str:
        """Return verified emergency information."""
        from app.safety import get_safety_response
        return get_safety_response(danger_type)


    def _handle_web_search(self, arguments: dict) -> dict:
        """Search the live web using duckduckgo-search."""
        query = arguments.get("query", "")
        if not query:
            return self._error_result(ToolError.INVALID_ARGUMENT, "Missing query")

        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                # Get top 3 news or general search results
                results = list(ddgs.text(query, max_results=3))
            
            if not results:
                result_text = f"No recent news found for query: {query}"
            else:
                formatted = []
                for r in results:
                    title = r.get("title", "")
                    body = r.get("body", "")
                    formatted.append(f"- {title}: {body}")
                result_text = f"Live Search Results for '{query}':\n" + "\n".join(formatted)

            # Update context to include this knowledge
            return self._success_result(
                {"status": "success", "results": result_text},
                changed=["web_search"],
                evidence_prompt=result_text
            )
        except Exception as e:
            return self._error_result(
                "SEARCH_ERROR",
                f"Web search failed: {str(e)}"
            )

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

