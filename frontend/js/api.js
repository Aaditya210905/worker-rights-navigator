/**
 * api.js — REST calls to the WorkerSaathi backend.
 *
 * Session creation, case polling and the LeMUR action-plan request.
 */

async function pollCase() {
    if (!sessionId) return;
    try {
        const r = await fetch(`${API_BASE}/sessions/${sessionId}/case`);
        if (!r.ok) return;
        const c = await r.json();
        updateCaseField('fStatus', c.status);
        updateCaseField('fWorkerType', c.worker_type);
        updateCaseField('fIssue', c.issue_category);
        updateCaseField('fState', c.state);
        updateCaseField('fEmployer', c.platform_or_employer);
        updateCaseField('fAmount', c.amount ? '₹' + c.amount : null);
        updateCaseField('fSafety', c.safety_level);

        // Auto-sync legal hub widgets if active
        if (c.eligibility_report && typeof renderEligibilityReport === 'function') {
            renderEligibilityReport(c.eligibility_report);
        }
        if (c.wage_calculation && typeof renderWageResults === 'function') {
            renderWageResults(c.wage_calculation);
        }

        // Update progress tracker (presentation-only)
        updateProgressTracker(c.status);
    } catch (e) { }
}

// ── Session creation ─────────────────────────────────────────────

/**
 * Create a session via REST and store its id in the shared state.
 * @returns {Promise<boolean>} false when the backend could not be reached.
 */
async function createSession() {
    try {
        const r = await fetch(`${API_BASE}/sessions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: '{}'
        });
        const data = await r.json();
        sessionId = data.session_id;
        addMsg('system', `Session ${sessionId} created`);
        if (typeof updateSessionDisplay === 'function') updateSessionDisplay();
        return true;
    } catch (e) {
        setStatus('disconnected', 'Connection Failed');
        addMsg('system', 'Failed to create session: ' + e.message);
        return false;
    }
}

// ── LeMUR action plan ────────────────────────────────────────────

async function fetchActionPlan(sid) {
    const modal = document.getElementById('actionPlanModal');
    const modalBody = document.getElementById('actionPlanBody');
    const downloadBtn = document.getElementById('downloadPdfBtn');
    const closeBtn = document.getElementById('closeModalBtn');

    modal.style.display = 'flex';
    modalBody.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <p>Synthesizing evidence-backed Indian Legal Action Plan...<br><span style="font-size: 0.8em; opacity: 0.7;">This may take a few seconds.</span></p>
        </div>

    `;

    closeBtn.onclick = () => { modal.style.display = 'none'; };

    try {
        const response = await fetch(`${API_BASE}/sessions/${sid}/action-plan`, {
            method: 'POST'
        });

        if (!response.ok) {
            throw new Error('Failed to generate action plan');
        }

        const data = await response.json();
        // Simple markdown parsing to HTML (newlines and bold)
        let htmlText = data.plan
            .replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>');

        modalBody.innerHTML = `<div>${htmlText}</div>`;
        downloadBtn.disabled = false;
        downloadBtn.onclick = () => {
            alert("Action Plan ready! In a full implementation, this would trigger a PDF download.");
        };
    } catch (e) {
        modalBody.innerHTML = `<p style="color: red;">Error: ${e.message}</p>`;
    }
}
