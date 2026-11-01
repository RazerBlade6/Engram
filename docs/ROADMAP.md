# Engram roadmap

The phases, and what is done and left in each. The [design](README.md) says what Engram is and how it works; D1, D2 and so on are entries in the [decision log](DECISIONS.md).

## Phase 0: Design

- [x] This roadmap and the [design](README.md)
- [x] Clickable prototype of the core screens: home, review, course view, chat, upload ([`design/prototype`](../design/prototype/index.html))
- [x] Walkthrough with target users ([script](usability/mockup-walkthrough.md)), with its [findings](OBSERVATIONS.md#phase-0-prototype-walkthrough) folded back into the design

## Phase 1: Functional core ✓

The smallest end-to-end product, live at https://engramstudy.app (invite-only). Tested by developers, not yet handed to users for daily study.

- [x] Repo scaffold: FastAPI, worker, Next.js, Docker Compose, CI (lint, types, tests)
- [x] Supabase project: schema, auth (invite-only), private storage
- [x] Ingestion: PDF and slides → Docling → figure captions → section-aware chunks → index
- [x] Minimal ingestion inspector (admin)
- [x] Courses, table of contents, "mark chapter covered"
- [x] Student upload for slides (PDF, PowerPoint): a large upload button and drop zone, kept visually separate from link entry
- [x] Courses created in the app (students for themselves, admins for anyone); admins add textbooks from the course page
- [x] A navigation bar on every signed-in page, so nothing is reachable only by typing its address
- [x] Card generation: Q → A, cloze, MCQ, with source citations
- [x] FSRS review with four ratings, keyboard controls and an in-review flag button
- [x] Review ordering (mixed, blocked, separate) behind an admin-only switch
- [x] Cited chat with click-through to the highlighted source page
- [x] Calendar: quick-add for exams, quizzes and deadlines; month grid with an upcoming list; next dates on Today
- [x] Usage event logging
- [x] Deploy: web on Vercel, API on Cloud Run, worker on Modal (woken by new jobs, with a periodic sweep for retries), deployed from `main` by CI, so users can use Engram on their own devices
- [x] **Exit:** a moderated usability session with a target user, on the deployed app ([script and observations](OBSERVATIONS.md#phase-1-exit-session))

## Phase 2: UI/UX

A dedicated pass on design and friction. Daily use by users starts at the end of this phase.

Designed directly in the app and reviewed on the local dev server, without a separate prototype (D56).

- [x] Visual direction: palette, type, and the overall look (D57–D59)
- [ ] Design system: tokens, components, light theme (tokens structured so a dark theme can be added without a redesign)
- [ ] Redesign the core flows from the Phase 1 session findings ([findings](OBSERVATIONS.md#phase-1-findings)):
  - [x] Dates written out and entered day/month/year (D54)
  - [x] Report control moved to the card's corner (D52)
  - [x] Card generation shows its progress (D53)
  - [x] Blocked review order as the default (D55)
- [ ] Changes from the second round of testing ([findings](OBSERVATIONS.md#second-round-findings)):
  - [x] A less zoomed-in interface at the same text size; review fits a 14-inch 1920×1080 laptop (a 1280×590 viewport) without scrolling (D63)
  - [x] Ask without the intro text (D64)
  - [x] Citations in Ask open the passage as text (D65)
  - [x] Chapter picker: covered chapters first, a range, the full list one step away; placed above Add (D66)
  - [x] Sidebar menu on phones (D67)
  - [x] Review on phones: ratings pinned to the bottom, source directly under the card (D68)
  - [x] Week-by-week calendar on phones (D69)
  - [x] Ask answers sized for phones; a send icon inside the question field and Clear above the conversation (D70)
- [x] Welcome tour on the first visit: a few cards walking through Today, courses, review, Calendar and Ask, with back, next and skip, ending on "Start your first review" (D60)
- [ ] Empty states, loading states, error states, including a stalled or failed upload
  - [x] A job whose worker dies on every attempt is given up on and shown as failed; a material or chapter shows as failed only once its job has (D71)
  - [x] An upload that stops making progress is stopped with a message, and a failed background check no longer replaces the course page
- [ ] Mobile pass for review
- [ ] **Exit:** a second moderated session where a user on a fresh account takes their first meaningful action within 5 seconds, then users begin daily study

## Phase 3: Depth for studying

- [ ] Review-order experiment in the first weeks of daily use: blocked against separate, then fix the preferred one (D55)
- [ ] Session goals (general revision, a quiz, a project), explored alongside exam focus mode
- [ ] More sources in the drop zone: photographed and typed notes, web articles via URL ("Add a link instead")
- [ ] Short-answer cards with LLM grading
- [ ] Concepts, mastery and the weak-spots view
- [ ] Syllabus upload with date extraction, confirmed in one click
- [ ] Exam focus mode: chapters mapped to exams, prioritized ahead of the date
- [ ] Anki export
- [ ] Eval suites in CI: retrieval, card quality, grading

## Phase 4: Showcase depth

- [ ] Image occlusion cards for diagrams
- [ ] Rubric-graded essay prompts
- [ ] Model benchmark and benchmark-driven routing
- [ ] Public demo account on OpenStax courses, including CS and STEM titles
- [ ] Polished ingestion inspector
- [ ] Dark theme as an option; light stays the default
- [ ] Published aggregate usage statistics
- [ ] Fitted learner model compared against the FSRS baseline
