-- How many cards a chapter's generation has drafted so far, so the course page can show
-- progress while a student waits (D53). The worker adds to it as each batch comes back, and
-- resets it when a run starts. It counts cards before repeats across batches are dropped, so
-- the final number can be a little lower.
--
-- Marking a chapter inserts a fresh covered_sections row, so the count starts at 0 each time;
-- unmarking deletes the row. Students can't update the table; the worker's connection can.
alter table public.covered_sections
  add column cards_drafted integer not null default 0;
