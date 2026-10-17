"""
evidence/ — Generated legal artifacts and evidence processing.

Modules:
- eligibility: Deterministic 90/120-day rule & statutory eligibility checker.
- wage_calculator: Unpaid wages, unlawful deductions & statutory compensation.
- screenshot_parser: Payment screenshot parsing, PII redaction, and Evidence Timeline.
- complaint_generator: Formal complaint draft generator (Labour Commissioner, Aggregators, DLSA).
- action_planner: Source-backed action plan generator.
"""

from app.evidence.action_planner import ActionPlanner
from app.evidence.eligibility import EligibilityChecker, EligibilityReport, EligibilityStatus
from app.evidence.wage_calculator import WageCalculator, WageCalculationResult
from app.evidence.screenshot_parser import EvidenceManager, EvidenceItem, EvidenceTimeline
from app.evidence.complaint_generator import ComplaintGenerator, ComplaintAuthority, ComplaintLanguage, GeneratedDocument

__all__ = [
    "ActionPlanner",
    "EligibilityChecker",
    "EligibilityReport",
    "EligibilityStatus",
    "WageCalculator",
    "WageCalculationResult",
    "EvidenceManager",
    "EvidenceItem",
    "EvidenceTimeline",
    "ComplaintGenerator",
    "ComplaintAuthority",
    "ComplaintLanguage",
    "GeneratedDocument",
]
