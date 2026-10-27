-- A new job wakes the worker only where a wake URL is set.
-- Run with `supabase test db`.
begin;
create extension if not exists pgtap with schema extensions;
select plan(3);

create temp table sent as select count(*) as n from net.http_request_queue;

insert into public.jobs (kind) values ('ingest_material');
select is((select count(*) from net.http_request_queue), (select n from sent),
  'without a wake URL, no request is sent');

select vault.create_secret('https://worker.test.invalid/wake', 'worker_wake_url');
select vault.create_secret('a-token', 'worker_wake_token');
insert into public.jobs (kind) values ('ingest_material'), ('generate_cards');
select is((select count(*) from net.http_request_queue), (select n from sent) + 1,
  'one request per insert, however many jobs it adds');
select is(
  (select headers ->> 'Authorization' from net.http_request_queue order by id desc limit 1),
  'Bearer a-token', 'the request carries the wake token');

select * from finish();
rollback;
