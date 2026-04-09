# AI Study Assistant

A full-stack study app: upload course material (PDF, text, images), generate flashcards and quizzes with **OpenAI**, review cards with **SM-2** scheduling, chat with a learning tutor, and view review statistics.

## Features

- **Decks** — Create, rename, delete; upload or replace documents (PDF, Markdown/text, images).
- **Extraction** — PDF text extraction; vision transcription for images and sparse PDFs (OpenAI vision).
- **Flashcards** — Manual or AI-generated from deck material; four-button review (again / hard / good / easy).
- **Learning chat** — Per-deck sessions with optional context from uploaded material.
- **Quiz** — AI-generated multiple-choice and short-answer; grading (MC + AI-assisted short answers).
- **Statistics** — Charts for upcoming reviews and interval distribution.

## Stack

| Layer    | Tech                          |
| -------- | ----------------------------- |
| Frontend | React 18, TypeScript, Vite    |
| Backend  | FastAPI, SQLAlchemy, SQLite   |
| AI       | OpenAI API (chat + vision)    |

## Prerequisites

- **Node.js** 18+ (for the frontend)
- **Python** 3.11+ (for the backend)
- An **OpenAI API key** (for generation, chat, quiz, grading, and image/PDF vision)

## Quick start

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Copy `backend/.env.example` to `backend/.env` and set:

- `OPENAI_API_KEY` — required for AI features
- `OPENAI_MODEL` — optional (default `gpt-4o-mini`)
- `OPENAI_VISION_MODEL` — optional for images / PDF vision fallback

Start the API (example port `8080`):

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8080
```

Health check: `http://127.0.0.1:8080/api/health`

### 2. Frontend

```bash
cd frontend
npm install
```

Copy `frontend/.env.example` to `frontend/.env` and set `VITE_API_PROXY` to your backend URL, e.g.:

```env
VITE_API_PROXY=http://127.0.0.1:8080
```

```bash
npm run dev
```

Open the URL shown in the terminal (usually `http://localhost:5173`).

## Project layout

```
AI Study Assistant/
├── backend/          # FastAPI app, SQLite DB, uploads under backend/data/
├── frontend/         # React + Vite SPA
├── SRS_AI_Study_Assistant.txt   # SRS (plain text)
└── SRS_AI_Study_Assistant.html  # SRS (paste into Google Docs)
```

## Tests

From `backend/`:

```bash
# Unit tests
python -m unittest discover -s tests -v

# End-to-end API tests (separate folder; uses temp DB)
python -m unittest e2e.test_api_e2e -v
```

See `backend/tests/RUN_TESTS.txt` and `backend/e2e/RUN_E2E.txt`.

## Notes

- Data is stored locally under `backend/data/` (SQLite + uploads). Add `backend/.env` to `.gitignore` if not already ignored.
- **Security:** This project is intended for **local / personal** use. There is no built-in login; do not expose the API to the internet without authentication and HTTPS.

## License

Use and modify for your course or personal projects as needed.
