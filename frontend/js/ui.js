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

// ── Formatting Helpers for Indian Legal & Scheme Intelligence ───

function escapeHtml(str) {
    if (!str) return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function formatInlineMarkdown(text) {
    if (!text) return '';
    let s = escapeHtml(text);

    // Bold: **text** or __text__
    s = s.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/__(.*?)__/g, '<strong>$1</strong>');

    // Italic: *text* or _text_
    s = s.replace(/\*([^\*]+?)\*/g, '<em>$1</em>');
    s = s.replace(/_([^_]+?)_/g, '<em>$1</em>');

    // Inline code: `code`
    s = s.replace(/`([^`]+)`/g, '<code class="msg-inline-code">$1</code>');

    // Statutory provisions: Section 114, Rule 2026, धारा 114
    s = s.replace(/\b(Section\s+\d+[A-Z]?|धारा\s+\d+|Rule\s+\d+|Rules,\s*\d{4})\b/gi, '<span class="badge-citation">$1</span>');

    // Rupee amounts: ₹4,500, ₹ 500, Rs. 500
    s = s.replace(/(₹\s?[\d,]+|Rs\.?\s?[\d,]+)/g, '<span class="badge-amount">$1</span>');

    // Important Helpline Numbers: 112, 1098, 181, 1091, 14434, 1930
    s = s.replace(/\b(112|1098|181|1091|14434|1930)\b/g, '<a href="tel:$1" class="helpline-chip" title="Call Helpline">📞 $1</a>');

    // URLs: https://...
    s = s.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener" style="color:var(--saffron);text-decoration:underline;">$1</a>');

    return s;
}

function formatSafetyMessage(text) {
    return `
        <div class="safety-alert-box">
            <div style="font-weight:700;margin-bottom:0.5rem;font-size:0.92rem;color:var(--red-dark);">
                🚨 Urgent Safety Escalation
            </div>
            <div style="margin-bottom:0.75rem;line-height:1.55;">
                ${formatInlineMarkdown(text)}
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:0.4rem;margin-top:0.6rem;">
                <a href="tel:112" class="helpline-chip" style="background:#EF4444;color:#FFF;border:none;padding:0.3rem 0.75rem;">📞 Police / Emergency 112</a>
                <a href="tel:1098" class="helpline-chip" style="background:#EF4444;color:#FFF;border:none;padding:0.3rem 0.75rem;">📞 Childline 1098</a>
                <a href="tel:181" class="helpline-chip" style="background:#EF4444;color:#FFF;border:none;padding:0.3rem 0.75rem;">📞 Women Helpline 181</a>
                <a href="tel:14434" class="helpline-chip" style="background:#EF4444;color:#FFF;border:none;padding:0.3rem 0.75rem;">📞 Labour Ministry 14434</a>
            </div>
        </div>
    `;
}

function formatUserMessage(text) {
    return `<div class="user-text">${escapeHtml(text).replace(/\n/g, '<br>')}</div>`;
}

function formatAgentMessage(rawText) {
    if (!rawText) return '';
    let t = rawText.trim();

    // 1. Extract statutory disclaimer if present
    let disclaimer = '';
    const discMatch = t.match(/(?:Yeh information verified government sources se hai[^\n]*?(?:lawyer se baat karna zaroori hai|legal advice)[^\n.]*\.?|Disclaimer:[^\n]+)/i);
    if (discMatch) {
        disclaimer = discMatch[0].trim();
        t = t.replace(discMatch[0], ' ').trim();
    }

    // 2. Extract closing question / prompt if present
    let promptText = '';
    const qMatch = t.match(/([A-Z\u0900-\u097F][^.!?\n]*\?[^\n]*)$/i);
    if (qMatch) {
        promptText = qMatch[1].trim();
        t = t.slice(0, qMatch.index).trim();
    }

    // 3. Detect schemes / numbered points
    // Handles inline formats like: "**1. Title:** ... **2. Title:** ..."
    // as well as "1. **Title:**" and "1. Title:"
    const itemRegex = /(?:^|\s+)(?:\*\*(\d+)[\.:]\s*([^*]+?)\*\*:?|(\d+)[\.:]\s+\*\*([^*]+?)\*\*:?|(\d+)[\.:]\s+([^:\n]+):)\s*/g;
    let match;
    const indices = [];

    while ((match = itemRegex.exec(t)) !== null) {
        const num = match[1] || match[3] || match[5];
        let title = (match[2] || match[4] || match[6] || '').trim();
        // Remove trailing colon or asterisks if still present
        title = title.replace(/[:*]+$/, '').trim();
        indices.push({ index: match.index, length: match[0].length, num, title });
    }

    let html = '';

    if (indices.length > 0) {
        // We have structured schemes/items!
        const intro = t.slice(0, indices[0].index).trim();
        if (intro) {
            html += `<div class="msg-lead">${formatInlineMarkdown(intro)}</div>`;
        }

        html += `<div class="msg-schemes-stack">`;
        for (let i = 0; i < indices.length; i++) {
            const start = indices[i].index + indices[i].length;
            const end = i < indices.length - 1 ? indices[i + 1].index : t.length;
            const body = t.slice(start, end).trim();

            html += `
                <div class="scheme-card">
                    <div class="scheme-card-header">
                        <span class="scheme-badge">${indices[i].num}</span>
                        <h4 class="scheme-title">${formatInlineMarkdown(indices[i].title)}</h4>
                    </div>
                    <div class="scheme-body">${formatInlineMarkdown(body)}</div>
                </div>
            `;
        }
        html += `</div>`;
    } else {
        // Check for bullet lists or standard paragraphs
        const lines = t.split('\n');
        let inBulletList = false;
        let paragraphs = [];
        let currentP = '';

        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed) {
                if (currentP) {
                    paragraphs.push(currentP);
                    currentP = '';
                }
                continue;
            }

            const bulletMatch = trimmed.match(/^[-*•]\s+(.*)$/);
            if (bulletMatch) {
                if (currentP) {
                    paragraphs.push(currentP);
                    currentP = '';
                }
                if (!inBulletList) {
                    html += `<ul class="msg-bullet-list">`;
                    inBulletList = true;
                }
                html += `<li class="msg-bullet-item">${formatInlineMarkdown(bulletMatch[1])}</li>`;
            } else {
                if (inBulletList) {
                    html += `</ul>`;
                    inBulletList = false;
                }
                currentP += (currentP ? ' ' : '') + trimmed;
            }
        }

        if (inBulletList) {
            html += `</ul>`;
        }
        if (currentP) {
            paragraphs.push(currentP);
        }

        for (const p of paragraphs) {
            html += `<p class="msg-paragraph">${formatInlineMarkdown(p)}</p>`;
        }
    }

    // 4. Render Disclaimer Card
    if (disclaimer) {
        html += `
            <div class="msg-disclaimer">
                <span class="disclaimer-icon">⚖️</span>
                <div class="disclaimer-text"><strong>Statutory Notice:</strong> ${formatInlineMarkdown(disclaimer)}</div>
            </div>
        `;
    }

    // 5. Render Concluding Question / Prompt Card with interactive Quick Chips
    if (promptText) {
        let chipsHtml = '';
        const lowerQ = promptText.toLowerCase();

        if (lowerQ.includes('type') || lowerQ.includes('delivery') || lowerQ.includes('construction') || lowerQ.includes('kaam karte')) {
            chipsHtml = `
                <div class="quick-chips-row">
                    <button class="quick-chip" onclick="handleQuickReply('Main delivery worker hoon (Zomato/Swiggy)')">🛵 Delivery Worker</button>
                    <button class="quick-chip" onclick="handleQuickReply('Main construction site par kaam karta hoon')">🏗️ Construction</button>
                    <button class="quick-chip" onclick="handleQuickReply('Main factory worker hoon')">🏭 Factory Worker</button>
                    <button class="quick-chip" onclick="handleQuickReply('Main cab driver hoon (Ola/Uber)')">🚖 Cab Driver</button>
                </div>
            `;
        } else if (lowerQ.includes('state') || lowerQ.includes('rajasthan') || lowerQ.includes('karnataka') || lowerQ.includes('delhi')) {
            chipsHtml = `
                <div class="quick-chips-row">
                    <button class="quick-chip" onclick="handleQuickReply('Rajasthan')">Rajasthan</button>
                    <button class="quick-chip" onclick="handleQuickReply('Karnataka')">Karnataka</button>
                    <button class="quick-chip" onclick="handleQuickReply('Delhi')">Delhi</button>
                    <button class="quick-chip" onclick="handleQuickReply('Maharashtra')">Maharashtra</button>
                </div>
            `;
        } else if (lowerQ.includes('e-shram') || lowerQ.includes('card') || lowerQ.includes('registered')) {
            chipsHtml = `
                <div class="quick-chips-row">
                    <button class="quick-chip" onclick="handleQuickReply('Haan, mere paas e-Shram card hai')">✅ Haan, mere paas hai</button>
                    <button class="quick-chip" onclick="handleQuickReply('Nahi, abhi tak register nahi kiya hai')">❌ Nahi, abhi nahi banaya</button>
                </div>
            `;
        }

        html += `
            <div class="msg-prompt-card">
                <div class="prompt-header">
                    <span class="material-symbols-outlined" style="font-size:16px;">forum</span>
                    <span>Next Question / Agla Sawaal</span>
                </div>
                <div class="prompt-text">${formatInlineMarkdown(promptText)}</div>
                ${chipsHtml}
            </div>
        `;
    }

    // 6. Action Toolbar (Copy text & Listen)
    html += `
        <div class="msg-toolbar">
            <button class="msg-action-btn" onclick="copyMsgText(this)" title="Copy message">
                <span class="material-symbols-outlined" style="font-size:14px;">content_copy</span>
                <span>Copy</span>
            </button>
            <button class="msg-action-btn" onclick="speakMsgText(this)" title="Read aloud">
                <span class="material-symbols-outlined" style="font-size:14px;">volume_up</span>
                <span>Read</span>
            </button>
        </div>
    `;

    return html;
}

// ── Interactive Actions for Message Cards ───────────────────────

window.copyMsgText = function(btn) {
    const msg = btn.closest('.msg');
    const text = msg ? msg.dataset.rawText || msg.innerText : '';
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
        btn.classList.add('copied');
        const span = btn.querySelector('span:not(.material-symbols-outlined)');
        if (span) span.textContent = 'Copied! ✓';
        setTimeout(() => {
            btn.classList.remove('copied');
            if (span) span.textContent = 'Copy';
        }, 2000);
    });
};

window.speakMsgText = function(btn) {
    const msg = btn.closest('.msg');
    if (!msg) return;
    if (msg.dataset.audioBase64) {
        playAudioBase64(msg.dataset.audioBase64);
        return;
    }
    const text = msg.dataset.rawText || msg.innerText;
    if (!text) return;
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const clean = text.replace(/[*_#`]/g, '');
        const utter = new SpeechSynthesisUtterance(clean);
        utter.lang = selectedTTSLanguage || 'hi-IN';
        window.speechSynthesis.speak(utter);
    }
};

