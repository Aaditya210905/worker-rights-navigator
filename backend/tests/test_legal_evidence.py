"""
test_legal_evidence.py -- Test suite for Gireesh's Legal Help & Evidence Modules.

Tests:
1. 90/120-Day Rule and Statutory Eligibility Checker (Code on Social Security 2020)
2. State-Specific Gig Legislation (Rajasthan 21-day timeline, Karnataka 14-day notice)
3. Salary & Unpaid-Wage Calculator (Section 18 deduction cap & Section 45 10x compensation)
4. Payment Screenshot Ingestion, PII Redaction & Timeline Generation
5. Formal Legal Complaint Petition Drafting (Labour Commissioner, Aggregator, DLSA)
6. Orchestrator Tool Integration for the new legal tools

Usage:
    python -m tests.test_legal_evidence
"""

import os
import sys
from pathlib import Path

# Ensure backend root is on sys.path
_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.case.models import CaseState, WorkerType, IndianState, IssueCategory
from app.evidence.eligibility import EligibilityChecker, EligibilityStatus
from app.evidence.wage_calculator import WageCalculator
from app.evidence.screenshot_parser import EvidenceManager, EvidenceType, redact_sensitive_pii
from app.evidence.complaint_generator import ComplaintGenerator, ComplaintAuthority, ComplaintLanguage
from app.agent.orchestrator import Orchestrator


def test_eligibility_90_120_rule():
    """Test 1: 90/120-Day rule under Code on Social Security 2020."""
    print("\n--- Test 1: 90/120-Day Rule Eligibility ---")

    # Scenario A: Single aggregator with 95 days worked -> ELIGIBLE
    rep1 = EligibilityChecker.evaluate(
        worker_type=WorkerType.GIG_WORKER,
        state=IndianState.DELHI,
        days_with_primary_aggregator=95,
        number_of_aggregators=1,
        platform_name="Zomato",
    )
    assert rep1.verdict == EligibilityStatus.ELIGIBLE
    assert rep1.rule_90_120_status["satisfied"] is True
    assert "Section 113" in rep1.criteria_checks[1].legal_basis
    assert "Section 114" in rep1.section_114_advisory
    print("  [ok] Single aggregator (95 days >= 90): ELIGIBLE")

    # Scenario B: Multiple aggregators (50 + 75 = 125 days across 2 apps) -> ELIGIBLE
    rep2 = EligibilityChecker.evaluate(
        worker_type=WorkerType.GIG_WORKER,
        state=IndianState.KARNATAKA,
        days_with_primary_aggregator=50,
        total_days_across_aggregators=125,
        number_of_aggregators=2,
        platform_name="Swiggy",
    )
    assert rep2.verdict == EligibilityStatus.ELIGIBLE
    assert rep2.rule_90_120_status["satisfied"] is True
    print("  [ok] Multi-aggregator (125 days >= 120 across 2 apps): ELIGIBLE")

    # Scenario C: Only 45 days worked -> CONDITIONALLY_ELIGIBLE (tenure pending)
    rep3 = EligibilityChecker.evaluate(
        worker_type=WorkerType.GIG_WORKER,
        state=IndianState.MAHARASHTRA,
        days_with_primary_aggregator=45,
        number_of_aggregators=1,
    )
    assert rep3.verdict == EligibilityStatus.CONDITIONALLY_ELIGIBLE
    assert rep3.rule_90_120_status["satisfied"] is False
    assert "need 45 more days" in rep3.rule_90_120_status["explanation"]
    print("  [ok] Under-tenure (45 days < 90): CONDITIONALLY_ELIGIBLE with days countdown")


def test_state_specific_protections():
    """Test 2: State-specific gig worker legislation (Rajasthan, Karnataka)."""
    print("\n--- Test 2: State Gig Worker Legislation ---")

    # Rajasthan Act 2023: 21-day dispute resolution & ₹5 lakh penalty
    rep_raj = EligibilityChecker.evaluate(
        worker_type=WorkerType.GIG_WORKER,
        state=IndianState.RAJASTHAN,
        days_with_primary_aggregator=100,
    )
    assert rep_raj.state_specific_rights is not None
    assert rep_raj.state_specific_rights["state"] == "Rajasthan"
    assert rep_raj.state_specific_rights["grievance_timeline_days"] == 21
    assert "₹5,00,000" in rep_raj.state_specific_rights["penal_provision"]
    print("  [ok] Rajasthan Act 2023: 21-day grievance & ₹5 Lakh penalty verified")

    # Karnataka Bill 2024: 14-day prior notice before deactivation
    rep_kar = EligibilityChecker.evaluate(
        worker_type=WorkerType.GIG_WORKER,
        state=IndianState.KARNATAKA,
        days_with_primary_aggregator=100,
    )
    assert rep_kar.state_specific_rights is not None
    assert rep_kar.state_specific_rights["state"] == "Karnataka"
    assert rep_kar.state_specific_rights["grievance_timeline_days"] == 14
    assert "14-day prior written notice" in rep_kar.state_specific_rights["key_benefit"]
    print("  [ok] Karnataka Legislation: 14-day notice protection verified")


