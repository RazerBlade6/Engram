-- Review order: whether flashcards and multiple choice are interleaved ("mixed"), flashcards
-- first ("blocked"), or split into a "Review" and a "Quiz" session ("separate"). It's chosen
-- by experiment, so it's set per student by an admin and is never a student-facing setting.

create type public.review_order as enum ('mixed', 'blocked', 'separate');

alter table public.profiles add column review_order public.review_order not null default 'mixed';

-- Admins may change only the review order; roles are still changed in SQL.
revoke update on public.profiles from anon, authenticated;
grant update (review_order) on public.profiles to authenticated;

create policy "Admins set review order"
  on public.profiles for update to authenticated
  using ((select public.is_admin()))
  with check ((select public.is_admin()));
