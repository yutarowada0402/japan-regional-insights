-- Gold (long format): the central fact table of the project.
-- One row per region x year x indicator, in persons.
select
    region_code,
    year,
    case age_group
        when 'total' then 'total_population'
        when 'elderly_65plus' then 'elderly_population'
    end as indicator_code,
    value_persons as value,
    source_id,
    retrieved_at as updated_at
from {{ ref('stg_population_by_age_group') }}
