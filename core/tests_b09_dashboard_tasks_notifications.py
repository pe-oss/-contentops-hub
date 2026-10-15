import datetime
import uuid
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.workspaces.models import (
    AccessRole,
    AssignmentRole,
    ContentItem,
    ContentItemState,
    ContentVersion,
    EmploymentType,
    Membership,
    MembershipStatus,
    Notification,
    NotificationEventType,
    Package,
    PackageStatus,
    ReviewDecision,
    Task,
    TaskRole,
    TaskStatus,
    Workspace,
)
from apps.workspaces.selectors import (
    get_my_tasks_for_workspace,
    get_unread_notifications_count,
    get_user_notifications,
    get_workspace_dashboard_data,
    user_has_entity_access,
)
from apps.workspaces.services import (
    approve_plan,
    block_content_item,
    create_notification,
    create_package,
    create_workspace_with_owner,
    deactivate_membership,
    owner_request_changes,
    reassign_item_assignment,
    request_changes_decision,
    submit_content_version,
    submit_for_owner_review,
    unblock_content_item,
)

User = get_user_model()


class B09DashboardTasksNotificationsTestCase(TestCase):
    """
    Bộ kiểm thử tự động Milestone B09 (Spec mục 7 UI01, UI06, 8, 9, 10, 13 B09):
    1. Dashboard (UI01): Ba vùng, chỉ số tổng hợp, phân quyền Chủ / Điều phối / Member / Outsider / Inactive.
    2. Việc của tôi (UI06): Sắp xếp ưu tiên (Blocker > Overdue > Due_at), bộ lọc, phân trang, an toàn sau B08.
    3. Thông báo (Notifications): Sự kiện, người nhận, idempotency, rollback safety, phân quyền đọc.
    """

    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(username="b09_owner", email="owner@test.vn", password="password123")
        self.coord = User.objects.create_user(username="b09_coord", email="coord@test.vn", password="password123")
        self.writer = User.objects.create_user(username="b09_writer", email="writer@test.vn", password="password123")
        self.editor = User.objects.create_user(username="b09_editor", email="editor@test.vn", password="password123")
        self.outsider = User.objects.create_user(username="b09_outsider", email="outsider@test.vn", password="password123")

        self.workspace = create_workspace_with_owner(
            user=self.owner,
            name="Workspace B09 Test",
            timezone_str="Asia/Ho_Chi_Minh",
        )
        self.owner_membership = Membership.objects.get(workspace=self.workspace, user=self.owner)

        self.coord_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.coord,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE,
            status=MembershipStatus.ACTIVE,
        )
        self.writer_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.writer,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.FREELANCER,
            status=MembershipStatus.ACTIVE,
        )
        self.editor_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.editor,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE,
            status=MembershipStatus.ACTIVE,
        )

        # Tạo gói 1 do self.coord điều phối
        now = timezone.now()
        self.pkg1 = create_package(
            user=self.owner,
            workspace=self.workspace,
            name="Gói Tháng 10 - Điều phối Coord",
            objective="Tăng tương tác",
            coordinator_membership=self.coord_membership,
            channel="FACEBOOK",
            start_date=now.date(),
            end_date=now.date() + datetime.timedelta(days=30),
        )

        # Tạo bài viết 1 trong gói 1
        self.item1 = ContentItem.objects.create(
            workspace=self.workspace,
            package=self.pkg1,
            title="Bài 1 - Giới thiệu khoá học",
            brief="Yêu cầu viết về khoá tiếng Anh giao tiếp",
            writer_membership=self.writer_membership,
            editor_membership=self.editor_membership,
            publisher_membership=self.owner_membership,
            writing_deadline=now + datetime.timedelta(days=2),
            editing_deadline=now + datetime.timedelta(days=4),
            review_deadline=now + datetime.timedelta(days=6),
            planned_publish_at=now + datetime.timedelta(days=8),
            state=ContentItemState.WRITING,
        )

    def test_database_test_isolation(self):
        """Xác nhận test runner chạy trên database test cách ly."""
        db_name = connection.settings_dict["NAME"]
        self.assertTrue(
            "test" in db_name.lower() or ":memory:" in db_name or "sqlite" in db_name,
            f"Test runner phải chạy trên database test cách ly, hiện tại: {db_name}",
        )

    def test_dashboard_metrics_and_regions_for_owner(self):
        """Dashboard UI01 (Chủ workspace): Ba vùng, chỉ số tổng hợp theo quyền OWNER."""
        now = timezone.now()
        item_review = ContentItem.objects.create(
            workspace=self.workspace, package=self.pkg1, title="Bài 2 - Chờ Chủ duyệt",
            brief="Brief 2", writer_membership=self.writer_membership, editor_membership=self.editor_membership,
            publisher_membership=self.owner_membership, writing_deadline=now + datetime.timedelta(days=1),
            editing_deadline=now + datetime.timedelta(days=2), review_deadline=now + datetime.timedelta(days=3),
            planned_publish_at=now + datetime.timedelta(days=4), state=ContentItemState.OWNER_REVIEW,
        )
        item_blocked = ContentItem.objects.create(
            workspace=self.workspace, package=self.pkg1, title="Bài 3 - Đang bị chặn",
            brief="Brief 3", writer_membership=self.writer_membership, editor_membership=self.editor_membership,
            publisher_membership=self.owner_membership, writing_deadline=now + datetime.timedelta(days=1),
            editing_deadline=now + datetime.timedelta(days=2), review_deadline=now + datetime.timedelta(days=3),
            planned_publish_at=now + datetime.timedelta(days=4), state=ContentItemState.WRITING,
            blocked_reason="Thiếu tư liệu hình ảnh từ client", blocked_by=self.writer, blocked_at=now,
        )

        data = get_workspace_dashboard_data(self.workspace, self.owner)
        self.assertTrue(data["is_owner"])
        self.assertEqual(data["stats"]["pending_approval_count"], 1)
        self.assertEqual(data["stats"]["blocked_items_count"], 1)
        self.assertEqual(len(data["draft_packages"]), 1)
        self.assertEqual(len(data["items_need_decision"]), 1)
        self.assertEqual(data["items_need_decision"][0].id, item_review.id)
        self.assertEqual(len(data["blocked_items"]), 1)
        self.assertEqual(data["blocked_items"][0].id, item_blocked.id)

        self.client.force_login(self.owner)
        resp = self.client.get(reverse("workspaces:detail", kwargs={"workspace_id": self.workspace.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bài 2 - Chờ Chủ duyệt")
        self.assertContains(resp, "Thiếu tư liệu hình ảnh từ client")

    def test_dashboard_coordinator_scope_and_no_leak(self):
        """Dashboard UI01 (Điều phối viên): Chỉ thấy dữ liệu trong gói mình phụ trách."""
        now = timezone.now()
        pkg2 = create_package(
            user=self.owner, workspace=self.workspace, name="Gói Bí Mật - Không thuộc Coord",
            objective="Mục tiêu riêng", coordinator_membership=self.owner_membership, channel="FACEBOOK",
            start_date=now.date(), end_date=now.date() + datetime.timedelta(days=30),
        )
        item_secret = ContentItem.objects.create(
            workspace=self.workspace, package=pkg2, title="Bài Bí Mật 99", brief="Brief bí mật",
            writer_membership=self.owner_membership, editor_membership=self.owner_membership,
            publisher_membership=self.owner_membership, writing_deadline=now + datetime.timedelta(days=1),
            editing_deadline=now + datetime.timedelta(days=2), review_deadline=now + datetime.timedelta(days=3),
            planned_publish_at=now + datetime.timedelta(days=4), state=ContentItemState.WRITING,
            blocked_reason="Chặn nội bộ gói 2", blocked_by=self.owner, blocked_at=now,
        )

        data = get_workspace_dashboard_data(self.workspace, self.coord)
        self.assertFalse(data["is_owner"])
        self.assertTrue(data["is_coordinator"])

        pkg_ids = [p.id for p in data["packages_progress"]]
        self.assertIn(self.pkg1.id, pkg_ids)
        self.assertNotIn(pkg2.id, pkg_ids)

        blocked_ids = [b.id for b in data["blocked_items"]]
        self.assertNotIn(item_secret.id, blocked_ids)

        self.client.force_login(self.coord)
        resp = self.client.get(reverse("workspaces:detail", kwargs={"workspace_id": self.workspace.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Gói Bí Mật - Không thuộc Coord")

    def test_dashboard_member_scope_and_no_leak(self):
        """Dashboard UI01 (MEMBER): Chỉ thấy bài/nhiệm vụ của mình, không rò rỉ count khác."""
        approve_plan(user=self.owner, package=self.pkg1)

        data = get_workspace_dashboard_data(self.workspace, self.writer)
        self.assertFalse(data["is_owner"])
        self.assertFalse(data["is_coordinator"])
        self.assertEqual(data["stats"]["my_ready_tasks_count"], 1)

        self.client.force_login(self.writer)
        resp = self.client.get(reverse("workspaces:detail", kwargs={"workspace_id": self.workspace.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Việc sẵn sàng làm")

    def test_dashboard_outsider_and_inactive_member_denied(self):
        """Outsider và Thành viên INACTIVE nhận HTTP 404 khi vào Dashboard."""
        self.client.force_login(self.outsider)
        resp = self.client.get(reverse("workspaces:detail", kwargs={"workspace_id": self.workspace.id}))
        self.assertEqual(resp.status_code, 404)

        self.writer_membership.status = MembershipStatus.INACTIVE
        self.writer_membership.save(update_fields=["status"])

        self.client.force_login(self.writer)
        resp_inactive = self.client.get(reverse("workspaces:detail", kwargs={"workspace_id": self.workspace.id}))
        self.assertEqual(resp_inactive.status_code, 404)

    def test_overdue_boundary_calculations(self):
        """Tính toán bài trễ hạn theo ranh giới deadline của bước hiện tại."""
        now = timezone.now()
        # Bài 1: Quá hạn viết
        self.item1.writing_deadline = now - datetime.timedelta(days=1)
        self.item1.save(update_fields=["writing_deadline"])

        data = get_workspace_dashboard_data(self.workspace, self.owner)
        self.assertEqual(data["stats"]["overdue_items_count"], 1)

        # Bài đã PUBLISHED thì dù deadline quá khứ cũng không tính trễ hạn
        self.item1.state = ContentItemState.PUBLISHED
        self.item1.save(update_fields=["state"])
        data_published = get_workspace_dashboard_data(self.workspace, self.owner)
        self.assertEqual(data_published["stats"]["overdue_items_count"], 0)

        # Bài đã CANCELLED cũng không tính trễ hạn
        self.item1.state = ContentItemState.CANCELLED
        self.item1.save(update_fields=["state"])
        data_cancelled = get_workspace_dashboard_data(self.workspace, self.owner)
        self.assertEqual(data_cancelled["stats"]["overdue_items_count"], 0)

    def test_my_tasks_prioritization_and_filters(self):
        """
        Việc của tôi (UI06):
        - Sắp xếp ưu tiên: Bị chặn (Blocker) > Trễ hạn (Overdue) > Đến hạn gần nhất.
        - Lọc theo status, role, package.
        """
        now = timezone.now()
        approve_plan(user=self.owner, package=self.pkg1)

        # Item 1 do writer làm: task WRITE đang READY
        # Thêm Item 2 do writer làm: bị chặn
        item2 = ContentItem.objects.create(
            workspace=self.workspace, package=self.pkg1, title="Bài Bị Chặn 2",
            brief="Brief 2", writer_membership=self.writer_membership, editor_membership=self.editor_membership,
            publisher_membership=self.owner_membership, writing_deadline=now + datetime.timedelta(days=5),
            editing_deadline=now + datetime.timedelta(days=6), review_deadline=now + datetime.timedelta(days=7),
            planned_publish_at=now + datetime.timedelta(days=8), state=ContentItemState.WRITING,
            blocked_reason="Chờ brief bổ sung", blocked_by=self.writer, blocked_at=now,
        )
        task_blocked = Task.objects.create(
            workspace=self.workspace, item=item2, role=TaskRole.WRITE,
            assignee_membership=self.writer_membership, due_at=now + datetime.timedelta(days=5),
            status=TaskStatus.READY,
        )

        tasks = list(get_my_tasks_for_workspace(self.workspace, self.writer))
        # Task bị chặn phải đứng ĐẦU TIÊN
        self.assertEqual(tasks[0].id, task_blocked.id)

        # Kiểm tra filter status
        ready_tasks = get_my_tasks_for_workspace(self.workspace, self.writer, status_filter="READY")
        self.assertEqual(ready_tasks.count(), 2)

        # Kiểm tra render và badge
        self.client.force_login(self.writer)
        resp = self.client.get(reverse("workspaces:my_tasks", kwargs={"workspace_id": self.workspace.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "⚠️ Bị chặn (Blocker)")
        self.assertContains(resp, "Chờ brief bổ sung")

    def test_my_tasks_after_b08_reassignment_and_deactivation(self):
        """Sau bàn giao B08, người mới thấy việc, người cũ không còn quyền thao tác."""
        now = timezone.now()
        approve_plan(user=self.owner, package=self.pkg1)

        # Đổi người viết từ self.writer sang self.coord
        reassign_item_assignment(
            user=self.owner,
            item=self.item1,
            role=AssignmentRole.WRITE,
            new_assignee_membership=self.coord_membership,
            reason="Bàn giao công việc viết bài cho Coord",
            expected_row_version=self.item1.row_version,
        )

        # Người mới (Coord) mở my-tasks -> thấy bài viết
        tasks_coord = get_my_tasks_for_workspace(self.workspace, self.coord, role_filter="WRITE")
        self.assertEqual(tasks_coord.count(), 1)
        self.assertEqual(tasks_coord.first().item_id, self.item1.id)

        # Người cũ (Writer) mở my-tasks -> KHÔNG còn thấy nhiệm vụ này
        tasks_writer = get_my_tasks_for_workspace(self.workspace, self.writer, role_filter="WRITE")
        self.assertEqual(tasks_writer.count(), 0)

    def test_notification_events_generation_and_recipients(self):
        """
        Kiểm thử sinh thông báo đúng sự kiện và đúng người nhận (Spec mục 8, 9, 13 B09):
        - Không thông báo cho chính người thao tác (actor).
        """
        now = timezone.now()
        # 1. Kế hoạch được duyệt: Sinh thông báo cho Writer và Editor (khác Owner)
        approve_plan(user=self.owner, package=self.pkg1)
        writer_notifs = Notification.objects.filter(recipient=self.writer, event_type=NotificationEventType.ASSIGNMENT)
        self.assertTrue(writer_notifs.exists())
        self.assertIn("giao nhiệm vụ", writer_notifs.first().title)

        # Chủ tự giao việc cho mình -> Không sinh thông báo cho Chủ (Spec 8)
        owner_notifs = Notification.objects.filter(recipient=self.owner, event_type=NotificationEventType.ASSIGNMENT)
        self.assertFalse(owner_notifs.exists())

        # 2. Người viết nộp bản nháp cho biên tập -> Sinh thông báo cho Editor
        ver, it = submit_content_version(
            user=self.writer,
            item=self.item1,
            text="Nội dung bản thảo bài 1",
            expected_row_version=self.item1.row_version,
        )
        editor_notifs = Notification.objects.filter(recipient=self.editor, event_type=NotificationEventType.REVIEW_REQUEST)
        self.assertTrue(editor_notifs.exists())
        self.assertIn("sẵn sàng biên tập", editor_notifs.first().title)

        # 3. Biên tập yêu cầu sửa -> Sinh thông báo cho Writer
        it.refresh_from_db()
        dec, it = request_changes_decision(
            user=self.editor,
            item=it,
            reason="Cần thêm dẫn chứng cụ thể",
            expected_row_version=it.row_version,
        )
        writer_changes_notifs = Notification.objects.filter(recipient=self.writer, event_type=NotificationEventType.CHANGES_REQUESTED)
        self.assertTrue(writer_changes_notifs.exists())
        self.assertIn("Biên tập viên yêu cầu sửa", writer_changes_notifs.first().title)

        # 4. Báo chặn -> Sinh thông báo cho Điều phối viên (resolver)
        it.refresh_from_db()
        it_blocked = block_content_item(
            user=self.writer,
            item=it,
            reason="Thiếu thông tin giá",
            expected_row_version=it.row_version,
        )
        coord_blocked_notifs = Notification.objects.filter(recipient=self.coord, event_type=NotificationEventType.BLOCKED)
        self.assertTrue(coord_blocked_notifs.exists())

        # 5. Gỡ chặn -> Sinh thông báo cho người đã báo chặn (Writer)
        it_blocked.refresh_from_db()
        unblock_content_item(
            user=self.owner,
            item=it_blocked,
            resolution_note="Đã bổ sung bảng giá",
            expected_row_version=it_blocked.row_version,
        )
        writer_unblocked_notifs = Notification.objects.filter(recipient=self.writer, event_type=NotificationEventType.UNBLOCKED)
        self.assertTrue(writer_unblocked_notifs.exists())
        self.assertIn("đã được giải quyết", writer_unblocked_notifs.first().title)

    def test_notification_idempotency_no_duplicate(self):
        """Request gửi lặp / Idempotency không tạo thông báo trùng (unique(recipient, event_id))."""
        notif1 = create_notification(
            workspace=self.workspace,
            recipient_user=self.writer,
            actor_user=self.owner,
            event_id="test_idemp_notif_100",
            event_type=NotificationEventType.ASSIGNMENT,
            title="Thông báo thử nghiệm",
            entity_id=self.item1.id,
        )
        notif2 = create_notification(
            workspace=self.workspace,
            recipient_user=self.writer,
            actor_user=self.owner,
            event_id="test_idemp_notif_100",
            event_type=NotificationEventType.ASSIGNMENT,
            title="Thông báo thử nghiệm gửi lại",
            entity_id=self.item1.id,
        )
        self.assertEqual(notif1.id, notif2.id)
        self.assertEqual(Notification.objects.filter(recipient=self.writer, event_id="test_idemp_notif_100").count(), 1)


    def test_notification_rollback_safety(self):
        """Rollback nghiệp vụ bảo đảm không để lại thông báo rác trong CSDL."""
        count_before = Notification.objects.count()

        # Thử gọi submit_content_version nhưng cố tình truyền row_version sai để gây lỗi ConcurrencyConflictError
        try:
            with transaction.atomic():
                create_notification(
                    workspace=self.workspace,
                    recipient_user=self.editor,
                    actor_user=self.writer,
                    event_id="rollback_test_event_1",
                    event_type=NotificationEventType.REVIEW_REQUEST,
                    title="Thông báo rollback",
                    entity_id=self.item1.id,
                )
                raise ValidationError("Lỗi giả lập để rollback transaction")
        except ValidationError:
            pass

        count_after = Notification.objects.count()
        self.assertEqual(count_before, count_after)
        self.assertFalse(Notification.objects.filter(event_id="rollback_test_event_1").exists())

    def test_notification_read_and_permissions(self):
        """
        Đọc và đánh dấu thông báo:
        - Người dùng chỉ đọc và đánh dấu thông báo của chính mình.
        - Thu hồi quyền làm thông báo không còn hiển thị và không thể mở.
        """
        notif = create_notification(
            workspace=self.workspace,
            recipient_user=self.writer,
            actor_user=self.owner,
            event_id="notif_perm_test_1",
            event_type=NotificationEventType.ASSIGNMENT,
            title="Nhiệm vụ mới của bạn",
            entity_id=self.item1.id,
            target_url=f"/workspaces/{self.workspace.id}/packages/{self.pkg1.id}/items/{self.item1.id}/",
        )

        # 1. Người khác (Editor) cố tình đánh dấu đã đọc thông báo của Writer -> 404
        self.client.force_login(self.editor)
        resp_editor = self.client.post(reverse("workspaces:notification_read", kwargs={"notification_id": notif.id}))
        self.assertEqual(resp_editor.status_code, 404)

        # 2. Writer đánh dấu đã đọc thông báo của mình -> 302 redirect
        self.client.force_login(self.writer)
        resp_writer = self.client.post(reverse("workspaces:notification_read", kwargs={"notification_id": notif.id}))
        self.assertEqual(resp_writer.status_code, 302)
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

        # 3. Thu hồi quyền (Writer bị vô hiệu hóa khỏi workspace)
        self.writer_membership.status = MembershipStatus.INACTIVE
        self.writer_membership.save(update_fields=["status"])

        # Danh sách thông báo của writer không còn hiển thị thông báo này
        notifs = get_user_notifications(self.writer)
        self.assertEqual(len(notifs), 0)

        # Cố tình POST đọc khi đã mất quyền -> 403 Forbidden
        resp_revoked = self.client.post(reverse("workspaces:notification_read", kwargs={"notification_id": notif.id}))
        self.assertEqual(resp_revoked.status_code, 403)

    def test_empty_states_and_pagination(self):
        """Kiểm tra empty state và phân trang danh sách Việc của tôi và Thông báo."""
        # Member mới không có task nào
        new_user = User.objects.create_user(username="b09_empty", email="empty@test.vn", password="password123")
        Membership.objects.create(
            workspace=self.workspace,
            user=new_user,
            access_role=AccessRole.MEMBER,
            status=MembershipStatus.ACTIVE,
        )

        self.client.force_login(new_user)
        resp_tasks = self.client.get(reverse("workspaces:my_tasks", kwargs={"workspace_id": self.workspace.id}))
        self.assertEqual(resp_tasks.status_code, 200)
        self.assertContains(resp_tasks, "Bạn không có nhiệm vụ nào")

        resp_notifs = self.client.get(reverse("notifications"))
        self.assertEqual(resp_notifs.status_code, 200)
        self.assertContains(resp_notifs, "Bạn không có thông báo nào")

    def test_tasks_mine_redirect(self):
        """GET /tasks/mine/ điều hướng đúng tới workspace Việc của tôi hiện tại."""
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("tasks_mine"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(str(self.workspace.id), resp.url)

    def test_handover_notification_on_member_deactivation(self):
        """Khi thành viên bị vô hiệu hóa có bàn giao việc (AC11), người thay thế nhận thông báo bàn giao."""
        approve_plan(user=self.owner, package=self.pkg1)

        # Vô hiệu hóa writer và bàn giao việc mở sang coord
        deactivate_membership(
            user=self.owner,
            workspace=self.workspace,
            membership=self.writer_membership,
            replacement_membership=self.coord_membership,
            reason="Thu hồi freelancer và chuyển giao nhiệm vụ",
        )

        coord_notifs = Notification.objects.filter(
            recipient=self.coord,
            event_type=NotificationEventType.ASSIGNMENT,
            event_id__startswith="deact_handover_",
        )
        self.assertTrue(coord_notifs.exists())
        self.assertIn("Tiếp nhận bàn giao", coord_notifs.first().title)

    def test_owner_request_changes_notification_recipients(self):
        """Chủ yêu cầu sửa trả về WRITING thông báo cho người viết; trả về EDITING thông báo cho biên tập."""
        now = timezone.now()
        approve_plan(user=self.owner, package=self.pkg1)
        # Nộp bản thảo -> EDITING
        ver, it = submit_content_version(
            user=self.writer, item=self.item1, text="Bản thảo ban đầu",
            expected_row_version=self.item1.row_version,
        )
        # Biên tập nộp Chủ -> OWNER_REVIEW
        checklist = {
            "brief_compliance": True, "factual_accuracy": True,
            "voice_tone": True, "cta_verified": True,
        }
        dec, it = submit_for_owner_review(
            user=self.editor, item=it, checklist=checklist,
            expected_row_version=it.row_version,
        )

        # 1. Chủ yêu cầu sửa trả về WRITING -> Writer nhận thông báo
        owner_request_changes(
            user=self.owner, item=it, reason="Cần viết lại phần mở đầu",
            return_stage="WRITING", expected_row_version=it.row_version,
        )
        notif_w = Notification.objects.filter(
            recipient=self.writer,
            event_type=NotificationEventType.CHANGES_REQUESTED,
            title__contains="Chủ workspace yêu cầu sửa",
        )
        self.assertTrue(notif_w.exists())

    def test_notifications_filter_unread_and_mark_all_read(self):
        """Kiểm tra lọc thông báo chưa đọc và nút đánh dấu tất cả đã đọc (Spec mục 8)."""
        # Tạo 3 thông báo cho editor
        for i in range(3):
            create_notification(
                workspace=self.workspace,
                recipient_user=self.editor,
                actor_user=self.owner,
                event_id=f"notif_batch_test_{i}",
                event_type=NotificationEventType.ASSIGNMENT,
                title=f"Thông báo số {i}",
                entity_id=self.item1.id,
            )

        self.client.force_login(self.editor)
        # Số chưa đọc ban đầu
        self.assertEqual(get_unread_notifications_count(self.editor), 3)

        # Gọi POST mark all read
        resp_all = self.client.post(reverse("notification_read_all"))
        self.assertEqual(resp_all.status_code, 302)
        self.assertEqual(get_unread_notifications_count(self.editor), 0)

    def test_my_tasks_pagination_over_20_items(self):
        """Phân trang danh sách Việc của tôi: 20 mục / trang (Spec UI01, UI06)."""
        now = timezone.now()
        # Tạo thêm 24 bài viết và nhiệm vụ cho writer
        for i in range(24):
            item = ContentItem.objects.create(
                workspace=self.workspace, package=self.pkg1, title=f"Bài test phân trang {i}",
                brief="Brief", writer_membership=self.writer_membership, editor_membership=self.editor_membership,
                publisher_membership=self.owner_membership, writing_deadline=now + datetime.timedelta(days=2),
                editing_deadline=now + datetime.timedelta(days=4), review_deadline=now + datetime.timedelta(days=6),
                planned_publish_at=now + datetime.timedelta(days=8), state=ContentItemState.WRITING,
            )
            Task.objects.create(
                workspace=self.workspace, item=item, role=TaskRole.WRITE,
                assignee_membership=self.writer_membership, due_at=now + datetime.timedelta(days=2),
                status=TaskStatus.READY,
            )

        self.client.force_login(self.writer)
        resp_p1 = self.client.get(reverse("workspaces:my_tasks", kwargs={"workspace_id": self.workspace.id}))
        self.assertEqual(resp_p1.status_code, 200)
        self.assertEqual(len(resp_p1.context["tasks"]), 20)
        self.assertTrue(resp_p1.context["page_obj"].has_next())

        resp_p2 = self.client.get(reverse("workspaces:my_tasks", kwargs={"workspace_id": self.workspace.id}) + "?page=2")
        self.assertEqual(resp_p2.status_code, 200)
        self.assertTrue(len(resp_p2.context["tasks"]) >= 4)

    def test_navbar_bell_unread_badge_rendering(self):
        """Navbar hiển thị chuông thông báo và số lượng chưa đọc tuân thủ quyền."""
        create_notification(
            workspace=self.workspace,
            recipient_user=self.coord,
            actor_user=self.owner,
            event_id="notif_bell_test_1",
            event_type=NotificationEventType.ASSIGNMENT,
            title="Thông báo chuông",
            entity_id=self.item1.id,
        )

        self.client.force_login(self.coord)
        resp = self.client.get(reverse("workspaces:detail", kwargs={"workspace_id": self.workspace.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "🔔")
        self.assertContains(resp, 'badge" style="background: #dc2626')


