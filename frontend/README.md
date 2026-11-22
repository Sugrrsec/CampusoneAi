# CampusOne AI — Approved V6 Frontend

This is the **approved V6 design** converted into a runnable Vite frontend package. It intentionally uses the original HTML, CSS, and JavaScript rather than rebuilding the approved design in React. This keeps the *exact* handwriting transition, typography, layout and sidebar behavior intact. It is a complete browser frontend and can be connected directly to FastAPI without needing a rewrite.

## Run

Requirements: Node.js 20+ (or compatible current LTS).

```bash
npm install
npm run dev
```

Open the address displayed by Vite, usually `http://localhost:5173`.

Production build:

```bash
npm run build
npm run preview
```

The build output is `dist/`.

## Demo vs backend

Copy `.env.example` to `.env`.

- `VITE_USE_LIVE_API=false` (default): exact V6 UI with illustrative replies; chat history saved in browser localStorage.
- `VITE_USE_LIVE_API=true`: sends each student message to the existing FastAPI `POST /chat` endpoint, using `VITE_API_BASE_URL` (default `http://127.0.0.1:8000`). Responses and available source links appear in the chat. Backend must be running and CORS must permit the site origin.

**Important:** the login page is a name-entry preview, not authentication. Chat history remains per-browser localStorage; the current backend does not provide history or identity endpoints. Do not claim server-side history syncing. The API integration is provided but has **not been verified against a live backend** in this environment.

Backend API request shape: `{ "message": "...", "session_id": "..." }`. API response fields used: `answer`, `domains`, `sources`, and `metadata.status`. No fake login, payment, complaint, or history API endpoints are used.

## Files

- `index.html` — approved V6 interface markup
- `src/styles.css` — extracted original V6 CSS, including the full handwriting animation
- `src/main.js` — original V6 interaction code, history, entrance transition, and optional live-response rendering
- `src/api.js` — small fetch client for FastAPI `/chat`
- `reference/CampusOne-V6-original.html` — byte-for-byte V6 prototype for visual comparison
- `ANTIGRAVITY_PROMPT.md` — handoff instructions for safely integrating and committing to GitHub

## Visual regression requirements

**Do not shorten, skip, or change the welcome transition.** The timing in `runOpeningSequence` is 250ms preparation, **5200ms actual SVG handwriting**, **1800ms hold**, and **1400ms fade**, taking approximately 8.65 seconds. Avoid routing to a different page before completion. Do not replace SVG pen strokes with typewriter text or CSS letter reveals. Keep the translucent overlay and green writing on top of the existing screen.

## Notes for contributors

Maintain the warm off-white and forest-green palette, custom cursive CampusOne wordmark, sketch login artwork, top-bar hierarchy, distinct history/sidebar tint, and chat composer. Avoid unnecessary dependencies, marketing sections, gradients, or fabricated project capabilities.
