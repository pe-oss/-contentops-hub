# ContentOps Hub - Hướng Dẫn Đóng Gói và Triển Khai (Deployment Guide)

Tài liệu này quy định kiến trúc runtime, quy trình đóng gói, các biến môi trường, chu trình phát hành (Build / Migrate / Start), quy trình Smoke Test và phương án Rollback cho **ContentOps Hub**.

---

## 1. Kiến Trúc Runtime & Công Nghệ Đóng Gói

- **Framework**: Django 5.2 LTS (`Django==5.2.18`), Python 3.12 (khuyến nghị 3.12.7+).
- **WSGI Application Server**: `gunicorn` (phiên bản `23.0.0`), chạy ứng dụng qua `core.wsgi:application`.
- **Static Assets Serving**: `whitenoise` (phiên bản `6.7.0`) kết hợp với Django `STORAGES`:
  - `STATIC_ROOT`: Thư mục tập hợp file tĩnh `staticfiles/`.
  - Storage backend: `whitenoise.storage.CompressedManifestStaticFilesStorage`.
  - Tự động nén gzip/brotli và gắn hash mã hóa tên file nhằm tối ưu cache HTTP lâu dài.
- **Cơ sở dữ liệu**:
  - **Local Development**: Mặc định SQLite (`db.sqlite3`) nếu không cấu hình `DATABASE_URL`.
  - **Production / Staging**: **BẮT BUỘC** sử dụng **PostgreSQL** (`psycopg2-binary==2.9.9` qua `dj-database-url`). Hệ thống áp dụng cơ chế fail-fast: từ chối khởi động ngay lập tức nếu thiếu `DATABASE_URL` hoặc nếu cấu hình SQLite trong môi trường production (`ENVIRONMENT=production`).
- **Feature Flags**:
  - `BILLING_ENABLED=False`: Tiếp tục giữ cờ tắt toàn bộ tính năng thương mại/thanh toán ở giai đoạn MVP/R1, trả về 404 cho các endpoint pricing/checkout/webhook và ẩn toàn bộ CTA thanh toán.

---

## 2. Bảng Danh Mục Biến Môi Trường (Environment Variables)

| Tên biến | Bắt buộc (Production) | Kiểu dữ liệu / Giá trị mẫu | Mô tả & Lưu ý an toàn |
|---|---|---|---|
| `ENVIRONMENT` | Có | `production` (Local: `local`) | Định danh môi trường chạy. Khi là `production`, kích hoạt các chốt kiểm tra bảo mật nghiêm ngặt. |
| `DEBUG` | Có | `False` (Local: `True`) | Tuyệt đối là `False` ở production. Nếu bật `True` ở production, hệ thống sẽ chặn khởi động (`ImproperlyConfigured`). |
| `SECRET_KEY` | Có | Chuỗi ngẫu nhiên >= 50 ký tự | Khóa mã hóa bảo mật của Django. Production từ chối khởi động nếu rỗng, ngắn hơn 50 ký tự, hoặc chứa tiền tố `django-insecure-`. |
| `ALLOWED_HOSTS` | Có | `app.domain.com,.onrender.com` | Danh sách hostname hợp lệ phân tách bằng dấu phẩy. Không được để trống ở production. |
| `DATABASE_URL` | Có | `postgresql://user:pass@host:5432/dbname` | Chuỗi kết nối PostgreSQL. Production chỉ chấp nhận engine PostgreSQL (`django.db.backends.postgresql`). |
| `CSRF_TRUSTED_ORIGINS` | Có (khi chạy HTTPS) | `https://app.domain.com,https://hub.onrender.com` | Nguồn gốc tin cậy cho CSRF protection khi triển khai sau reverse proxy/HTTPS. |
| `BILLING_ENABLED` | Không | `False` (mặc định) | Cờ tính năng thanh toán. Luôn giữ `False` ở phiên bản hiện tại. |
| `SESSION_COOKIE_SECURE` | Không | `True` (mặc định ở prod) | Bắt buộc truyền cookie session qua kênh bảo mật HTTPS. |
| `CSRF_COOKIE_SECURE` | Không | `True` (mặc định ở prod) | Bắt buộc truyền cookie CSRF qua kênh bảo mật HTTPS. |
| `SECURE_SSL_REDIRECT` | Không | `False` (mặc định) / `True` | Bật nếu muốn Django tự chuyển hướng HTTP sang HTTPS (nếu reverse proxy chưa xử lý). |
| `SECURE_HSTS_SECONDS` | Không | `0` (mặc định) / `31536000` | Thiết lập tiêu đề HSTS (HTTP Strict Transport Security) cho trình duyệt. |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | Không | `False` (mặc định) / `True` | Áp dụng HSTS cho toàn bộ subdomain. |
| `SECURE_HSTS_PRELOAD` | Không | `False` (mặc định) / `True` | Cho phép đăng ký tên miền vào HSTS Preload list của trình duyệt. |
| `WHITENOISE_MANIFEST_STRICT` | Không | `False` (mặc định) | Nếu `True`, WhiteNoise sẽ báo lỗi khi thiếu static file trong manifest thay vì fallback file gốc. |


