-- Daily limits and kept figure descriptions (D96).
-- Run with `supabase test db`.
begin;
create extension if not exists pgtap with schema extensions;
select plan(5);

insert into auth.users (id, aud, role, email) values
  ('11111111-1111-1111-1111-111111111111', 'authenticated', 'authenticated', 'a@test.invalid');
insert into public.daily_questions (user_id, day, questions)
  values ('11111111-1111-1111-1111-111111111111', current_date, 3);
insert into public.figure_descriptions (image_sha256, model, kind, description)
  values (repeat('a', 64), 'm', 'diagram', 'd');

create function pg_temp.act_as(user_id uuid) returns void language sql as $$
  select set_config('request.jwt.claims', json_build_object('sub', user_id, 'role', 'authenticated')::text, true);
  set local role authenticated;
$$;

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
select throws_ok('select 1 from public.daily_questions', '42501', null,
  'students cannot read their question counts');
select throws_ok($$ update public.daily_questions set questions = 0 $$, '42501', null,
  'or reset them');
select throws_ok('select 1 from public.figure_descriptions', '42501', null,
  'or read kept figure descriptions');
reset role;

set local role anon;
select throws_ok('select 1 from public.figure_descriptions', '42501', null,
  'and neither can visitors');
reset role;

select throws_ok($$ insert into public.figure_descriptions (image_sha256, model, kind, description)
  values ('not-a-hash', 'm', 'diagram', 'd') $$, '23514', null, 'a description is kept by a SHA-256');

select * from finish();
rollback;
