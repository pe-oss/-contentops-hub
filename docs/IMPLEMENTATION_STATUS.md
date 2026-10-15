# ==============================================================================
# Implementation Status - ContentOps Hub
# ==============================================================================

## 1. Trạng thái tổng thể

- **Spec cơ sở:** `docs/Spec-Ban-Content-Marketing-v1.0.md` (Phiên bản v1.0).
- **Mốc xuất phát:** Nhánh `chore/boilerplate-baseline` (commit `4fd4046`).
- **Nhánh hiện tại:** `feat/b08` (tiếp nối nhánh `feat/b07`, commit `38373f1`).

| Giai đoạn / Nhiệm vụ | Trạng thái | Ghi chú |
|---|---|---|
| **B00.1 — Chuẩn hóa môi trường & cấu hình** | **HOÀN TẤT** | Python 3.12, Django 5.2.18, `BILLING_ENABLED=False`, STORAGES, fail-fast production |
| **B00.2 — Chuẩn hóa Email identity & verification** | **HOÀN TẤT** | AccountEmailIdentity unique, chặn login mơ hồ, token verification, rate limit, migration backfill an toàn |
| **B01 — Workspace & Cách ly dữ liệu (Tenant Isolation)** | **HOÀN TẤT** | Workspace UUID, membership OWNER nguyên tử, cách ly truy cập 404, kiểm soát quyền sửa 403, chống giả mạo |
| **B02 — Thành viên, Lời mời & Phân quyền chi tiết** | **HOÀN TẤT** | Spec mục 3.1, 3.2, 9, 10, 13 (Lời mời token SHA-256 hash, hạn 7 ngày, nhận atomic lock DB, ma trận quyền OWNER/MEMBER, bảo vệ Chủ) |
| **B03 — Hồ sơ thương hiệu (Brand Profile)** | **HOÀN TẤT** | Spec mục 4, 7 UI02, 9, 10, 13, 14 AC15 (OneToOne unique, validate trường dữ liệu, HTTPS source URLs, auto-increment revision, optimistic concurrency 409, snapshot bất biến) |
| **B04 — Gói, kế hoạch, phân công (Packages & Planning)** | **HOÀN TẤT** | Spec mục 4, 5 F02, 9, 13 B04, 14 AC04/AC05 (Gói 50 bài, deadline 4 chặng, 3 vai trò, duyệt kế hoạch snapshot thương hiệu bất biến, sinh Task) |
| **B05 — Phiên bản và luồng viết/biên tập (Writing/Editing)** | **HOÀN TẤT** | Spec mục 5 F03-F04, 6, 9, 13 B05, 14 AC06/AC08/AC10/AC12 (ContentVersion bất biến, ReviewDecision append-only, Brief copy AI 1-click, Checklist 4 mục, OCC 409, phân quyền, Việc của tôi) |
| **B06 — Chủ duyệt, mở lại, trạng thái (Approval & Lifecycle)** | **HOÀN TẤT** | Spec mục 5 F05, 6, 9, 13 B06, 14 AC07/AC08/AC09/AC10/AC12 (Chủ duyệt version chốt, ContentApproval append-only & invalidation khi mở lại, stale version 409, phân quyền Chủ, nút rút duyệt, cờ chặn/gỡ chặn blocker, UI05 tác nghiệp hoàn chỉnh) |
| **B07 — Xuất bản và hoàn thành gói (Publishing)** | **HOÀN TẤT** | Spec mục 5 F06, 6.1, 6.2, 7 UI04, 9, 10, 13 B07, 14 AC12/AC13/AC14 (ContentPublication lưu lịch sử xuất bản có URL, thời điểm, approval/version chốt; Task PUBLISH -> DONE; tự động hoàn thành gói COMPLETED; giữ lịch sử khi mở lại; sửa metadata audit trail; OCC 409 & Idempotency) |
| **B08 — Blocker, đổi người, thu hồi (Task Reassignment)** | **HOÀN TẤT** | Spec mục 3.1, 3.2, 5 F07, 6.1, 6.2, 6.3, 7 UI03/UI05, 9, 10, 13 B08, 14 AC10, AC11, AC12 (AssignmentHistory append-only audit trail; đồng bộ ContentItem & Task nguyên tử; phân quyền Chủ workspace & Điều phối viên gói; OCC 409 & Idempotency; thu hồi thành viên bắt buộc bàn giao việc mở AC11; bảo vệ Single Owner; bảo toàn blocker AC12) |
| **B09 — Tổng quan, Việc của tôi, thông báo (Dashboard & Tasks)** | **HOÀN TẤT** | Spec mục 7 UI01/UI06, 8, 9, 10, 13 B09 (Dashboard UI01 3 vùng Cần quyết định, Bị chặn/Trễ hạn, Tiến độ gói; Việc của tôi UI06 ưu tiên Blocker > Overdue > Due_at, lọc trạng thái/vai trò/gói, bảo vệ task WAITING, phân trang 20/trang; In-App Notification unique recipient/event_id, rollback-safe, chuông navbar và trang /notifications) |
| **B10 — Responsive, lỗi, backup, QA lõi (Core QA)** | **HOÀN TẤT** | Spec mục 12, 13 B10, 14 AC01-AC18 (Responsive chuẩn 390px mobile & 1280px desktop, chụp 12 ảnh bằng chứng bằng Chrome Headless; xử lý lỗi 400/403/404/409/500 & CSRF không rò rỉ traceback/secrets; backup/restore tự động SQLite & PostgreSQL kèm SHA256 và retention 7 bản; full suite 201/201 tests PASS bao phủ toàn diện AC01-AC18) |


## 14. Chi tiết thực hiện B10 (Responsive 390px, Xử lý lỗi, Backup/Restore & QA Lõi AC01-AC18)

### 14.1. Tối ưu Giao diện Responsive & Bằng chứng Trình duyệt Thực tế (Spec UI01–UI06, AC16)
- **Chuẩn hóa màn hình di động 390px (Viewport chuẩn iPhone):**
  - Khắc phục triệt để hiện tượng vỡ khung / tràn ngang (`overflow-x: hidden` trên `html, body`).
  - Toàn bộ bảng dữ liệu (`<table>`) trong ứng dụng (bao gồm danh sách thành viên `workspace_members.html`, danh sách lời mời, lịch sử xuất bản, v.v.) được bọc trong container `.table-wrap` / `.table-responsive` với thanh cuộn ngang độc lập, không gây xô lệch bố cục trang.
  - Các grid tác vụ (`action-grid-2`, `responsive-two-cols`, deadline inputs trong biểu mẫu tạo/sửa gói và bài viết) tự động chuyển đổi từ 2 cột sang 1 cột dạng xếp chồng (stacking) trên màn hình <= 640px.
  - Tiêu đề, liên kết, URL dài và các chuỗi định danh được bổ sung thuộc tính `.break-words` (`word-break: break-word`, `overflow-wrap: anywhere`) chống tràn giao diện.
- **Kiểm chứng thực tế bằng Trình duyệt Google Chrome Headless:**
  - Xây dựng công cụ tự động hóa `scripts/capture_browser_evidence.py` khởi chạy máy chủ WSGI in-process kết hợp Google Chrome Headless (`chrome.exe --headless=new`).
  - Chụp và lưu trữ 12 ảnh bằng chứng thực tế tại thư mục `docs/screenshots/`:
    1. `mobile_390px_owner_review_ac16.png` (390 x 844 px): Màn hình Chủ workspace xem xét bài viết tại công đoạn `OWNER_REVIEW` (AC16) với 2 khối tác vụ "Phê duyệt" và "Yêu cầu sửa" hiển thị cân đối, vừa vặn, không tràn ngang.
    2. `mobile_390px_dashboard_ui01.png` (390 x 844 px): Tổng quan Workspace UI01 với 3 vùng chỉ số responsive.
    3. `mobile_390px_my_tasks_ui06.png` (390 x 844 px): Giao diện Việc của tôi UI06 xếp chồng gọn gàng, bộ lọc dropdown co giãn linh hoạt.
    4. `mobile_390px_brand_profile.png` (390 x 844 px): Hồ sơ thương hiệu với banner quy tắc phiên bản bất biến.
    5. `mobile_390px_members.png` (390 x 844 px): Danh sách thành viên và lời mời với bảng cuộn ngang mượt mà.
    6. `mobile_390px_notifications.png` (390 x 844 px): Trung tâm thông báo.
    7. `desktop_1280px_owner_review.png` (1280 x 800 px): Giao diện Chủ duyệt bài trên máy tính để bàn.
    8. `desktop_1280px_dashboard_ui01.png` (1280 x 800 px): Tổng quan Dashboard UI01 trên máy tính để bàn.
    9. `mobile_390px_error_403.png` (390 x 844 px): Trang lỗi 403 Forbidden thân thiện.
    10. `mobile_390px_error_404.png` (390 x 844 px): Trang lỗi 404 Not Found an toàn, zero-leakage.
    11. `mobile_390px_error_409.png` (390 x 844 px): Trang xung đột phiên bản dữ liệu (OCC 409).
    12. `mobile_390px_error_500.png` (390 x 844 px): Trang sự cố hệ thống 500 không lộ traceback/secrets.