---

## 3. Vòng Đời Triển Khai (Build, Migrate, Start)

Hệ thống tuân thủ nguyên tắc **Separation of Concerns**: tách biệt hoàn toàn giữa quá trình đóng gói tĩnh (Build), nâng cấp cấu trúc dữ liệu (Migrate), và chạy dịch vụ web (Start).

### Bước 1: Build Phase (`build.sh`)
- Tập lệnh: `build.sh` (định dạng UTF-8, LF, thực thi với `set -euo pipefail`).
- Nội dung thực thi:
  ```bash
  python -m pip install -r requirements.txt
  python manage.py collectstatic --noinput
  python manage.py check
  ```
- Không chứa lệnh `migrate` trong bước này để ngăn chặn việc chạy lặp lại hoặc lỗi trên môi trường CI build.

### Bước 2: Release / Migrate Phase (Thực hiện duy nhất 1 lần cho mỗi đợt release)
- **Trên Render**: Tự động hóa qua cấu hình `preDeployCommand` trong `render.yaml`:
  ```yaml
  preDeployCommand: python manage.py migrate
  ```
- **Trên Docker / Containerized Environment**:
  ```bash
  docker run --rm --env-file .env.production <image_tag> python manage.py migrate
  ```

### Bước 3: Start Phase (Chạy Web Server)
- Khởi động WSGI server bằng `gunicorn`:
  ```bash
  gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
  ```

---

## 4. Kiểm Thử Khởi Động & Xác Minh Vận Hành (Smoke Test)

Sau khi hoàn tất triển khai hoặc trong môi trường Staging/Linux, thực hiện các bước kiểm tra thực tế:

### 4.1. Kiểm tra cấu hình bảo mật Django
```bash
python manage.py check --deploy
```

### 4.2. Kiểm tra phục vụ Static Files qua WhiteNoise
- Truy cập file static ứng dụng: `GET /static/css/style.css` (hoặc hashed static path).
  - Kết quả mong muốn: HTTP 200 OK, header `Cache-Control: max-age=31536000, public, immutable`.
- Truy cập static Django Admin: `GET /static/admin/css/base.css`.
  - Kết quả mong muốn: HTTP 200 OK.

### 4.3. Kiểm tra Luồng Xác Thực (Auth Smoke Test)
1. Đăng ký tài khoản: `POST /accounts/register/` -> Tạo thành công, điều hướng đăng nhập.
2. Đăng nhập: `POST /accounts/login/` -> Nhận session cookie có thuộc tính `HttpOnly` và `Secure`.
3. Đăng xuất: `POST /accounts/logout/` -> Xóa session cookie, điều hướng về trang chủ.

