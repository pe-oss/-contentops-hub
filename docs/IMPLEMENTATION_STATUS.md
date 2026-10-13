# ==============================================================================
# Implementation Status - ContentOps Hub
# ==============================================================================

## 1. Trạng thái tổng thể

- **Spec cơ sở:** `docs/Spec-Ban-Content-Marketing-v1.0.md` (Phiên bản v1.0).
- **Mốc xuất phát:** Nhánh `chore/boilerplate-baseline` (commit `4fd4046`).
- **Nhánh hiện tại:** `feat/b01-workspaces` (tiếp nối nhánh `feat/b00-email-identity`, commit `9c589fb`).

| Giai đoạn / Nhiệm vụ | Trạng thái | Ghi chú |
|---|---|---|
| **B00.1 — Chuẩn hóa môi trường & cấu hình** | **HOÀN TẤT** | Python 3.12, Django 5.2.18, `BILLING_ENABLED=False`, STORAGES, fail-fast production |
| **B00.2 — Chuẩn hóa Email identity & verification** | **HOÀN TẤT** | AccountEmailIdentity unique, chặn login mơ hồ, token verification, rate limit, migration backfill an toàn |
| **B01 — Workspace & Cách ly dữ liệu (Tenant Isolation)** | **HOÀN TẤT** | Workspace UUID, membership OWNER nguyên tử, cách ly truy cập 404, kiểm soát quyền sửa 403, chống giả mạo |
| **B02 — Thành viên, Lời mời & Phân quyền chi tiết** | CHƯA LÀM | Spec mục 3.2, 8, 18 (Dừng trước B02 theo yêu cầu) |
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

## 4. Chi tiết thực hiện B01 (Workspaces & Tenant Data Isolation)

### 4.1. Ứng dụng `apps/workspaces` & Mô hình Dữ liệu Tối thiểu
- **Tạo ứng dụng:** Khởi tạo `apps/workspaces` (`apps.py`, `models.py`, `selectors.py`, `services.py`, `forms.py`, `views.py`, `urls.py`, `admin.py`, `context_processors.py`). Đã đăng ký vào `INSTALLED_APPS` và gán template context processor `workspace_context`.
- **Mô hình `Workspace`:**
  - Khóa chính: `id` kiểu `UUIDField` (`default=uuid.uuid4`, editable=False).
  - Tên: `name` (1–100 ký tự, strip whitespace, không rỗng, không chỉ khoảng trắng).
  - Múi giờ: `timezone` (mặc định `Asia/Ho_Chi_Minh`, validate chuẩn danh mục IANA `zoneinfo.available_timezones()`).
  - Chủ workspace: `owner_user` (`ForeignKey` trỏ `settings.AUTH_USER_MODEL`, `on_delete=models.PROTECT`, `related_name="owned_workspaces"`).
  - Thời gian: `created_at` (auto_now_add), `updated_at` (auto_now).
- **Mô hình `Membership`:**
  - Khóa chính: `id` kiểu `UUIDField` (`default=uuid.uuid4`, editable=False).
  - Quan hệ: `workspace` (FK CASCADE), `user` (FK CASCADE).
  - `access_role`: Enum `OWNER` ("Chủ workspace"), `MEMBER` ("Thành viên").
  - `employment_type`: Enum `IN_HOUSE` ("Nội bộ"), `FREELANCER` ("Freelancer / Đối tác ngoài").
  - `status`: Enum `ACTIVE` ("Đang hoạt động"), `INACTIVE` ("Vô hiệu hóa"), `INVITED` ("Đang mời").
  - `ai_use_allowed`: BooleanField (`default=False`, OWNER mặc định True).
  - Ràng buộc toàn vẹn CSDL: `UniqueConstraint(fields=["workspace", "user"], name="unique_workspace_user")` ngăn chặn hoàn toàn việc tạo trùng lặp membership cho cùng một người dùng trong một workspace.
- **Migration:** `workspaces.0001_initial` đã khởi tạo và áp dụng thành công trên cơ sở dữ liệu PostgreSQL.

### 4.2. Khởi tạo Workspace & Quyền Chủ (Single Owner Consistency)
- `create_workspace_with_owner()`:
  - Bọc `@transaction.atomic`.
  - Validate tên và timezone.
  - Tạo `Workspace` và gắn `owner_user = user`.
  - Tạo `Membership` gắn vai trò `access_role=OWNER`, `status=ACTIVE`, `ai_use_allowed=True` trong cùng transaction.
  - Nếu xảy ra lỗi bất kỳ, toàn bộ transaction bị rollback, không để lại bản ghi rác hoặc dở dang.
  - `owner_user` là nguồn duy nhất xác định Chủ; membership OWNER luôn nhất quán với trường này.
  - Không lấy `owner_user` hay `access_role` từ dữ liệu form client để cấp quyền (chống parameter tampering / privilege escalation).
  - Không cấp cờ `is_staff` hay `is_superuser` của Django cho Chủ workspace.
- **Quản trị Django Admin (`apps/workspaces/admin.py`):**
  - Đồng bộ nhất quán `WorkspaceAdmin.save_model` và `MembershipAdmin.save_model`.
  - Ngăn cấm hạ quyền OWNER của người đang là `owner_user` của workspace.
  - Từ chối tạo hai Chủ trong cùng một workspace qua Admin.

### 4.3. Phân quyền & Cách ly Dữ liệu (Backend Enforcing)
- **Tầng Selectors (`apps/workspaces/selectors.py`):**
  - `get_user_workspaces(user)`: Lọc nghiêm ngặt các workspace mà người dùng có membership trạng thái `ACTIVE`.
  - `get_workspace_for_user(user, workspace_id)`:
    - Nếu workspace không tồn tại HOẶC người dùng không có membership `ACTIVE`: **trả về HTTP 404** (Spec 3.1: "Với đối tượng ngoài phạm vi đọc trả 404", ngăn chặn kẻ tấn công dò quét ID workspace bằng URL injection).
