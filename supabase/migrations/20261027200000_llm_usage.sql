-- Tokens billed by each job that calls a language model: one row per job run, so cost per
-- chapter or per textbook can be measured and models compared on real work (D25, D26).
--
-- Written by the worker only. Like the job queue, it is invisible to students: RLS is
-- enabled with no policies. Rows outlive the material or chapter they were for.

create table public.llm_usage (
  id bigint generated always as identity primary key,
  job text not null,
  model text not null,
  material_id uuid references public.materials (id) on delete set null,
  section_id uuid references public.sections (id) on delete set null,
  requests integer not null check (requests >= 0),
  input_tokens bigint not null check (input_tokens >= 0),
  output_tokens bigint not null check (output_tokens >= 0),
  cache_read_input_tokens bigint not null default 0 check (cache_read_input_tokens >= 0),
  cache_creation_input_tokens bigint not null default 0
    check (cache_creation_input_tokens >= 0),
  created_at timestamptz not null default now()
);

create index llm_usage_material_id_idx on public.llm_usage (material_id);
create index llm_usage_section_id_idx on public.llm_usage (section_id);

alter table public.llm_usage enable row level security;
revoke all on public.llm_usage from anon, authenticated;