### 4.4. Kiểm tra Đọc / Ghi Dữ liệu Nghiệp Vụ (Data R/W Smoke Test)
1. Tạo Workspace mới: `POST /workspaces/create/` -> Workspace được tạo, cấp quyền OWNER.
2. Tạo Gói nội dung (Package) & Thêm bài viết (Content Item): Kiểm tra ghi bản ghi và sinh phiên bản nội dung v1.
3. Chuyển trạng thái nội dung (Workflow transition): Kiểm tra ghi nhận lịch sử và bảo vệ kiểm soát đồng thời (OCC `row_version`).

---

## 5. Quy Trình Rollback Khi Gặp Sự Cố

### 5.1. Rollback Phiên Bản Mã Nguồn (Code Rollback)
- **Trên Render**: Vào thẻ **Deploys** -> Chọn bản deploy ổn định gần nhất -> Bấm **Rollback to this deploy**.
- **Trên Container / Git**:
  - Kéo và khởi động lại container image của bản phát hành trước:
    ```bash
    docker stop <container_id>
    docker run -d --name contentops-web --env-file .env.production <previous_image_tag>
    ```

### 5.2. Rollback Cơ Sở Dữ Liệu (Database Rollback)
1. **Sao lưu trước khi nâng cấp (Pre-release Backup)**:
   - Sử dụng lệnh sao lưu có kiểm chứng mã băm SHA256:
     ```bash
     python manage.py backup_database --target-dir backups/
     ```
   - Hoặc công cụ PostgreSQL native:
     ```bash
     pg_dump -Fc $DATABASE_URL -f pre_release_backup.dump
     ```
2. **Hạ cấp migration (Reverse Migration)**:
   - Nếu lỗi do migration mới nhất, rollback ngược về migration ổn định trước đó:
     ```bash
     python manage.py migrate <app_label> <previous_migration_name>
     ```
3. **Khôi phục toàn phần từ bản sao lưu (Restore Drill)**:
   - Sử dụng lệnh phục hồi hệ thống:
     ```bash
     python manage.py restore_database backups/backup_manifest.json
     ```
   - Hoặc với `pg_restore`:
     ```bash
     pg_restore --clean --if-exists -d $DATABASE_URL pre_release_backup.dump
     ```

---

## 6. Phân Tích Cảnh Báo Django `check --deploy` và Chốt Gate PostgreSQL

### 6.1. Gate PostgreSQL
- **Cơ chế**: Hệ thống kiểm tra trực tiếp thuộc tính `DATABASES["default"]["ENGINE"]`.
- **Kết quả**:
  - Nếu `DATABASE_URL` rỗng -> Lỗi `ImproperlyConfigured`.
  - Nếu `DATABASE_URL` trỏ tới `sqlite` -> Lỗi `ImproperlyConfigured`.
  - Nếu `DATABASE_URL` trỏ tới hệ quản trị khác không phải PostgreSQL -> Lỗi `ImproperlyConfigured`.
  - Chỉ khi sử dụng PostgreSQL (`django.db.backends.postgresql`), cấu hình mới được phê duyệt hợp lệ.

### 6.2. Phân tích Cảnh Báo (Warnings)
1. **`security.W004` (SECURE_HSTS_SECONDS)**:
   - *Nguyên nhân*: Django chưa bật tiêu đề HTTP Strict Transport Security.
   - *Xử lý*: Có thể thiết lập qua biến môi trường `SECURE_HSTS_SECONDS=31536000`. Khi hạ tầng (Render/Cloudflare) đã gán HSTS ở Edge/Load Balancer, cảnh báo này là an toàn và có thể giữ mặc định 0.
2. **`security.W008` (SECURE_SSL_REDIRECT)**:
   - *Nguyên nhân*: Django chưa bật tự động chuyển hướng HTTP sang HTTPS trong code.
   - *Xử lý*: Trên Render, SSL Termination và Force HTTPS được xử lý tại Reverse Proxy/Load Balancer. Cấu hình `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` đã thiết lập sẵn. Nếu muốn Django tự chuyển hướng, cấu hình `SECURE_SSL_REDIRECT=True`.

---

## 7. Cấu Hình Môi Trường Staging Trên Render (Staging Specification)

