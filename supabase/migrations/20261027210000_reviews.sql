-- Review scheduling. Each card a student has started gets one progress row: the scheduler's
-- state (FSRS) and when the card is next due. A card without a row is new.
--
-- Only the current state is kept, which is all scheduling needs. A history of individual
-- reviews and ratings is a usage event, logged only with the student's consent (see
-- "Privacy and data" in the roadmap); it is not recorded here.
--
-- Flagging a card suspends it for that student; the reason is kept for the optional triage
-- view. Unflagging resumes it where it was.

-- Can the current user read this card? (Owner of its course, or admin.)
create function public.can_read_card(card uuid) returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.cards k where k.id = card and public.can_read_material(k.material_id)
  );
$$;

create type public.card_state as enum ('learning', 'review', 'relearning');
create type public.card_flag as enum ('wrong', 'confusing', 'not_useful');

create table public.card_progress (
  card_id uuid not null references public.cards (id) on delete cascade,
  user_id uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  state public.card_state not null,
  step integer check (step >= 0),
  stability double precision check (stability > 0),
  difficulty double precision check (difficulty between 1 and 10),
  due timestamptz not null,
  last_review timestamptz,
  -- When the card was first studied: new cards are introduced a few at a time each day.
  introduced_at timestamptz not null default now(),
  flag public.card_flag,
  flagged_at timestamptz,
  primary key (card_id, user_id),
  check ((flag is null) = (flagged_at is null))
);

create index card_progress_user_due_idx on public.card_progress (user_id, due) where flag is null;

alter table public.card_progress enable row level security;

create policy "Students read their own progress"
  on public.card_progress for select to authenticated
  using (user_id = (select auth.uid()));

create policy "Students start cards they can read"
  on public.card_progress for insert to authenticated
  with check (user_id = (select auth.uid()) and (select public.can_read_card(card_id)));

create policy "Students update their own progress"
  on public.card_progress for update to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));
