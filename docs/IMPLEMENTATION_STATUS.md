# ==============================================================================
# Implementation Status - ContentOps Hub
# ==============================================================================

## 1. Trạng thái tổng thể

- **Spec cơ sở:** `docs/Spec-Ban-Content-Marketing-v1.0.md` (Phiên bản v1.0).
- **Mốc xuất phát:** Nhánh `chore/boilerplate-baseline` (commit `4fd4046`).
- **Nhánh hiện tại:** `feat/b02-workspace-members` (tiếp nối nhánh `feat/b01-workspaces`, commit `447fdd9`).

| Giai đoạn / Nhiệm vụ | Trạng thái | Ghi chú |
|---|---|---|
| **B00.1 — Chuẩn hóa môi trường & cấu hình** | **HOÀN TẤT** | Python 3.12, Django 5.2.18, `BILLING_ENABLED=False`, STORAGES, fail-fast production |
| **B00.2 — Chuẩn hóa Email identity & verification** | **HOÀN TẤT** | AccountEmailIdentity unique, chặn login mơ hồ, token verification, rate limit, migration backfill an toàn |
| **B01 — Workspace & Cách ly dữ liệu (Tenant Isolation)** | **HOÀN TẤT** | Workspace UUID, membership OWNER nguyên tử, cách ly truy cập 404, kiểm soát quyền sửa 403, chống giả mạo |
| **B02 — Thành viên, Lời mời & Phân quyền chi tiết** | **HOÀN TẤT** | Spec mục 3.1, 3.2, 9, 10, 13 (Lời mời token SHA-256 hash, hạn 7 ngày, nhận atomic lock DB, ma trận quyền OWNER/MEMBER, bảo vệ Chủ) |
| **B03 — Pipeline Sinh nội dung & AI Gateway (BYOK)** | CHƯA LÀM | Spec mục 10, 11 (Dừng trước B03 theo yêu cầu) |
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

## 5. Chi tiết thực hiện B02 (Thành viên, Lời mời & Phân quyền chi tiết)

### 5.1. Mô hình `Invitation` & Bảo mật Token (Spec mục 3.2 & 9)
- **Mô hình `Invitation` (`apps/workspaces/models.py`):**
  - Khóa chính: `id` kiểu `UUIDField` (`default=uuid.uuid4`, editable=False).
  - Khóa ngoại: `workspace` (`ForeignKey` trỏ `Workspace`, `on_delete=models.CASCADE`, `related_name="invitations"`).
  - Email: `email` (chuẩn hóa theo cơ chế `AccountEmailIdentity.normalize_email`, db_index=True).
  - Hash Token: `token_hash` (`CharField(max_length=64, unique=True, db_index=True)`), lưu băm SHA-256 của token an toàn (`secrets.token_urlsafe(32)`). Tuyệt đối không lưu raw token trong CSDL và không log raw token hoặc URL đầy đủ.
  - Vai trò: `access_role` mặc định `MEMBER`. Ràng buộc `clean()` chặn cứng không cho phép mời vai trò `OWNER`.
  - Hình thức quan hệ: `employment_type` (`IN_HOUSE` hoặc `FREELANCER`).
  - Cờ quyền AI: `ai_use_allowed` (`BooleanField`, mặc định False).
  - Người mời: `invited_by` (`ForeignKey` trỏ `User`, `on_delete=models.SET_NULL`, nullable).
  - Thời hạn: `expires_at` (mặc định 7 ngày theo Spec 3.2), `accepted_at` (nullable), `revoked_at` (nullable), `last_sent_at` (nullable).
  - Ràng buộc Index: `idx_invitation_ws_email` và `idx_invitation_token_hash`.
- **Migration:** `workspaces.0002_invitation` đã được tạo và áp dụng.

### 5.2. Service Layer Lời mời & Nhận lời mời (`apps/workspaces/services.py`)
- `create_workspace_invitation()`: Chỉ Chủ (`OWNER`) mới có quyền tạo lời mời. Chuẩn hóa email; từ chối mời nếu đã là thành viên `ACTIVE`; từ chối nếu thành viên đang `INACTIVE` (phải kích hoạt lại thay vì tạo lời mời mới). Gửi email sau commit transaction (`transaction.on_commit`), lỗi mail không làm mất lời mời đã tạo; trả về raw token để Chủ sao chép trực tiếp.
- `resend_workspace_invitation()`: Chỉ Chủ; áp dụng cooldown 60 giây; sinh token mới và gia hạn 7 ngày.
- `revoke_workspace_invitation()`: Chỉ Chủ; đánh dấu `revoked_at`; lời mời sau khi thu hồi không thể sử dụng hay gửi lại.
- `accept_workspace_invitation()`: Bọc `@transaction.atomic` cùng với khóa DB `select_for_update()` trên bản ghi `Invitation` và `Membership`. Yêu cầu đăng nhập và email identity đã xác minh (`AccountEmailIdentity.is_verified == True`). Kiểm tra email đã xác minh khớp chính xác với `invitation.email`. Cấp `Membership` theo dữ liệu lời mời, không tin dữ liệu client. Đánh dấu `accepted_at`, bảo đảm chống race condition khi có nhiều request đồng thời.

### 5.3. Quản trị Thành viên & Bảo vệ Chủ (Member Management & Owner Guards)
- `update_member_settings()`: Chỉ Chủ được sửa `employment_type` và `ai_use_allowed` của thành viên.
- `deactivate_membership()`: Chỉ Chủ được vô hiệu hóa thành viên (`status=INACTIVE`). **Bảo vệ Chủ tuyệt đối:** ném `ValidationError` nếu cố tình vô hiệu hóa Chủ workspace (`membership.user_id == workspace.owner_user_id` hoặc `access_role == OWNER`).
- `reactivate_membership()`: Kích hoạt lại thành viên đã bị vô hiệu hóa (`status=ACTIVE`).
- **Hiệu lực tức thì:** Khi thành viên bị vô hiệu hóa, `get_workspace_for_user()` trả về 404 ngay ở request kế tiếp; context processor lập tức dọn session key `active_workspace_id`.

