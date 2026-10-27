-- Coverage: a student marks a chapter covered once it has been taught. That is the only
-- trigger for card generation (D4). Marking is recorded per section, so finer-grained
-- coverage needs no schema change. Re-ingesting a material replaces its sections; the
-- ingestion store carries coverage over to sections with the same level and title.

-- Can the current user read this section? (Owner of its course, or admin.)
create function public.can_read_section(section uuid) returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
      from public.sections s
     where s.id = section
       and public.can_read_material(s.material_id)
  );
$$;

create table public.covered_sections (
  section_id uuid primary key references public.sections (id) on delete cascade,
  covered_at timestamptz not null default now(),
  covered_by uuid default auth.uid() references public.profiles (id) on delete set null
);

create index covered_sections_covered_by_idx on public.covered_sections (covered_by);

alter table public.covered_sections enable row level security;

create policy "Readers of the section read its coverage"
  on public.covered_sections for select to authenticated
  using ((select public.can_read_section(section_id)));

-- No update policy: a mark is added or removed, never edited.
create policy "Readers of the section mark it covered"
  on public.covered_sections for insert to authenticated
  with check (
    (select public.can_read_section(section_id))
    and covered_by = (select auth.uid())
  );

create policy "Readers of the section unmark it"
  on public.covered_sections for delete to authenticated
  using ((select public.can_read_section(section_id)));
