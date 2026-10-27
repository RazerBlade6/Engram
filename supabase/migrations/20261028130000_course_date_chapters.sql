-- The chapters an exam, quiz or deadline covers. Optional when a date is added; ahead of an
-- exam, focus mode (Phase 3) uses them to prioritize those chapters' cards.

create function public.can_read_date(course_date uuid) returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.course_dates d
     where d.id = course_date and (public.owns_course(d.course_id) or public.is_admin())
  );
$$;

-- A date only covers chapters from its own course.
create function public.section_in_date_course(course_date uuid, section uuid) returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
      from public.course_dates d
      join public.materials m on m.course_id = d.course_id
      join public.sections s on s.material_id = m.id
     where d.id = course_date and s.id = section
  );
$$;

create table public.course_date_chapters (
  date_id uuid not null references public.course_dates (id) on delete cascade,
  section_id uuid not null references public.sections (id) on delete cascade,
  primary key (date_id, section_id)
);

create index course_date_chapters_section_id_idx on public.course_date_chapters (section_id);

alter table public.course_date_chapters enable row level security;

create policy "Readers of the date read its chapters"
  on public.course_date_chapters for select to authenticated
  using ((select public.can_read_date(date_id)));

create policy "Readers of the date add chapters from its course"
  on public.course_date_chapters for insert to authenticated
  with check (
    (select public.can_read_date(date_id))
    and (select public.section_in_date_course(date_id, section_id))
  );

create policy "Readers of the date remove its chapters"
  on public.course_date_chapters for delete to authenticated
  using ((select public.can_read_date(date_id)));
