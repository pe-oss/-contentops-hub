# ==============================================================================
# Implementation Status - ContentOps Hub
# ==============================================================================

## 1. Trạng thái tổng thể

- **Spec cơ sở:** `docs/Spec-Ban-Content-Marketing-v1.0.md` (Phiên bản v1.0).
- **Mốc xuất phát:** Nhánh `chore/boilerplate-baseline` (commit `4fd4046`).
- **Nhánh hiện tại:** `feat/b00-email-identity` (tiếp nối commit `10104d7`).

| Giai đoạn / Nhiệm vụ | Trạng thái | Ghi chú |
|---|---|---|
| **B00.1 — Chuẩn hóa môi trường & cấu hình** | **HOÀN TẤT** | Python 3.12, Django 5.2.18, `BILLING_ENABLED=False`, STORAGES, fail-fast production |
| **B00.2 — Chuẩn hóa Email identity & verification** | **HOÀN TẤT** | AccountEmailIdentity unique, chặn login mơ hồ, token verification, rate limit, migration backfill an toàn |
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

## 3. Chi tiết thực hiện B00.2 (Email Identity & Verification)

### 3.1. Model `AccountEmailIdentity` & Database Constraints
- Tạo model `AccountEmailIdentity` quan hệ OneToOne với `User` (`related_name="email_identity"`).
- `normalized_email`: `EmailField(unique=True, db_index=True)` chuẩn hóa chữ thường và loại bỏ khoảng trắng thừa, đảm bảo ràng buộc unique thực sự ở mức Database thay vì chỉ ở form.
- `verified_at`: `DateTimeField(null=True, blank=True)` lưu mốc thời gian xác minh. Thuộc tính `is_verified` trả về `True` nếu đã xác minh.
- `last_verification_sent_at`: `DateTimeField` hỗ trợ kiểm soát rate-limiting.

### 3.2. Data Migration An toàn (Spec 17.4)
- Migration `0001_initial.py`: Khởi tạo bảng `accounts_accountemailidentity`.
- Migration `0002_backfill_email_identities.py`: Backfill dữ liệu từ `User.email`:
  - Quét toàn bộ người dùng hiện có trong database.
  - Kiểm tra tính hợp lệ và trùng lặp email: nếu phát hiện bất kỳ tài khoản nào có email trống, không hợp lệ hoặc trùng lặp giữa nhiều tài khoản, migration lập tức **DỪNG LẠI (`RuntimeError`)** và in danh sách chi tiết các tài khoản vi phạm để quản trị viên xử lý thủ công, tuyệt đối không tự ý gộp/xóa tài khoản.
  - Backfill các tài khoản hợp lệ sang `AccountEmailIdentity` ở trạng thái chưa xác minh (`verified_at=None`), yêu cầu xác minh trước khi nhận lời mời workspace.

### 3.3. Xử lý Chống Đăng nhập Mơ hồ (Ambiguous Login Prevention)
- Tái cấu trúc `EmailOrUsernameModelBackend`:
  - Khi người dùng đăng nhập bằng chuỗi định danh: tìm đồng thời identity theo email và user theo username.
  - Nếu chuỗi đăng nhập khớp đồng thời username của User A và email của User B (User A != User B), backend từ chối xác thực ngay lập tức (`return None`), ghi log cảnh báo và không bao giờ chọn tùy tiện tài khoản đầu tiên (`order_by("id").first()`).
  - Nếu có nhiều hơn 1 bản ghi khớp trong cùng một tiêu chí tìm kiếm, từ chối xác thực ngay lập tức.

### 3.4. Service Layer, Token Verification Dùng Một Lần & Rate Limiting
- `apps/accounts/services.py`:
  - `normalize_email()`: chuẩn hóa email nhất quán.
  - `create_user_with_identity()`: tạo User và AccountEmailIdentity trong một transaction atomic, kiểm tra unique ở CSDL, chỉ gửi email xác minh sau khi transaction commit thành công (`transaction.on_commit`).
  - `update_user_email()`: cập nhật email trong transaction, khóa hàng bằng `select_for_update()`, kiểm tra unique ở CSDL, tự động reset `verified_at = None`, tăng `token_version += 1` để hủy toàn bộ token cũ, và chỉ gửi email xác minh sau khi commit (`transaction.on_commit`).
  - `EmailVerificationTokenGenerator`: mở rộng từ `PasswordResetTokenGenerator`, hash bao gồm user id, password, email, `token_version` và `verified_at`. Bất kỳ thay đổi nào về mật khẩu, email, hoặc `token_version` đều làm mất hiệu lực token cũ.
  - `send_verification_email()`: hỗ trợ rate limit cooldown 60 giây (`can_send_verification_email`). Nếu gửi email thất bại do lỗi SMTP: giữ nguyên tài khoản và identity trong DB, không ghi nhận thời điểm gửi (`last_verification_sent_at`) để người dùng không bị phạt cooldown oan và có thể thử lại ngay; tuyệt đối không ghi token hay URL xác minh vào log.
  - `verify_email_token()`: khóa hàng bằng `select_for_update()` chống tranh chấp đồng thời (race condition); từ chối nếu email đã xác minh hoặc email không khớp tài khoản; sau khi xác minh thành công lập tức cập nhật `verified_at` và tăng `token_version += 1`, bảo đảm token là **dùng một lần duy nhất (single-use)**, không thể bị tái sử dụng (replay attack); tuyệt đối không log token hay URL xác minh.

