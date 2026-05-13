-- Data profiling for `${dataset}.ip_locations`.

SELECT 'row_count'              AS metric, CAST(COUNT(*) AS STRING) AS value FROM `${project}.${dataset}.ip_locations`
UNION ALL
SELECT 'distinct_ip',           CAST(COUNT(DISTINCT ip) AS STRING)         FROM `${project}.${dataset}.ip_locations`
UNION ALL
SELECT 'distinct_country',      CAST(COUNT(DISTINCT country_short) AS STRING) FROM `${project}.${dataset}.ip_locations`
UNION ALL
SELECT 'min_latitude',          CAST(MIN(latitude) AS STRING)              FROM `${project}.${dataset}.ip_locations`
UNION ALL
SELECT 'max_latitude',          CAST(MAX(latitude) AS STRING)              FROM `${project}.${dataset}.ip_locations`
UNION ALL
SELECT 'min_longitude',         CAST(MIN(longitude) AS STRING)             FROM `${project}.${dataset}.ip_locations`
UNION ALL
SELECT 'max_longitude',         CAST(MAX(longitude) AS STRING)             FROM `${project}.${dataset}.ip_locations`
UNION ALL
SELECT 'min_updated_at',        CAST(MIN(updated_at) AS STRING)            FROM `${project}.${dataset}.ip_locations`
UNION ALL
SELECT 'max_updated_at',        CAST(MAX(updated_at) AS STRING)            FROM `${project}.${dataset}.ip_locations`;
