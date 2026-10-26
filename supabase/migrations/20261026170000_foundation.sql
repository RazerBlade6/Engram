-- Foundation schema: profiles and roles, courses, materials, the job queue and private storage.
--
-- Access model. Row-level security is the single place ownership is enforced. The API runs
-- each request as the signed-in user (role `authenticated` with their JWT claims), so the
-- policies below apply to it exactly as they would to a direct Data API call. The worker
-- connects as a privileged role and bypasses RLS. Storage objects have no policies at all:
-- only the API, holding the secret key, reads or writes them, via short-lived signed URLs.

create extension if not exists vector with schema extensions;

-- Shared helpers ------------------------------------------------------------------------

create function public.set_updated_at() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- Profiles ------------------------------------------------------------------------------

create type public.user_role as enum ('student', 'admin');

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  role public.user_role not null default 'student',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger profiles_set_updated_at before update on public.profiles
  for each row execute function public.set_updated_at();

-- Every auth user gets a profile. Roles are changed by an admin in SQL, never by users.
create function public.handle_new_user() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, new.raw_user_meta_data ->> 'display_name');
  return new;
end;
$$;

create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

create function public.is_admin() returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.profiles where id = (select auth.uid()) and role = 'admin'
  );
$$;

alter table public.profiles enable row level security;

create policy "Users read their own profile; admins read all"
  on public.profiles for select to authenticated
  using (id = (select auth.uid()) or (select public.is_admin()));

-- Courses -------------------------------------------------------------------------------

create table public.courses (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete cascade,
  title text not null check (length(trim(title)) > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index courses_owner_id_idx on public.courses (owner_id);

create trigger courses_set_updated_at before update on public.courses
  for each row execute function public.set_updated_at();

create function public.owns_course(course uuid) returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.courses where id = course and owner_id = (select auth.uid())
  );
$$;

alter table public.courses enable row level security;

create policy "Owners and admins read courses"
  on public.courses for select to authenticated
  using (owner_id = (select auth.uid()) or (select public.is_admin()));

create policy "Users create their own courses; admins create any"
  on public.courses for insert to authenticated
  with check (owner_id = (select auth.uid()) or (select public.is_admin()));

create policy "Owners and admins update courses"
  on public.courses for update to authenticated
  using (owner_id = (select auth.uid()) or (select public.is_admin()))
  with check (owner_id = (select auth.uid()) or (select public.is_admin()));

create policy "Owners and admins delete courses"
  on public.courses for delete to authenticated
  using (owner_id = (select auth.uid()) or (select public.is_admin()));

-- Materials -----------------------------------------------------------------------------

create type public.material_kind as enum ('textbook', 'slides');
create type public.material_status as enum ('uploading', 'queued', 'processing', 'ready', 'failed');

create table public.materials (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses (id) on delete cascade,
  kind public.material_kind not null,
  title text not null check (length(trim(title)) > 0),
  -- Object path inside the private `materials` bucket: <course_id>/<material_id>/<filename>.
  storage_path text not null unique,
  status public.material_status not null default 'uploading',
  error text,
  added_by uuid references public.profiles (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index materials_course_id_idx on public.materials (course_id);

create trigger materials_set_updated_at before update on public.materials
  for each row execute function public.set_updated_at();

alter table public.materials enable row level security;

create policy "Course owners and admins read materials"
  on public.materials for select to authenticated
  using ((select public.owns_course(course_id)) or (select public.is_admin()));

-- Students add slides to their own courses; textbooks are added by admins.
create policy "Course owners add slides; admins add anything"
  on public.materials for insert to authenticated
  with check (
    (select public.is_admin())
    or (
      kind = 'slides'
      and added_by = (select auth.uid())
      and status = 'uploading'
      and (select public.owns_course(course_id))
    )
  );

create policy "Admins update materials"
  on public.materials for update to authenticated
  using ((select public.is_admin()))
  with check ((select public.is_admin()));

create policy "Course owners and admins delete materials"
  on public.materials for delete to authenticated
  using ((select public.owns_course(course_id)) or (select public.is_admin()));

-- Job queue -----------------------------------------------------------------------------
-- Only the API and worker touch jobs, through privileged connections. RLS is enabled with
-- no policies, so the table is invisible to anon and authenticated roles.

create type public.job_status as enum ('queued', 'running', 'succeeded', 'failed');

create table public.jobs (
  id bigint generated always as identity primary key,
  kind text not null,
  payload jsonb not null default '{}'::jsonb,
  status public.job_status not null default 'queued',
  attempts integer not null default 0,
  max_attempts integer not null default 3 check (max_attempts > 0),
  run_after timestamptz not null default now(),
  locked_at timestamptz,
  locked_by text,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index jobs_claimable_idx on public.jobs (run_after, id) where status = 'queued';
create index jobs_running_idx on public.jobs (locked_at) where status = 'running';

create trigger jobs_set_updated_at before update on public.jobs
  for each row execute function public.set_updated_at();

alter table public.jobs enable row level security;
revoke all on public.jobs from anon, authenticated;

-- Storage -------------------------------------------------------------------------------
-- 50 MiB is the free-tier per-file ceiling.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'materials',
  'materials',
  false,
  52428800,
  array[
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation'
  ]
);
