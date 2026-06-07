# drawSQL — Glamira Project 7 data model

**File import (FK inline — drawSQL vẽ line):** [`glamira_drawsql_erd.sql`](glamira_drawsql_erd.sql)

File cũ (FK cuối file, thường **không** vẽ line): [`glamira_drawsql_schema.sql`](glamira_drawsql_schema.sql)

---

## Cách 1 — Import SQL (khuyên dùng)

1. Vào https://drawsql.app
2. **New diagram** → tên `Glamira P7`
3. **Import → From SQL → PostgreSQL**
4. Copy **toàn bộ** `glamira_drawsql_erd.sql` → Paste → Import
5. Bật **Show relationships** / zoom out — line có thể nằm ngoài màn hình
6. Sắp layout → **Export PNG**

**Quan trọng:** Diagram **mới**, import **một lần** — tránh duplicate `events`, `products` như ảnh cũ.

---

## Vẫn không có line?

### A. Re-import đúng file

Dùng `glamira_drawsql_erd.sql` (không phải `glamira_drawsql_schema.sql`).

### B. Nối tay trong drawSQL

Click **Add relationship** (icon/link) → kéo từ cột PK sang cột FK:

| Từ (PK) | Sang (FK) |
|---------|-----------|
| `events.event_id` | `stg_events__checkout_success.event_id` |
| `products.product_id` | `stg_products.product_id` |
| `ip_locations.ip` | `stg_ip_locations.ip` |
| `stg_events.event_id` | `stg_checkout_line_items.event_id` |
| `stg_products.product_id` | `stg_checkout_line_items.product_id` |
| `stg_products.product_id` | `dim_product.product_id` |
| `stg_ip_locations.ip` | `dim_geo.ip` |
| `dim_date.date_key` | `fact_sales_order_detail.date_key` |
| `dim_customer.customer_key` | `fact.customer_key` |
| `dim_product.product_key` | `fact.product_key` |
| `dim_geo.geo_key` | `fact.geo_key` |
| `dim_payment_method.payment_method_key` | `fact.payment_method_key` |
| `stg_events.event_id` | `fact.event_id` |
| `stg_checkout_line_items.line_item_id` | `fact.line_item_id` |

### C. Xóa bảng trùng

Nếu thấy **2 bảng `events`** hoặc **2 `products`**: xóa duplicate → import lại diagram mới.

---

## Luồng sau khi nối đủ

```text
events ──► stg_events ──► stg_line_items ──► fact ◄── dim_*
products ──► stg_products ──► dim_product ────────┘
ip_locations ──► stg_ip_locations ──► dim_geo ────┘
```

---

## Cách 2 — Postgres + Connect (tuỳ chọn)

```bash
docker run -d --name glamira-p7-pg \
  -e POSTGRES_PASSWORD=drawsql -e POSTGRES_DB=glamira_p7 -p 5432:5432 postgres:16
docker exec -i glamira-p7-pg psql -U postgres -d glamira_p7 < glamira_drawsql_erd.sql
```

drawSQL → Connect PostgreSQL → reverse engineer.

---

## Liên quan

- Cột chi tiết: [`DATA_MODEL.md`](DATA_MODEL.md)
- dbdiagram: [`glamira_mart.dbml`](glamira_mart.dbml)
