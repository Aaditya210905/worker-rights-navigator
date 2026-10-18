"""
complaint_generator.py -- Formal Legal Complaint Draft & Dispute Notice Generator.

Generates statutory complaint petitions and formal demand notices for:
1. Aggregator Grievance Redressal Officer (Internal Dispute Resolution under Central/State Gig Acts).
2. Office of the Assistant Labour Commissioner / Conciliation Officer (Samadhan Portal / Code on Wages).
3. District Legal Services Authority (DLSA) (Free Legal Representation under LSA Act, 1987).
4. State Gig & Platform Workers Welfare Board (Rajasthan / Karnataka / Tamil Nadu / Telangana).

Available in English and Hindi with full statutory citations and Annexures table.
Supports PDF generation via fpdf2 (pure Python, no external dependencies).
"""

import re
import html
import base64
from enum import Enum
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.case.models import CaseState, WorkerType, IndianState, IssueCategory
from app.evidence.eligibility import EligibilityReport
from app.evidence.wage_calculator import WageCalculationResult
from app.evidence.screenshot_parser import EvidenceTimeline, EvidenceItem

# Optional fpdf2 import for PDF generation (pure Python, no external deps)
try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False
    FPDF = None


class ComplaintAuthority(str, Enum):
    AGGREGATOR_GRIEVANCE_OFFICER = "aggregator_grievance_officer"
    LABOUR_COMMISSIONER = "labour_commissioner"
    DLSA_LEGAL_AID = "dlsa_legal_aid"
    STATE_WELFARE_BOARD = "state_welfare_board"


class ComplaintLanguage(str, Enum):
    ENGLISH = "en"
    HINDI = "hi"


class GeneratedDocument(BaseModel):
    document_id: str
    case_id: str
    authority_type: ComplaintAuthority
    authority_name: str
    language: ComplaintLanguage
    title: str
    date: str
    subject_line: str
    body_markdown: str
    body_html: str
    body_pdf_base64: Optional[str] = None  # Base64-encoded PDF
    prayers_reliefs: List[str]
    annexures: List[Dict[str, str]]
    statutory_citations: List[str]
    destination_office_guidance: str


