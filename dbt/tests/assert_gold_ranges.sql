-- Singular test: value-range sanity for the Gold dashboard table.
-- Returns offending rows only (test fails then).
select *
from {{ ref('gold_prefecture_year') }}
where
    total_population <= 0
    or elderly_population < 0
    or elderly_population > total_population
    or aging_rate < 0
    or aging_rate > 100
    or (population_change_rate is not null and abs(population_change_rate) > 20)
