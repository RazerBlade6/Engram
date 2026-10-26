# Engram

A study system that turns course materials into spaced-repetition practice.

Students bring textbooks, lecture slides, notes and readings. Engram parses them, generates flashcards and practice questions that cite the exact page they came from, schedules reviews with [FSRS](https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-Algorithm), and answers questions about the material when the student gets stuck.

> **Status: Phase 0 (design) complete.** The roadmap is final and a clickable prototype has been tested with a target user. Next: Phase 1, the functional core. See [docs/ROADMAP.md](docs/ROADMAP.md).

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
design/prototype/   Clickable prototype of the core screens (single HTML file, open it in a browser)
docs/ROADMAP.md     Product, architecture, phases and decision log
docs/usability/     Usability session scripts
```

Application code arrives in Phase 1.

## History

Engram was originally called ScholarRAG: a single-afternoon "chat with your textbook" prototype. It has been rebuilt from scratch.
