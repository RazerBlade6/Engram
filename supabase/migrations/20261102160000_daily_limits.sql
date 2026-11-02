-- Daily limits on what costs money, per user (D96). A spend alert only reports after the
-- fact, and marking a whole textbook is one click per chapter. Admins have no limits.
--
-- Chapters marked covered: at most 10 in any 24 hours. Checked here rather than in the API,
-- because students insert these rows as themselves. Rows the worker inserts (keeping a mark
-- when a material is read again) are not a student's request and aren't counted against one.
--
-- Questions in Ask: at most 100 a day, counted by the API in daily_questions. A count only:
-- questions themselves are never stored.
--
-- Figure descriptions: kept by the image's SHA-256 and the model that wrote them, so a
-- material uploaded again, or read again after a failure, pays nothing for figures already
-- described. Written and read by the worker only.

create function public.limit_chapters_per_day() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if (select auth.uid()) is null or public.is_admin() then
    return new;
  end if;
  if (
    select count(*) from public.covered_sections
     where covered_by = (select auth.uid()) and covered_at > now() - interval '24 hours'
  ) >= 10 then
    -- engram.api.routes.courses.DAILY_LIMIT
    raise exception 'daily chapter limit reached' using errcode = 'EG429';
  end if;
  return new;
end;
$$;

revoke execute on function public.limit_chapters_per_day() from public, anon, authenticated;

create trigger covered_sections_daily_limit before insert on public.covered_sections
  for each row execute function public.limit_chapters_per_day();

create table public.daily_questions (
  user_id uuid not null references public.profiles (id) on delete cascade,
  -- The user's own date, from their browser's time zone.
  day date not null,
  questions integer not null default 0 check (questions >= 0),
  primary key (user_id, day)
);

alter table public.daily_questions enable row level security;
revoke all on public.daily_questions from anon, authenticated;

create table public.figure_descriptions (
  image_sha256 text not null check (image_sha256 ~ '^[0-9a-f]{64}$'),
  model text not null,
  kind text not null,
  description text not null,
  labels text[] not null default '{}',
  created_at timestamptz not null default now(),
  primary key (image_sha256, model)
);

alter table public.figure_descriptions enable row level security;
revoke all on public.figure_descriptions from anon, authenticated;
