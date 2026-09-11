"""
sources.py -- Reads links.txt and builds the source registry.

LinksParser: parses links.txt into LegalSource objects.
SourceRegistry: queries sources by worker_type, state, issue.

links.txt is the single source of truth. Add/remove links there,
and this code automatically reflects the changes.
"""

import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Optional

from app.rag.models import (
    LegalSource, SourceType, SourceStatus, Jurisdiction,
)


# ── LinksParser ──────────────────────────────────────────────────────────────

class LinksParser:
    """
    Parses the links.txt file into structured LegalSource objects.

    Format:
        ---
        # KEY: VALUE
        # KEY: VALUE
        https://url.here
        ---
    """

    @staticmethod
    def parse(filepath: str) -> list[LegalSource]:
        """Parse links.txt and return a list of LegalSource objects."""
        sources = []

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Split by --- separator
        blocks = content.split("---")

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            # Parse metadata and URL from the block
            source = LinksParser._parse_block(block)
            if source:
                sources.append(source)

        return sources

    @staticmethod
    def _parse_block(block: str) -> Optional[LegalSource]:
        """Parse a single block into a LegalSource."""
        metadata = {}
        url = None

        for line in block.split("\n"):
            line = line.strip()
            if not line:
                continue

            if line.startswith("# ") and ":" in line:
                # Metadata line: # KEY: VALUE
                key_val = line[2:]  # strip "# "
                colon_idx = key_val.index(":")
                key = key_val[:colon_idx].strip().upper()
                value = key_val[colon_idx + 1:].strip()
                metadata[key] = value

            elif line.startswith("http://") or line.startswith("https://"):
                url = line

            elif line.startswith("#"):
                # Comment line (header comments), skip
                continue

        if not url:
            return None

        # Build source_id from URL hash
        source_id = hashlib.md5(url.encode()).hexdigest()[:12]

        # Parse comma-separated lists
        worker_types = [
            w.strip() for w in metadata.get("WORKER_TYPES", "all").split(",")
        ]
        issues = [
            i.strip() for i in metadata.get("ISSUES", "all").split(",")
        ]

        # Map source type
        type_map = {
            "law": SourceType.LAW,
            "rules": SourceType.RULES,
            "scheme": SourceType.SCHEME,
            "portal": SourceType.PORTAL,
            "board": SourceType.BOARD,
            "notification": SourceType.NOTIFICATION,
        }
        source_type = type_map.get(
            metadata.get("TYPE", "portal").lower(),
            SourceType.PORTAL,
        )

        # Map status
        status_map = {
            "active": SourceStatus.ACTIVE,
            "verify": SourceStatus.VERIFY,
            "disabled": SourceStatus.DISABLED,
            "superseded": SourceStatus.SUPERSEDED,
            "proposed": SourceStatus.PROPOSED,
        }
        status = status_map.get(
            metadata.get("STATUS", "active").lower(),
            SourceStatus.ACTIVE,
        )

        # Map jurisdiction
        jurisdiction_map = {
            "central": Jurisdiction.CENTRAL,
            "state": Jurisdiction.STATE,
            "ut": Jurisdiction.UT,
        }
        jurisdiction = jurisdiction_map.get(
            metadata.get("JURISDICTION", "central").lower(),
            Jurisdiction.CENTRAL,
        )

        return LegalSource(
            source_id=source_id,
            title=metadata.get("TITLE", "Unknown"),
            source_type=source_type,
            authority=metadata.get("AUTHORITY", "Unknown"),
            jurisdiction=jurisdiction,
            state=metadata.get("STATE"),
            worker_types=worker_types,
            issue_categories=issues,
            source_url=url,
            status=status,
            effective_from=metadata.get("EFFECTIVE"),
            last_verified=date.today().isoformat(),
            notes=metadata.get("NOTES"),
        )


# ── SourceRegistry ───────────────────────────────────────────────────────────

class SourceRegistry:
    """
    Loads and queries legal sources.

    Can load from:
      - links.txt directly (parse on the fly)
      - sources.json (pre-generated cache)
    """

    def __init__(self):
        self._sources: list[LegalSource] = []

    def load_from_links(self, filepath: str):
        """Parse links.txt and load all sources."""
        self._sources = LinksParser.parse(filepath)

    def load_from_json(self, filepath: str):
        """Load pre-generated sources.json."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._sources = [LegalSource(**s) for s in data]

    def save_to_json(self, filepath: str):
        """Save current sources to sources.json."""
        data = [s.model_dump() for s in self._sources]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @property
    def sources(self) -> list[LegalSource]:
        return self._sources

    def get_by_id(self, source_id: str) -> Optional[LegalSource]:
        """Get a source by its ID."""
        for s in self._sources:
            if s.source_id == source_id:
                return s
        return None

    def query(
        self,
        worker_type: str = None,
        state: str = None,
        issue: str = None,
        include_central: bool = True,
    ) -> list[LegalSource]:
        """
        Find all sources relevant to a case.

        Args:
            worker_type: e.g., "gig_worker"
            state: e.g., "Karnataka"
            issue: e.g., "platform_deactivation"
            include_central: whether to include central govt sources

        Returns:
            Matching sources, sorted by relevance (specific > general).
        """
        results = []

        for source in self._sources:
            if not include_central and source.jurisdiction == Jurisdiction.CENTRAL:
                continue

            if source.matches_case(worker_type, state, issue):
                results.append(source)

        # Sort: state-specific sources first, then central
        # Within each group: laws > schemes > boards > portals
        type_priority = {
            SourceType.LAW: 0,
            SourceType.RULES: 1,
            SourceType.NOTIFICATION: 2,
            SourceType.SCHEME: 3,
            SourceType.BOARD: 4,
            SourceType.PORTAL: 5,
        }

        def sort_key(s: LegalSource):
            is_central = 1 if s.jurisdiction == Jurisdiction.CENTRAL else 0
            return (is_central, type_priority.get(s.source_type, 9))

        results.sort(key=sort_key)
        return results

    def get_active_count(self) -> int:
        """Count active (non-disabled) sources."""
        return sum(1 for s in self._sources if s.status != SourceStatus.DISABLED)

    def get_states_covered(self) -> list[str]:
        """List all states/UTs that have at least one source."""
        states = set()
        for s in self._sources:
            if s.state:
                states.add(s.state)
        return sorted(states)
