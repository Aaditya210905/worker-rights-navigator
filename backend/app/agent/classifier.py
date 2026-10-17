"""
classifier.py -- Tool definitions for LLM-based classification.

Instead of brittle keyword matching, we define tools that the
AssemblyAI LLM calls when it identifies case information from
the worker's speech. The LLM naturally handles:
  - Multiple languages (Hindi, English, Hinglish)
  - Paraphrasing and indirect descriptions
  - Ambiguity detection
  - Context from conversation history

The tools defined here are sent in session.update and the LLM
calls them via tool.call events. We process the structured
arguments and update the case state.
"""

# ── Tool definitions for session.update ──────────────────────────────────────
# These follow the AssemblyAI tool schema (same as OpenAI function calling).

CASE_TOOLS = [
    {
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
                        "unpaid_wages",
                        "workplace_injury",
                        "platform_deactivation",
                        "unknown",
                    ],
                    "description": (
                        "The type of problem. "
                        "unpaid_wages: salary, payment, wages not received. "
                        "workplace_injury: accident, injury, hurt at work. "
                        "platform_deactivation: app account blocked/deactivated/suspended. "
                        "unknown: if the problem doesn't fit these categories."
                    ),
                },
                "worker_type": {
                    "type": "string",
                    "enum": [
                        "gig_worker",
                        "construction_worker",
                        "domestic_worker",
                        "factory_worker",
                        "other",
                        "unknown",
                    ],
                    "description": (
                        "The type of work. "
                        "gig_worker: delivery, ride-sharing, platform-based work. "
                        "construction_worker: building sites, masonry, labour. "
                        "domestic_worker: household cleaning, cooking, caregiving. "
                        "factory_worker: manufacturing, assembly, warehouse. "
                        "other: any other type of work."
                    ),
                },
                "state": {
                    "type": "string",
                    "description": (
                        "The Indian state or union territory where the worker works. "
                        "If the worker mentions a city, infer the state. "
                        "Examples: Mumbai -> Maharashtra, Bangalore -> Karnataka, "
                        "Noida -> Uttar Pradesh. Use the full official state name."
                    ),
                },
                "platform_or_employer": {
                    "type": "string",
                    "description": (
                        "Name of the platform (Zomato, Swiggy, Uber, etc.) "
                        "or employer/contractor the worker works for."
                    ),
                },
                "amount": {
                    "type": "string",
                    "description": (
                        "Pending payment amount in rupees. "
                        "Extract the number. E.g., '20 hazaar' -> '20000'."
                    ),
                },
                "payment_pending_duration": {
                    "type": "string",
                    "description": (
                        "How long payment has been pending. "
                        "E.g., '2 months', '3 weeks', 'do mahine'-> '2 months'."
                    ),
                },
                "incident_date": {
                    "type": "string",
                    "description": (
                        "When the incident happened. "
                        "E.g., 'pichle hafte' -> 'approximately 1 week ago'."
                    ),
                },
                "deactivation_reason": {
                    "type": "string",
                    "description": (
                        "Why the platform deactivated the account. "
                        "E.g., 'no reason given', 'low rating', 'customer complaint'."
                    ),
                },
                "injury_details": {
                    "type": "string",
                    "description": (
                        "Description of the injury or accident. "
                        "E.g., 'fell from scaffolding', 'hand fracture'."
                    ),
                },
                "confidence": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": (
                        "How confident you are about this classification. "
                        "high: clearly stated. medium: inferred from context. "
                        "low: ambiguous, might need clarification."
                    ),
                },
            },
            "required": ["confidence"],
        },
    },
]
