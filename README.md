# Engram

A study system that turns course materials into spaced-repetition practice.

Students bring textbooks, lecture slides, notes and readings. Engram parses them, generates flashcards and practice questions that cite the exact page they came from, schedules reviews with [FSRS](https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-Algorithm), and answers questions about the material when the student gets stuck.

> **Status: Phase 1 (functional core) in progress.** Phase 0 produced the roadmap and a clickable prototype tested with a target user. See [docs/ROADMAP.md](docs/ROADMAP.md).

## What it does

- **Review**: a daily queue of flashcards, fill-in-the-blank and multiple-choice questions, scheduled by FSRS. Keyboard-first: Space shows the answer, 1–4 rates it.
- **Cited sources**: every card and every answer links back to the passage it came from, highlighted on the original page.
- **Chapter-driven**: mark a chapter as covered in class, and Engram generates its cards.
- **Ask**: chat that answers from course material first, and labels anything that comes from general knowledge.
- **Calendar**: exams, quizzes and deadlines across courses, in one place.

## Planned stack

| Layer      | Choice                                                                 |
| ---------- | ---------------------------------------------------------------------- |
| Frontend   | Next.js (PWA) on Vercel                                                |
| Backend    | FastAPI and a background worker on Fly.io                              |
| Data       | Supabase: Postgres with pgvector and full-text search, Auth, Storage   |
| Ingestion  | Docling layout parsing, vision-model figure captions, section-aware chunks |
| LLMs       | Provider-agnostic layer; Claude for reasoning-heavy jobs               |
| Evaluation | Retrieval, card quality, grading and model-cost suites in CI           |

The reasoning behind each choice is in the roadmap's [decision log](docs/ROADMAP.md#decision-log).

## Repository layout

```text
backend/            FastAPI app (engram.api) and background worker (engram.worker), Python 3.13, uv
web/                Next.js app (App Router, TypeScript, Tailwind)
docker-compose.yml  Local stack: Postgres with pgvector, API, worker, web
design/prototype/   Clickable prototype of the core screens (single HTML file, open it in a browser)
docs/ROADMAP.md     Product, architecture, phases and decision log
docs/usability/     Usability session scripts
```

## Development

The whole stack, with hot reload:

```sh
docker compose up --build
```

The web app is on http://localhost:3000 and the API on http://localhost:8000 (interactive docs at `/docs`).

Or run each part directly:

```sh
cd backend
uv sync
uv run uvicorn engram.api.main:app --reload   # API
uv run engram-worker                          # worker
uv run ruff check . && uv run mypy && uv run pytest

cd web
npm install
npm run dev
npm run lint && npm run typecheck && npm test
```

CI runs the same lint, type and test checks on every push and pull request.

## History

Engram was originally called ScholarRAG: a single-afternoon "chat with your textbook" prototype. It has been rebuilt from scratch.
