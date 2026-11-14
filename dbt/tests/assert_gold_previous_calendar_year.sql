-- A rate must use the same region's immediately preceding calendar year.
select current_year.*
from {{ ref('gold_prefecture_year') }} current_year
left join {{ ref('gold_prefecture_year') }} previous_year
    on current_year.region_code = previous_year.region_code
    and previous_year.year = current_year.year - 1
where
    (previous_year.year is null and (
        current_year.prev_year_population is not null
        or current_year.population_change_rate is not null
    ))
    or (previous_year.year is not null and (
        current_year.prev_year_population is distinct from previous_year.total_population
        or current_year.population_change_rate is distinct from round(
            100.0 * (current_year.total_population - previous_year.total_population)
            / nullif(previous_year.total_population, 0), 3
        )
    ))
