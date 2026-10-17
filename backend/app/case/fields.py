"""
fields.py -- Field requirements and question templates per issue category.

Defines which fields are REQUIRED vs HELPFUL for each issue type,
the priority order to ask questions, and the bilingual question templates
that guide WorkerSaathi's clarification flow.
"""

from app.case.models import IssueCategory


# ── Field definitions ────────────────────────────────────────────────────────
# Each field has:
#   priority  : lower = ask first
#   required  : must have before legal retrieval
#   question  : Hinglish question template for the voice agent

FIELD_DEFINITIONS = {
    "state": {
        "priority": 1,
        "required": True,
        "question": "Aap kis state mein kaam karte hain?",
    },
    "worker_type": {
        "priority": 2,
        "required": True,
        "question": "Aap kis tarah ka kaam karte hain? Jaise delivery, construction, ya ghar mein kaam?",
    },
    "platform_or_employer": {
        "priority": 3,
        "required": False,
        "question": "Aap kiske liye kaam karte hain? Platform, contractor, ya koi employer?",
    },
    "amount": {
        "priority": 4,
        "required": False,
        "question": "Kitna amount pending hai, approximately?",
    },
    "payment_pending_duration": {
        "priority": 4,
        "required": False,
        "question": "Payment kitne time se pending hai?",
    },
    "payment_due_date": {
        "priority": 5,
        "required": False,
        "question": "Payment kab milna chahiye tha?",
    },
    "incident_date": {
        "priority": 3,
        "required": False,
        "question": "Yeh kab hua tha?",
    },
    "deactivation_reason": {
        "priority": 3,
        "required": False,
        "question": "Kya platform ne deactivation ka koi reason bataya?",
    },
    "injury_details": {
        "priority": 3,
        "required": False,
        "question": "Kya aap bata sakte hain ki chot kaise lagi?",
    },
}


# ── Which fields are relevant per issue category ─────────────────────────────

ISSUE_FIELDS = {
    IssueCategory.UNPAID_WAGES: [
        "state",
        "worker_type",
        "platform_or_employer",
        "amount",
        "payment_pending_duration",
        "payment_due_date",
    ],
    IssueCategory.WORKPLACE_INJURY: [
        "state",
        "worker_type",
        "platform_or_employer",
        "incident_date",
        "injury_details",
    ],
    IssueCategory.PLATFORM_DEACTIVATION: [
        "state",
        "worker_type",
        "platform_or_employer",
        "incident_date",
        "deactivation_reason",
    ],
    IssueCategory.UNKNOWN: [
        "state",
        "worker_type",
    ],
}


# ── Safety-first questions (for workplace_injury) ───────────────────────────

SAFETY_FIRST_QUESTION = (
    "Pehle yeh bataiye -- kya aap abhi safe jagah par hain "
    "aur aapko medical help mil rahi hai?"
)


def get_missing_fields(issue_category: IssueCategory, filled_fields: dict) -> list:
    """
    Return a priority-sorted list of missing fields for the given issue.

    Each item is: {"field": str, "question": str, "required": bool, "priority": int}
    """
    relevant_fields = ISSUE_FIELDS.get(issue_category, ISSUE_FIELDS[IssueCategory.UNKNOWN])

    missing = []
    for field_name in relevant_fields:
        if field_name not in filled_fields:
            defn = FIELD_DEFINITIONS.get(field_name)
            if defn:
                missing.append({
                    "field": field_name,
                    "question": defn["question"],
                    "required": defn["required"],
                    "priority": defn["priority"],
                })

    # Sort by priority (lower = ask first), required fields first
    missing.sort(key=lambda x: (not x["required"], x["priority"]))
    return missing


def get_next_question(issue_category: IssueCategory, filled_fields: dict) -> str | None:
    """
    Return the single most important question to ask next,
    or None if we have enough information.
    """
    missing = get_missing_fields(issue_category, filled_fields)
    if missing:
        return missing[0]["question"]
    return None


def has_required_fields(issue_category: IssueCategory, filled_fields: dict) -> bool:
    """Check if all required fields for this issue are filled."""
    relevant_fields = ISSUE_FIELDS.get(issue_category, ISSUE_FIELDS[IssueCategory.UNKNOWN])
    for field_name in relevant_fields:
        defn = FIELD_DEFINITIONS.get(field_name)
        if defn and defn["required"] and field_name not in filled_fields:
            return False
    return True
