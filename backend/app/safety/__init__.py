"""
safety/ — Critical safety, escalation, and privacy safeguards.

Exports:
  - get_safety_response: official emergency helpline routing
  - redact_sensitive_pii: PII sanitization (Aadhaar, bank, OTPs)
"""

from app.safety.emergency import get_safety_response, EMERGENCY_HELPLINES
from app.safety.redaction import redact_sensitive_pii

__all__ = [
    "get_safety_response",
    "EMERGENCY_HELPLINES",
    "redact_sensitive_pii",
]
