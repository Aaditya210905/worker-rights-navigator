/**
 * audio.js — Microphone capture, recording, and agent audio playback.
 *
 * Uses MediaRecorder to capture audio → sends to /voice/converse.
 * Plays back Sarvam TTS audio via Web Audio API.
 */

// ── Agent audio playback ─────────────────────────────────────────

function playAudioBase64(base64) {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === 'suspended') audioCtx.resume();

    // Decode base64 safely
    const binaryStr = atob(base64);
    const bytes = new Uint8Array(binaryStr.length);
    for (let i = 0; i < binaryStr.length; i++) bytes[i] = binaryStr.charCodeAt(i);

    // Decode as WAV/MP3 (Sarvam returns full audio files)
    audioCtx.decodeAudioData(bytes.buffer.slice(0), (buffer) => {
        const src = audioCtx.createBufferSource();
        src.buffer = buffer;
        src.connect(audioCtx.destination);
        src.start(0);
    }, (err) => {
        console.warn('[audio] Failed to decode audio:', err);
    });
}

function flushAudio() {
    nextPlayTime = 0;
}

// ── MediaRecorder-based recording ────────────────────────────────

async function startRecording() {
    try {
        micStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                sampleRate: RECORDING_SAMPLE_RATE,
                channelCount: RECORDING_CHANNELS,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            }
        });
    } catch (e) {
        addMsg('system', '🎙️ Microphone access denied. Please allow microphone access.');
        return false;
    }

    audioChunks = [];

    // Use webm/opus for browser compat
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';

    mediaRecorder = new MediaRecorder(micStream, { mimeType });

    mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.start();
    isRecording = true;

    // Start visualizer
    startVisualizer();

    return true;
}

function stopRecording() {
    return new Promise((resolve) => {
        if (!mediaRecorder || mediaRecorder.state === 'inactive') {
            resolve(null);
            return;
        }

        mediaRecorder.onstop = () => {
            const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType });
            audioChunks = [];
            isRecording = false;
            resolve(blob);
        };

        mediaRecorder.stop();
    });
}

function releaseRecording() {
    if (micStream) {
        micStream.getTracks().forEach(t => t.stop());
        micStream = null;
    }
    if (mediaRecorder) {
        mediaRecorder = null;
    }
    isRecording = false;
    stopVisualizer();
}

// ── Visualizer ──────────────────────────────────────────────────

let analyserNode = null;
let analyserCtx = null;
let animationId = null;

function startVisualizer() {
    if (!micStream) return;

    analyserCtx = new AudioContext({ sampleRate: RECORDING_SAMPLE_RATE });
    const source = analyserCtx.createMediaStreamSource(micStream);
    analyserNode = analyserCtx.createAnalyser();
    analyserNode.fftSize = 256;
    source.connect(analyserNode);

    const canvas = document.getElementById('audioVisualizer');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    canvas.width = 140;
    canvas.height = 140;

    const bufferLength = analyserNode.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    function draw() {
        if (!isRecording && !isRunning) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            return;
        }
        animationId = requestAnimationFrame(draw);

        analyserNode.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < bufferLength; i++) sum += dataArray[i];
        let average = sum / bufferLength;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Outer glow
        let radius = 35 + (average / 255) * 30;
        ctx.beginPath();
        ctx.arc(canvas.width / 2, canvas.height / 2, radius, 0, 2 * Math.PI);
        ctx.fillStyle = isRecording
            ? 'rgba(239, 68, 68, 0.4)'   // Red pulse while recording
            : 'rgba(224, 122, 47, 0.5)';  // Saffron while idle
        ctx.fill();

        // Inner circle
        ctx.beginPath();
        ctx.arc(canvas.width / 2, canvas.height / 2, radius * 0.7, 0, 2 * Math.PI);
        ctx.fillStyle = isRecording
            ? 'rgba(239, 68, 68, 0.7)'
            : 'rgba(224, 122, 47, 0.8)';
        ctx.fill();
    }

    draw();
}

function stopVisualizer() {
    if (animationId) {
        cancelAnimationFrame(animationId);
        animationId = null;
    }
    if (analyserCtx) {
        analyserCtx.close().catch(() => {});
        analyserCtx = null;
        analyserNode = null;
    }
    const canvas = document.getElementById('audioVisualizer');
    if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
}
