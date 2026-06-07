# Looker Studio — Sale Performance Dashboard (Glamira P7)

Mẫu thầy: **Sale Performance Dashboard** (1 report tổng hợp).  
Nguồn: `unigap-de-glamira-data.glamira_mart.vw_sales_performance` (view denormalized từ star schema).

---

## 0. Deploy view lên BigQuery (Cloud Shell)

```bash
# Copy file từ Mac hoặc paste nội dung models/mart/looker/vw_sales_performance.sql
cd ~/glamira_dbt
dbt run --select vw_sales_performance

bq query --use_legacy_sql=false --location=asia-southeast1 \
'SELECT COUNT(*) n FROM `unigap-de-glamira-data.glamira_mart.vw_sales_performance`'
# Kỳ vọng: n ≈ 29065
```

---

## 1. Tạo report

1. Mở [Looker Studio](https://lookerstudio.google.com)
2. **Create** → **Report**
3. Add data → **BigQuery** → authorize GCP
4. Project: `unigap-de-glamira-data` → Dataset: `glamira_mart` → Table: **`vw_sales_performance`**
5. **Add to report**

---

## 2. Chuẩn hóa field types (Resource panel → Manage added data sources → Edit)

| Field | Type |
|-------|------|
| `full_date` | Date (YYYY-MM-DD) |
| `sales_amount` | Number |
| `order_qty` | Number |
| `order_id` | Text |
| `country_name` | Geo → Country |
| `product_name`, `metal_type`, `stone_type` | Text |

---

## 3. Calculated fields (Add a field)

| Tên | Formula | Dùng cho |
|-----|---------|----------|
| `Daily Avg Revenue` | `SUM(sales_amount) / COUNT_DISTINCT(full_date)` | Scorecard |
| `Daily Avg Quantity` | `SUM(order_qty) / COUNT_DISTINCT(full_date)` | Scorecard |
| `Order Count` | `COUNT_DISTINCT(order_id)` | Line chart orders |

*Trong scorecard: chọn metric → Aggregation **SUM** hoặc dùng calculated field ở trên.*

---

## 4. Layout — map từng chart (giống mẫu thầy)

### Hàng 1 — Scorecards (4 ô)

| Widget | Metric | Aggregation |
|--------|--------|-------------|
| Total Revenue | `sales_amount` | SUM |
| Daily Avg Revenue | `Daily Avg Revenue` | (calculated) |
| Total Quantity | `order_qty` | SUM |
| Daily Avg Quantity | `Daily Avg Quantity` | (calculated) |

Style: dark theme (Theme → Dark), số format **Compact** (2.94M).

### Hàng 2 — Time series

| Chart | Dimension | Metric |
|-------|-----------|--------|
| **Revenue Over Time** | `full_date` (Day) | `sales_amount` SUM |
| **Number of Orders Over Time** | `full_date` (Day) | `Order Count` |

Chart type: **Time series** (line).

### Hàng 3 — Product breakdown

| Chart | Dimension | Metric | Sort |
|-------|-----------|--------|------|
| **Top 5 Revenue By Stone** | `stone_type` | `sales_amount` SUM | Desc, limit 5 |
| **Top 5 Product By Revenue** | `product_name` | `sales_amount` SUM | Desc, limit 5 |
| **Revenue By Metal Type** | `metal_type` | `sales_amount` SUM | Pie chart |

### Hàng 4 — Geo

| Chart | Setup |
|-------|--------|
| **Revenue By Country** | Geo chart → Dimension `country_name`, Metric `sales_amount` SUM, show bubble/color |

### Sidebar — Filters (Control)

| Control | Field |
|---------|-------|
| Country filter | `country_name` (Drop-down list, multi-select) |
| Date filter | `full_date` (Date range control) |

Đặt 2 control bên trái như mẫu thầy.

---

## 5. Title & footer

- Title: **SALE PERFORMANCE DASHBOARD** (text box, center top)
- Footer: **Data Last Updated** → Insert → **BigQuery parameter** hoặc text + ngày build mart

Optional: thêm `is_paypal` filter (PayPal vs Other) thay cho payment dim đã gộp vào fact.

---

## 6. PII (bắt buộc theo review)

- Dashboard **chỉ** dùng `vw_sales_performance` — **không** join `dim_customer` / `email_address`.
- Nếu cần metric customer: tạo view riêng với `TO_HEX(SHA256(email_address)) AS email_hash` — không expose raw email.

---

## 7. 4 dashboard theo đề (có thể tách hoặc dùng 1 report như thầy)

| Đề bài | Charts lấy từ dashboard trên |
|--------|------------------------------|
| Revenue analysis | Scorecards + Revenue Over Time + `is_paypal` breakdown |
| Geographic distribution | Map + country filter |
| Time-based trends | 2 line charts (revenue + orders) |
| Product performance | Top products + stone + metal |

**Nộp bài:** 1 report như mẫu thầy là đủ; hoặc duplicate report → 4 tab.

---

## 8. Checklist trước khi screenshot nộp

- [ ] Total Revenue ≈ **2.94M** (khớp `SUM(sales_amount)` trên fact)
- [ ] Map có heat Europe (Glamira traffic)
- [ ] Date filter hoạt động
- [ ] Không có cột email / ip raw trên data source

---

## 9. Troubleshooting

| Vấn đề | Cách xử lý |
|--------|------------|
| Không thấy BQ dataset | IAM: account cần `bigquery.dataViewer` trên `glamira_mart` |
| `country_name` map lỗi | Set field type **Geo → Country** |
| Stone/Metal toàn "Not Defined" | Tên SP không chứa keyword — chỉnh regex trong `vw_sales_performance.sql` |
| Số khác 2.94M | Check date filter default range |