### 14.2. Xử lý Lỗi Toàn diện & Bảo vệ CSRF (Zero Leakage)
- **Tập hợp Templates trang lỗi thân thiện:**
  - `templates/400.html`: Yêu cầu không hợp lệ (Bad Request).
  - `templates/403.html`: Truy cập bị từ chối / Không có quyền (Forbidden).
  - `templates/403_csrf.html`: Lỗi xác thực bảo mật / Phiên làm việc hết hạn (CSRF Failure).
  - `templates/404.html`: Không tìm thấy trang hoặc tài nguyên ngoài phạm vi (Not Found).
  - `templates/409.html`: Xung đột phiên bản dữ liệu đồng thời (Concurrency Conflict).
  - `templates/500.html`: Sự cố kỹ thuật hệ thống (Internal Server Error).
- **Nguyên tắc an toàn (Zero Leakage):**
  - Tuyệt đối không hiển thị Traceback, mã nguồn nội bộ, connection string, credentials hay secret keys ra ngoài màn hình người dùng.
  - Người ngoài (`OUTSIDER`) và thành viên vô hiệu hóa (`INACTIVE`) nhận mã `404 Not Found` đối với mọi tài nguyên workspace, ngăn ngừa nguy cơ đoán ID hay dò quét siêu dữ liệu (metadata leakage).
  - Cấu hình `CSRF_FAILURE_VIEW = "core.views.custom_csrf_failure_view"` trong `settings.py` hướng dẫn người dùng tải lại trang khi token hết hạn.
  - Bảo toàn dữ liệu người dùng (`form retention`): Khi xảy ra lỗi validation (HTTP 400) hoặc xung đột phiên bản (HTTP 409), dữ liệu người dùng vừa nhập được bảo lưu nguyên vẹn trên form để người dùng kiểm tra lại mà không phải gõ lại từ đầu.

### 14.3. Công cụ Sao lưu & Diễn tập Phục hồi Cơ sở Dữ liệu (Spec Mục 12, AC18)
- **Lệnh quản trị Django `manage.py backup_database` (`apps/workspaces/management/commands/backup_database.py`):**
  - Hỗ trợ cả 2 engine PostgreSQL (`pg_dump` định dạng custom compressed `-F c`) và SQLite (dùng Python SQLite Backup API đảm bảo snapshot nhất quán).
  - Bảo mật thông tin xác thực: Đọc credentials từ biến môi trường (`PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`) hoặc Django settings; không in mật khẩu ra log.
  - Ghi file tạm thời (`.tmp`) trước, chỉ rename thành file backup chính thức khi quá trình dump hoàn tất thành công 100% (chống ghi đè hỏng bản backup tốt).
  - Tính toán mã băm SHA-256 cho file backup và lưu kèm file `manifest.json` chứa thông tin thời gian UTC, kích thước và checksum.
  - Tự động áp dụng chính sách lưu giữ (Retention Policy): Giữ lại 7 bản sao lưu gần nhất theo Spec mục 12, tự động dọn dẹp các bản cũ hơn.
- **Lệnh quản trị Django `manage.py restore_database` (`apps/workspaces/management/commands/restore_database.py`):**
  - Tự động đối chiếu mã băm SHA-256 từ file manifest trước khi thực hiện phục hồi, ngăn chặn việc phục hồi từ file bị lỗi/sửa đổi.
  - Yêu cầu tham số `--target-db` bắt buộc chỉ định CSDL đích độc lập dùng cho diễn tập, loại trừ nguy cơ ghi đè nhầm database sản xuất.
  - Cơ chế tự kiểm chứng sau phục hồi: Kiểm tra số lượng bản ghi các bảng cốt lõi (`workspaces_workspace`, `workspaces_brandprofile`, `workspaces_package`, `workspaces_contentitem`, `workspaces_task`) và chạy kiểm tra ràng buộc khóa ngoại (`PRAGMA foreign_key_check` trên SQLite hoặc relational integrity trên PG).
- **Kịch bản tự động hóa máy chủ Linux/Production (`scripts/`):**
  - `scripts/backup_postgres.sh`: Shell script chạy cronjob hằng ngày cho PostgreSQL với SHA-256 và retention 7 bản.
  - `scripts/restore_postgres.sh`: Shell script diễn tập phục hồi thử nghiệm vào database cách ly `saas_content_drill`.

### 14.4. Ma trận Kiểm chứng Toàn diện AC01–AC18 (Spec Mục 14)
| ID | Yêu cầu kiểm chứng (Given / When) | Kết quả kỳ vọng (Then) | Ca kiểm thử / Bằng chứng | Môi trường | Kết quả |
|---|---|---|---|---|---|
| **AC01** | Không có kết nối AI; hoàn thành gói với AI bên ngoài | Tất cả bước hoạt động, không bị buộc nhập key | `CoreQAMilestoneB10Tests.test_ac01_no_ai_connection_complete_package_normally` | SQLite / Local | **PASS** |
| **AC02** | Freelancer biết ID bài người khác ngoài phạm vi | View/API trả 404; không lộ title, count, lịch sử | `test_ac02_freelancer_access_out_of_scope_item_returns_404` | SQLite / Local | **PASS** |
| **AC03** | MEMBER tự gọi endpoint duyệt / kết nối AI | Bị từ chối 403; dữ liệu kế hoạch/bài không đổi | `test_ac03_member_cannot_call_approve_endpoints` | SQLite / Local | **PASS** |
| **AC04** | Kế hoạch thiếu người hoặc hạn sai thứ tự; Chủ duyệt | Báo lỗi từng trường; không sinh một phần nhiệm vụ | `test_ac04_plan_approval_deadline_order_validation` | SQLite / Local | **PASS** |
| **AC05** | Nhấp duyệt kế hoạch 2 lần cùng idempotency key | Chỉ 1 snapshot và đúng 1 bộ nhiệm vụ (3 task/bài) | `test_ac05_plan_approval_double_click_idempotency` | SQLite / Local | **PASS** |
| **AC06** | Nộp v1, biên tập trả sửa, nộp v2 | V1 giữ nguyên; lý do sửa và người chịu trách nhiệm đúng | `test_ac06_version_immutability_and_return_reason` | SQLite / Local | **PASS** |
| **AC07** | Chủ đang xem v1 trong khi bản hiện hành đã đổi | Duyệt thất bại HTTP 409; không duyệt nhầm bản v2 | `test_ac07_owner_approve_stale_version_rejected_409` | SQLite / Local | **PASS** |
| **AC08** | Bài đang chờ duyệt, người viết gọi lưu bản mới | Bị từ chối tới khi rút/trả bước hợp lệ | `test_ac08_cannot_submit_version_when_in_owner_review` | SQLite / Local | **PASS** |
| **AC09** | Duyệt v2, Chủ mở lại để sửa | Approval v2 hết hiệu lực; không cho đăng theo approval cũ | `test_ac09_reopen_invalidates_approval_and_blocks_publication` | SQLite / Local | **PASS** |
| **AC10** | Hai người sửa cùng row_version | Một ghi thành công, một nhận 409; không mất dữ liệu | `test_ac10_optimistic_concurrency_control_409` | SQLite / Local | **PASS** |
| **AC11** | Thu hồi freelancer còn việc đang mở | Việc chuyển cho người thay/Chủ; quyền cũ hết; lịch sử giữ nguyên | `test_ac11_member_deactivation_reassigns_open_tasks` | SQLite / Local | **PASS** |
| **AC12** | Bài bị chặn; thử nộp/duyệt/đăng | Bị từ chối; lưu nháp hoặc gỡ chặn vẫn được theo quyền | `test_ac12_blocked_item_rejects_workflow_transitions` | SQLite / Local | **PASS** |
| **AC13** | Ghi nhận đăng thiếu URL hoặc chưa duyệt | Bị từ chối; nhập hợp lệ ghi đúng người, giờ, version | `test_ac13_publication_missing_url_or_unapproved_rejected` | SQLite / Local | **PASS** |
| **AC14** | 2 bài đăng, 1 bài hủy; hoặc cả 3 bài hủy | TH1 hoàn thành 2/2 và hiện 1 hủy; TH2 không hoàn thành | `test_ac14_package_completion_conditions` | SQLite / Local | **PASS** |
| **AC15** | Sửa thương hiệu sau duyệt kế hoạch | Snapshot gói không tự đổi; độc lập toàn diện | `test_ac15_brand_profile_immutability_snapshot_isolation` | SQLite / Local | **PASS** |
| **AC16** | Màn hình 390 px, Chủ duyệt bài | Đọc và thao tác được, không tràn ngang nội dung chính | `test_ac16_mobile_390px_owner_review_view` + `docs/screenshots/mobile_390px_owner_review_ac16.png` | Chrome Headless | **PASS** |
| **AC17** | Mất kết nối khi lưu form | Không báo thành công giả; giữ nội dung, thử lại không tạo trùng | `test_ac17_form_validation_retention_and_idempotency` | SQLite / Local | **PASS** |
| **AC18** | Khôi phục bản sao lưu thử | Đọc được gói/phiên bản/quyết định và quan hệ nhất quán | `test_ac18_database_backup_and_restore_verification` | SQLite Drill DB | **PASS** |

