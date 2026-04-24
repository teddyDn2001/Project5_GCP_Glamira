# Project 05 — Day 1–3 Setup Notes (Security-first)

Tài liệu này là “nhật ký có cấu trúc” cho 3 ngày đầu của Project 05. Mục tiêu là để mình đọc lại là nhớ ngay:

- Mình đã **tạo gì** trên GCP (Project / APIs / IAM / GCS / Firewall / VM / Linux users)
- Mình đã **học gì** (concepts + best practices)
- Những lỗi thực tế đã gặp và cách xử lý (resource exhausted, IPv4/IPv6 firewall, IP đổi làm mất SSH…)

> Triết lý xuyên suốt: **Least privilege + Defense in Depth + Auditability**.

---

## TL;DR (nhanh)

- **GCS**
  - Bucket: `gs://unigap-prj5-raw` (region `asia-southeast1`)
  - Public access prevention: **ON**
  - Uniform bucket-level access: **ON**
  - Bucket IAM (final):
    - `user:anhwin01@gmail.com` → `roles/storage.admin`
    - `serviceAccount:sa-p05-vm-ingest@unigap-de-glamira-data.iam.gserviceaccount.com` → `roles/storage.objectAdmin`
- **Compute**
  - VM: `p05-mongo-vm` (zone `asia-southeast1-c`, type `e2-standard-2`, external IP `34.124.185.213`)
  - Firewall SSH whitelist:
    - `p05-allow-ssh-from-home-ipv4` (tcp:22, `YOUR_IPV4/32`)
    - `p05-allow-ssh-from-home-ipv6` (tcp:22, `YOUR_IPV6/128`)
- **SSH hardening trên VM**
  - `PermitRootLogin no`
  - `PasswordAuthentication no`
  - `PubkeyAuthentication yes`
  - 2 user takeover:
    - primary: `doananh`
    - backup: `ssh_backup`

---

## Day 1 — Project + APIs + “identity” (human vs service account)

### Mục tiêu

- Có GCP project “sạch” cho project 05.
- Enable đúng APIs (tối thiểu cần dùng).
- Tách rõ **human access** vs **machine identity** để không bị lẫn quyền và dễ audit.

### Những thứ đã làm

1) **Chọn project**: `unigap-de-glamira-data`

2) **Enable APIs tối thiểu**

- Identity and Access Management (IAM) API
- Cloud Resource Manager API
- Cloud Storage API
- Compute Engine API
- Cloud Logging API

> Lưu ý: không bật nhầm các API “IAM connector …” (không cần cho bài này).

3) **Tạo Service Accounts**

- `sa-p05-vm-ingest@unigap-de-glamira-data.iam.gserviceaccount.com`
  - Dùng cho VM ingest/enrich, đọc/ghi dữ liệu vào GCS theo đúng scope.
- (Tạo sẵn) `sa-p05-bq-loader@...`
  - Dùng cho giai đoạn load vào BigQuery (Day sau).

4) **Chuẩn bị SSH keys (primary/backup) ở local**

- `~/.ssh/p05_primary_ed25519` (+ `.pub`)
- `~/.ssh/p05_backup_ed25519` (+ `.pub`)

### Kiến thức rút ra (Day 1)

- **Least privilege**: account người và account máy phải tách ra để dễ revoke.
- **Không tạo key JSON** cho service account nếu không bắt buộc; ưu tiên gắn SA trực tiếp vào VM.
- **Enable API tối thiểu** giúp giảm bề mặt tấn công và giảm rủi ro bật nhầm dịch vụ.

### Checklist verify (Day 1)

- [ ] Project đúng: `unigap-de-glamira-data`
- [ ] APIs cần thiết đã enable
- [ ] Có `sa-p05-vm-ingest` (và `sa-p05-bq-loader` nếu muốn tạo sẵn)
- [ ] Local có 2 cặp key: primary/backup

---

