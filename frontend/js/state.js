/**
 * state.js — Mutable session state and cached DOM references.
 *
 * Loaded second. Kept in one place so every other module reads/writes the
 * same session, audio and streaming state.
 */

// ── Session state ────────────────────────────────────────────────
let sessionId = null;
let audioCtx = null;
let micStream = null;
let isRunning = false;
let isMuted = false;
let isRecording = false;
let isProcessing = false; // True while waiting for Sarvam STT/TTS response
let mediaRecorder = null;
let audioChunks = [];

// ── Language settings ────────────────────────────────────────────
let selectedLanguage = 'auto';     // STT input language
let selectedTTSLanguage = 'hi-IN'; // TTS output language
let selectedSpeaker = 'shubh';    // TTS voice persona (valid Bulbul v3 speaker)

// ── DOM references ───────────────────────────────────────────────
const badge = document.getElementById('statusBadge');
const micBtn = document.getElementById('micBtn');
const micHint = document.getElementById('micHint');
const chatEl = document.getElementById('chatMessages');
const toolLog = document.getElementById('toolLog');
const muteBtn = document.getElementById('muteBtn');
const muteIndicator = document.getElementById('muteIndicator');
const micArea = document.getElementById('micArea');
const muteIconUnmuted = document.getElementById('muteIconUnmuted');
const muteIconMuted = document.getElementById('muteIconMuted');
const langSelect = document.getElementById('langSelect');
const textInput = document.getElementById('textInput');
const sendTextBtn = document.getElementById('sendTextBtn');

// ── Streaming agent bubble state ─────────────────────────────────
let streamingBubble = null;
let streamingTextNode = null;
let streamingTextAccum = '';

// ── Audio playback state ─────────────────────────────────────────
let nextPlayTime = 0;