### 14.5. Phân tách Môi trường & Tình trạng Cổng Nghiệm thu (Release Gates R1)
| Cổng Nghiệm thu (Gate) | Tiêu chí Spec | Bằng chứng thực tế | Trạng thái cổng |
|---|---|---|---|
| **SQLite Regression Suite** | 100% tests PASS, không có lỗi hoặc skip | **201/201 tests PASS** (chạy trong 7.2s trên `core.test_settings`) | **ĐẠT (VERIFIED PASS)** |
| **Bố cục Trình duyệt 390px & Desktop** | Hiển thị trọn vẹn, không vỡ layout, table scroll riêng | Chụp thành công 12 ảnh bằng chứng bằng Chrome Headless tại `docs/screenshots/` | **ĐẠT (VERIFIED PASS)** |
| **Xử lý Lỗi & CSRF (Zero Leakage)** | 400/403/404/409/500 và CSRF không lộ secret | Templates tùy biến thân thiện, kiểm thử bằng RequestFactory và Client | **ĐẠT (VERIFIED PASS)** |
| **Sao lưu & Diễn tập Phục hồi CSDL** | Dump có SHA256, retention 7 bản, diễn tập phục hồi không lỗi FK | Lệnh `backup_database` & `restore_database` chạy diễn tập thành công trên target DB độc lập | **ĐẠT (VERIFIED PASS)** |
| **PostgreSQL Concurrency Gate** | Chạy concurrency OCC / Locking với kết nối riêng | Môi trường máy trạm phát triển cục bộ không cài đặt PostgreSQL service (cổng 5432 đóng). Đã chuẩn bị runner `core/postgres_test_settings.py` và shell scripts `scripts/`. | **CHỜ MÔI TRƯỜNG (PENDING CI/PG)** |
| **Release Gate R1 Lõi (Pilot Readiness)** | AC01–AC18 đạt, không mất dữ liệu, có hướng dẫn thử một gói | 18/18 tiêu chí AC01–AC18 được kiểm chứng tự động và bằng chứng trình duyệt; luồng E2E trọn vẹn | **SẴN SÀNG CHO PILOT NỘI BỘ (READY FOR PILOT)** |

---


## 13. Chi tiết thực hiện B09 (Dashboard UI01, Việc của tôi UI06 & Thông báo In-App)

### 13.1. Mô hình Dữ liệu B09 (`apps/workspaces/models.py`)
- **`NotificationEventType` (Enum sự kiện thông báo):**
  - `ASSIGNMENT` ("Giao việc / Đổi người"): khi duyệt kế hoạch gói, bàn giao bài viết (B08), hoặc bàn giao việc khi thu hồi thành viên (AC11).
  - `REVIEW_REQUEST` ("Bài chờ duyệt"): người viết nộp bản nháp cho biên tập, hoặc biên tập nộp bài cho Chủ duyệt.
  - `CHANGES_REQUESTED` ("Yêu cầu sửa"): biên tập yêu cầu người viết sửa lại, hoặc Chủ yêu cầu sửa trả về viết/biên tập.
  - `BLOCKED` ("Có blocker hướng tới bạn"): bài viết bị báo chặn kèm lý do.
  - `UNBLOCKED` ("Blocker đã được giải quyết"): bài viết được giải quyết và gỡ chặn.
- **`Notification` (Mô hình Thông báo trong ứng dụng - Spec mục 8, 9, 10, 13 B09):**
  - Trường dữ liệu: `id` (UUID), `workspace`, `recipient` (User), `event_id` (Idempotency key duy nhất), `event_type`, `entity_type` (`CONTENT_ITEM`/`TASK`/`PACKAGE`), `entity_id` (UUID), `title`, `message`, `target_url`, `read_at` (nullable), `created_at`.
  - Ràng buộc: `UniqueConstraint(fields=["recipient", "event_id"], name="unique_recipient_event")` — bảo đảm chống duplicate thông báo khi retry hoặc double-click.
  - Chỉ mục: `idx_notif_recip_read`, `idx_notif_ws_recip`.
  - Migration: `apps/workspaces/migrations/0011_notification.py`.
  - Quản trị: `apps/workspaces/admin.py` (`NotificationAdmin`).

### 13.2. Nghiệp vụ Domain, Bộ chọn & Lọc Quyền B09
- **`create_notification()` (`apps/workspaces/services.py`):**
  - Quy tắc cốt lõi Spec mục 8: *"Không thông báo cho chính người thao tác"* (`actor.pk == recipient.pk` tự động bỏ qua).
  - Thực thi nguyên tử trong transaction nghiệp vụ; nếu transaction rollback do lỗi/validation, không để lại thông báo rác trong CSDL.
  - Tích hợp tự động vào: `approve_plan`, `reassign_item_assignment`, `_reassign_member_responsibilities`, `submit_content_version`, `submit_for_owner_review`, `request_changes_decision`, `owner_request_changes`, `block_content_item`, `unblock_content_item`.
- **`get_workspace_dashboard_data()` (`apps/workspaces/selectors.py`):**
  - **Vùng 1: Cần quyết định:** Kế hoạch DRAFT chờ Chủ duyệt, Bài viết `OWNER_REVIEW` chờ Chủ duyệt, hoặc nhiệm vụ `READY` của chính user.
  - **Vùng 2: Bị chặn / Trễ hạn:** Lọc chính xác các bài có `blocked_reason` (Blockers) và tính hạn chót công đoạn hiện tại so với `timezone.now()` (Overdue). Bài đã xuất bản hoặc đã hủy không bao giờ bị tính trễ hạn.
  - **Vùng 3: Tiến độ gói:** Thống kê `x/y bài đã đăng` (trong đó mẫu số y không tính các bài đã hủy theo Spec AC14), ghi chú riêng số bài hủy nếu có.
  - **Phân quyền cách ly nghiêm ngặt:** Chủ workspace xem toàn bộ; Điều phối viên chỉ xem trong phạm vi gói được phân công; Thành viên thường chỉ xem các bài/nhiệm vụ của mình. Bộ đếm chỉ số tuyệt đối không làm rò rỉ dữ liệu ngoài quyền đọc.
- **`get_my_tasks_for_workspace()` (`apps/workspaces/selectors.py`):**
  - Thứ tự ưu tiên (Spec UI06): 1. Bài bị chặn (`is_blocked`) &rarr; 2. Việc trễ hạn (`is_overdue`) &rarr; 3. Đến hạn gần nhất (`due_at ASC`).
  - Hỗ trợ lọc theo trạng thái (`READY`, `IN_PROGRESS`, `WAITING`, `DONE`, `CANCELLED`), theo vai trò (`WRITE`, `EDIT`, `PUBLISH`) và theo gói nội dung.
- **`user_has_entity_access()` & `get_user_notifications()` (`apps/workspaces/selectors.py`):**
  - Kiểm tra quyền thực tế tại thời điểm đọc. Nếu thành viên bị thu hồi khỏi workspace hoặc bị đổi người phụ trách bài viết, thông báo cũ tự động bị ẩn khỏi danh sách và số chưa đọc; link thông báo kiểm tra quyền tại backend và trả về 403/404 không làm rò rỉ nội dung bài.

### 13.3. Giao diện & Trải nghiệm Người dùng B09
- `templates/workspaces/workspace_detail.html`: Màn hình Dashboard (UI01) tích hợp 3 vùng, stat cards và modular partials (`dashboard_decision_region.html`, `dashboard_blocked_overdue_region.html`, `dashboard_package_progress_region.html`).
- `templates/workspaces/my_tasks.html` & `my_tasks_card.html`: Màn hình Việc của tôi (UI06) với bộ lọc, sắp xếp ưu tiên trực quan, bảo vệ nhiệm vụ `WAITING` không có nút thao tác vượt bước, phân trang 20 dòng/trang.
- `templates/workspaces/notifications.html`: Hộp thông báo trong ứng dụng, lọc Chưa đọc / Tất cả, đánh dấu đã đọc từng cái hoặc tất cả 1-click.
- `templates/base.html`: Chuông thông báo 🔔 trên thanh điều hướng với badge đỏ số lượng chưa đọc thời gian thực.
- Routes logic: `GET /workspaces/{w}/dashboard`, `GET /tasks/mine/`, `GET /notifications/`, `POST /notifications/{id}/read/`, `POST /notifications/read-all/`.


