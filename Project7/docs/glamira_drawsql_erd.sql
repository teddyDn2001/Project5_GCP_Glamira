-- Glamira P7 — drawSQL ERD (all FK inline so connector lines appear)
-- Import ENTIRE file: drawSQL → New diagram → Import → PostgreSQL → paste all
-- Do NOT import twice (avoids duplicate tables)

CREATE SCHEMA glamira_raw;
CREATE SCHEMA staging;
CREATE SCHEMA mart;

-- ========== RAW ==========

CREATE TABLE glamira_raw.events (
    event_id        VARCHAR(64) PRIMARY KEY,
    time_stamp      BIGINT,
    collection      VARCHAR(255),
    event_name      VARCHAR(255),
    device_id       VARCHAR(255),
    user_id_db      VARCHAR(255),
    ip              VARCHAR(64),
    country         VARCHAR(255),
    city            VARCHAR(255),
    product_id      VARCHAR(255),
    price           VARCHAR(64),
    currency        VARCHAR(16),
    is_paypal       VARCHAR(64),
    email_address   VARCHAR(512),
    order_id        VARCHAR(255)
);

CREATE TABLE glamira_raw.products (
    product_id      VARCHAR(255) PRIMARY KEY,
    product_name    VARCHAR(1024),
    source_url      VARCHAR(2048),
    status          INTEGER,
    error           VARCHAR(1024),
    updated_at      TIMESTAMPTZ
);

CREATE TABLE glamira_raw.ip_locations (
    ip              VARCHAR(64) PRIMARY KEY,
    country_short   VARCHAR(8),
    country_long    VARCHAR(255),
    region          VARCHAR(255),
    city            VARCHAR(255),
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    timezone        VARCHAR(64),
    updated_at      TIMESTAMPTZ
);

-- ========== STAGING ==========

CREATE TABLE staging.stg_events__checkout_success (
    event_id        VARCHAR(64) PRIMARY KEY
                    REFERENCES glamira_raw.events (event_id),
    event_type      VARCHAR(255),
    time_stamp      BIGINT,
    event_ts        TIMESTAMPTZ,
    event_date      DATE,
    device_id       VARCHAR(255),
    user_id_db      VARCHAR(255),
    ip              VARCHAR(64)
                    REFERENCES glamira_raw.ip_locations (ip),
    order_id        VARCHAR(255),
    product_id      VARCHAR(255)
                    REFERENCES glamira_raw.products (product_id),
    price_raw       NUMERIC(18, 2),
    currency_code   VARCHAR(16),
    is_paypal_raw   VARCHAR(64)
);

CREATE TABLE staging.stg_products (
    product_id          VARCHAR(255) PRIMARY KEY
                        REFERENCES glamira_raw.products (product_id),
    product_name        VARCHAR(1024),
    source_url          VARCHAR(2048),
    crawl_status_code   INTEGER,
    is_crawl_success    BOOLEAN,
    updated_at          TIMESTAMPTZ
);

CREATE TABLE staging.stg_ip_locations (
    ip              VARCHAR(64) PRIMARY KEY
                    REFERENCES glamira_raw.ip_locations (ip),
    country_short   VARCHAR(8),
    country_name    VARCHAR(255),
    region_name     VARCHAR(255),
    city_name       VARCHAR(255),
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    timezone        VARCHAR(64)
);

CREATE TABLE staging.stg_checkout_line_items (
    line_item_id    VARCHAR(128) PRIMARY KEY,
    event_id        VARCHAR(64) NOT NULL
                    REFERENCES staging.stg_events__checkout_success (event_id),
    order_id        VARCHAR(255),
    product_id      VARCHAR(255) NOT NULL
                    REFERENCES staging.stg_products (product_id),
    order_qty       INTEGER,
    line_amount     NUMERIC(18, 2),
    unit_price      NUMERIC(18, 2),
    currency_code   VARCHAR(16),
    line_number     INTEGER
);

-- ========== MART — DIMENSIONS FIRST ==========

CREATE TABLE mart.dim_date (
    date_key            INTEGER PRIMARY KEY,
    full_date           DATE NOT NULL,
    year_number         INTEGER,
    quarter_number      INTEGER,
    month_number        INTEGER,
    month_name          VARCHAR(32),
    is_weekday          BOOLEAN
);

-- Payment: only is_paypal on raw events — kept on fact (no separate dim per review)

CREATE TABLE mart.dim_customer (
    customer_key        BIGSERIAL PRIMARY KEY,
    device_id           VARCHAR(255),
    user_id_db          VARCHAR(255),
    email_address       VARCHAR(512),
    is_identified_user  BOOLEAN
);

CREATE TABLE mart.dim_product (
    product_key         BIGSERIAL PRIMARY KEY,
    product_id          VARCHAR(255) NOT NULL UNIQUE
                        REFERENCES staging.stg_products (product_id),
    product_name        VARCHAR(1024),
    is_crawl_success    BOOLEAN
);

-- dim_location: geographic attributes only — IP stays in staging/events, not in dim
CREATE TABLE mart.dim_location (
    location_key        BIGSERIAL PRIMARY KEY,
    country_short       VARCHAR(8),
    country_name        VARCHAR(255),
    region_name         VARCHAR(255),
    city_name           VARCHAR(255),
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    timezone            VARCHAR(64)
);

-- ========== MART — FACT (center of star) ==========

CREATE TABLE mart.fact_sales_order_detail (
    sales_order_line_key    BIGSERIAL PRIMARY KEY,
    date_key                INTEGER NOT NULL
                            REFERENCES mart.dim_date (date_key),
    customer_key            BIGINT NOT NULL
                            REFERENCES mart.dim_customer (customer_key),
    product_key             BIGINT NOT NULL
                            REFERENCES mart.dim_product (product_key),
    location_key            BIGINT NOT NULL
                            REFERENCES mart.dim_location (location_key),
    is_paypal               VARCHAR(16),
    event_id                VARCHAR(64) NOT NULL
                            REFERENCES staging.stg_events__checkout_success (event_id),
    line_item_id            VARCHAR(128) NOT NULL
                            REFERENCES staging.stg_checkout_line_items (line_item_id),
    order_id                VARCHAR(255),
    order_qty               INTEGER,
    sales_amount            NUMERIC(18, 2),
    unit_price              NUMERIC(18, 2),
    currency_code           VARCHAR(16)
);
