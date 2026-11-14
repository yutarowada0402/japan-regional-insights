-- Gold (wide format): dashboard-ready prefecture x year indicators.
-- Only compare consecutive calendar years. Missing years are not back-filled.
with pivoted as (
    select
        region_code,
        year,
        max(case when indicator_code = 'total_population' then value end)
            as total_population,
        max(case when indicator_code = 'elderly_population' then value end)
            as elderly_population,
        max(source_id) as source_id,
        max(updated_at) as updated_at
    from {{ ref('fact_regional_indicator') }}
    group by region_code, year
),

with_previous as (
    select
        current_year.*,
        previous_year.total_population as prev_year_population
    from pivoted current_year
    left join pivoted previous_year
        on current_year.region_code = previous_year.region_code
        and previous_year.year = current_year.year - 1
)

select
    p.region_code,
    r.region_name,
    p.year,
    p.total_population,
    p.elderly_population,
    round(100.0 * p.elderly_population / nullif(p.total_population, 0), 2)
        as aging_rate,
    p.prev_year_population,
    round(
        100.0 * (p.total_population - p.prev_year_population)
        / nullif(p.prev_year_population, 0),
        3
    ) as population_change_rate,
    p.source_id,
    p.updated_at
from with_previous p
left join {{ ref('dim_region') }} r on p.region_code = r.region_code
