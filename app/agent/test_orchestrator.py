"""
test_orchestrator.py -- Phase 6 orchestrator tests.

Tests each tool independently, then the full flow.

Usage:
    python -m app.agent.test_orchestrator
"""

import json
import sys

from app.agent.orchestrator import Orchestrator, ToolError
from app.agent.tool_registry import get_tools_for_status


def test_tool_permissions():
    """Test 0: Tool permissions by status."""
    print("\n  Test 0: Tool permissions")

    # NEW status — only update_case_info and escalate_safety
    tools = get_tools_for_status("new")
    names = [t["name"] for t in tools]
    assert "update_case_info" in names, f"Missing update_case_info in 'new': {names}"
    assert "escalate_safety" in names, f"Missing escalate_safety in 'new': {names}"
    assert "retrieve_rights" not in names, f"retrieve_rights shouldn't be in 'new'"
    print("    NEW: update_case_info + escalate_safety only -> PASS")

    # CLASSIFIED — gains retrieve_rights
    tools = get_tools_for_status("classified")
    names = [t["name"] for t in tools]
    assert "retrieve_rights" in names, f"Missing retrieve_rights in 'classified'"
    print("    CLASSIFIED: +retrieve_rights -> PASS")

    # RIGHTS_VERIFIED — gains generate_evidence + draft_message
    tools = get_tools_for_status("rights_verified")
    names = [t["name"] for t in tools]
    assert "generate_evidence" in names
    assert "draft_message" in names
    print("    RIGHTS_VERIFIED: +generate_evidence, +draft_message -> PASS")

    # SAFETY — always has escalate_safety
    for status in ["new", "listening", "classified", "closed"]:
        tools = get_tools_for_status(status)
        names = [t["name"] for t in tools]
        assert "escalate_safety" in names, f"Missing escalate_safety in '{status}'"
    print("    escalate_safety always available -> PASS")

    return True


def test_update_case_info():
    """Test 1: log_case_field via update_case_info."""
    print("\n  Test 1: update_case_info")

    orch = Orchestrator()

    result = orch.handle_tool_call("update_case_info", {
        "worker_type": "gig_worker",
        "issue_category": "unpaid_wages",
        "confidence": "high",
    })

    parsed = json.loads(result["tool_result"])
    assert parsed["status"] == "updated", f"Expected 'updated', got {parsed['status']}"
    assert "worker_type" in parsed["fields_updated"]
    assert "issue_category" in parsed["fields_updated"]
    assert orch.case.worker_type.value == "gig_worker"
    assert orch.case.issue_category.value == "unpaid_wages"
    print(f"    Fields: {parsed['fields_updated']} -> PASS")

    # Test prompt update
    assert result["needs_prompt_update"], "Should need prompt update"
    assert result["new_prompt"] is not None
    print("    Prompt updated -> PASS")

    return True


def test_unknown_tool():
    """Test 2: Unknown tool returns error."""
    print("\n  Test 2: Unknown tool")

    orch = Orchestrator()
    result = orch.handle_tool_call("hack_database", {"table": "users"})

    parsed = json.loads(result["tool_result"])
    assert parsed["status"] == "error"
    assert parsed["error_code"] == ToolError.UNKNOWN_TOOL
    print(f"    Error: {parsed['error_code']} -> PASS")

    return True


def test_tool_not_allowed():
    """Test 3: Tool not allowed in current status."""
    print("\n  Test 3: Tool not allowed")

    orch = Orchestrator()
    # Case is NEW — generate_evidence should not be allowed
    result = orch.handle_tool_call("generate_evidence", {"purpose": "complaint"})

    parsed = json.loads(result["tool_result"])
    assert parsed["status"] == "error"
    assert parsed["error_code"] == ToolError.TOOL_NOT_ALLOWED
    print(f"    Error: {parsed['error_code']} -> PASS")

    return True


def test_escalate_safety():
    """Test 4: Safety escalation."""
    print("\n  Test 4: Safety escalation")

    orch = Orchestrator()

    result = orch.handle_tool_call("escalate_safety", {
        "danger_type": "immediate_physical_danger",
        "description": "Worker trapped in unsafe construction site",
    })

    parsed = json.loads(result["tool_result"])
    assert parsed["status"] == "safety_escalation"
    assert "112" in parsed["safety_response"]
    assert orch.case.status.value == "safety_escalation"
    print(f"    Status: {orch.case.status.value} -> PASS")
    print(f"    Has emergency numbers -> PASS")

    return True


def test_retrieve_rights_permission():
    """Test 5: retrieve_rights only after classification."""
    print("\n  Test 5: retrieve_rights permission flow")

    orch = Orchestrator()

    # Should fail in NEW status
    result = orch.handle_tool_call("retrieve_rights", {"query": "wages"})
    parsed = json.loads(result["tool_result"])
    assert parsed["status"] == "error"
    assert parsed["error_code"] == ToolError.TOOL_NOT_ALLOWED
    print("    NEW -> not allowed -> PASS")

    # Classify first
    orch.handle_tool_call("update_case_info", {
        "issue_category": "unpaid_wages",
        "confidence": "high",
    })

    # Now should be allowed (case is CLASSIFIED)
    assert orch.case.status.value == "classified"
    print(f"    Status after classify: {orch.case.status.value} -> PASS")

    return True


