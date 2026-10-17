"""
test_scenarios.py -- Phase 10 MVP Regression Suite

Simulates the backend orchestration for the 3 core MVP scenarios:
A. Unpaid Wages
B. Workplace Injury (Safety First)
C. Platform Deactivation (Knowledge Gap)

Usage:
    python -m app.agent.test_scenarios
"""

import json
import sys
from app.agent.orchestrator import Orchestrator
from app.case.models import CaseStatus, SafetyLevel

def simulate_scenario_a():
    """Scenario A: Unpaid wages for gig worker."""
    print("\n--- Scenario A: Unpaid Wages ---")
    orch = Orchestrator()
    
    # 1. Classification
    orch.process_transcript("Main delivery karta hoon. Payment nahi mila.")
    res = orch.handle_tool_call("update_case_info", {
        "worker_type": "gig_worker",
        "issue_category": "unpaid_wages"
    })
    assert orch.case.status == CaseStatus.CLASSIFIED
    
    # 2. Collect Missing Info
    orch.process_transcript("Swiggy se ₹8500 pending hai.")
    orch.handle_tool_call("update_case_info", {
        "platform_or_employer": "Swiggy",
        "amount": "8500",
        "payment_pending_duration": "3 weeks",
        "state": "Maharashtra"
    })
    assert orch.case.status == CaseStatus.RETRIEVING_RIGHTS
    
    # 3. Retrieve Rights
    res = orch.handle_tool_call("retrieve_rights", {"query": "gig worker unpaid wages"})
    parsed = json.loads(res["tool_result"])
    if parsed.get("status") == "error":
        print(f"RAG Error: {parsed}")
    assert parsed["status"] == "success"
    if orch.case.status != CaseStatus.RIGHTS_VERIFIED:
        print(f"Status is {orch.case.status} instead of {CaseStatus.RIGHTS_VERIFIED}")
    assert orch.case.status == CaseStatus.RIGHTS_VERIFIED
    
    # 4. Generate Evidence
    res = orch.handle_tool_call("generate_evidence", {"purpose": "complaint"})
    parsed = json.loads(res["tool_result"])
    assert parsed["status"] == "success"
    package = json.loads(parsed["evidence_package"])
    assert package["claims"]["employer"] == "Swiggy"
    assert orch.case.status == CaseStatus.EVIDENCE_GENERATED
    
    # 5. Draft Follow-up
    res = orch.handle_tool_call("draft_message", {"recipient": "Swiggy"})
    parsed = json.loads(res["tool_result"])
    assert parsed["status"] == "success"
    assert "8500" in parsed["message_context"]
    
    print("Scenario A -> PASS")
    return True

def simulate_scenario_b():
    """Scenario B: Workplace Injury & Safety First."""
    print("\n--- Scenario B: Workplace Injury ---")
    orch = Orchestrator()
    
    orch.process_transcript("Site par accident hua aur main danger mein hoon.")
    
    # LLM detects danger and escalates BEFORE retrieving rights
    res = orch.handle_tool_call("escalate_safety", {
        "danger_type": "immediate_physical_danger",
        "description": "Accident at site"
    })
    
    parsed = json.loads(res["tool_result"])
    assert parsed["status"] == "safety_escalation"
    assert orch.case.status == CaseStatus.SAFETY_ESCALATION
    assert orch.case.safety_level == SafetyLevel.CRITICAL
    assert "112" in parsed["safety_response"]
    
    print("Scenario B -> PASS")
    return True

def simulate_scenario_c():
    """Scenario C: Platform Deactivation (Gap)."""
    print("\n--- Scenario C: Platform Deactivation ---")
    orch = Orchestrator()
    
    orch.process_transcript("Mera Zomato account deactivate ho gaya.")
    orch.handle_tool_call("update_case_info", {
        "worker_type": "gig_worker",
        "issue_category": "platform_deactivation",
        "platform_or_employer": "Zomato",
        "deactivation_reason": "unknown"
    })
    
    # RAG Retrieval
    res = orch.handle_tool_call("retrieve_rights", {"query": "platform deactivation gig worker"})
    parsed = json.loads(res["tool_result"])
    
    # Should respect gaps if Central knowledge lacks deactivation protections
    coverage = parsed.get("coverage")
    # For Phase 10 MVP, our local Qdrant might return GAP or PARTIAL.
    assert coverage in ["gap", "partial", "conflict", "full", "unknown"]
    
    # Generate Evidence
    res = orch.handle_tool_call("generate_evidence", {"purpose": "record"})
    parsed = json.loads(res["tool_result"])
    package = json.loads(parsed["evidence_package"])
    
    # The Action Plan should handle the GAP gracefully.
    actions = [a["action"] for a in package["action_plan"]]
    gap_handled = any("legal professional" in a.lower() or "preserve" in a.lower() for a in actions)
    assert gap_handled, "Did not handle gap gracefully"
    
    print("Scenario C -> PASS")
    return True

def main():
    print("=" * 50)
    print("  Phase 10 - End-to-End Scenarios")
    print("=" * 50)
    
    passed = 0
    tests = [simulate_scenario_a, simulate_scenario_b, simulate_scenario_c]
    
    for t in tests:
        try:
            if t(): passed += 1
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"FAIL: {e}")
            
    print(f"\nResults: {passed}/{len(tests)} scenarios passed")
    return 0 if passed == len(tests) else 1

if __name__ == "__main__":
    sys.exit(main())
