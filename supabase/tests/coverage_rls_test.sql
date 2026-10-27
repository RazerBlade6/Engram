-- Row-level security for chapter coverage. Run with `supabase test db`.
begin;
create extension if not exists pgtap with schema extensions;
select plan(8);

insert into auth.users (id, aud, role, email) values
  ('11111111-1111-1111-1111-111111111111', 'authenticated', 'authenticated', 'a@test.invalid'),
  ('22222222-2222-2222-2222-222222222222', 'authenticated', 'authenticated', 'b@test.invalid'),
  ('33333333-3333-3333-3333-333333333333', 'authenticated', 'authenticated', 'c@test.invalid');
update public.profiles set role = 'admin' where id = '33333333-3333-3333-3333-333333333333';

insert into public.courses (id, owner_id, title) values
  ('aaaaaaaa-0000-0000-0000-000000000000', '11111111-1111-1111-1111-111111111111', 'Biology');
insert into public.materials (id, course_id, kind, title, storage_path, status) values
  ('cccccccc-0000-0000-0000-000000000000', 'aaaaaaaa-0000-0000-0000-000000000000', 'textbook',
   'Biology 2e', 'aaaaaaaa/cccccccc/bio.pdf', 'ready');
insert into public.sections (id, material_id, ordinal, level, title, page_start, page_end) values
  ('dddddddd-0000-0000-0000-000000000001', 'cccccccc-0000-0000-0000-000000000000', 0, 1, 'Chapter 1', 1, 9),
  ('dddddddd-0000-0000-0000-000000000002', 'cccccccc-0000-0000-0000-000000000000', 1, 1, 'Chapter 2', 10, 19);

create function pg_temp.act_as(user_id uuid) returns void language sql as $$
  select set_config('request.jwt.claims', json_build_object('sub', user_id, 'role', 'authenticated')::text, true);
  set local role authenticated;
$$;

-- The course owner marks and unmarks.
select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
select lives_ok($$ insert into public.covered_sections (section_id)
  values ('dddddddd-0000-0000-0000-000000000001') $$, 'owners mark a chapter covered');
select is((select covered_by from public.covered_sections),
  '11111111-1111-1111-1111-111111111111'::uuid, 'the mark records who made it');
select throws_ok($$ insert into public.covered_sections (section_id, covered_by)
  values ('dddddddd-0000-0000-0000-000000000002', '33333333-3333-3333-3333-333333333333') $$,
  '42501', null, 'a mark cannot be attributed to someone else');

-- Other students see nothing and change nothing.
reset role;
select pg_temp.act_as('22222222-2222-2222-2222-222222222222');
select is_empty('select 1 from public.covered_sections', 'other students cannot read coverage');
select throws_ok($$ insert into public.covered_sections (section_id)
  values ('dddddddd-0000-0000-0000-000000000002') $$,
  '42501', null, 'other students cannot mark chapters');
delete from public.covered_sections;

-- Admins can mark on any course; the owner can unmark.
reset role;
select pg_temp.act_as('33333333-3333-3333-3333-333333333333');
select lives_ok($$ insert into public.covered_sections (section_id)
  values ('dddddddd-0000-0000-0000-000000000002') $$, 'admins mark chapters on any course');

reset role;
select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
select is((select count(*)::int from public.covered_sections), 2,
  'other students'' delete removed nothing');
delete from public.covered_sections where section_id = 'dddddddd-0000-0000-0000-000000000001';
select is((select count(*)::int from public.covered_sections), 1, 'owners unmark a chapter');

select * from finish();
rollback;
