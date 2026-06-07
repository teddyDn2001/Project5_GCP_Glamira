{{ config(tags=["staging", "checkout"]) }}

/*
  Checkout events only — grain: one row per successful checkout event.
  IP stays here for join to ip_locations; NOT carried into dim_location.
*/
SELECT
    {{ mongo_oid('_id') }} AS event_id
    , COALESCE(event_name, collection) AS event_type
    , time_stamp
    , TIMESTAMP_SECONDS(time_stamp) AS event_ts
    , DATE(TIMESTAMP_SECONDS(time_stamp)) AS event_date
    , device_id
    , user_id_db
    , email_address
    , ip
    , order_id
    , CAST(product_id AS STRING) AS product_id
    , SAFE_CAST(price AS NUMERIC) AS price_raw
    , currency AS currency_code
    , is_paypal AS is_paypal_raw
    , country AS country_event
    , city AS city_event
    , cart_products
    , (
        SAFE_CAST(price AS NUMERIC) IS NOT NULL
    ) AS is_price_valid
FROM {{ source('glamira_raw', 'events') }}
WHERE COALESCE(event_name, collection) = 'checkout_success'
  AND {{ mongo_oid('_id') }} IS NOT NULL