### 13.4. Kết quả Kiểm thử Tự động B09 (19/19 tests Passed)
File kiểm thử: `core/tests_b09_dashboard_tasks_notifications.py`
1. `test_database_test_isolation`: Xác nhận test runner chạy trên DB test cách ly.
2. `test_dashboard_metrics_and_regions_for_owner`: Dashboard UI01 của Chủ hiển thị đúng 3 vùng, gói DRAFT chờ duyệt, bài chờ duyệt, bài bị chặn.
3. `test_dashboard_coordinator_scope_and_no_leak`: Điều phối viên chỉ xem gói phụ trách, không thấy gói bí mật hay bài bị chặn ngoài phạm vi.
4. `test_dashboard_member_scope_and_no_leak`: Member chỉ thấy nhiệm vụ READY của mình, không lộ count gói khác.
5. `test_dashboard_outsider_and_inactive_member_denied`: Outsider và Thành viên INACTIVE nhận HTTP 404 khi vào Dashboard.
6. `test_overdue_boundary_calculations`: Tính toán trễ hạn chính xác theo trạng thái công đoạn hiện tại; bài PUBLISHED/CANCELLED không bị tính trễ hạn.
7. `test_my_tasks_prioritization_and_filters`: Sắp xếp ưu tiên chuẩn (Blocker > Overdue > Due_at), bộ lọc trạng thái/vai trò hoạt động chính xác.
8. `test_my_tasks_after_b08_reassignment_and_deactivation`: Sau bàn giao B08, người nhận mới thấy việc, người cũ mất quyền thao tác.
9. `test_notification_events_generation_and_recipients`: Sinh thông báo chuẩn 5 sự kiện (duyệt kế hoạch, nộp bản nháp, yêu cầu sửa, báo chặn, gỡ chặn); không thông báo cho chính actor.
10. `test_notification_idempotency_no_duplicate`: Gửi lặp cùng idempotency event_id không tạo thông báo trùng lặp.
11. `test_notification_rollback_safety`: Lỗi nghiệp vụ gây rollback không để lại thông báo rác trong DB.
12. `test_notification_read_and_permissions`: Người dùng chỉ đọc thông báo của mình (người khác nhận 404); thành viên mất quyền nhận 403 và bị ẩn thông báo.
13. `test_empty_states_and_pagination`: Trạng thái rỗng hiển thị thông điệp thân thiện; phân trang hoạt động chuẩn xác.
14. `test_tasks_mine_redirect`: Route `GET /tasks/mine/` điều hướng chính xác về Việc của tôi ở workspace đang kích hoạt.
15. `test_handover_notification_on_member_deactivation`: Bàn giao việc khi thu hồi thành viên (AC11) tự động gửi thông báo bàn giao cho người thay thế.
16. `test_owner_request_changes_notification_recipients`: Chủ yêu cầu sửa trả về WRITING gửi thông báo cho writer; trả về EDITING gửi cho editor.
17. `test_notifications_filter_unread_and_mark_all_read`: Nút đánh dấu tất cả đã đọc và bộ lọc chưa đọc hoạt động hoàn hảo.
18. `test_my_tasks_pagination_over_20_items`: Phân trang 20 nhiệm vụ / trang theo quy định Spec.
19. `test_navbar_bell_unread_badge_rendering`: Navbar render chuông thông báo kèm badge đếm số lượng chưa đọc chính xác.

### 13.5. Phân tách Môi trường & Tình trạng Cổng Kiểm chứng (Gates)
| Môi trường CSDL | Cấu hình sử dụng | Kết quả kiểm thử B09 | Trạng thái cổng (Gate) |
|---|---|---|---|
| **SQLite (Test Runner cách ly)** | `core.test_settings` (SQLite in-memory test DB `test_suite_db.sqlite3`) | **19/19 B09 tests Passed** (Tổng suite: **180/180 tests Passed**) | **ĐẠT (VERIFIED)** — Toàn bộ Dashboard UI01, Việc của tôi UI06, hệ thống Thông báo, phân quyền ma trận đọc, chống N+1 và template rendering đạt 100%. |
| **PostgreSQL (Môi trường máy cục bộ)** | `core.postgres_test_settings` (yêu cầu `TEST_DATABASE_URL` kết nối máy chủ PG) | *Chưa chạy do máy trạm local hiện chưa cài đặt / bật dịch vụ PostgreSQL engine cục bộ (đã xác nhận cổng 5432 đóng).* | **CHỜ KẾT NỐI (PENDING PG RUNNER)** — Đã duy trì sẵn file cấu hình cách ly `core/postgres_test_settings.py` để chạy ngay khi có database PostgreSQL. |

---

## 12. Chi tiết thực hiện B08 (Đổi người phân công, Thu hồi thành viên & Ngoại lệ)

### 12.1. Mô hình Dữ liệu B08 (`apps/workspaces/models.py`)
- **`AssignmentRole` (Enum vai trò phân công):** `WRITE` ("Viết bài"), `EDIT` ("Biên tập"), `PUBLISH` ("Xuất bản"), `COORDINATOR` ("Điều phối gói").
- **`AssignmentHistory` (Bản ghi lịch sử bàn giao phân công - Spec mục 3.1, 3.2, 5 F07, 6.3, 7 UI05, 9, 10, 13 B08, AC11):**
  - Lưu trữ: `id` (UUID), `workspace`, `package`, `item` (nullable với gói), `task` (nullable nếu gói chưa duyệt), `role`, `previous_assignee`, `new_assignee`, `reassigned_by`, `reason` (bắt buộc, max 2.000 ký tự), `idempotency_key`, `created_at`.
  - Tính chất append-only bất biến: Override `save()` chặn sửa hoặc cập nhật bản ghi đã tồn tại.
  - Chỉ mục tìm kiếm: `idx_assign_ws_created`, `idx_assign_item_created`, `idx_assign_pkg_created`.
  - Migration: `apps/workspaces/migrations/0010_assignmenthistory.py`.
  - Quản trị: `apps/workspaces/admin.py` (`AssignmentHistoryAdmin`).

### 12.2. Domain Services B08 (`apps/workspaces/services.py`)
- **`reassign_item_assignment()` (Đổi người phân công bài viết):**
  - **Phân quyền chặt chẽ:** Chỉ Chủ workspace (`AccessRole.OWNER` toàn workspace) hoặc Điều phối viên được gán cho gói (`package.coordinator_membership` trong gói phụ trách). Thành viên thường (`MEMBER`), outsider hoặc tài khoản `INACTIVE` bị từ chối `PermissionDenied`.
  - **Ràng buộc đối tượng:** Người nhận mới phải thuộc cùng workspace, đang `ACTIVE`, và phải khác người đang chịu trách nhiệm hiện tại.
  - **Bảo vệ OCC 409 (AC10):** Xác thực `expected_row_version` với `locked_item.row_version` qua `select_for_update()`. Lệch trả `ConcurrencyConflictError` (HTTP 409).
  - **Chống trùng lặp (Idempotency):** Sử dụng `idempotency_key` để nhấp đôi không tạo bản ghi bàn giao trùng hay tăng row_version thừa.
  - **Đồng bộ nguyên tử ContentItem & Task (Spec 6.2):**
    - Cập nhật trường phân công trên `ContentItem` (`writer_membership` / `editor_membership` / `publisher_membership`).
    - Cập nhật `Task.assignee_membership` tương ứng.
    - **Bảo toàn tiến độ công việc:** Trạng thái Task (`WAITING`, `READY`, `IN_PROGRESS`, `DONE`, `CANCELLED`) được giữ nguyên, tuyệt đối không tự ý reset tiến độ.
  - **Bảo toàn tính bất biến & Blocker (Spec F07, AC12):**
    - Không làm thay đổi tác giả của `ContentVersion`, người quyết định `ReviewDecision`, người duyệt `ContentApproval`, hoặc người xuất bản `ContentPublication`.
    - Không tự tạo phiên bản, tự duyệt hoặc tự đăng bài.
    - Bài `BLOCKED` vẫn cho phép đổi người; cờ chặn (`blocked_reason`, `blocked_by`, `blocked_at`) được giữ nguyên 100%.
- **`deactivate_membership()` (Thu hồi thành viên có trách nhiệm mở — AC11):**
  - **Chỉ Chủ workspace có quyền thu hồi.**
  - **Bảo vệ Chủ (Single Owner guard):** Tuyệt đối không cho phép vô hiệu hóa Chủ workspace.
  - **Rà soát trách nhiệm mở:** Quét toàn bộ Task `WAITING`, `READY`, `IN_PROGRESS` của thành viên, các bài viết chưa kết thúc (không CANCELLED/PUBLISHED) được phân công, và các gói đang điều phối (`DRAFT`/`ACTIVE`).
  - **Bắt buộc phương án bàn giao hợp lệ (AC11):**
    - Nếu còn trách nhiệm mở mà không có `replacement_membership`, từ chối `ValidationError`, rollback toàn bộ, không vô hiệu hóa, không bàn giao một phần.
    - `replacement_membership` phải là thành viên `ACTIVE` cùng workspace hoặc chính Chủ workspace.
  - **Bàn giao nguyên tử trong một transaction (`@transaction.atomic`):**
    - Chuyển giao toàn bộ Task mở, ContentItem, Package sang người thay thế.
    - Ghi nhận `AssignmentHistory` cho từng trách nhiệm được bàn giao.
    - Chuyển thành viên sang `status = INACTIVE`.
  - **Hiệu lực tức thì:** Thành viên bị vô hiệu hóa lập tức bị từ chối truy cập workspace (404 Not Found) theo quy tắc tenant isolation.

