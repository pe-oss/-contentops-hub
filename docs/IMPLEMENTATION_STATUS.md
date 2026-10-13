# ==============================================================================
# Implementation Status - ContentOps Hub
# ==============================================================================

## 1. Trạng thái tổng thể

- **Spec cơ sở:** `docs/Spec-Ban-Content-Marketing-v1.0.md` (Phiên bản v1.0).
- **Mốc xuất phát:** Nhánh `chore/boilerplate-baseline` (commit `4fd4046`).
- **Nhánh hiện tại:** `feat/b03` (tiếp nối nhánh `feat/b02-workspace-members`, commit `bbf4938`).

| Giai đoạn / Nhiệm vụ | Trạng thái | Ghi chú |
|---|---|---|
| **B00.1 — Chuẩn hóa môi trường & cấu hình** | **HOÀN TẤT** | Python 3.12, Django 5.2.18, `BILLING_ENABLED=False`, STORAGES, fail-fast production |
| **B00.2 — Chuẩn hóa Email identity & verification** | **HOÀN TẤT** | AccountEmailIdentity unique, chặn login mơ hồ, token verification, rate limit, migration backfill an toàn |
| **B01 — Workspace & Cách ly dữ liệu (Tenant Isolation)** | **HOÀN TẤT** | Workspace UUID, membership OWNER nguyên tử, cách ly truy cập 404, kiểm soát quyền sửa 403, chống giả mạo |
| **B02 — Thành viên, Lời mời & Phân quyền chi tiết** | **HOÀN TẤT** | Spec mục 3.1, 3.2, 9, 10, 13 (Lời mời token SHA-256 hash, hạn 7 ngày, nhận atomic lock DB, ma trận quyền OWNER/MEMBER, bảo vệ Chủ) |
| **B03 — Hồ sơ thương hiệu (Brand Profile)** | **HOÀN TẤT** | Spec mục 4, 7 UI02, 9, 10, 13, 14 AC15 (OneToOne unique, validate trường dữ liệu, HTTPS source URLs, auto-increment revision, optimistic concurrency 409, snapshot bất biến) |
| **B04 — Gói, kế hoạch, phân công (Packages & Planning)** | CHƯA LÀM | Spec mục 4, 5 F02, 9, 13 B04 (Dừng trước B04 theo quy định) |
| **B05 — Phiên bản và luồng viết/biên tập (Writing/Editing)** | CHƯA LÀM | Spec mục 5 F03-F04, 9, 13 B05 |
| **B06 — Chủ duyệt, mở lại, trạng thái (Approval & Lifecycle)** | CHƯA LÀM | Spec mục 5 F05, 9, 13 B06 |
| **B07 — Xuất bản và hoàn thành gói (Publishing)** | CHƯA LÀM | Spec mục 5 F06, 9, 13 B07 |
| **B08 — Blocker, đổi người, thu hồi (Task Reassignment)** | CHƯA LÀM | Spec mục 6, 9, 13 B08 |
| **B09 — Tổng quan, Việc của tôi, thông báo (Dashboard & Tasks)** | CHƯA LÀM | Spec mục 7 UI01/UI06, 8, 9, 13 B09 |
| **B10 — Responsive, lỗi, backup, QA lõi (Core QA)** | CHƯA LÀM | Spec mục 13 B10, 14 AC01-AC18 |

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

## 6. Chi tiết thực hiện B03 (Hồ sơ thương hiệu - Brand Profile)

