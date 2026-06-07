{{ config(tags=["staging"]) }}

WITH ranked AS (
    SELECT
        CAST(product_id AS STRING) AS product_id
        , product_name
        , source_url
        , status AS crawl_status_code
        , error AS crawl_error
        , (status = 200) AS is_crawl_success
        , updated_at
        , ROW_NUMBER() OVER (
            PARTITION BY product_id
            ORDER BY updated_at DESC NULLS LAST
        ) AS rn
    FROM {{ source('glamira_raw', 'products') }}
    WHERE product_id IS NOT NULL
)

SELECT
    product_id
    , product_name
    , source_url
    , crawl_status_code
    , crawl_error
    , is_crawl_success
    , updated_at
FROM ranked
WHERE rn = 1
