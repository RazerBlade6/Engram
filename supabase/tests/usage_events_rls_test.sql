-- Usage events are logged only for people who agreed, and only admins read them.
-- Run with `supabase test db`.
begin;
create extension if not exists pgtap with schema extensions;
select plan(9);

insert into auth.users (id, aud, role, email) values
  ('11111111-1111-1111-1111-111111111111', 'authenticated', 'authenticated', 'a@test.invalid'),
  ('22222222-2222-2222-2222-222222222222', 'authenticated', 'authenticated', 'b@test.invalid'),
  ('99999999-9999-9999-9999-999999999999', 'authenticated', 'authenticated', 'admin@test.invalid');
update public.profiles set role = 'admin' where id = '99999999-9999-9999-9999-999999999999';

create function pg_temp.act_as(user_id uuid) returns void language sql as $$
  select set_config('request.jwt.claims', json_build_object('sub', user_id, 'role', 'authenticated')::text, true);
  set local role authenticated;
$$;

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
select throws_ok($$ insert into public.usage_events (name) values ('page_view') $$,
  '42501', null, 'nothing is logged before consent');
update public.profiles set usage_consent_at = now();
reset role;
select is((select usage_consent_at from public.profiles where id = '11111111-1111-1111-1111-111111111111'),
  null, 'students cannot record their own consent');

select pg_temp.act_as('99999999-9999-9999-9999-999999999999');
select lives_ok($$ update public.profiles set usage_consent_at = now()
  where id = '11111111-1111-1111-1111-111111111111' $$, 'admins record consent');

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
select lives_ok($$ insert into public.usage_events (name, data) values ('review', '{"rating": 3}') $$,
  'consenting students log events');
select throws_ok($$ insert into public.usage_events (user_id, name)
  values ('22222222-2222-2222-2222-222222222222', 'review') $$,
  '42501', null, 'but only as themselves');
select is((select count(*) from public.usage_events), 0::bigint, 'and cannot read events back');
select throws_ok($$ delete from public.usage_events $$, '42501', null, 'or delete them');

select pg_temp.act_as('99999999-9999-9999-9999-999999999999');
select is((select count(*) from public.usage_events where user_id = '11111111-1111-1111-1111-111111111111'),
  1::bigint, 'admins read events');

select pg_temp.act_as('22222222-2222-2222-2222-222222222222');
select is(public.logs_usage(), false, 'others are still not logged');

select * from finish();
rollback;
