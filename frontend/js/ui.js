/**
 * ui.js — Pure DOM/presentation helpers.
 *
 * Renders chat messages, status badge, streaming agent bubble, tool log,
 * case snapshot fields and the case progress tracker. No network calls.
 */

// ── UI helpers ────────────────────────────────────────────────

function setStatus(status, text) {
    badge.className = 'status-badge ' + status;
    badge.textContent = text;
}

function addMsg(type, text) {
    // Hide the empty state when first real message arrives
    const emptyState = document.getElementById('emptyState');
    if (emptyState) emptyState.style.display = 'none';

    const div = document.createElement('div');
    div.className = 'msg ' + type;
    const label = document.createElement('div');
    label.className = 'label';
    label.textContent = type === 'user' ? 'You' : type === 'agent' ? 'WorkerSaathi' : type === 'safety' ? '🚨 Safety Alert' : '';
    if (label.textContent) div.appendChild(label);
    div.appendChild(document.createTextNode(text));
    chatEl.appendChild(div);
    chatEl.scrollTop = chatEl.scrollHeight;
    return div;
}

// ── Streaming agent bubble ───────────────────────────────────────
function startStreamingBubble() {
    finalizeStreamingBubble();
    const emptyState = document.getElementById('emptyState');
    if (emptyState) emptyState.style.display = 'none';

    const div = document.createElement('div');
    div.className = 'msg agent streaming';
    const label = document.createElement('div');
    label.className = 'label';
    label.textContent = 'WorkerSaathi';
    div.appendChild(label);

    streamingTextNode = document.createElement('span');
    streamingTextNode.className = 'streaming-text';
    div.appendChild(streamingTextNode);

    const cursor = document.createElement('span');
    cursor.className = 'typing-cursor';
    cursor.textContent = '▍';
    div.appendChild(cursor);

    chatEl.appendChild(div);
    streamingBubble = div;
    chatEl.scrollTop = chatEl.scrollHeight;
}

function updateStreamingBubble(text) {
    if (!streamingBubble || !streamingTextNode) {
        startStreamingBubble();
    }
    streamingTextNode.textContent = text;
    chatEl.scrollTop = chatEl.scrollHeight;
}

function finalizeStreamingBubble() {
    if (streamingBubble) {
        streamingBubble.classList.remove('streaming');
        const cursor = streamingBubble.querySelector('.typing-cursor');
        if (cursor) cursor.remove();
        streamingBubble = null;
        streamingTextNode = null;
        streamingTextAccum = '';
    }
}

function addToolEntry(name, status) {
    if (toolLog.children.length === 1 && toolLog.children[0].textContent === 'No tool calls yet') {
        toolLog.innerHTML = '';
    }
    const div = document.createElement('div');
    div.className = 'tool-entry';
    div.innerHTML = `<span class="tool-name">${name}</span> <span class="tool-status">${status}</span>`;
    toolLog.appendChild(div);
    toolLog.scrollTop = toolLog.scrollHeight;
}

function updateCaseField(id, val) {
    const el = document.getElementById(id);
    if (!el) return;
    if (val && val !== 'unknown' && val !== 'Unknown') {
        el.textContent = val.replace(/_/g, ' ');
        el.className = 'field-val';
    }
}

// ── Case progress tracker ────────────────────────────────────────
// Reads case status from api.pollCase() and highlights the matching step.
// Does NOT create new API calls or modify backend state.

function updateProgressTracker(statusValue) {
    if (!statusValue) return;
    const normalizedStatus = statusValue.replace(/ /g, '_').toLowerCase();
    const steps = document.querySelectorAll('.progress-step');
    let found = false;

    steps.forEach((step, index) => {
        const stepStatuses = step.dataset.status.split(',');
        step.classList.remove('active', 'completed');

        if (found) {
            // Steps after the active one — leave unstyled
            return;
        }

        if (stepStatuses.includes(normalizedStatus)) {
            step.classList.add('active');
            found = true;
        } else {
            // If we haven't found the active status yet, this step is completed
            step.classList.add('completed');
        }
    });

    // Handle safety_escalation — highlight all steps as paused
    if (normalizedStatus === 'safety_escalation') {
        steps.forEach(step => {
            step.classList.remove('active', 'completed');
        });
    }
}
