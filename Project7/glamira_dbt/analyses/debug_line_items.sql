-- Run in BQ Console to explain empty fact_sales_order_detail

SELECT
    COUNT(*) AS n_checkout_success
    , COUNTIF(product_id IS NOT NULL) AS n_top_level_product_id
    , COUNTIF(cart_products IS NOT NULL) AS n_has_cart_products
    , COUNTIF(JSON_TYPE(cart_products) = 'array') AS n_cart_is_array
    , COUNTIF(
        JSON_TYPE(cart_products) = 'array'
        AND ARRAY_LENGTH(JSON_QUERY_ARRAY(cart_products, '$')) > 0
    ) AS n_cart_nonempty_array
FROM `unigap-de-glamira-data.glamira_staging.stg_events__checkout_success`
