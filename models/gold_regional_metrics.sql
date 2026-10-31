select prefecture_code, prefecture, year,
  max(value) filter (where indicator = 'population') as population,
  max(value) filter (where indicator = 'aging_rate') as aging_rate,
  max(unit) filter (where indicator = 'population') as population_unit,
  max(unit) filter (where indicator = 'aging_rate') as aging_rate_unit,
  max(source) as source, max(stats_data_id) as stats_data_id,
  max(updated_at) as updated_at
from {{ source('main', 'silver_observations') }}
group by prefecture_code, prefecture, year
