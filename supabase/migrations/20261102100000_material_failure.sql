-- Why a material couldn't be read, so the course page can say what to do about it. The
-- worker sets it for a file it can tell is unreadable (scanned pages, a password, a damaged
-- file); a job that fails for any other reason leaves it to the trigger below, which records
-- 'stalled' for a job given up on because its worker died on every attempt and 'unknown'
-- otherwise. `error` keeps the technical detail for admins.

create type public.material_failure as enum ('no_text', 'protected', 'damaged', 'stalled', 'unknown');

alter table public.materials add column failure public.material_failure;

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
             -- engram.worker.queue.GAVE_UP
             case when new.last_error like 'Abandoned:%' then 'stalled' else 'unknown' end
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
