-- Row-level security for parsed material content. Run with `supabase test db`.
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
insert into public.sections (id, material_id, ordinal, level, title, page_start, page_end) values
  ('dddddddd-0000-0000-0000-000000000000', 'cccccccc-0000-0000-0000-000000000000', 0, 1, 'Cells', 1, 9);
insert into public.figures (material_id, section_id, ordinal, page, bbox) values
  ('cccccccc-0000-0000-0000-000000000000', 'dddddddd-0000-0000-0000-000000000000', 0, 2, '{1,2,3,4}');
insert into public.chunks (material_id, section_id, ordinal, kind, content) values
  ('cccccccc-0000-0000-0000-000000000000', 'dddddddd-0000-0000-0000-000000000000', 0, 'text', 'Cells');

create function pg_temp.act_as(user_id uuid) returns void language sql as $$
  select set_config('request.jwt.claims', json_build_object('sub', user_id, 'role', 'authenticated')::text, true);
  set local role authenticated;
$$;

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
select is((select count(*)::int from public.sections), 1, 'course owners read sections');
select is((select count(*)::int from public.chunks), 1, 'course owners read chunks');
select throws_ok($$ insert into public.chunks (material_id, ordinal, kind, content)
  values ('cccccccc-0000-0000-0000-000000000000', 1, 'text', 'planted') $$,
  '42501', null, 'users cannot write chunks');

reset role;
select pg_temp.act_as('22222222-2222-2222-2222-222222222222');
select is_empty('select 1 from public.sections', 'other students cannot read sections');
select is_empty('select 1 from public.figures', 'other students cannot read figures');
select is_empty('select 1 from public.chunks', 'other students cannot read chunks');

select * from finish();
rollback;
