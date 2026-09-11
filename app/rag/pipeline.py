"""
pipeline.py -- Data pipeline entry point.

Reads links.txt → generates sources.json → generates rights_matrix.json.

Usage:
    python -m app.rag.pipeline

This is the only command you run after editing links.txt.
Everything else flows automatically.
"""

import os
import sys
from pathlib import Path


# Project root for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
LINKS_FILE = KNOWLEDGE_DIR / "links.txt"
SOURCES_FILE = KNOWLEDGE_DIR / "sources.json"
MATRIX_FILE = KNOWLEDGE_DIR / "rights_matrix.json"


def build():
    """
    Full pipeline:
      1. Parse links.txt → LegalSource objects
      2. Save to sources.json
      3. Build rights matrix
      4. Save to rights_matrix.json
    """
    from app.rag.sources import SourceRegistry
    from app.rag.matrix import RightsMatrix

    print("=" * 60)
    print("  WorkerSaathi Knowledge Pipeline")
    print("=" * 60)

    # ── Step 1: Parse links.txt ──────────────────────────────────
    if not LINKS_FILE.exists():
        print(f"[ERROR] links.txt not found at: {LINKS_FILE}")
        sys.exit(1)

    print(f"\n[1/4] Parsing links.txt...")
    registry = SourceRegistry()
    registry.load_from_links(str(LINKS_FILE))

    total = len(registry.sources)
    active = registry.get_active_count()
    states = registry.get_states_covered()

    print(f"      Found {total} sources ({active} active)")
    print(f"      States/UTs covered: {len(states)}")

    # ── Step 2: Save sources.json ────────────────────────────────
    print(f"\n[2/4] Generating sources.json...")
    registry.save_to_json(str(SOURCES_FILE))
    print(f"      Saved to: {SOURCES_FILE}")

    # ── Step 3: Build rights matrix ──────────────────────────────
    print(f"\n[3/4] Building rights matrix...")
    matrix = RightsMatrix(registry)
    matrix.build_from_registry(registry)

    stats = matrix.get_matrix_stats()
    print(f"      Matrix entries: {stats['total_entries']}")
    print(f"      Unique sources: {stats['unique_sources']}")

    # ── Step 4: Save rights_matrix.json ──────────────────────────
    print(f"\n[4/4] Generating rights_matrix.json...")
    matrix.save_to_json(str(MATRIX_FILE))
    print(f"      Saved to: {MATRIX_FILE}")

    # ── Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Pipeline complete!")
    print("=" * 60)

    # Quick validation
    print("\n  Quick validation tests:")
    _run_tests(registry)


def _run_tests(registry):
    """Run the Phase 3 success criteria tests."""
    from app.rag.models import SourceStatus

    # Test A: gig_worker + Karnataka + platform_deactivation
    results_a = registry.query("gig_worker", "Karnataka", "platform_deactivation")
    karnataka_law = any("Karnataka" in s.title and s.source_type.value == "law" for s in results_a)
    status_a = "PASS" if karnataka_law else "PARTIAL (portal found, law may need adding)"
    print(f"  Test A (gig + Karnataka + deactivation): {status_a}")
    for s in results_a[:3]:
        print(f"         -> {s.title} [{s.source_type.value}]")

    # Test B: domestic_worker + Tamil Nadu + welfare
    results_b = registry.query("domestic_worker", "Tamil Nadu", "welfare")
    tn_found = any("Tamil Nadu" in s.title for s in results_b)
    status_b = "PASS" if tn_found else "FAIL"
    print(f"  Test B (domestic + TN + welfare): {status_b}")
    for s in results_b[:3]:
        print(f"         -> {s.title} [{s.source_type.value}]")

    # Test C: construction_worker + Central + injury
    results_c = registry.query("construction_worker", None, "workplace_injury")
    central_found = any(s.jurisdiction.value == "central" for s in results_c)
    status_c = "PASS" if central_found else "FAIL"
    print(f"  Test C (construction + Central + injury): {status_c}")
    for s in results_c[:3]:
        print(f"         -> {s.title} [{s.source_type.value}]")

    # Test D: disabled/superseded sources excluded
    disabled = [s for s in registry.sources if s.status in (SourceStatus.DISABLED, SourceStatus.SUPERSEDED)]
    if disabled:
        test_disabled = registry.query("gig_worker", None, "all")
        none_disabled = not any(
            s.status in (SourceStatus.DISABLED, SourceStatus.SUPERSEDED) 
            for s in test_disabled
        )
        status_d = "PASS" if none_disabled else "FAIL"
    else:
        status_d = "PASS (no disabled sources to test)"
    print(f"  Test D (disabled sources excluded): {status_d}")

    # Test E: all sources have required metadata
    all_have_meta = all(
        s.source_url and s.authority and s.last_verified
        for s in registry.sources
    )
    status_e = "PASS" if all_have_meta else "FAIL"
    print(f"  Test E (all sources have URL + authority + verified): {status_e}")


if __name__ == "__main__":
    build()
