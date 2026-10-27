-- Review progress: each student reads and writes only their own, for cards they can read.
-- Run with `supabase test db`.
begin;
create extension if not exists pgtap with schema extensions;
select plan(6);

insert into auth.users (id, aud, role, email) values
  ('11111111-1111-1111-1111-111111111111', 'authenticated', 'authenticated', 'a@test.invalid'),
  ('22222222-2222-2222-2222-222222222222', 'authenticated', 'authenticated', 'b@test.invalid');

insert into public.courses (id, owner_id, title) values
  ('aaaaaaaa-0000-0000-0000-000000000000', '11111111-1111-1111-1111-111111111111', 'Biology');
insert into public.materials (id, course_id, kind, title, storage_path, status) values
  ('cccccccc-0000-0000-0000-000000000000', 'aaaaaaaa-0000-0000-0000-000000000000', 'textbook',
   'Biology 2e', 'aaaaaaaa/cccccccc/bio.pdf', 'ready');
insert into public.cards (id, material_id, ordinal, kind, concept, prompt, answer, sources,
                          generated_by, prompt_version) values
  ('eeeeeeee-0000-0000-0000-000000000000', 'cccccccc-0000-0000-0000-000000000000', 0, 'basic',
   'Cells', 'What is a cell?', 'The unit of life.', '[{"quote": "q", "locations": []}]', 'm', 'v');

create function pg_temp.act_as(user_id uuid) returns void language sql as $$
  select set_config('request.jwt.claims', json_build_object('sub', user_id, 'role', 'authenticated')::text, true);
  set local role authenticated;
$$;

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
select lives_ok($$ insert into public.card_progress (card_id, state, due)
  values ('eeeeeeee-0000-0000-0000-000000000000', 'learning', now()) $$,
  'owners start studying their cards');
select is((select user_id from public.card_progress),
  '11111111-1111-1111-1111-111111111111'::uuid, 'progress belongs to the student');

select pg_temp.act_as('22222222-2222-2222-2222-222222222222');
select is_empty('select 1 from public.card_progress', 'others cannot read the progress');
update public.card_progress set due = now() + interval '1 year';
select throws_ok($$ insert into public.card_progress (card_id, state, due)
  values ('eeeeeeee-0000-0000-0000-000000000000', 'learning', now()) $$, '42501', null,
  'others cannot study cards they cannot read');
select throws_ok($$ insert into public.card_progress (card_id, user_id, state, due)
  values ('eeeeeeee-0000-0000-0000-000000000000', '11111111-1111-1111-1111-111111111111',
          'review', now()) $$, '42501', null, 'nobody writes progress for someone else');

reset role;
select cmp_ok((select due from public.card_progress
                where card_id = 'eeeeeeee-0000-0000-0000-000000000000'), '<', now() + interval '1 day',
  'others cannot change the progress');

select * from finish();
rollback;
