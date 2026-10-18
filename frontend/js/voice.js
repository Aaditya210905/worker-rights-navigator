/**
 * voice.js — Voice session lifecycle (Sarvam push-to-talk).
 *
 * Flow: Press mic → record → release → Sarvam STT → orchestrator → Sarvam TTS → play
 */

// ── Main toggle ──────────────────────────────────────────────────

async function toggleSession() {
    if (isProcessing) return; // Don't interrupt while processing

    if (isRecording) {
        // Stop recording → send to Sarvam
        await finishRecordingAndConverse();
    } else if (!isRunning) {
        // First press → create session + start
        await startSarvamSession();
    } else {
        // Session active, not recording → start recording
        await startSarvamRecording();
    }
}

// ── Session lifecycle ────────────────────────────────────────────

async function startSarvamSession() {
    setStatus('connecting', 'Starting...');
    micHint.textContent = 'Creating session...';

    // Create session via REST
    if (!(await createSession())) return;

    isRunning = true;
    addMsg('system', '🎤 WorkerSaathi is ready! Tap the microphone and speak.');

    // Immediately start first recording
    await startSarvamRecording();

    // Speak the greeting
    const greeting = 'Namaste! Main WorkerSaathi hoon. Aap mujhe apni problem bata sakte hain — Hindi, English, ya apni bhasha mein.';
    addMsg('agent', greeting);

    // TTS the greeting
    speakText(greeting, selectedTTSLanguage);
}

async function startSarvamRecording() {
    if (isProcessing) return;

    setStatus('listening', '🎤 Recording...');
    micBtn.className = 'mic-btn recording';
    micBtn.innerHTML = '<svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';
    micHint.textContent = 'Speaking... tap to send';

    // Add pulse animation
    micArea.classList.add('is-recording');
    muteBtn.classList.add('visible');

    const started = await startRecording();
    if (!started) {
        setStatus('connected', '⚠️ Mic failed');
        micBtn.className = 'mic-btn start';
        return;
    }
}

async function finishRecordingAndConverse() {
    // Stop recording and get audio blob
    setStatus('connected', '⏳ Processing...');
    micHint.textContent = 'Processing your speech...';
    micBtn.className = 'mic-btn processing';
    micBtn.innerHTML = '<div class="mic-spinner"></div>';
    micArea.classList.remove('is-recording');
    isProcessing = true;

    const audioBlob = await stopRecording();
    releaseRecording();

    if (!audioBlob || audioBlob.size < 1000) {
        addMsg('system', '⚠️ Recording too short. Please speak longer.');
        isProcessing = false;
        resetMicButton();
        return;
    }

    // Convert blob to base64
    const base64Audio = await blobToBase64(audioBlob);

    // Call /voice/converse endpoint
    try {
        const response = await fetch(VOICE_API.CONVERSE, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                audio_base64: base64Audio,
                session_id: sessionId,
                language_code: selectedLanguage,
                stt_mode: 'transcribe',
                tts_speaker: selectedSpeaker,
                tts_language: selectedTTSLanguage,
            }),
        });

        // If session was lost (server restart), auto-recover
        if (response.status === 404 && sessionId) {
            console.warn(`[voice] Session ${sessionId} expired — recreating...`);
            const oldId = sessionId;
            sessionId = null;
            const ok = await createSession();
            if (ok) {
                addMsg('system', `♻️ Session recovered (server restarted). Previous: ${oldId.slice(0, 12)}`);
                addMsg('system', '🎤 Please speak again — your last recording was lost.');
            }
            isProcessing = false;
            resetMicButton();
            return;
        }

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || `Server error ${response.status}`);
        }

        const data = await response.json();

        // Handle STT error
        if (data.stt_error) {
            addMsg('system', `⚠️ Speech recognition error: ${data.stt_error}`);
            isProcessing = false;
            resetMicButton();
            return;
        }

        // Show user transcript
        if (data.user_transcript) {
            addMsg('user', data.user_transcript);

            // Auto-detect language for TTS responses
            if (data.detected_language && data.detected_language !== 'unknown') {
                selectedTTSLanguage = data.detected_language;
                console.log(`[voice] Auto-detected language: ${data.detected_language}`);
            }
        }

        // Show tool calls
        if (data.tool_calls_made && data.tool_calls_made.length > 0) {
            data.tool_calls_made.forEach(tool => {
                addToolEntry(tool, '✅ completed');
            });
        }

        // Show agent text response
        if (data.agent_text) {
            addMsg('agent', data.agent_text, { audioBase64: data.audio_base64 });
        }

        // Update case status
        if (data.case_status) {
            pollCase();
        }

        // Play TTS audio
        if (data.audio_base64) {
            playAudioBase64(data.audio_base64);
        } else if (data.tts_error) {
            console.warn('[voice] TTS error:', data.tts_error);
        }

    } catch (e) {
        addMsg('system', `⚠️ Error: ${e.message}`);
        console.error('[voice] Converse error:', e);
    }

    isProcessing = false;
    resetMicButton();
}

