/**
 * voice.js — Voice session lifecycle.
 *
 * Owns the websocket conversation with the backend proxy: start/stop the
 * session, stream microphone audio upstream, route backend events to the UI
 * and handle mute/unmute.
 */

async function toggleSession() {
    if (isRunning) {
        stopSession();
    } else {
        await startSession();
    }
}

// ── Start / stop session ─────────────────────────────────────────

async function startSession() {
    setStatus('connecting', 'Connecting...');
    micHint.textContent = 'Connecting...';

    // 1. Create the session through the REST API
    if (!(await createSession())) return;

    // 2. Audio context — use default sample rate for best playback quality
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();

    // 3. Connect WebSocket
    const wsUrl = `${WS_BASE}/voice/${sessionId}`;
    ws = new WebSocket(wsUrl);

    ws.onopen = async () => {
        setStatus('connected', 'Connected');

        // 4. Capture the microphone and start streaming audio upstream
        if (!(await startAudioPipeline())) return;

        isRunning = true;
        isMuted = false;
        micBtn.className = 'mic-btn stop recording';
        micBtn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M6 6h12v12H6z"/></svg>';
        micHint.textContent = 'Listening... click to end session';
        setStatus('listening', '🎤 Listening');
        // Show the mute button
        muteBtn.classList.add('visible');
        updateMuteUI();
    };

    ws.onmessage = handleServerEvent;

    ws.onclose = (e) => {
        if (isRunning) {
            // Detect keepalive timeout (1011) vs normal close
            if (e.code === 1011 || e.code === 1006) {
                addMsg('system', '⚠️ Connection timed out — the server may be processing a heavy request. Try starting a new session.');
            } else if (e.code !== 1000) {
                addMsg('system', `Connection closed (code: ${e.code})`);
            } else {
                addMsg('system', 'Connection closed');
            }
            stopSession();
        }
    };

    ws.onerror = (e) => {
        addMsg('system', '⚠️ WebSocket error — check your network connection');
    };
}

function stopSession() {
    isRunning = false;
    isMuted = false;
    if (ws && ws.readyState === 1) {
        try { ws.send(JSON.stringify({ type: 'session.end' })); } catch(e) {}
        ws.close();
    }
    ws = null;

    // Release microphone / audio-graph resources
    stopAudioPipeline();

    flushAudio();
    micBtn.className = 'mic-btn start';
    micBtn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1-9c0-.55.45-1 1-1s1 .45 1 1v6c0 .55-.45 1-1 1s-1-.45-1-1V5z"/><path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>';
    micHint.textContent = 'Click to start';
    setStatus('disconnected', 'Disconnected');
    // Hide mute button and reset mute state
    muteBtn.classList.remove('visible', 'muted');
    muteIndicator.classList.remove('visible');
    micArea.classList.remove('is-muted');
    updateMuteUI();
}

// ── Server events ────────────────────────────────────────────────

/**
 * Route a single event pushed by the backend websocket proxy.
 * @param {MessageEvent} e raw JSON event frame
 */
function handleServerEvent(e) {
    const event = JSON.parse(e.data);
    const type = event.type;

    // Debug: log all events to see what AssemblyAI sends
    if (type !== 'reply.audio') console.log('[ws]', type, event);

    if (type === 'session.ready') {
        addMsg('system', 'WorkerSaathi is ready. Speak now!');
    }
    else if (type === 'transcript.user') {
        const text = event.text;
        if (text && text.trim()) {
            finalizeStreamingBubble();
            addMsg('user', text);
        }
    }
    else if (type === 'transcript.agent.delta') {
        // Stream the text as it is generated!
        const textChunk = event.delta || event.text || "";
        if (textChunk) {
            if (!streamingBubble) {
                startStreamingBubble();
                streamingTextNode.textContent = "";
            }
            // If it currently says "Speaking...", clear it before appending
            if (streamingTextNode.textContent === 'Speaking...') {
                streamingTextNode.textContent = "";
            }
            streamingTextNode.textContent += textChunk;
            chatEl.scrollTop = chatEl.scrollHeight;
        }
    }
    else if (type === 'transcript.agent') {
        // Final complete transcript — replace "Speaking..." with actual text
        const text = event.text;
        const interrupted = event.interrupted;

        // Try JS reference first, then fallback to DOM lookup
        let bubble = streamingBubble;
        let textNode = streamingTextNode;

        if (!bubble) {
            // Find the last "Speaking..." bubble in the DOM
            const allAgentMsgs = chatEl.querySelectorAll('.msg.agent');
            for (let i = allAgentMsgs.length - 1; i >= 0; i--) {
                const span = allAgentMsgs[i].querySelector('.streaming-text');
                if (span && span.textContent === 'Speaking...') {
                    bubble = allAgentMsgs[i];
                    textNode = span;
                    break;
                }
            }
        }

        if (bubble && textNode && text && text.trim()) {
            textNode.textContent = text;
            if (interrupted) bubble.classList.add('interrupted');
            bubble.classList.remove('streaming');
            const cursor = bubble.querySelector('.typing-cursor');
            if (cursor) cursor.remove();
            streamingBubble = null;
            streamingTextNode = null;
        } else if (text && text.trim()) {
            const el = addMsg('agent', text);
            if (interrupted) el.classList.add('interrupted');
        }
        if (interrupted) flushAudio();
    }
    else if (type === 'reply.audio') {
        // Agent is speaking — show streaming bubble with speaking indicator
        if (!streamingBubble) {
            startStreamingBubble();
            updateStreamingBubble('Speaking...');
        }
        if (event.data) playAudioChunk(event.data);
    }
    else if (type === 'reply.done') {
        // Don't finalize streaming bubble here — transcript.agent will do it
        if (event.status === 'interrupted') {
            finalizeStreamingBubble();
            flushAudio();
        }
        pollCase();  // refresh side panel
    }
    else if (type === 'tool.call') {
        addToolEntry(event.name, '⏳ executing...');
    }
    else if (type === 'session.ended') {
        addMsg('system', 'Session ended. Generating action plan...');
        stopSession();
        if (sessionId) {
            fetchActionPlan(sessionId);
        }
    }
    else if (type === 'error') {
        addMsg('system', '⚠️ ' + (event.message || 'Unknown error'));
    }
}


// ── Mute / unmute (keeps the session alive) ──────────────────────

function toggleMute() {
    if (!isRunning) return;
    isMuted = !isMuted;
    updateMuteUI();
    addMsg('system', isMuted ? '🔇 Microphone muted — agent can\'t hear you' : '🎙️ Microphone unmuted — agent is listening');
}

function updateMuteUI() {
    if (isMuted) {
        muteBtn.classList.add('muted');
        muteBtn.title = 'Unmute mic';
        muteBtn.setAttribute('aria-label', 'Unmute microphone');
        muteIconUnmuted.style.display = 'none';
        muteIconMuted.style.display = 'block';
        muteIndicator.classList.add('visible');
        micArea.classList.add('is-muted');
        if (isRunning) {
            micHint.textContent = 'Muted — click 🔇 to unmute';
            setStatus('connected', '🔇 Muted');
        }
    } else {
        muteBtn.classList.remove('muted');
        muteBtn.title = 'Mute mic (keeps session alive)';
        muteBtn.setAttribute('aria-label', 'Mute microphone');
        muteIconUnmuted.style.display = 'block';
        muteIconMuted.style.display = 'none';
        muteIndicator.classList.remove('visible');
        micArea.classList.remove('is-muted');
        if (isRunning) {
            micHint.textContent = 'Listening... click to end session';
            setStatus('listening', '🎤 Listening');
        }
    }
}
