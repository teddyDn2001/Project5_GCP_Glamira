{{ config(schema='mart', tags=["mart", "fact"]) }}

/*
  Transaction fact — grain: one checkout line item (checkout_success).
  Payment: is_paypal on fact (no dim_payment_method per model review).
*/
WITH lines AS (
    SELECT * FROM {{ ref('stg_checkout_line_items') }}
)

, events AS (
    SELECT * FROM {{ ref('stg_events__checkout_success') }}
)

, event_geo AS (
    SELECT
        e.event_id
        , COALESCE(ip.country_short, e.country_event) AS country_short
        , COALESCE(ip.country_name, e.country_event) AS country_name
        , COALESCE(ip.region_name, CAST(NULL AS STRING)) AS region_name
        , COALESCE(ip.city_name, e.city_event) AS city_name
        , ip.latitude
        , ip.longitude
        , ip.timezone
        , CASE WHEN ip.ip IS NOT NULL THEN 'ip2location' ELSE 'event_fallback' END AS geo_source
    FROM events AS e
    LEFT JOIN {{ ref('stg_ip_locations') }} AS ip
        ON e.ip = ip.ip
)

SELECT
    ROW_NUMBER() OVER (ORDER BY l.line_item_id) AS sales_order_line_key
    , CAST(FORMAT_DATE('%Y%m%d', e.event_date) AS INT64) AS date_key
    , c.customer_key
    , p.product_key
    , loc.location_key
    , CASE
        WHEN LOWER(e.is_paypal_raw) IN ('true', '1', 'yes') THEN 'paypal'
        WHEN LOWER(e.is_paypal_raw) IN ('false', '0', 'no') THEN 'other'
        ELSE 'unknown'
    END AS is_paypal
    , l.event_id
    , l.line_item_id
    , l.order_id
    , l.order_qty
    , l.line_amount AS sales_amount
    , l.unit_price
    , l.currency_code
FROM lines AS l
INNER JOIN events AS e
    ON l.event_id = e.event_id
INNER JOIN {{ ref('dim_product') }} AS p
    ON l.product_id = p.product_id
INNER JOIN {{ ref('dim_customer') }} AS c
    ON e.device_id = c.device_id
    AND IFNULL(e.user_id_db, '') = IFNULL(c.user_id_db, '')
    AND IFNULL(e.email_address, '') = IFNULL(c.email_address, '')
INNER JOIN event_geo AS eg
    ON e.event_id = eg.event_id
INNER JOIN {{ ref('dim_location') }} AS loc
    ON IFNULL(eg.country_short, '') = IFNULL(loc.country_short, '')
    AND IFNULL(eg.country_name, '') = IFNULL(loc.country_name, '')
    AND IFNULL(eg.region_name, '') = IFNULL(loc.region_name, '')
    AND IFNULL(eg.city_name, '') = IFNULL(loc.city_name, '')
    AND IFNULL(eg.geo_source, '') = IFNULL(loc.geo_source, '')
