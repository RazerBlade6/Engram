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

## Phase 2: UI/UX ✓

A dedicated pass on design and friction. Daily use by users starts at the end of this phase.

Designed directly in the app and reviewed on the local dev server, without a separate prototype (D56).

- [x] Visual direction: palette, type, and the overall look (D57–D59)
- [x] Design system: tokens, components, light theme, and a dark theme from the same tokens, all shown live at `/styleguide` (D75)
- [x] Redesign the core flows from the Phase 1 session findings ([findings](OBSERVATIONS.md#phase-1-findings)):
  - [x] Dates written out and entered day/month/year (D54)
  - [x] Report control moved to the card's corner (D52)
  - [x] Card generation shows its progress (D53)
  - [x] Blocked review order as the default (D55)
- [x] Changes from the second round of testing ([findings](OBSERVATIONS.md#second-round-findings)):
  - [x] A less zoomed-in interface at the same text size; review fits a 14-inch 1920×1080 laptop (a 1280×590 viewport) without scrolling (D63)
  - [x] Ask without the intro text (D64)
  - [x] Citations in Ask open the passage as text (D65)
  - [x] Chapter picker: covered chapters first, a range, the full list one step away; placed above Add (D66)
  - [x] Sidebar menu on phones (D67)
  - [x] Review on phones: ratings pinned to the bottom, source directly under the card (D68)
  - [x] Week-by-week calendar on phones (D69)
  - [x] Ask answers sized for phones; a send icon inside the question field and Clear above the conversation (D70)
- [x] Welcome tour on the first visit: a few cards walking through Today, courses, review, Calendar and Ask, with back, next and skip, ending on "Start your first review" (D60)
- [x] Empty states, loading states, error states, including a stalled or failed upload
  - [x] A job whose worker dies on every attempt is given up on and shown as failed; a material or chapter shows as failed only once its job has (D71)
  - [x] An upload that stops making progress is stopped with a message, and a failed background check no longer replaces the course page
  - [x] A file that can't be read says why: scanned pages with no text, a password, a damaged file, or reading that took too long; such files fail at once instead of being retried (D72)
  - [x] A chapter whose cards couldn't be made has a Try again button, and a file being read shows its step: waiting, reading, looking at figures, almost ready (D73)
  - [x] A card batch that fails is sent again, a chapter whose cards are all dropped shows as failed rather than ready with none, an interrupted upload has Try again, and an ended session goes to sign-in with a note saying so (D74)
- [x] Mobile pass for review: ratings pinned to the bottom, the source under the card, and a fit for short laptop screens (D63, D68)
- [x] **Exit:** a second moderated session where a user on a fresh account takes their first meaningful action within 5 seconds, then users begin daily study (findings being written up in [OBSERVATIONS.md](OBSERVATIONS.md))

## Phase 3: Depth for studying

Daily use has begun. Findings from it and from the Phase 2 exit session are collected for Phase 4 rather than fixed one at a time, unless something stops users studying, which is fixed at once (D76).

- [ ] The worker on GKE Autopilot, benchmarked against Modal to decide which runs the production worker (D104–D106). Modal stays the production worker while the benchmark runs:
  - [ ] Benchmark database: a separate Supabase project with the same schema and a fixed set of OpenStax chapters, and a second Modal app pointed at it, so production is never touched (D105)
  - [ ] A worker entry point that drains one kind of job and exits, and Docling's models built into the worker image
  - [ ] Helm chart: a KEDA ScaledJob for each kind of job, scaled on the number of jobs ready and down to zero when there are none, with reading and card making on separate compute classes sized like Modal's; tried on a local cluster (kind) before GKE (D106)
  - [ ] Cluster scripts: create the Autopilot cluster, install KEDA and the chart, and delete it all again
  - [ ] Benchmark script: queues the same materials and chapters on each platform and records, from the jobs table, the wait before a job starts, its run time and the time end to end, from a cold start and while warm, with reused figure descriptions cleared between runs
  - [ ] Results written up (wait before a job starts, run time, cost a month at our size, and the upkeep each needs), and a decision from them: keep Modal, or move the production worker to GKE without interrupting users
- [x] Ready for daily use (D79):
  - [x] Email alerts, sent by the worker's sweep every 15 minutes: a job that failed or hasn't started within an hour, an error in the API, and estimated inference spend over $5 in a day or $30 in a month (D99); an uptime check emails when the API stops answering
  - [x] Supabase backups confirmed
  - [x] Each user's consent to usage logging confirmed, before the review-order experiment starts
- [ ] Faster answers in Ask, which took 15–20 s to start on the first question after the API started (D89):
  - [x] Each answer logs how long each step took (embedding, search, first words, total) and its size, never its text
  - [x] The embedding model loads while the API starts, from the copy in the image, without first asking Hugging Face for a newer one
  - [x] The sign-in page wakes the API, so it's running by the time the user is signed in
  - [ ] Try Sonnet against Opus for Ask in the eval suite: faster to start and to write, if its answers hold up
  - [ ] Only if these aren't enough: keep one API instance running, or move the API to a host without cold starts, within the cost ceiling (D90)
- [x] Hardening: things that work today but break easily (D91–D97)
  - [x] A card keeps the text of its source passage, and an ingest skips a material that is already ready, so reading a material again never strips its cards' sources (D91)
  - [x] Card jobs run alongside a textbook being read instead of queuing behind it, each job with its own time limit (D92)
  - [x] A card is kept only if its answer appears in the passages it cites (a cloze's hidden words exactly, most of a basic or multiple-choice answer's words), before any cheaper model is tried (D93)
  - [x] Ask's vector search stays exact within a course as more courses are added, with a test across two courses (D94)
  - [x] FSRS parameters, desired retention and learning steps set in code rather than taken from the library's defaults, and recorded with each review (D95)
  - [x] A daily limit per user on chapters marked for cards and on questions in Ask, and figure descriptions reused by image so a re-upload or retry costs nothing (D96)
  - [x] Review ignores held-down keys, and a card is rated at most once each time it is shown (D97)
- [ ] Review-order experiment in the first weeks of daily use: blocked against separate, then fix the preferred one (D55)
- [ ] Eval suites in CI, on an OpenStax corpus that later seeds the demo account (D80, D100–D103). Code in `backend/evals/`, each suite also runnable locally:
  - [ ] Corpus: Psychology 2e, Biology 2e and Principles of Data Science, about nine chapters each for retrieval and three each for cards, read by the real pipeline and published as a versioned snapshot on a GitHub Release, with a committed manifest (D100)
  - [ ] Retrieval suite on every backend push: about 150 questions labelled with gold quotes, recall@8, recall@30 and MRR, failing the build below the committed baseline (D101)
  - [ ] Hand review (admin): check the model-drafted questions and gold quotes (about 1–2 hours), then label about 100 generated cards as good, wrong, confusing or not useful (about 1 hour), each with clear instructions
  - [ ] Card quality suite: cards for the nine eval chapters judged for faithfulness, correctness, one clear answer, making sense alone, worth remembering and, for multiple choice, plausible distractors; drop rates from the existing checks reported too (D102)
  - [ ] Judge calibrated against the hand labels, with Opus and Sonnet both tried as the judge; reported, not gated, until it agrees (D102)
  - [ ] Ask suite: the labelled questions through Ask with Opus and with Sonnet, judged for answering the question, every claim supported by its citation and the "not from your course materials" label used when it should be, with time to first words and in total: decides the Sonnet trial
  - [ ] Full runs by hand at the end of Phase 3 and of Phase 5, through the Batch API, on a separate Anthropic workspace ($50 limit the month it's built, $25 after); about $25 a run, about $50 in all (D103)
  - [ ] Grading suite, built with short-answer cards: hand-graded answers and the grader's agreement with them
- [ ] Flagged cards: a list where a flag can be undone or the card removed; a card flagged before it was ever studied comes back as new, within the day's new cards (D3, D81)
- [ ] Send feedback: a small link in the menu (or on the settings page) where users report what they dislike in a few words, with the page they were on attached, and admins read it in the app (D86)
- [ ] Subject lock: study only one course's cards for the day; every course by default (D77)
- [ ] Uploaded materials belong to chapters: each upload is placed in the chapter it most resembles, and each chapter expands to list its textbook chapter and the materials placed in it, each with a View button (a textbook chapter opens at its first page) and every upload movable to another chapter. A chapter's cards are made from all of its materials ([sketch](../design/courses-ui-mockup.png), D87), without paying twice for what they share (D88):
  - [ ] Slides the textbook already covers, by embedding closeness to the chapter's passages, aren't sent for cards; the threshold is set on real decks
  - [ ] The slides that are sent come with the chapter's existing card questions, and the model is told not to repeat them
  - [ ] Repeated cards are found by meaning (card embeddings) rather than shared words, catching paraphrases from any source
- [ ] Progress and mastery: how well each chapter is known on the course page, then concepts taken from chapter and heading structure, then the weak-spots view
- [ ] More sources in the drop zone: photographed and typed notes, web articles via URL ("Add a link instead")
- [ ] Short-answer cards with LLM grading, checked by the grading eval
- [ ] Exam focus mode: chapters mapped to exams, prioritized ahead of the date
- [ ] Installable on phones: a web app manifest and icon, so Engram can be added to the home screen
- [ ] Possibly a settings page: optional, unobtrusive, every setting with a default that works; what goes in it is decided when it's built (D78)

## Phase 4: UI/UX after daily use

A second design pass, after about two weeks of regular use. From here Engram is treated as a released app: users report what they dislike themselves, and there are no more moderated sessions (D85).

- [ ] Findings from the Phase 2 exit session and the first weeks of daily use, written up in [OBSERVATIONS.md](OBSERVATIONS.md)
- [ ] Changes from those findings, including the screens added in Phase 3
- [ ] Icons in place of words where an icon is clearer, such as a check mark for a chapter already covered, each with its words kept as a tooltip and for screen readers

## Phase 5: Showcase depth

- [ ] Syllabus upload with date extraction, confirmed in one click (moved from Phase 3, D98)
- [ ] Image occlusion cards for diagrams
- [ ] Rubric-graded essay prompts
- [ ] Model benchmark and benchmark-driven routing
- [ ] Public demo account on OpenStax courses, including CS and STEM titles
- [ ] Polished ingestion inspector
- [ ] Anki export (D82)
- [ ] Published aggregate usage statistics, once enough users have agreed to logging that no one can be picked out; until then only eval and benchmark results are published (D83)
- [ ] Fitted learner model compared against the FSRS baseline, fitted on a public review dataset and checked against users' reviews (D84)
