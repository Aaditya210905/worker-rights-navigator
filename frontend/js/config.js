/**
 * config.js — Backend endpoints, audio constants and UI step definitions.
 *
 * Loaded first: everything else reads these values.
 */

// ── Backend endpoints (same origin as the page) ───────────────────
const API_BASE = window.location.origin + '/api/v1';
const WS_BASE = (window.location.protocol === 'https:' ? 'wss:' : 'ws:') +
    '//' + window.location.host + '/api/v1';

// ── Audio pipeline constants ─────────────────────────────────────
// AssemblyAI outputs PCM16 mono at 24kHz
const AAI_SAMPLE_RATE = 24000;
// Small lookahead buffer (50ms) to smooth out jitter from network delays
const AUDIO_BUFFER_MS = 0.05;

// ── Case progress steps (presentation only) ──────────────────────
const STATUS_ORDER = [
    'new,listening',
    'classified',
    'collecting_information,safety_check',
    'retrieving_rights',
    'rights_verified',
    'action_plan_ready',
    'evidence_generated'
];