### 12.3. Giao diện & Tương tác Người dùng (`views.py` & `templates/`)
- `ContentItemReassignView`: Xử lý POST đổi người phân công (`/assignments/`), trả 302 khi thành công, 400 khi lỗi dữ liệu, 409 khi xung đột OCC; giữ nguyên dữ liệu nhập trên form.
- `MemberDeactivateView`:
  - `GET`: Hiển thị tóm tắt danh sách nhiệm vụ mở, bài viết được phân công, gói điều phối, form chọn người thay thế và lý do (`member_deactivate.html`).
  - `POST`: Thực hiện bàn giao nguyên tử và vô hiệu hóa thành viên.
- `templates/workspaces/item_detail.html`:
  - Bổ sung form bàn giao phân công gọn gàng trong thẻ nhiệm vụ (chỉ hiển thị với Chủ / Điều phối).
  - Vẫn cho phép thao tác bàn giao khi bài viết đang bị `BLOCKED`.
  - Hiển thị danh sách lịch sử bàn giao phân công (`AssignmentHistory`) minh bạch theo quyền đọc.
- `templates/workspaces/workspace_members.html`: Nút "Vô hiệu" liên kết trực tiếp tới màn hình kiểm tra trách nhiệm và chọn người thay thế.
### 12.4. Kết quả Kiểm thử Tự động B08 (22/22 tests Passed)
- Bộ kiểm thử: `core/tests_b08_reassignment_deactivation.py`.
- Bao phủ 22 ca kiểm thử toàn diện:
  1. `test_reassign_write_role_synchronizes_content_item_and_task`: Bàn giao vai trò WRITE, đồng bộ Task và ContentItem, không reset status Task.
  2. `test_reassign_edit_and_publish_roles`: Bàn giao vai trò EDIT và PUBLISH, đồng bộ Task tương ứng.
  3. `test_reassign_by_package_coordinator_allowed_in_own_package`: Điều phối viên có quyền đổi người trong gói phụ trách (Spec 3.1).
  4. `test_reassign_coordinator_denied_in_other_package`: Điều phối viên bị từ chối 403 khi thao tác gói khác.
  5. `test_reassign_by_regular_member_denied`: Thành viên thường (writer/editor) bị từ chối 403.
  6. `test_reassign_outsider_and_inactive_actor_denied`: Outsider và Inactive actor bị từ chối theo Spec.
  7. `test_reassign_new_assignee_invalid_workspace_or_inactive_or_same_rejected`: Từ chối người nhận khác workspace, INACTIVE, hoặc trùng người hiện tại.
  8. `test_reassign_missing_reason_and_cancelled_item_rejected`: Từ chối khi thiếu lý do hoặc bài đã CANCELLED.
  9. `test_reassign_occ_conflict_409_ac10`: Lệch expected_row_version nhận HTTP 409 OCC, không ghi đè dữ liệu (AC10).
  10. `test_reassign_idempotency_ac10`: Nhấp đôi cùng idempotency_key trả về bản ghi cũ, không nhân bản (AC10).
  11. `test_reassign_preserves_historical_authors_versions_and_decisions`: Không sửa lịch sử tác giả phiên bản, review decision, approval hay publication.
  12. `test_reassign_preserves_blocker_state_ac12`: Bài BLOCKED vẫn đổi được người; cờ blocker giữ nguyên 100% (AC12).
  13. `test_deactivate_member_with_no_open_tasks_success`: Thành viên không có việc mở được vô hiệu hóa trực tiếp.
  14. `test_deactivate_member_with_open_tasks_without_replacement_rejected_ac11`: Thành viên có việc mở nhưng thiếu phương án bàn giao bị từ chối, không thu hồi một phần (AC11).
  15. `test_deactivate_member_with_open_tasks_reassigns_atomically_ac11`: Bàn giao nguyên tử toàn bộ việc mở và vô hiệu hóa thành viên (AC11).
  16. `test_deactivate_member_reassigns_to_owner`: Chủ workspace có thể tự tiếp quản trách nhiệm mở (Spec 3.2).
  17. `test_deactivate_member_reassigns_unstarted_draft_items_and_package_coord`: Bàn giao bài viết ở gói DRAFT và quyền điều phối gói (AC11).
  18. `test_deactivate_member_invalid_replacement_rejected`: Người thay thế INACTIVE, khác workspace, hoặc chính người bị thu hồi bị từ chối.
  19. `test_deactivate_owner_strictly_prevented`: Bảo vệ Single Owner, không cho phép vô hiệu hóa Chủ.
  20. `test_deactivated_member_loses_workspace_access_immediately`: Thành viên bị thu hồi lập tức bị từ chối truy cập (404 Not Found).
  21. `test_view_reassign_post_success_and_validations`: Kiểm thử View HTTP POST ContentItemReassignView (302, 400, 409).
  22. `test_view_member_deactivate_get_and_post`: Kiểm thử View HTTP MemberDeactivateView GET hiển thị việc mở & POST vô hiệu hóa.

### 12.5. Phân tách Môi trường & Tình trạng Cổng Kiểm chứng (Gates)
| Môi trường CSDL | Cấu hình sử dụng | Kết quả kiểm thử B08 | Trạng thái cổng (Gate) |
|---|---|---|---|
| **SQLite (Test Runner cách ly)** | `core.test_settings` (SQLite in-memory test DB `test_suite_db.sqlite3`) | **22/22 B08 tests Passed** (Tổng suite: **161/161 tests Passed**) | **ĐẠT (VERIFIED)** — Logic nghiệp vụ, phân quyền, validation, OCC, atomicity, idempotency và template rendering hoạt động chính xác 100%. |
| **PostgreSQL (Môi trường máy cục bộ)** | `core.postgres_test_settings` (yêu cầu `TEST_DATABASE_URL` kết nối máy chủ PG) | *Chưa chạy do máy trạm local hiện chưa cài đặt / bật dịch vụ PostgreSQL engine cục bộ (đã xác nhận cổng 5432 đóng).* | **CHỜ KẾT NỐI (PENDING PG RUNNER)** — Đã chuẩn bị sẵn file cấu hình cách ly `core/postgres_test_settings.py` để chạy ngay khi có database PostgreSQL. |




## 11. Chi tiết thực hiện B07 (Ghi nhận xuất bản & Hoàn thành gói)

### 11.1. Mô hình Dữ liệu B07 (`apps/workspaces/models.py`)
- **`ContentPublication` (Bản ghi xuất bản bài viết - Spec mục 5 F06, 6.1, 9, 13 B07, AC13, AC14):**
  - Lưu trữ: `id` (UUID), `workspace`, `item`, `version` (bản version_id cụ thể đã được duyệt), `approval` (bản phê duyệt có hiệu lực tương ứng), `url` (bắt buộc URL hợp lệ), `published_at` (thời điểm xuất bản thực tế), `recorded_by` (người xác nhận đăng), `recorded_at` (thời điểm ghi nhận).
  - SaaS ghi rõ: *"Đã đăng — do [người] xác nhận"* (không tuyên bố đã kiểm chứng tự động Facebook API).
  - Giữ lại bản ghi cũ trong DB khi bài viết được mở lại và xuất bản phiên bản mới.
  - Sắp xếp và chỉ mục: `ordering = ["-recorded_at"]`, `idx_pub_item_recorded` (`item`, `recorded_at`), `idx_pub_ws_recorded` (`workspace`, `recorded_at`).
  - Đăng ký và quản trị qua `apps/workspaces/admin.py` (`ContentPublicationAdmin`).
  - Migration: `apps/workspaces/migrations/0009_contentpublication.py`.

