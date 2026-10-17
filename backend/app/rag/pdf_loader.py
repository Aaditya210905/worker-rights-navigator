"""
pdf_loader.py -- Extract text from PDF files and convert to RAGDocument objects.

Loads legal PDFs from knowledge/workersaathi/pdfs/ and creates
RAGDocument objects that can be fed into the same chunking + embedding
pipeline used by the JSON-based loader.

Handles:
  - Multi-page PDF text extraction
  - Hindi + English mixed-language documents
  - Metadata inference from filename
  - Page-level chunking for large documents
"""

import re
from pathlib import Path
from typing import Optional

from app.rag.models import RAGDocument, EvidenceLevel


# ── Filename → metadata mapping ─────────────────────────────────────────────
# Maps PDF filenames to structured metadata so the RAG pipeline knows
# what kind of document it's dealing with.

PDF_METADATA = {
    "wages_central_rules_2026.pdf": {
        "title": "Code on Wages (Central) Rules, 2026",
        "authority": "Ministry of Labour and Employment",
        "source_type": "rules",
        "evidence_level": EvidenceLevel.PRIMARY_LEGAL.value,
        "topic": "wages",
        "worker_types": ["all_workers"],
        "issue_categories": ["unpaid_wages"],
    },
    "wages_commencement_so5322.pdf": {
        "title": "Code on Wages Commencement Notification SO 5322",
        "authority": "Ministry of Labour and Employment",
        "source_type": "notification",
        "evidence_level": EvidenceLevel.PRIMARY_LEGAL.value,
        "topic": "wages",
        "worker_types": ["all_workers"],
        "issue_categories": ["unpaid_wages"],
    },
    "osh_central_rules_2026.pdf": {
        "title": "Occupational Safety, Health and Working Conditions (Central) Rules, 2026",
        "authority": "Ministry of Labour and Employment",
        "source_type": "rules",
        "evidence_level": EvidenceLevel.PRIMARY_LEGAL.value,
        "topic": "workplace_safety",
        "worker_types": ["construction_worker", "all_workers"],
        "issue_categories": ["workplace_injury"],
    },
    "ss_central_rules_2026.pdf": {
        "title": "Code on Social Security (Central) Rules, 2026",
        "authority": "Ministry of Labour and Employment",
        "source_type": "rules",
        "evidence_level": EvidenceLevel.PRIMARY_LEGAL.value,
        "topic": "social_security",
        "worker_types": ["gig_worker", "all_workers"],
        "issue_categories": ["all"],
    },
    "ss_commencement_so5319.pdf": {
        "title": "Social Security Code Commencement Notification SO 5319",
        "authority": "Ministry of Labour and Employment",
        "source_type": "notification",
        "evidence_level": EvidenceLevel.PRIMARY_LEGAL.value,
        "topic": "social_security",
        "worker_types": ["gig_worker", "all_workers"],
        "issue_categories": ["all"],
    },
    "ir_code_2020.pdf": {
        "title": "Industrial Relations Code, 2020",
        "authority": "Ministry of Labour and Employment",
        "source_type": "law",
        "evidence_level": EvidenceLevel.PRIMARY_LEGAL.value,
        "topic": "industrial_relations",
        "worker_types": ["all_workers"],
        "issue_categories": ["all"],
    },
    "ir_central_rules_2026.pdf": {
        "title": "Industrial Relations (Central) Rules, 2026",
        "authority": "Ministry of Labour and Employment",
        "source_type": "rules",
        "evidence_level": EvidenceLevel.PRIMARY_LEGAL.value,
        "topic": "industrial_relations",
        "worker_types": ["all_workers"],
        "issue_categories": ["all"],
    },
    "additional_faqs_labour_codes_20260316.pdf": {
        "title": "FAQs on Labour Codes Implementation",
        "authority": "Ministry of Labour and Employment",
        "source_type": "faq",
        "evidence_level": EvidenceLevel.OFFICIAL_EXPLANATORY.value,
        "topic": "labour_codes",
        "worker_types": ["all_workers"],
        "issue_categories": ["all"],
    },
    "mole_explainer.pdf": {
        "title": "Ministry of Labour - Labour Codes Explainer",
        "authority": "Ministry of Labour and Employment",
        "source_type": "government_guidance",
        "evidence_level": EvidenceLevel.OFFICIAL_EXPLANATORY.value,
        "topic": "labour_codes",
        "worker_types": ["all_workers"],
        "issue_categories": ["all"],
    },
    "mole_annual_report.pdf": {
        "title": "Ministry of Labour and Employment Annual Report",
        "authority": "Ministry of Labour and Employment",
        "source_type": "government_guidance",
        "evidence_level": EvidenceLevel.OFFICIAL_EXPLANATORY.value,
        "topic": "labour_overview",
        "worker_types": ["all_workers"],
        "issue_categories": ["all"],
        "max_pages": 30,  # Annual report is 200+ pages, mostly statistics
    },
    "pib_gig_dec2025.pdf": {
        "title": "PIB Press Release - Gig Workers December 2025",
        "authority": "Press Information Bureau",
        "source_type": "government_guidance",
        "evidence_level": EvidenceLevel.OFFICIAL_EXPLANATORY.value,
        "topic": "gig_workers",
        "worker_types": ["gig_worker"],
        "issue_categories": ["all"],
    },
}


