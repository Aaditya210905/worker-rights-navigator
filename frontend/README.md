# WorkerSaathi — Frontend

Zero-dependency voice web client for WorkerSaathi. Plain HTML/CSS/JS — **no build
step, no npm install**. It is served by the FastAPI backend at `GET /voice`
(`../backend/app/main.py` mounts `css/` at `/css` and `js/` at `/js`).

## Layout

```
frontend/
├── index.html          # Page shell + markup (header, chat, side panel, modal)
├── css/
│   ├── 01-base.css       # Design tokens, reset, base typography
│   ├── 02-layout.css     # Header, main grid, chat + side panels
│   ├── 03-components.css # Chat bubbles, mic hero, mute, waveform, progress tracker, tool log
│   ├── 04-responsive.css # Reduced-motion + tablet/mobile/desktop breakpoints
│   └── 05-modal.css      # LeMUR action-plan modal + spinner
└── js/
    ├── config.js       # API/WS base URLs, audio constants, progress steps
    ├── state.js        # Session state (socket, audio ctx, flags) + DOM references
    ├── ui.js           # Chat rendering, status badge, progress tracker
    ├── audio.js        # Mic capture, PCM playback scheduling, visualizer
    ├── api.js          # REST: create session, poll case, fetch action plan
    ├── voice.js        # WebSocket lifecycle: start/stop, mute, server events
    └── main.js         # Entry point: binds mic/mute buttons
```

## Notes

- **Load order matters.** The scripts are *classic* scripts (not ES modules) that
  share one global scope, so `index.html` loads them in dependency order:
  `config → state → ui → audio → api → voice → main`.
  Converting them to ES modules (`import`/`export`) is a possible follow-up.
- **CSS cascade order** is fixed by the numeric filename prefixes and the
  `<link>` order in `index.html`.
- `config.js` derives the API/WS origin from `window.location`, so the client
  must be served by the backend (or a reverse proxy on the same origin).
- Microphone access requires `https://` or `localhost`.
- Dependencies: Google Fonts (Plus Jakarta Sans, Noto Sans Devanagari, Material
  Symbols) and the Web Audio API.

## Run

Through the backend (recommended):

```bash
cd backend && uvicorn app.main:app --reload
# open http://127.0.0.1:8000/voice
```

The folder can also be served by any static file server, but requests to the
API/WebSocket will then point at that server's origin instead of the backend.
