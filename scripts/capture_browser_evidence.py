"""
Kịch bản tự động chụp ảnh bằng chứng trình duyệt thực tế (Milestone B10 & Spec AC16).
Sử dụng Google Chrome Headless để kiểm chứng bố cục hiển thị trên:
1. Màn hình di động 390px (390 x 844 px - Viewport iPhone chuẩn)
2. Màn hình máy tính Desktop 1280px (1280 x 800 px)
"""
import os
import sys
import time
import subprocess
import urllib.request
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ["DJANGO_SETTINGS_MODULE"] = "core.settings"
os.environ["SCREENSHOT_MODE"] = "True"

import django
django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.workspaces.models import (
    Workspace,
    Membership,
    BrandProfile,
    Package,
    ContentItem,
    ContentVersion,
    Task,
    Notification,
)

User = get_user_model()
CHROME_BIN = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SCREENSHOT_DIR = BASE_DIR / "docs" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


from apps.workspaces.services import create_workspace_with_owner


def seed_data():
    owner, _ = User.objects.get_or_create(username="owner_b10", defaults={"email": "owner_b10@example.com"})
    freelancer, _ = User.objects.get_or_create(username="freelancer_b10", defaults={"email": "freelancer_b10@example.com"})

    ws = Workspace.objects.filter(name="Trung tâm Anh ngữ mẫu B10").first()
    if not ws:
        ws = create_workspace_with_owner(user=owner, name="Trung tâm Anh ngữ mẫu B10")
    m_owner = Membership.objects.get(workspace=ws, user=owner)

    m_free, _ = Membership.objects.get_or_create(workspace=ws, user=freelancer, defaults={"access_role": "MEMBER", "employment_type": "FREELANCER"})

    bp, _ = BrandProfile.objects.get_or_create(
        workspace=ws,
        defaults={
            "name": "Trung tâm Anh ngữ Quốc tế mẫu",
            "product_summary": "Khóa học tiếng Anh giao tiếp và luyện thi IELTS cho người đi làm.",
            "tone_of_voice": "Truyền cảm hứng, chuyên nghiệp và tận tâm.",
            "target_audience": "Người đi làm 22-35 tuổi tại các thành phố lớn.",
            "source_urls": ["https://english.example.com", "https://blog.english.example.com"],
        }
    )

    pkg, _ = Package.objects.get_or_create(
        workspace=ws,
        name="Chiến dịch Facebook Tháng 10",
        defaults={
            "coordinator_membership": m_owner,
            "status": "ACTIVE",
            "start_date": timezone.now().date(),
            "end_date": (timezone.now() + timedelta(days=30)).date(),
        }
    )

    now = timezone.now()
    item_review, _ = ContentItem.objects.get_or_create(
        workspace=ws,
        package=pkg,
        title="Bí quyết vượt qua nỗi sợ nói tiếng Anh trước đám đông",
        defaults={
            "state": "OWNER_REVIEW",
            "writer_membership": m_free,
            "editor_membership": m_owner,
            "publisher_membership": m_owner,
            "writing_deadline": now + timedelta(days=1),
            "editing_deadline": now + timedelta(days=2),
            "review_deadline": now + timedelta(days=3),
            "planned_publish_at": now + timedelta(days=4),
        }
    )
    v1, _ = ContentVersion.objects.get_or_create(
        workspace=ws,
        item=item_review,
        version_no=1,
        defaults={
            "text": "Nội dung bài viết mẫu dành cho kiểm chứng AC16 trên màn hình 390px. Giao diện vừa vặn, không tràn ngang nội dung chính, các nút bấm thao tác Chủ duyệt bài rõ ràng.",
            "author_membership": m_free,
        }
    )

    Task.objects.get_or_create(
        workspace=ws,
        item=item_review,
        role="PUBLISH",
        defaults={"assignee_membership": m_owner, "status": "WAITING", "due_at": now + timedelta(days=4)}
    )
    Notification.objects.get_or_create(
        recipient=owner,
        event_id=f"notif_seed_{item_review.id}",
        defaults={
            "workspace": ws,
            "event_type": "REVIEW_REQUEST",
            "entity_type": "CONTENT_ITEM",
            "entity_id": item_review.id,
            "title": f"Bài viết '{item_review.title}' đang chờ bạn duyệt",
            "message": "Biên tập viên đã hoàn thành và chuyển bài lên cấp phê duyệt Chủ.",
            "target_url": f"/workspaces/{ws.id}/packages/{pkg.id}/items/{item_review.id}/",
        }
    )
    return owner, ws, pkg, item_review


def capture(url, output_path, width=390, height=844):
    cmd = [
        CHROME_BIN,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--window-size={width},{height}",
        f"--screenshot={output_path}",
        url,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"  [OK] Saved: {output_path.name} ({width}x{height})")


def main():
    print("=== BẮT ĐẦU CHỤP BẰNG CHỨNG TRÌNH DUYỆT THỰC TẾ (B10 / AC16) ===")
    owner, ws, pkg, item = seed_data()

    from wsgiref.simple_server import make_server
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from django.core.wsgi import get_wsgi_application
    import threading

    PORT = 8899
    app = StaticFilesHandler(get_wsgi_application())
    httpd = make_server("127.0.0.1", PORT, app)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    print(f"Django In-Process Server đã sẵn sàng tại cổng {PORT}!")
    print("Bắt đầu chụp giao diện qua Chrome Headless...\n")

    base = f"http://127.0.0.1:{PORT}"
    login_prefix = f"{base}/test-auto-login/{owner.id}/?next="

    targets = [
        ("mobile_390px_owner_review_ac16.png", f"{login_prefix}/workspaces/{ws.id}/packages/{pkg.id}/items/{item.id}/", 390, 844),
        ("mobile_390px_dashboard_ui01.png", f"{login_prefix}/workspaces/{ws.id}/", 390, 844),
        ("mobile_390px_my_tasks_ui06.png", f"{login_prefix}/workspaces/{ws.id}/my-tasks/", 390, 844),
        ("mobile_390px_brand_profile.png", f"{login_prefix}/workspaces/{ws.id}/brand/", 390, 844),
        ("mobile_390px_members.png", f"{login_prefix}/workspaces/{ws.id}/members/", 390, 844),
        ("mobile_390px_notifications.png", f"{login_prefix}/notifications/", 390, 844),
        ("desktop_1280px_owner_review.png", f"{login_prefix}/workspaces/{ws.id}/packages/{pkg.id}/items/{item.id}/", 1280, 800),
        ("desktop_1280px_dashboard_ui01.png", f"{login_prefix}/workspaces/{ws.id}/", 1280, 800),
        ("mobile_390px_error_403.png", f"{base}/test-trigger-error/403/", 390, 844),
        ("mobile_390px_error_404.png", f"{base}/test-trigger-error/404/", 390, 844),
        ("mobile_390px_error_409.png", f"{base}/test-trigger-error/409/", 390, 844),
        ("mobile_390px_error_500.png", f"{base}/test-trigger-error/500/", 390, 844),
    ]

    for filename, url, w, h in targets:
        capture(url, SCREENSHOT_DIR / filename, width=w, height=h)

    httpd.shutdown()
    print("\n[THÀNH CÔNG] Toàn bộ ảnh bằng chứng trình duyệt đã được chụp và lưu tại docs/screenshots/")



if __name__ == "__main__":
    main()

