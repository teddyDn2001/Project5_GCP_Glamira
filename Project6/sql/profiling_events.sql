-- Data profiling for `${dataset}.events` (raw layer).
-- Placeholders ${project}, ${dataset} are substituted by scripts/30_data_profiling.py
-- before submitting to BigQuery.

-- 1) Row count and partition coverage
SELECT
  'row_count'                                                AS metric,
  CAST(COUNT(*) AS STRING)                                   AS value
FROM `${project}.${dataset}.events`
UNION ALL
SELECT
  'partition_dates_covered',
  CAST(COUNT(DISTINCT DATE(_PARTITIONTIME)) AS STRING)
FROM `${project}.${dataset}.events`
UNION ALL
SELECT
  'distinct_event_names',
  CAST(COUNT(DISTINCT COALESCE(event_name, collection)) AS STRING)
FROM `${project}.${dataset}.events`
UNION ALL
SELECT
  'distinct_product_ids',
  CAST(COUNT(DISTINCT product_id) AS STRING)
FROM `${project}.${dataset}.events`
UNION ALL
SELECT
  'distinct_device_ids',
  CAST(COUNT(DISTINCT device_id) AS STRING)
FROM `${project}.${dataset}.events`
UNION ALL
SELECT
  'distinct_ips',
  CAST(COUNT(DISTINCT ip) AS STRING)
FROM `${project}.${dataset}.events`
UNION ALL
SELECT
  'min_time_stamp',
  CAST(MIN(time_stamp) AS STRING)
FROM `${project}.${dataset}.events`
UNION ALL
SELECT
  'max_time_stamp',
  CAST(MAX(time_stamp) AS STRING)
FROM `${project}.${dataset}.events`;
