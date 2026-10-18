"""
test_api_integration.py -- End-to-End API endpoint test for Gireesh's Legal & Evidence routes.

Tests all REST endpoints added to FastAPI:
1. POST /api/v1/sessions
2. GET  /api/v1/sessions/{id}/case
3. POST /api/v1/sessions/{id}/eligibility
4. POST /api/v1/sessions/{id}/wages
5. POST /api/v1/sessions/{id}/evidence/upload (with simulated payment screenshot / text)
6. GET  /api/v1/sessions/{id}/evidence
7. POST /api/v1/sessions/{id}/complaint
8. GET  /api/v1/sessions/{id}/complaint/{doc_id}/html
"""

import sys
import io
from pathlib import Path

# Ensure backend root is on sys.path
_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_full_legal_api_workflow():
    print("\n--- Starting Legal & Evidence API Integration Test ---")

    # 1. Create a session
    resp = client.post("/api/v1/sessions")
    assert resp.status_code in (200, 201), f"Session create failed: {resp.text}"
    session_data = resp.json()
    session_id = session_data["session_id"]
    print(f"  [1] Created session: {session_id}")

    # 2. Update case context to Rajasthan Gig Worker
    from app.api.session import session_manager
    from app.case.models import WorkerType, IndianState, IssueCategory, CaseStatus

    session = session_manager.get_session(session_id)
    cm = session.orchestrator.case_manager
    cm.update_field("worker_type", WorkerType.GIG_WORKER)
    cm.update_field("state", IndianState.RAJASTHAN)
    cm.update_field("platform_or_employer", "Swiggy")
    cm.update_field("issue_category", IssueCategory.UNPAID_WAGES)
    cm.update_field("status", CaseStatus.RIGHTS_VERIFIED)

    # Verify case state retrieval
    resp = client.get(f"/api/v1/sessions/{session_id}/case")
    assert resp.status_code == 200
    case_json = resp.json()
    assert case_json["worker_type"] == "gig_worker"
    assert case_json["state"] == "Rajasthan"
    print("  [2] Case context verified via GET /case")

    # 3. Test Eligibility Endpoint
    resp = client.post(
        f"/api/v1/sessions/{session_id}/eligibility",
        json={
            "days_with_primary_aggregator": 105,
            "number_of_aggregators": 1,
            "has_eshram": True,
        },
    )
    assert resp.status_code == 200, f"Eligibility failed: {resp.text}"
    elig_data = resp.json()
    assert elig_data["verdict"] == "eligible"
    assert elig_data["rule_90_120_status"]["satisfied"] is True
    assert elig_data["state_specific_rights"] is not None
    assert elig_data["state_specific_rights"]["state"] == "Rajasthan"
    print(f"  [3] POST /eligibility passed: {elig_data['verdict_badge']}")

    # 4. Test Wage Calculation Endpoint
    resp = client.post(
        f"/api/v1/sessions/{session_id}/wages",
        json={
            "base_unpaid": 12000.0,
            "withheld_incentives": 4500.0,
            "unauthorized_deductions": 3200.0,
            "period_description": "October 2026 Payout Cycle",
        },
    )
    assert resp.status_code == 200, f"Wage calculation failed: {resp.text}"
    wage_data = resp.json()
    assert wage_data["net_unpaid_balance"] == 19700.0
    assert wage_data["statutory_compensation_estimate"] > 0
    assert wage_data["total_statutory_claim_amount"] > 19700.0
    print(
        f"  [4] POST /wages passed: Net ₹{wage_data['net_unpaid_balance']}, "
        f"Claim ₹{wage_data['total_statutory_claim_amount']}"
    )

    # 5. Test Evidence Upload (simulating an earnings report with PII)
    sample_text_evidence = (
        "Weekly Settlement Swiggy Delivery Partner.\n"
        "Aadhaar Number: 4832 9182 3421 (Do not share)\n"
        "Account Number: 91827364510293 Bank of Baroda\n"
        "OTP code: 827103\n"
        "Net Amount Withheld: Rs. 19,700 for October.\n"
    )
    file_bytes = io.BytesIO(sample_text_evidence.encode("utf-8"))

    resp = client.post(
        f"/api/v1/sessions/{session_id}/evidence/upload",
        files={"file": ("swiggy_october_payout.txt", file_bytes, "text/plain")},
        data={"caption": "Swiggy App Withheld Earnings Statement"},
    )
    assert resp.status_code == 200, f"Evidence upload failed: {resp.text}"
    upload_res = resp.json()
    assert upload_res["parsed_data"]["sensitive_data_redacted"] is True
    assert upload_res["parsed_data"]["primary_amount"] == 19700.0
    print(f"  [5] POST /evidence/upload passed with PII redaction: {upload_res['annexure_label']}")

    # 6. Test Evidence Timeline Retrieval
    resp = client.get(f"/api/v1/sessions/{session_id}/evidence")
    assert resp.status_code == 200
    evidence_res = resp.json()
    assert len(evidence_res["evidence_items"]) >= 1
    assert len(evidence_res["timeline"]["events"]) >= 1
    print(f"  [6] GET /evidence passed: {len(evidence_res['timeline']['events'])} timeline events")

    # 7. Test Complaint Generation (English & Hindi)
    resp = client.post(
        f"/api/v1/sessions/{session_id}/complaint",
        json={"authority_type": "labour_commissioner", "language": "en"},
    )
    assert resp.status_code == 200, f"Complaint generation failed: {resp.text}"
    doc_en = resp.json()
    assert "Formal Legal Complaint" in doc_en["title"]
    assert "RELIEFS SOUGHT" in doc_en["body_markdown"]
    assert "Rajasthan" in doc_en["body_markdown"]
    doc_id = doc_en["document_id"]
    print(f"  [7a] POST /complaint (English) passed: Doc ID {doc_id}")

    # Test Hindi generation
    resp = client.post(
        f"/api/v1/sessions/{session_id}/complaint",
        json={"authority_type": "dlsa_legal_aid", "language": "hi"},
    )
    assert resp.status_code == 200
    doc_hi = resp.json()
    assert "District Legal Services Authority" in doc_hi["authority_name"]
    assert "प्रार्थना" in doc_hi["body_markdown"]
    print("  [7b] POST /complaint (Hindi DLSA) passed successfully")

    # 8. Test Complaint HTML View
    resp = client.get(f"/api/v1/sessions/{session_id}/complaint/{doc_id}/html")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "FORMAL DISPUTE NOTICE" in resp.text
    print("  [8] GET /complaint/{doc_id}/html rendered printable petition successfully")

    # 9. Test Action Plan Endpoint (AssemblyAI-free, Indian Language & Law optimized)
    resp = client.post(f"/api/v1/sessions/{session_id}/action-plan")
    assert resp.status_code == 200, f"Action plan failed: {resp.status_code} - {resp.text}"
    plan_json = resp.json()
    assert "WorkerSaathi Legal Action Plan" in plan_json["plan"]
    assert "Rajasthan" in plan_json["plan"]
    print("  [9] POST /action-plan rendered statutory Indian Legal Action Plan successfully")

    print("\n✅ ALL 9 REST API ENDPOINTS VALIDATED AND PASSING E2E (100%)\n")


if __name__ == "__main__":
    test_full_legal_api_workflow()
