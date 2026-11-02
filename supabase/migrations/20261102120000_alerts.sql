-- Alerts for the operator (D99): failed jobs, API errors and inference spend are checked
-- every 15 minutes by the worker's sweep, which emails what it finds.
--
-- api_errors: one row per request the API failed with a server error. It holds where the
-- error happened (route, exception type, file and line), never its message or anything a
-- user sent: the traceback is in the API's logs.
--
-- alerts_sent: what has been emailed already, so each failure is reported once.
--
-- Both are written by the API and the worker only. Like the job queue, they are invisible
-- to users: RLS is enabled with no policies.

create table public.api_errors (
  id bigint generated always as identity primary key,
  method text not null,
  route text not null,
  status integer,
  error text not null,
  created_at timestamptz not null default now()
);

create index api_errors_created_at_idx on public.api_errors (created_at);

alter table public.api_errors enable row level security;
revoke all on public.api_errors from anon, authenticated;

create table public.alerts_sent (
  kind text not null,
  key text not null,
  sent_at timestamptz not null default now(),
  primary key (kind, key)
);

alter table public.alerts_sent enable row level security;
revoke all on public.alerts_sent from anon, authenticated;

-- For finding recently failed jobs without scanning the whole queue.
create index jobs_failed_idx on public.jobs (updated_at) where status = 'failed';
