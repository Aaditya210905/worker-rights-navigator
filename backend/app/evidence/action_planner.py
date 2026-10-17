"""
action_planner.py -- Action Planner Layer

Takes CaseState and LegalEvidence and generates a source-backed action plan.
Separates worker claims from legal facts.
"""

from typing import Optional
from app.case.models import CaseState, IssueCategory, WorkerType
from app.rag.models import LegalEvidence, RetrievalCoverage

class ActionPlanner:
    """
    Generates actionable next steps based on verified evidence.
    """

    @classmethod
    def generate_plan(cls, case: CaseState, evidence: Optional[LegalEvidence]) -> list[dict]:
        """Generate a list of action steps."""
        actions = []

        # 1. Immediate Safety Check (if applicable)
        if case.injury_details or case.issue_category == IssueCategory.WORKPLACE_INJURY:
            actions.append({
                "step": len(actions) + 1,
                "action": "Ensure immediate physical safety and seek necessary medical attention.",
                "reason": "Safety is the highest priority before addressing legal rights.",
                "source": "WorkerSaathi Safety Guidelines"
            })

        # 2. Preserve Evidence (always applicable)
        actions.append({
            "step": len(actions) + 1,
            "action": "Preserve all relevant records (screenshots, messages, work logs, payment receipts).",
            "reason": "Documentary evidence is required for any formal complaint or follow-up.",
            "source": "General Legal Best Practice"
        })

        # 3. Handle specific issues based on evidence
        if case.issue_category == IssueCategory.UNPAID_WAGES:
            cls._plan_unpaid_wages(case, evidence, actions)
        elif case.issue_category == IssueCategory.WORKPLACE_INJURY:
            cls._plan_workplace_injury(case, evidence, actions)
        elif case.issue_category == IssueCategory.PLATFORM_DEACTIVATION:
            cls._plan_deactivation(case, evidence, actions)

        # 4. Handle Gaps or Conflicts
        if evidence:
            if evidence.coverage == RetrievalCoverage.GAP:
                actions.append({
                    "step": len(actions) + 1,
                    "action": "Consult a legal professional or legal aid center.",
                    "reason": "Verified Central Government information is currently missing for your specific situation.",
                    "source": "WorkerSaathi Knowledge Gap"
                })
            elif evidence.coverage == RetrievalCoverage.CONFLICT:
                actions.append({
                    "step": len(actions) + 1,
                    "action": "Be aware that official sources provide conflicting information on this topic.",
                    "reason": "Do not rely on a single source. A legal professional can help interpret the current application of the law.",
                    "source": "WorkerSaathi Conflict Detection"
                })

        return actions

    @classmethod
    def _plan_unpaid_wages(cls, case: CaseState, evidence: Optional[LegalEvidence], actions: list):
        # Recommend drafting a message
        actions.append({
            "step": len(actions) + 1,
            "action": f"Send a formal written request for pending payment to {case.platform_or_employer or 'the employer/platform'}.",
            "reason": "A written record of demanding payment is the first step in dispute resolution.",
            "source": "General Practice"
        })

        # Look for verified complaint mechanisms in evidence
        complaint_sources = cls._find_evidence_keywords(evidence, ["samadhan", "labour commissioner", "inspector", "complaint"])
        if complaint_sources:
            for src in complaint_sources:
                actions.append({
                    "step": len(actions) + 1,
                    "action": "Review the applicable official complaint mechanism.",
                    "reason": "Verified official procedure found.",
                    "source": src
                })

    @classmethod
    def _plan_workplace_injury(cls, case: CaseState, evidence: Optional[LegalEvidence], actions: list):
        actions.append({
            "step": len(actions) + 1,
            "action": "Document the incident location, date, time, and any witnesses.",
            "reason": "Crucial for establishing that the injury occurred during work.",
            "source": "General Practice"
        })
        
        notify_sources = cls._find_evidence_keywords(evidence, ["notify", "notice", "report", "accident"])
        if notify_sources:
            for src in notify_sources:
                actions.append({
                    "step": len(actions) + 1,
                    "action": "Ensure the employer notifies the appropriate authorities about the accident.",
                    "reason": "Statutory requirement found.",
                    "source": src
                })

    @classmethod
    def _plan_deactivation(cls, case: CaseState, evidence: Optional[LegalEvidence], actions: list):
        if evidence and evidence.coverage in (RetrievalCoverage.GAP, RetrievalCoverage.CONFLICT):
             actions.append({
                "step": len(actions) + 1,
                "action": "Preserve the deactivation notice and all platform communications.",
                "reason": "Central reinstatement procedures are currently unverified for gig workers.",
                "source": "WorkerSaathi Knowledge Base"
            })
        else:
             actions.append({
                "step": len(actions) + 1,
                "action": "Request a formal reason for deactivation from the platform support.",
                "reason": "Establishing the reason is necessary for any appeal.",
                "source": "General Practice"
            })

    @classmethod
    def _find_evidence_keywords(cls, evidence: Optional[LegalEvidence], keywords: list[str]) -> list[str]:
        """Helper to find specific actions in the retrieved legal evidence."""
        if not evidence or not evidence.evidence:
            return []
        
        sources = set()
        for f in evidence.evidence:
            text = f.evidence_text.lower()
            if any(k in text for k in keywords):
                sources.add(f.official_url or "Verified Legal Document")
                
        return list(sources)
