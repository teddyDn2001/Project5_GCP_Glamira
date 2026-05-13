# Project 6 — Step-by-step: hiểu bài toán & giải quyết

> Tài liệu này giải thích **vì sao** Project 6 lại được thiết kế như trong `ARCHITECTURE.md`,
> và **làm sao** từ tay không đi đến một pipeline tự động chạy được trên GCP.
> Đọc cùng `ARCHITECTURE.md` (rationale) và `README.md` (commands).

Mục lục:

1. [Hiểu bài toán đang giải](#1-hiểu-bài-toán-đang-giải)
2. [Các khái niệm nền tảng cần nắm](#2-các-khái-niệm-nền-tảng-cần-nắm)
3. [Đi từ requirement → kiến trúc](#3-đi-từ-requirement--kiến-trúc)
4. [Step-by-step giải quyết](#4-step-by-step-giải-quyết)
5. [Kiểm thử & data profiling](#5-kiểm-thử--data-profiling)
6. [Lỗi hay gặp & cách xử lý](#6-lỗi-hay-gặp--cách-xử-lý)
7. [Câu hỏi review/phỏng vấn có thể bị hỏi](#7-câu-hỏi-reviewphỏng-vấn-có-thể-bị-hỏi)

---

## 1. Hiểu bài toán đang giải

### 1.1. Đầu vào (đã có từ Project 5)

- VM `p05-mongo-vm` (GCP, asia-southeast1-c) chạy MongoDB chứa `countly.summary` ~ **41 triệu document** event log của Glamira (view product, add to cart, checkout, …).
- Bucket GCS `gs://unigap-prj5-raw` (lake immutable, region asia-southeast1).
- 2 dataset đã được xử lý ở Project 5 và export ra CSV:
  - `ip_locations` ~3.24M dòng (IP → country/region/city) từ thư viện IP2Location.
  - `products` ~19K dòng (product_id → product_name, crawl từ URL).

### 1.2. Đầu ra Project 6 yêu cầu (deliverables)

1. **Automated data pipeline** — không phải chạy tay, mỗi file mới upload lên GCS thì BigQuery tự load.
2. **Cloud Function trigger** — đây là cái "automatic".
3. **BigQuery raw tables** — 3 bảng, schema rõ ràng.
4. **GitHub repo** — code review-able.

### 1.3. "Raw layer" nghĩa là gì?

Trong kiến trúc lakehouse / Medallion (bronze → silver → gold), **raw layer = bronze**: giữ nguyên bản nhất có thể của dữ liệu nguồn, **chưa transform**. Mục đích:

- Có "single source of truth" để re-build silver/gold khi logic thay đổi.
- Audit: chứng minh được "dữ liệu nguồn đúng là cái này tại thời điểm X".
- Tách biệt extract/load (ngày Project 6) khỏi transform (ngày Project 7 với dbt).

Hệ quả thiết kế: **không clean, không cast, không join** ở Project 6. Chỉ "đưa nguyên" về BigQuery.

### 1.4. Vì sao cần Cloud Function trigger?

Nếu không có trigger, ta phải:
- Chạy tay `bq load …` mỗi lần có file mới → không scale, dễ quên.
- Hoặc dùng cron mỗi giờ scan bucket → trễ + lãng phí (file có khi 1 ngày mới có 1 cái).

**Event-driven** (GCS phát event `object.finalized` → Eventarc nhận → invoke Cloud Function → submit BQ load job): rẻ, nhanh, đúng nguyên tắc serverless. Đây là pattern chuẩn của GCP.

---

## 2. Các khái niệm nền tảng cần nắm

| Khái niệm | Một câu giải thích | Vì sao quan trọng trong Project 6 |
| --- | --- | --- |
| **ETL vs ELT** | ETL transform xong mới load; ELT load thô vào DW rồi transform bằng SQL ngay trong DW | Project 6 đang làm **EL** (extract + load); transform để Project 7 (dbt) làm trong BQ |
| **Data lake** | Nơi lưu file thô, schema-on-read, rẻ | GCS bucket = lake |
| **Data warehouse** | Nơi lưu bảng có schema, query bằng SQL nhanh | BigQuery `glamira_raw` = DW |
| **Object storage event** | Khi file finalize trên GCS, GCS phát ra một event qua Pub/Sub | Đây là tín hiệu để CF khởi động |
| **Eventarc** | Router event của GCP, cho phép map "event type X → invoke service Y" | Eventarc lấy event GCS, gọi CF Gen 2 |
| **Cloud Functions Gen 2** | Lớp serverless kế tiếp, chạy trên Cloud Run, timeout 60', cold start tốt hơn | Chính là cái xử lý load job |
| **BigQuery Load Job** | Cách "ngoài SQL" để đưa file GCS vào BQ table; có job_id riêng | Mỗi event = 1 load job |
| **Idempotent job_id** | `job_id` deterministic ⇒ submit lần 2 sẽ bị "Already Exists" thay vì duplicate | Cứu khi Eventarc retry |
| **Ingestion-time partitioning** | BQ tự partition theo ngày load (`_PARTITIONDATE`) | Không cần derive cột date từ source |
| **Clustering** | Sắp xếp dữ liệu trong partition theo cột → query filter rẻ hơn | `events` cluster theo `event_name`, `product_id` |
| **`WRITE_APPEND` vs `WRITE_TRUNCATE`** | Thêm vào / Ghi đè bảng | Events append (incremental); ip/products truncate (full refresh) |
| **NDJSON (JSONL)** | Mỗi dòng là 1 JSON, không có dấu phẩy ở cuối | BQ load native; giữ được nested fields của Mongo |
| **Resumable upload** | Upload chunk có checkpoint, fail thì resume | Quan trọng cho file 41M docs |
| **Schema autodetect** | BQ tự đoán schema từ file đầu tiên | Ta KHÔNG dùng (kém tin cậy) — dùng explicit JSON schema |
| **Least privilege IAM** | Mỗi identity (user/SA) chỉ có quyền tối thiểu cần | CF chỉ cần `objectViewer` + `bigquery.dataEditor` + `jobUser`, không phải `Editor` |
| **Data profiling** | Khám phá dữ liệu: schema, null %, distinct, dải giá trị | Mục 3 của Project 6 yêu cầu |

---

## 3. Đi từ requirement → kiến trúc

Đây là quá trình suy luận khi tôi đọc đề Project 6 và quyết định thiết kế. Bạn nên hiểu được sequence này để khi sếp/interviewer hỏi "vì sao chọn X" thì trả lời tự tin.

### 3.1. Phân rã requirement

| Yêu cầu spec | Quyết định đầu tiên cần đưa ra |
| --- | --- |
| "Connect to MongoDB" | Dùng `pymongo` với connection string từ `.env` |
| "Extract data in batches" | Mongo cursor `batch_size=2000`, gom 200K docs / shard file |
| "Convert to appropriate format" | NDJSON (lý do ở §3.2) |
| "Upload to GCS" | `google-cloud-storage` resumable upload |
| "Log operations" | `logging` module + file log mỗi script |
| "min 3 files" | 1 file raw (chia shards), 1 file ip_locations, 1 file products |
| "Create BigQuery raw dataset" | `glamira_raw` ở asia-southeast1 |
| "Define table schemas" | JSON schemas explicit trong `schemas/` |
| "Write script to load data from GCS to raw layer" | `scripts/21_load_gcs_to_bq.py` (manual) + Cloud Function |
| "Set up automated triggers using Cloud Functions" | Eventarc Gen 2 trigger trên GCS finalize |
| "Test end-to-end pipeline" | Upload sample, watch logs, query BQ |
| "Data profiling" | `scripts/30_data_profiling.py` sinh Markdown report |

### 3.2. Quyết định khó nhất: chọn format file cho 41M events

Có 3 candidate: **CSV**, **NDJSON (JSONL)**, **Parquet**.

| Tiêu chí | CSV | **NDJSON** | Parquet |
| --- | --- | --- | --- |
| Giữ được nested fields (cart_products là array) | ❌ | ✅ | ✅ (sau khi flatten) |
| BigQuery load native | ✅ | ✅ | ✅ |
| Cần thêm dependency (pyarrow, …) | ❌ | ❌ | ✅ |
| Compression (gzip) | ~5x | ~6x | ~10x |
| Đơn giản cho người mới đọc | ✅ | ✅ | ❌ |
| Phù hợp "raw fidelity" principle | ❌ | ✅ | ⚠️ (đã phải flatten ⇒ không còn raw thuần) |

⇒ **NDJSON + gzip** thắng cho raw events.
IP locations và products đã là flat CSV từ Project 5 ⇒ giữ **CSV + gzip** (consistency với output sẵn có, tiết kiệm code).

### 3.3. Quyết định khó thứ hai: schema strategy

Có 3 cách load NDJSON vào BQ:

1. **Schema autodetect**: BQ tự đoán → tiện nhưng dễ vỡ khi data drift, không reproducible.
2. **Schema all-STRING**: ép tất cả về STRING → an toàn nhất nhưng query phải `SAFE_CAST` lằng nhằng.
3. **Schema explicit + ignore_unknown_values + ALLOW_FIELD_ADDITION**: định nghĩa rõ những cột thường dùng (đã type chuẩn), bỏ qua hoặc auto-add cột mới. ← **Chọn cái này.**

Lợi ích cách 3:
- Cột "thường dùng" (event_name, product_id, ip, time_stamp, …) có type đúng → query rẻ, không phải cast.
- Có cột mới thêm ở Mongo? BQ tự `ALLOW_FIELD_ADDITION` ⇒ không vỡ pipeline.
- Cột giá trị biến hình (như `cart_products`, `option`) → khai báo type `JSON` để giữ nguyên cấu trúc.

### 3.4. Quyết định khó thứ ba: idempotency

Eventarc **có thể retry** một event (network blip, function timeout, …). Nếu CF chạy load job lần 2 với cùng file → **dữ liệu bị duplicate** (vì `WRITE_APPEND`).

Cách giải quyết "đẹp" của GCP:
- BigQuery cho phép set `job_id` tự đặt.
- Submit job với cùng `job_id` lần 2 → BQ **reject** với lỗi `Already Exists` (409).
- ⇒ Ta dùng `job_id = sha1(bucket + name + generation)` (xem `cloud_function/routing.py::deterministic_job_id`).
- CF catch `Conflict` → return success. Eventarc thấy success → stop retry.

Đây là **idempotency pattern chuẩn** mà mọi DE phải biết. Hỏi 10 interview, 7 lần dính.

---

## 4. Step-by-step giải quyết

> Đây là sequence chạy thực tế trên VM hoặc local. Mỗi step có 4 phần: **mục tiêu — lệnh — verify — pitfall**.

### Step 0 — Chuẩn bị env (lần đầu)

**Mục tiêu**: máy chạy được, có credentials đúng.

```bash
# Trên VM p05-mongo-vm (hoặc local sau khi gcloud auth):
git clone https://github.com/teddyDn2001/Project6-Data-Pipeline-Storage.git
cd Project6-Data-Pipeline-Storage

python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
$EDITOR .env       # điền MONGO_ADMIN_PWD, đảm bảo INGEST_DATE đúng
```

**Verify**:
```bash
python3 -c "from dotenv import load_dotenv; load_dotenv(); \
  import os; print('GCP:', os.environ['GCP_PROJECT_ID'])"
# Phải in: GCP: unigap-de-glamira-data
```

**Pitfall**: nếu chạy LOCAL (không trên VM), phải `gcloud auth application-default login` để Python SDK biết identity.

---

### Step 1 — Bật API và cấp IAM (lần đầu trên project)

**Mục tiêu**: cho phép các service nói chuyện với nhau.

```bash
PROJECT=unigap-de-glamira-data

# Bật API cần thiết
gcloud services enable \
  bigquery.googleapis.com \
  cloudfunctions.googleapis.com cloudbuild.googleapis.com \
  eventarc.googleapis.com run.googleapis.com pubsub.googleapis.com \
  artifactregistry.googleapis.com logging.googleapis.com \
  --project="$PROJECT"

# Cấp quyền cho SA loader
SA=sa-p05-bq-loader@${PROJECT}.iam.gserviceaccount.com
gcloud storage buckets add-iam-policy-binding gs://unigap-prj5-raw \
  --member="serviceAccount:${SA}" --role="roles/storage.objectViewer"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA}" --role="roles/bigquery.jobUser"

# Cho Eventarc agent (1 lần)
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
EVENTARC_SA="service-${PROJECT_NUMBER}@gcp-sa-eventarc.iam.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${EVENTARC_SA}" --role="roles/eventarc.eventReceiver"

# Cho GCS publish Pub/Sub event (1 lần)
GCS_SA=$(gsutil kms serviceaccount -p "$PROJECT")
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${GCS_SA}" --role="roles/pubsub.publisher"
```

**Verify**:
```bash
gcloud services list --enabled --project="$PROJECT" | grep -E "eventarc|cloudfunctions|bigquery"
```

**Pitfall**: deploy CF báo "Permission 'eventarc.events.receiveAuditLogWritten' denied" → quên grant `eventReceiver` cho Eventarc agent.

---

### Step 2 — Bootstrap BigQuery dataset & tables

**Mục tiêu**: tạo `glamira_raw` + 3 bảng với schema explicit, partition + cluster.

```bash
python3 scripts/20_create_bq_dataset.py
```

**Verify**:
```bash
bq ls --project_id=$PROJECT glamira_raw
# Phải thấy: events, ip_locations, products
bq show --schema --format=prettyjson $PROJECT:glamira_raw.events | head -30
```

**Pitfall**: chạy lại lần 2 không bị xóa data (idempotent). Nếu muốn xóa hết để làm lại, `bq rm -r -f glamira_raw` (cẩn thận!).

**Vì sao script này quan trọng**: tách tạo bảng ra khỏi load data ⇒ schema review-able trong git, không "chỉ tồn tại trong BQ".

---

### Step 3 — Export raw events 41M dòng từ Mongo lên GCS (heavy step)

**Mục tiêu**: dump `countly.summary` ra NDJSON.gz sharded trên GCS.

```bash
# CHẠY TRONG tmux trên VM — bước này 1-3 tiếng
tmux new -s p06-events
. .venv/bin/activate
set -a && source .env && set +a
python3 scripts/10_export_events_to_gcs.py
# Ctrl-b d  để detach mà không kill
```

**Verify** (mở SSH session khác):
```bash
# Theo dõi log
tail -f logs/export_events_to_gcs_*.log

# Đếm shards đã upload
gcloud storage ls gs://unigap-prj5-raw/raw/p06/events/ingest_date=$(date -u +%F)/ | wc -l
```

**Pitfall**:
- SSH timeout → KHÔNG mất công, chạy lại lệnh y nguyên, script tự skip shards đã có.
- Mongo cursor `CursorNotFound` sau >10 phút idle → giảm `EVENTS_BATCH_SIZE` (200K → 100K) để mỗi shard finalize nhanh hơn.
- Đĩa VM đầy (tmp gzip buffer) → buffer ở đây là **in-memory**, không ghi đĩa, nên thường không bị.

**Tại sao chia shards 200K?** Vì BQ load song song được nhiều file, mỗi file ~200-500 MB là sweet spot. Nếu để 1 file 200GB sẽ load mất hàng giờ + không retry được từng shard.

---

### Step 4 — Đẩy IP locations & products lên Project 6 prefix

**Mục tiêu**: tái sử dụng CSV Project 5, gzip + upload vào prefix `raw/p06/...`.

```bash
python3 scripts/11_export_ip_locations_to_gcs.py
python3 scripts/12_export_products_to_gcs.py
```

**Verify**:
```bash
gcloud storage ls -l gs://unigap-prj5-raw/raw/p06/ip_locations/**
gcloud storage ls -l gs://unigap-prj5-raw/raw/p06/products/**
```

**Pitfall**: script tự refuse overwrite nếu blob đã tồn tại (lake immutable). Muốn upload lại → bump `INGEST_DATE` trong `.env`.

---

### Step 5 — Deploy Cloud Function

**Mục tiêu**: từ giờ trở đi, mọi file mới trong `raw/p06/...` sẽ tự load vào BQ.

```bash
cd cloud_function
set -a && source ../.env && set +a
bash deploy.sh
```

Quá trình deploy:
1. `gcloud functions deploy` zip toàn bộ `cloud_function/` (trừ những gì trong `.gcloudignore`).
2. Cloud Build build image Python 3.11 + cài `requirements.txt`.
3. Cloud Run deploy revision mới.
4. Eventarc tạo subscription Pub/Sub bám vào bucket.

**Verify**:
```bash
gcloud functions describe "$CF_NAME" --gen2 --region="$GCP_REGION" \
    --format="value(state,serviceConfig.uri)"
# state phải là ACTIVE

# Test trigger bằng cách re-upload 1 file nhỏ
INGEST_DATE=$(date -u +%F-smoke) python3 ../scripts/12_export_products_to_gcs.py

# Đợi 10s rồi xem CF có chạy không
sleep 10
gcloud functions logs read "$CF_NAME" --gen2 --region="$GCP_REGION" --limit=20
```

**Pitfall**:
- Deploy lần đầu rất chậm (Cloud Build 3-5 phút) → bình thường.
- "ERROR: gcloud crashed (HttpError)" giữa chừng → retry lệnh deploy, idempotent.
- CF không trigger sau khi upload → kiểm tra `gcloud eventarc triggers list --location=$GCP_REGION` xem trigger tồn tại không.

---

### Step 6 — Load full data (manual lần đầu, sau đó CF tự lo)

Nếu CF deploy XONG MỚI làm Step 3-4 → CF tự load mọi file. Nếu Step 3-4 làm TRƯỚC khi deploy CF → cần chạy manual loader 1 lần để backfill những file đã có:

```bash
python3 scripts/21_load_gcs_to_bq.py --ingest-date $(date -u +%F)
```

**Verify**:
```sql
-- Trong BigQuery Console
SELECT 'events', COUNT(*) FROM `unigap-de-glamira-data.glamira_raw.events`
UNION ALL SELECT 'ip_locations', COUNT(*) FROM `unigap-de-glamira-data.glamira_raw.ip_locations`
UNION ALL SELECT 'products', COUNT(*) FROM `unigap-de-glamira-data.glamira_raw.products`;
```

Expected:
- `events` ~ 40-41M
- `ip_locations` ~ 3.24M
- `products` ~ 19K

---

## 5. Kiểm thử & data profiling

### 5.1. End-to-end test

```bash
# Tạo 1 file giả lập 100 dòng products, upload với INGEST_DATE mới
INGEST_DATE=2026-05-10-test
python3 scripts/12_export_products_to_gcs.py
# Watch logs Cloud Function → phải thấy load job thành công
```

### 5.2. Data profiling

```bash
python3 scripts/30_data_profiling.py
# Sinh: docs/data_profiling_report_<INGEST_DATE>.md
```

Report sẽ bao gồm (đúng theo spec):

- **Schema info**: table names, column names, types, modes.
- **Relationships**: declared logical FKs (`events.product_id → products.product_id`, `events.ip → ip_locations.ip`).
- **Null + distinct counts** mỗi cột (dùng `APPROX_COUNT_DISTINCT` để tiết kiệm slot).
- **Type consistency**: với mỗi cột, đếm số rows có giá trị KHÔNG ép được về type khai báo (`SAFE_CAST`).
- **Per-table KPIs**: count event_names, country distribution, crawl success rate.

### 5.3. Quick checks bằng tay sau profiling

```sql
-- Có bao nhiêu event không khớp IP nào trong ip_locations?
SELECT COUNTIF(l.ip IS NULL) / COUNT(*) AS unmatched_ip_ratio
FROM `unigap-de-glamira-data.glamira_raw.events` e
LEFT JOIN `unigap-de-glamira-data.glamira_raw.ip_locations` l USING (ip);

-- Top 5 event types
SELECT COALESCE(event_name, collection) AS event, COUNT(*) AS n
FROM `unigap-de-glamira-data.glamira_raw.events`
GROUP BY 1 ORDER BY n DESC LIMIT 5;
```

---

## 6. Lỗi hay gặp & cách xử lý

| Lỗi | Triệu chứng | Cách xử lý |
| --- | --- | --- |
| Mongo cursor timeout | `pymongo.errors.CursorNotFound` sau ~10 phút | Đã handle bằng `no_cursor_timeout=True`. Nếu vẫn lỗi, giảm batch hoặc dùng `find().sort('_id').skip().limit()` với resume token. |
| SSH disconnect khi đang export | Terminal mất, script chết | Chạy lại lệnh — script tự skip shard đã upload. Khuyến nghị dùng `tmux`. |
| BQ load fail: "Could not parse … as INT64" | Cột `time_stamp` có vài giá trị string | Schema event đã để `time_stamp` là INTEGER + `ignore_unknown_values=True`. Nếu vẫn lỗi, đổi sang STRING ở schema. |
| CF báo `Already Exists` | Eventarc retry với cùng file | **Bình thường!** Đây là idempotency hoạt động. CF treat thành success. |
| CF báo `Permission denied: bigquery.tables.updateData` | SA loader chưa có `bigquery.dataEditor` ở dataset | `bq add-iam-policy-binding --member=… --role=roles/bigquery.dataEditor PROJECT:glamira_raw` |
| Báo `service-…@gcp-sa-eventarc … not found` | Eventarc agent chưa được auto-create | Bật API Eventarc trước (`gcloud services enable eventarc.googleapis.com`), đợi 2-3 phút, deploy lại CF. |
| Data profiling fail trên `events.cart_products` | JSON type không SAFE_CAST được | Đã handle: script skip JSON/RECORD/STRUCT trong type consistency check. |

---

## 7. Câu hỏi review/phỏng vấn có thể bị hỏi

### Về design

1. **"Tại sao chọn NDJSON mà không Parquet cho 41M events?"**
   → Raw layer cần giữ fidelity tuyệt đối với source. Mongo doc lồng nhau, Parquet phải flatten ⇒ vi phạm "raw faithful to source". Khi sang silver/gold dbt sẽ flatten + materialize Parquet/clustered table. Cost wise Parquet tiết kiệm storage hơn nhưng raw chỉ giữ 30-90 ngày → trade-off chấp nhận được.

2. **"Tại sao Cloud Function chứ không Dataflow / Cloud Composer (Airflow)?"**
   → Use case của ta là **event-driven, single file → single load job**, không có DAG phức tạp. CF rẻ, không cần cluster luôn chạy, scale-to-zero. Composer dùng khi có nhiều bước phụ thuộc nhau. Dataflow dùng khi cần stream transformation hoặc batch >> 1 file.

3. **"Tại sao ingestion-time partitioning chứ không partition theo cột `time_stamp` của event?"**
   → 2 lý do: (a) `time_stamp` của event có thể NULL hoặc out-of-range (epoch 0); partition theo nó dễ vỡ. (b) Raw layer quan tâm "khi nào ta load", không phải "khi nào event xảy ra" — cái đó để silver xử lý. Trade-off: query theo event time sẽ phải scan toàn bảng — chấp nhận được ở raw, dbt sẽ tạo bảng silver partitioned theo event time.

4. **"Pipeline idempotent thế nào?"**
   → 3 layers: 
   - Export: skip shard đã tồn tại trên GCS (theo blob.exists()).
   - Manual loader & CF: deterministic `job_id = sha1(bucket+name+generation)` ⇒ submit lần 2 BQ reject `Conflict` ⇒ no duplicate.
   - GCS lake: immutable, mỗi rerun = `ingest_date` mới.

5. **"Tại sao Cloud Function Gen 2 chứ không Gen 1?"**
   → Gen 2 chạy trên Cloud Run, timeout 60 phút (Gen 1 chỉ 9 phút), cold start nhanh hơn, runtime mới hơn, Eventarc native (Gen 1 là legacy event triggers). Gen 1 đang maintenance mode — GCP đang push Gen 2.

### Về vận hành

6. **"Nếu Mongo có thêm field mới thì sao?"**
   → CF load với `schema_update_options=["ALLOW_FIELD_ADDITION"]` ⇒ BQ tự thêm column NULLABLE. Sau đó ta update `schemas/events.json` để keep explicit schema in sync, commit & PR review.

7. **"Nếu BQ load job fail giữa chừng (file corrupt)?"**
   → CF raise exception → Eventarc retry với backoff (default Pub/Sub retry policy). Sau N lần fail → dead-letter (cần config). Trong Cloud Logging hiện severity=ERROR, ops team alert.

8. **"Làm sao biết pipeline thực sự đang chạy đúng?"**
   → 3 layers:
   - Cloud Logging: lọc `resource.type=cloud_function` + severity ≥ INFO.
   - BigQuery `INFORMATION_SCHEMA.JOBS` để xem rows_loaded, slot_ms.
   - Data profiling report so sánh row counts với source Mongo.

### Về bảo mật / cost

9. **"Cost optimization?"**
   → Bucket + dataset cùng region (asia-southeast1) ⇒ không egress. Gzip giảm ~6x storage. Partition + cluster giảm bytes scanned khi query. Raw layer set lifecycle TTL 90 ngày.

10. **"Bảo mật?"**
    → SA loader chỉ có `objectViewer` + `bigquery.dataEditor` (dataset-level) + `jobUser` (project-level). Không có `Editor`/`Owner`. Không có service account key JSON đẻ thêm — dùng ADC. Bucket có Public Access Prevention ON từ Project 5.

---

## TL;DR sequence để chạy (sau khi đã có Project 5)

```bash
# trên VM, virtualenv đã activate:
python3 scripts/20_create_bq_dataset.py            # 5 giây
python3 scripts/11_export_ip_locations_to_gcs.py   # 1 phút
python3 scripts/12_export_products_to_gcs.py       # 10 giây
cd cloud_function && bash deploy.sh && cd ..       # 5 phút
tmux new -s p06 -d "python3 scripts/10_export_events_to_gcs.py"  # 1-3 giờ
# ... đợi events xong ...
python3 scripts/30_data_profiling.py               # 1 phút
# nộp: docs/data_profiling_report_<date>.md + repo URL
```

Hết. Đọc lại `ARCHITECTURE.md` cho rationale chi tiết, `README.md` cho command reference.
