-- Cancelling jobs whose work was removed. Deleting a material (or the course holding it)
-- cancels its ingestion, and deleting a chapter, which deleting its material does too,
-- cancels its card generation. A running job's worker notices at its next lock renewal
-- (within a minute) and stops, so a removed textbook is not read to the end.

alter type public.job_status add value 'cancelled';

create function public.cancel_jobs_for_material() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.jobs
     set status = 'cancelled', last_error = 'Cancelled: the material was removed',
         locked_at = null, locked_by = null
   where kind = 'ingest_material'
     and payload ->> 'material_id' = old.id::text
     and status in ('queued', 'running');
  return null;
end;
$$;

create function public.cancel_jobs_for_section() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.jobs
     set status = 'cancelled', last_error = 'Cancelled: the chapter was removed',
         locked_at = null, locked_by = null
   where kind = 'generate_cards'
     and payload ->> 'section_id' = old.id::text
     and status in ('queued', 'running');
  return null;
end;
$$;

revoke execute on function public.cancel_jobs_for_material() from public, anon, authenticated;
revoke execute on function public.cancel_jobs_for_section() from public, anon, authenticated;

create trigger materials_cancel_jobs after delete on public.materials
  for each row execute function public.cancel_jobs_for_material();

create trigger sections_cancel_jobs after delete on public.sections
  for each row execute function public.cancel_jobs_for_section();
