-- Ask's vector search measures every passage of the course instead of using an approximate
-- index (D94). The HNSW index found the nearest passages across all courses before the
-- search narrowed them to one, so a small course could get no matches once the planner
-- chose it. Nothing else searches by vector, so the index is dropped: it only slowed
-- ingestion. A course is a few thousand passages, which an exact scan handles in
-- milliseconds; the (material_id, ordinal) index keeps that scan to the course.

drop index public.chunks_embedding_idx;
