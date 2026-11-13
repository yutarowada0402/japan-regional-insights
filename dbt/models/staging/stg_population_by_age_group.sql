-- Silver: normalise Bronze rows to prefecture/year/age-group grain.
-- * region_code unified to the 2-digit prefecture code ('01000' -> '01')
-- * national total ('00000') excluded: this dataset is prefecture-level
-- * values converted from thousands to persons
-- * duplicates (same region/year/age group) resolved by latest retrieval
with raw as (
    select *
    from read_csv_auto('{{ var("bronze_csv_path") }}', header = true)
),

normalised as (
    select
        substr(cast(region_code_estat as varchar), 1, 2) as region_code,
        cast(year as integer) as year,
        cast(age_group as varchar) as age_group,
        cast(value_thousands as double) * 1000 as value_persons,
        cast(source_id as varchar) as source_id,
        cast(stats_data_id as varchar) as stats_data_id,
        cast(retrieved_at as timestamp) as retrieved_at
    from raw
    where cast(region_code_estat as varchar) <> '00000'
),

deduped as (
    select *
    from normalised
    qualify
        row_number() over (
            partition by region_code, year, age_group
            order by retrieved_at desc
        ) = 1
)

select * from deduped