class ComplaintGenerator:
    """
    Generates formal legal documents customized to the worker's case.
    """

    @classmethod
    def generate(
        cls,
        case: CaseState,
        authority: ComplaintAuthority = ComplaintAuthority.AGGREGATOR_GRIEVANCE_OFFICER,
        language: ComplaintLanguage = ComplaintLanguage.ENGLISH,
        wage_calc: Optional[WageCalculationResult] = None,
        eligibility: Optional[EligibilityReport] = None,
        timeline: Optional[EvidenceTimeline] = None,
        evidence_items: Optional[List[EvidenceItem]] = None,
    ) -> GeneratedDocument:
        """
        Builds a comprehensive, courtroom-ready or grievance-ready complaint document.
        """
        doc_id = f"DOC-{case.case_id}-{authority.value[:3].upper()}-{language.value.upper()}"
        today_str = datetime.now().strftime("%d %B %Y")
        today_hi = datetime.now().strftime("%d/%m/%Y")

        worker_name = "Aggrieved Worker / Delivery Partner"
        platform = case.platform_or_employer or "The Aggregator / Platform Employer"
        state_str = case.state.value if case.state and case.state != IndianState.UNKNOWN else "Applicable State Jurisdiction"

        # Determine authority details
        auth_details = cls._get_authority_details(authority, platform, state_str, language)

        # Build Financial Claim Section
        claim_section = cls._build_claim_section(wage_calc, case, language)

        # Build Evidence Timeline Section
        timeline_section = cls._build_timeline_section(timeline, evidence_items, language)

        # Build Legal Grounds Section
        legal_grounds = cls._build_legal_grounds(case, state_str, language)

        # Build Prayers / Reliefs
        prayers = cls._build_prayers(case, wage_calc, state_str, language)

        # Compile Annexures List
        annexures = []
        if evidence_items:
            for item in evidence_items:
                annexures.append({
                    "label": item.annexure_label,
                    "description": f"{item.filename} ({item.evidence_type.value.replace('_', ' ')})",
                })
        else:
            annexures.append({"label": "Annexure A-1", "description": "Earnings statement & proof of withheld payment"})

        if language == ComplaintLanguage.HINDI:
            doc_title = f"औपचारिक शिकायत पत्र — {auth_details['name']}"
            subject = f"विषय: {platform} द्वारा अवैधानिक वेतन रोके जाने, एकतरफा आईडी बंद करने व क्षतिपूर्ति बाबत (मामला संख्या: {case.case_id})"
            body_md = cls._render_hindi_markdown(
                doc_id=doc_id,
                date_str=today_hi,
                auth_details=auth_details,
                case=case,
                platform=platform,
                state_str=state_str,
                subject=subject,
                timeline_section=timeline_section,
                claim_section=claim_section,
                legal_grounds=legal_grounds,
                prayers=prayers,
                annexures=annexures,
            )
        else:
            doc_title = f"Formal Legal Complaint — {auth_details['name']}"
            subject = f"SUBJECT: FORMAL DISPUTE NOTICE REGARDING UNLAWFUL WITHHOLDING OF WAGES, SUDDEN DEACTIVATION & STATUTORY RELIEF AGAINST {platform.upper()} (CASE REF: {case.case_id})"
            body_md = cls._render_english_markdown(
                doc_id=doc_id,
                date_str=today_str,
                auth_details=auth_details,
                case=case,
                platform=platform,
                state_str=state_str,
                subject=subject,
                timeline_section=timeline_section,
                claim_section=claim_section,
                legal_grounds=legal_grounds,
                prayers=prayers,
                annexures=annexures,
            )

        body_html = cls._convert_md_to_html(body_md)

        # Generate PDF from HTML
        body_pdf_base64 = cls._generate_pdf_from_html(body_html)

        return GeneratedDocument(
            document_id=doc_id,
            case_id=case.case_id,
            authority_type=authority,
            authority_name=auth_details["name"],
            language=language,
            title=doc_title,
            date=today_str if language == ComplaintLanguage.ENGLISH else today_hi,
            subject_line=subject,
            body_markdown=body_md,
            body_html=body_html,
            body_pdf_base64=body_pdf_base64,
            prayers_reliefs=prayers,
            annexures=annexures,
            statutory_citations=legal_grounds["citations"],
            destination_office_guidance=auth_details["filing_guidance"],
        )

    @classmethod
    def _get_authority_details(cls, authority: ComplaintAuthority, platform: str, state: str, lang: ComplaintLanguage) -> Dict[str, str]:
        """Provides addressing and jurisdictional details for selected authority."""
        if authority == ComplaintAuthority.AGGREGATOR_GRIEVANCE_OFFICER:
            return {
                "name": f"Grievance Redressal Officer, {platform}",
                "designation": "Nodal Officer / Grievance Redressal Authority",
                "office": f"Corporate & Operations Headquarters, {platform}",
                "address": "Registered Office / Grievance Portal",
                "filing_guidance": f"Submit this formal notice via the {platform} Partner Help section, registered email, or by Speed Post to their registered corporate office. They are statutorily required to resolve it within 14-21 days.",
            }
        elif authority == ComplaintAuthority.LABOUR_COMMISSIONER:
            return {
                "name": f"Office of the Assistant Labour Commissioner / Conciliation Officer",
                "designation": "The Assistant Labour Commissioner (Central / State)",
                "office": f"Department of Labour, Government of {state}",
                "address": f"District Labour Office, {state} / Samadhan Portal (samadhan.labour.gov.in)",
                "filing_guidance": "File online on the Central Samadhan Portal (samadhan.labour.gov.in) or submit two physical signed copies at your local District Labour Commissioner's office. No court fees are required.",
            }
        elif authority == ComplaintAuthority.DLSA_LEGAL_AID:
            return {
                "name": "District Legal Services Authority (DLSA)",
                "designation": "The Member Secretary, District Legal Services Authority",
                "office": f"District Court Complex, {state}",
                "address": "Front Office, DLSA Legal Aid Clinic",
                "filing_guidance": "Under Section 12(h) of the Legal Services Authorities Act, 1987, informal workers and gig workers are entitled to 100% free legal aid. Visit your nearest District Court complex to be assigned a panel lawyer at zero cost.",
            }
        else:  # STATE_WELFARE_BOARD
            return {
                "name": f"{state} Gig and Platform Workers Welfare Board",
                "designation": "The Chief Executive Officer / Welfare Commissioner",
                "office": f"State Gig Workers Welfare Board, Government of {state}",
                "address": f"Headquarters / Labour Bhawan, {state}",
                "filing_guidance": f"Submit to the State Welfare Board established under the State Gig Workers Act. Aggregators face penalties up to ₹5 Lakhs for non-compliance with Board directives.",
            }

    @classmethod
    def _build_claim_section(cls, wage_calc: Optional[WageCalculationResult], case: CaseState, lang: ComplaintLanguage) -> str:
        """Builds financial claim markdown."""
        if wage_calc:
            return wage_calc.to_annexure_markdown()

        amt = case.amount or "Unspecified"
        if lang == ComplaintLanguage.HINDI:
            return f"**दावा की गई बकाया राशि:** ₹{amt}\n\n*वेतन संहिता, 2019 की धारा 18 व 43 के तहत तुरंत भुगतान योग्य।*"
        return f"**Principal Amount Due:** ₹{amt}\n\n*Payable immediately under Section 18 and Section 43 of the Code on Wages, 2019.*"

    @classmethod
    def _build_timeline_section(cls, timeline: Optional[EvidenceTimeline], items: Optional[List[EvidenceItem]], lang: ComplaintLanguage) -> str:
        """Builds timeline markdown."""
        if timeline:
            return timeline.to_markdown_table()
        if lang == ComplaintLanguage.HINDI:
            return "*शिकायतकर्ता द्वारा दिए गए विवरण के आधार पर साक्ष्य संकलन प्रक्रिया में है।*"
        return "*Evidence chronology compiled from worker statement and verified records.*"

    @classmethod
    def _build_legal_grounds(cls, case: CaseState, state: str, lang: ComplaintLanguage) -> Dict[str, Any]:
        """Compiles statutory legal grounds based on issue category and jurisdiction."""
        citations = [
            "The Code on Wages, 2019 (Act No. 29 of 2019) — Section 18 & Section 45",
            "The Code on Social Security, 2020 (Act No. 36 of 2020) — Section 113 & Section 114",
            "Constitution of India — Article 21 (Right to Livelihood) & Article 23 (Prohibition of Begar / Forced Labour)",
        ]

        if "rajasthan" in state.lower():
            citations.append("The Rajasthan Platform Based Gig Workers (Registration and Welfare) Act, 2023 — Section 11, 12 & 15")
        elif "karnataka" in state.lower():
            citations.append("The Karnataka Platform-based GIG Workers (Social Security and Welfare) Bill, 2024 — Section 10 & 14-day notice requirement")

        grounds_list = [
            "1. **Violation of Statutory Payment Obligations:** Non-payment or delayed disbursement of earned wages violates Section 43 of the Code on Wages, 2019.",
            "2. **Illegal and Arbitrary Deductions:** Unilateral deductions, cancellation penalties, or negative balances imposed without notice or fair hearing violate Section 18 of the Code on Wages, 2019, which strictly caps total deductions at 50% of wage.",
            "3. **Arbitrary Deactivation without Due Process:** Suspending or terminating a worker's account without written cause and 14 days' prior notice violates statutory fair contract principles and Article 21 of the Constitution.",
            "4. **Liability for Exemplary Statutory Compensation:** Section 45(2) of the Code on Wages empowers the competent authority to award compensation up to ten (10) times the withheld wages.",
        ]

        return {
            "citations": citations,
            "grounds": grounds_list,
        }

    @classmethod
    def _build_prayers(cls, case: CaseState, wage_calc: Optional[WageCalculationResult], state: str, lang: ComplaintLanguage) -> List[str]:
        """Builds the prayers / reliefs sought."""
        amt = f"₹{wage_calc.net_unpaid_balance:,.2f}" if wage_calc else (f"₹{case.amount}" if case.amount else "the entire outstanding amount")
        statutory_amt = f"₹{wage_calc.total_statutory_claim_amount:,.2f}" if wage_calc else amt

        if lang == ComplaintLanguage.HINDI:
            return [
                f"1. अनावेदक/प्लेटफॉर्म को तुरंत बकाया राशि {amt} का 18% वार्षिक ब्याज सहित भुगतान करने का आदेश दिया जाए।",
                "2. वेतन संहिता, 2019 की धारा 45 के अंतर्गत अनुकरणीय वैधानिक मुआवजा स्वीकृत किया जाए।",
                "3. शिकायतकर्ता की पार्टनर आईडी को बिना किसी पूर्वाग्रह के तत्काल बहाल किया जाए।",
                "4. अनावेदक को भविष्य में ऐसी गैर-कानूनी कटौती व उत्पीड़न बंद करने के निर्देश दिए जाएं।",
            ]
        return [
            f"1. Direct the Opposite Party / Platform to immediately disburse the principal unpaid wage sum of {amt} along with statutory interest @ 18% p.a. from the date due.",
            f"2. Award exemplary compensation under Section 45(2) of the Code on Wages, 2019, bringing the total statutory claim to {statutory_amt}.",
            "3. Order the immediate and unconditional restoration/reinstatement of the Complainant's partner account/ID without penalty or algorithmic rating degradation.",
            "4. Direct the Opposite Party to cease arbitrary deductions and comply with the statutory dispute resolution timeline.",
        ]

    @classmethod
    def _render_english_markdown(cls, **kwargs) -> str:
        """Renders standard formal English complaint petition."""
        auth = kwargs["auth_details"]
        case = kwargs["case"]
        annexures_md = "\n".join([f"- **{a['label']}:** {a['description']}" for a in kwargs["annexures"]])
        grounds_md = "\n".join(kwargs["legal_grounds"]["grounds"])
        citations_md = "\n".join([f"- {c}" for c in kwargs["legal_grounds"]["citations"]])
        prayers_md = "\n".join(kwargs["prayers"])

        return f"""# FORMAL LEGAL COMPLAINT & DISPUTE RESOLUTION PETITION
**Case Reference Number:** `{kwargs['doc_id']}`  
**Date of Filing:** {kwargs['date_str']}  

---

### BEFORE:
**{auth['designation']}**  
{auth['office']}  
{auth['address']}  

### IN THE MATTER OF:
**Complainant:** Aggrieved Worker / Partner (Case Ref: {case.case_id})  
*Worker Type:* {case.worker_type.value.replace('_', ' ').title()} | *State:* {kwargs['state_str']}  
**VERSUS**  
**Opposite Party (Aggregator / Employer):** {kwargs['platform']}  

---

### {kwargs['subject']}

**RESPECTFUL SUBMISSION ON BEHALF OF THE COMPLAINANT:**

The Complainant above-named respectfully states and submits as follows:

#### 1. PARTIES & BACKGROUND
1.1 The Complainant is an informal / platform gig worker engaged with {kwargs['platform']} performing essential delivery, logistics, or transport services in the State of {kwargs['state_str']}.  
1.2 The Opposite Party is a digital platform / aggregator entity governed by the provisions of the Code on Social Security, 2020, the Code on Wages, 2019, and applicable State Gig Worker Welfare Legislations.

#### 2. FACTUAL NARRATIVE & CHRONOLOGY OF DISPUTE
{kwargs['timeline_section']}

#### 3. STATEMENT OF FINANCIAL CLAIM & UNLAWFUL DEDUCTIONS
{kwargs['claim_section']}

#### 4. STATUTORY GROUNDS & LEGAL PROVISIONS
The action of the Opposite Party in withholding payment, imposing penalties, or abruptly deactivating the Complainant is in direct contravention of the following statutory provisions:
{grounds_md}

**Key Applicable Statutes:**
{citations_md}

#### 5. PRAYERS / RELIEFS SOUGHT
In light of the facts and statutory grounds stated above, the Complainant humbly prays that this Hon'ble Authority / Grievance Officer may be pleased to:
{prayers_md}

---

### LIST OF ANNEXURES & DOCUMENTARY PROOF
{annexures_md}

---

**VERIFICATION:**  
I, the Complainant, do hereby verify that the contents of the above complaint are true and correct to the best of my knowledge and belief, and nothing material has been concealed therefrom.

**Prepared and Assisted by:** WorkerSaathi Legal & Evidence Engine  
*Generated on {kwargs['date_str']}*
"""

    @classmethod
    def _render_hindi_markdown(cls, **kwargs) -> str:
        """Renders formal Hindi (Devanagari) complaint petition."""
        auth = kwargs["auth_details"]
        case = kwargs["case"]
        annexures_md = "\n".join([f"- **{a['label']}:** {a['description']}" for a in kwargs["annexures"]])
        citations_md = "\n".join([f"- {c}" for c in kwargs["legal_grounds"]["citations"]])
        prayers_md = "\n".join(kwargs["prayers"])

        return f"""# औपचारिक वैधानिक शिकायत एवं विवाद समाधान प्रार्थना पत्र
**मामला संदर्भ संख्या:** `{kwargs['doc_id']}`  
**दिनांक:** {kwargs['date_str']}  

---

### सेवा में,
**{auth['designation']}**  
{auth['office']}  
{auth['address']}  

### मामला:
**शिकायतकर्ता:** पीड़ित श्रमिक / डिलीवरी पार्टनर (मामला सं: {case.case_id})  
*श्रमिक श्रेणी:* {case.worker_type.value.replace('_', ' ').title()} | *राज्य:* {kwargs['state_str']}  
**बनाम**  
**अनावेदक (प्लेटफॉर्म / नियोक्ता):** {kwargs['platform']}  

---

### {kwargs['subject']}

**महोदय/महोदया,**  
निवेदन है कि शिकायतकर्ता उपरोक्त पते पर अनावेदक कंपनी {kwargs['platform']} के साथ डिलीवरी / गिग वर्कर के रूप में कार्यरत है। प्रार्थी निम्नलिखित तथ्य सादर प्रस्तुत करता है:

#### 1. घटनाक्रम एवं साक्ष्य विवरण
{kwargs['timeline_section']}

#### 2. वित्तीय दावा एवं गैर-कानूनी कटौती का ब्यौरा
{kwargs['claim_section']}

#### 3. विधिक आधार (कानूनी प्रावधान)
अनावेदक कंपनी द्वारा प्रार्थी का पारिश्रमिक रोकना, एकतरफा पेनल्टी लगाना अथवा बिना नोटिस आईडी बंद करना वेतन संहिता, 2019 तथा सामाजिक सुरक्षा संहिता, 2020 का सीधा उल्लंघन है।
- **वेतन संहिता, 2019 की धारा 18:** किसी भी स्थिति में कुल वेतन से 50% से अधिक कटौती प्रतिबंधित है।
- **वेतन संहिता, 2019 की धारा 45:** विलंबित वेतन पर 10 गुना तक वैधानिक मुआवजा देय है।
- **प्रासंगिक कानून:**  
{citations_md}

#### 4. चाही गई राहत (प्रार्थना)
अतः श्रीमान जी से विनम्र प्रार्थना है कि न्यायहित में निम्न आदेश पारित करने की कृपा करें:
{prayers_md}

---

### संलग्न साक्ष्य सूची (Annexures)
{annexures_md}

---

**सत्यापन:**  
मैं सत्यापित करता/करती हूँ कि इस शिकायत पत्र में वर्णित समस्त तथ्य मेरी व्यक्तिगत जानकारी के अनुसार पूर्णतः सत्य हैं।

**सहायक प्रणाली:** वर्करसाथी (WorkerSaathi) लीगल हेल्प एंड एविडेंस इंजन  
*प्रमाणित डिजिटल ड्राफ्ट*
"""

    @classmethod
    def _convert_md_to_html(cls, md: str) -> str:
        """Converts Markdown complaint into clean printable HTML."""
        import html
        lines = md.split("\n")
        html_lines = [
            "<div class='formal-complaint-document' style='font-family: Georgia, serif; line-height: 1.6; color: #111; max-width: 800px; margin: 0 auto; padding: 30px; background: #fff; border: 1px solid #ddd; border-radius: 8px;'>"
        ]
        in_table = False
        table_rows = []

        for line in lines:
            line = line.strip()
            if not line:
                if in_table:
                    html_lines.append(cls._render_table_html(table_rows))
                    in_table = False
                    table_rows = []
                continue

            if line.startswith("|") and line.endswith("|"):
                in_table = True
                table_rows.append(line)
                continue
            elif in_table:
                html_lines.append(cls._render_table_html(table_rows))
                in_table = False
                table_rows = []

            if line.startswith("# "):
                html_lines.append(f"<h1 style='text-align: center; color: #1a365d; font-size: 1.4rem; margin-bottom: 8px;'>{html.escape(line[2:])}</h1>")
            elif line.startswith("### "):
                html_lines.append(f"<h3 style='color: #2b6cb0; font-size: 1.1rem; margin-top: 20px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px;'>{html.escape(line[4:])}</h3>")
            elif line.startswith("#### "):
                html_lines.append(f"<h4 style='color: #2d3748; font-size: 1rem; margin-top: 14px;'>{html.escape(line[5:])}</h4>")
            elif line.startswith("---"):
                html_lines.append("<hr style='border: 0; border-top: 1px solid #cbd5e0; margin: 16px 0;'>")
            elif line.startswith("> "):
                html_lines.append(f"<blockquote style='background: #fffaf0; border-left: 4px solid #dd6b20; padding: 8px 12px; margin: 10px 0;'>{html.escape(line[2:])}</blockquote>")
            elif line.startswith("- "):
                html_lines.append(f"<li style='margin-left: 20px;'>{html.escape(line[2:])}</li>")
            else:
                formatted = html.escape(line)
                # Bold
                formatted = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', formatted)
                formatted = re.sub(r'`(.*?)`', r'<code style="background:#edf2f7;padding:2px 4px;border-radius:4px;">\1</code>', formatted)
                html_lines.append(f"<p style='margin: 8px 0;'>{formatted}</p>")



        if in_table:
            html_lines.append(cls._render_table_html(table_rows))

        html_lines.append("</div>")
        return "\n".join(html_lines)

    @classmethod
    def _render_table_html(cls, rows: List[str]) -> str:
        """Renders markdown table rows as clean HTML table."""
        if not rows:
            return ""
        out = ["<table style='width: 100%; border-collapse: collapse; margin: 14px 0; font-size: 0.9rem;'>"]
        is_header = True
        for row in rows:
            cols = [c.strip() for c in row.split("|")[1:-1]]
            if all(set(c).issubset({'-', ':', ' '}) for c in cols):
                is_header = False
                continue

            tag = "th" if is_header else "td"
            style = "border: 1px solid #cbd5e0; padding: 8px 12px; text-align: left;"
            if is_header:
                style += " background-color: #f7fafc; font-weight: bold; color: #2d3748;"

            row_html = "".join([f"<{tag} style='{style}'>{c}</{tag}>" for c in cols])
            out.append(f"<tr>{row_html}</tr>")
        out.append("</table>")
        return "\n".join(out)

    @classmethod
    def _generate_pdf_from_html(cls, html_content: str) -> Optional[str]:
        """
        Generate PDF from HTML content using fpdf2.
        Returns base64-encoded PDF string, or None if fpdf2 unavailable.
        """
        if not FPDF_AVAILABLE or FPDF is None:
            return None
        
        try:
            # Create a simple PDF from the HTML content
            pdf = FPDF()
            pdf.add_page()
            pdf.set_auto_page_break(auto=True, margin=25)
            
            # Use a Unicode-capable font
            # Try to use a system font that supports Unicode
            font_added = False
            font_paths = [
                # Windows fonts
                ('C:/Windows/Fonts/arial.ttf', 'C:/Windows/Fonts/arialbd.ttf', 'C:/Windows/Fonts/ariali.ttf', 'C:/Windows/Fonts/arialbi.ttf'),
                ('C:/Windows/Fonts/segui.ttf', 'C:/Windows/Fonts/seguib.ttf', 'C:/Windows/Fonts/seguii.ttf', 'C:/Windows/Fonts/seguiz.ttf'),  # Segoe UI
                # Linux fonts
                ('/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf'),
                ('/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf', '/usr/share/fonts/truetype/noto/NotoSerif-Bold.ttf', '/usr/share/fonts/truetype/noto/NotoSerif-Italic.ttf', '/usr/share/fonts/truetype/noto/NotoSerif-BoldItalic.ttf'),
            ]
            
            for regular, bold, italic, bold_italic in font_paths:
                import os
                if os.path.exists(regular):
                    pdf.add_font('CustomFont', '', regular, uni=True)
                    if os.path.exists(bold):
                        pdf.add_font('CustomFont', 'B', bold, uni=True)
                    if os.path.exists(italic):
                        pdf.add_font('CustomFont', 'I', italic, uni=True)
                    if os.path.exists(bold_italic):
                        pdf.add_font('CustomFont', 'BI', bold_italic, uni=True)
                    font_name = 'CustomFont'
                    font_added = True
                    break
            
            if not font_added:
                # Fallback to built-in font (limited Unicode)
                font_name = 'Helvetica'
            
            pdf.set_font(font_name, '', 11)
            
            # Simple HTML to text conversion for PDF
            import re
            
            # Replace common HTML tags with plain text equivalents
            text = html_content
            # Headers
            text = re.sub(r'<h1[^>]*>(.*?)</h1>', r'\1\n\n', text, flags=re.IGNORECASE | re.DOTALL)
            text = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\1\n\n', text, flags=re.IGNORECASE | re.DOTALL)
            text = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\1\n', text, flags=re.IGNORECASE | re.DOTALL)
            text = re.sub(r'<h4[^>]*>(.*?)</h4>', r'\1\n', text, flags=re.IGNORECASE | re.DOTALL)
            # Paragraphs
            text = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', text, flags=re.IGNORECASE | re.DOTALL)
            # Bold
            text = re.sub(r'<strong>(.*?)</strong>', r'\1', text, flags=re.IGNORECASE | re.DOTALL)
            text = re.sub(r'<b>(.*?)</b>', r'\1', text, flags=re.IGNORECASE | re.DOTALL)
            # Line breaks
            text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
            text = re.sub(r'<hr\s*/?>', '\n' + '-'*50 + '\n', text, flags=re.IGNORECASE)
            # Lists
            text = re.sub(r'<li[^>]*>(.*?)</li>', r'  - \1\n', text, flags=re.IGNORECASE | re.DOTALL)
            # Tables - simplified
            text = re.sub(r'<table[^>]*>.*?</table>', '[Table - see HTML version for full details]', text, flags=re.IGNORECASE | re.DOTALL)
            # Remove remaining tags
            text = re.sub(r'<[^>]+>', '', text)
            # Decode HTML entities
            text = html.unescape(text)
            # Clean up whitespace
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = re.sub(r' {2,}', ' ', text)
            text = text.strip()
            
            # Write to PDF
            pdf.multi_cell(0, 5, text)
            
            # Output as bytes
            pdf_bytes = pdf.output(dest='S')
            if isinstance(pdf_bytes, str):
                pdf_bytes = pdf_bytes.encode('latin-1')
            return base64.b64encode(pdf_bytes).decode('utf-8')
        except Exception as e:
            print(f"[complaint_generator] PDF generation failed: {e}")
            return None
