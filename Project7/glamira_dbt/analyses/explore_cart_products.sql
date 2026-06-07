-- Run on BigQuery before extending stg_checkout_line_items with UNNEST:
--   dbt compile && dbt show --select explore_cart_products
-- Or paste in Console:

SELECT
    cart_products
    , order_id
    , product_id
    , price
    , currency
FROM `unigap-de-glamira-data.glamira_raw.events`
WHERE COALESCE(event_name, collection) = 'checkout_success'
  AND cart_products IS NOT NULL
LIMIT 20