### 6.1. Mô hình `BrandProfile` & Ràng buộc toàn vẹn CSDL (Spec mục 4 & 9)
- **Mô hình `BrandProfile` (`apps/workspaces/models.py`):**
  - Khóa chính: `id` kiểu `UUIDField` (`default=uuid.uuid4`, editable=False).
  - Khóa ngoại: `workspace` quan hệ `OneToOneField` với `Workspace` (`related_name="brand_profile"`, `on_delete=models.CASCADE`), đảm bảo mỗi workspace có duy nhất một hồ sơ thương hiệu.
  - Trường bắt buộc:
    - `name`: Tên thương hiệu, `CharField(max_length=100)`, strip whitespace, không rỗng.
    - `product_summary`: Sản phẩm / Dịch vụ chủ lực, `TextField(max_length=5000)`, strip whitespace, không rỗng.
    - `target_audience`: Khách hàng mục tiêu, `TextField(max_length=3000)`, strip whitespace, không rỗng.
  - Trường tùy chọn (Brand Guidelines):
    - `tone_of_voice`: Giọng văn thương hiệu, `TextField(max_length=3000, blank=True)`.
    - `avoid_guidelines`: Điều cần tránh (từ ngữ, thông điệp cấm kỵ), `TextField(max_length=3000, blank=True)`.
    - `allowed_claims`: Tuyên bố, cam kết được phép sử dụng, `TextField(max_length=3000, blank=True)`.
  - Kiểm tra URL nguồn tham khảo:
    - `source_urls`: `JSONField(default=list, blank=True)`, tối đa 10 URL.
    - Validate bắt buộc giao thức HTTPS và tên miền hợp lệ; cấm tuyệt đối HTTP hoặc scheme khác (Spec mục 4).
  - Quản lý phiên bản & Người cập nhật:
    - `revision`: `PositiveIntegerField(default=1)`, tự động tăng tuần tự sau mỗi lần cập nhật thành công.
    - `updated_by`: `ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)`, ghi nhận người cập nhật.
    - `created_at`, `updated_at`: mốc thời gian lưu UTC.
  - Phương thức `to_snapshot()`: Trích xuất snapshot JSON độc lập chứa đầy đủ thông tin thương hiệu tại `revision` hiện tại, phục vụ gắn vào Gói content (Packages) ở các milestone sau mà không bị ảnh hưởng khi hồ sơ sau đó bị sửa đổi (Spec F02 & AC15).
- **Migration:** `workspaces.0003_brandprofile` đã tạo và áp dụng thành công trên PostgreSQL.

### 6.2. Service Layer & Xử lý Tranh chấp Phiên bản Đồng thời (Optimistic Concurrency Control)
- `apps/workspaces/services.py`:
  - `save_brand_profile()`: Bọc trong transaction nguyên tử `@transaction.atomic`.
  - Khóa dòng bằng `select_for_update()` trên bản ghi `BrandProfile` của workspace để tuần tự hóa các thao tác cập nhật.
  - Hỗ trợ cơ chế Optimistic Concurrency Control (Spec AC10): Nếu `expected_revision` được truyền lên từ form client không khớp với `revision` thực tế trong CSDL, hệ thống ném `ConcurrencyConflictError` (HTTP 409 Conflict) và không ghi đè dữ liệu; bảo toàn nội dung người dùng vừa nhập để họ kiểm tra lại.
  - Tự động tăng `revision += 1` khi lưu thành công.

### 6.3. Ma trận Phân quyền B03 & Cách ly Workspace
- **Phân quyền Backend (Spec mục 3.1 & 10):**
  - **Chủ workspace (OWNER):** Có toàn quyền xem và tạo/sửa hồ sơ thương hiệu (GET 200, POST 302/redirect).
  - **Thành viên (MEMBER):** Có quyền xem hồ sơ ở chế độ chỉ đọc (GET 200); nếu gửi POST cố tình sửa đổi sẽ bị chặn ngay lập tức với mã lỗi **HTTP 403 Forbidden** (`PermissionDenied`).
  - **Người ngoài workspace (OUTSIDER) / Thành viên bị vô hiệu hóa (INACTIVE):** Khi truy cập URL hồ sơ thương hiệu nhận ngay mã lỗi **HTTP 404 Not Found** (`get_workspace_for_user`), hoàn toàn không phân biệt hoặc tiết lộ sự tồn tại của workspace.

### 6.4. Giao diện Người dùng (UI02 Template & HTMX)
- `templates/workspaces/brand_profile.html`:
  - Tương thích giao diện Bootstrap/Custom CSS hiện có.
  - Banner cảnh báo quy tắc snapshot độc lập theo Spec UI02 & AC15: ghi rõ snapshot gói cũ không tự đổi khi sửa hồ sơ thương hiệu.
  - Hiển thị badge vai trò (Chủ workspace / Thành viên chỉ đọc) và số phiên bản (`Revision X`).
  - Phân nhánh hiển thị:
    - Với Chủ: Form đầy đủ có các ô nhập liệu, help text, hiển thị lỗi validation giữ nguyên nội dung đã nhập, và banner cảnh báo lỗi xung đột phiên bản (HTTP 409).
    - Với Thành viên: Thẻ hiển thị quy chuẩn thương hiệu trang nhã, làm nổi bật điều cần tránh (màu đỏ) và tuyên bố được phép (màu xanh), danh sách URL nguồn có link mở tab mới an toàn.
  - Tích hợp nút điều hướng "🏷️ Hồ sơ thương hiệu" trên trang chi tiết Workspace (`workspace_detail.html`).


