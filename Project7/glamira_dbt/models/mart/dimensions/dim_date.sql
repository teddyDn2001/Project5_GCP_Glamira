{{ config(tags=["mart", "dimension"]) }}

WITH bounds AS (
    SELECT
        MIN(event_date) AS min_date
        , MAX(event_date) AS max_date
    FROM {{ ref('stg_events__checkout_success') }}
)

SELECT
    CAST(FORMAT_DATE('%Y%m%d', date_day) AS INT64) AS date_key
    , date_day AS full_date
    , EXTRACT(YEAR FROM date_day) AS year_number
    , EXTRACT(QUARTER FROM date_day) AS quarter_number
    , EXTRACT(MONTH FROM date_day) AS month_number
    , FORMAT_DATE('%B', date_day) AS month_name
    , EXTRACT(WEEK FROM date_day) AS week_of_year
    , EXTRACT(DAY FROM date_day) AS day_of_month
    , FORMAT_DATE('%A', date_day) AS day_of_week
    , EXTRACT(DAYOFWEEK FROM date_day) AS day_of_week_number
    , (EXTRACT(DAYOFWEEK FROM date_day) BETWEEN 2 AND 6) AS is_weekday
    , NOT (EXTRACT(DAYOFWEEK FROM date_day) BETWEEN 2 AND 6) AS is_weekend
FROM bounds AS b
CROSS JOIN UNNEST(
    GENERATE_DATE_ARRAY(b.min_date, b.max_date, INTERVAL 1 DAY)
) AS date_day
