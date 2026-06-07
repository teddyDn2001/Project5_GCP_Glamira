{{ config(tags=["mart", "dimension"]) }}

/*
  Where — geographic attributes ONLY (no ip / ip_hash on dim per model review).

  Built from distinct locations seen on checkout events via ip_locations join,
  with fallback to event country/city when IP lookup is missing.
*/
WITH event_geo AS (
    SELECT
        e.event_id
        , COALESCE(ip.country_short, e.country_event) AS country_short
        , COALESCE(ip.country_name, e.country_event) AS country_name
        , COALESCE(ip.region_name, CAST(NULL AS STRING)) AS region_name
        , COALESCE(ip.city_name, e.city_event) AS city_name
        , ip.latitude
        , ip.longitude
        , ip.timezone
        , CASE
            WHEN ip.ip IS NOT NULL THEN 'ip2location'
            ELSE 'event_fallback'
        END AS geo_source
    FROM {{ ref('stg_events__checkout_success') }} AS e
    LEFT JOIN {{ ref('stg_ip_locations') }} AS ip
        ON e.ip = ip.ip
)

, distinct_locations AS (
    SELECT DISTINCT
        country_short
        , country_name
        , region_name
        , city_name
        , latitude
        , longitude
        , timezone
        , geo_source
    FROM event_geo
    WHERE country_name IS NOT NULL
       OR city_name IS NOT NULL
)

SELECT
    ROW_NUMBER() OVER (
        ORDER BY country_short, country_name, region_name, city_name
    ) AS location_key
    , country_short
    , country_name
    , region_name
    , city_name
    , latitude
    , longitude
    , timezone
    , geo_source
FROM distinct_locations
