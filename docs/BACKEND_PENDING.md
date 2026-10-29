# Pending backend work

API and database changes the Phase 2 UI pass needs but doesn't make. The UI pass is frontend-only, so each of these waits here until it's picked up. Tick items off, or delete them, as they land.

| #   | Change                                                              | Needs                      | Frontend ready?                                        |
| --- | ------------------------------------------------------------------- | -------------------------- | ------------------------------------------------------ |
| 1   | [Card generation shows its progress](#1-card-generation-progress-d53) (D53) | Migration, worker, API | No: needs a few lines once the field exists           |
| 3   | [Each course's owner on `/courses`](#3-each-courses-owner-on-courses) | API                      | Yes: the admin page filters as soon as it's sent      |
| 4   | [Who uploaded a material, and whose it is](#4-who-uploaded-a-material-and-whose-it-is) | Migration, API | Yes: the admin columns fill in as soon as it's sent    |
| 5   | [Delete a material (admin)](#5-delete-a-material-admin)            | Probably nothing           | Stub: `deleteMaterial` in `web/src/app/admin/page.tsx` |
| 6   | [Delete a course](#6-delete-a-course)                               | API (maybe RLS)            | Stub: `deleteCourse` in `web/src/app/admin/page.tsx`   |
| 7   | [Remove a person](#7-remove-a-person)                               | API, Auth, Storage         | Stub: `removePerson` in `web/src/app/admin/page.tsx`   |
| 8   | [Remember the welcome tour per account](#8-remember-the-welcome-tour-per-account) (D60) | Migration, API | No: swap the browser flag for the profile field |
| 9   | [Forgot password](#9-forgot-password) | Auth config, frontend | No: needs a "Forgot your password?" link and a reset page |

Already made during Phase 2, recorded here for completeness: review cards carry `course_id` (`backend/src/engram/api/routes/review.py`), so the review screen can color a card's course. No migration.

## 1. Card generation progress (D53)

**Goal:** while a chapter's cards are made, the course page says how many exist so far ("14 cards so far…"), not just "Making cards…".

**Why it needs the backend:** `backend/src/engram/cards/job.py` stores a chapter's cards in one transaction once every batch is done (after dropping repeats across batches). Until then nothing in the database says how far along it is.

**The approach that was started and reverted** (it went in without being agreed first; nothing was committed):

1. **Migration**, e.g. `supabase/migrations/<timestamp>_cards_progress.sql`:

   ```sql
   -- How many cards a chapter's generation has drafted so far, so the course page can show
   -- progress while a student waits (D53). The worker adds to it as each batch comes back.
   -- It counts cards before repeats across batches are dropped, so the final number can be
   -- a little lower.
   alter table public.covered_sections
     add column cards_drafted integer not null default 0;
   ```

   Marking a chapter inserts a fresh `covered_sections` row, so the count starts at 0 each time; unmarking deletes the row. RLS is unchanged: students can't update the table, and the worker's connection can.

2. **Worker**, `backend/src/engram/cards/job.py`:
   - a helper that adds to the count:

     ```python
     async def _drafted(conn: AsyncConnection[Any], section_id: str, count: int) -> None:
         """Counts cards as batches come back, so the course page can show progress (D53)."""
         await conn.execute(
             "update public.covered_sections set cards_drafted = cards_drafted + %s"
             " where section_id = %s",
             (count, section_id),
         )
     ```

   - `make_cards` takes `drafted: Callable[[int], Awaitable[None]] | None = None`, and in each batch's task, after `accept(...)`, calls `await drafted(len(cards))` when there are cards;
   - `generate` passes `drafted=lambda n: _drafted(conn, section_id, n)`.

   The worker's connection is autocommit, so each update is visible at once. Batches run concurrently on one connection, the same as the existing `still_covered` check.

3. **API**, `backend/src/engram/api/routes/courses.py`:
   - `cards_drafted: int` on `Chapter` and `_SectionRow`;
   - `_SECTIONS` selects `coalesce(c.cards_drafted, 0) as cards_drafted`.

4. **Tests:**
   - `backend/tests/test_courses.py`: the `section()` helper passes `cards_drafted=0`;
   - `backend/tests/test_cards.py`, `test_chapters_show_their_cards`: `cards_drafted` is 0 while pending, 2 after the run (the fake provider's two cards), and 0 again after unmarking.

5. **Frontend**, still to do once the field exists:
   - `cards_drafted: number` on `Chapter` in `web/src/lib/courses.ts`;
   - `chapterNote` shows "N cards so far…" instead of "Making cards…" when it's above 0, with a test in `web/src/lib/courses.test.ts`;
   - the course page already polls every 4 s while a chapter is pending, so the count updates without further work. The small animated pile next to it is already built.

**Open question:** the count is taken before repeats are dropped, so "23 so far" can end as "21 cards are ready". Counting batches done out of total ("3 of 5 parts") is exact but means less to a student. The draft used the card count, worded "so far".

## 3. Each course's owner on `/courses`

The admin page's Courses section lists one person's courses. As an admin, `GET /courses` already returns every course (RLS lets admins read all), but not whose each one is, so the page lists all of them with a note saying so.

- `backend/src/engram/api/routes/courses.py`: add `owner_id: UUID` to `CourseSummary`, and select `c.owner_id` in `list_courses`.
- No migration: `courses.owner_id` exists.
- Frontend: `owner_id` is already an optional field on `CourseSummary`; once every course has it, the filter turns on and the note disappears.

## 4. Who uploaded a material, and whose it is

The admin materials table has "Uploaded by" and "Belongs to" columns, showing "—" for now.

- **Belongs to** (the course's owner): no migration. In `/admin/materials` (`backend/src/engram/api/routes/inspector.py`, `_SUMMARY`), join `courses` and `profiles` and return the owner's display name as `owner`.
- **Uploaded by:** nothing records it today. Needs:

  ```sql
  alter table public.materials
    add column uploaded_by uuid references public.profiles (id) on delete set null;
  ```

  set to the signed-in user in `POST /courses/{course_id}/materials` (`backend/src/engram/api/routes/materials.py`), and returned by `/admin/materials` as `uploaded_by` (a display name). Existing materials stay null and show "—".

- Frontend: `uploaded_by` and `owner` are already optional fields on `MaterialSummary` (`web/src/lib/inspector.ts`).

## 5. Delete a material (admin)

`DELETE /materials/{material_id}` already exists (`backend/src/engram/api/routes/materials.py`): the course page uses it, and it removes the stored files. Check that its RLS lets an admin delete any course's material; if so, `deleteMaterial` on the admin page only needs to call it (and reload the list).

## 6. Delete a course

There's no `DELETE /courses/{course_id}` yet. To decide:

- what goes with it: materials, chunks, cards, coverage and dates follow by cascade where foreign keys allow; stored files (textbooks, slides, page images) need removing from Storage the way `remove` does for one material;
- who can do it: admins only from the admin page, or owners too;
- RLS: the courses policies allow `delete` for the owner or an admin (`20261026170000_foundation.sql`), so the endpoint can run as the signed-in user.

## 7. Remove a person

Needs an admin endpoint, e.g. `DELETE /admin/people/{id}`:

- delete the Auth user with the Supabase admin API (service key); `profiles` and their courses go by cascade;
- remove their stored files;
- their usage events: decide whether removal also deletes them (D42 deletes past events on request).

The admin page hides Remove on your own row, so an admin can't remove themselves by accident.

## 8. Remember the welcome tour per account (D60)

The welcome tour shows once per browser: `web/src/components/welcome-tour.tsx` stores `engram.welcomed` in `localStorage`. A new device or a cleared browser shows it again.

- Migration: `alter table public.profiles add column welcomed_at timestamptz;`, with the column added to the update grant students already have on `profiles`.
- API: return `welcomed_at` from `GET /me`, and an endpoint (or `PUT /me`) that sets it.
- Frontend: `tourSeen()` reads the profile instead of storage, and finishing or skipping the tour sets it.

## 9. Forgot password

There's no way to recover a forgotten password: an admin would have to send a new invite to a new address, or reset it by hand. Someone signed out without their password saved has no way back in.

Supabase Auth covers most of it:

- **Request:** a "Forgot your password?" link on the sign-in page opens a form for the email address and calls `supabase.auth.resetPasswordForEmail(email, { redirectTo: <web url>/auth/reset-password })`. The page always says "If that address has an account, a link is on its way", so it doesn't reveal who has one.
- **Reset:** the link signs them in for a moment and lands on a page that sets the new password with `supabase.auth.updateUser({ password })`. `web/src/app/auth/set-password/page.tsx`, which invite links already use, does exactly this and can likely be reused.
- **Configuration:** add the reset page to the allowed redirect URLs (`supabase/config.toml` locally, and the hosted project's Auth settings), and word the reset email template plainly. Production needs working email sending (custom SMTP) for these to arrive reliably.
- **Admin fallback:** a "Send a password reset" button per person on the admin page, calling the same thing from the API with the service key, for anyone who can't get the email.
- **Locally:** emails are caught at http://localhost:54324, so the flow can be tested end to end.
