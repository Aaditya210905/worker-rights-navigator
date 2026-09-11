"""
database.py -- SQLite persistence for WorkerSaathi cases.

Provides an audit trail (case_events) and persistent case storage.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Any

# Default path: worker-rights-navigator/data/worker_cases.db
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "worker_cases.db"

class DatabaseManager:
    """Manages SQLite connection and schema."""

    def __init__(self, db_path: str = str(DEFAULT_DB_PATH)):
        self.db_path = db_path
        # Ensure directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initialize schema if it doesn't exist."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # Cases table: Current state snapshot
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    worker_type TEXT,
                    issue_category TEXT,
                    status TEXT,
                    state TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            ''')
            
            # Case Events: Audit log of what changed and when
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS case_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT,
                    timestamp TEXT,
                    event_type TEXT,
                    field TEXT,
                    value TEXT,
                    source TEXT,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id)
                )
            ''')
            
            # Action Plans: Generated next steps
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS action_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT,
                    action TEXT,
                    status TEXT,
                    source TEXT,
                    created_at TEXT,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id)
                )
            ''')
            
            # Evidence Items: Pointers to collected evidence
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS evidence_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT,
                    evidence_type TEXT,
                    description TEXT,
                    reference TEXT,
                    created_at TEXT,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id)
                )
            ''')
            
            conn.commit()

    def upsert_case(self, case_id: str, worker_type: str, issue_category: str, status: str, state: str, created_at: str):
        """Insert or update a case record."""
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO cases (case_id, worker_type, issue_category, status, state, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(case_id) DO UPDATE SET
                    worker_type=excluded.worker_type,
                    issue_category=excluded.issue_category,
                    status=excluded.status,
                    state=excluded.state,
                    updated_at=excluded.updated_at
            ''', (case_id, worker_type, issue_category, status, state, created_at, now))
            conn.commit()

    def log_event(self, case_id: str, event_type: str, field: str, value: Any, source: str = "worker_statement"):
        """Append an event to the audit log."""
        now = datetime.now().isoformat()
        val_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO case_events (case_id, timestamp, event_type, field, value, source)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (case_id, now, event_type, field, val_str, source))
            conn.commit()

    def save_action_plan(self, case_id: str, actions: list[dict]):
        """Save a generated action plan."""
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            cursor = conn.cursor()
            # For simplicity, we just insert the actions. In a real system we might version them.
            for action in actions:
                cursor.execute('''
                    INSERT INTO action_plans (case_id, action, status, source, created_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    case_id, 
                    action.get("action", ""), 
                    action.get("status", "pending"), 
                    action.get("source", ""), 
                    now
                ))
            conn.commit()

    def save_evidence_item(self, case_id: str, evidence_type: str, description: str, reference: str = ""):
        """Save a reference to an evidence item."""
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO evidence_items (case_id, evidence_type, description, reference, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (case_id, evidence_type, description, reference, now))
            conn.commit()

# Global instance
db = DatabaseManager()
