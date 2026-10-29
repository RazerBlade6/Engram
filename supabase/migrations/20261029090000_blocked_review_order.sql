-- Blocked becomes the default review order (D55). Existing profiles keep the order they have;
-- an admin changes them by hand.
alter table public.profiles alter column review_order set default 'blocked';
