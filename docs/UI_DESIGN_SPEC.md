# UI Design Specification — ContentOps Hub (APAG Modernized)

## 1. Tổng Quan Thiết Kế & Nguyên Tắc Hệ Thống (Design Foundation)
Bộ nhận diện giao diện dựa trên 10 màn hình chuẩn từ Figma (`design/contentops-ui/SCREEN/*.png`) theo phong cách APAG hiện đại hóa:
- **Brand Archetype**: Chuyên nghiệp, sạch sẽ, phẳng tinh tế, độ tương phản cao, tập trung vào thao tác tác nghiệp (editorial & workflow-driven).
- **Gam màu chủ đạo (Color Palette)**:
  - `Primary / Brand`: `#1877F2` (Electric / Modern Royal Blue), Hover: `#1464cc`
  - `Brand Accent / Logo Hub`: `#1877F2`
  - `Text Primary`: `#0F172A` (Slate 900)
  - `Text Secondary / Muted`: `#64748B` (Slate 500)
  - `Background System / App Canvas`: `#F4F7FB` (Light airy blue-gray canvas)
  - `Card / Surface Background`: `#FFFFFF` (Pure white)
  - `Border / Divider`: `#E2E8F0` hoặc `#EEF2F6`
  - `Status Tokens`:
    - *Success / Hoàn thành*: Text `#15803D`, BG `#DCFCE7`, Icon `#22C55E`
    - *Warning / Sắp hạn / Chờ duyệt*: Text `#B45309`, BG `#FEF3C7`, Icon `#F59E0B`
    - *Danger / Quá hạn / Bị chặn*: Text `#B91C1C`, BG `#FEE2E2`, Icon `#EF4444`
    - *Draft / Nháp / Info*: Text `#4338CA`, BG `#EEF2FF`, Icon `#6366F1`
    - *Badge Facebook / Kênh*: Text `#1D4ED8`, BG `#DBEAFE`
    - *Priority High / Cao*: Text `#BE123C`, BG `#FFE4E6`
    - *Priority Medium / TB*: Text `#B45309`, BG `#FEF3C7`
    - *Priority Low / Thấp*: Text `#047857`, BG `#D1FAE5`
- **Typography**:
  - `Font-family`: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif.
  - `Page Title (H1)`: 24px - 28px, Font-weight: 800, Letter-spacing: -0.02em, Text Transform: UPPERCASE.
  - `Section / Subtitle`: 14px - 15px, Font-weight: 400, Color: `#64748B`.
  - `Card Header / Section Heading`: 16px - 18px, Font-weight: 700.
  - `Body / Metric Numbers`: 28px - 32px cho số KPI (Font-weight: 800), 14px cho dữ liệu bảng/danh sách.
- **Bố cục & Spacing (Layout & Grid)**:
  - `Sidebar Navigation`: Cố định 240px bên trái, nền `#FFFFFF`, border-right `#EEF2F6`. Active link bo tròn pill (`border-radius: 12px`), nền `#EEF4FF`, chữ `#1877F2`, icon đồng màu.
  - `Top Header`: Chiều cao 64px - 72px, thanh tìm kiếm bo tròn pill (`border-radius: 9999px`) với icon search xám, khu vực phải có icon Lịch, Chuông thông báo (kèm badge đếm đỏ), Tin nhắn, và User Profile Avatar/Role.
  - `Main Content Area`: Padding 24px - 32px, max-width co giãn linh hoạt 1400px, responsive co về 1 cột trên Tablet/Mobile.
  - `Border Radius System`: Buttons/Tags: 8px-10px / 9999px pill; Cards/Panels: 16px; Inputs: 10px.
  - `Box Shadows`: Mềm nhẹ `box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04), 0 4px 12px rgba(15, 23, 42, 0.03)`.

## 2. Bảng Đối Soát Màn Hình Mockup Figma vs Cấu Trúc Django Hiện Có

