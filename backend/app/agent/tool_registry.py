"""
tool_registry.py -- Central tool registry for WorkerSaathi.

Defines ALL tools in one place. Each tool has:
  - AssemblyAI schema (for session.update)
  - Allowed case statuses (when the tool can be used)
  - Handler function name

Tools:
  1. update_case_info    — Extract case info from worker speech
  2. retrieve_rights     — Search Central legal knowledge base
  3. generate_evidence   — Build structured evidence package
  4. draft_message       — Draft follow-up message for employer
  5. escalate_safety     — Trigger safety-first response
"""


# ── Tool permission map ──────────────────────────────────────────────────────
# Which tools are available at which case status.
# Safety tool is ALWAYS available.

TOOL_PERMISSIONS = {
    "update_case_info": [
        "new", "listening", "classified",
        "collecting_information", "safety_check",
        "retrieving_rights",
    ],
    "retrieve_rights": [
        "listening", "classified", "collecting_information",
        "retrieving_rights", "rights_verified",
    ],
    "generate_evidence": [
        "rights_verified", "action_plan_ready",
    ],
    "draft_message": [
        "rights_verified", "action_plan_ready",
        "evidence_generated",
    ],
    "escalate_safety": [
        # Available at ANY status
        "new", "listening", "classified",
        "collecting_information", "safety_check",
        "retrieving_rights", "rights_verified",
        "action_plan_ready", "evidence_generated",
        "closed", "safety_escalation",
    ],
    "search_live_news": [
        "new", "listening", "classified", "collecting_information",
        "retrieving_rights", "rights_verified",
    ],
    "check_eligibility": [
        "classified", "collecting_information", "retrieving_rights",
        "rights_verified", "action_plan_ready", "evidence_generated",
    ],
    "calculate_unpaid_wages": [
        "classified", "collecting_information", "retrieving_rights",
        "rights_verified", "action_plan_ready", "evidence_generated",
    ],
    "generate_complaint_letter": [
        "rights_verified", "action_plan_ready", "evidence_generated",
    ],
}


# ── AssemblyAI tool schemas ──────────────────────────────────────────────────

TOOL_UPDATE_CASE = {
    "type": "function",
    "name": "update_case_info",
    "description": (
        "Call this tool EVERY TIME the worker reveals information about "
        "their problem. Extract ALL fields you can identify from what "
        "they said. Only include fields you are confident about. "
        "Do NOT guess — if unsure about a field, omit it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "issue_category": {
                "type": "string",
                "enum": [
                    "unpaid_wages", "workplace_injury",
                    "platform_deactivation", "unknown",
                ],
                "description": (
                    "The type of problem. "
                    "unpaid_wages: salary, payment, wages not received. "
                    "workplace_injury: accident, injury, hurt at work. "
                    "platform_deactivation: app account blocked/deactivated. "
                    "unknown: if the problem doesn't fit these categories."
                ),
            },
            "worker_type": {
                "type": "string",
                "enum": [
                    "gig_worker", "construction_worker",
                    "domestic_worker", "factory_worker",
                    "other", "unknown",
                ],
                "description": (
                    "The type of work. "
                    "gig_worker: delivery, ride-sharing, platform work. "
                    "construction_worker: building sites, masonry. "
                    "domestic_worker: household help. "
                    "factory_worker: manufacturing, warehouse."
                ),
            },
            "state": {
                "type": "string",
                "description": (
                    "Indian state/UT. Infer from city if needed. "
                    "Mumbai -> Maharashtra, Bangalore -> Karnataka."
                ),
            },
            "platform_or_employer": {
                "type": "string",
                "description": "Name of platform or employer.",
            },
            "amount": {
                "type": "string",
                "description": "Pending amount in rupees. '20 hazaar' -> '20000'.",
            },
            "payment_pending_duration": {
                "type": "string",
                "description": "How long pending. 'do mahine' -> '2 months'.",
            },
            "incident_date": {
                "type": "string",
                "description": "When it happened. 'pichle hafte' -> '1 week ago'.",
            },
            "deactivation_reason": {
                "type": "string",
                "description": "Why deactivated. 'low rating', 'no reason'.",
            },
            "injury_details": {
                "type": "string",
                "description": "Injury description. 'fell from scaffolding'.",
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "Confidence in classification.",
            },
        },
        "required": ["confidence"],
    },
}

TOOL_RETRIEVE_RIGHTS = {
    "type": "function",
    "name": "retrieve_rights",
    "description": (
        "Search the Central Government legal knowledge base for worker rights. "
        "Call this AS SOON AS the worker describes their problem — do NOT wait "
        "to collect all information first. Even partial info (just worker type "
        "or just issue type) is enough. The result will contain verified legal "
        "evidence, known gaps, and any conflicts in sources."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "A natural language search query describing the worker's "
                    "legal question. Include worker type and issue details."
                ),
            },
        },
        "required": ["query"],
    },
}

TOOL_GENERATE_EVIDENCE = {
    "type": "function",
    "name": "generate_evidence",
    "description": (
        "Generate a structured evidence package summarizing the worker's case "
        "with relevant legal sources. Call this when the worker wants to file "
        "a complaint or needs their case information organized."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "purpose": {
                "type": "string",
                "enum": ["complaint", "reference", "follow_up"],
                "description": (
                    "complaint: for filing with labour department. "
                    "reference: for worker's own records. "
                    "follow_up: for following up with employer/platform."
                ),
            },
        },
        "required": ["purpose"],
    },
}

