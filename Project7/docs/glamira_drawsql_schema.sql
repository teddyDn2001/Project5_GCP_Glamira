-- Project 07 — Glamira data model for drawSQL import
-- Database dialect: PostgreSQL (drawSQL supports import + live Postgres connection)
-- Usage: drawSQL → New diagram → Import → paste this file OR run on local Postgres then Connect
--
-- BigQuery target: unigap-de-glamira-data.glamira_mart / glamira_staging / glamira_raw

CREATE SCHEMA IF NOT EXISTS glamira_raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS mart;

-- =============================================================================
-- P6 RAW (reference — already exists in BigQuery)
-- =============================================================================

CREATE TABLE glamira_raw.events (
    _id                 JSONB,
    time_stamp          BIGINT,
    collection          VARCHAR(255),
    event_name          VARCHAR(255),
    device_id           VARCHAR(255),
    user_id_db          VARCHAR(255),
    ip                  VARCHAR(64),
    country             VARCHAR(255),
    city                VARCHAR(255),
    product_id          VARCHAR(255),
    price               VARCHAR(64),
    currency            VARCHAR(16),
    is_paypal           VARCHAR(64),
    email_address       VARCHAR(512),
    cart_products       JSONB,
    option              JSONB,
    order_id            VARCHAR(255)
);

CREATE TABLE glamira_raw.products (
    product_id          VARCHAR(255) NOT NULL PRIMARY KEY,
    product_name        VARCHAR(1024),
    source_url          VARCHAR(2048),
    status              INTEGER,
    error               VARCHAR(1024),
    updated_at          TIMESTAMPTZ
);

CREATE TABLE glamira_raw.ip_locations (
    ip                  VARCHAR(64) NOT NULL PRIMARY KEY,
    country_short       VARCHAR(8),
    country_long        VARCHAR(255),
    region              VARCHAR(255),
    city                VARCHAR(255),
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    timezone            VARCHAR(64),
    updated_at          TIMESTAMPTZ
);

-- =============================================================================
-- P7 STAGING (dbt — glamira_staging)
-- =============================================================================

CREATE TABLE staging.stg_events__checkout_success (
    event_id            VARCHAR(64) NOT NULL,
    event_type          VARCHAR(255),
    time_stamp          BIGINT,
    event_ts            TIMESTAMPTZ,
    event_date          DATE,
    device_id           VARCHAR(255),
    user_id_db          VARCHAR(255),
    email_address       VARCHAR(512),
    ip                  VARCHAR(64),
    order_id            VARCHAR(255),
    product_id          VARCHAR(255),
    price_raw           NUMERIC(18, 2),
    currency_code       VARCHAR(16),
    is_paypal_raw       VARCHAR(64),
    country_event       VARCHAR(255),
    city_event          VARCHAR(255),
    cart_products       JSONB,
    option              JSONB,
    is_price_valid      BOOLEAN,
    PRIMARY KEY (event_id)
);

CREATE TABLE staging.stg_checkout_line_items (
    line_item_id        VARCHAR(128) NOT NULL PRIMARY KEY,
    event_id            VARCHAR(64) NOT NULL REFERENCES staging.stg_events__checkout_success (event_id),
    order_id            VARCHAR(255),
    product_id          VARCHAR(255),
    order_qty           INTEGER,
    line_amount         NUMERIC(18, 2),
    unit_price          NUMERIC(18, 2),
    currency_code       VARCHAR(16),
    line_number         INTEGER
);

CREATE TABLE staging.stg_products (
    product_id          VARCHAR(255) NOT NULL PRIMARY KEY,
    product_name        VARCHAR(1024),
    source_url          VARCHAR(2048),
    crawl_status_code   INTEGER,
    crawl_error         VARCHAR(1024),
    is_crawl_success    BOOLEAN,
    updated_at          TIMESTAMPTZ
);

CREATE TABLE staging.stg_ip_locations (
    ip                  VARCHAR(64) NOT NULL PRIMARY KEY,
    country_short       VARCHAR(8),
    country_name        VARCHAR(255),
    region_name         VARCHAR(255),
    city_name           VARCHAR(255),
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    timezone            VARCHAR(64),
    updated_at          TIMESTAMPTZ
);

-- =============================================================================
-- P7 MART — Dimensions (create before fact for FK import order)
-- =============================================================================

CREATE TABLE mart.dim_date (
    date_key            INTEGER NOT NULL PRIMARY KEY,
    full_date           DATE NOT NULL,
    year_number         INTEGER,
    quarter_number      INTEGER,
    month_number        INTEGER,
    month_name          VARCHAR(32),
    week_of_year        INTEGER,
    day_of_month        INTEGER,
    day_of_week         VARCHAR(16),
    day_of_week_number  INTEGER,
    is_weekday          BOOLEAN,
    is_weekend          BOOLEAN
);