### 11.2. Domain Services B07 (`apps/workspaces/services.py`)
- `record_content_publication()`:
  - Phân quyền: Chỉ Người xuất bản được phân công (`item.publisher_membership`) hoặc Chủ workspace (`AccessRole.OWNER`) có quyền ghi nhận.
  - Kiểm tra trạng thái bài viết: Bắt buộc ở `READY_TO_PUBLISH`.
  - Kiểm tra phê duyệt: Bắt buộc có `ContentApproval` có hiệu lực (`invalidated_at is None`) gắn đúng `version` đã duyệt (AC13).
  - Chặn xuất bản khi bài bị `BLOCKED` (AC12).
  - Ràng buộc dữ liệu: URL bắt buộc hợp lệ (scheme + netloc), thời điểm đăng bắt buộc.
  - Optimistic Concurrency Control (OCC): Xác thực `expected_row_version` chống xung đột 409 (AC10).
  - Idempotency: Hỗ trợ `idempotency_key` chống double-click (AC13).
  - Chuyển `ContentItem.state` từ `READY_TO_PUBLISH` -> `PUBLISHED`, tăng `row_version`.
  - Cập nhật `TaskRole.PUBLISH` từ `READY` -> `DONE` (Spec 6.2).
  - Tự động đồng bộ trạng thái gói `_sync_package_status`: Nếu tất cả bài không hủy đã `PUBLISHED` -> gói tự động chuyển sang `COMPLETED` (Spec 6.2, AC14).
- `update_publication_metadata()`:
  - Chỉnh sửa nhầm URL hoặc thời điểm đăng thực tế (Spec F06, mục 10).
  - Bắt buộc có lý do sửa (`reason`) để lưu vết audit trail.
  - Không cho phép thay đổi `version_id`, `approval_id`, hay `item`.
- `_sync_package_status()`:
  - Tự động chuyển `ACTIVE` -> `COMPLETED` khi có ít nhất một bài không hủy và tất cả bài không hủy đã `PUBLISHED`.
  - Mở lại bài làm gói `COMPLETED` tự động trở lại `ACTIVE`.
  - Nếu tất cả bài bị hủy: không hiện hoàn thành (giữ nguyên trạng thái để Chủ xử lý hủy gói).

### 11.3. Giao diện Người dùng B07 (`templates/workspaces/`)
- `templates/workspaces/item_detail.html`:
  - Trạng thái `READY_TO_PUBLISH`: Hiển thị form ghi nhận xuất bản cho Người xuất bản/Chủ (URL, thời điểm đăng, CSRF, idempotency key, giữ dữ liệu form khi validation lỗi).
  - Trạng thái `PUBLISHED`: Hiển thị thông tin xuất bản hiện hành (Link bài viết, thời điểm đăng, người xác nhận). Cung cấp form sửa nhầm URL/thời điểm đăng kèm lý do (audit trail).
  - Lịch sử xuất bản: Hiển thị danh sách các lần xuất bản `publications` với nhãn bản đăng hiện hành.
- `templates/workspaces/package_detail.html`:
  - Hiển thị tiến độ xuất bản chuẩn xác: `x/y bài đã đăng` (Spec UI04, AC14).
  - Bài hủy được hiển thị riêng và loại trừ khỏi mẫu số tiến độ.

### 11.4. Bộ Kiểm thử B07 (`core/tests_b07_content_publication.py`)
- Gồm 18 ca kiểm thử chuyên sâu bao phủ toàn diện:
  1. `test_record_publication_success_publisher`: Người xuất bản được phân công ghi nhận thành công, sinh ContentPublication, chuyển Task PUBLISH -> DONE, bài chuyển PUBLISHED.
  2. `test_record_publication_success_owner`: Chủ workspace ghi nhận xuất bản thay mặt publisher.
  3. `test_record_publication_forbidden_writer_and_editor`: Writer và Editor không có quyền bị từ chối 403 PermissionDenied.
  4. `test_record_publication_blocked_item_rejected_ac12`: Bài bị chặn (BLOCKED) từ chối xuất bản; sau khi unblock thì xuất bản thành công (AC12).
  5. `test_record_publication_invalid_state_rejected`: Bài chưa đến trạng thái READY_TO_PUBLISH bị từ chối.
  6. `test_record_publication_no_active_approval_rejected_ac13`: Bài chưa có duyệt hoặc duyệt đã bị vô hiệu bị từ chối (AC13).
  7. `test_record_publication_missing_or_invalid_url_rejected_ac13`: URL rỗng hoặc sai định dạng bị từ chối (AC13).
  8. `test_record_publication_missing_published_at_rejected`: Thiếu thời điểm đăng bị từ chối.
  9. `test_record_publication_idempotency_ac13`: Gửi lặp cùng idempotency_key trả về bản ghi cũ, không nhân bản (AC13).
  10. `test_record_publication_occ_conflict_409_ac10`: Lệch expected_row_version nhận lỗi 409 OCC (AC10).
  11. `test_reopen_and_republish_preserves_publication_history_spec_f06`: Bài đã đăng khi mở lại giữ nguyên lịch sử xuất bản cũ, xuất bản lần tiếp theo ghi nhận bản duyệt mới (Spec F06).
  12. `test_edit_publication_metadata_success`: Sửa nhầm URL/thời điểm đăng thành công, bảo toàn version/approval.
  13. `test_edit_publication_metadata_missing_reason_rejected`: Sửa metadata thiếu lý do bị từ chối.
  14. `test_package_completion_ac14_two_published_one_cancelled`: 2 bài đăng, 1 bài hủy -> gói hoàn thành 2/2 COMPLETED, hiện 1 bài hủy (AC14).
  15. `test_package_completion_ac14_all_three_cancelled_not_completed`: Cả 3 bài bị hủy -> gói không hiện hoàn thành (AC14).
  16. `test_package_reverts_to_active_on_reopen_spec_6_2`: Mở lại bài trong gói COMPLETED đưa gói về ACTIVE (Spec 6.2).
  17. `test_view_record_publication_http_post`: Kiểm thử View POST ghi nhận, redirect 302, validation 400 và OCC 409.
  18. `test_view_edit_publication_metadata_http_post`: Kiểm thử View POST sửa metadata thành công.

---

## 10. Chi tiết thực hiện B06 (Chủ duyệt, Mở lại & Vòng đời bài viết)

### 10.1. Mô hình Dữ liệu B06 (`apps/workspaces/models.py`)
- **`ContentApproval` (Bản ghi phê duyệt bài viết - Spec mục 6.1, 6.3, 9, 13 B06):**
  - Lưu: `item`, `workspace`, `version` (bản version_id cụ thể được duyệt), `approved_by` (Chủ workspace), `approved_at`, `invalidated_at` (thời điểm bị vô hiệu hóa), `invalidation_reason` (lý do mở lại/hủy bài), `idempotency_key`.
  - Property `is_active`: `invalidated_at is None`. Mỗi bài viết chỉ có tối đa một approval có hiệu lực (invalidated_at__isnull=True).
  - Chỉ mục tìm kiếm: `idx_appr_item_inval` (`item`, `invalidated_at`), `idx_appr_ws_approved` (`workspace`, `approved_at`).
- **Mở rộng `ReviewDecision`:**
  - Bổ sung các loại quyết định vòng đời: `APPROVE` (Chủ duyệt), `WITHDRAW_REVIEW` (Rút gửi duyệt), `REOPEN` (Mở lại bài viết), `CANCEL` (Hủy bài viết).
  - Duy trì tính chất append-only bất biến phục vụ audit trail.

### 10.2. Domain Services B06 (`apps/workspaces/services.py`)
- `owner_approve_item()`:
  - Chủ workspace phê duyệt bài viết từ trạng thái `OWNER_REVIEW`.
  - Kiểm tra quyền Chủ workspace (`AccessRole.OWNER`, ACTIVE membership).
  - Chặn duyệt nếu bài đang bị `BLOCKED` (AC12).
  - Kiểm tra Optimistic Concurrency Control `row_version` (AC10).
  - **Kiểm tra phiên bản cũ (AC07):** Nếu `expected_version_id` từ client khác với `latest_version_id` hiện hành của bài viết, lập tức trả về `ConcurrencyConflictError` (HTTP 409 Conflict), chặn duyệt nhầm bản cũ.
  - Vô hiệu hóa phê duyệt cũ (nếu có), tạo bản ghi `ContentApproval` mới gắn với `version_id` được chốt.
  - Chuyển trạng thái `ContentItem`: `OWNER_REVIEW` -> `READY_TO_PUBLISH`, cập nhật `approval_id`.
  - Chuyển nhiệm vụ `TaskRole.PUBLISH` sang `READY` để mở việc xuất bản (Spec 6.2).
  - Ghi nhận `ReviewDecision` append-only (`decision="APPROVE"`).
  - Chống nhấp đôi qua `idempotency_key`.
- `owner_request_changes()`:
  - Chủ workspace yêu cầu sửa lại kèm chỉ định bước trả về (`WRITING` hoặc `EDITING`). Bắt buộc có lý do sửa cụ thể.
  - Nếu trả về `WRITING`: bài viết chuyển `WRITING`; Task `WRITE` sang `READY`; Task `EDIT` về `WAITING`.
  - Nếu trả về `EDITING`: bài viết chuyển `EDITING`; Task `EDIT` sang `READY`.
  - Ghi nhận `ReviewDecision` append-only.
