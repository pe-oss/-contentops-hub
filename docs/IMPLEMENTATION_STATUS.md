# ==============================================================================
# Implementation Status - ContentOps Hub
# ==============================================================================

## 1. Trạng thái tổng thể

- **Spec cơ sở:** `docs/Spec-Ban-Content-Marketing-v1.0.md` (Phiên bản v1.0).
- **Mốc xuất phát:** Nhánh `chore/boilerplate-baseline` (commit `4fd4046`).
- **Nhánh hiện tại:** `chore/b00-runtime-config`.

| Giai đoạn / Nhiệm vụ | Trạng thái | Ghi chú |
|---|---|---|
| **B00.1 — Chuẩn hóa môi trường & cấu hình** | **HOÀN TẤT** | Python 3.12, Django 5.2.18, `BILLING_ENABLED=False`, STORAGES, fail-fast production |
| **B00.2 — Chuẩn hóa Email identity & verification** | CHƯA LÀM | Phạm vi lượt tiếp theo |
| **B01 — Kiến trúc Workspace & Phân quyền nghiệp vụ** | CHƯA LÀM | Spec mục 3, 5, 8, 18 |
| **B02 — Quản lý Chiến dịch & Content Calendar** | CHƯA LÀM | Spec mục 6, 9 |
| **B03 — Pipeline Sinh nội dung & AI Gateway (BYOK)** | CHƯA LÀM | Spec mục 10, 11 |
| **B04 — Quality Gate & Duyệt bài (Review/Approval)** | CHƯA LÀM | Spec mục 12, 13 |
| **B05 — Publishing Channel Adapters & Automation** | CHƯA LÀM | Spec mục 14, 15 |
| **B06 — Analytics, Performance Loop & Audit Trail** | CHƯA LÀM | Spec mục 16, 17, 19 |

---

## 2. Chi tiết thực hiện B00.1 (Runtime & Configuration)

### 2.1. Chuẩn hóa Python 3.12 & Django 5.2 LTS
- **Python:** Đã cài đặt và kích hoạt Python 3.12.7 (64-bit). Khởi tạo lại môi trường ảo `.venv` hoàn toàn bằng Python 3.12.
- **Django:** Cập nhật và pin chính xác `Django==5.2.18` (bản vá bảo mật được hỗ trợ dài hạn của nhánh 5.2 LTS).
- **WhiteNoise & Staticfiles:** Chuyển đổi cấu hình từ `STATICFILES_STORAGE` (đã bị loại bỏ trong Django 5.1+) sang dictionary `STORAGES["staticfiles"]` với `whitenoise.storage.CompressedManifestStaticFilesStorage`. Cấu hình `WHITENOISE_MANIFEST_STRICT=False` để tương thích linh hoạt giữa môi trường test và static manifest.
- **Đồng bộ runtime:** Cập nhật `Dockerfile` (`FROM python:3.12-slim`), `render.yaml` (`PYTHON_VERSION: 3.12.7`), `requirements.txt`, `.gitignore` và `README.md`.

### 2.2. Phân tách môi trường & Cơ chế Fail-fast Production
- **Biến `ENVIRONMENT`:** Phân định rõ `local` và `production`.
- **DEBUG:** Local mặc định `True`; Production bắt buộc `False` (nếu cấu hình `DEBUG=True` trên production sẽ từ chối khởi động ngay lập tức).
- **SECRET_KEY:** Local cho phép fallback key dev an toàn; Production từ chối khởi động (`ImproperlyConfigured`) nếu thiếu `SECRET_KEY` hoặc sử dụng key mặc định / key insecure.
- **DATABASE_URL:** Local tự động fallback sang SQLite (`db.sqlite3`); Production bắt buộc phải có chuỗi kết nối PostgreSQL (`postgresql://...`) và từ chối khởi động nếu thiếu hoặc nếu cố tình cấu hình SQLite.
- **Không để file `.env` ghi đè host:** `core/settings.py` sử dụng hàm nạp `.env` an toàn bằng `os.environ.setdefault`, đảm bảo biến môi trường do host/paas cấp phát luôn có độ ưu tiên cao nhất.
- **Bảo mật Cookies:** `SESSION_COOKIE_SECURE=True` và `CSRF_COOKIE_SECURE=True` được kích hoạt tự động trên môi trường production.

### 2.3. Feature Flag `BILLING_ENABLED=False`
- **Mặc định:** `BILLING_ENABLED = False`.
- **Giao diện người dùng:** Ẩn toàn bộ nút bấm / link "Bảng giá", CTA thanh toán và các thành phần gói Pro/bảng lịch sử thanh toán trên thanh Header, Trang chủ (`home.html`) và `Dashboard` (`dashboard.html`).
- **Backend Enforcing:** Chặn cứng ở tầng View và Service:
  - Route `/pricing/` trả về `Http404`.
  - Route tạo đơn `/payments/checkout/<plan_type>/` trả về `Http404`.
  - Route chi tiết checkout `/payments/checkout/<order_id>/` trả về `Http404`.
  - Webhooks `/payments/webhook/payos/` và `/payments/webhook/sepay/` trả về `Http404` và service chặn hoàn toàn xử lý webhook.
  - Ngăn chặn hoàn toàn việc gửi thông báo tới Telegram bot khi billing bị tắt.
- **Bảo toàn dữ liệu:** Models, migrations và cấu trúc bảng `PaymentHistory`, `PaymentOrder` được giữ nguyên vẹn 100%.

### 2.4. Rà soát Build & Release Migration
- **Tách Migration khỏi Build:** Loại bỏ `python manage.py migrate` khỏi `build.sh` (chỉ còn `pip install` và `collectstatic`).
- **Render deployment:** Đưa lệnh migrate vào `preDeployCommand: python manage.py migrate` trong `render.yaml` để chạy độc lập trước khi triển khai release container.
- Cập nhật `.env.example` và `README.md` với tài liệu rõ ràng.

---

## 3. Kết quả Kiểm thử (Validation)

- **Django Check:** `manage.py check` đạt 0 lỗi.
- **Django Migrations:** `manage.py migrate` chạy hoàn tất trên database SQLite local.
- **Bộ kiểm thử tự động (Unit / Integration Tests):** 15 tests trong `core/tests_b00_runtime.py` đều `PASSED (OK)`:
  - 5 tests kiểm tra fail-fast cấu hình production (thiếu secret, secret insecure, debug bật trên prod, thiếu database url, sqlite trên prod).
  - 8 tests kiểm tra `BILLING_ENABLED=False` (chặn 404 cho pricing, checkout, webhooks, ẩn CTA trên landing và dashboard).
  - 1 test kiểm tra quy trình xác thực người dùng: Đăng ký, đăng nhập bằng email hoặc username, đăng xuất, đổi mật khẩu.
  - 1 test kiểm tra khả năng phục vụ static files qua WhiteNoise.
- **Phần chưa kiểm tra thực tế (ghi rõ):**
  - Môi trường máy chưa cài đặt PostgreSQL engine nội bộ nên chưa chạy migration trên database PostgreSQL thực tế tại máy (chỉ đã kiểm thử import và tương thích driver psycopg2-binary).
  - Chưa kết nối hay kiểm thử database PostgreSQL từ xa (tuân thủ nguyên tắc không tự ý kết nối database thật).