function resetMicButton() {
    if (!isRunning) {
        micBtn.className = 'mic-btn start';
        micBtn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1-9c0-.55.45-1 1-1s1 .45 1 1v6c0 .55-.45 1-1 1s-1-.45-1-1V5z"/><path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>';
        micHint.textContent = 'Click to start';
        setStatus('disconnected', 'Disconnected');
        return;
    }

    micBtn.className = 'mic-btn start recording-ready';
    micBtn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1-9c0-.55.45-1 1-1s1 .45 1 1v6c0 .55-.45 1-1 1s-1-.45-1-1V5z"/><path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>';
    micHint.textContent = 'Tap to speak';
    setStatus('connected', '✅ Ready');
}

function stopSession() {
    isRunning = false;
    isRecording = false;
    isProcessing = false;
    releaseRecording();
    flushAudio();
    resetMicButton();
    muteBtn.classList.remove('visible', 'muted');
    muteIndicator.classList.remove('visible');
    micArea.classList.remove('is-muted', 'is-recording');
    addMsg('system', 'Session ended.');

    // Trigger action plan generation if available
    if (sessionId) {
        fetchActionPlan(sessionId);
    }
}

// ── Text input support ───────────────────────────────────────────

async function sendTextMessage() {
    const input = textInput || document.getElementById('textInput');
    if (!input || !input.value.trim()) return;
    if (!isRunning) {
        // Auto-start a session
        setStatus('connecting', 'Starting...');
        if (!(await createSession())) return;
        isRunning = true;
    }

    const text = input.value.trim();
    input.value = '';
    addMsg('user', text);

    isProcessing = true;
    setStatus('connected', '⏳ Thinking...');

    try {
        const resp = await apiFetch(
            () => `${API_BASE}/voice/chat`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    message: text,
                    tts_speaker: selectedSpeaker,
                    tts_language: selectedTTSLanguage,
                    synthesize_speech: false,
                }),
            }
        );

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `Server error ${resp.status}`);
        }

        const data = await resp.json();

        // Show tool calls
        if (data.tool_calls_made && data.tool_calls_made.length > 0) {
            data.tool_calls_made.forEach(tool => {
                addToolEntry(tool, '✅ completed');
            });
        }

        // Show agent text response formatted
        if (data.agent_text) {
            addMsg('agent', data.agent_text, { audioBase64: data.audio_base64 });
        }

        // Update case state
        if (typeof pollCase === 'function') {
            await pollCase();
        }

    } catch (e) {
        addMsg('system', `⚠️ Error: ${e.message}`);
    }

    isProcessing = false;
    resetMicButton();
}

// ── TTS helper ───────────────────────────────────────────────────

async function speakText(text, langCode) {
    try {
        const resp = await fetch(VOICE_API.TTS, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: text,
                language_code: langCode || selectedTTSLanguage,
                speaker: selectedSpeaker,
                pace: 1.0,
            }),
        });
        const data = await resp.json();
        if (data.audio_base64) {
            playAudioBase64(data.audio_base64);
        }
    } catch (e) {
        console.warn('[voice] TTS failed:', e);
    }
}

// ── Utilities ────────────────────────────────────────────────────

function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => {
            const base64 = reader.result.split(',')[1];
            resolve(base64);
        };
        reader.onerror = reject;
        reader.readAsDataURL(blob);
    });
}

// ── Language change handler ──────────────────────────────────────

function onLanguageChange(e) {
    const code = e.target.value;
    selectedLanguage = code;
    if (code !== 'auto') {
        selectedTTSLanguage = code;
    }
    console.log(`[voice] Language set to: ${code}`);
}

// ── Mute / unmute ────────────────────────────────────────────────

function toggleMute() {
    if (!isRunning) return;
    isMuted = !isMuted;
    updateMuteUI();
    addMsg('system', isMuted ? '🔇 Microphone muted' : '🎙️ Microphone unmuted');
}

function updateMuteUI() {
    if (isMuted) {
        muteBtn.classList.add('muted');
        muteBtn.title = 'Unmute mic';
        muteBtn.setAttribute('aria-label', 'Unmute microphone');
        if (muteIconUnmuted) muteIconUnmuted.style.display = 'none';
        if (muteIconMuted) muteIconMuted.style.display = 'block';
        muteIndicator.classList.add('visible');
        micArea.classList.add('is-muted');
        if (isRunning) {
            micHint.textContent = 'Muted — click 🔇 to unmute';
            setStatus('connected', '🔇 Muted');
        }
    } else {
        muteBtn.classList.remove('muted');
        muteBtn.title = 'Mute mic';
        muteBtn.setAttribute('aria-label', 'Mute microphone');
        if (muteIconUnmuted) muteIconUnmuted.style.display = 'block';
        if (muteIconMuted) muteIconMuted.style.display = 'none';
        muteIndicator.classList.remove('visible');
        micArea.classList.remove('is-muted');
        if (isRunning) {
            micHint.textContent = 'Tap to speak';
            setStatus('connected', '✅ Ready');
        }
    }
}