- **Tầng Services (`apps/workspaces/services.py`):**
  - `update_workspace_info()`: Kiểm tra quyền Chủ. Nếu người dùng chỉ là `MEMBER` hoặc membership không active, lập tức ném `PermissionDenied` (HTTP 403: "Với đối tượng được đọc nhưng không được sửa trả 403").
  - `switch_active_workspace()`: Kiểm tra quyền thành viên trước khi ghi nhận `active_workspace_id` vào session; nếu không phải thành viên ném 404.
  - `get_current_active_workspace()`: Tái xác thực membership thực tế trong DB trên mỗi request. Nếu session chứa ID mà user đã bị thu hồi/vô hiệu hóa quyền (`status=INACTIVE`), session key lập tức bị xóa bỏ và hệ thống tự động fallback an toàn về workspace hợp lệ khác hoặc `None`. Tuyệt đối không coi session là bằng chứng phân quyền.

### 4.4. Giao diện Người dùng (Templates & HTMX)
- `templates/workspaces/workspace_list.html`: Danh sách các workspace người dùng đang tham gia; nếu chưa có workspace nào sẽ hiển thị giao diện hướng dẫn và nút CTA "Tạo Workspace đầu tiên".
- `templates/workspaces/workspace_form.html`: Giao diện tạo workspace với validate tên và timezone trực quan.
- `templates/workspaces/workspace_detail.html`: Trang tổng quan workspace tối thiểu, hiển thị thông tin ranh giới cách ly UUID, vai trò người dùng, số thành viên, và nút chỉnh sửa (chỉ hiển thị với Chủ).
- `templates/workspaces/workspace_edit.html`: Giao diện sửa thông tin dành riêng cho Chủ.
- `templates/base.html` & `templates/dashboard.html`: Tích hợp hiển thị workspace đang chọn trên thanh điều hướng và trang Dashboard của người dùng.

---


## 5. Kết quả Kiểm thử & Cách ly Database (Validation)

- **PostgreSQL Database & Cách ly Kiểm thử (Test Database Isolation):**
  - Đã kết nối và xác nhận trực tiếp trên PostgreSQL 17.11 (Supabase Session Pooler).
  - **Chứng minh cách ly độc lập:** Cấu hình rõ ràng `DATABASES["default"]["TEST"]` trong `core/settings.py` (hỗ trợ `TEST_DATABASE_URL` và `TEST_DATABASE_NAME`). CSDL ứng dụng thực tế (`postgres`) và CSDL test runner (`test_postgres`) là hai database riêng biệt trong hệ thống PostgreSQL (đã kiểm chứng qua truy vấn kích thước catalog: `postgres` 11 MB, `test_postgres` ~8 MB; bảng người dùng ứng dụng trên `postgres` hoàn toàn không bị ảnh hưởng bởi test).
- **Django Migrations:** Toàn bộ migrations (`accounts.0001_initial`, `accounts.0002_backfill_email_identities`, `accounts.0003_accountemailidentity_token_version`, `workspaces.0001_initial`) áp dụng thành công 100% trên PostgreSQL.
- **Toàn bộ Bộ kiểm thử tự động (56/56 tests Passed):**
  - **15 tests** `core/tests_b00_runtime.py`: Pass 100% (fail-fast, billing disabled, auth cơ bản, staticfiles).
  - **26 tests** `core/tests_b00_email_identity.py`: Pass 100% (chuẩn hóa email, single-use token, atomic concurrency lock `select_for_update`, out-of-transaction email, SMTP error handling, signals & admin write-path sync).
  - **15 tests** `core/tests_b01_workspaces.py`: Pass 100%:
    1. Xác nhận test runner chạy trên database test độc lập (`test_postgres`).
    2. Người dùng chưa đăng nhập bị chặn (chuyển hướng 302 về login) trên tất cả các routes workspace.
    3. Tạo workspace atomic sinh đúng 1 `Membership(OWNER, IN_HOUSE, ACTIVE, ai_use_allowed=True)`, không cấp staff/superuser.
    4. Validation tên (1-100 ký tự, strip whitespace, không rỗng) và múi giờ IANA.
    5. Rollback atomic khi gặp lỗi: không để lại workspace hoặc membership mồ côi/dở dang.
    6. Danh sách workspace hiển thị riêng cho từng user; người chưa có workspace thấy hướng dẫn và CTA tạo mới.
    7. Cách ly dữ liệu: người ngoài workspace truy cập trực tiếp bằng ID (detail, edit, switch) nhận 404 (chống enumeration).
    8. Client không thể giả mạo `owner_user` hoặc `access_role` để leo thang đặc quyền.
    9. Ràng buộc CSDL `UniqueConstraint(workspace, user)` từ chối tạo trùng membership.
    10. Membership bị vô hiệu hóa (`INACTIVE`) lập tức mất quyền ở request kế tiếp, kể cả session còn lưu ID cũ.
    11. Vai trò `MEMBER` xem được tổng quan (200), nhưng truy cập hoặc POST sửa thông tin workspace bị chặn 403 (`PermissionDenied`).
    12. Người dùng tham gia nhiều workspace chuyển đổi trơn tru và session cập nhật đúng ranh giới.
    13. Các đường ghi bảo toàn tính nhất quán một Chủ duy nhất, từ chối tạo lệch giữa `owner_user` và `OWNER`.
    14. Admin model save bảo toàn tính nhất quán giữa `owner_user` và `Membership OWNER`.
    15. Context processor tự động dọn session khi membership bị vô hiệu và fallback an toàn sang workspace active khác.

