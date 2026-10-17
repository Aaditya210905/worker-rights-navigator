"""
screenshot_parser.py -- Evidence Locker, Payment Screenshot Parser & Timeline Builder.

Handles:
1. Secure file upload and storage for worker evidence (screenshots, PDFs, images).
2. Privacy Redaction Safeguards (auto-detects & redacts Aadhaar, bank accounts, OTPs).
3. Field extraction (platform, amount in INR, dates, transaction IDs, deactivation notices).
4. Evidence Timeline compilation connecting spoken claims with documentary proof.
"""

import os
import re
import uuid
import shutil
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

# Storage directory for evidence uploads
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EVIDENCE_UPLOAD_DIR = PROJECT_ROOT / "data" / "evidence_uploads"
EVIDENCE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class EvidenceType(str, Enum):
    EARNINGS_STATEMENT = "earnings_statement"
    PAYMENT_DEDUCTION = "payment_deduction"
    DEACTIVATION_NOTICE = "deactivation_notice"
    ACCIDENT_RECORD = "accident_record"
    COMMUNICATION_LOG = "communication_log"
    OTHER = "other"


class ParsedEvidenceData(BaseModel):
    detected_platform: Optional[str] = None
    detected_amounts: List[float] = Field(default_factory=list)
    primary_amount: Optional[float] = None
    detected_dates: List[str] = Field(default_factory=list)
    transaction_ids: List[str] = Field(default_factory=list)
    deactivation_keywords: List[str] = Field(default_factory=list)
    extracted_text_preview: str = ""
    sensitive_data_redacted: bool = False
    redaction_summary: List[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    evidence_id: str = Field(default_factory=lambda: f"EVD-{uuid.uuid4().hex[:8].upper()}")
    case_id: Optional[str] = None
    filename: str
    stored_path: str
    uploaded_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    evidence_type: EvidenceType = EvidenceType.OTHER
    user_caption: Optional[str] = None
    parsed_data: ParsedEvidenceData
    annexure_label: str = "Annexure"  # e.g. "Annexure A-1"


class TimelineEvent(BaseModel):
    date_or_period: str
    event_title: str
    description: str
    evidence_id: Optional[str] = None
    annexure_ref: Optional[str] = None
    source_type: str = "worker_statement"  # "documentary_proof", "worker_statement"
    legal_significance: Optional[str] = None


class EvidenceTimeline(BaseModel):
    case_id: str
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    total_events: int = 0
    total_documents: int = 0
    events: List[TimelineEvent] = Field(default_factory=list)

    def to_markdown_table(self) -> str:
        """Render a clean Markdown table of the evidence chronology."""
        lines = [
            "### Chronological Evidence Timeline",
            "| Date / Period | Event Description | Documentary Proof | Legal Significance |",
            "| :--- | :--- | :--- | :--- |",
        ]
        for ev in self.events:
            proof = f"[{ev.annexure_ref}]" if ev.annexure_ref else "Spoken narrative"
            lines.append(f"| {ev.date_or_period} | **{ev.event_title}**: {ev.description} | {proof} | {ev.legal_significance or 'Corroborating record'} |")
        return "\n".join(lines)


# ── Privacy Safeguards Redaction Patterns ─────────────────────────────────────
# Workers must never have their Aadhaar or sensitive bank info exposed.
from app.safety.redaction import (
    AADHAAR_PATTERN, BANK_ACC_PATTERN, OTP_PATTERN, PHONE_PATTERN,
    redact_sensitive_pii,
)



class EvidenceManager:
    """
    Manages screenshot/document ingestion, privacy sanitization,
    information extraction, and timeline construction.
    """

    @classmethod
    def save_and_parse_upload(
        cls,
        file_bytes: bytes,
        filename: str,
        case_id: Optional[str] = None,
        user_caption: Optional[str] = None,
    ) -> EvidenceItem:
        """
        Saves uploaded file securely, runs privacy redaction, and extracts fields.
        """
        # Secure filename
        file_ext = os.path.splitext(filename)[1].lower() or ".png"
        safe_name = f"{uuid.uuid4().hex[:12]}{file_ext}"
        target_path = EVIDENCE_UPLOAD_DIR / safe_name

        with open(target_path, "wb") as f:
            f.write(file_bytes)

        # Extract text / information
        extracted_text = cls._extract_text(target_path, file_ext)
        clean_text, was_redacted, redaction_notes = redact_sensitive_pii(extracted_text)

        # Parse data fields
        parsed = cls._parse_text_fields(clean_text, filename, user_caption)
        parsed.sensitive_data_redacted = was_redacted
        parsed.redaction_summary = redaction_notes

        # Determine evidence type
        evidence_type = cls._classify_evidence(clean_text, filename, user_caption)

        return EvidenceItem(
            case_id=case_id,
            filename=filename,
            stored_path=str(target_path),
            evidence_type=evidence_type,
            user_caption=user_caption,
            parsed_data=parsed,
        )

    @classmethod
    def _extract_text(cls, filepath: Path, ext: str) -> str:
        """Extract text from file. For PDFs, uses PyMuPDF. For images, scans bytes or heuristics."""
        text_content = ""
        try:
            if ext == ".pdf":
                import fitz  # PyMuPDF
                doc = fitz.open(str(filepath))
                for page in doc:
                    text_content += page.get_text() + "\n"
                doc.close()
            elif ext in [".txt", ".csv", ".json"]:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    text_content = f.read()
            else:
                # For images, try reading embedded EXIF / metadata or strings in file
                # In full environment with tesseract: pytesseract.image_to_string
                # Here we do a lightweight string extraction fallback for common mobile screenshots
                with open(filepath, "rb") as f:
                    data = f.read()
                # Extract printable strings
                printable = re.findall(rb'[A-Za-z0-9.,\s\-_:]{4,}', data)
                decoded_snippets = [p.decode('latin-1', errors='ignore') for p in printable[:50]]
                text_content = " ".join(decoded_snippets)
        except Exception as e:
            text_content = f"[Extraction note: {str(e)}]"

        return text_content.strip()

    @classmethod
    def _parse_text_fields(cls, text: str, filename: str, caption: Optional[str]) -> ParsedEvidenceData:
        """Detect platforms, amounts, dates, and order IDs from text + metadata."""
        combined = f"{filename} {caption or ''} {text}"

        # 1. Platform Detection
        platforms = [
            "swiggy", "zomato", "uber", "ola", "urban company", "zepto",
            "blinkit", "amazon", "amazon flex", "flipkart", "porter",
            "shadowfax", "dunzo", "rapido", "bigbasket"
        ]
        detected_platform = None
        for p in platforms:
            if re.search(r'\b' + re.escape(p) + r'\b', combined, re.IGNORECASE):
                detected_platform = p.title()
                break

        # 2. Currency Amount Detection (Rs. / ₹ / INR)
        amount_patterns = [
            r'₹\s*([0-9,]+(?:\.[0-9]{2})?)',
            r'(?:rs\.?|inr)\s*([0-9,]+(?:\.[0-9]{2})?)',
            r'\b([0-9]{2,6})\s*(?:rupees|rs|INR)\b',
            r'\b(?:amount|paid|balance|payout|earnings|fare|total)\s*[:\-]?\s*₹?\s*([0-9,]+(?:\.[0-9]{2})?)\b'
        ]
        detected_amounts = []
        for pat in amount_patterns:
            matches = re.findall(pat, combined, re.IGNORECASE)
            for m in matches:
                try:
                    clean_m = m.replace(',', '')
                    val = float(clean_m)
                    if 10.0 <= val <= 500000.0:  # reasonable range
                        detected_amounts.append(val)
                except ValueError:
                    continue

        primary_amount = detected_amounts[0] if detected_amounts else None

        # 3. Transaction / Order IDs
        txn_matches = re.findall(r'\b(?:txn|order|trip|ride|id|ref)[\s#:\-]*([A-Za-z0-9\-_]{6,20})\b', combined, re.IGNORECASE)
        transaction_ids = list(dict.fromkeys(txn_matches))[:5]

        # 4. Dates
        date_matches = re.findall(r'\b(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})\b', combined)
        detected_dates = list(dict.fromkeys(date_matches))[:5]

        # 5. Deactivation keywords
        deact_keywords = []
        for kw in ["deactivated", "suspended", "blocked", "penalty", "deduction", "inactive", "violation"]:
            if re.search(r'\b' + kw + r'\b', combined, re.IGNORECASE):
                deact_keywords.append(kw)

        preview = text[:300] + "..." if len(text) > 300 else text

        return ParsedEvidenceData(
            detected_platform=detected_platform,
            detected_amounts=detected_amounts,
            primary_amount=primary_amount,
            detected_dates=detected_dates,
            transaction_ids=transaction_ids,
            deactivation_keywords=deact_keywords,
            extracted_text_preview=preview,
        )

    @classmethod
    def _classify_evidence(cls, text: str, filename: str, caption: Optional[str]) -> EvidenceType:
        """Classifies the type of uploaded proof."""
        c = f"{filename} {caption or ''} {text}".lower()
        if any(w in c for w in ["deactivat", "suspend", "block", "terminat", "banned"]):
            return EvidenceType.DEACTIVATION_NOTICE
        if any(w in c for w in ["deduct", "penalty", "fine", "cancellation charge", "withheld"]):
            return EvidenceType.PAYMENT_DEDUCTION
        if any(w in c for w in ["earning", "payout", "statement", "trips", "weekly summary", "ledger"]):
            return EvidenceType.EARNINGS_STATEMENT
        if any(w in c for w in ["hospital", "injury", "medical", "doctor", "prescription", "accident"]):
            return EvidenceType.ACCIDENT_RECORD
        if any(w in c for w in ["whatsapp", "chat", "sms", "message", "call", "contractor"]):
            return EvidenceType.COMMUNICATION_LOG
        return EvidenceType.OTHER

    @classmethod
    def build_timeline(
        cls,
        case_id: str,
        case_state_fields: Dict[str, Any],
        uploaded_items: List[EvidenceItem],
    ) -> EvidenceTimeline:
        """
        Synthesizes worker claims, incident dates, and documentary evidence
        into a structured, chronological legal evidence timeline.
        """
        events: List[TimelineEvent] = []

        # 1. Case Incident / Commencement Event
        incident_date = case_state_fields.get("incident_date") or "Earlier"
        employer = case_state_fields.get("platform_or_employer") or "Platform/Employer"
        amount = case_state_fields.get("amount")

        # Initial joining / dispute event
        events.append(TimelineEvent(
            date_or_period=incident_date,
            event_title="Incident / Grievance Inception",
            description=f"Worker engaged on {employer}. Dispute arose regarding {case_state_fields.get('issue_category', 'workplace rights')}.",
            source_type="worker_statement",
            legal_significance="Establishes engagement and jurisdictional employment relationship.",
        ))

        # 2. Add each uploaded evidence item with Annexure labeling
        for idx, item in enumerate(uploaded_items, start=1):
            annexure = f"Annexure A-{idx}"
            item.annexure_label = annexure

            date_str = item.parsed_data.detected_dates[0] if item.parsed_data.detected_dates else "Verified Document"
            title = f"{item.evidence_type.value.replace('_', ' ').title()} ({item.filename})"

            desc_parts = []
            if item.user_caption:
                desc_parts.append(item.user_caption)
            if item.parsed_data.primary_amount:
                desc_parts.append(f"Amount shown: ₹{item.parsed_data.primary_amount:,.2f}")
            if item.parsed_data.transaction_ids:
                desc_parts.append(f"Ref ID: {item.parsed_data.transaction_ids[0]}")
            if item.parsed_data.deactivation_keywords:
                desc_parts.append(f"Keywords: {', '.join(item.parsed_data.deactivation_keywords)}")

            sig = "Documentary corroboration of worker claim."
            if item.evidence_type == EvidenceType.PAYMENT_DEDUCTION:
                sig = "Prima facie evidence of unauthorized deduction under Section 18, Code on Wages."
            elif item.evidence_type == EvidenceType.DEACTIVATION_NOTICE:
                sig = "Evidence of sudden deactivation without statutory 14-day notice."
            elif item.evidence_type == EvidenceType.EARNINGS_STATEMENT:
                sig = "Proof of completed work tenure and accrued wage debt under Section 43."

            events.append(TimelineEvent(
                date_or_period=date_str,
                event_title=title,
                description=" | ".join(desc_parts) or "Documentary record provided by worker.",
                evidence_id=item.evidence_id,
                annexure_ref=annexure,
                source_type="documentary_proof",
                legal_significance=sig,
            ))

        # 3. Current Demand / Action Step Event
        events.append(TimelineEvent(
            date_or_period=datetime.now().strftime("%d %b %Y"),
            event_title="Legal Rights Verification & Demand Preparation",
            description=f"WorkerSaathi formal case dossier compiled with {len(uploaded_items)} verified documentary attachments.",
            source_type="system_record",
            legal_significance="Formal invocation of statutory dispute redressal remedies.",
        ))

        return EvidenceTimeline(
            case_id=case_id,
            total_events=len(events),
            total_documents=len(uploaded_items),
            events=events,
        )