- `withdraw_review()`:
  - Người biên tập được phân công hoặc Chủ workspace rút bài khỏi hàng đợi chờ duyệt.
  - Chuyển `OWNER_REVIEW` -> `EDITING`; Task `EDIT` mở lại `READY`. Bắt buộc có lý do rút bài.
- `reopen_content_item()`:
  - Chủ workspace mở lại bài viết từ `READY_TO_PUBLISH` hoặc `PUBLISHED` (AC09). Bắt buộc có lý do mở lại.
  - **Vô hiệu hóa toàn bộ `ContentApproval` hiện tại của bài viết (AC09):** ghi nhận `invalidated_at` và `invalidation_reason`.
  - Xóa `approval_id` trên `ContentItem` về `None`.
  - Chuyển trạng thái `ContentItem` về `EDITING`; Task `EDIT` sang `READY`; Task `PUBLISH` về `WAITING`.
  - Tự động đồng bộ trạng thái Gói nội dung: Nếu gói đang `COMPLETED` sẽ chuyển lại thành `ACTIVE` (Spec 6.2).
- `cancel_content_item()`:
  - Chủ workspace hủy bài viết có lý do. Không cho phép hủy bài đã `PUBLISHED` hoặc `CANCELLED`.
  - Thu hồi duyệt nếu bài đang ở `READY_TO_PUBLISH`.
  - Chuyển tất cả nhiệm vụ chưa hoàn thành sang `CANCELLED`.
- `block_content_item()` & `unblock_content_item()`:
  - Đặt và gỡ cờ chặn (Blocker) theo Spec F07 & AC12; lưu vết lý do, người báo chặn, thời điểm và ghi chú giải quyết.

### 10.3. Giao diện & Form tác nghiệp B06 (`templates/workspaces/item_detail.html` - UI05)
- Bổ sung các khu vực thao tác cho Chủ workspace khi bài ở `OWNER_REVIEW`: Phê duyệt phiên bản chốt (kèm cảnh báo xác nhận), Yêu cầu sửa lại (chọn trả về viết hoặc biên tập).
- Nút rút bài khỏi chờ duyệt (Biên tập hoặc Chủ).
- Nút mở lại bài viết (Thu hồi duyệt) khi bài ở `READY_TO_PUBLISH` hoặc `PUBLISHED`.
- Nút hủy bài viết dành cho Chủ workspace.
- Bảng thông báo Blocker và nút gỡ chặn trực tiếp khi người có trách nhiệm xử lý xong.
- Khối lịch sử phê duyệt của Chủ (`approvals`): hiển thị chi tiết trạng thái hiệu lực / vô hiệu hóa, thời điểm và lý do.

### 10.4. Kiểm thử B06 (`core/tests_b06_approval_lifecycle.py`)
- Bộ kiểm thử gồm 11 tests toàn diện:
  1. `test_owner_approve_success_lifecycle`: Luồng duyệt chuẩn thành công, sinh ContentApproval, mở Task PUBLISH.
  2. `test_stale_version_approval_rejected_ac07`: Duyệt trên phiên bản cũ trả về HTTP 409 (AC07).
  3. `test_reopen_invalidates_approval_and_transitions_ac09`: Mở lại bài viết vô hiệu hóa approval, xóa approval_id, chuyển EDITING (AC09).
  4. `test_owner_request_changes_to_writing_and_editing`: Chủ trả về viết hoặc biên tập, cập nhật Task đúng quy tắc.
  5. `test_withdraw_review_lifecycle`: Rút gửi duyệt trả bài về biên tập.
  6. `test_cancel_content_item_lifecycle`: Hủy bài viết và thu hồi duyệt nếu đang chờ đăng.
  7. `test_blocked_item_lifecycle_ac12`: Quản lý cờ chặn blocker, từ chối duyệt khi bị chặn, cho phép gỡ chặn (AC12).
  8. `test_permission_matrix_and_tenant_isolation`: Chặn thành viên duyệt/mở lại (403), chặn outsider và inactive member (404).
  9. `test_optimistic_concurrency_control_409_ac10`: Xung đột row_version trả về 409 OCC (AC10).
  10. `test_idempotency_double_click_protection`: Chống double-click bằng idempotency key.
  11. `test_package_status_sync_on_reopen_spec_6_2`: Mở lại bài làm gói COMPLETED chuyển lại ACTIVE.

---

## 9. Chi tiết thực hiện B05 (Phiên bản & Luồng viết/biên tập)

### 9.1. Mô hình Dữ liệu B05 (`apps/workspaces/models.py`)
- Bổ sung trường `draft_text` (TextField) và `draft_reference_urls` (JSONField) vào `ContentItem` để người viết lưu nháp an toàn mà không cần tạo ContentVersion (AC12).
- **`ContentVersion` (Phiên bản nội dung):**
  - Lưu: `item`, `workspace`, `version_no` (tự tăng tuần tự duy nhất trong bài viết), `text`, `reference_urls` (JSONField HTTPS), `source` (`MANUAL` hoặc `EXTERNAL_AI`), `author_membership`, `parent_version`, `idempotency_key`, `created_at`.
  - **Bất biến (Immutable):** Ghi đè `save()` chặn cập nhật bản ghi đã tồn tại.
  - Ràng buộc: `UniqueConstraint(fields=["item", "version_no"])`.
- **`ReviewDecision` (Quyết định biên tập/duyệt):**
  - Lưu: `item`, `workspace`, `version`, `decision` (`REQUEST_CHANGES` hoặc `SUBMIT_REVIEW`), `return_stage`, `reason`, `checklist` (JSONField), `actor_membership`, `idempotency_key`, `created_at`.
  - **Append-only:** Ghi đè `save()` chặn sửa bản ghi lịch sử đã tạo.

### 9.2. Domain Services B05 (`apps/workspaces/services.py`)
- `format_brief_for_copy()`: Tạo văn bản Brief chuẩn hóa để người viết sao chép 1-click sang AI riêng (ChatGPT/Claude/Gemini). Gồm mục tiêu, đối tượng, giọng văn, yêu cầu bài, điều tránh, định dạng đầu ra và yêu cầu bắt buộc đánh dấu `[CẦN XÁC MINH]`.
- `start_writing_task()`: Chuyển bài `TODO` -> `WRITING`, nhiệm vụ `TaskRole.WRITE` từ `READY` -> `IN_PROGRESS`.
- `save_draft_content()`: Cho phép lưu nháp; giữ nguyên nội dung khi gặp lỗi; cho phép lưu ngay cả khi bài bị `BLOCKED` (AC12); kiểm tra optimistic concurrency `row_version` (AC10).
- `submit_content_version()`:
  - Người viết nộp bản hoàn chỉnh cho biên tập viên.
  - Chặn nộp nếu bài đang bị `BLOCKED` (AC12) hoặc đang ở trạng thái `OWNER_REVIEW` (AC08).
  - Sinh `ContentVersion` bất biến với `version_no` tự tăng tuần tự.
  - Chuyển `ContentItem.state` từ `WRITING` -> `EDITING`.
  - Đồng bộ `TaskRole.WRITE` -> `DONE` và `TaskRole.EDIT` -> `READY`.
  - Hỗ trợ chống double-click qua `idempotency_key`.
- `create_editor_version()`: Biên tập viên chỉnh sửa và sinh phiên bản mới với `version_no` tăng tiếp, giữ nguyên vẹn phiên bản của người viết (AC06).
- `request_changes_decision()`:
  - Biên tập viên yêu cầu sửa có lý do bắt buộc.
  - Chuyển `ContentItem.state` từ `EDITING` -> `WRITING`.
  - Lưu bản ghi `ReviewDecision` append-only.
  - Mở lại `TaskRole.WRITE` thành `IN_PROGRESS`, đưa `TaskRole.EDIT` về `WAITING` (Spec 6.2, AC06).
- `submit_for_owner_review()`:
  - Biên tập viên hoàn tất 4 tiêu chí checklist (đúng brief, chính xác dữ liệu, giọng văn, CTA).
  - Chuyển `ContentItem.state` sang `OWNER_REVIEW`, `TaskRole.EDIT` -> `DONE`.

### 9.3. Giao diện & Trải nghiệm Người dùng B05
- `templates/workspaces/item_detail.html`: Màn hình tác nghiệp chi tiết bài viết (UI05) chia theo công đoạn, tích hợp nút sao chép brief 1-click, các form thao tác nộp bài/sửa bài/trả bài, lịch sử phiên bản và quyết định biên tập.
- `templates/workspaces/my_tasks.html`: Màn hình "Việc của tôi" (UI06) lọc theo trạng thái nhiệm vụ (READY, IN_PROGRESS, WAITING, DONE).

