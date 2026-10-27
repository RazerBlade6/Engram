-- Cards. Marking a chapter covered queues a job that generates its cards (D4); they go
-- straight into the deck (D3). Unmarking a chapter keeps its cards but stops any generation
-- that hasn't finished, and marking it again doesn't generate a second set.
--
-- Cards are written only by the worker. Each card keeps a copy of where its sources are on
-- the page, so its citation survives the material being re-ingested (which replaces chunks);
-- the ingestion store re-attaches cards to the chapter with the same level and title.

-- Generation status, per covered chapter -------------------------------------------------
-- 'pending' while the job is queued or running; the worker sets 'ready' or 'failed'.

create type public.cards_status as enum ('pending', 'ready', 'failed');

alter table public.covered_sections
  add column cards_status public.cards_status not null default 'pending';

-- Students mark a chapter; only the worker reports on its cards.
drop policy "Readers of the section mark it covered" on public.covered_sections;

create policy "Readers of the section mark it covered"
  on public.covered_sections for insert to authenticated
  with check (
    (select public.can_read_section(section_id))
    and covered_by = (select auth.uid())
    and cards_status = 'pending'
  );

-- Marking a chapter queues its generation in the same transaction. The trigger runs as its
-- owner because students cannot touch the job queue.
create function public.queue_card_generation() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.cards_status = 'pending' then
    insert into public.jobs (kind, payload)
    values ('generate_cards', jsonb_build_object('section_id', new.section_id));
  end if;
  return new;
end;
$$;

revoke execute on function public.queue_card_generation() from public, anon, authenticated;

create trigger covered_sections_queue_cards after insert on public.covered_sections
  for each row execute function public.queue_card_generation();

-- Cards ---------------------------------------------------------------------------------

create type public.card_kind as enum ('basic', 'cloze', 'mcq');

create table public.cards (
  id uuid primary key default gen_random_uuid(),
  material_id uuid not null references public.materials (id) on delete cascade,
  -- The chapter the card was generated for. Null only while a re-ingest drops the chapter.
  section_id uuid references public.sections (id) on delete set null,
  ordinal integer not null,
  kind public.card_kind not null,
  -- The idea the card tests, in a few words; groups cards for mastery later.
  concept text not null,
  -- basic: the question. cloze: a sentence with the hidden part marked {{like this}}.
  -- mcq: the question.
  prompt text not null,
  -- basic: the answer. cloze: the hidden part. mcq: the correct choice.
  answer text not null,
  -- mcq only: every choice, including the answer, in display order.
  choices text[] not null default '{}',
  -- The passages the card comes from: [{"chunk_id", "quote", "heading_path", "locations"}],
  -- with locations as in chunks.
  sources jsonb not null check (jsonb_typeof(sources) = 'array' and jsonb_array_length(sources) > 0),
  -- Which model and prompt made it, so evals can compare them and attribute flags (D25).
  generated_by text not null,
  prompt_version text not null,
  created_at timestamptz not null default now(),
  check ((kind = 'mcq') = (cardinality(choices) > 0)),
  check (kind <> 'mcq' or answer = any (choices)),
  check (kind <> 'cloze' or prompt like '%{{%}}%')
);

create index cards_material_id_idx on public.cards (material_id);
create index cards_section_id_idx on public.cards (section_id);

alter table public.cards enable row level security;

create policy "Readers of the material read its cards"
  on public.cards for select to authenticated
  using ((select public.can_read_material(material_id)));