# ── Default metadata for unrecognized PDFs ───────────────────────────────────

DEFAULT_META = {
    "title": "",
    "authority": "Government of India",
    "source_type": "other",
    "evidence_level": EvidenceLevel.SECONDARY.value,
    "topic": "",
    "worker_types": ["all_workers"],
    "issue_categories": ["all"],
}


# ── Maximum pages to extract per PDF (to avoid giant annual reports) ─────────
MAX_PAGES_PER_PDF = 100

# ── Minimum text length per page to include (filters blank/image pages) ──────
MIN_PAGE_TEXT_LENGTH = 50

# ── Maximum characters per page chunk (split long pages) ─────────────────────
MAX_CHUNK_CHARS = 2000


class PDFLoader:
    """
    Loads PDF files from a directory and converts them to RAGDocument objects.

    Usage:
        loader = PDFLoader("knowledge/workersaathi/pdfs")
        docs = loader.load()
        # docs is a list of RAGDocument objects ready for chunking
    """

    def __init__(self, pdf_dir: str):
        self._dir = Path(pdf_dir)
        self._documents: list[RAGDocument] = []

    def load(self) -> list[RAGDocument]:
        """Load all PDFs from the directory and return RAGDocument objects."""
        if not self._dir.exists():
            print(f"  [pdf] Directory not found: {self._dir}")
            return []

        pdf_files = sorted(self._dir.glob("*.pdf"))
        if not pdf_files:
            print(f"  [pdf] No PDF files found in {self._dir}")
            return []

        print(f"  [pdf] Found {len(pdf_files)} PDF files")

        try:
            import pymupdf as fitz
        except ImportError:
            try:
                import fitz  # fallback for older versions
            except ImportError:
                print("  [pdf] pymupdf not installed. Run: pip install pymupdf")
                return []

        for pdf_path in pdf_files:
            try:
                docs = self._process_pdf(pdf_path, fitz)
                self._documents.extend(docs)
            except Exception as e:
                print(f"  [pdf] Error processing {pdf_path.name}: {e}")

        print(f"  [pdf] Extracted {len(self._documents)} documents from PDFs")
        return self._documents

    def _process_pdf(self, pdf_path: Path, fitz) -> list[RAGDocument]:
        """Extract text from a single PDF and create RAGDocument objects."""
        filename = pdf_path.name
        meta = PDF_METADATA.get(filename, {**DEFAULT_META, "title": filename})

        doc = fitz.open(str(pdf_path))
        # Use per-PDF max_pages if specified, otherwise global limit
        page_limit = meta.get("max_pages", MAX_PAGES_PER_PDF)
        total_pages = min(len(doc), page_limit)
        documents = []
        page_batch = []  # accumulate pages into larger chunks

        for page_num in range(total_pages):
            page = doc[page_num]
            text = page.get_text("text").strip()

            # Skip blank / image-only pages
            if len(text) < MIN_PAGE_TEXT_LENGTH:
                continue

            # Clean up the text
            text = self._clean_text(text)
            page_batch.append(text)

            # Create a document every few pages or at end
            batch_text = "\n\n".join(page_batch)
            if len(batch_text) >= MAX_CHUNK_CHARS or page_num == total_pages - 1:
                if batch_text.strip():
                    rag_doc = RAGDocument(
                        doc_id=f"pdf_{filename}_{len(documents)}",
                        text=batch_text,
                        source_id=f"pdf_{filename.replace('.pdf', '')}",
                        title=meta["title"],
                        authority=meta["authority"],
                        jurisdiction="central",
                        source_type=meta["source_type"],
                        evidence_level=meta["evidence_level"],
                        worker_types=meta["worker_types"],
                        issue_categories=meta["issue_categories"],
                        topic=meta["topic"],
                        legal_status="active",
                        notes=f"Extracted from {filename}, pages {page_num - len(page_batch) + 2}-{page_num + 1}",
                    )
                    documents.append(rag_doc)
                page_batch = []

        doc.close()

        if documents:
            print(f"  [pdf] {filename}: {len(documents)} chunks from {total_pages} pages")

        return documents

    def _clean_text(self, text: str) -> str:
        """Clean extracted PDF text."""
        # Remove excessive whitespace but preserve paragraph breaks
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Remove page numbers (standalone numbers)
        text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)
        # Remove excessive spaces
        text = re.sub(r' {3,}', ' ', text)
        # Remove header/footer artifacts (common in govt PDFs)
        text = re.sub(r'(?i)^(the gazette of india|extraordinary|part ii)', '', text, flags=re.MULTILINE)
        return text.strip()