### 5.4. Giao diện Người dùng & Ranh giới Phân quyền (Templates & Views)
- `templates/workspaces/workspace_members.html`: Danh sách thành viên trong workspace và danh sách lời mời (dành riêng cho Chủ).
- `templates/workspaces/workspace_invite.html` & `workspace_invite_success.html`: Form gửi lời mời và trang hiển thị liên kết để Chủ sao chép trực tiếp.
- `templates/workspaces/member_edit.html`: Form sửa thiết lập thành viên.
- `templates/workspaces/invitation_accept.html`: Trang tiếp nhận và nút POST chấp nhận lời mời có CSRF.
- `templates/workspaces/invitation_unverified.html`: Hướng dẫn xác minh email nếu tài khoản chưa xác minh.
- `templates/workspaces/invitation_mismatch.html`: Cảnh báo khi tài khoản đăng nhập không khớp với email được mời.
- `templates/workspaces/invitation_invalid.html`: Thông báo khi liên kết hết hạn, đã thu hồi hoặc đã sử dụng.

---



## 6. Kết quả Kiểm thử & Cách ly Database (Validation)

- **PostgreSQL Database & Cách ly Kiểm thử (Test Database Isolation):**
  - Đã kết nối và xác nhận trực tiếp trên PostgreSQL 17.11 (Supabase Session Pooler).
  - **Chứng minh cách ly độc lập:** Cấu hình rõ ràng `DATABASES["default"]["TEST"]` trong `core/settings.py` (hỗ trợ `TEST_DATABASE_URL` và `TEST_DATABASE_NAME`). CSDL ứng dụng thực tế (`postgres`) và CSDL test runner (`test_postgres`) là hai database riêng biệt trong hệ thống PostgreSQL (đã kiểm chứng qua truy vấn kích thước catalog: `postgres` 11 MB, `test_postgres` ~8 MB; bảng người dùng ứng dụng trên `postgres` hoàn toàn không bị ảnh hưởng bởi test).
- **Django Migrations:** Toàn bộ migrations (`accounts.0001_initial`, `accounts.0002_backfill_email_identities`, `accounts.0003_accountemailidentity_token_version`, `workspaces.0001_initial`, `workspaces.0002_invitation`) áp dụng thành công 100% trên PostgreSQL.
- **Toàn bộ Bộ kiểm thử tự động (74/74 tests Passed):**
  - **15 tests** `core/tests_b00_runtime.py`: Pass 100% (fail-fast, billing disabled, auth cơ bản, staticfiles).
  - **26 tests** `core/tests_b00_email_identity.py`: Pass 100% (chuẩn hóa email, single-use token, atomic concurrency lock `select_for_update`, out-of-transaction email, SMTP error handling, signals & admin write-path sync).
  - **15 tests** `core/tests_b01_workspaces.py`: Pass 100% (tenant isolation, single-owner consistency, HTTP 403/404, session fallback).
  - **18 tests** `core/tests_b02_workspace_members.py`: Pass 100%:
    1. Xác nhận test runner chạy trên database test độc lập (`test_postgres`).
    2. Ma trận quyền B02: Chủ có quyền mời/sửa/thu hồi, thành viên bị chặn 403 khi thao tác quản trị, người ngoài nhận 404 khi truy cập workspace ID.
    3. Tạo lời mời thành công, email chuẩn hóa, token lưu dạng SHA-256 hash (64 hex), raw token không lọt vào DB.
    4. Chặn tạo lời mời với vai trò OWNER (ValidationError).
    5. Chặn tạo lời mời trùng đang chờ xử lý cho cùng một email.
    6. Chặn mời người đã là thành viên ACTIVE hoặc INACTIVE (phải kích hoạt lại qua quản lý thành viên).
    7. Gửi email sau commit; lỗi gửi mail không rollback lời mời đã tạo.
    8. Gửi lại có cooldown 60s; sau khi thu hồi không thể nhận hoặc gửi lại.
    9. Nhận lời mời yêu cầu đăng nhập (redirect kèm next parameter) và email identity đã xác minh.
    10. Tài khoản có email khác bị chặn không được chấp nhận lời mời của email được mời.
    11. Nhận lời mời thành công qua POST có CSRF, tạo Membership ACTIVE (role MEMBER, đúng employment_type và ai_use_allowed), cập nhật session active workspace.
    12. Ràng buộc token an toàn: dùng một lần duy nhất, token hết hạn bị chặn, token đã thu hồi bị chặn, token giả mạo trả 404 không lộ workspace.
    13. Bảo vệ Chủ workspace: cấm vô hiệu hóa hoặc hạ quyền Chủ.
    14. Hiệu lực tức thì sau khi vô hiệu hóa: thành viên bị vô hiệu hóa nhận ngay 404 ở request kế tiếp, session bị xóa bỏ.
    15. Chủ cập nhật `employment_type` và `ai_use_allowed` của thành viên thành công.
    16. Chủ kích hoạt lại thành viên đã bị vô hiệu hóa thành công.
    17. Lời mời bị thu hồi trước khi nhận bị chặn.
    18. Kiểm thử cạnh tranh song song (`WorkspaceConcurrencyB02Tests`): hai request nhận đồng thời chỉ đúng 1 request thành công, không sinh membership trùng nhờ `select_for_update()` và ràng buộc DB.

