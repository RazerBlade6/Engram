-- Row-level security for the foundation schema. Run with `supabase test db`.
begin;
create extension if not exists pgtap with schema extensions;
select plan(16);

-- Fixtures: two students and an admin, one course each for the students.
insert into auth.users (id, aud, role, email) values
  ('11111111-1111-1111-1111-111111111111', 'authenticated', 'authenticated', 'a@test.invalid'),
  ('22222222-2222-2222-2222-222222222222', 'authenticated', 'authenticated', 'b@test.invalid'),
  ('33333333-3333-3333-3333-333333333333', 'authenticated', 'authenticated', 'admin@test.invalid');
update public.profiles set role = 'admin' where id = '33333333-3333-3333-3333-333333333333';

insert into public.courses (id, owner_id, title) values
  ('aaaaaaaa-0000-0000-0000-000000000000', '11111111-1111-1111-1111-111111111111', 'Biology'),
  ('bbbbbbbb-0000-0000-0000-000000000000', '22222222-2222-2222-2222-222222222222', 'Psychology');

insert into public.materials (course_id, kind, title, storage_path, status) values
  ('bbbbbbbb-0000-0000-0000-000000000000', 'textbook', 'Psychology 2e', 'bbbbbbbb/textbook.pdf', 'ready');

insert into public.jobs (kind) values ('test');

create function pg_temp.act_as(user_id uuid) returns void language sql as $$
  select set_config('request.jwt.claims', json_build_object('sub', user_id, 'role', 'authenticated')::text, true);
  set local role authenticated;
$$;

-- New auth users get a student profile.
select is(
  (select role::text from public.profiles where id = '11111111-1111-1111-1111-111111111111'),
  'student', 'new users get a student profile');

-- Student A -----------------------------------------------------------------------------
select pg_temp.act_as('11111111-1111-1111-1111-111111111111');

select results_eq('select id from public.profiles',
  $$values ('11111111-1111-1111-1111-111111111111'::uuid)$$, 'students see only their own profile');
select results_eq('select title from public.courses', $$values ('Biology')$$,
  'students see only their own courses');
select is_empty('select 1 from public.materials', 'students cannot see materials in other courses');
select throws_ok('select 1 from public.jobs', '42501', null, 'the job queue is not readable by users');

select throws_ok($$ update public.profiles set role = 'admin'
  where id = '11111111-1111-1111-1111-111111111111' $$, '42501', null,
  'students cannot make themselves admins');

update public.courses set title = 'Hijacked' where id = 'bbbbbbbb-0000-0000-0000-000000000000';
delete from public.courses where id = 'bbbbbbbb-0000-0000-0000-000000000000';

select lives_ok($$
  insert into public.materials (course_id, kind, title, storage_path, added_by)
  values ('aaaaaaaa-0000-0000-0000-000000000000', 'slides', 'Week 1', 'aaaaaaaa/week1.pdf',
          '11111111-1111-1111-1111-111111111111')
$$, 'students can add slides to their own course');

select throws_ok($$
  insert into public.materials (course_id, kind, title, storage_path, added_by)
  values ('aaaaaaaa-0000-0000-0000-000000000000', 'textbook', 'Book', 'aaaaaaaa/book.pdf',
          '11111111-1111-1111-1111-111111111111')
$$, '42501', null, 'students cannot add textbooks');

select throws_ok($$
  insert into public.materials (course_id, kind, title, storage_path, added_by)
  values ('bbbbbbbb-0000-0000-0000-000000000000', 'slides', 'Sneaky', 'bbbbbbbb/sneaky.pdf',
          '11111111-1111-1111-1111-111111111111')
$$, '42501', null, 'students cannot add slides to other courses');

select throws_ok($$
  insert into public.materials (course_id, kind, title, storage_path, added_by, status)
  values ('aaaaaaaa-0000-0000-0000-000000000000', 'slides', 'Fake', 'aaaaaaaa/fake.pdf',
          '11111111-1111-1111-1111-111111111111', 'ready')
$$, '42501', null, 'students cannot mark their uploads as processed');

select throws_ok($$
  insert into public.courses (owner_id, title)
  values ('22222222-2222-2222-2222-222222222222', 'Planted')
$$, '42501', null, 'students cannot create courses for someone else');

select is_empty('select 1 from storage.objects', 'storage objects are not readable by users');

-- Admin ---------------------------------------------------------------------------------
reset role;
select pg_temp.act_as('33333333-3333-3333-3333-333333333333');

select results_eq($$select title from public.courses
    where id in ('aaaaaaaa-0000-0000-0000-000000000000', 'bbbbbbbb-0000-0000-0000-000000000000')
    order by title$$,
  $$values ('Biology'), ('Psychology')$$,
  'admins see every course, and student A changed nothing in B''s');
select is((select count(*)::int from public.materials
    where course_id in ('aaaaaaaa-0000-0000-0000-000000000000', 'bbbbbbbb-0000-0000-0000-000000000000')),
  2, 'admins see every material');
select lives_ok($$
  insert into public.materials (course_id, kind, title, storage_path, status)
  values ('aaaaaaaa-0000-0000-0000-000000000000', 'textbook', 'Biology 2e', 'aaaaaaaa/bio.pdf', 'queued')
$$, 'admins can add textbooks');

-- Storage -------------------------------------------------------------------------------
reset role;
select is((select public from storage.buckets where id = 'materials'), false,
  'the materials bucket is private');

select * from finish();
rollback;
