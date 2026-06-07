{{ config(tags=["mart", "dimension"]) }}

SELECT
    ROW_NUMBER() OVER (ORDER BY product_id) AS product_key
    , product_id
    , product_name
    , source_url
    , crawl_status_code
    , is_crawl_success
    , updated_at AS product_updated_at
FROM {{ ref('stg_products') }}