TOOL_DRAFT_MESSAGE = {
    "type": "function",
    "name": "draft_message",
    "description": (
        "Draft a follow-up message the worker can send to their employer "
        "or platform about their issue. The message will be professional "
        "and include relevant details from the case."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "recipient": {
                "type": "string",
                "description": "Who the message is for: employer name or platform.",
            },
            "tone": {
                "type": "string",
                "enum": ["formal", "firm", "polite"],
                "description": "Tone of the message.",
            },
        },
        "required": ["recipient"],
    },
}

TOOL_ESCALATE_SAFETY = {
    "type": "function",
    "name": "escalate_safety",
    "description": (
        "IMMEDIATELY call this if the worker is in danger, injured, "
        "trapped, being threatened, or mentions child labour, trafficking, "
        "or violence. This overrides ALL other conversation flow. "
        "Do NOT ask more questions first — call this tool immediately."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "danger_type": {
                "type": "string",
                "enum": [
                    "immediate_physical_danger",
                    "ongoing_injury",
                    "workplace_trapped",
                    "violence_threat",
                    "child_labour",
                    "trafficking",
                    "other_emergency",
                ],
                "description": "Type of safety concern detected.",
            },
            "description": {
                "type": "string",
                "description": "Brief description of the safety situation.",
            },
        },
        "required": ["danger_type"],
    },
}


TOOL_WEB_SEARCH = {
    "type": "function",
    "name": "search_live_news",
    "description": (
        "Search the live internet for recent news, platform policy changes, "
        "or current events (e.g., strikes, recent layoffs) that might "
        "affect the worker's case. Use this when the worker mentions "
        "a recent event that you don't know about."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (e.g., 'Swiggy new payout policy 2026' or 'Zomato delivery strike Bangalore')",
            },
        },
        "required": ["query"],
    },
}


TOOL_CHECK_ELIGIBILITY = {
    "type": "function",
    "name": "check_eligibility",
    "description": (
        "Check worker eligibility under the Code on Social Security 2020 90/120-Day Rule, "
        "e-Shram registration, and State Gig Worker Acts (Rajasthan, Karnataka, etc.). "
        "Call this when the worker mentions how long they have worked, their platform(s), "
        "or asks about their legal rights and eligibility."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "days_with_primary_aggregator": {
                "type": "integer",
                "description": "Days worked with their primary platform (e.g., 95).",
            },
            "total_days_across_aggregators": {
                "type": "integer",
                "description": "Total days worked across all apps (e.g., 130).",
            },
            "number_of_aggregators": {
                "type": "integer",
                "description": "How many apps/aggregators the worker works on.",
            },
            "has_eshram": {
                "type": "boolean",
                "description": "Whether the worker has an e-Shram UAN card.",
            },
        },
    },
}


TOOL_CALCULATE_WAGES = {
    "type": "function",
    "name": "calculate_unpaid_wages",
    "description": (
        "Calculate unpaid wages, unlawful deductions (under Section 18 Code on Wages 2019), "
        "and potential statutory compensation up to 10x (under Section 45). "
        "Call this when specific amounts, deductions, or withheld pay are mentioned."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "base_unpaid": {
                "type": "number",
                "description": "Unpaid base trip earnings or salary in rupees.",
            },
            "withheld_incentives": {
                "type": "number",
                "description": "Surge, peak-hour, or target bonuses withheld in rupees.",
            },
            "unauthorized_deductions": {
                "type": "number",
                "description": "Deductions for penalties, cancellations, or uniforms in rupees.",
            },
            "period_description": {
                "type": "string",
                "description": "Period of disputed work (e.g. 'Last 2 weeks').",
            },
        },
    },
}


TOOL_GENERATE_COMPLAINT = {
    "type": "function",
    "name": "generate_complaint_letter",
    "description": (
        "Generate a formal legal complaint or dispute notice. "
        "Can target the Aggregator Grievance Redressal Officer, Assistant Labour Commissioner, "
        "or District Legal Services Authority (DLSA for free legal aid). "
        "Available in English or Hindi."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "authority_type": {
                "type": "string",
                "enum": [
                    "aggregator_grievance_officer",
                    "labour_commissioner",
                    "dlsa_legal_aid",
                    "state_welfare_board",
                ],
                "description": "Target authority to address the complaint to.",
            },
            "language": {
                "type": "string",
                "enum": ["en", "hi"],
                "description": "Language of complaint ('en' for English, 'hi' for Hindi).",
            },
        },
    },
}


# ── All tools list ───────────────────────────────────────────────────────────

ALL_TOOLS = [
    TOOL_UPDATE_CASE,
    TOOL_RETRIEVE_RIGHTS,
    TOOL_GENERATE_EVIDENCE,
    TOOL_DRAFT_MESSAGE,
    TOOL_ESCALATE_SAFETY,
    TOOL_WEB_SEARCH,
    TOOL_CHECK_ELIGIBILITY,
    TOOL_CALCULATE_WAGES,
    TOOL_GENERATE_COMPLAINT,
]


def get_tools_for_status(case_status: str) -> list[dict]:
    """
    Return only the tools available for the current case status.
    This prevents the LLM from calling tools at inappropriate times.
    """
    available = []
    for tool in ALL_TOOLS:
        name = tool["name"]
        allowed_statuses = TOOL_PERMISSIONS.get(name, [])
        if case_status in allowed_statuses:
            available.append(tool)
    return available
