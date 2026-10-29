-- Students record that they've seen the welcome tour, for themselves only.
-- Run with `supabase test db`.
begin;
create extension if not exists pgtap with schema extensions;
select plan(4);

insert into auth.users (id, aud, role, email) values
  ('11111111-1111-1111-1111-111111111111', 'authenticated', 'authenticated', 'a@test.invalid'),
  ('22222222-2222-2222-2222-222222222222', 'authenticated', 'authenticated', 'b@test.invalid');

create function pg_temp.act_as(user_id uuid) returns void language sql as $$
  select set_config('request.jwt.claims', json_build_object('sub', user_id, 'role', 'authenticated')::text, true);
  set local role authenticated;
$$;

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
select throws_ok($$ update public.profiles set welcomed_at = now() $$,
  '42501', null, 'students cannot set the column directly');
select public.mark_welcomed();
reset role;
select isnt((select welcomed_at from public.profiles where id = '11111111-1111-1111-1111-111111111111'),
  null, 'mark_welcomed records the tour');
select is((select welcomed_at from public.profiles where id = '22222222-2222-2222-2222-222222222222'),
  null, 'and only for the caller');

set local role anon;
select throws_ok($$ select public.mark_welcomed() $$, '42501', null, 'signed-out visitors cannot call it');
reset role;

select * from finish();
rollback;
