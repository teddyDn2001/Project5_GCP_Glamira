-- Data profiling for `${dataset}.products`.

SELECT 'row_count'                  AS metric, CAST(COUNT(*) AS STRING) AS value FROM `${project}.${dataset}.products`
UNION ALL
SELECT 'distinct_product_id',       CAST(COUNT(DISTINCT product_id) AS STRING)         FROM `${project}.${dataset}.products`
UNION ALL
SELECT 'rows_with_product_name',    CAST(COUNTIF(product_name IS NOT NULL AND product_name != '') AS STRING) FROM `${project}.${dataset}.products`
UNION ALL
SELECT 'rows_with_error',           CAST(COUNTIF(error IS NOT NULL AND error != '') AS STRING) FROM `${project}.${dataset}.products`
UNION ALL
SELECT 'distinct_status_codes',     CAST(COUNT(DISTINCT status) AS STRING)             FROM `${project}.${dataset}.products`
UNION ALL
SELECT 'min_updated_at',            CAST(MIN(updated_at) AS STRING)                    FROM `${project}.${dataset}.products`
UNION ALL
SELECT 'max_updated_at',            CAST(MAX(updated_at) AS STRING)                    FROM `${project}.${dataset}.products`;
