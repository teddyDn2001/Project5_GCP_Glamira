{{ config(tags=["staging"]) }}

/*
  IP reference for staging joins only. dim_location does NOT store ip (per model review).
*/
WITH ranked AS (
    SELECT
        ip
        , country_short
        , country_long AS country_name
        , region AS region_name
        , city AS city_name
        , latitude
        , longitude
        , timezone
        , updated_at
        , ROW_NUMBER() OVER (
            PARTITION BY ip
            ORDER BY updated_at DESC NULLS LAST
        ) AS rn
    FROM {{ source('glamira_raw', 'ip_locations') }}
    WHERE ip IS NOT NULL
)

SELECT
    ip
    , country_short
    , country_name
    , region_name
    , city_name
    , CASE
        WHEN latitude BETWEEN -90 AND 90 THEN latitude
    END AS latitude
    , CASE
        WHEN longitude BETWEEN -180 AND 180 THEN longitude
    END AS longitude
    , timezone
    , updated_at
FROM ranked
WHERE rn = 1