## Day 2 — GCS bucket + prefix/pattern + IAM “khóa chặt” (audit-friendly)

### Mục tiêu

- Tạo nơi lưu raw data đúng chuẩn doanh nghiệp: **không public**, **ít quyền nhất**, **dễ audit**.
- Tạo prefix naming theo `ingest_date` / `run_date` để version hóa theo lần chạy.

### Những thứ đã tạo

#### 1) Bucket

- Bucket: `gs://unigap-prj5-raw`
- Region: `asia-southeast1`
- Public access prevention: **ON**
- Uniform bucket-level access: **ON**

> GCS “folder” thực chất là **prefix**. Console chỉ hiển thị “folder” khi trong prefix có object.

#### 2) Prefix structure (để audit theo ngày)

Gợi ý prefix dùng trong dự án (audit-friendly):

- `raw/glamira/ingest_date=YYYY-MM-DD/`
- `staging/glamira/run_date=YYYY-MM-DD/`
- `processed/glamira/run_date=YYYY-MM-DD/`
- `exports/ip_locations/run_date=YYYY-MM-DD/`
- `exports/products/run_date=YYYY-MM-DD/`
- `docs/`
- `tmp/`

#### 3) Tạo “folder/prefix” bằng placeholder object (CLI)

Vì GCS là flat namespace, nên mình tạo file `_PLACEHOLDER` (rất nhỏ) để Console hiện prefix.

Ví dụ lệnh đã dùng (Cloud Shell):

```bash
BUCKET="unigap-prj5-raw"
TODAY="$(date +%F)"

for p in \
  "raw/glamira/ingest_date=${TODAY}/" \
  "staging/glamira/run_date=${TODAY}/" \
  "processed/glamira/run_date=${TODAY}/" \
  "exports/ip_locations/run_date=${TODAY}/" \
  "exports/products/run_date=${TODAY}/" \
  "docs/" \
  "tmp/"
do
  printf "." | gcloud storage cp - "gs://${BUCKET}/${p}_PLACEHOLDER"
done
```

#### 4) IAM bucket (final, đúng least privilege)

Sau khi “dọn legacy bindings” để không bị projectViewer/projectOwner đọc tràn, bucket policy cuối cùng:

```bash
gcloud storage buckets get-iam-policy gs://unigap-prj5-raw
```

Kết quả mong đợi (final):

- `user:anhwin01@gmail.com` → `roles/storage.admin`
- `serviceAccount:sa-p05-vm-ingest@unigap-de-glamira-data.iam.gserviceaccount.com` → `roles/storage.objectAdmin`

> Lưu ý: lúc dọn legacy bindings đã có lúc bị “mất getIamPolicy” tạm thời. Cách cứu: tạm cấp `roles/storage.admin` project-level cho user, thêm binding bucket-level, rồi gỡ project-level.

### Kiến thức rút ra (Day 2)

- **Public access prevention + Uniform access** là “khóa” quan trọng nhất.
- **Không dùng** `projectViewer:` / `projectOwner:` binding ở bucket nếu muốn bucket “private-by-design”.
- **Prefix design** = nền tảng audit. Raw nên “immutable”, không overwrite. Rerun thì tăng `run_date` hoặc `run=001/002`.

### Checklist verify (Day 2)

- [ ] Bucket `unigap-prj5-raw` đúng region, PAP ON, Uniform ON
- [ ] Bucket IAM chỉ còn `user:` và `serviceAccount:` cần thiết
- [ ] Prefix theo `ingest_date`/`run_date` đã tạo

---

## Day 3 — Firewall + VM + SSH hardening + 2-user takeover

### Mục tiêu

- Tạo VM để chạy MongoDB + scripts.
- SSH từ local vào VM theo **whitelist IP**.
- Có **2 user takeover** (primary/backup) và SSH hardening chuẩn.

### Những thứ đã tạo

#### 1) Firewall rules (tách IPv4 và IPv6)

