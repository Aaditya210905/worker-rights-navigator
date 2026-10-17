/**
 * state.js — Mutable session state and cached DOM references.
 *
 * Loaded second. Kept in one place so every other module reads/writes the
 * same session, audio and streaming state.
 */

// ── Session state ────────────────────────────────────────────────
let sessionId = null;
let ws = null;
let audioCtx = null;
let micStream = null;
let scriptProcessor = null;
let isRunning = false;
let isMuted = false;

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

// ── Streaming agent bubble state ─────────────────────────────────
let streamingBubble = null;
let streamingTextNode = null;
let streamingTextAccum = '';

// ── Audio playback state ─────────────────────────────────────────
let nextPlayTime = 0;
