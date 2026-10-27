-- Review order is set by admins only, and only that column of a profile can change.
-- Run with `supabase test db`.
begin;
create extension if not exists pgtap with schema extensions;
select plan(5);

insert into auth.users (id, aud, role, email) values
  ('11111111-1111-1111-1111-111111111111', 'authenticated', 'authenticated', 'a@test.invalid'),
  ('99999999-9999-9999-9999-999999999999', 'authenticated', 'authenticated', 'admin@test.invalid');
update public.profiles set role = 'admin' where id = '99999999-9999-9999-9999-999999999999';

create function pg_temp.act_as(user_id uuid) returns void language sql as $$
  select set_config('request.jwt.claims', json_build_object('sub', user_id, 'role', 'authenticated')::text, true);
  set local role authenticated;
$$;

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
update public.profiles set review_order = 'separate';
reset role;
select is((select review_order::text from public.profiles where id = '11111111-1111-1111-1111-111111111111'),
  'mixed', 'students cannot change their own review order');

select pg_temp.act_as('99999999-9999-9999-9999-999999999999');
select lives_ok($$ update public.profiles set review_order = 'blocked'
  where id = '11111111-1111-1111-1111-111111111111' $$, 'admins set a student''s review order');
select throws_ok($$ update public.profiles set role = 'admin'
  where id = '11111111-1111-1111-1111-111111111111' $$, '42501', null, 'admins cannot change roles');
select throws_ok($$ update public.profiles set display_name = 'x'
  where id = '11111111-1111-1111-1111-111111111111' $$, '42501', null, 'or other profile fields');
reset role;
select is((select review_order::text from public.profiles where id = '11111111-1111-1111-1111-111111111111'),
  'blocked', 'the change is saved');

select * from finish();
rollback;
