"""
knowledge.py -- Read-only endpoints for the legal knowledge base.

Serves indexed sources and statistics from the knowledge/ directory.
"""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from app.api.schemas import (
    KnowledgeStatsResponse,
    KnowledgeSourcesResponse,
    SourceItem,
)

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
SOURCES_FILE = KNOWLEDGE_DIR / "sources.json"
RESEARCH_DIR = KNOWLEDGE_DIR / "workersaathi" / "json"


def _load_sources() -> list[dict]:
    """Load sources.json if it exists."""
    if not SOURCES_FILE.exists():
        return []
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("sources", [])


def _load_research_data() -> dict:
    """Load research JSON files and count items."""
    stats = {"items": 0, "sources": 0, "gaps": 0, "conflicts": 0}
    if not RESEARCH_DIR.exists():
        return stats

    for fname in ["knowledge_items.json", "knowledge.json"]:
        path = RESEARCH_DIR / fname
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data if isinstance(data, list) else data.get("items", [])
            stats["items"] = len(items)
            break

    for fname in ["sources.json"]:
        path = RESEARCH_DIR / fname
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            sources = data if isinstance(data, list) else data.get("sources", [])
            stats["sources"] = len(sources)
            break

    for fname in ["gaps.json"]:
        path = RESEARCH_DIR / fname
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            gaps = data if isinstance(data, list) else data.get("gaps", [])
            stats["gaps"] = len(gaps)
            break

    for fname in ["conflicts.json"]:
        path = RESEARCH_DIR / fname
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            conflicts = data if isinstance(data, list) else data.get("conflicts", [])
            stats["conflicts"] = len(conflicts)
            break

    return stats


@router.get("/sources", response_model=KnowledgeSourcesResponse)
async def list_sources():
    """List all indexed legal sources."""
    raw = _load_sources()
    sources = []
    for s in raw:
        sources.append(SourceItem(
            id=s.get("id", s.get("source_id", "")),
            title=s.get("title", s.get("name", "")),
            source_type=s.get("type", s.get("source_type", "")),
            url=s.get("url", s.get("official_url", "")),
            jurisdiction=s.get("jurisdiction", "central"),
        ))
    return KnowledgeSourcesResponse(sources=sources, total=len(sources))


@router.get("/stats", response_model=KnowledgeStatsResponse)
async def knowledge_stats():
    """Knowledge base statistics."""
    research = _load_research_data()
    sources = _load_sources()
    return KnowledgeStatsResponse(
        total_sources=len(sources) or research["sources"],
        total_documents=research["items"],
        total_gaps=research["gaps"],
        total_conflicts=research["conflicts"],
        jurisdiction="central",
    )
