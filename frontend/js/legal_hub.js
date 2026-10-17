/**
 * legal_hub.js — Interactive Client Logic for WorkerSaathi Legal Defender.
 *
 * Provides:
 * 1. Multi-page Navigation (Voice, Eligibility, Wage Calc, Evidence Locker, Complaints, Action Plan)
 * 2. Real-time Eligibility Evaluation (90/120-Day Rule progress bar & state acts)
 * 3. Interactive Wage & Unlawful Deduction Calculator (with Sec 45 10x penalty claim)
 * 4. Screenshot Uploader with PII Redaction Shield & Corroborated Evidence Timeline
 * 5. Complaint Petition Studio & Courtroom-Ready Export
 * 6. Case Dossier & Strategic Statutory Action Plan
 */

let currentComplaintLanguage = 'en';
let currentComplaintAuthority = 'labour_commissioner';
let currentGeneratedDoc = null;

// ── Multi-Page Navigation ─────────────────────────────────────────────────────

async function ensureSession() {
    if (!sessionId) {
        if (typeof createSession === 'function') {
            await createSession();
        }
    }
    updateSessionDisplay();
    return sessionId;
}

function updateSessionDisplay() {
    const pill = document.getElementById('currentSessionPill');
    if (pill) {
        if (sessionId) {
            pill.innerHTML = `<span>Session</span> <strong>#${sessionId.slice(0, 8)}</strong>`;
        } else {
            pill.innerHTML = `<span>+ New Session</span>`;
        }
    }
}

async function navigateToPage(pageId) {
    if (!pageId) pageId = 'voice';
    if (pageId === 'overview') pageId = 'action-plan';

    // Update Top Navigation Tabs
    document.querySelectorAll('.nav-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.page === pageId);
    });

    // Update Dedicated Page Views
    document.querySelectorAll('.page-view').forEach(view => {
        view.classList.toggle('active', view.id === `page-${pageId}`);
    });

    // Backward compatibility for legacy hub tab buttons if present
    document.querySelectorAll('.hub-nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === pageId);
    });

    // Update URL hash
    try {
        if (history.pushState) {
            history.pushState(null, null, `#${pageId}`);
        } else {
            window.location.hash = `#${pageId}`;
        }
    } catch (e) { }

    // Auto-create session if user navigates to an interactive tool and none exists
    if (!sessionId && ['eligibility', 'wages', 'evidence', 'complaint', 'action-plan'].includes(pageId)) {
        await ensureSession();
    }

    // Update breadcrumb title
    const crumbTitle = document.getElementById('activePageCrumb');
    if (crumbTitle) {
        const titles = {
            'voice': '🎙️ Voice Saathi AI',
            'eligibility': '🛡️ Statutory Eligibility Navigator',
            'wages': '💰 Forensic Wage & 10x Claim Calculator',
            'evidence': '📁 Evidence Locker & Timeline',
            'complaint': '⚖️ Courtroom Legal Petition Studio',
            'action-plan': '📋 Case Dossier & Strategic Action Plan'
        };
        crumbTitle.textContent = titles[pageId] || 'Legal Workspace';
    }

    // Close mobile drawer if open
    const sidebar = document.getElementById('sidebarNav');
    if (sidebar) sidebar.classList.remove('mobile-open');

    // Page-specific lazy loaders
    if (pageId === 'evidence') {
        loadEvidenceTimeline();
    } else if (pageId === 'action-plan') {
        if (typeof pollCase === 'function') pollCase();
    }
}

function toggleMobileSidebar() {
    const sidebar = document.getElementById('sidebarNav');
    if (sidebar) sidebar.classList.toggle('mobile-open');
}

function switchHubTab(tabName) {
    navigateToPage(tabName);
}

// ── 1. Eligibility Evaluation ─────────────────────────────────────────────────

