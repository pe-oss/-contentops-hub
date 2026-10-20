# TASK HANDOFF: UX Updates — ContentOps Hub

## 1. Mục tiêu của task
Triển khai toàn diện 3 nhóm cập nhật trải nghiệm người dùng (UX) trên ContentOps Hub tại branch `fix/ux-navigation-packages-notifications`:
- **Nhóm 1 — Điều hướng & Tổng quan**:
  - Tách lịch thành trang độc lập `/<workspace_id>/calendar/` với lưới tháng (Planned Publishing) chuyển đổi timezone workspace và lọc quyền hạn.
  - Tối ưu header tổng quan workspace: dọn dẹp các nút điều hướng ngang trùng lặp, thêm tiêu đề rõ ràng `Vùng 2 — Bị chặn / Trễ hạn`.
  - Đồng bộ sub-navigation hai tab (`Thông tin workspace` / `Hồ sơ thương hiệu`) trên cả trang chỉnh sửa workspace và hồ sơ thương hiệu.
- **Nhóm 2 — Form tạo & sửa gói content**:
  - Tái cấu trúc form (`package_create.html`, `package_edit.html`) theo 3 nhóm rõ ràng: (1) Thông tin gói, (2) Thời gian thực hiện (2 cột desktop), (3) Người phụ trách.
  - Đồng bộ typography, input, textarea, select, border, focus state, min-height cho textarea mục tiêu.
  - Hiển thị timeline các bước tiếp theo: `Tạo gói nháp → Thêm bài / Phân công → Chủ duyệt kế hoạch`.
  - Cập nhật nhãn nút hành động phù hợp (`Tạo gói nháp`, `Hủy`, `Lưu thay đổi`).
- **Nhóm 3 — Chuông thông báo & popover**:
  - Chuông thông báo góc trên bên phải với badge đếm số lượng chưa đọc.
  - Popover thông báo danh sách xem nhanh, phân loại và đánh dấu đã đọc.

---

## 2. Những thay đổi đã hoàn thành
- **Nhóm 1 (ĐÃ HOÀN TẤT VÀ COMMIT)**:
  - Commit SHA: `8608928` (`fix(ux): implement calendar view, streamline overview navigation, and unify settings`).
  - View `WorkspaceCalendarView` tại `apps/workspaces/views.py`: tính toán ranh giới tháng dựa trên `workspace.timezone` (`zoneinfo.ZoneInfo`), lọc bài viết theo scope quyền (Owner / Coordinator / Member).
  - Template `templates/workspaces/calendar.html`: lưới 7 cột ngày trong tuần, hiển thị bài viết theo ngày dự kiến xuất bản, badge trạng thái, liên kết xem chi tiết, và bộ điều hướng tháng trước/sau.
  - Route `<uuid:workspace_id>/calendar/` (`workspaces:calendar`).
  - Cập nhật tất cả điểm truy cập lịch (sidebar, topbar, dashboard service card) trỏ trực tiếp đến `workspaces:calendar` với active state chuẩn xác.
  - Loại bỏ các nút điều hướng ngang dư thừa ở `workspace_detail.html` nhưng giữ nguyên bối cảnh tên/kế hoạch của workspace.
  - Thêm header định danh `Vùng 2 — Bị chặn / Trễ hạn` ở `workspace_detail.html`.
  - Thêm navigation tab đôi thống nhất giữa `workspace_edit.html` và `brand_profile.html`.
  - Thêm mục menu sidebar cho Brand Profile.
  - Tạo bộ test tự động `core/tests_ux_group1_navigation.py` (4 tests) kiểm tra toàn bộ luồng Nhóm 1 và pass 100%.

- **Nhóm 2 (ĐÃ HOÀN TẤT VÀ COMMIT)**:
  - Commit SHA: `2e7a177` (`fix(ux): redesign package creation and edit forms into structured groups`).
  - Cập nhật form `PackageForm`, `package_create.html`, và `package_edit.html` thành 3 nhóm rõ ràng (Thông tin gói, Thời gian thực hiện, Người phụ trách), hiển thị quy trình 3 bước trực quan, responsive 2 cột desktop và 1 cột mobile.
  - Tạo bộ test tự động `core/tests_ux_group2_packages.py` (6 tests) kiểm tra toàn bộ form, indicator, validation ngày tháng, phân quyền và responsive CSS.

- **Nhóm 3 (ĐÃ HOÀN TẤT VÀ SẴN SÀNG COMMIT)**:
  - Tách chức năng thông báo khỏi menu sidebar (`templates/includes/sidebar.html`), nâng cấp chuông trên `topbar.html` thành popover dropdown hoàn chỉnh.
  - Hỗ trợ AJAX JSON cho `NotificationListView` (`format=json` hoặc request header), `NotificationReadView`, và `NotificationReadAllView` trong `apps/workspaces/views.py`.
  - Viết module frontend `static/js/notifications.js` quản lý mở/đóng dropdown ngoài màn hình, tab chuyển đổi Tất cả/Chưa đọc, tải thêm phân trang (10 item/trang), đánh dấu đã đọc (click vào item hoặc nút Đánh dấu tất cả), cập nhật badge realtime.
  - Tạo bộ test tự động `core/tests_ux_group3_notifications.py` (7 tests) kiểm tra toàn diện API, filter chưa đọc, phân trang, mark read/read all, phân quyền tenant isolation, và responsive CSS nhỏ hơn 480px.

---

## 3. Danh sách file đã sửa
### Đã commit trong Nhóm 1 (commit `8608928`):
1. `apps/workspaces/urls.py`
2. `apps/workspaces/views.py`
3. `templates/includes/sidebar.html`
4. `templates/includes/topbar.html`
5. `templates/workspaces/brand_profile.html`
6. `templates/workspaces/dashboard_services_grid.html`
7. `templates/workspaces/workspace_detail.html`
8. `templates/workspaces/workspace_edit.html`
9. `templates/workspaces/calendar.html` (tạo mới)
10. `core/tests_ux_group1_navigation.py` (tạo mới)

### Đã commit trong Nhóm 2 (commit `2e7a177`):
1. `apps/workspaces/forms.py`
2. `static/css/app.css`
3. `templates/workspaces/package_create.html`
4. `templates/workspaces/package_edit.html`
5. `core/tests_ux_group2_packages.py` (tạo mới)

### Đang chuẩn bị commit trong Nhóm 3:
1. `apps/workspaces/views.py` (hỗ trợ AJAX/JSON API cho notifications)
2. `core/test_settings.py` (cấu hình StaticFilesStorage cho môi trường test)
3. `static/css/app.css` (bổ sung popover dropdown styles & mobile responsive)
4. `static/js/notifications.js` (module dropdown popover)
5. `templates/base.html` (nhúng notifications.js)
6. `templates/includes/sidebar.html` (xóa mục menu Thông báo)
7. `templates/includes/topbar.html` (cấu trúc chuông popover dropdown)
8. `core/tests_ux_group3_notifications.py` (bộ 7 bài test Nhóm 3)
9. `TASK_HANDOFF.md`

---

## 4. Tình trạng và Kết quả kiểm thử
- **100% PASS**: Tất cả test suites liên quan đều vượt qua:
  - `core.tests_ux_group1_navigation`: 4/4 pass
  - `core.tests_ux_group2_packages`: 6/6 pass
  - `core.tests_ux_group3_notifications`: 7/7 pass
  - `core.tests_b09_dashboard_tasks_notifications`: 20/20 pass
  - Tổng cộng 37/37 tests pass không có bất kỳ cảnh báo hay lỗi hồi quy nào.
