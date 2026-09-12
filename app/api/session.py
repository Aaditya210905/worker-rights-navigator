"""
session.py -- SessionManager for multi-session WorkerSaathi backend.

Each voice/chat conversation gets its own session with a dedicated
Orchestrator instance. Sessions are stored in-memory with TTL-based
expiry.
"""

import uuid
import time
from typing import Optional
from app.agent.orchestrator import Orchestrator
from app.agent.tool_registry import get_tools_for_status


# Default session timeout: 30 minutes of inactivity
SESSION_TTL_SECONDS = 30 * 60


class Session:
    """A single conversation session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.orchestrator = Orchestrator()
        self.created_at = time.time()
        self.last_active = time.time()

    def touch(self):
        """Update last activity timestamp."""
        self.last_active = time.time()

    @property
    def case_id(self) -> str:
        return self.orchestrator.case.case_id

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.last_active) > SESSION_TTL_SECONDS


class SessionManager:
    """
    Manages multiple concurrent conversation sessions.

    Each session gets its own Orchestrator, CaseManager, and CaseState.
    Sessions expire after 30 minutes of inactivity.
    """

    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def create_session(self) -> Session:
        """Create a new conversation session."""
        session_id = f"sess-{uuid.uuid4().hex[:12]}"
        session = Session(session_id)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get an existing session by ID. Returns None if not found or expired."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired:
            self._sessions.pop(session_id, None)
            return None
        session.touch()
        return session

    def delete_session(self, session_id: str) -> bool:
        """Delete a session. Returns True if it existed."""
        return self._sessions.pop(session_id, None) is not None

    def list_sessions(self) -> list[Session]:
        """List all active (non-expired) sessions."""
        self._cleanup_expired()
        return list(self._sessions.values())

    def count(self) -> int:
        """Number of active sessions."""
        self._cleanup_expired()
        return len(self._sessions)

    def _cleanup_expired(self):
        """Remove expired sessions."""
        expired = [
            sid for sid, s in self._sessions.items()
            if s.is_expired
        ]
        for sid in expired:
            self._sessions.pop(sid, None)

    def cleanup_all(self):
        """Remove all sessions (for shutdown)."""
        self._sessions.clear()


# Global singleton — shared across the FastAPI app
session_manager = SessionManager()