window.handleQuickReply = function(text) {
    const input = document.getElementById('textInput');
    if (input) {
        input.value = text;
        if (typeof sendTextMessage === 'function') {
            sendTextMessage();
        }
    }
};

function addMsg(type, text, options = {}) {
    // Hide the empty state when first real message arrives
    const emptyState = document.getElementById('emptyState');
    if (emptyState) emptyState.style.display = 'none';

    const div = document.createElement('div');
    div.className = 'msg ' + type;
    div.dataset.rawText = text;
    if (options.audioBase64) {
        div.dataset.audioBase64 = options.audioBase64;
    }

    const label = document.createElement('div');
    label.className = 'label';
    label.textContent = type === 'user' ? 'You' : type === 'agent' ? 'WorkerSaathi' : type === 'safety' ? '🚨 Safety Alert' : '';
    if (label.textContent) div.appendChild(label);

    const bodyDiv = document.createElement('div');
    bodyDiv.className = 'msg-content';

    if (type === 'agent') {
        bodyDiv.innerHTML = formatAgentMessage(text);
    } else if (type === 'safety') {
        bodyDiv.innerHTML = formatSafetyMessage(text);
    } else if (type === 'user') {
        bodyDiv.innerHTML = formatUserMessage(text);
    } else {
        bodyDiv.textContent = text;
    }

    div.appendChild(bodyDiv);
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
    streamingTextAccum = text;
    streamingTextNode.textContent = text;
    chatEl.scrollTop = chatEl.scrollHeight;
}

function finalizeStreamingBubble() {
    if (streamingBubble) {
        streamingBubble.classList.remove('streaming');
        const cursor = streamingBubble.querySelector('.typing-cursor');
        if (cursor) cursor.remove();

        if (streamingTextAccum) {
            streamingBubble.dataset.rawText = streamingTextAccum;
            const contentNode = streamingBubble.querySelector('.streaming-text');
            if (contentNode) {
                contentNode.innerHTML = formatAgentMessage(streamingTextAccum);
            }
        }

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
    const els = document.querySelectorAll(`[id="${id}"], .${id}`);
    if (!els.length) return;
    els.forEach(el => {
        if (val && val !== 'unknown' && val !== 'Unknown') {
            el.textContent = val.replace(/_/g, ' ');
            el.classList.remove('empty');
            el.classList.add('field-val');
        }
    });
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
