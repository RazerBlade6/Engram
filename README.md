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
| Backend    | FastAPI on Cloud Run and a background worker on Modal                  |
| Data       | Supabase: Postgres with pgvector and full-text search, Auth, Storage   |
| Ingestion  | Docling layout parsing, vision-model figure captions, section-aware chunks |
| LLMs       | Provider-agnostic layer; Claude for reasoning-heavy jobs               |
| Evaluation | Retrieval, card quality, grading and model-cost suites in CI           |

The reasoning behind each choice is in the roadmap's [decision log](docs/ROADMAP.md#decision-log).

## Repository layout

```text
backend/            FastAPI app (engram.api) and background worker (engram.worker), Python 3.13, uv
web/                Next.js app (App Router, TypeScript, Tailwind)
supabase/           Database migrations, row-level security tests and local Supabase config
docker-compose.yml  Local stack: API, worker and web app (Supabase runs from its CLI)
design/prototype/   Clickable prototype of the core screens (single HTML file, open it in a browser)
docs/ROADMAP.md     Product, architecture, phases and decision log
docs/usability/     Usability session scripts
```

## Development

Requires Docker, the [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started), [uv](https://docs.astral.sh/uv/) and Node 24.

```sh
echo '[]' > supabase/signing_keys.json && supabase gen signing-key --algorithm ES256 --append   # once
supabase start                 # local Postgres, Auth and Storage, with migrations applied
cp .env.example .env           # then paste the Publishable and Secret keys from `supabase status`
docker compose up --build      # API, worker and web app, with hot reload
```

The web app is on http://localhost:3000, the API on http://localhost:8000 (interactive docs at `/docs`), Supabase Studio on http://localhost:54323, and invite emails are caught at http://localhost:54324.

Accounts are invite-only. To create the first admin locally, add a user in Studio (Authentication → Add user), then run `update profiles set role = 'admin' where id = '<user id>';` in the SQL editor. Admins invite others with `POST /admin/invites`.

### Ingesting a textbook

Admins add textbooks from the command line. The worker parses the file with Docling, describes each figure with a vision model (set `ANTHROPIC_API_KEY` in `.env`), embeds the chunks and builds the table of contents.

```sh
cd backend
uv run engram-admin create-course --owner student@example.com --title "Biology 101"
uv run engram-admin ingest ~/books/biology.pdf --course <course id>
uv run engram-admin materials            # status: queued → processing → ready (or failed, with the error)
```

The first ingestion downloads Docling's layout models and the embedding model (a few hundred MB); later runs reuse them.

Or run each part directly:

```sh
cd backend
uv sync --all-extras                          # the ingest extra brings Docling and PyTorch
uv run uvicorn engram.api.main:app --reload   # API
uv run engram-worker                          # worker
uv run ruff check . && uv run mypy && uv run pytest

cd web
npm install
npm run dev
npm run lint && npm run typecheck && npm test
```

Database changes are SQL migrations in `supabase/migrations/` (create one with `supabase migration new <name>`), and row-level security tests live in `supabase/tests/` (`supabase test db`). Migrations are applied to the hosted project when they reach `main`.

CI runs the schema linter, the row-level security tests, and the backend and web lint, type and test checks on every push and pull request.

## History

Engram was originally called ScholarRAG: a single-afternoon "chat with your textbook" prototype. It has been rebuilt from scratch.
