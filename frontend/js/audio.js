/**
 * audio.js — Microphone capture, agent audio playback and the visualizer.
 *
 * Talks to the Web Audio API only; it never creates sessions or sockets.
 */

// ── Agent audio playback ─────────────────────────────────────────
// AssemblyAI output is PCM16 mono at 24 kHz (see config.js).

function playAudioChunk(base64) {
    if (!audioCtx) return;
    // Resume audio context if suspended (browser autoplay policy)
    if (audioCtx.state === 'suspended') audioCtx.resume();

    // Decode base64 safely (no spread operator — avoids stack overflow)
    const binaryStr = atob(base64);
    const bytes = new Uint8Array(binaryStr.length);
    for (let i = 0; i < binaryStr.length; i++) bytes[i] = binaryStr.charCodeAt(i);

    // Convert PCM16 LE to Float32
    const samples = new Int16Array(bytes.buffer);
    const floats = new Float32Array(samples.length);
    for (let i = 0; i < samples.length; i++) floats[i] = samples[i] / 32768;

    // Create audio buffer at AssemblyAI's output rate
    const buf = audioCtx.createBuffer(1, floats.length, AAI_SAMPLE_RATE);
    buf.getChannelData(0).set(floats);

    // Schedule gapless playback with a small lookahead to prevent choppy speech
    const src = audioCtx.createBufferSource();
    src.buffer = buf;
    src.connect(audioCtx.destination);

    const now = audioCtx.currentTime;
    // If we've fallen behind, re-anchor with a tiny buffer for smoothness
    if (nextPlayTime < now) nextPlayTime = now + AUDIO_BUFFER_MS;
    src.start(nextPlayTime);
    nextPlayTime += buf.duration;
}

function flushAudio() {
    // Reset scheduling so next chunk starts immediately
    nextPlayTime = 0;
}

// ── Microphone capture + visualizer ──────────────────────────────

async function startAudioPipeline() {
    // 4. Get microphone
    try {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    } catch (e) {
        addMsg('system', 'Microphone access denied. Please allow microphone access.');
        stopSession();
        return;
    }

    const micCtx = new AudioContext({ sampleRate: 16000 });
    const source = micCtx.createMediaStreamSource(micStream);

    // ── Visualizer setup ──────────────────────────────────────────
    const analyser = micCtx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const canvas = document.getElementById('audioVisualizer');
    const canvasCtx = canvas.getContext('2d');

    // Match canvas logical size to physical CSS size
    canvas.width = 140;
    canvas.height = 140;

    function drawVisualizer() {
        if (!isRunning) return; // Stop animation loop when session ends
        requestAnimationFrame(drawVisualizer);

        analyser.getByteFrequencyData(dataArray);

        // Calculate average volume
        let sum = 0;
        for(let i = 0; i < bufferLength; i++) {
            sum += dataArray[i];
        }
        let average = sum / bufferLength;

        canvasCtx.clearRect(0, 0, canvas.width, canvas.height);

        // Draw circle that scales with volume
        let radius = 35 + (average / 255) * 30; // base radius 35, max 65

        canvasCtx.beginPath();
        canvasCtx.arc(canvas.width/2, canvas.height/2, radius, 0, 2 * Math.PI, false);
        canvasCtx.fillStyle = 'rgba(224, 122, 47, 0.5)'; // Saffron tint
        canvasCtx.fill();

        // Optionally, draw a second inner circle
        canvasCtx.beginPath();
        canvasCtx.arc(canvas.width/2, canvas.height/2, radius * 0.7, 0, 2 * Math.PI, false);
        canvasCtx.fillStyle = 'rgba(224, 122, 47, 0.8)';
        canvasCtx.fill();
    }

    drawVisualizer();
    // ──────────────────────────────────────────────────────────────

    scriptProcessor = micCtx.createScriptProcessor(4096, 1, 1);

    scriptProcessor.onaudioprocess = (e) => {
        if (!isRunning || !ws || ws.readyState !== 1) return;
        // When muted, don't send audio — session stays alive
        if (isMuted) return;
        const float32 = e.inputBuffer.getChannelData(0);
        const int16 = new Int16Array(float32.length);
        for (let i = 0; i < float32.length; i++) {
            int16[i] = Math.max(-32768, Math.min(32767, Math.floor(float32[i] * 32768)));
        }
        // Safe base64 encode (chunk to avoid stack overflow)
        const uint8 = new Uint8Array(int16.buffer);
        let binary = '';
        for (let i = 0; i < uint8.length; i++) binary += String.fromCharCode(uint8[i]);
        const base64 = btoa(binary);
        ws.send(JSON.stringify({ type: 'input.audio', audio: base64 }));
    };

    source.connect(scriptProcessor);
    scriptProcessor.connect(micCtx.destination);

    return true;
}

/**
 * Release every audio resource created by startAudioPipeline().
 * Called by voice.stopSession() and on microphone-permission failure.
 */
function stopAudioPipeline() {
    if (micStream) {
        micStream.getTracks().forEach(t => t.stop());
        micStream = null;
    }
    if (scriptProcessor) {
        scriptProcessor.disconnect();
        scriptProcessor = null;
    }

    const canvas = document.getElementById('audioVisualizer');
    if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
}
