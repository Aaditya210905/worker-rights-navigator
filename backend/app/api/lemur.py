"""
lemur.py -- Re-export of action_plan router for backward compatibility.
No assemblyai dependency required.
"""

from app.api.action_plan import router, ActionPlanResponse, generate_action_plan

__all__ = ["router", "ActionPlanResponse", "generate_action_plan"]