async function runEligibilityCheck() {
    await ensureSession();
    if (!sessionId) {
        alert("Unable to initialize session with backend. Please ensure server is running.");
        return;
    }

    const daysInput = document.getElementById('eligDaysInput');
    const appsInput = document.getElementById('eligAppsInput');
    const eshramCheck = document.getElementById('eligEshramCheck');

    const days = parseInt(daysInput ? daysInput.value : 90) || 0;
    const apps = parseInt(appsInput ? appsInput.value : 1) || 1;
    const hasEshram = eshramCheck ? eshramCheck.checked : false;

    try {
        const resp = await fetch(`${API_BASE}/sessions/${sessionId}/eligibility`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                days_with_primary_aggregator: days,
                total_days_across_aggregators: days,
                number_of_aggregators: apps,
                has_eshram: hasEshram
            })
        });

        if (!resp.ok) throw new Error("Eligibility check failed");
        const data = await resp.json();
        renderEligibilityReport(data);
    } catch (err) {
        console.error(err);
    }
}

function setEligDaysPreset(days) {
    const input = document.getElementById('eligDaysInput');
    if (input) {
        input.value = days;
        runEligibilityCheck();
    }
}

function renderEligibilityReport(data) {
    const banner = document.getElementById('eligStatusBanner');
    const fill = document.getElementById('tenureProgressFill');
    const progressLabel = document.getElementById('tenureProgressLabel');
    const criteriaList = document.getElementById('eligCriteriaList');
    const stateRightsBox = document.getElementById('eligStateRights');

    if (banner) {
        banner.className = `eligibility-status-banner ${data.verdict}`;
        banner.textContent = data.verdict_badge;
    }

    if (fill && data.rule_90_120_status) {
        const primary = data.rule_90_120_status.days_primary || 0;
        const target = data.rule_90_120_status.target_single || 90;
        const pct = Math.min(100, Math.round((primary / target) * 100));
        fill.style.width = `${pct}%`;
        if (progressLabel) {
            progressLabel.textContent = `${primary} / ${target} days completed (${pct}%)`;
        }
    }

    if (criteriaList && data.criteria_checks) {
        criteriaList.innerHTML = data.criteria_checks.map(c => `
            <div class="criteria-item ${c.passed ? 'passed' : 'pending'}">
                <span class="criteria-icon">${c.passed ? '✓' : '○'}</span>
                <div class="criteria-content">
                    <strong>${c.name}</strong>
                    <span>${c.detail} (Basis: ${c.legal_basis})</span>
                </div>
            </div>
        `).join('');
    }

    if (stateRightsBox) {
        if (data.state_specific_rights) {
            stateRightsBox.style.display = 'block';
            stateRightsBox.innerHTML = `
                <strong>🏛️ ${data.state_specific_rights.state} Statutory Protections:</strong>
                ${data.state_specific_rights.key_benefit}
                <div style="margin-top:4px;font-size:0.75rem;opacity:0.85;">Statute: ${data.state_specific_rights.statute}</div>
            `;
        } else {
            stateRightsBox.style.display = 'none';
        }
    }
}

// ── 2. Wage Calculator ────────────────────────────────────────────────────────

