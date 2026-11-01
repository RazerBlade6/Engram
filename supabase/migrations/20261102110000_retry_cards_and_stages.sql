-- Two things the course page needs while work is under way or has failed.
--
-- Stages: while a material is 'processing', the worker records which step it is on, so the
-- page can say more than "Reading it now" during a wait that runs to minutes for a textbook.

create type public.material_stage as enum ('parsing', 'describing', 'indexing');

alter table public.materials add column stage public.material_stage;

-- Trying again: a chapter whose cards couldn't be made can be queued again in one step,
-- instead of unmarking and marking it. Students can't update covered_sections or touch the
-- job queue, so this function is the narrow exception, as queue_material is for uploads: it
-- only moves a failed chapter the caller can read back to 'pending' and queues its job.

create function public.retry_cards(section uuid) returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.covered_sections
     set cards_status = 'pending', cards_drafted = 0
   where section_id = section
     and cards_status = 'failed'
     and public.can_read_section(section);
  if not found then
    raise exception 'cards for section % cannot be retried', section using errcode = '42501';
  end if;

  insert into public.jobs (kind, payload)
  values ('generate_cards', jsonb_build_object('section_id', section));
end;
$$;

revoke execute on function public.retry_cards(uuid) from public, anon;
grant execute on function public.retry_cards(uuid) to authenticated;