### 3.5. Đồng bộ Email Ở Mọi Đường Ghi & Quản trị Admin
- `apps/accounts/signals.py`: Lắng nghe tín hiệu `post_save` trên `User` để đồng bộ tự động `AccountEmailIdentity`, reset `verified_at` và tăng `token_version` khi đổi email trực tiếp hoặc qua script, loại bỏ hoàn toàn nguy cơ lệch dữ liệu giữa `User.email` và `AccountEmailIdentity`.
- `apps/accounts/admin.py`: Tùy biến `CustomUserAdmin.save_model` bọc transaction kiểm tra trùng email trên toàn hệ thống trước khi lưu, đồng bộ an toàn `AccountEmailIdentity`, hiển thị `token_version` và cấm sửa đổi tùy tiện.

### 3.6. Web Views & Giao diện Dashboard
- Thêm routes `/auth/verify-email/<uidb64>/<token>/` và `/auth/resend-verification/`.
- Cập nhật `CustomUserCreationForm` để gọi transaction atomic tạo User và Identity, đăng ký gửi email xác minh qua `transaction.on_commit`.
- Cập nhật `dashboard.html`:
  - Hiển thị badge trạng thái "Đã xác minh" (xanh) hoặc "Chưa xác minh" (đỏ).
  - Hiển thị banner nhắc nhở kèm nút bấm gửi lại email xác minh nếu tài khoản chưa xác minh email.

---

## 4. Kết quả Kiểm thử & Cách ly Database (Validation)

- **PostgreSQL Database & Cách ly Kiểm thử (Test Database Isolation):**
  - Đã kết nối và xác nhận trực tiếp trên PostgreSQL 17.11 (Supabase Session Pooler).
  - **Chứng minh cách ly độc lập:** Cấu hình rõ ràng `DATABASES["default"]["TEST"]` trong `core/settings.py` (hỗ trợ `TEST_DATABASE_URL` và `TEST_DATABASE_NAME`). CSDL ứng dụng thực tế (`postgres`) và CSDL test runner (`test_postgres`) là hai database riêng biệt trong hệ thống PostgreSQL (đã kiểm chứng qua truy vấn kích thước catalog: `postgres` 11 MB, `test_postgres` ~8 MB; bảng người dùng ứng dụng trên `postgres` hoàn toàn không bị ảnh hưởng bởi test).
- **Django Migrations:** Toàn bộ migrations (`accounts.0001_initial`, `accounts.0002_backfill_email_identities`, `accounts.0003_accountemailidentity_token_version`) áp dụng thành công 100% trên PostgreSQL.
- **Toàn bộ Bộ kiểm thử tự động (41/41 tests Passed):**
  - **15 tests** `core/tests_b00_runtime.py`: Pass 100% (fail-fast, billing disabled, auth cơ bản, staticfiles).
  - **26 tests** `core/tests_b00_email_identity.py`: Pass 100%:
    - Chuẩn hóa email, ràng buộc unique DB, reset verification khi đổi email.
    - Chặn đăng nhập mơ hồ giữa 2 user khác nhau (Ambiguous Login Prevention).
    - Chu kỳ tạo & xác minh token; bảo đảm token dùng một lần duy nhất (Replay Attack Rejected).
    - Token mất hiệu lực khi đổi mật khẩu, đổi email, hoặc đổi qua lại email cũ (`token_version`).
    - Gửi email qua `transaction.on_commit` không phát tán khi rollback.
    - Chịu lỗi SMTP: bảo toàn tài khoản, không phạt cooldown oan, không ghi lộ token/URL vào logs.
    - Đồng bộ email ở mọi đường ghi (`post_save` signal, Django Admin `save_model`).
    - Kiểm thử cạnh tranh đồng thời đa luồng (`TransactionTestCase` với `threading.Barrier` và `select_for_update()`).
    - Migration backfill dừng khi gặp duplicate/invalid email; luồng giao diện đăng ký & xác minh.

