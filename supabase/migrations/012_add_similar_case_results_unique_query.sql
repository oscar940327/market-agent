do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'similar_case_results_unique_query'
    ) then
        alter table public.similar_case_results
            add constraint similar_case_results_unique_query
            unique (query_ticker, query_date);
    end if;
end $$;
