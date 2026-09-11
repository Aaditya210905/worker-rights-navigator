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
    """Run Phase 4 retrieval test cases."""
    import json
    from app.rag.loader import ResearchLoader
    from app.rag.chunker import chunk_documents
    from app.rag.embeddings import EmbeddingClient
    from app.rag.qdrant_store import QdrantStore
    from app.rag.retriever import HybridRetriever
    from app.rag.models import RetrievalCoverage

    print("\n" + "=" * 60)
    print("  Phase 4 - RAG Retrieval Tests")
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

    # Test cases
    tests = [
        {
            "name": "Test 1: Unpaid wages",
            "params": {"query": "employer not paid salary wages", "issue": "unpaid_wages"},
            "expect_topic": "wages",
        },
        {
            "name": "Test 2: Gig worker social security",
            "params": {"worker_type": "gig_worker", "issue": "social_security"},
            "expect_topic": "gig",
        },
        {
            "name": "Test 3: Construction worker safety",
            "params": {"worker_type": "construction_worker", "issue": "workplace_safety"},
            "expect_topic": "construction",
        },
        {
            "name": "Test 4: Gig account deactivated (gap)",
            "params": {"worker_type": "gig_worker", "issue": "platform_deactivation"},
            "expect_gap": True,
        },
        {
            "name": "Test 5: Legal aid (data gap — NALSA has no content in KB)",
            "params": {"query": "free legal aid help", "issue": "legal_aid"},
            "expect_data_gap": True,
        },
        {
            "name": "Test 6: Karnataka state query",
            "params": {"worker_type": "gig_worker", "state": "Karnataka", "issue": "platform_deactivation"},
            "expect_limitation": True,
        },
    ]

    passed = 0
    for test in tests:
        print(f"\n  {test['name']}")
        result = retriever.retrieve(**test["params"])

        print(f"    Coverage: {result.coverage.value}")

        if result.evidence:
            for e in result.evidence[:2]:
                score_str = f"{e.retrieval_score:.4f}"
                print(f"    -> {e.source_title} [{e.evidence_level}] score={score_str}")

        if result.gaps:
            print(f"    Gaps: {len(result.gaps)}")
            for g in result.gaps[:1]:
                print(f"    -> {g[:80]}...")

        if result.conflicts:
            print(f"    Conflicts: {len(result.conflicts)}")

        # Check expectations
        if "expect_topic" in test:
            topic_found = any(
                test["expect_topic"].lower() in (e.source_title.lower() + e.evidence_text.lower())
                for e in result.evidence
            )
            status = "PASS" if topic_found else "PARTIAL"
            if topic_found:
                passed += 1
            print(f"    Result: {status}")

        elif "expect_gap" in test:
            gap_found = result.coverage in (RetrievalCoverage.GAP, RetrievalCoverage.PARTIAL)
            status = "PASS" if gap_found or result.gaps else "PARTIAL"
            if gap_found or result.gaps:
                passed += 1
            print(f"    Result: {status}")

        elif "expect_data_gap" in test:
            # Data gap — system should correctly return no/minimal results
            is_gap = result.coverage in (
                RetrievalCoverage.NONE, RetrievalCoverage.GAP
            ) or not result.evidence
            status = "PASS (correctly identified no data)" if is_gap else "PARTIAL"
            if is_gap:
                passed += 1
            print(f"    Result: {status}")

        elif "expect_limitation" in test:
            has_limitation = any("State" in lim or "state" in lim for lim in result.limitations)
            status = "PASS" if has_limitation else "PARTIAL"
            if has_limitation:
                passed += 1
            print(f"    Result: {status}")

    print(f"\n  Results: {passed}/{len(tests)} passed")
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