async function runWageCalculation() {
    await ensureSession();
    if (!sessionId) {
        alert("Unable to initialize session with backend. Please ensure server is running.");
        return;
    }

    const baseEl = document.getElementById('calcBaseInput');
    const incEl = document.getElementById('calcIncInput');
    const dedEl = document.getElementById('calcDedInput');
    const periodEl = document.getElementById('calcPeriodInput');

    const base = parseFloat(baseEl ? baseEl.value : 0) || 0;
    const inc = parseFloat(incEl ? incEl.value : 0) || 0;
    const ded = parseFloat(dedEl ? dedEl.value : 0) || 0;
    const period = periodEl ? periodEl.value : 'Disputed Period';

    try {
        const resp = await fetch(`${API_BASE}/sessions/${sessionId}/wages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                base_unpaid: base,
                withheld_incentives: inc,
                unauthorized_deductions: ded,
                period_description: period
            })
        });

        if (!resp.ok) throw new Error("Wage calculation failed");
        const data = await resp.json();
        renderWageResults(data);
    } catch (err) {
        console.error(err);
    }
}

function setWagePreset(base, inc, ded, period) {
    const b = document.getElementById('calcBaseInput');
    const i = document.getElementById('calcIncInput');
    const d = document.getElementById('calcDedInput');
    const p = document.getElementById('calcPeriodInput');
    if (b) b.value = base;
    if (i) i.value = inc;
    if (d) d.value = ded;
    if (p) p.value = period;
    runWageCalculation();
}

function renderWageResults(data) {
    const card = document.getElementById('wageResultsCard');
    if (!card) return;
    card.style.display = 'block';

    const fmt = n => '₹' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 });

    const baseEl = document.getElementById('resBasePay');
    const incEl = document.getElementById('resIncentives');
    const dedEl = document.getElementById('resDeductions');
    const princEl = document.getElementById('resPrincipalTotal');
    const damEl = document.getElementById('resStatutoryDamages');
    const claimEl = document.getElementById('resTotalClaimDemand');

    if (baseEl) baseEl.textContent = fmt(data.base_unpaid);
    if (incEl) incEl.textContent = fmt(data.withheld_incentives);
    if (dedEl) dedEl.textContent = fmt(data.unauthorized_deductions);
    if (princEl) princEl.textContent = fmt(data.net_unpaid_balance);
    if (damEl) damEl.textContent = fmt(data.statutory_compensation_estimate);
    if (claimEl) claimEl.textContent = fmt(data.total_statutory_claim_amount);

    const violationBox = document.getElementById('resViolationPill');
    if (violationBox) {
        violationBox.style.display = data.deduction_cap_violation ? 'flex' : 'none';
    }
}

function transferToComplaint() {
    navigateToPage('complaint');
    generateLegalComplaint();
}

// ── 3. Evidence Locker & Screenshot Upload ─────────────────────────────────────

async function handleEvidenceFileUpload(file, caption = "") {
    await ensureSession();
    if (!sessionId) {
        alert("Unable to initialize session with backend. Please ensure server is running.");
        return;
    }
    if (!file) return;

    const statusHint = document.getElementById('uploadStatusHint');
    if (statusHint) statusHint.textContent = `Uploading & scanning ${file.name} for PII...`;

    const formData = new FormData();
    formData.append('file', file);
    if (caption) formData.append('caption', caption);

    try {
        const resp = await fetch(`${API_BASE}/sessions/${sessionId}/evidence/upload`, {
            method: 'POST',
            body: formData
        });

        if (!resp.ok) throw new Error("Upload failed");
        const data = await resp.json();

        if (statusHint) statusHint.textContent = `✅ ${file.name} analyzed & PII redacted!`;
        if (typeof addMsg === 'function') {
            addMsg('system', `📎 Evidence uploaded: ${file.name} (${data.evidence_type.replace(/_/g, ' ')}) — Sensitive numbers redacted.`);
        }
        loadEvidenceTimeline();
    } catch (err) {
        if (statusHint) statusHint.textContent = `❌ Upload failed: ${err.message}`;
    }
}

async function loadEvidenceTimeline() {
    if (!sessionId) return;
    try {
        const resp = await fetch(`${API_BASE}/sessions/${sessionId}/evidence`);
        if (!resp.ok) return;
        const data = await resp.json();
        renderEvidenceListAndTimeline(data);
    } catch (e) { }
}

function renderEvidenceListAndTimeline(data) {
    const listEl = document.getElementById('evidenceItemsList');
    const timelineEl = document.getElementById('evidenceTimelineNodes');

    if (listEl) {
        if (!data.evidence_items || data.evidence_items.length === 0) {
            listEl.innerHTML = '<div style="color:var(--text-muted);font-size:0.82rem;padding:1rem 0;">No evidence files uploaded yet. Drag & drop above.</div>';
        } else {
            listEl.innerHTML = data.evidence_items.map(item => `
                <div class="evidence-item-card">
                    <div class="evidence-item-meta">
                        <strong>${item.annexure_label || 'Annexure'}: ${item.filename}</strong>
                        <span>${item.evidence_type.replace(/_/g, ' ')} ${item.parsed_data.sensitive_data_redacted ? '· 🛡️ PII Masked' : ''}</span>
                    </div>
                    <span class="evidence-extracted-badge">
                        ${item.parsed_data.primary_amount ? '₹' + item.parsed_data.primary_amount : (item.parsed_data.detected_platform || 'Verified')}
                    </span>
                </div>
            `).join('');
        }
    }

    if (timelineEl && data.timeline && data.timeline.events) {
        timelineEl.innerHTML = data.timeline.events.map(ev => `
            <div class="timeline-node">
                <div class="timeline-node-date">${ev.date_or_period} — ${ev.event_title}</div>
                <div class="timeline-node-desc">${ev.description}</div>
            </div>
        `).join('');
    }
}

// ── 4. Legal Complaint Generator ──────────────────────────────────────────────

function selectComplaintAuthority(authType) {
    currentComplaintAuthority = authType;
    document.querySelectorAll('.auth-pill').forEach(pill => {
        pill.classList.toggle('active', pill.dataset.auth === authType);
    });
}

function selectComplaintLanguage(lang) {
    currentComplaintLanguage = lang;
    document.querySelectorAll('.lang-pill').forEach(pill => {
        pill.classList.toggle('active', pill.dataset.lang === lang);
    });
}

async function generateLegalComplaint() {
    await ensureSession();
    if (!sessionId) {
        alert("Unable to initialize session with backend. Please ensure server is running.");
        return;
    }

    const previewBox = document.getElementById('complaintPreviewBox');
    if (previewBox) {
        previewBox.innerHTML = '<div style="padding:3rem 0;text-align:center;color:var(--text-muted);"><div class="spinner" style="margin:0 auto 1rem auto;"></div>Drafting formal statutory petition with citations...</div>';
    }

    try {
        const resp = await fetch(`${API_BASE}/sessions/${sessionId}/complaint`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                authority_type: currentComplaintAuthority,
                language: currentComplaintLanguage
            })
        });

        if (!resp.ok) throw new Error("Failed to generate complaint");
        const doc = await resp.json();
        currentGeneratedDoc = doc;

        if (previewBox) {
            previewBox.innerHTML = doc.body_html;
        }

        const guidanceEl = document.getElementById('filingGuidanceBox');
        if (guidanceEl) {
            guidanceEl.style.display = 'block';
            guidanceEl.textContent = `📍 Filing Guidance: ${doc.destination_office_guidance}`;
        }

        if (typeof addMsg === 'function') {
            addMsg('system', `⚖️ Legal Complaint petition drafted for: ${doc.authority_name}`);
        }
    } catch (err) {
        if (previewBox) {
            previewBox.innerHTML = `<div style="color:var(--red);">Error: ${err.message}</div>`;
        }
    }
}

function copyComplaintToClipboard() {
    if (!currentGeneratedDoc) {
        alert("Please draft a complaint petition first.");
        return;
    }
    navigator.clipboard.writeText(currentGeneratedDoc.body_markdown).then(() => {
        alert("Formal Legal Petition copied to clipboard!");
    });
}

function printOrSaveComplaintPdf() {
    if (!currentGeneratedDoc) {
        alert("Please draft a complaint petition first.");
        return;
    }
    const win = window.open('', '_blank');
    win.document.write(`
        <!DOCTYPE html>
        <html>
        <head>
            <title>${currentGeneratedDoc.title}</title>
            <style>
                body { font-family: 'Times New Roman', serif; padding: 40px; color: #111; max-width: 800px; margin: 0 auto; line-height: 1.6; }
                table { width: 100%; border-collapse: collapse; margin: 15px 0; }
                th, td { border: 1px solid #333; padding: 8px; text-align: left; }
                th { background: #f2f2f2; }
                h1, h2, h3 { color: #1a365d; font-family: sans-serif; }
                @media print { button { display: none; } }
            </style>
        </head>
        <body>
            <button onclick="window.print()" style="padding: 10px 20px; font-size: 15px; margin-bottom: 25px; cursor: pointer; background: #ea580c; color: white; border: none; border-radius: 6px; font-weight: bold;">🖨️ Print / Save as PDF</button>
            ${currentGeneratedDoc.body_html}
        </body>
        </html>
    `);
    win.document.close();
}

// ── 5. Strategic Action Plan & Dossier ─────────────────────────────────────────

async function generateFullActionPlan() {
    await ensureSession();
    if (!sessionId) {
        alert("Please initialize session first.");
        return;
    }

    const container = document.getElementById('actionPlanDisplayArea');
    if (container) {
        container.innerHTML = `
            <div class="loading-state" style="padding: 2.5rem 0;">
                <div class="spinner"></div>
                <p>Synthesizing evidence-backed Indian Legal Action Plan...<br><span style="font-size: 0.8em; opacity: 0.7;">Retrieving statutory rights and conciliation roadmap...</span></p>
            </div>
        `;
    }

    try {
        const response = await fetch(`${API_BASE}/sessions/${sessionId}/action-plan`, {
            method: 'POST'
        });

        if (!response.ok) throw new Error('Failed to generate action plan');
        const data = await response.json();

        let htmlText = data.plan
            .replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>');

        if (container) {
            container.innerHTML = `
                <div class="action-plan-content-box">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;border-bottom:1px solid var(--border-light);padding-bottom:0.75rem;">
                        <span style="font-size:0.8rem;font-weight:700;color:var(--saffron);">LEGAL DEFENSE ROADMAP GENERATED</span>
                        <button class="preset-chip" onclick="printActionPlan()">🖨️ Print Action Plan</button>
                    </div>
                    <div>${htmlText}</div>
                </div>
            `;
        }
    } catch (e) {
        if (container) {
            container.innerHTML = `<p style="color: var(--red); padding: 1.5rem;">Error: ${e.message}</p>`;
        }
    }
}

function printActionPlan() {
    const content = document.querySelector('.action-plan-content-box');
    if (!content) return;
    const win = window.open('', '_blank');
    win.document.write(`
        <!DOCTYPE html>
        <html>
        <head>
            <title>WorkerSaathi — Legal Action Plan</title>
            <style>
                body { font-family: sans-serif; padding: 40px; color: #111; max-width: 800px; margin: 0 auto; line-height: 1.6; }
                h1, h2, h3 { color: #0f172a; }
                @media print { button { display: none; } }
            </style>
        </head>
        <body>
            <button onclick="window.print()" style="padding: 10px 20px; font-size: 15px; margin-bottom: 25px; cursor: pointer; background: #ea580c; color: white; border: none; border-radius: 6px;">Print</button>
            ${content.innerHTML}
        </body>
        </html>
    `);
    win.document.close();
}

// ── DOM Listeners & Dropzone Setup ─────────────────────────────────────────────

window.addEventListener('hashchange', () => {
    const hash = window.location.hash.replace('#', '');
    if (hash) navigateToPage(hash);
});

window.addEventListener('DOMContentLoaded', () => {
    // Initial page load from hash or default to voice
    const hash = window.location.hash.replace('#', '');
    if (hash && ['voice', 'eligibility', 'wages', 'evidence', 'complaint', 'action-plan'].includes(hash)) {
        navigateToPage(hash);
    } else {
        navigateToPage('voice');
    }

    // Dropzone setup
    const dropzone = document.getElementById('evidenceDropzone');
    const fileInput = document.getElementById('evidenceFileInput');

    if (dropzone && fileInput) {
        dropzone.onclick = () => fileInput.click();
        dropzone.ondragover = (e) => { e.preventDefault(); dropzone.classList.add('dragover'); };
        dropzone.ondragleave = () => dropzone.classList.remove('dragover');
        dropzone.ondrop = (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                handleEvidenceFileUpload(e.dataTransfer.files[0]);
            }
        };
        fileInput.onchange = () => {
            if (fileInput.files.length > 0) {
                handleEvidenceFileUpload(fileInput.files[0]);
            }
        };
    }
});
