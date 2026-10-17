"""
eligibility.py -- Deterministic Eligibility Checker for Indian Gig & Informal Workers.

Implements verified legal rules under:
1. Code on Social Security, 2020 (Sections 112, 113, 114) & May 2026 Central Rules
   - The 90/120-Day Rule for Aggregator Registration.
2. State-specific Gig Worker Acts & Boards:
   - Rajasthan Platform Based Gig Workers (Registration and Welfare) Act, 2023
   - Karnataka Platform-Based Gig Workers Bill/Act, 2024
   - Tamil Nadu Gig Workers Welfare Board
   - Telangana Gig Workers Welfare Board
3. e-Shram Registration & Social Security Portals (Do NOT collect Aadhaar numbers).
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.case.models import WorkerType, IndianState


class EligibilityStatus(str, Enum):
    ELIGIBLE = "eligible"
    CONDITIONALLY_ELIGIBLE = "conditionally_eligible"
    INELIGIBLE = "ineligible"
    SCHEME_PENDING = "scheme_pending"


class CriteriaCheck(BaseModel):
    name: str
    passed: bool
    target: str
    actual: str
    detail: str
    legal_basis: str


class EligibilityReport(BaseModel):
    verdict: EligibilityStatus
    verdict_badge: str
    headline: str
    summary: str
    rule_90_120_status: Dict[str, Any]
    criteria_checks: List[CriteriaCheck]
    state_specific_rights: Optional[Dict[str, Any]] = None
    section_114_advisory: str
    eshram_advisory: Dict[str, Any]
    immediate_steps: List[str]
    legal_citations: List[str]

    def to_summary_text(self) -> str:
        """Generate human-readable summary for agent speech or markdown."""
        lines = [
            f"**Eligibility Verdict:** {self.verdict_badge}",
            f"{self.headline}\n",
            f"**90/120-Day Rule Status:** {self.rule_90_120_status.get('explanation', '')}",
        ]
        if self.state_specific_rights:
            lines.append(f"**State Benefits ({self.state_specific_rights.get('state', '')}):** {self.state_specific_rights.get('key_benefit', '')}")
        lines.append(f"\n**Next Steps:**")
        for i, step in enumerate(self.immediate_steps, 1):
            lines.append(f"{i}. {step}")
        return "\n".join(lines)


class EligibilityChecker:
    """
    Evaluates worker eligibility against verified legal standards in India.
    """

    @classmethod
    def evaluate(
        cls,
        worker_type: WorkerType | str = WorkerType.GIG_WORKER,
        state: IndianState | str = IndianState.UNKNOWN,
        days_with_primary_aggregator: Optional[int] = None,
        total_days_across_aggregators: Optional[int] = None,
        number_of_aggregators: int = 1,
        has_eshram: Optional[bool] = None,
        age: Optional[int] = None,
        platform_name: Optional[str] = None,
    ) -> EligibilityReport:
        """
        Runs deterministic legal eligibility assessment.
        """
        wt_str = worker_type.value if hasattr(worker_type, "value") else str(worker_type).lower()
        state_str = state.value if hasattr(state, "value") else str(state)

        criteria_checks: List[CriteriaCheck] = []
        citations: List[str] = []
        immediate_steps: List[str] = []

        # ── 1. Age Verification Check ─────────────────────────────────
        if age is not None:
            age_valid = 16 <= age <= 60
            criteria_checks.append(CriteriaCheck(
                name="Age Criterion (16-60 Years)",
                passed=age_valid,
                target="16 to 60 years",
                actual=f"{age} years",
                detail="Worker falls within the statutory eligibility age bracket." if age_valid else "Outside the eligible age bracket (16-60).",
                legal_basis="Section 2(82) and Section 113, Code on Social Security, 2020",
            ))
            citations.append("Code on Social Security, 2020 — Section 2(82) & Section 113")
        else:
            # Assumed met unless stated otherwise
            criteria_checks.append(CriteriaCheck(
                name="Age Criterion (16-60 Years)",
                passed=True,
                target="16 to 60 years",
                actual="Presumed valid",
                detail="Worker must be at least 16 and under 60 years of age.",
                legal_basis="Code on Social Security, 2020 — Section 113",
            ))

        # ── 2. The 90 / 120-Day Rule Assessment ───────────────────────
        rule_satisfied = False
        rule_explanation = ""
        days_primary = days_with_primary_aggregator or 0
        days_total = total_days_across_aggregators or days_primary
        num_apps = max(number_of_aggregators, 1)

        if days_primary >= 90:
            rule_satisfied = True
            rule_explanation = f"Met: You have logged {days_primary} days with a single platform (threshold: 90 days in 12 months)."
        elif num_apps > 1 and days_total >= 120:
            rule_satisfied = True
            rule_explanation = f"Met: You have logged {days_total} days across {num_apps} platforms (threshold: 120 days across multiple aggregators in 12 months)."
        elif days_primary > 0 or days_total > 0:
            needed_single = max(0, 90 - days_primary)
            needed_multi = max(0, 120 - days_total)
            rule_satisfied = False
            rule_explanation = (
                f"Pending: You have completed {days_primary} days with your primary app (need {needed_single} more days) "
                f"or {days_total} days total across apps (need {needed_multi} more days for multi-app threshold)."
            )
        else:
            rule_satisfied = False
            rule_explanation = "Information needed: Please provide how many days or months you have worked on the platform(s)."

        criteria_checks.append(CriteriaCheck(
            name="90/120-Day Work Tenure Rule",
            passed=rule_satisfied,
            target="90 days with 1 aggregator OR 120 days across aggregators in last 12 months",
            actual=f"{days_primary} days (single app) / {days_total} days (total)",
            detail=rule_explanation,
            legal_basis="Rules under Section 113, Code on Social Security, 2020 (Notified May 2026)",
        ))
        citations.append("Central Rules under Section 113, Code on Social Security, 2020 (May 2026)")

        # ── 3. e-Shram Registration Check ─────────────────────────────
        eshram_info = {
            "is_registered": bool(has_eshram),
            "uan_card_available": bool(has_eshram),
            "registration_portal": "https://eshram.gov.in",
            "prerequisites": [
                "Mobile number linked to Aadhaar for OTP verification",
                "Savings Bank Account with IFSC code",
                "Age between 16 and 59 years",
            ],
            "safeguard_note": "WorkerSaathi NEVER asks for or stores your 12-digit Aadhaar number or OTP.",
        }

        if has_eshram is True:
            criteria_checks.append(CriteriaCheck(
                name="e-Shram National Database Registration",
                passed=True,
                target="Registered on e-Shram with 12-digit UAN",
                actual="Registered (UAN Card holder)",
                detail="Worker is officially recorded on the Ministry of Labour unorganised worker portal.",
                legal_basis="Ministry of Labour & Employment e-Shram Framework",
            ))
        elif has_eshram is False:
            criteria_checks.append(CriteriaCheck(
                name="e-Shram National Database Registration",
                passed=False,
                target="Registered on e-Shram with 12-digit UAN",
                actual="Not Registered",
                detail="Registration is free and grants access to national welfare benefits & accident cover.",
                legal_basis="Ministry of Labour & Employment e-Shram Framework",
            ))
            immediate_steps.append("Register on e-Shram portal (eshram.gov.in) using your mobile number to get your 12-digit UAN card.")
        else:
            criteria_checks.append(CriteriaCheck(
                name="e-Shram National Database Registration",
                passed=False,
                target="Registered on e-Shram with 12-digit UAN",
                actual="Status unconfirmed",
                detail="e-Shram card gives national recognition and accident insurance benefits.",
                legal_basis="Ministry of Labour & Employment e-Shram Framework",
            ))

        # ── 4. State-Specific Protections Check ───────────────────────
        state_rights = cls._get_state_rights(state_str)
        if state_rights:
            citations.append(state_rights["statute"])
            if state_rights.get("action_step"):
                immediate_steps.append(state_rights["action_step"])

        # ── 5. Section 114 Advisory ───────────────────────────────────
        section_114_text = (
            "IMPORTANT STATUTORY NOTE (Section 114, Code on Social Security 2020): "
            "Aggregators are mandated to register gig workers, but specific central payout schemes "
            "(life, disability, maternity, and old age) are currently being formulated by the National Social Security Board. "
            "However, your right against unlawful deactivation and wage withholding remains actionable immediately."
        )

        # ── 6. Formulate Overall Verdict ──────────────────────────────
        if "gig" not in wt_str and wt_str != "unknown":
            # Construction / domestic / unorganised worker
            verdict = EligibilityStatus.ELIGIBLE
            verdict_badge = "✅ Eligible (Unorganised Worker / State Board)"
            headline = f"Eligible for statutory protections under {state_str if state_str != 'Unknown' else 'Central'} Labour Laws."
            summary = (
                f"As a {wt_str.replace('_', ' ')}, your rights are protected under the Code on Wages, 2019 "
                "and state welfare boards (e.g. BOCW for construction, Unorganised Workers Board)."
            )
            immediate_steps.append("Demand itemized wage slip and preserve all written/WhatsApp attendance and payment records.")
        elif rule_satisfied:
            verdict = EligibilityStatus.ELIGIBLE
            verdict_badge = "✅ Eligible for Aggregator Registration & Protections"
            headline = "You satisfy the 90/120-Day Rule under the Code on Social Security, 2020!"
            summary = (
                f"You have completed sufficient work days to require {platform_name or 'the aggregator'} "
                "to register you on the government portal. You are entitled to fair notice, grievance redressal, "
                "and welfare board protections."
            )
            immediate_steps.append(f"Request {platform_name or 'the platform'} for your official aggregator registration acknowledgement number.")
            immediate_steps.append("Preserve trip receipts, weekly payouts, and log sheets as evidence of your active tenure.")
        elif days_primary > 0 or days_total > 0:
            verdict = EligibilityStatus.CONDITIONALLY_ELIGIBLE
            verdict_badge = "⏳ Conditionally Eligible (Tenure Pending)"
            headline = "You are on track toward statutory aggregator registration."
            summary = (
                f"You currently have {days_primary} days logged with your platform. "
                "While full registration requires 90 days with one platform or 120 days across platforms, "
                "your earned wages and protection against wrongful deductions are protected by law right now."
            )
            immediate_steps.append("Keep logging your shifts and preserve screenshots of daily active hours.")
        else:
            verdict = EligibilityStatus.CONDITIONALLY_ELIGIBLE
            verdict_badge = "🔍 Information Needed to Complete Eligibility Check"
            headline = "We need your work duration to confirm full statutory benefits."
            summary = (
                "Tell WorkerSaathi roughly how many days or months you have worked on the platform. "
                "If you have worked at least 90 days with one app or 120 days across apps, you meet the legal registration criteria."
            )
            immediate_steps.append("Check your app profile or bank statements to see when your first trip was completed.")

        # Default action steps if none yet
        if not immediate_steps:
            immediate_steps.append("Preserve all screenshots of your earnings tab, ratings, and deactivation notices.")

        rule_90_120_data = {
            "satisfied": rule_satisfied,
            "days_primary": days_primary,
            "days_total": days_total,
            "target_single": 90,
            "target_multi": 120,
            "explanation": rule_explanation,
        }

        return EligibilityReport(
            verdict=verdict,
            verdict_badge=verdict_badge,
            headline=headline,
            summary=summary,
            rule_90_120_status=rule_90_120_data,
            criteria_checks=criteria_checks,
            state_specific_rights=state_rights,
            section_114_advisory=section_114_text,
            eshram_advisory=eshram_info,
            immediate_steps=immediate_steps,
            legal_citations=list(dict.fromkeys(citations)),
        )

    @classmethod
    def _get_state_rights(cls, state_name: str) -> Optional[Dict[str, Any]]:
        """Returns verified state-specific gig worker legislation details."""
        sn = state_name.lower().strip()

        if "rajasthan" in sn:
            return {
                "state": "Rajasthan",
                "statute": "Rajasthan Platform Based Gig Workers (Registration and Welfare) Act, 2023",
                "key_benefit": "Mandatory unique Social Security ID, automated welfare cess (1-2% on transaction), and 21-day statutory grievance redressal.",
                "grievance_timeline_days": 21,
                "penal_provision": "Aggregators failing to register workers or comply with welfare orders face penalties up to ₹5,00,000.",
                "action_step": "File a formal complaint before the Rajasthan Gig Workers Welfare Board or State Appellate Authority if platform fails to resolve dispute in 21 days.",
            }
        elif "karnataka" in sn:
            return {
                "state": "Karnataka",
                "statute": "Karnataka Platform-based GIG Workers (Social Security and Welfare) Bill, 2024",
                "key_benefit": "Mandatory 14-day prior written notice before deactivation of ID, welfare fee tracking, and Internal Dispute Redressal Officer.",
                "grievance_timeline_days": 14,
                "penal_provision": "Arbitrary account deactivation without 14 days' notice and written grounds is a direct statutory breach.",
                "action_step": "Demand a formal written explanation from the aggregator's Grievance Redressal Officer citing the 14-day notice requirement.",
            }
        elif "tamil nadu" in sn or "tamilnadu" in sn:
            return {
                "state": "Tamil Nadu",
                "statute": "Tamil Nadu Platform Based Gig Workers Welfare Board (Manual Workers Act)",
                "key_benefit": "Special Gig Workers Welfare Board providing accidental death compensation (up to ₹5,00,000), medical and educational assistance.",
                "grievance_timeline_days": 30,
                "penal_provision": "Platform aggregators must contribute to the State Gig Workers Welfare Fund.",
                "action_step": "Register with the Tamil Nadu Gig Workers Welfare Board at your nearest District Labour Office to claim social security cards.",
            }
        elif "telangana" in sn:
            return {
                "state": "Telangana",
                "statute": "Telangana Gig and Platform Workers Welfare Board Policy (2024-2025)",
                "key_benefit": "₹5 Lakh Accidental Insurance and ₹10 Lakh Health Cover for active delivery and transport gig workers.",
                "grievance_timeline_days": 30,
                "penal_provision": "Aggregators required to enroll all active partners into the State Welfare Directory.",
                "action_step": "Verify that your platform partner ID is linked to the Telangana Gig Worker Welfare insurance enrollment list.",
            }
        elif "delhi" in sn:
            return {
                "state": "Delhi",
                "statute": "Delhi Motor Vehicles Aggregator and Delivery Service Provider Scheme & Code on Wages Minimum Wage Standards",
                "key_benefit": "Strict aggregator grievance redressal mechanism and nation-leading minimum wage benchmarks (~₹18,000 - ₹21,000/month).",
                "grievance_timeline_days": 30,
                "penal_provision": "Non-compliant aggregators risk vehicle operating licence suspension.",
                "action_step": "Approach the Office of the Joint Labour Commissioner (Pusa Road / District Office) or Samadhan portal for wage recovery.",
            }
        return None
