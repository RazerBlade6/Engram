-- A job that fails for good marks its work failed: the material it was reading, or the
-- chapter whose cards it was making. Done here rather than in the worker's handlers so it
-- covers every way a job ends up failed: an error on its last attempt, a permanent error,
-- and a job given up on because its worker died on every attempt (out of memory on a large
-- book, say), which no handler is left running to report. Until then the work stays
-- 'processing' or 'pending', so an attempt that will be retried doesn't show as a failure.

create function public.mark_failed_job_work() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.kind = 'ingest_material' then
    update public.materials
       set status = 'failed', error = new.last_error
     where id::text = new.payload ->> 'material_id'
       and status in ('queued', 'processing');
  elsif new.kind = 'generate_cards' then
    update public.covered_sections
       set cards_status = 'failed'
     where section_id::text = new.payload ->> 'section_id'
       and cards_status = 'pending';
  end if;
  return null;
end;
$$;

revoke execute on function public.mark_failed_job_work() from public, anon, authenticated;

create trigger jobs_mark_failed_work after update of status on public.jobs
  for each row
  when (new.status = 'failed' and old.status is distinct from 'failed')
  execute function public.mark_failed_job_work();
