/**
 * api.js — REST calls to the WorkerSaathi backend.
 *
 * Session creation, case polling and the LeMUR action-plan request.
 * Includes auto-recovery from stale sessions (e.g. after server restart).
 */

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

// ── Resilient fetch wrapper ──────────────────────────────────────

/**
 * Fetch wrapper that auto-recovers from stale/expired sessions.
 *
 * If the server returns 404 on a session endpoint (e.g. after
 * uvicorn --reload wipes in-memory sessions), this automatically
 * creates a fresh session and retries the request once.
 *
 * @param {string} urlBuilder  - Function or URL string. If a function,
 *                               called with current sessionId to build URL.
 * @param {object} opts        - fetch() options (method, body, headers, etc.)
 * @returns {Promise<Response>} - The fetch Response object.
 */
async function apiFetch(urlBuilder, opts = {}) {
    const buildUrl = typeof urlBuilder === 'function'
        ? urlBuilder
        : () => urlBuilder;

    let url = buildUrl(sessionId);
    let resp = await fetch(url, opts);

    // If 404 on a session-scoped endpoint, try to recover
    if (resp.status === 404 && sessionId && url.includes(`/sessions/${sessionId}`)) {
        console.warn(`[api] Session ${sessionId} expired/lost — creating new session...`);
        const oldId = sessionId;
        sessionId = null;
        const ok = await createSession();
        if (ok) {
            addMsg('system', `♻️ Session recovered (server restarted). Previous: ${oldId.slice(0, 12)}`);
            url = buildUrl(sessionId);
            resp = await fetch(url, opts);
        }
    }

    return resp;
}

// ── Case polling ─────────────────────────────────────────────────

async function pollCase() {
    if (!sessionId) return;
    try {
        const r = await apiFetch(
            sid => `${API_BASE}/sessions/${sid}/case`
        );
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
        const response = await apiFetch(
            s => `${API_BASE}/sessions/${s}/action-plan`,
            { method: 'POST' }
        );

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