def test_draft_message():
    """Test 6: Draft message."""
    print("\n  Test 6: Draft message")

    orch = Orchestrator()

    # Set up case first
    orch.handle_tool_call("update_case_info", {
        "worker_type": "gig_worker",
        "issue_category": "unpaid_wages",
        "platform_or_employer": "Swiggy",
        "amount": "15000",
        "confidence": "high",
    })

    # Move to rights_verified manually for testing
    from app.case.models import CaseStatus
    orch.case_manager.case.status = CaseStatus.RIGHTS_VERIFIED

    result = orch.handle_tool_call("draft_message", {
        "recipient": "Swiggy",
        "tone": "formal",
    })

    parsed = json.loads(result["tool_result"])
    assert parsed["status"] == "success"
    assert "Swiggy" in parsed["message_context"]
    assert "15000" in parsed["message_context"]
    print(f"    Message context includes case details -> PASS")

    return True


def test_generate_evidence():
    """Test 7: Generate evidence package."""
    print("\n  Test 7: Generate evidence")

    orch = Orchestrator()

    # Set up case
    orch.handle_tool_call("update_case_info", {
        "worker_type": "construction_worker",
        "issue_category": "workplace_injury",
        "injury_details": "fell from scaffolding, broken arm",
        "confidence": "high",
    })

    from app.case.models import CaseStatus
    orch.case_manager.case.status = CaseStatus.RIGHTS_VERIFIED

    result = orch.handle_tool_call("generate_evidence", {"purpose": "complaint"})

    parsed = json.loads(result["tool_result"])
    assert parsed["status"] == "success"
    package = json.loads(parsed["evidence_package"])
    assert package["purpose"] == "complaint"
    assert package["worker_summary"]["worker_type"] == "construction_worker"
    assert "scaffolding" in package["claims"]["injury_details"]
    print(f"    Package includes worker info + claims -> PASS")

    return True


def test_full_flow():
    """Test 8: Full conversation flow simulation."""
    print("\n  Test 8: Full conversation flow")

    orch = Orchestrator()

    # Step 1: Worker speaks
    orch.process_transcript("Meri salary nahi mili, main delivery karta hoon")
    assert orch.case.turn_count == 1
    print("    Step 1: Transcript logged -> OK")

    # Step 2: LLM classifies
    r1 = orch.handle_tool_call("update_case_info", {
        "worker_type": "gig_worker",
        "issue_category": "unpaid_wages",
        "confidence": "high",
    })
    assert orch.case.worker_type.value == "gig_worker"
    assert orch.case.issue_category.value == "unpaid_wages"
    print(f"    Step 2: Classified as gig_worker/unpaid_wages -> OK")

    # Step 3: More info
    orch.process_transcript("Swiggy ke liye kaam karta hoon, 2 mahine se payment nahi")
    r2 = orch.handle_tool_call("update_case_info", {
        "platform_or_employer": "Swiggy",
        "payment_pending_duration": "2 months",
        "confidence": "high",
    })
    print(f"    Step 3: Added employer + duration -> OK")

    # Step 4: retrieve_rights should now be allowed
    status = orch.case.status.value
    tools = get_tools_for_status(status)
    has_retrieve = any(t["name"] == "retrieve_rights" for t in tools)
    assert has_retrieve, f"retrieve_rights not available in {status}"
    print(f"    Step 4: retrieve_rights available in '{status}' -> OK")

    # Step 5: Safety escalation at any time
    r3 = orch.handle_tool_call("escalate_safety", {
        "danger_type": "violence_threat",
        "description": "Contractor threatened worker",
    })
    parsed3 = json.loads(r3["tool_result"])
    assert parsed3["status"] == "safety_escalation"
    assert orch.case.status.value == "safety_escalation"
    print(f"    Step 5: Safety escalation override -> OK")

    print("    Full flow: PASS")
    return True


def main():
    print("\n" + "=" * 60)
    print("  Phase 6 - Orchestrator Tests")
    print("=" * 60)

    tests = [
        test_tool_permissions,
        test_update_case_info,
        test_unknown_tool,
        test_tool_not_allowed,
        test_escalate_safety,
        test_retrieve_rights_permission,
        test_draft_message,
        test_generate_evidence,
        test_full_flow,
    ]

    passed = 0
    for test in tests:
        try:
            if test():
                passed += 1
        except AssertionError as e:
            print(f"    FAIL: {e}")
        except Exception as e:
            print(f"    ERROR: {e}")

    print(f"\n  Results: {passed}/{len(tests)} passed")
    pct = (passed / len(tests) * 100) if tests else 0
    print(f"  Score: {pct:.0f}%")
    print("=" * 60)

    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