CREATE TABLE mart.dim_customer (
    customer_key        BIGSERIAL PRIMARY KEY,
    device_id           VARCHAR(255),
    user_id_db          VARCHAR(255),
    email_hash          VARCHAR(128),
    is_identified_user  BOOLEAN,
    first_seen_date     DATE,
    last_seen_date      DATE
);

CREATE TABLE mart.dim_product (
    product_key         BIGSERIAL PRIMARY KEY,
    product_id          VARCHAR(255) NOT NULL UNIQUE,
    product_name        VARCHAR(1024),
    source_url          VARCHAR(2048),
    crawl_status_code   INTEGER,
    is_crawl_success    BOOLEAN,
    product_updated_at  TIMESTAMPTZ
);

CREATE TABLE mart.dim_geo (
    geo_key             BIGSERIAL PRIMARY KEY,
    ip                  VARCHAR(64),
    ip_hash             VARCHAR(128),
    country_short       VARCHAR(8),
    country_name        VARCHAR(255),
    region_name         VARCHAR(255),
    city_name           VARCHAR(255),
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    timezone            VARCHAR(64),
    geo_source          VARCHAR(64)
);

CREATE TABLE mart.dim_payment_method (
    payment_method_key  SERIAL PRIMARY KEY,
    payment_method_code VARCHAR(32) NOT NULL,
    payment_method_name VARCHAR(64) NOT NULL
);

-- Seed payment methods for diagram clarity
INSERT INTO mart.dim_payment_method (payment_method_code, payment_method_name) VALUES
    ('paypal', 'PayPal'),
    ('other', 'Other'),
    ('unknown', 'Unknown');

-- =============================================================================
-- P7 MART — Transaction fact (star center)
-- =============================================================================

CREATE TABLE mart.fact_sales_order_detail (
    sales_order_line_key    BIGSERIAL PRIMARY KEY,
    date_key                INTEGER NOT NULL REFERENCES mart.dim_date (date_key),
    customer_key            BIGINT NOT NULL REFERENCES mart.dim_customer (customer_key),
    product_key             BIGINT NOT NULL REFERENCES mart.dim_product (product_key),
    geo_key                 BIGINT NOT NULL REFERENCES mart.dim_geo (geo_key),
    payment_method_key      INTEGER NOT NULL REFERENCES mart.dim_payment_method (payment_method_key),
    order_id                VARCHAR(255),
    event_id                VARCHAR(64),
    order_qty               INTEGER,
    sales_amount            NUMERIC(18, 2),
    unit_price              NUMERIC(18, 2),
    currency_code           VARCHAR(16)
);

CREATE INDEX idx_fact_sales_date ON mart.fact_sales_order_detail (date_key);
CREATE INDEX idx_fact_sales_product ON mart.fact_sales_order_detail (product_key);
CREATE INDEX idx_fact_sales_geo ON mart.fact_sales_order_detail (geo_key);

COMMENT ON TABLE mart.fact_sales_order_detail IS
    'Transaction fact — grain: one checkout line item from checkout_success events';

-- =============================================================================
-- Lineage FKs (for drawSQL ERD — logical pipeline links)
-- Re-import glamira_drawsql_schema.sql to refresh connector lines.

-- Raw → Staging
ALTER TABLE staging.stg_products
    ADD CONSTRAINT fk_stg_products__raw
    FOREIGN KEY (product_id) REFERENCES glamira_raw.products (product_id);

ALTER TABLE staging.stg_ip_locations
    ADD CONSTRAINT fk_stg_ip_locations__raw
    FOREIGN KEY (ip) REFERENCES glamira_raw.ip_locations (ip);

-- Staging internal
ALTER TABLE staging.stg_checkout_line_items
    ADD CONSTRAINT fk_line_items__stg_products
    FOREIGN KEY (product_id) REFERENCES staging.stg_products (product_id);

-- Staging → Mart (dbt build path)
ALTER TABLE mart.dim_product
    ADD CONSTRAINT fk_dim_product__stg
    FOREIGN KEY (product_id) REFERENCES staging.stg_products (product_id);

ALTER TABLE mart.dim_geo
    ADD CONSTRAINT fk_dim_geo__stg_ip
    FOREIGN KEY (ip) REFERENCES staging.stg_ip_locations (ip);

ALTER TABLE mart.fact_sales_order_detail
    ADD CONSTRAINT fk_fact__stg_event
    FOREIGN KEY (event_id) REFERENCES staging.stg_events__checkout_success (event_id);

-- glamira_raw.events → stg_events: no PK on raw events — draw this line MANUALLY in drawSQL

