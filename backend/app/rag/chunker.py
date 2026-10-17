"""
chunker.py -- Legal document chunker.

Splits RAGDocuments into smaller chunks while preserving
legal structure (section, subsection, source metadata).

Knowledge items from the research package are already well-structured
(~584 chars avg), so most become 1 chunk each. Only long items
are split further.
"""

from app.rag.models import RAGDocument


MAX_CHUNK_SIZE = 1200  # chars — keep chunks focused
OVERLAP = 100          # char overlap between chunks


def chunk_documents(docs: list[RAGDocument]) -> list[RAGDocument]:
    """
    Chunk RAG documents. Most items are small enough to be
    one chunk. Long items are split preserving sentence boundaries.
    """
    chunks = []

    for doc in docs:
        text = doc.text.strip()
        if not text:
            continue

        if len(text) <= MAX_CHUNK_SIZE:
            # Small enough — keep as-is
            chunks.append(doc)
        else:
            # Split long text into chunks
            sub_chunks = _split_text(text, MAX_CHUNK_SIZE, OVERLAP)
            for i, chunk_text in enumerate(sub_chunks):
                chunk = doc.model_copy(update={
                    "doc_id": f"{doc.doc_id}_chunk_{i}",
                    "text": chunk_text,
                })
                chunks.append(chunk)

    print(f"  Chunked {len(docs)} documents into {len(chunks)} chunks")
    return chunks


def _split_text(text: str, max_size: int, overlap: int) -> list[str]:
    """Split text at sentence boundaries with overlap."""
    # Split by sentences (period + space or newline)
    sentences = []
    current = ""
    for char in text:
        current += char
        if char in ".;:" and len(current) > 50:
            sentences.append(current.strip())
            current = ""
    if current.strip():
        sentences.append(current.strip())

    # Group sentences into chunks
    chunks = []
    current_chunk = ""
    for sentence in sentences:
        if len(current_chunk) + len(sentence) > max_size and current_chunk:
            chunks.append(current_chunk.strip())
            # Keep overlap from end of previous chunk
            words = current_chunk.split()
            overlap_words = words[-min(len(words), overlap // 5):]
            current_chunk = " ".join(overlap_words) + " " + sentence
        else:
            current_chunk += " " + sentence if current_chunk else sentence

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks if chunks else [text]
