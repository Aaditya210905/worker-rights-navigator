"""
Pre-embed all knowledge (JSON + PDF) into Qdrant.

Supports RESUME — saves progress after each batch so if the API
fails mid-way, re-running picks up where it left off.

Usage:
    python -m scripts.embed          # normal run (resumes if possible)
    python -m scripts.embed --fresh  # force re-embed everything
"""

import json
import sys
import time
from pathlib import Path

CHECKPOINT_FILE = Path(__file__).resolve().parent.parent / "data" / "embed_checkpoint.json"
BATCH_SIZE = 16

print("=" * 60)
print("  WorkerSaathi — Knowledge Embedding")
print("=" * 60)

force_fresh = "--fresh" in sys.argv

# ── Load checkpoint ──────────────────────────────────────────────────────────

checkpoint = {"completed_batches": 0, "vectors": [], "total_chunks": 0}

if CHECKPOINT_FILE.exists() and not force_fresh:
    try:
        with open(CHECKPOINT_FILE, "r") as f:
            checkpoint = json.load(f)
        print(f"\n  Resuming from batch {checkpoint['completed_batches']} "
              f"({len(checkpoint['vectors'])} vectors already done)")
    except Exception:
        checkpoint = {"completed_batches": 0, "vectors": [], "total_chunks": 0}


def save_checkpoint():
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(checkpoint, f)


# ── Step 1: Load documents ───────────────────────────────────────────────────

start = time.time()

print("\n[1/5] Loading JSON knowledge...")
from app.rag.loader import ResearchLoader
project_root = Path(__file__).resolve().parent.parent
research_dir = project_root / "knowledge" / "workersaathi" / "json"
loader = ResearchLoader(str(research_dir))
loader.load()
json_docs = loader.to_rag_documents()

print("\n[2/5] Loading PDF documents...")
from app.rag.pdf_loader import PDFLoader
pdf_dir = project_root / "knowledge" / "workersaathi" / "pdfs"
pdf_loader = PDFLoader(str(pdf_dir))
pdf_docs = pdf_loader.load()

all_docs = json_docs + pdf_docs
print(f"\n  Total: {len(all_docs)} documents (JSON: {len(json_docs)}, PDF: {len(pdf_docs)})")

# ── Step 2: Chunk ────────────────────────────────────────────────────────────

print("\n[3/5] Chunking documents...")
from app.rag.chunker import chunk_documents
chunks = chunk_documents(all_docs)

# Check if chunks changed since last run
if checkpoint["total_chunks"] != len(chunks) and checkpoint["completed_batches"] > 0:
    print(f"  ⚠ Chunk count changed ({checkpoint['total_chunks']} → {len(chunks)}). Starting fresh.")
    checkpoint = {"completed_batches": 0, "vectors": [], "total_chunks": 0}

checkpoint["total_chunks"] = len(chunks)

# ── Step 3: Embed (with resume) ──────────────────────────────────────────────

total_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE
start_batch = checkpoint["completed_batches"]

if start_batch >= total_batches:
    print(f"\n[4/5] All {len(chunks)} chunks already embedded! Skipping.")
    vectors = checkpoint["vectors"]
else:
    print(f"\n[4/5] Embedding chunks (batch {start_batch + 1}/{total_batches})...")
    from app.rag.embeddings import EmbeddingClient
    embedder = EmbeddingClient()

    texts = [doc.text for doc in chunks]
    vectors = checkpoint["vectors"]  # start with already-done vectors

    for i in range(start_batch * BATCH_SIZE, len(texts), BATCH_SIZE):
        batch_num = i // BATCH_SIZE + 1
        batch = texts[i:i + BATCH_SIZE]

        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} texts)...", end=" ", flush=True)

        try:
            batch_vectors = embedder.embed_texts(batch)
            # Convert numpy arrays to plain lists for JSON serialization
            batch_vectors = [
                v.tolist() if hasattr(v, 'tolist') else list(v)
                for v in batch_vectors
            ]
            vectors.extend(batch_vectors)
            checkpoint["completed_batches"] = batch_num
            checkpoint["vectors"] = vectors
            save_checkpoint()
            print("✓")
        except Exception as e:
            print(f"✗ Error: {e}")
            save_checkpoint()
            print(f"\n  Saved progress at batch {batch_num - 1}/{total_batches}.")
            print(f"  Re-run this script to resume from batch {batch_num}.")
            sys.exit(1)

    print(f"  Embedded {len(vectors)} vectors (dimension: {len(vectors[0])})")

# ── Step 4: Index into Qdrant ────────────────────────────────────────────────

print("\n[5/5] Indexing into Qdrant...")
from app.rag.qdrant_store import QdrantStore
qdrant = QdrantStore(path=str(project_root / "data" / "qdrant"))
qdrant.create_collection(len(vectors[0]))
qdrant.upsert_documents(chunks, vectors)

# Clean up checkpoint file (embedding complete)
if CHECKPOINT_FILE.exists():
    CHECKPOINT_FILE.unlink()
    print("  Checkpoint cleared.")

elapsed = time.time() - start
print(f"\n{'=' * 60}")
print(f"  ✅ Done! {len(chunks)} chunks embedded in {elapsed:.1f}s")
print(f"  Stored in: data/qdrant/")
print(f"{'=' * 60}")