### 9.4. Kết quả Kiểm thử Tự động B05 (13/13 tests Passed)
- Kiểm thử `core/tests_b05_content_operations.py`:
  - Database test isolation.
  - Định dạng Brief sao chép sang AI riêng (F03).
  - Luồng hoàn chỉnh từ Viết bài đến Biên tập và Chủ duyệt.
  - Vòng lặp yêu cầu sửa có lý do (AC06) và giữ nguyên phiên bản cũ.
  - Kiểm tra checklist bắt buộc 4 mục khi nộp duyệt (F04).
  - Ma trận phân quyền: chặn người không có thẩm quyền / sai vai trò.
  - Cách ly tenant: Outsider và Inactive member nhận HTTP 404.
  - Chặn người viết nộp bài khi đang ở OWNER_REVIEW (AC08).
  - Xử lý bài bị chặn (AC12): cho phép lưu nháp, từ chối nộp bài.
  - Optimistic concurrency control 409 (AC10).
  - Chống double-click với idempotency key.
  - Kiểm tra HTTPS URLs tham khảo.
  - Màn hình Việc của tôi (UI06).
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

    11. Cạnh tranh khởi tạo BrandProfile lần đầu: Khóa Workspace và chuyển đổi `IntegrityError` thành `ConcurrencyConflictError` rõ ràng, đảm bảo duy nhất 1 hồ sơ được tạo, không sinh lỗi 500 ngoài ý muốn.
    12. Tính độc lập sâu của snapshot: Danh sách `source_urls` được copy độc lập dạng chuỗi, thao tác sửa đổi trên profile hoặc trên snapshot không làm biến đổi chéo.

---

## 8. Chi tiết thực hiện B04 (Gói, kế hoạch, phân công - Packages & Planning)

### 8.1. Mô hình dữ liệu B04 & Ràng buộc toàn vẹn CSDL (Spec mục 4, 6.2, 9 & 13)
- **Mô hình `Package` (`apps/workspaces/models.py`):**
  - Khóa chính: `id` kiểu `UUIDField` (`default=uuid.uuid4`, editable=False).
  - Khóa ngoại: `workspace` (ForeignKey), `coordinator_membership` (ForeignKey on_delete=PROTECT).
  - Các trường: `name` (1–150), `objective` (1–3.000), `channel` ("FACEBOOK"), `start_date`, `end_date`, `status` (`DRAFT`, `ACTIVE`, `COMPLETED`, `CANCELLED`), `plan_revision` (tăng khi sửa scope sau duyệt), `brand_snapshot` (JSONField), `row_version` (PositiveIntegerField OCC).
- **Mô hình `PlanApproval`:** Lưu `plan_revision`, `immutable_plan_snapshot`, `owner`, `approved_at`, và `idempotency_key` (chống nhấp đôi AC05).
- **Mô hình `ContentItem`:** Thuộc `workspace` và `package` (tối đa 50 bài/gói). Chứa `title` (1–200), `brief` (1–5.000), `cta` (<=500), `state` (`TODO`, `WRITING`, `EDITING`, `OWNER_REVIEW`, `READY_TO_PUBLISH`, `PUBLISHED`, `CANCELLED`). Hạn định: `writing_deadline <= editing_deadline <= review_deadline <= planned_publish_at`. Phân công 3 vai trò: `writer_membership`, `editor_membership`, `publisher_membership` (phải cùng workspace và ACTIVE).
- **Mô hình `Task`:** 3 nhiệm vụ `WRITE`, `EDIT`, `PUBLISH` trên mỗi bài (`UniqueConstraint(item, role)`). Trạng thái khởi tạo khi duyệt: WRITE: READY, EDIT & PUBLISH: WAITING.
- **Migration:** `workspaces.0004_package_contentitem_planapproval_task_and_more` áp dụng thành công.
### 8.2. Service Layer & Giao dịch Nguyên tử
- `create_package()`: Chủ workspace tạo gói, chỉ định người điều phối thuộc cùng workspace (ACTIVE).
- `update_package()`: Chỉnh sửa thông tin gói, kiểm tra optimistic concurrency `row_version`. Nếu gói đã ACTIVE, tăng `plan_revision`.
- `add_content_item()`: Chủ hoặc Người điều phối thêm bài vào gói DRAFT; kiểm tra giới hạn 50 bài, kiểm tra thứ tự deadline và quan hệ workspace.
- `update_content_item()`: Sửa bài viết; kiểm tra `row_version`; nếu gói đã ACTIVE chỉ Chủ mới được sửa và tự động cập nhật lại thời hạn/người của các `Task` tương ứng.
- `approve_plan()`: Duyệt kế hoạch nguyên tử:
  - Khóa dòng package bằng `select_for_update()`.
  - Chống nhấp đôi qua `idempotency_key` (AC05): Nếu key đã tồn tại, trả về kết quả cũ, không sinh thêm snapshot hay task.
  - Kiểm tra điều kiện tiên quyết: kế hoạch phải có ít nhất 1 bài viết, các thành viên được phân công phải đang ACTIVE, hạn bài hợp lệ.
  - Lưu snapshot thương hiệu bất biến vào `package.brand_snapshot` (AC15).
  - Lưu snapshot kế hoạch bất biến vào `PlanApproval.immutable_plan_snapshot`.
  - Chuyển `package.status` từ `DRAFT` sang `ACTIVE`.
  - Tự động sinh bộ 3 `Task` (WRITE/EDIT/PUBLISH) cho mỗi bài viết.

### 8.3. Ma trận Phân quyền B04 & Giao diện Người dùng
- **Phân quyền Backend:**
  - `PackageListView`: Xem danh sách gói trong workspace (Chủ và Thành viên).
  - `PackageCreateView` & `PackageUpdateView`: Chỉ Chủ workspace có quyền tạo/sửa gói (Thành viên nhận HTTP 403 Forbidden).
  - `PackageApprovePlanView`: Chỉ Chủ workspace có quyền duyệt kế hoạch (AC03).
  - `ContentItemCreateView` & `ContentItemUpdateView`: Khi gói DRAFT, Chủ và Người điều phối được thêm/sửa; khi gói ACTIVE, chỉ Chủ mới được sửa bài.
  - Người ngoài workspace (OUTSIDER) và thành viên bị vô hiệu hóa (INACTIVE) nhận ngay **HTTP 404 Not Found**.
- **Giao diện Templates:**
  - `package_list.html`: Danh sách gói, lọc badge trạng thái, thẻ bài viết, empty state.
  - `package_create.html` & `package_edit.html`: Form tạo và sửa gói, giữ lại nội dung khi lỗi validation, cảnh báo lỗi xung đột phiên bản 409.
  - `package_detail.html`: Kế hoạch chi tiết, mục tiêu chiến dịch, danh sách bài viết kèm 3 người phân công và 4 mốc thời hạn, nút phê duyệt kế hoạch cho Chủ có xác nhận và idempotency key.
  - `item_create.html` & `item_edit.html`: Form thêm/sửa bài viết với widget date/time, phân công 3 vị trí.
  - Tích hợp nút điều hướng "📦 Kế hoạch & Gói bài" trên trang chi tiết Workspace (`workspace_detail.html`).

### 8.4. Kết quả Kiểm thử Tự động B04 (10/10 tests Passed)
- Kiểm thử `core/tests_b04_packages_planning.py`:
  1. `test_database_test_isolation`: Test runner chạy trên database test độc lập (`test_postgres`).
  2. `test_create_package_success_and_validations`: Tạo gói thành công; chặn ngày kết thúc trước ngày bắt đầu.
  3. `test_create_content_items_and_deadline_sequence_validation`: Thêm bài hợp lệ; chặn hạn sai thứ tự (viết > biên tập) và hạn vượt ngoài khoảng thời gian của gói (AC04).
  4. `test_approve_plan_full_lifecycle_and_ac04`: Duyệt kế hoạch, lưu snapshot, chuyển DRAFT -> ACTIVE, sinh đúng 3 nhiệm vụ/bài với trạng thái WRITE: READY, EDIT/PUBLISH: WAITING.
  5. `test_approve_plan_idempotency_double_click_protection_ac05`: Chống nhấp đôi với idempotency key; không sinh dư thừa task hoặc snapshot (AC05).
  6. `test_brand_snapshot_isolation_after_plan_approval_ac15`: Sửa hồ sơ thương hiệu sau khi duyệt không làm thay đổi snapshot gói đã chốt (AC15).
  7. `test_tenant_isolation_cannot_assign_or_access_cross_workspace`: Chặn gán thành viên workspace khác; chặn người ngoài và Chủ workspace khác truy cập (HTTP 404).
  8. `test_optimistic_concurrency_control_on_package_and_items`: Xung đột phiên bản đồng thời trả về HTTP 409 ConcurrencyConflictError (AC10).
  9. `test_permission_matrix_and_member_role_checks`: Ma trận phân quyền: Thành viên bị chặn tạo gói/duyệt gói (403 - AC03); Điều phối được thêm bài ở DRAFT nhưng bị chặn sửa khi ACTIVE (403); Thành viên INACTIVE nhận 404.
  10. `test_form_validation_and_input_retention`: Form trả về 400 khi thiếu trường và giữ nguyên dữ liệu đã nhập.


