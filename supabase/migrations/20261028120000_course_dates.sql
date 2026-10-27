-- Important dates per course: exams, quizzes and deadlines, shown on the calendar and on
-- Today. Students add them with a one-line quick-add; lecture timetables are out of scope.

create type public.date_kind as enum ('exam', 'quiz', 'deadline');

create table public.course_dates (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses (id) on delete cascade,
  kind public.date_kind not null,
  title text not null check (length(trim(title)) between 1 and 200),
  on_date date not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index course_dates_course_id_idx on public.course_dates (course_id, on_date);

create trigger course_dates_set_updated_at before update on public.course_dates
  for each row execute function public.set_updated_at();

alter table public.course_dates enable row level security;

create policy "Course owners and admins read dates"
  on public.course_dates for select to authenticated
  using ((select public.owns_course(course_id)) or (select public.is_admin()));

create policy "Course owners and admins add dates"
  on public.course_dates for insert to authenticated
  with check ((select public.owns_course(course_id)) or (select public.is_admin()));

create policy "Course owners and admins change dates"
  on public.course_dates for update to authenticated
  using ((select public.owns_course(course_id)) or (select public.is_admin()))
  with check ((select public.owns_course(course_id)) or (select public.is_admin()));

create policy "Course owners and admins delete dates"
  on public.course_dates for delete to authenticated
  using ((select public.owns_course(course_id)) or (select public.is_admin()));
