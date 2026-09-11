"""
pipeline.py -- Data pipeline entry point.

Phase 3: links.txt -> sources.json -> rights_matrix.json
Phase 4: research package -> chunks -> embeddings -> Qdrant -> retrieval tests

Usage:
    python -m app.rag.pipeline              # Phase 3 only (fast)
    python -m app.rag.pipeline --index      # Phase 3 + Phase 4 indexing
    python -m app.rag.pipeline --test       # Run retrieval tests

This is the only command you run after editing links.txt or data.
"""

import sys
from pathlib import Path


# Project root for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
LINKS_FILE = KNOWLEDGE_DIR / "links.txt"
SOURCES_FILE = KNOWLEDGE_DIR / "sources.json"
MATRIX_FILE = KNOWLEDGE_DIR / "rights_matrix.json"
RESEARCH_DIR = KNOWLEDGE_DIR / "workersaathi" / "json"
QDRANT_PATH = PROJECT_ROOT / "data" / "qdrant"


def build_sources():
    """
    Phase 3 pipeline:
      1. Parse links.txt -> LegalSource objects
      2. Save to sources.json
      3. Build rights matrix
      4. Save to rights_matrix.json
    """
    from app.rag.sources import SourceRegistry
    from app.rag.matrix import RightsMatrix

    print("=" * 60)
    print("  WorkerSaathi Knowledge Pipeline")
    print("=" * 60)

    # Step 1: Parse links.txt
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

    # Step 2: Save sources.json
    print(f"\n[2/4] Generating sources.json...")
    registry.save_to_json(str(SOURCES_FILE))
    print(f"      Saved to: {SOURCES_FILE}")

    # Step 3: Build rights matrix
    print(f"\n[3/4] Building rights matrix...")
    matrix = RightsMatrix(registry)
    matrix.build_from_registry(registry)

    stats = matrix.get_matrix_stats()
    print(f"      Matrix entries: {stats['total_entries']}")
    print(f"      Unique sources: {stats['unique_sources']}")

    # Step 4: Save rights_matrix.json
    print(f"\n[4/4] Generating rights_matrix.json...")
    matrix.save_to_json(str(MATRIX_FILE))
    print(f"      Saved to: {MATRIX_FILE}")

    print("\n" + "=" * 60)
    print("  Phase 3 pipeline complete!")
    print("=" * 60)

    # Quick validation
    _run_source_tests(registry)


def build_index():
    """
    Phase 4 pipeline:
      1. Load research package
      2. Create RAG documents
      3. Chunk documents
      4. Generate embeddings
      5. Store in Qdrant
    """
    from app.rag.loader import ResearchLoader
    from app.rag.chunker import chunk_documents
    from app.rag.embeddings import EmbeddingClient
    from app.rag.qdrant_store import QdrantStore

    print("\n" + "=" * 60)
    print("  Phase 4 - Building RAG Index")
    print("=" * 60)

    if not RESEARCH_DIR.exists():
        print(f"[ERROR] Research data not found at: {RESEARCH_DIR}")
        return

    # Step 1: Load research package
    print("\n[1/5] Loading research package...")
    loader = ResearchLoader(str(RESEARCH_DIR))
    loader.load()

    # Step 2: Create RAG documents
    print("\n[2/5] Creating RAG documents...")
    docs = loader.to_rag_documents()

    # Step 3: Chunk documents
    print("\n[3/5] Chunking documents...")
    chunks = chunk_documents(docs)

    # Step 4: Generate embeddings
    print("\n[4/5] Generating embeddings (Qwen3-Embedding-8B)...")
    embedder = EmbeddingClient()
    texts = [c.text for c in chunks]

    print(f"      Embedding {len(texts)} chunks...")
    vectors = embedder.embed_texts(texts)
    print(f"      Generated {len(vectors)} vectors (dim={len(vectors[0]) if vectors else '?'})")

    # Step 5: Store in Qdrant
    print("\n[5/5] Storing in Qdrant...")
    qdrant = QdrantStore(path=str(QDRANT_PATH))
    dimension = len(vectors[0]) if vectors else 4096
    qdrant.create_collection(dimension)
    qdrant.upsert_documents(chunks, vectors)

    print(f"      Documents in Qdrant: {qdrant.count()}")

    # Save metadata for later use
    _save_index_metadata(chunks, loader)

    print("\n" + "=" * 60)
    print("  Phase 4 indexing complete!")
    print("=" * 60)


