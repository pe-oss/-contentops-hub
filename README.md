# ContentOps Hub (SaaS Boilerplate)

Boilerplate nền tảng Django phục vụ dự án ContentOps Hub (SaaS-mini-001), tích hợp sẵn xác thực người dùng, bảng điều khiển và kiến trúc phân tách môi trường runtime.

## 1. Yêu cầu hệ thống
- Python 3.12 (khuyến nghị Python 3.12.7+)
- Django 5.2 LTS (pin `Django==5.2.18`)
- Git

## 2. Thiết lập môi trường

### Khởi tạo Virtual Environment
Trên Windows (PowerShell):
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Trên macOS / Linux:
```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### Cài đặt thư viện
```bash
pip install -r requirements.txt
```

## 3. Cấu hình biến môi trường (.env)
Tạo file `.env` từ file mẫu `.env.example`:
```bash
cp .env.example .env
```
- **ENVIRONMENT**: `local` (mặc định) hoặc `production`.
- **DEBUG**: `True` cho local, `False` bắt buộc cho production.
- **BILLING_ENABLED**: Mặc định `False`. Ẩn toàn bộ CTA bảng giá/thanh toán, khóa các route checkout, order, pricing và webhook ở backend.
- **SECRET_KEY**: Local có thể để trống (tự fallback key dev). Production từ chối khởi động nếu thiếu hoặc dùng key mặc định/insecure.
- **DATABASE_URL**: 
  - Local: Để trống để tự động fallback sang SQLite (`db.sqlite3`).
  - Production: Bắt buộc cấu hình chuỗi kết nối PostgreSQL (`postgresql://...`). Production sẽ từ chối khởi động (fail-fast) nếu thiếu hoặc nếu dùng SQLite.

## 4. Chạy Migration & Kiểm tra Local
```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py migrate
```

## 5. Khởi động ứng dụng Local
```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```
Truy cập ứng dụng tại: `http://127.0.0.1:8000/`

## 6. Quy trình Build & Triển khai (Deploy)
Chi tiết xem tại tài liệu hướng dẫn triển khai: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

- **Kiến trúc:** WSGI qua Gunicorn, Static files qua WhiteNoise (`CompressedManifestStaticFilesStorage`), Cơ sở dữ liệu PostgreSQL bắt buộc trong production qua `DATABASE_URL`.
- **Bước Build (`build.sh`):** Cài đặt dependencies, thu thập static files và kiểm tra tính toàn vẹn hệ thống (`fail-fast` với `set -euo pipefail`):
  ```bash
  python -m pip install -r requirements.txt
  python manage.py collectstatic --noinput
  python manage.py check
  ```
- **Bước Release Migration:** Quá trình migration CSDL được tách riêng khỏi bước build để tránh xung đột khi scale nhiều web worker và đảm bảo kiểm soát rollback.
  - Trên Render: Cấu hình `preDeployCommand: python manage.py migrate` trong `render.yaml`.
  - Trên Docker/Kubernetes: Chạy migration qua one-off job hoặc entrypoint script có kiểm soát trước khi scale web replicas.
  - **Lưu ý an toàn:** Không tự động chạy migration vào cơ sở dữ liệu production từ xa mà không có kế hoạch sao lưu.
- **Bước Khởi động (Start):**
  ```bash
  gunicorn core.wsgi:application --bind 0.0.0.0:8000
  ```
- **Smoke Test & Kiểm tra bảo mật:**
  ```bash
  python manage.py check --deploy
  ```
- **Kế hoạch Rollback:** Xem chi tiết tại mục 5 của [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## 7. Trạng thái và giới hạn kiểm thử (B00.1)
- **Đã kiểm thử đạt:**
  - Python 3.12 runtime và Django 5.2.18 LTS tương thích hoàn toàn.
  - Phân tách cấu hình Local vs Production: Production fail-fast khi thiếu `SECRET_KEY` hoặc `DATABASE_URL`, hoặc khi cấu hình SQLite cho production.
  - `BILLING_ENABLED=False`: Ẩn bảng giá trên header, trang chủ và dashboard; backend trả về 404 cho `/pricing/`, `/payments/checkout/...`, và webhooks; ngăn chặn gọi Telegram/thanh toán.
  - Staticfiles với `STORAGES` và WhiteNoise hoạt động bình thường kể cả khi `DEBUG=False`.
  - Luồng auth: Đăng ký, đăng nhập (email/username), đăng xuất, đổi mật khẩu hoạt động ổn định.
- **Giới hạn hiện tại (chưa thực hiện trong B00.1):**
  - Môi trường máy chưa có dịch vụ PostgreSQL local nên chưa chạy migration trên database PostgreSQL thực tế tại máy (đã kiểm thử psycopg2 driver import thành công).
  - Chưa triển khai Email identity / verification (nhiệm vụ B00.2).
  - Chưa triển khai Workspace, phân quyền nghiệp vụ và các chức năng content (B01 trở đi).

