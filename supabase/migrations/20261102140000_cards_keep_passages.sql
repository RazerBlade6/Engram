-- Each card's sources keep the text of the passage they cite (D91). Reading a material
-- again replaces its chunks, which left cards pointing at chunks that no longer exist, and
-- review showed only the quoted words. New cards are written with the passage; this copies
-- it into existing cards wherever their chunk is still there. The heading path the chunk's
-- text starts with is removed, as the API does when it shows a passage.

update public.cards k
   set sources = (
     select jsonb_agg(
              case
                when e.s ? 'passage' or ch.id is null then e.s
                else e.s || jsonb_build_object(
                  'passage',
                  case
                    when starts_with(ch.content, array_to_string(ch.heading_path, ' > ') || E'\n\n')
                      then substr(ch.content,
                                  length(array_to_string(ch.heading_path, ' > ') || E'\n\n') + 1)
                    else ch.content
                  end)
              end
              order by e.n)
       from jsonb_array_elements(k.sources) with ordinality as e(s, n)
       left join public.chunks ch on ch.id = (e.s ->> 'chunk_id')::uuid
   )
 where exists (
   select 1 from jsonb_array_elements(k.sources) as e(s) where not e.s ? 'passage'
 );
