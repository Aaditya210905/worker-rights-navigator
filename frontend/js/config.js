/**
 * config.js — Backend endpoints, audio constants and UI step definitions.
 *
 * Loaded first: everything else reads these values.
 */

// ── Backend endpoints (same origin as the page) ───────────────────
const API_BASE = window.location.origin + '/api/v1';

// ── Voice API endpoints ──────────────────────────────────────────
const VOICE_API = {
    STT: API_BASE + '/voice/stt',
    TTS: API_BASE + '/voice/tts',
    CONVERSE: API_BASE + '/voice/converse',
    LANGUAGES: API_BASE + '/voice/languages',
    SPEAKERS: API_BASE + '/voice/speakers',
};

// ── Audio pipeline constants ─────────────────────────────────────
// Sarvam outputs audio at 24kHz
const SARVAM_SAMPLE_RATE = 24000;
// Small lookahead buffer (50ms) to smooth out jitter from network delays
const AUDIO_BUFFER_MS = 0.05;
// Recording settings
const RECORDING_SAMPLE_RATE = 16000;
const RECORDING_CHANNELS = 1;

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

// ── Supported languages ──────────────────────────────────────────
const DEFAULT_LANGUAGES = [
    { code: 'auto', name: 'Auto Detect', native: '🌐 Auto' },
    { code: 'hi-IN', name: 'Hindi', native: 'हिन्दी' },
    { code: 'en-IN', name: 'English', native: 'English' },
    { code: 'bn-IN', name: 'Bengali', native: 'বাংলা' },
    { code: 'ta-IN', name: 'Tamil', native: 'தமிழ்' },
    { code: 'te-IN', name: 'Telugu', native: 'తెలుగు' },
    { code: 'mr-IN', name: 'Marathi', native: 'मराठी' },
    { code: 'gu-IN', name: 'Gujarati', native: 'ગુજરાતી' },
    { code: 'kn-IN', name: 'Kannada', native: 'ಕನ್ನಡ' },
    { code: 'ml-IN', name: 'Malayalam', native: 'മലയാളം' },
    { code: 'pa-IN', name: 'Punjabi', native: 'ਪੰਜਾਬੀ' },
    { code: 'od-IN', name: 'Odia', native: 'ଓଡ଼ିଆ' },
];
