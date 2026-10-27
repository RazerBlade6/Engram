-- Raise the per-file limit on uploaded materials from 50 MiB (the free-tier ceiling) to
-- 500 MiB, which fits full textbooks. The project-wide upload limit (dashboard: Storage >
-- Settings) must be at least as high, or it still applies.

update storage.buckets
   set file_size_limit = 524288000
 where id = 'materials';
