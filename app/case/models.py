"""
models.py -- Canonical enums and the CaseState data model.

Every internal representation of worker type, issue category, state,
and safety level lives here. Spoken language gets normalized to these
enums before anything else touches the data.
"""

from enum import Enum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


# ── Enums ────────────────────────────────────────────────────────────────────

class WorkerType(str, Enum):
    GIG_WORKER = "gig_worker"
    CONSTRUCTION_WORKER = "construction_worker"
    DOMESTIC_WORKER = "domestic_worker"
    OTHER = "other"
    UNKNOWN = "unknown"


class IssueCategory(str, Enum):
    UNPAID_WAGES = "unpaid_wages"
    WORKPLACE_INJURY = "workplace_injury"
    PLATFORM_DEACTIVATION = "platform_deactivation"
    UNKNOWN = "unknown"


class CaseStatus(str, Enum):
    NEW = "new"
    LISTENING = "listening"
    CLASSIFIED = "classified"
    COLLECTING_INFORMATION = "collecting_information"
    SAFETY_CHECK = "safety_check"
    RETRIEVING_RIGHTS = "retrieving_rights"
    RIGHTS_VERIFIED = "rights_verified"
    ACTION_PLAN_READY = "action_plan_ready"
    EVIDENCE_GENERATED = "evidence_generated"
    CLOSED = "closed"
    SAFETY_ESCALATION = "safety_escalation"


class SafetyLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class IndianState(str, Enum):
    """All 28 Indian states + 8 union territories."""
    # States
    ANDHRA_PRADESH = "Andhra Pradesh"
    ARUNACHAL_PRADESH = "Arunachal Pradesh"
    ASSAM = "Assam"
    BIHAR = "Bihar"
    CHHATTISGARH = "Chhattisgarh"
    GOA = "Goa"
    GUJARAT = "Gujarat"
    HARYANA = "Haryana"
    HIMACHAL_PRADESH = "Himachal Pradesh"
    JHARKHAND = "Jharkhand"
    KARNATAKA = "Karnataka"
    KERALA = "Kerala"
    MADHYA_PRADESH = "Madhya Pradesh"
    MAHARASHTRA = "Maharashtra"
    MANIPUR = "Manipur"
    MEGHALAYA = "Meghalaya"
    MIZORAM = "Mizoram"
    NAGALAND = "Nagaland"
    ODISHA = "Odisha"
    PUNJAB = "Punjab"
    RAJASTHAN = "Rajasthan"
    SIKKIM = "Sikkim"
    TAMIL_NADU = "Tamil Nadu"
    TELANGANA = "Telangana"
    TRIPURA = "Tripura"
    UTTAR_PRADESH = "Uttar Pradesh"
    UTTARAKHAND = "Uttarakhand"
    WEST_BENGAL = "West Bengal"

    # Union Territories
    ANDAMAN_NICOBAR = "Andaman and Nicobar Islands"
    CHANDIGARH = "Chandigarh"
    DADRA_NAGAR_HAVELI_DAMAN_DIU = "Dadra and Nagar Haveli and Daman and Diu"
    DELHI = "Delhi"
    JAMMU_KASHMIR = "Jammu and Kashmir"
    LADAKH = "Ladakh"
    LAKSHADWEEP = "Lakshadweep"
    PUDUCHERRY = "Puducherry"

    UNKNOWN = "Unknown"


# ── State name variations (for keyword extraction) ──────────────────────────
# Only alternate spellings, abbreviations, and Hindi names.
# City → State resolution is handled by the LLM, not hardcoded here.

