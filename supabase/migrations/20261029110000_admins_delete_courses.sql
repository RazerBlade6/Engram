-- Deleting a course takes its chapters, cards and review history with it, with no undo, so
-- only admins may do it (from the admin page). Owners could before.

drop policy "Owners and admins delete courses" on public.courses;

create policy "Admins delete courses"
  on public.courses for delete to authenticated
  using ((select public.is_admin()));
