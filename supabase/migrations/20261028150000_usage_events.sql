-- Usage events: sessions, page views, reviews and ratings, flags, and the other things
-- students do, for measuring the product (Phase 2 exit, published aggregate statistics) and
-- later fitting the scheduler to real reviews.
--
-- Logged only for people who agreed to it. An admin records that agreement, since students
-- have no settings (zero configuration); turning it off stops logging. Events never hold
-- text a student wrote or read: no questions, answers or card content, only ids, counts,
-- ratings and timings.

alter table public.profiles add column usage_consent_at timestamptz;

-- Admins may change only the review order and the consent record (see the review order
-- migration for the policy).
grant update (usage_consent_at) on public.profiles to authenticated;

create function public.logs_usage() returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.profiles
     where id = (select auth.uid()) and usage_consent_at is not null
  );
$$;

create table public.usage_events (
  id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  -- One visit: a browser tab, until it's been idle for half an hour.
  session_id uuid,
  name text not null check (name ~ '^[a-z_]{1,40}$'),
  data jsonb not null default '{}' check (jsonb_typeof(data) = 'object'),
  created_at timestamptz not null default now()
);

create index usage_events_user_created_idx on public.usage_events (user_id, created_at);
create index usage_events_name_created_idx on public.usage_events (name, created_at);

alter table public.usage_events enable row level security;
revoke update, delete, truncate on public.usage_events from anon, authenticated;

create policy "Consenting users log their own events"
  on public.usage_events for insert to authenticated
  with check (user_id = (select auth.uid()) and (select public.logs_usage()));

create policy "Admins read events"
  on public.usage_events for select to authenticated
  using ((select public.is_admin()));