| STT | Tên ảnh Mockup (Figma) | Mô tả & Thành phần UI | Template & View Django mục tiêu | Lưu ý Guardrails (Giữ nguyên nghiệp vụ) |
|---|---|---|---|---|
| 1 | `01 Login.png` | Màn hình 2 cột: Cột trái minh họa hero card xanh, cột phải Form đăng nhập (Email/User, Mật khẩu, Checkbox duy trì, Button Blue) | `templates/auth/login.html` (`apps/accounts/`) | Giữ nguyên POST `/auth/login/`, CSRF token, thông báo lỗi field. |
| 2 | `Dashboard.png` | 3 Metric Cards trên đầu + Grid 6 thẻ Dịch vụ chính + 2 Cột dưới (Hạn sắp tới / Hoạt động gần đây) | `templates/workspaces/workspace_detail.html` | Giữ nguyên 3 vùng nghiệp vụ B09 từ `get_workspace_dashboard_data`. |
| 3 | `Gói Content.png` | 3 Metric Cards + Thanh lọc trạng thái/tìm kiếm + Nút "+ Tạo gói content" + Bảng danh sách gói | `templates/workspaces/package_list.html` | Giữ nguyên link xem chi tiết gói, phân quyền OWNER/COORDINATOR. |
| 4 | `Công việc.png` | 4 Metric Cards + Bộ lọc + Board công việc theo 4 cột trạng thái: Cần làm, Đang viết, Chờ duyệt, Hoàn thành | `templates/workspaces/my_tasks.html` (Việc của tôi UI06) | Tương thích dữ liệu nhiệm vụ Task: READY, IN_PROGRESS, WAITING, DONE; badge kênh, ưu tiên. |
| 5 | `Lịch đăng nội dung.png` | Thanh điều hướng tháng + Filter Kênh + Nút "+ Tạo lịch đăng" + Grid Lịch tháng + Panel bên phải "Sự kiện sắp tới" | `templates/workspaces/package_detail.html` (Section Lịch) | Hiển thị bài viết theo kế hoạch xuất bản `planned_publish_at`. |
| 6 | `Duyệt bài.png` | Giao diện 2 cột: Cột trái danh sách bài "Chờ duyệt", Cột phải Chi tiết bài viết đang duyệt kèm nút "Yêu cầu sửa" & "Phê duyệt" | `templates/workspaces/item_detail.html` (UI05) | Giữ nguyên logic form phê duyệt của Chủ workspace (`item_owner_approve`, `item_owner_request_changes`). |
| 7 | `Thành viên.png` | 3 Metric Cards + Lọc Vai trò / Trạng thái + Nút "+ Mời thành viên" + Bảng thành viên kèm cột hành động | `templates/workspaces/workspace_members.html` | Giữ nguyên form mời thành viên, danh sách lời mời chờ, trạng thái ACTIVE/DEACTIVATED. |
| 8 | `Thông báo.png` | Tabs lọc (Tất cả, Chưa đọc, Nhắc hạn, Hệ thống) + Nút "Đánh dấu đã đọc" + Danh sách card thông báo có icon màu | `templates/workspaces/notifications.html` | Kết nối `NotificationListView`, nút mark_all_read, lọc `unread=1`. |
| 9 | `Báo cáo.png` | 4 Metric Cards + Biểu đồ cột sản lượng tuần + Tiến độ thanh % theo gói + Tổng hợp kết quả vận hành | `templates/workspaces/workspace_detail.html` (Tab/Section Báo cáo) | Dựa trên stats có thật: tổng bài xuất bản, tỉ lệ hoàn thành; không sinh fake API. |
| 10 | `Cài đặt.png` | Form thông tin Workspace: Tên, Email, SĐT, Múi giờ, Địa chỉ, Mô tả, Logo thương hiệu + Tùy chọn hệ thống + Nút "Lưu thay đổi" | `templates/workspaces/workspace_edit.html` & `brand_profile.html` | Giữ nguyên `WorkspaceUpdateForm`, `BrandProfileForm`, xử lý quyền OWNER. |

## 3. Hệ Thống Component Tái Sử Dụng & Kế Hoạch Triển Khai
1. **Layout Wrapper (`templates/base_app.html`)**: Layout nội bộ có Sidebar (240px cố định) + Topbar (Search pill, Notification bell đếm số, user avatar).
2. **Inline SVG Icon System (Lucide Design)**: Icon inline SVG gọn nhẹ, sắc nét, không dùng thư viện ngoài.
3. **Metric Stat Card Component**: `.stat-card-modern` chuẩn hóa icon box, số KPI to bản và nhãn chú thích.
4. **Data Table Component**: `.table-modern` viền mỏng mượt mà, badge trạng thái bo tròn.
5. **Kế hoạch triển khai (Roadmap)**:
   - **Giai đoạn 1**: Thiết lập Design System Tokens & Base Layout (`base_app.html`, `app.css`).
   - **Giai đoạn 2**: Triển khai Màn hình Auth (`01 Login.png`).
   - **Giai đoạn 3**: Triển khai Màn hình Dashboard, Gói Content, Việc của tôi (`Dashboard.png`, `Gói Content.png`, `Công việc.png`).
   - **Giai đoạn 4**: Triển khai Màn hình Duyệt bài, Thành viên, Thông báo, Cài đặt (`Duyệt bài.png`, `Thành viên.png`, `Thông báo.png`, `Cài đặt.png`).
   - **Giai đoạn 5**: Kiểm thử tự động hồi quy và kiểm tra responsive 390px Mobile & 1440px Desktop.
