-- Cards and their generation: who can read them, and what a student can and cannot write.
-- Run with `supabase test db`.
begin;
create extension if not exists pgtap with schema extensions;
select plan(8);

insert into auth.users (id, aud, role, email) values
  ('11111111-1111-1111-1111-111111111111', 'authenticated', 'authenticated', 'a@test.invalid'),
  ('22222222-2222-2222-2222-222222222222', 'authenticated', 'authenticated', 'b@test.invalid');

insert into public.courses (id, owner_id, title) values
  ('aaaaaaaa-0000-0000-0000-000000000000', '11111111-1111-1111-1111-111111111111', 'Biology');
insert into public.materials (id, course_id, kind, title, storage_path, status) values
  ('cccccccc-0000-0000-0000-000000000000', 'aaaaaaaa-0000-0000-0000-000000000000', 'textbook',
   'Biology 2e', 'aaaaaaaa/cccccccc/bio.pdf', 'ready');
insert into public.sections (id, material_id, ordinal, level, title) values
  ('dddddddd-0000-0000-0000-000000000001', 'cccccccc-0000-0000-0000-000000000000', 0, 1, 'Chapter 1'),
  ('dddddddd-0000-0000-0000-000000000002', 'cccccccc-0000-0000-0000-000000000000', 1, 1, 'Chapter 2');
insert into public.cards (material_id, section_id, ordinal, kind, concept, prompt, answer,
                          sources, generated_by, prompt_version) values
  ('cccccccc-0000-0000-0000-000000000000', 'dddddddd-0000-0000-0000-000000000002', 0, 'basic',
   'Cells', 'What is a cell?', 'The unit of life.', '[{"quote": "q", "locations": []}]', 'm', 'v');

create function pg_temp.act_as(user_id uuid) returns void language sql as $$
  select set_config('request.jwt.claims', json_build_object('sub', user_id, 'role', 'authenticated')::text, true);
  set local role authenticated;
$$;

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');

select lives_ok($$ insert into public.covered_sections (section_id)
  values ('dddddddd-0000-0000-0000-000000000001') $$, 'owners mark a chapter covered');
select throws_ok($$ insert into public.covered_sections (section_id, cards_status)
  values ('dddddddd-0000-0000-0000-000000000002', 'ready') $$, '42501', null,
  'students cannot claim a chapter''s cards are ready');
update public.covered_sections set cards_status = 'ready';
select is((select cards_status::text from public.covered_sections), 'pending',
  'students cannot change a chapter''s card status');
select is((select count(*)::int from public.cards), 1, 'owners read their cards');
select throws_ok($$ insert into public.cards (material_id, section_id, ordinal, kind, concept,
    prompt, answer, sources, generated_by, prompt_version)
  values ('cccccccc-0000-0000-0000-000000000000', null, 1, 'basic', 'c', 'Q', 'A',
          '[{"quote": "q"}]', 'm', 'v') $$, '42501', null, 'students cannot write cards');

select pg_temp.act_as('22222222-2222-2222-2222-222222222222');
select is_empty('select 1 from public.cards', 'other students cannot read the cards');

reset role;
select is(
  (select count(*)::int from public.jobs
    where kind = 'generate_cards'
      and payload->>'section_id' = 'dddddddd-0000-0000-0000-000000000001'),
  1, 'marking a chapter queues its card generation');
select throws_ok($$ insert into public.cards (material_id, section_id, ordinal, kind, concept,
    prompt, answer, sources, generated_by, prompt_version)
  values ('cccccccc-0000-0000-0000-000000000000', null, 1, 'cloze', 'c', 'No braces', 'A',
          '[{"quote": "q"}]', 'm', 'v') $$, '23514', null, 'a cloze card must hide something');

select * from finish();
rollback;