---



## 7. Kết quả Kiểm thử & Cách ly Database (Validation)

- **PostgreSQL Database & Cách ly Kiểm thử (Test Database Isolation):**
  - Đã kết nối và xác nhận trực tiếp trên PostgreSQL 17.11 (Supabase Session Pooler).
  - **Chứng minh cách ly độc lập:** Cấu hình rõ ràng `DATABASES["default"]["TEST"]` trong `core/settings.py` (hỗ trợ `TEST_DATABASE_URL` và `TEST_DATABASE_NAME`). CSDL ứng dụng thực tế (`postgres`) và CSDL test runner (`test_postgres`) là hai database riêng biệt trong hệ thống PostgreSQL (đã kiểm chứng qua truy vấn kích thước catalog: `postgres` 11 MB, `test_postgres` ~8 MB; bảng người dùng ứng dụng trên `postgres` hoàn toàn không bị ảnh hưởng bởi test).
- **Django Migrations:** Toàn bộ migrations (`accounts.0001_initial`, `accounts.0002_backfill_email_identities`, `accounts.0003_accountemailidentity_token_version`, `workspaces.0001_initial`, `workspaces.0002_invitation`, `workspaces.0003_brandprofile`) áp dụng thành công 100% trên PostgreSQL.
- **Toàn bộ Bộ kiểm thử tự động (84/84 tests Passed):**
  - **15 tests** `core/tests_b00_runtime.py`: Pass 100% (fail-fast, billing disabled, auth cơ bản, staticfiles).
  - **26 tests** `core/tests_b00_email_identity.py`: Pass 100% (chuẩn hóa email, single-use token, atomic concurrency lock `select_for_update`, out-of-transaction email, SMTP error handling, signals & admin write-path sync).
  - **15 tests** `core/tests_b01_workspaces.py`: Pass 100% (tenant isolation, single-owner consistency, HTTP 403/404, session fallback).
  - **18 tests** `core/tests_b02_workspace_members.py`: Pass 100% (ma trận quyền B02, lời mời SHA-256 token hash, bảo vệ Chủ, vô hiệu hóa tức thì, concurrency lock).
  - **10 tests** `core/tests_b03_brand_profile.py`: Pass 100%:
    1. Xác nhận test runner chạy trên database test độc lập (`test_postgres`).
    2. Khởi tạo và tự động tăng số phiên bản `revision` tuần tự (+1) sau mỗi lần lưu.
    3. Ràng buộc toàn vẹn CSDL: Mỗi workspace chỉ có duy nhất một BrandProfile (`OneToOneField` unique constraint).
    4. Validation trường dữ liệu theo Spec mục 4: tên (1-100 ký tự), tóm tắt sản phẩm (1-5000 ký tự), khách hàng mục tiêu (1-3000 ký tự), không chấp nhận chuỗi chỉ chứa khoảng trắng.
    5. Validation URL nguồn tham khảo: chỉ chấp nhận giao thức HTTPS, tối đa 10 URL, từ chối HTTP và scheme khác.
    6. Tính bất biến của snapshot thương hiệu (`to_snapshot()`): Snapshot đã xuất tại revision cũ không bị thay đổi khi BrandProfile được cập nhật sau đó (AC15 & Spec F02).
    7. Xử lý xung đột phiên bản đồng thời (Optimistic Concurrency Control - AC10): Truyền sai `expected_revision` lập tức trả về `ConcurrencyConflictError` (HTTP 409 Conflict), không ghi đè dữ liệu và giữ nguyên nội dung trên form.
    8. Ma trận phân quyền B03 & Cách ly Workspace: Chủ có quyền GET (200) và POST (302/redirect); Thành viên (MEMBER) chỉ được xem (GET 200, POST 403); Người ngoài (OUTSIDER) và thành viên bị vô hiệu hóa (INACTIVE) nhận HTTP 404 Not Found.
    9. Form validation lỗi trả về HTTP 400 và bảo toàn toàn bộ dữ liệu người dùng đã nhập.
    10. Đăng ký quản trị Django Admin cho `BrandProfile` với các trường chỉ đọc `id`, `revision`, `created_at`, `updated_at`.

