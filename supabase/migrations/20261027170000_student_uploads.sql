-- Student uploads. A student inserts a material (status 'uploading'; see the materials insert
-- policy), the API stores the file, then calls queue_material in the same transaction: the
-- material becomes 'queued' and its ingestion job is created, both committed together so the
-- worker never sees a job for a material that doesn't exist yet.
--
-- Students cannot update materials or touch the job queue directly. This function is the one
-- narrow exception: it only moves a material the caller can read from 'uploading' to
-- 'queued', so a finished material can't be re-ingested at will.

create function public.queue_material(material uuid) returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.materials
     set status = 'queued'
   where id = material
     and status = 'uploading'
     and public.can_read_material(id);
  if not found then
    raise exception 'material % cannot be queued', material using errcode = '42501';
  end if;

  insert into public.jobs (kind, payload)
  values ('ingest_material', jsonb_build_object('material_id', material));
end;
$$;

revoke execute on function public.queue_material(uuid) from public, anon;
grant execute on function public.queue_material(uuid) to authenticated;

-- Students remove their own uploads (a wrong file, an old version), but not the textbook a
-- course is built on: that would take its chapters and coverage with it.
drop policy "Course owners and admins delete materials" on public.materials;

create policy "Course owners delete slides; admins delete anything"
  on public.materials for delete to authenticated
  using (
    (select public.is_admin())
    or (kind = 'slides' and (select public.owns_course(course_id)))
  );
