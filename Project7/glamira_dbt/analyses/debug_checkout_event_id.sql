-- Paste in BQ Console if staging count is still 0:
SELECT
    COUNT(*) AS n_checkout_success
    , COUNTIF(JSON_VALUE(_id, '$.oid') IS NOT NULL) AS n_oid_plain
    , COUNTIF(JSON_VALUE(_id, '$."$oid"') IS NOT NULL) AS n_oid_dollar
    , COUNTIF(
        COALESCE(
            JSON_VALUE(_id, '$."$oid"')
            , REGEXP_EXTRACT(TO_JSON_STRING(_id), r'"\$oid"\s*:\s*"([^"]+)"')
        ) IS NOT NULL
    ) AS n_event_id_ok
FROM `unigap-de-glamira-data.glamira_raw.events`
WHERE COALESCE(event_name, collection) = 'checkout_success'
