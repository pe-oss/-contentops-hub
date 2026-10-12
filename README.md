# ContentOps Hub (SaaS Boilerplate)

Boilerplate nền tảng Django phục vụ dự án ContentOps Hub, tích hợp sẵn xác thực người dùng, bảng điều khiển và cấu hình thanh toán.

## 1. Yêu cầu hệ thống
- Python 3.10+
- Git

## 2. Thiết lập môi trường

### Khởi tạo Virtual Environment
Trên Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Trên macOS / Linux:
```bash
python3 -m venv .venv
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
- Mặc định chạy local sử dụng SQLite (`DATABASE_URL=` để trống).
- Đặt `SECRET_KEY` riêng cho môi trường local.
- Cập nhật `ALLOWED_HOSTS=localhost,127.0.0.1`.

## 4. Chạy Migration & Kiểm tra
```bash
python manage.py check
python manage.py migrate
```

## 5. Khởi động ứng dụng Local
```bash
python manage.py runserver 127.0.0.1:8000
```
Truy cập ứng dụng tại: `http://127.0.0.1:8000/`

## 6. Trạng thái và giới hạn kiểm thử
- **Đã kiểm thử đạt:**
  - Luồng xác thực tài khoản: Đăng ký, đăng nhập (bằng username hoặc email), đăng xuất, đổi mật khẩu.
  - Phân quyền & truy cập Dashboard cho người dùng ẩn danh và người dùng đã xác thực.
  - Khả năng hiển thị giao diện trên Desktop và màn hình thiết bị di động (responsive qua CSS media queries).
- **Giới hạn hiện tại:**
  - Chưa gọi cổng thanh toán thực tế (PayOS / SePay) và chưa kích hoạt webhook thật.
  - Chưa gửi email hay thông báo Telegram thật.
  - Chưa triển khai các nghiệp vụ tính năng Content (Spec B00).
