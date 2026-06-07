{{ config(tags=["mart", "dimension"]) }}

/*
  Who — device / user / email_address on dim (hash via SHA256 in Looker view when exposing).
*/
WITH src AS (
    SELECT DISTINCT
        device_id
        , user_id_db
        , email_address
    FROM {{ ref('stg_events__checkout_success') }}
    WHERE device_id IS NOT NULL
       OR user_id_db IS NOT NULL
       OR email_address IS NOT NULL
)

SELECT
    ROW_NUMBER() OVER (ORDER BY device_id, user_id_db, email_address) AS customer_key
    , device_id
    , user_id_db
    , email_address
    , (
        user_id_db IS NOT NULL
        OR email_address IS NOT NULL
    ) AS is_identified_user
FROM src