def test_wage_calculator_and_statutory_claims():
    """Test 3: Unpaid wages, Section 18 cap violation, and Section 45 10x compensation."""
    print("\n--- Test 3: Wage Calculator & Statutory Damages ---")

    # Worker earned ₹12,000 base, ₹3,000 incentives withheld, ₹4,500 arbitrary deductions
    res = WageCalculator.calculate(
        base_unpaid=12000.0,
        withheld_incentives=3000.0,
        unauthorized_deductions=4500.0,
        worker_type=WorkerType.GIG_WORKER,
        state=IndianState.DELHI,
        period_description="August 2026",
    )

    assert res.net_unpaid_balance == 19500.0
    assert res.statutory_compensation_estimate > 0.0
    assert res.total_statutory_claim_amount == res.net_unpaid_balance + res.statutory_compensation_estimate
    assert len(res.itemized_breakdown) == 3
    assert "Section 45" in res.legal_citations[2]
    assert "वेतन संहिता" in res.claim_summary_hi

    # Test Section 18 50% cap detection (e.g. deductions = ₹8,000 on base = ₹4,000 -> 66% deduction)
    res_cap = WageCalculator.calculate(
        base_unpaid=4000.0,
        unauthorized_deductions=8000.0,
    )
    assert res_cap.deduction_cap_violation is True
    print(f"  [ok] Principal due: ₹{res.net_unpaid_balance:,.0f} | Claim with Section 45 damages: ₹{res.total_statutory_claim_amount:,.0f}")
    print("  [ok] Section 18(3) 50% deduction cap breach correctly flagged")


def test_privacy_redaction_and_evidence():
    """Test 4: Privacy redaction of Aadhaar/Bank/OTP and screenshot parsing."""
    print("\n--- Test 4: Privacy Redaction & Screenshot Ingestion ---")

    sample_ocr = (
        "Zomato Payout Statement. Partner ID: ZOM-84920. Amount: ₹4,250.00. "
        "Aadhaar Number: 5491 8294 1029. Bank Account No: 9182748192019. "
        "Your login OTP is 4821. Account suspended low rating."
    )

    clean_text, was_redacted, notes = redact_sensitive_pii(sample_ocr)
    assert was_redacted is True
    assert "5491 8294 1029" not in clean_text
    assert "[REDACTED_AADHAAR_NUMBER]" in clean_text
    assert "9182748192019" not in clean_text
    assert "[REDACTED_BANK_ACCOUNT]" in clean_text
    assert "4821" not in clean_text
    assert "[REDACTED_OTP]" in clean_text
    print("  [ok] Sensitive PII (Aadhaar, Bank Account, OTP) successfully redacted")

    # Ingest mock file
    item = EvidenceManager.save_and_parse_upload(
        file_bytes=b"Swiggy Delivery Partner Weekly Earnings Statement: Rs. 6500 earned, Order #SW-83912",
        filename="swiggy_earnings_aug.txt",
        case_id="WS-TEST-001",
        user_caption="Weekly earnings screenshot",
    )
    assert item.parsed_data.detected_platform == "Swiggy"
    assert 6500.0 in item.parsed_data.detected_amounts
    assert item.evidence_type == EvidenceType.EARNINGS_STATEMENT
    print("  [ok] Screenshot parsing extracted: Platform=Swiggy, Amount=₹6,500")

    # Timeline generation
    timeline = EvidenceManager.build_timeline(
        case_id="WS-TEST-001",
        case_state_fields={"platform_or_employer": "Swiggy", "incident_date": "10 Aug 2026", "issue_category": "unpaid_wages"},
        uploaded_items=[item],
    )
    assert timeline.total_events >= 2
    assert "Annexure A-1" in timeline.events[1].annexure_ref
    print(f"  [ok] Evidence Timeline generated with {timeline.total_events} chronological milestones")


