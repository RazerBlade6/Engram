-- Parsed structure of a material: its table of contents, searchable chunks and figures.
--
-- Everything here is written by the worker (privileged, bypasses RLS) and is readable by
-- whoever can read the material. Re-ingesting a material replaces all of its rows.

alter table public.materials add column page_count integer check (page_count > 0);

-- Can the current user read this material? (Course owner or admin.)
create function public.can_read_material(material uuid) returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
      from public.materials m
      join public.courses c on c.id = m.course_id
     where m.id = material
       and (c.owner_id = (select auth.uid()) or (select public.is_admin()))
  );
$$;

-- Sections ------------------------------------------------------------------------------
-- The table of contents. Level 1 is a chapter (or a top-level unit); "mark covered" acts on
-- sections. Pages are 1-based and inclusive.

create table public.sections (
  id uuid primary key default gen_random_uuid(),
  material_id uuid not null references public.materials (id) on delete cascade,
  parent_id uuid references public.sections (id) on delete cascade,
  ordinal integer not null,
  level integer not null check (level >= 1),
  title text not null,
  page_start integer check (page_start >= 1),
  page_end integer check (page_end >= page_start),
  unique (material_id, ordinal)
);

create index sections_parent_id_idx on public.sections (parent_id);

alter table public.sections enable row level security;

create policy "Readers of the material read its sections"
  on public.sections for select to authenticated
  using ((select public.can_read_material(material_id)));

-- Figures -------------------------------------------------------------------------------
-- Diagrams and photos. `description` and `labels` come from a vision model; labels will
-- drive image-occlusion cards. The cropped image is stored in the materials bucket.

create table public.figures (
  id uuid primary key default gen_random_uuid(),
  material_id uuid not null references public.materials (id) on delete cascade,
  section_id uuid references public.sections (id) on delete set null,
  ordinal integer not null,
  page integer not null check (page >= 1),
  -- [left, top, right, bottom] in PDF points from the page's top-left corner.
  bbox double precision[4] not null,
  caption text,
  description text,
  labels text[] not null default '{}',
  storage_path text,
  described_by text,
  unique (material_id, ordinal)
);

create index figures_section_id_idx on public.figures (section_id);

alter table public.figures enable row level security;

create policy "Readers of the material read its figures"
  on public.figures for select to authenticated
  using ((select public.can_read_material(material_id)));

-- Chunks --------------------------------------------------------------------------------
-- Retrieval units. `content` is the text that is embedded and searched, prefixed with its
-- heading path; `locations` lists every page region the chunk came from, so a citation can
-- highlight it: [{"page": 12, "bbox": [l, t, r, b]}, ...] with the same coordinates as figures.

create type public.chunk_kind as enum ('text', 'table', 'figure', 'slide');

create table public.chunks (
  id uuid primary key default gen_random_uuid(),
  material_id uuid not null references public.materials (id) on delete cascade,
  section_id uuid references public.sections (id) on delete set null,
  figure_id uuid references public.figures (id) on delete cascade,
  ordinal integer not null,
  kind public.chunk_kind not null,
  heading_path text[] not null default '{}',
  content text not null,
  locations jsonb not null default '[]'::jsonb check (jsonb_typeof(locations) = 'array'),
  embedding extensions.vector(384),
  embedding_model text,
  fts tsvector generated always as (to_tsvector('english', content)) stored,
  unique (material_id, ordinal),
  check ((embedding is null) = (embedding_model is null))
);

create index chunks_section_id_idx on public.chunks (section_id);
create index chunks_fts_idx on public.chunks using gin (fts);
create index chunks_embedding_idx on public.chunks
  using hnsw (embedding extensions.vector_cosine_ops);

alter table public.chunks enable row level security;

create policy "Readers of the material read its chunks"
  on public.chunks for select to authenticated
  using ((select public.can_read_material(material_id)));

-- Storage -------------------------------------------------------------------------------
-- Cropped figures are stored next to their material as PNGs.

update storage.buckets
   set allowed_mime_types = array_append(allowed_mime_types, 'image/png')
 where id = 'materials' and not ('image/png' = any (allowed_mime_types));
