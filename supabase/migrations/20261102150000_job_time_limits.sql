-- Every job has its own time limit (D92). A material whose reading ran past its limit shows
-- as 'stalled', like one whose worker died on every attempt: in both cases the file took
-- too long to read, and the course page says so. Otherwise as in material_failure.

create or replace function public.mark_failed_job_work() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.kind = 'ingest_material' then
    update public.materials
       set status = 'failed', error = new.last_error,
           failure = coalesce(
             failure,
             -- engram.worker.queue.GAVE_UP and engram.worker.main.TimedOut
             case when new.last_error like 'Abandoned:%' or new.last_error like 'TimedOut:%'
                  then 'stalled' else 'unknown' end
               ::public.material_failure)
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
