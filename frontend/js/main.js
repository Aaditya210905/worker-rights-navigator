/**
 * main.js — Frontend entry point.
 *
 * Loaded last: binds the header/mic controls to the voice session,
 * language selector, text input, and end-session button.
 */

// ── Mic button ───────────────────────────────────────────────────
micBtn.addEventListener('click', toggleSession);
muteBtn.addEventListener('click', toggleMute);

// ── Language selector ────────────────────────────────────────────
if (langSelect) {
    // Populate language dropdown from config
    DEFAULT_LANGUAGES.forEach(lang => {
        const opt = document.createElement('option');
        opt.value = lang.code;
        opt.textContent = `${lang.native} (${lang.name})`;
        if (lang.code === selectedLanguage) opt.selected = true;
        langSelect.appendChild(opt);
    });

    langSelect.addEventListener('change', onLanguageChange);
}

// ── Text input (send on Enter) ───────────────────────────────────
const textInputEl = document.getElementById('textInput');
const sendTextBtnEl = document.getElementById('sendTextBtn');

if (textInputEl) {
    textInputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendTextMessage();
        }
    });
}
if (sendTextBtnEl) {
    sendTextBtnEl.addEventListener('click', sendTextMessage);
}

// ── Preset Government Schemes Quick Handler ──────────────────────
window.handlePresetGovtSchemes = async function() {
    const query = "Kya government ne gig aur unorganized workers ke liye koi important schemes nikali hain?";
    const input = document.getElementById('textInput');
    if (input) {
        input.value = query;
    }
    if (typeof sendTextMessage === 'function') {
        await sendTextMessage();
    }
};

// ── End session button ───────────────────────────────────────────
const endSessionBtn = document.getElementById('endSessionBtn');
if (endSessionBtn) {
    endSessionBtn.addEventListener('click', () => {
        stopSession();
    });
}

// ── Keyboard shortcuts ──────────────────────────────────────────
document.addEventListener('keydown', (e) => {
    // Space bar to toggle recording (when not typing)
    if (e.code === 'Space' && document.activeElement !== textInput) {
        e.preventDefault();
        toggleSession();
    }
    // Escape to end session
    if (e.code === 'Escape' && isRunning) {
        stopSession();
    }
});

console.log('[WorkerSaathi] Voice client ready (Sarvam AI) — click the microphone to start.');
console.log('[WorkerSaathi] Keyboard shortcuts: Space=record, Escape=end session');
