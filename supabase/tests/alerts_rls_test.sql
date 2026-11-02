-- The operator's alert records are invisible to users and visitors (D99).
-- Run with `supabase test db`.
begin;
create extension if not exists pgtap with schema extensions;
select plan(6);

insert into public.api_errors (method, route, error) values ('GET', '/x', 'KeyError at engram/x.py:1');
insert into public.alerts_sent (kind, key) values ('api_error', '1');

set local role authenticated;
select throws_ok('select 1 from public.api_errors', '42501', null, 'users cannot read API errors');
select throws_ok($$ insert into public.api_errors (method, route, error) values ('GET', '/', 'x') $$,
  '42501', null, 'or record them');
select throws_ok('select 1 from public.alerts_sent', '42501', null, 'or read which alerts were sent');
reset role;

set local role anon;
select throws_ok('select 1 from public.api_errors', '42501', null, 'visitors cannot read API errors');
select throws_ok('select 1 from public.alerts_sent', '42501', null, 'or sent alerts');
reset role;

select is((select count(*)::int from public.alerts_sent where kind = 'api_error' and key = '1'), 1,
  'the service role reads and writes both');

select * from finish();
rollback;
