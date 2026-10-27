-- Student uploads: inserting slides and queueing them. Run with `supabase test db`.
begin;
create extension if not exists pgtap with schema extensions;
select plan(10);

insert into auth.users (id, aud, role, email) values
  ('11111111-1111-1111-1111-111111111111', 'authenticated', 'authenticated', 'a@test.invalid'),
  ('22222222-2222-2222-2222-222222222222', 'authenticated', 'authenticated', 'b@test.invalid');

insert into public.courses (id, owner_id, title) values
  ('aaaaaaaa-0000-0000-0000-000000000000', '11111111-1111-1111-1111-111111111111', 'Biology');
insert into public.materials (id, course_id, kind, title, storage_path, status) values
  ('cccccccc-0000-0000-0000-000000000000', 'aaaaaaaa-0000-0000-0000-000000000000', 'textbook',
   'Biology 2e', 'aaaaaaaa/cccccccc/bio.pdf', 'ready');

create function pg_temp.act_as(user_id uuid) returns void language sql as $$
  select set_config('request.jwt.claims', json_build_object('sub', user_id, 'role', 'authenticated')::text, true);
  set local role authenticated;
$$;

select ok(not has_function_privilege('anon', 'public.queue_material(uuid)', 'execute'),
  'anonymous visitors cannot queue materials');

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
select lives_ok($$ insert into public.materials (id, course_id, kind, title, storage_path, added_by)
  values ('dddddddd-0000-0000-0000-000000000000', 'aaaaaaaa-0000-0000-0000-000000000000', 'slides',
          'Week 1', 'aaaaaaaa/dddddddd/week1.pdf', '11111111-1111-1111-1111-111111111111') $$,
  'owners add slides');
select throws_ok($$ insert into public.materials (course_id, kind, title, storage_path, added_by)
  values ('aaaaaaaa-0000-0000-0000-000000000000', 'textbook', 'Mine', 'aaaaaaaa/x/mine.pdf',
          '11111111-1111-1111-1111-111111111111') $$,
  '42501', null, 'owners cannot add textbooks');
select lives_ok($$ select public.queue_material('dddddddd-0000-0000-0000-000000000000') $$,
  'owners queue their upload');
select is((select status::text from public.materials where id = 'dddddddd-0000-0000-0000-000000000000'),
  'queued', 'the upload is queued');
select throws_ok($$ select public.queue_material('dddddddd-0000-0000-0000-000000000000') $$,
  '42501', null, 'a material is queued only once');
select throws_ok($$ select public.queue_material('cccccccc-0000-0000-0000-000000000000') $$,
  '42501', null, 'finished materials cannot be re-queued');

delete from public.materials where id = 'cccccccc-0000-0000-0000-000000000000';
select isnt_empty($$ select 1 from public.materials where id = 'cccccccc-0000-0000-0000-000000000000' $$,
  'owners cannot delete the textbook');
delete from public.materials where id = 'dddddddd-0000-0000-0000-000000000000';
select is_empty($$ select 1 from public.materials where id = 'dddddddd-0000-0000-0000-000000000000' $$,
  'owners delete their slides');

reset role;
select is((select count(*)::int from public.jobs
  where payload->>'material_id' = 'dddddddd-0000-0000-0000-000000000000'), 1,
  'one ingestion job was created');

select * from finish();
rollback;
