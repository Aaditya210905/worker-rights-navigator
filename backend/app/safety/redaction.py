"""
redaction.py -- Sensitive PII Redaction Safeguards.

Ensures worker privacy by automatically detecting and masking Aadhaar numbers,
bank account numbers, and OTPs.
"""

import re

# Privacy Safeguards Patterns
# Workers must never have their Aadhaar or sensitive bank info exposed.
AADHAAR_PATTERN = re.compile(r'\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b')
BANK_ACC_PATTERN = re.compile(r'\b(?:account|a/c|acc\.?)\s*(?:no\.?|num\.?)?\s*[:\-]?\s*([0-9]{9,18})\b', re.IGNORECASE)
OTP_PATTERN = re.compile(r'\b(?:otp|one time password|pin)\s*(?:is|:)?\s*([0-9]{4,6})\b', re.IGNORECASE)
PHONE_PATTERN = re.compile(r'\b(?:(?:\+91|0)?[6-9]\d{9})\b')


def redact_sensitive_pii(text: str) -> tuple[str, bool, list[str]]:
    """
    Detects and masks Aadhaar numbers, bank account details, and OTPs.
    Returns (cleaned_text, was_redacted, list_of_redactions).
    """
    redactions = []
    clean_text = text

    # Redact Aadhaar
    if AADHAAR_PATTERN.search(clean_text):
        clean_text = AADHAAR_PATTERN.sub("[REDACTED_AADHAAR_NUMBER]", clean_text)
        redactions.append("12-digit Aadhaar number masked")

    # Redact Bank Account
    if BANK_ACC_PATTERN.search(clean_text):
        clean_text = BANK_ACC_PATTERN.sub("A/C: [REDACTED_BANK_ACCOUNT]", clean_text)
        redactions.append("Bank account number masked")

    # Redact OTP
    if OTP_PATTERN.search(clean_text):
        clean_text = OTP_PATTERN.sub("OTP: [REDACTED_OTP]", clean_text)
        redactions.append("One-Time Password (OTP) masked")

    was_redacted = len(redactions) > 0
    return clean_text, was_redacted, redactions
