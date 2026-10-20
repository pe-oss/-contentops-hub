import datetime
import uuid
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.workspaces.models import (
    AccessRole,
    ContentItem,
    ContentItemState,
    EmploymentType,
    Membership,
    MembershipStatus,
    Notification,
    NotificationEventType,
    Package,
    PackageStatus,
)
from apps.workspaces.selectors import get_unread_notifications_count
from apps.workspaces.services import create_workspace_with_owner

User = get_user_model()


class UXGroup3NotificationsTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(username="grp3_owner", email="owner@grp3.vn", password="password123")
        self.writer = User.objects.create_user(username="grp3_writer", email="writer@grp3.vn", password="password123")
        self.outsider = User.objects.create_user(username="grp3_outsider", email="outsider@grp3.vn", password="password123")

        self.workspace = create_workspace_with_owner(
            user=self.owner,
            name="Workspace Group 3",
            timezone_str="Asia/Ho_Chi_Minh",
        )
        self.owner_membership = Membership.objects.get(workspace=self.workspace, user=self.owner)
        self.writer_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.writer,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE,
            status=MembershipStatus.ACTIVE,
        )

        now = timezone.now()
        self.package = Package.objects.create(
            workspace=self.workspace,
            name="Chiến dịch Q4",
            objective="Mục tiêu Q4",
            coordinator_membership=self.owner_membership,
            start_date=now.date(),
            end_date=now.date() + datetime.timedelta(days=30),
            status=PackageStatus.ACTIVE,
        )

        self.content_item = ContentItem.objects.create(
            workspace=self.workspace,
            package=self.package,
            title="Bài viết SEO Top 1",
            brief="Yêu cầu viết bài SEO",
            state=ContentItemState.WRITING,
            writer_membership=self.writer_membership,
            editor_membership=self.owner_membership,
            publisher_membership=self.owner_membership,
            writing_deadline=now + datetime.timedelta(days=2),
            editing_deadline=now + datetime.timedelta(days=4),
            review_deadline=now + datetime.timedelta(days=6),
            planned_publish_at=now + datetime.timedelta(days=8),
        )

    def test_topbar_bell_dropdown_markup_and_sidebar_removal(self):
        """Kiểm tra chuông topbar có cấu trúc dropdown hoàn chỉnh và sidebar đã loại bỏ mục thông báo."""
        self.client.force_login(self.writer)
        resp = self.client.get(reverse("workspaces:detail", kwargs={"workspace_id": self.workspace.id}))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")

        # 1. Topbar dropdown markup
        self.assertIn('id="notificationDropdownWrapper"', content)
        self.assertIn('id="notificationDropdownBtn"', content)
        self.assertIn('id="notificationDropdownPanel"', content)
        self.assertIn("Thông báo", content)
        self.assertIn("Đánh dấu tất cả đã đọc", content)
        self.assertIn('id="notifTabAll"', content)
        self.assertIn('id="notifTabUnread"', content)
        self.assertIn('id="notifListContainer"', content)
        self.assertIn('id="notifLoadMoreBtn"', content)

        # 2. Sidebar removal: không còn mục menu Thông báo trong sidebar
        self.assertNotIn('sidebar-link" href="/notifications/"', content)
        self.assertNotIn('sidebar-link active" href="/notifications/"', content)
        self.assertNotIn('<span>Thông báo</span>', content)

    def test_notification_list_json_api_structure(self):
        """API trả về JSON chuẩn cho chuông dropdown khi gọi format=json hoặc X-Requested-With."""
        notif = Notification.objects.create(
            workspace=self.workspace,
            recipient=self.writer,
            event_id="evt_test_1",
            event_type=NotificationEventType.ASSIGNMENT,
            entity_type="CONTENT_ITEM",
            entity_id=self.content_item.id,
            title="Bạn được giao viết bài: Bài viết SEO Top 1",
            message="Vui lòng hoàn thành trước hạn chót.",
            target_url=f"/workspaces/{self.workspace.id}/items/{self.content_item.id}/",
        )

        self.client.force_login(self.writer)
        url = reverse("workspaces:workspace_notifications", kwargs={"workspace_id": self.workspace.id})
        resp = self.client.get(url, {"format": "json"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["unread_count"], 1)
        self.assertEqual(len(data["notifications"]), 1)

        item = data["notifications"][0]
        self.assertEqual(item["id"], str(notif.id))
        self.assertEqual(item["event_type"], "ASSIGNMENT")
        self.assertEqual(item["title"], notif.title)
        self.assertEqual(item["message"], notif.message)
        self.assertFalse(item["is_read"])
        self.assertIn("read_url", item)

    def test_notification_list_unread_filter_and_pagination(self):
        """Kiểm tra tab Chưa đọc và phân trang server 10 item/trang."""
        now = timezone.now()
        for i in range(10):
            Notification.objects.create(
                workspace=self.workspace,
                recipient=self.writer,
                event_id=f"evt_unread_{i}",
                event_type=NotificationEventType.ASSIGNMENT,
                entity_type="CONTENT_ITEM",
                entity_id=self.content_item.id,
                title=f"Thông báo chưa đọc {i}",
            )
        for i in range(2):
            Notification.objects.create(
                workspace=self.workspace,
                recipient=self.writer,
                event_id=f"evt_read_{i}",
                event_type=NotificationEventType.REVIEW_REQUEST,
                entity_type="CONTENT_ITEM",
                entity_id=self.content_item.id,
                title=f"Thông báo đã đọc {i}",
                read_at=now,
            )

        self.client.force_login(self.writer)
        url = reverse("workspaces:workspace_notifications", kwargs={"workspace_id": self.workspace.id})

        # Trang 1: Tất cả -> 10 items, has_next=True
        resp1 = self.client.get(url, {"format": "json", "page": 1})
        d1 = resp1.json()
        self.assertEqual(len(d1["notifications"]), 10)
        self.assertTrue(d1["has_next"])
        self.assertEqual(d1["unread_count"], 10)

        # Trang 2: Tất cả -> 2 items còn lại, has_next=False
        resp2 = self.client.get(url, {"format": "json", "page": 2})
        d2 = resp2.json()
        self.assertEqual(len(d2["notifications"]), 2)
        self.assertFalse(d2["has_next"])

        # Tab Chưa đọc: status=unread
        resp_unread = self.client.get(url, {"format": "json", "status": "unread", "page": 1})
        du = resp_unread.json()
        self.assertEqual(len(du["notifications"]), 10)
        self.assertFalse(du["has_next"])
        for item in du["notifications"]:
            self.assertFalse(item["is_read"])
    def test_notification_read_ajax(self):
        """Bấm vào mục thông báo gọi POST đánh dấu đã đọc và cập nhật unread_count."""
        notif = Notification.objects.create(
            workspace=self.workspace,
            recipient=self.writer,
            event_id="evt_read_ajax_1",
            event_type=NotificationEventType.ASSIGNMENT,
            entity_type="CONTENT_ITEM",
            entity_id=self.content_item.id,
            title="Giao bài tập",
            target_url=f"/workspaces/{self.workspace.id}/items/{self.content_item.id}/",
        )
        self.assertFalse(notif.is_read)

        self.client.force_login(self.writer)
        read_url = reverse("workspaces:notification_read", kwargs={"notification_id": notif.id})
        resp = self.client.post(read_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["notification_id"], str(notif.id))
        self.assertEqual(data["unread_count"], 0)

        notif.refresh_from_db()
        self.assertTrue(notif.is_read)
        self.assertIsNotNone(notif.read_at)

    def test_notification_read_all_ajax(self):
        """Bấm 'Đánh dấu tất cả đã đọc' cập nhật toàn bộ thông báo chưa đọc thành đã đọc."""
        for i in range(3):
            Notification.objects.create(
                workspace=self.workspace,
                recipient=self.writer,
                event_id=f"evt_all_{i}",
                event_type=NotificationEventType.ASSIGNMENT,
                entity_type="CONTENT_ITEM",
                entity_id=self.content_item.id,
                title=f"Chưa đọc số {i}",
            )

        self.client.force_login(self.writer)
        self.assertEqual(get_unread_notifications_count(self.writer, workspace=self.workspace), 3)

        read_all_url = reverse("workspaces:notification_read_all")
        resp = self.client.post(read_all_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["unread_count"], 0)
        self.assertEqual(get_unread_notifications_count(self.writer, workspace=self.workspace), 0)

    def test_notification_permission_isolation(self):
        """Bảo mật: Không xem hoặc đánh dấu thông báo của người khác; mất quyền đối tượng nhận 403."""
        notif_writer = Notification.objects.create(
            workspace=self.workspace,
            recipient=self.writer,
            event_id="evt_sec_writer",
            event_type=NotificationEventType.ASSIGNMENT,
            entity_type="CONTENT_ITEM",
            entity_id=self.content_item.id,
            title="Bảo mật của Writer",
        )

        # 1. Outsider gọi API list của workspace -> 404
        self.client.force_login(self.outsider)
        url = reverse("workspaces:workspace_notifications", kwargs={"workspace_id": self.workspace.id})
        resp = self.client.get(url, {"format": "json"})
        self.assertEqual(resp.status_code, 404)

        # 2. Owner không thể đọc thông báo của Writer -> 404
        self.client.force_login(self.owner)
        read_url = reverse("workspaces:notification_read", kwargs={"notification_id": notif_writer.id})
        resp = self.client.post(read_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 404)

        # 3. Writer mất quyền truy cập đối tượng (bị vô hiệu hóa membership) -> nhận 403
        self.writer_membership.status = MembershipStatus.INACTIVE
        self.writer_membership.save()

        self.client.force_login(self.writer)
        resp = self.client.post(read_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 403)

    def test_mobile_responsive_css_present(self):
        """CSS kiểm soát dropdown thông báo không bị tràn hoặc cắt trên màn hình nhỏ (390px)."""
        import os
        from django.conf import settings
        css_path = os.path.join(settings.BASE_DIR, "static", "css", "app.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css_content = f.read()

        self.assertIn(".notification-dropdown-panel", css_content)
        self.assertIn("@media (max-width: 480px)", css_content)
        self.assertIn("max-width: calc(100vw - 20px)", css_content)