def test_complaint_generator():
    """Test 5: Formal legal complaint generation in English and Hindi."""
    print("\n--- Test 5: Legal Complaint Generator ---")

    case = CaseState(
        platform_or_employer="Swiggy",
        state=IndianState.KARNATAKA,
        worker_type=WorkerType.GIG_WORKER,
        issue_category=IssueCategory.PLATFORM_DEACTIVATION,
        amount="18500",
        deactivation_reason="Sudden account suspension without notice",
    )

    # Generate sample wage calculation
    wcalc = WageCalculator.calculate(base_unpaid=18500, state=IndianState.KARNATAKA)

    # English complaint to Labour Commissioner
    doc_en = ComplaintGenerator.generate(
        case=case,
        authority=ComplaintAuthority.LABOUR_COMMISSIONER,
        language=ComplaintLanguage.ENGLISH,
        wage_calc=wcalc,
    )
    assert "Formal Legal Complaint" in doc_en.title
    assert "Code on Wages, 2019" in doc_en.body_markdown
    assert "Karnataka" in doc_en.body_markdown
    assert "Samadhan Portal" in doc_en.destination_office_guidance
    assert "<table" in doc_en.body_html
    print("  [ok] English Labour Commissioner complaint drafted with full statutory citations and calculation table")

    # Hindi complaint to Aggregator Grievance Officer
    doc_hi = ComplaintGenerator.generate(
        case=case,
        authority=ComplaintAuthority.AGGREGATOR_GRIEVANCE_OFFICER,
        language=ComplaintLanguage.HINDI,
    )
    assert "शिकायत" in doc_hi.title
    assert "अनावेदक" in doc_hi.body_markdown
    assert "वेतन संहिता" in doc_hi.body_markdown
    print("  [ok] Hindi Grievance Officer notice generated in clean Devanagari script")


def test_orchestrator_legal_tool_integration():
    """Test 6: End-to-end Orchestrator tool calls for new legal tools."""
    print("\n--- Test 6: Orchestrator Legal Tool Call Integration ---")

    orch = Orchestrator()

    # 1. Update case
    orch.handle_tool_call("update_case_info", {
        "worker_type": "gig_worker",
        "issue_category": "unpaid_wages",
        "state": "Karnataka",
        "platform_or_employer": "Zomato",
        "confidence": "high",
    })

    # 2. Call check_eligibility via Orchestrator
    import json
    elig_result = orch.handle_tool_call("check_eligibility", {
        "days_with_primary_aggregator": 110,
        "has_eshram": True,
    })
    elig_data = json.loads(elig_result["tool_result"])
    assert elig_data["status"] == "success"
    assert "Eligible" in elig_data["badge"]
    assert orch.case.days_worked == 110
    print("  [ok] Orchestrator executed check_eligibility tool successfully")

    # 3. Call calculate_unpaid_wages via Orchestrator
    wage_result = orch.handle_tool_call("calculate_unpaid_wages", {
        "base_unpaid": 14000,
        "unauthorized_deductions": 2500,
    })
    wage_data = json.loads(wage_result["tool_result"])
    assert wage_data["status"] == "success"
    assert wage_data["net_unpaid"] == 16500.0
    assert orch.case.amount == "16500"
    print("  [ok] Orchestrator executed calculate_unpaid_wages tool successfully")

    # 4. Advance status to rights_verified and call generate_complaint_letter
    orch.case_manager.update_field("status", "rights_verified")
    comp_result = orch.handle_tool_call("generate_complaint_letter", {
        "authority_type": "labour_commissioner",
        "language": "en",
    })
    comp_data = json.loads(comp_result["tool_result"])
    assert comp_data["status"] == "success"
    assert len(orch.case.complaint_drafts) == 1
    print("  [ok] Orchestrator executed generate_complaint_letter tool successfully")


if __name__ == "__main__":
    print("=" * 60)
    print("  WorkerSaathi — Gireesh Legal & Evidence Test Suite")
    print("=" * 60)

    test_eligibility_90_120_rule()
    test_state_specific_protections()
    test_wage_calculator_and_statutory_claims()
    test_privacy_redaction_and_evidence()
    test_complaint_generator()
    test_orchestrator_legal_tool_integration()

    print("\n" + "=" * 60)
    print("  ALL 6 LEGAL & EVIDENCE TEST SUITES PASSED (100%)!")
    print("=" * 60)