### 7.1. Thông Tin Dịch Vụ & Hạ Tầng
- **Dịch vụ Web**:
  - Tên Service: `contentops-staging`
  - Loại dịch vụ: Render Web Service (Native Python runtime)
  - Plan: Free
  - Repository: `https://github.com/pe-oss/-contentops-hub`
  - Branch: `deploy/staging`
  - Commit baseline: `190d0cf` (kế thừa `c7ee50d` và `71b797e`)
  - Python Version: `3.12.7` (được pin qua `.python-version` và `PYTHON_VERSION=3.12.7`)
  - Root Directory: `/` (gốc repo chứa `manage.py` và `build.sh`)
  - Build Command: `bash build.sh`
  - Start Command: `python manage.py migrate --noinput && python -m gunicorn core.wsgi:application --bind 0.0.0.0:$PORT --workers 2` (hoặc `bash start.sh`)
  - Auto-Deploy: Tắt (Manual deploy để kiểm soát phát hành)
- **Cơ Sở Dữ Liệu Staging**:
  - Tên Database: `contentops-staging-db`
  - Loại dịch vụ: Render PostgreSQL
  - Plan: Free (Lưu ý: Render Free PostgreSQL tự động hết hạn sau 30 ngày hoặc theo chính sách của Render, chỉ dùng cho mục đích staging/thử nghiệm, KHÔNG bảo đảm lưu trữ dài hạn và KHÔNG thay thế CSDL Production)
  - Region: Khuyến nghị Singapore (`singapore`) hoặc Oregon (`oregon`) - **Bắt buộc cùng Region với Web Service**.
  - Kết nối: Sử dụng **Internal Database URL** được truyền trực tiếp vào biến môi trường `DATABASE_URL` của Web Service. Không mở public access rộng hơn nhu cầu.

### 7.2. Danh Mục Biến Môi Trường Staging Cần Thiết
*(Tuyệt đối không lưu giá trị bí mật vào kho mã nguồn)*
- `ENVIRONMENT`: `production` (kích hoạt chế độ kiểm soát chặt chẽ)
- `DEBUG`: `False` (bắt buộc)
- `PYTHON_VERSION`: `3.12.7`
- `DATABASE_URL`: `<Internal Database URL>` (cung cấp từ `contentops-staging-db`)
- `SECRET_KEY`: `<Secret key ngẫu nhiên >= 50 ký tự được sinh an toàn>`
- `ALLOWED_HOSTS`: `<subdomain>.onrender.com` (tên miền thực tế do Render cấp, không chứa `https://`)
- `CSRF_TRUSTED_ORIGINS`: `https://<subdomain>.onrender.com`
- `BILLING_ENABLED`: `False`
- `SESSION_COOKIE_SECURE`: `True`
- `CSRF_COOKIE_SECURE`: `True`
- `SECURE_SSL_REDIRECT`: `False` (Render Edge xử lý TLS Termination, Django nhận diện HTTPS qua `SECURE_PROXY_SSL_HEADER`)
- `SECURE_HSTS_SECONDS`: `0` (giữ 0 ở giai đoạn staging ban đầu)

### 7.3. Trạng Thái Các Gate Vận Hành & Hạn Chế Còn Thiếu
- [x] **PostgreSQL Integration**: Đã kiểm chứng migrate và ORM trên PostgreSQL 16.
- [x] **Static Assets Serving**: WhiteNoise phục vụ đầy đủ cache và nén cho app + Django admin.
- [x] **Concurrency & OCC**: Đã kiểm chứng Row Locking và ConcurrencyConflictError 409 trên PostgreSQL.
- [ ] **Email / SMTP Service**: Staging hiện dùng Console Backend (`EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"`). Tính năng xác minh email ngoài đời thực chưa gửi được email đến hòm thư thật. **Chưa đủ điều kiện nhận người dùng thật**.
- [ ] **Automated Daily Backup**: Gói PostgreSQL Free trên Render không hỗ trợ snapshot tự động lâu dài; chưa đánh dấu đạt Gate backup định kỳ cho đến khi thiết lập cron job / pg_dump ngoài và kiểm chứng khôi phục thực tế.

