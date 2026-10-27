-- Waking the worker. In production the worker scales to zero (D35), so a new job asks it to
-- start: after any insert into the queue, one HTTP request goes to the worker's wake URL.
-- The URL and its token live in Vault, set once per deployment (see docs/DEPLOY.md). Where
-- they aren't set, as in local development, nothing is sent and a polling worker picks the
-- job up instead. pg_net sends the request after the transaction commits, and not at all if
-- it rolls back. Retries that wait for their backoff are found by the worker's periodic sweep.

create extension if not exists pg_net with schema extensions;

create function public.wake_worker() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  wake_url text;
  wake_token text;
begin
  select decrypted_secret into wake_url
    from vault.decrypted_secrets where name = 'worker_wake_url';
  if wake_url is null then
    return null;
  end if;
  select decrypted_secret into wake_token
    from vault.decrypted_secrets where name = 'worker_wake_token';
  perform net.http_post(
    url := wake_url,
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer ' || coalesce(wake_token, '')
    ),
    body := '{}'::jsonb,
    timeout_milliseconds := 10000
  );
  return null;
end;
$$;

revoke execute on function public.wake_worker() from public, anon, authenticated;

create trigger jobs_wake_worker after insert on public.jobs
  for each statement execute function public.wake_worker();
