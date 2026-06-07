{{ config(schema='mart', materialized='view', tags=['mart', 'looker']) }}

/*
  Denormalized mart for Looker Studio — matches teacher "Sale Performance Dashboard".
  No PII: dim_customer not joined (email stays out of BI layer).
  metal_type / stone_type: parsed from product_name (jewelry catalog naming).
*/
SELECT
    f.sales_order_line_key
    , f.order_id
    , f.event_id
    , f.order_qty
    , f.sales_amount
    , f.unit_price
    , f.currency_code
    , f.is_paypal
    , d.full_date
    , d.year_number
    , d.month_number
    , d.month_name
    , d.quarter_number
    , d.day_of_week
    , p.product_id
    , p.product_name
    , loc.country_name
    , loc.country_short
    , loc.city_name
    , loc.region_name
    , CASE
        WHEN REGEXP_CONTAINS(LOWER(p.product_name), r'18k|750') THEN '18K Gold - 750'
        WHEN REGEXP_CONTAINS(LOWER(p.product_name), r'14k|585') THEN '14K Gold - 585'
        WHEN REGEXP_CONTAINS(LOWER(p.product_name), r'9k|375') THEN '9K Gold - 375'
        WHEN REGEXP_CONTAINS(LOWER(p.product_name), r'silver|925') THEN 'Silver - 925'
        WHEN REGEXP_CONTAINS(LOWER(p.product_name), r'platinum|950') THEN 'Platinum - 950'
        ELSE 'Not Defined'
    END AS metal_type
    , CASE
        WHEN REGEXP_CONTAINS(LOWER(p.product_name), r'diamond') THEN 'Diamond'
        WHEN REGEXP_CONTAINS(LOWER(p.product_name), r'sapphire') THEN 'White Sapphire'
        WHEN REGEXP_CONTAINS(LOWER(p.product_name), r'topaz') THEN 'White Topaz'
        WHEN REGEXP_CONTAINS(LOWER(p.product_name), r'zirconia') THEN 'Zirconia'
        WHEN REGEXP_CONTAINS(LOWER(p.product_name), r'emerald') THEN 'Emerald'
        WHEN REGEXP_CONTAINS(LOWER(p.product_name), r'ruby') THEN 'Ruby'
        ELSE 'Not Defined'
    END AS stone_type
FROM {{ ref('fact_sales_order_detail') }} AS f
INNER JOIN {{ ref('dim_date') }} AS d
    ON f.date_key = d.date_key
INNER JOIN {{ ref('dim_product') }} AS p
    ON f.product_key = p.product_key
INNER JOIN {{ ref('dim_location') }} AS loc
    ON f.location_key = loc.location_key
