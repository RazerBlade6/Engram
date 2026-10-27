-- Row-level security for course dates. Run with `supabase test db`.
begin;
create extension if not exists pgtap with schema extensions;
select plan(12);

insert into auth.users (id, aud, role, email) values
  ('11111111-1111-1111-1111-111111111111', 'authenticated', 'authenticated', 'a@test.invalid'),
  ('22222222-2222-2222-2222-222222222222', 'authenticated', 'authenticated', 'b@test.invalid'),
  ('33333333-3333-3333-3333-333333333333', 'authenticated', 'authenticated', 'c@test.invalid');
update public.profiles set role = 'admin' where id = '33333333-3333-3333-3333-333333333333';

insert into public.courses (id, owner_id, title) values
  ('aaaaaaaa-0000-0000-0000-000000000000', '11111111-1111-1111-1111-111111111111', 'Biology'),
  ('bbbbbbbb-0000-0000-0000-000000000000', '11111111-1111-1111-1111-111111111111', 'Chemistry');
insert into public.materials (id, course_id, kind, title, storage_path, status) values
  ('cccccccc-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0000-000000000000', 'textbook',
   'Biology 2e', 'aaaaaaaa/cccccccc/bio.pdf', 'ready'),
  ('cccccccc-0000-0000-0000-000000000002', 'bbbbbbbb-0000-0000-0000-000000000000', 'textbook',
   'Chemistry 2e', 'bbbbbbbb/cccccccc/chem.pdf', 'ready');
insert into public.sections (id, material_id, ordinal, level, title, page_start, page_end) values
  ('dddddddd-0000-0000-0000-000000000001', 'cccccccc-0000-0000-0000-000000000001', 0, 1, 'Chapter 1', 1, 9),
  ('dddddddd-0000-0000-0000-000000000002', 'cccccccc-0000-0000-0000-000000000002', 0, 1, 'Chapter 1', 1, 9);

create function pg_temp.act_as(user_id uuid) returns void language sql as $$
  select set_config('request.jwt.claims', json_build_object('sub', user_id, 'role', 'authenticated')::text, true);
  set local role authenticated;
$$;

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
select lives_ok($$ insert into public.course_dates (id, course_id, kind, title, on_date)
  values ('eeeeeeee-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0000-000000000000', 'exam', 'Midterm', '2026-11-13') $$,
  'owners add dates to their course');
select is((select count(*) from public.course_dates where course_id = 'aaaaaaaa-0000-0000-0000-000000000000'),
  1::bigint, 'and read them');

select lives_ok($$ insert into public.course_date_chapters (date_id, section_id)
  values ('eeeeeeee-0000-0000-0000-000000000001', 'dddddddd-0000-0000-0000-000000000001') $$,
  'owners say which chapters a date covers');
select throws_ok($$ insert into public.course_date_chapters (date_id, section_id)
  values ('eeeeeeee-0000-0000-0000-000000000001', 'dddddddd-0000-0000-0000-000000000002') $$,
  '42501', null, 'but only chapters from the date''s course');

select pg_temp.act_as('22222222-2222-2222-2222-222222222222');
select is((select count(*) from public.course_date_chapters), 0::bigint, 'others cannot read a date''s chapters');
delete from public.course_date_chapters;
select is((select count(*) from public.course_dates where course_id = 'aaaaaaaa-0000-0000-0000-000000000000'),
  0::bigint, 'others cannot read them');
select throws_ok($$ insert into public.course_dates (course_id, kind, title, on_date)
  values ('aaaaaaaa-0000-0000-0000-000000000000', 'quiz', 'Quiz', '2026-11-04') $$,
  '42501', null, 'or add to the course');
update public.course_dates set title = 'Changed';
delete from public.course_dates;

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
select is((select title from public.course_dates where id = 'eeeeeeee-0000-0000-0000-000000000001'),
  'Midterm', 'or change or delete them');
select is((select count(*) from public.course_date_chapters), 1::bigint, 'or their chapters');

select pg_temp.act_as('33333333-3333-3333-3333-333333333333');
select lives_ok($$ insert into public.course_dates (course_id, kind, title, on_date)
  values ('aaaaaaaa-0000-0000-0000-000000000000', 'deadline', 'Essay 1', '2026-11-20') $$,
  'admins add dates to any course');

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
update public.course_dates set on_date = '2026-11-14' where id = 'eeeeeeee-0000-0000-0000-000000000001';
delete from public.course_dates where kind = 'deadline';
reset role;
select is((select on_date from public.course_dates where id = 'eeeeeeee-0000-0000-0000-000000000001'),
  '2026-11-14'::date, 'owners change their dates');
select is((select count(*) from public.course_dates where course_id = 'aaaaaaaa-0000-0000-0000-000000000000'),
  1::bigint, 'and delete them');

select * from finish();
rollback;