GCP **không cho mix IPv4 + IPv6 trong cùng firewall rule**, nên tách 2 rules:

- `p05-allow-ssh-from-home-ipv4` → allow `tcp:22` từ `YOUR_IPV4/32`, tag `p05-ssh`
- `p05-allow-ssh-from-home-ipv6` → allow `tcp:22` từ `YOUR_IPV6/128`, tag `p05-ssh`

Verify:

```bash
gcloud compute firewall-rules list \
  --filter="name~'p05-allow-ssh-from-home-ipv'" \
  --format="table(name,network,direction,allowed,sourceRanges,targetTags)"
```

**Note thực tế**: IP nhà có thể đổi. Nếu đổi IPv4, update rule:

```bash
gcloud compute firewall-rules update p05-allow-ssh-from-home-ipv4 \
  --source-ranges="NEW_IPV4/32"
```

#### 2) VM instance

Tạo VM (do zone A/B hết capacity, cuối cùng tạo ở `asia-southeast1-c`):

- Name: `p05-mongo-vm`
- Zone: `asia-southeast1-c`
- Type: `e2-standard-2`
- Disk: 50GB (cảnh báo I/O < 200GB là warning, không phải lỗi)
- External IP: `34.124.185.213`
- Tag: `p05-ssh`
- Attached service account: `sa-p05-vm-ingest@...`

Verify:

```bash
gcloud compute instances describe p05-mongo-vm \
  --zone asia-southeast1-c \
  --format="yaml(name,zone,status,tags.items,serviceAccounts.email,networkInterfaces[].accessConfigs[].natIP)"
```

#### 3) SSH access từ local + hardening

SSH từ local:

```bash
gcloud compute ssh p05-mongo-vm --zone asia-southeast1-c
```

Hardening SSHD (effective config cuối):

- `permitrootlogin no`
- `passwordauthentication no`
- `pubkeyauthentication yes`

Verify:

```bash
sudo sshd -T | egrep 'permitrootlogin|passwordauthentication|pubkeyauthentication'
```

Để override chắc chắn, dùng file:

`/etc/ssh/sshd_config.d/99-hardening.conf`

#### 4) Two-user takeover (primary + backup)

Tạo/đảm bảo 2 users:

- `doananh` (primary)
- `ssh_backup` (backup)

Cả 2:

- Có `authorized_keys` riêng
- Thuộc group `sudo`
- Test takeover từ local OK

Verify group sudo:

```bash
getent group sudo | tr ',' '\n' | egrep 'doananh|ssh_backup'
```

### Kiến thức rút ra (Day 3)

- **Defense in depth** = GCP firewall whitelist + OS hardening.
- **IP thay đổi** là vấn đề vận hành thực tế khi whitelist theo IP; cần biết cách update firewall nhanh.
- Zone capacity có thể thiếu; cần linh hoạt đổi zone hoặc machine type.
- Không chạy `gcloud compute ssh` “ở trong VM” để quản VM (thiếu scopes, không đúng chỗ).

### Checklist verify (Day 3)

- [ ] Firewall rules ipv4/ipv6 tồn tại, chỉ allow tcp:22, sourceRanges đúng, tag đúng
- [ ] VM `p05-mongo-vm` RUNNING, đúng zone, đúng service account
- [ ] SSHD effective config đúng: root disabled, password disabled, pubkey enabled
- [ ] `doananh` + `ssh_backup` đều SSH được và sudo OK

---

## Kết thúc Day 1–3: trạng thái sẵn sàng cho Day 4

Sau 3 ngày, hạ tầng nền đã sẵn sàng để bắt đầu phần “Data Collection & Storage”:

- Bucket raw đã khóa IAM chuẩn và có prefix audit-friendly.
- VM đã dựng xong, SSH an toàn, có backup user takeover.
- Bước tiếp theo (Day 4) sẽ là: **cài MongoDB (bind localhost + auth)** và bắt đầu ingest raw data.

