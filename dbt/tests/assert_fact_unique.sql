-- Singular test: fact grain must be unique per region/year/indicator.
-- Returns rows only when duplicates exist (test fails then).
select region_code, year, indicator_code, count(*) as n
from {{ ref('fact_regional_indicator') }}
group by region_code, year, indicator_code
having count(*) > 1
