{% macro mongo_oid(json_col) %}
COALESCE(
    JSON_VALUE({{ json_col }}, '$."$oid"')
    , REGEXP_EXTRACT(TO_JSON_STRING({{ json_col }}), r'"\$oid"\s*:\s*"([^"]+)"')
)
{% endmacro %}
