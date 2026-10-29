-- When someone finished or skipped the welcome tour, so it shows once per account rather than
-- once per browser (D60). Null until then.
--
-- Students cannot update their profile (only admins can, and only some columns), so this
-- function is the one narrow exception: it records the tour for the caller and nothing else.

alter table public.profiles add column welcomed_at timestamptz;

create function public.mark_welcomed() returns void
language sql
security definer
set search_path = ''
as $$
  update public.profiles
     set welcomed_at = coalesce(welcomed_at, now())
   where id = (select auth.uid());
$$;

revoke execute on function public.mark_welcomed() from public, anon;
grant execute on function public.mark_welcomed() to authenticated;
