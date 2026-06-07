{{ config(tags=["staging", "checkout"]) }}

/*
  Line-item grain for fact_sales_order_detail.

  1) Unnest cart_products JSON array when present.
  2) Fallback to top-level product_id + price_raw for single-item checkouts.
*/
WITH checkout_events AS (
    SELECT * FROM {{ ref('stg_events__checkout_success') }}
)

, cart_array_lines AS (
    SELECT
        e.event_id
        , e.order_id
        , e.currency_code
        , e.price_raw AS event_price_raw
        , line_item
        , line_offset + 1 AS line_number
    FROM checkout_events AS e
    , UNNEST(
        IFNULL(JSON_QUERY_ARRAY(e.cart_products, '$'), [])
    ) AS line_item WITH OFFSET AS line_offset
    WHERE JSON_TYPE(e.cart_products) = 'array'
      AND ARRAY_LENGTH(JSON_QUERY_ARRAY(e.cart_products, '$')) > 0
)

, from_cart AS (
    SELECT
        CONCAT(event_id, '-', CAST(line_number AS STRING)) AS line_item_id
        , event_id
        , order_id
        , COALESCE(
            JSON_VALUE(line_item, '$.product_id')
            , JSON_VALUE(line_item, '$.productId')
            , JSON_VALUE(line_item, '$.id')
        ) AS product_id
        , COALESCE(
            SAFE_CAST(JSON_VALUE(line_item, '$.qty') AS INT64)
            , SAFE_CAST(JSON_VALUE(line_item, '$.quantity') AS INT64)
            , SAFE_CAST(JSON_VALUE(line_item, '$.order_qty') AS INT64)
            , 1
        ) AS order_qty
        , COALESCE(
            SAFE_CAST(JSON_VALUE(line_item, '$.price') AS NUMERIC)
            , SAFE_CAST(JSON_VALUE(line_item, '$.amount') AS NUMERIC)
            , SAFE_CAST(JSON_VALUE(line_item, '$.line_amount') AS NUMERIC)
            , event_price_raw
        ) AS line_amount
        , currency_code
        , line_number
    FROM cart_array_lines
    WHERE COALESCE(
        JSON_VALUE(line_item, '$.product_id')
        , JSON_VALUE(line_item, '$.productId')
        , JSON_VALUE(line_item, '$.id')
    ) IS NOT NULL
)

, from_event_level AS (
    SELECT
        CONCAT(event_id, '-', '1') AS line_item_id
        , event_id
        , order_id
        , product_id
        , 1 AS order_qty
        , price_raw AS line_amount
        , currency_code
        , 1 AS line_number
    FROM checkout_events
    WHERE product_id IS NOT NULL
      AND event_id NOT IN (SELECT DISTINCT event_id FROM from_cart)
)

SELECT
    line_item_id
    , event_id
    , order_id
    , product_id
    , order_qty
    , line_amount
    , SAFE_DIVIDE(line_amount, order_qty) AS unit_price
    , currency_code
    , line_number
FROM from_cart

UNION ALL

SELECT
    line_item_id
    , event_id
    , order_id
    , product_id
    , order_qty
    , line_amount
    , SAFE_DIVIDE(line_amount, order_qty) AS unit_price
    , currency_code
    , line_number
FROM from_event_level