STATE_NAME_MAP = {
    # States
    "andhra pradesh": IndianState.ANDHRA_PRADESH,
    "andhra": IndianState.ANDHRA_PRADESH,
    "ap": IndianState.ANDHRA_PRADESH,

    "arunachal pradesh": IndianState.ARUNACHAL_PRADESH,
    "arunachal": IndianState.ARUNACHAL_PRADESH,

    "assam": IndianState.ASSAM,

    "bihar": IndianState.BIHAR,

    "chhattisgarh": IndianState.CHHATTISGARH,
    "chattisgarh": IndianState.CHHATTISGARH,

    "goa": IndianState.GOA,

    "gujarat": IndianState.GUJARAT,

    "haryana": IndianState.HARYANA,

    "himachal pradesh": IndianState.HIMACHAL_PRADESH,
    "himachal": IndianState.HIMACHAL_PRADESH,
    "hp": IndianState.HIMACHAL_PRADESH,

    "jharkhand": IndianState.JHARKHAND,

    "karnataka": IndianState.KARNATAKA,

    "kerala": IndianState.KERALA,

    "madhya pradesh": IndianState.MADHYA_PRADESH,
    "mp": IndianState.MADHYA_PRADESH,

    "maharashtra": IndianState.MAHARASHTRA,

    "manipur": IndianState.MANIPUR,

    "meghalaya": IndianState.MEGHALAYA,

    "mizoram": IndianState.MIZORAM,

    "nagaland": IndianState.NAGALAND,

    "odisha": IndianState.ODISHA,
    "orissa": IndianState.ODISHA,

    "punjab": IndianState.PUNJAB,

    "rajasthan": IndianState.RAJASTHAN,

    "sikkim": IndianState.SIKKIM,

    "tamil nadu": IndianState.TAMIL_NADU,
    "tamilnadu": IndianState.TAMIL_NADU,
    "tn": IndianState.TAMIL_NADU,

    "telangana": IndianState.TELANGANA,

    "tripura": IndianState.TRIPURA,

    "uttar pradesh": IndianState.UTTAR_PRADESH,
    "up": IndianState.UTTAR_PRADESH,

    "uttarakhand": IndianState.UTTARAKHAND,
    "uttaranchal": IndianState.UTTARAKHAND,

    "west bengal": IndianState.WEST_BENGAL,
    "bengal": IndianState.WEST_BENGAL,

    # Union Territories
    "andaman and nicobar": IndianState.ANDAMAN_NICOBAR,
    "andaman": IndianState.ANDAMAN_NICOBAR,

    "chandigarh": IndianState.CHANDIGARH,

    "dadra and nagar haveli": IndianState.DADRA_NAGAR_HAVELI_DAMAN_DIU,
    "daman and diu": IndianState.DADRA_NAGAR_HAVELI_DAMAN_DIU,
    "daman": IndianState.DADRA_NAGAR_HAVELI_DAMAN_DIU,

    "delhi": IndianState.DELHI,
    "new delhi": IndianState.DELHI,
    "dilli": IndianState.DELHI,

    "jammu and kashmir": IndianState.JAMMU_KASHMIR,
    "jammu kashmir": IndianState.JAMMU_KASHMIR,
    "j&k": IndianState.JAMMU_KASHMIR,
    "kashmir": IndianState.JAMMU_KASHMIR,

    "ladakh": IndianState.LADAKH,

    "lakshadweep": IndianState.LAKSHADWEEP,

    "puducherry": IndianState.PUDUCHERRY,
    "pondicherry": IndianState.PUDUCHERRY,
}


# ── Case State ──────────────────────────────────────────────────────────────

def _generate_case_id() -> str:
    """Generate a human-readable case ID: WS-YYYY-NNNNNN."""
    now = datetime.now()
    short_id = uuid.uuid4().hex[:6].upper()
    return f"WS-{now.year}-{short_id}"


class CaseState(BaseModel):
    """
    The structured representation of a worker's case.

    This is WorkerSaathi's internal notebook — the authoritative
    record of what we know, what we don't, and what to ask next.
    The LLM should NOT own this state; it lives here.
    """

    case_id: str = Field(default_factory=_generate_case_id)

    # ── Classification ───────────────────────────────────────────
    worker_type: WorkerType = WorkerType.UNKNOWN
    issue_category: IssueCategory = IssueCategory.UNKNOWN
    status: CaseStatus = CaseStatus.NEW

    # ── Jurisdiction ─────────────────────────────────────────────
    state: IndianState = IndianState.UNKNOWN

    # ── Issue details ────────────────────────────────────────────
    platform_or_employer: Optional[str] = None
    incident_date: Optional[str] = None
    payment_due_date: Optional[str] = None
    amount: Optional[str] = None
    deactivation_reason: Optional[str] = None
    injury_details: Optional[str] = None
    payment_pending_duration: Optional[str] = None

    # ── Safety ───────────────────────────────────────────────────
    safety_level: SafetyLevel = SafetyLevel.UNKNOWN

    # ── Conversation metadata ────────────────────────────────────
    turn_count: int = 0
    raw_description: Optional[str] = None

    def get_filled_fields(self) -> dict:
        """Return all fields that have been filled (non-None, non-unknown)."""
        filled = {}
        for field_name in [
            "worker_type", "issue_category", "state",
            "platform_or_employer", "incident_date",
            "payment_due_date", "amount", "deactivation_reason",
            "injury_details", "payment_pending_duration",
        ]:
            val = getattr(self, field_name)
            if val is not None and val not in (
                WorkerType.UNKNOWN, IssueCategory.UNKNOWN,
                IndianState.UNKNOWN, SafetyLevel.UNKNOWN,
            ):
                filled[field_name] = str(val) if isinstance(val, Enum) else val
        return filled

    def summary(self) -> str:
        """Human-readable summary of the current case state."""
        filled = self.get_filled_fields()
        if not filled:
            return "No information collected yet."
        lines = [f"  {k}: {v}" for k, v in filled.items()]
        return "\n".join(lines)