def run_retrieval_tests():
    """Run Phase 5 retrieval test cases — expanded test matrix."""
    from app.rag.loader import ResearchLoader
    from app.rag.chunker import chunk_documents
    from app.rag.embeddings import EmbeddingClient
    from app.rag.qdrant_store import QdrantStore
    from app.rag.retriever import HybridRetriever
    from app.rag.models import RetrievalCoverage

    print("\n" + "=" * 60)
    print("  Phase 5 - RAG Retrieval & Evidence Tests")
    print("=" * 60)

    # Load everything
    print("\n  Loading index...")
    loader = ResearchLoader(str(RESEARCH_DIR))
    loader.load()
    docs = loader.to_rag_documents()
    chunks = chunk_documents(docs)

    embedder = EmbeddingClient()
    qdrant = QdrantStore(path=str(QDRANT_PATH))

    retriever = HybridRetriever(
        qdrant=qdrant,
        embedder=embedder,
        documents=chunks,
        gaps=loader.gaps,
        conflicts=loader.conflicts,
    )

    # ── Phase 5 Test Matrix ──────────────────────────────────────
    tests = [
        # Gig worker tests
        {
            "name": "1. Gig worker unpaid wages",
            "params": {"worker_type": "gig_worker", "issue": "unpaid_wages",
                       "query": "salary not paid by platform"},
            "expect_topic": "wages",
        },
        {
            "name": "2. Gig worker deactivation (gap)",
            "params": {"worker_type": "gig_worker", "issue": "platform_deactivation"},
            "expect_gap": True,
        },
        {
            "name": "3. Gig worker social security",
            "params": {"worker_type": "gig_worker", "issue": "social_security"},
            "expect_topic": "gig",
        },
        # Construction worker tests
        {
            "name": "4. Construction worker injury",
            "params": {"worker_type": "construction_worker", "issue": "workplace_injury",
                       "query": "construction site injury accident"},
            "expect_topic": "accident",
        },
        {
            "name": "5. Construction worker unpaid wages",
            "params": {"worker_type": "construction_worker", "issue": "unpaid_wages"},
            "expect_topic": "wages",
        },
        # Unknown worker tests
        {
            "name": "6. Unknown worker unpaid wages",
            "params": {"worker_type": "unknown", "issue": "unpaid_wages",
                       "query": "meri salary nahi mili"},
            "expect_topic": "wages",
            "expect_worker_limitation": True,
        },
        {
            "name": "7. Unknown worker injury",
            "params": {"worker_type": "unknown", "issue": "workplace_injury"},
            "expect_topic": "safety",
        },
        # Special tests
        {
            "name": "8. Legal aid (NALSA data gap)",
            "params": {"query": "free legal aid help", "issue": "legal_aid"},
            "expect_data_gap": True,
        },
        {
            "name": "9. State-specific query (Karnataka)",
            "params": {"worker_type": "gig_worker", "state": "Karnataka",
                       "issue": "platform_deactivation"},
            "expect_limitation": True,
        },
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        print(f"\n  {test['name']}")
        result = retriever.retrieve(**test["params"])

        print(f"    Coverage: {result.coverage.value}")

        if result.evidence:
            for e in result.evidence[:2]:
                score = f"{e.retrieval_score:.4f}"
                print(f"    -> [{e.evidence_level}] {e.source_title} "
                      f"(score={score})")

        if result.gaps:
            print(f"    Gaps: {len(result.gaps)}")
            for g in result.gaps[:1]:
                print(f"    -> {g[:80]}...")

        if result.conflicts:
            print(f"    Conflicts: {len(result.conflicts)}")

        if result.limitations:
            for lim in result.limitations[:2]:
                if "state" in lim.lower() or "unknown" in lim.lower() or "worker type" in lim.lower():
                    print(f"    Limitation: {lim[:80]}...")

        # ── Check expectations ───────────────────────────────────
        ok = True

        if "expect_topic" in test:
            topic = test["expect_topic"].lower()
            topic_found = any(
                topic in (e.source_title.lower() + e.evidence_text.lower())
                for e in result.evidence
            )
            if not topic_found:
                ok = False

        if "expect_gap" in test:
            gap_found = (
                result.coverage in (RetrievalCoverage.GAP, RetrievalCoverage.PARTIAL)
                or bool(result.gaps)
            )
            if not gap_found:
                ok = False

        if "expect_data_gap" in test:
            is_data_gap = (
                result.coverage in (RetrievalCoverage.NONE, RetrievalCoverage.GAP)
                or not result.evidence
            )
            if not is_data_gap:
                ok = False

        if "expect_limitation" in test:
            has_lim = any(
                "state" in lim.lower() or "State" in lim
                for lim in result.limitations
            )
            if not has_lim:
                ok = False

        if "expect_worker_limitation" in test:
            has_worker_lim = any(
                "worker type" in lim.lower() or "classification" in lim.lower()
                for lim in result.limitations
            )
            if not has_worker_lim:
                ok = False

        status = "PASS" if ok else "PARTIAL"
        if ok:
            passed += 1
        print(f"    Result: {status}")

    # ── Summary ──────────────────────────────────────────────────
    print(f"\n  Results: {passed}/{total} passed")
    pct = (passed / total * 100) if total else 0
    print(f"  Score: {pct:.0f}%")
    print("=" * 60)

    # Print prompt context for test 1 as a demo
    print("\n  [DEMO] LegalEvidence prompt context for test 1:")
    demo = retriever.retrieve(
        worker_type="gig_worker", issue="unpaid_wages",
        query="salary not paid by platform"
    )
    print(demo.to_prompt_context())
    print("=" * 60)


def _run_source_tests(registry):
    """Run Phase 3 source validation tests."""
    from app.rag.models import SourceStatus

    results_a = registry.query("gig_worker", "Karnataka", "platform_deactivation")
    karnataka_law = any("Karnataka" in s.title and s.source_type.value == "law" for s in results_a)
    status_a = "PASS" if karnataka_law else "PARTIAL"
    print(f"  Test A (gig + Karnataka + deactivation): {status_a}")
    for s in results_a[:3]:
        print(f"         -> {s.title} [{s.source_type.value}]")

    results_b = registry.query("domestic_worker", "Tamil Nadu", "welfare")
    tn_found = any("Tamil Nadu" in s.title for s in results_b)
    print(f"  Test B (domestic + TN + welfare): {'PASS' if tn_found else 'FAIL'}")
    for s in results_b[:3]:
        print(f"         -> {s.title} [{s.source_type.value}]")

    results_c = registry.query("construction_worker", None, "workplace_injury")
    central_found = any(s.jurisdiction.value == "central" for s in results_c)
    print(f"  Test C (construction + Central + injury): {'PASS' if central_found else 'FAIL'}")

    disabled = [s for s in registry.sources if s.status in (SourceStatus.DISABLED, SourceStatus.SUPERSEDED)]
    if disabled:
        test_d = registry.query("gig_worker", None, "all")
        none_disabled = not any(s.status in (SourceStatus.DISABLED, SourceStatus.SUPERSEDED) for s in test_d)
        print(f"  Test D (disabled excluded): {'PASS' if none_disabled else 'FAIL'}")
    else:
        print(f"  Test D (disabled excluded): PASS (none to test)")

    all_meta = all(s.source_url and s.authority and s.last_verified for s in registry.sources)
    print(f"  Test E (metadata complete): {'PASS' if all_meta else 'FAIL'}")


def _save_index_metadata(chunks, loader):
    """Save index metadata for debugging/inspection."""
    import json

    meta_dir = QDRANT_PATH / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "total_chunks": len(chunks),
        "total_gaps": len(loader.gaps),
        "total_conflicts": len(loader.conflicts),
        "total_sources": len(loader.source_registry),
        "topics": sorted(set(c.topic for c in chunks if c.topic)),
        "worker_types": sorted(set(
            wt for c in chunks for wt in c.worker_types
        )),
        "issue_categories": sorted(set(
            ic for c in chunks for ic in c.issue_categories
        )),
    }

    with open(meta_dir / "index_info.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--test" in args:
        run_retrieval_tests()
    elif "--index" in args:
        build_sources()
        build_index()
    else:
        build_sources()
