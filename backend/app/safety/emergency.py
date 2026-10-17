"""
emergency.py -- Official Government Emergency Helplines & Escalation Responses.

Verified central and state emergency routing for physical danger, trafficking,
and workplace accidents.
"""

from typing import Dict, List

EMERGENCY_HELPLINES: Dict[str, str] = {
    "emergency_universal": "112 (National Emergency Helpline - Police/Fire/Ambulance)",
    "police": "100",
    "ambulance": "108",
    "women_helpline": "1091 / 181",
    "childline": "1098 (Child Helpline)",
    "anti_trafficking": "1800-419-8588 (Toll-Free National Anti-Trafficking)",
    "ncpcr": "1800-121-0260 (National Commission for Protection of Child Rights)",
    "fire_brigade": "101",
    "ndrf": "011-24363260 (National Disaster Response Force)",
}


def get_safety_response(danger_type: str) -> str:
    """Return verified official emergency information based on detected danger."""
    lines = []
    lines.append("EMERGENCY HELPLINES:")
    lines.append("  - Emergency (Police/Fire/Ambulance): 112")
    lines.append("  - Police: 100")
    lines.append("  - Ambulance: 108")
    lines.append("  - Women Helpline: 1091 / 181")
    lines.append("  - Child Helpline (Childline): 1098")
    lines.append("  - Anti-Trafficking: 1800-419-8588 (toll-free)")

    if danger_type in ("child_labour", "trafficking"):
        lines.append("")
        lines.append("SPECIFIC:")
        lines.append("  - National Commission for Protection of Child Rights: 1800-121-0260")
        lines.append("  - Anti-Human Trafficking Unit: Contact local police or 112")

    if danger_type in ("immediate_physical_danger", "workplace_trapped"):
        lines.append("")
        lines.append("SPECIFIC:")
        lines.append("  - NDRF (National Disaster Response Force): 011-24363260")
        lines.append("  - Fire Brigade: 101")

    lines.append("")
    lines.append("IMPORTANT: These are verified government helpline numbers.")
    lines.append("Do NOT share any numbers not listed above.")

    return "\n".join(lines)
