"""
safety/ — Critical safety logic.

Responsibilities:
  - Danger detection (violence, trafficking, child labour, etc.)
  - Risk classification (HIGH / MEDIUM / LOW)
  - Emergency escalation routing (112 / 181 / 1098 / 15100)
  - PII redaction (Aadhaar, PAN, phone, bank)
  - Safety policy enforcement

IMPORTANT: Safety escalation can interrupt ANY conversation state.
It always takes priority over the rights-mapping flow.
"""
