import datetime
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.workspaces.models import (
    AccessRole, ContentItem, ContentItemState, ContentVersion,
    EmploymentType, Membership, MembershipStatus, Package, PackageStatus,
    ReviewDecision, Task, TaskExecutionMode, TaskRole, TaskStatus, Workspace,
)
from apps.workspaces.services import (
    ConcurrencyConflictError,
    add_content_item,
    approve_plan,
    create_editor_version,
    create_package,
    create_workspace_with_owner,
    format_brief_for_copy,
    request_changes_decision,
    save_draft_content,
    start_writing_task,
    submit_content_version,
    submit_for_owner_review,
)

User = get_user_model()


class B05ContentOperationsTestCase(TestCase):
    """
    Bộ kiểm thử B05 - Vận hành Task nội dung, Phiên bản và Luồng viết/biên tập.
    Kiểm tra đầy đủ các yêu cầu Spec mục 5 F03-F04, 6, 9, 13 B05 và AC06, AC08, AC10, AC12.
    """

    def setUp(self):
        self.owner = User.objects.create_user(username="owner_user", email="owner@test.com", password="password123")
        self.writer = User.objects.create_user(username="writer_user", email="writer@test.com", password="password123")
        self.editor = User.objects.create_user(username="editor_user", email="editor@test.com", password="password123")
        self.publisher = User.objects.create_user(username="publisher_user", email="publisher@test.com", password="password123")
        self.outsider = User.objects.create_user(username="outsider_user", email="outsider@test.com", password="password123")

        self.workspace = create_workspace_with_owner(
            user=self.owner,
            name="Trung tâm Anh ngữ Mẫu",
            timezone_str="Asia/Ho_Chi_Minh",
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
            employment_type=EmploymentType.FREELANCER,
            status=MembershipStatus.ACTIVE,
        )
        self.publisher_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.publisher,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE,
            status=MembershipStatus.ACTIVE,
        )

        today = timezone.now().date()
        owner_membership = Membership.objects.get(workspace=self.workspace, user=self.owner)
        self.pkg = create_package(
            user=self.owner,
            workspace=self.workspace,
            coordinator_membership=owner_membership,
            name="Gói 3 bài Facebook Chiến dịch Tháng 10",
            objective="Tăng tương tác và chuyển đổi học viên mới",
            channel="FACEBOOK",
            start_date=today,
            end_date=today + datetime.timedelta(days=30),
        )

        base_time = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) + datetime.timedelta(days=2)
        self.item = add_content_item(
            user=self.owner,
            package=self.pkg,
            title="Bài 1: 5 bí quyết luyện IELTS Speaking",
            brief="Chia sẻ mẹo thực chiến luyện phản xạ nói Band 7.0+",
            cta="Đăng ký test trình độ miễn phí",
            writing_deadline=base_time + datetime.timedelta(days=2),
            editing_deadline=base_time + datetime.timedelta(days=4),
            review_deadline=base_time + datetime.timedelta(days=6),
            planned_publish_at=base_time + datetime.timedelta(days=8),
            writer_membership=self.writer_membership,
            editor_membership=self.editor_membership,
            publisher_membership=self.publisher_membership,
        )

        # Chủ duyệt kế hoạch -> sinh 3 tasks
        approve_plan(user=self.owner, package=self.pkg)
        self.item.refresh_from_db()

    def test_database_test_isolation(self):
        """Xác nhận test database hoàn toàn tách biệt khỏi database ứng dụng."""
        db_name = connection.settings_dict.get("NAME", "")
        self.assertTrue(
            db_name.startswith("test_") or ":memory:" in db_name,
            f"Test runner phải chạy trên database test riêng biệt, hiện tại: {db_name}",
        )

    def test_format_brief_for_copy_f03(self):
        """
        Spec F03: Kiểm tra định dạng Brief sao chép sang AI riêng:
        Bao gồm mục tiêu, đối tượng, giọng văn, yêu cầu bài, điều tránh và đánh dấu [CẦN XÁC MINH].
        """
        brief_text = format_brief_for_copy(self.item)
        self.assertIn("=== BRIEF NỘI DUNG: Bài 1: 5 bí quyết luyện IELTS Speaking ===", brief_text)
        self.assertIn("Kênh đăng: FACEBOOK", brief_text)
        self.assertIn("Chia sẻ mẹo thực chiến luyện phản xạ nói Band 7.0+", brief_text)
        self.assertIn("Đăng ký test trình độ miễn phí", brief_text)
        self.assertIn("[CẦN XÁC MINH]", brief_text)

    def test_valid_workflow_from_writing_to_editing_and_owner_review(self):
        """
        Kiểm tra luồng chuẩn hoàn chỉnh từ Viết bài đến Biên tập và Chủ duyệt (Spec F03, F04, 6.1, 6.2).
        """
        # 1. Người viết nhận việc & bắt đầu viết
        start_writing_task(user=self.writer, item=self.item)
        self.item.refresh_from_db()
        self.assertEqual(self.item.state, ContentItemState.WRITING)
        write_task = Task.objects.get(item=self.item, role=TaskRole.WRITE)
        self.assertEqual(write_task.status, TaskStatus.IN_PROGRESS)

        # 2. Lưu bản nháp nhiều lần
        save_draft_content(
            user=self.writer,
            item=self.item,
            text="Bản nháp đang viết câu mở đầu...",
            reference_urls=["https://ielts.org/speaking"],
            expected_row_version=self.item.row_version,
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.draft_text, "Bản nháp đang viết câu mở đầu...")
        self.assertEqual(self.item.draft_reference_urls, ["https://ielts.org/speaking"])
        self.assertEqual(self.item.versions.count(), 0)  # Lưu nháp không tạo ContentVersion

        # 3. Nộp bản v1 hoàn chỉnh cho Biên tập
        v1, item_after_v1 = submit_content_version(
            user=self.writer,
            item=self.item,
            text="Toàn văn bài viết v1 hoàn thiện.",
            reference_urls=["https://ielts.org/speaking"],
            expected_row_version=self.item.row_version,
        )
        self.assertEqual(v1.version_no, 1)
        self.assertEqual(item_after_v1.state, ContentItemState.EDITING)
        self.assertEqual(item_after_v1.latest_version_id, v1.id)

        write_task.refresh_from_db()
        edit_task = Task.objects.get(item=self.item, role=TaskRole.EDIT)
        self.assertEqual(write_task.status, TaskStatus.DONE)
        self.assertEqual(edit_task.status, TaskStatus.READY)

        # 4. Biên tập viên kiểm tra và tạo bản chỉnh sửa v2
        v2, item_after_v2 = create_editor_version(
            user=self.editor,
            item=item_after_v1,
            text="Toàn văn bài viết v2 đã qua biên tập chu đáo.",
            expected_row_version=item_after_v1.row_version,
        )
        self.assertEqual(v2.version_no, 2)
        self.assertEqual(v2.parent_version_id, v1.id)
        self.assertEqual(item_after_v2.latest_version_id, v2.id)
        self.assertEqual(self.item.versions.count(), 2)  # Phiên bản cũ v1 vẫn nguyên vẹn

        # 5. Biên tập viên hoàn tất 4 tiêu chí checklist và chuyển Chủ duyệt
        decision, item_after_review = submit_for_owner_review(
            user=self.editor,
            item=item_after_v2,
            checklist={
                "brief_compliance": True,
                "factual_accuracy": True,
                "voice_tone": True,
                "cta_verified": True,
            },
            expected_row_version=item_after_v2.row_version,
        )
        self.assertEqual(item_after_review.state, ContentItemState.OWNER_REVIEW)
        self.assertEqual(decision.decision, "SUBMIT_REVIEW")
        edit_task.refresh_from_db()
        self.assertEqual(edit_task.status, TaskStatus.DONE)

    def test_request_changes_lifecycle_ac06(self):
        """
        AC06: Nộp v1, biên tập trả sửa có lý do, nộp v2:
        - V1 vẫn giữ nguyên trong lịch sử, không bị ghi đè.
        - Trạng thái trả từ EDITING về WRITING.
        - Nhiệm vụ Viết mở lại (IN_PROGRESS); Biên tập về WAITING (Spec 6.2).
        """
        # Người viết nộp v1
        v1, _ = submit_content_version(
            user=self.writer,
            item=self.item,
            text="Nội dung bài viết v1 sơ sài.",
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.state, ContentItemState.EDITING)

        # Biên tập viên yêu cầu sửa có lý do
        decision, item_returned = request_changes_decision(
            user=self.editor,
            item=self.item,
            reason="Thiếu phần giải thích band điểm và CTA chưa thu hút.",
            expected_row_version=self.item.row_version,
        )
        self.assertEqual(item_returned.state, ContentItemState.WRITING)
        self.assertEqual(decision.decision, "REQUEST_CHANGES")
        self.assertEqual(decision.reason, "Thiếu phần giải thích band điểm và CTA chưa thu hút.")

        write_task = Task.objects.get(item=self.item, role=TaskRole.WRITE)
        edit_task = Task.objects.get(item=self.item, role=TaskRole.EDIT)
        self.assertEqual(write_task.status, TaskStatus.IN_PROGRESS)
        self.assertEqual(edit_task.status, TaskStatus.WAITING)

        # Người viết nộp lại v2
        v2, item_v2 = submit_content_version(
            user=self.writer,
            item=item_returned,
            text="Nội dung bài viết v2 đã bổ sung giải thích band điểm đầy đủ.",
            expected_row_version=item_returned.row_version,
        )
        self.assertEqual(v2.version_no, 2)
        self.assertEqual(item_v2.latest_version_id, v2.id)

        # Bản v1 vẫn giữ nguyên
        v1.refresh_from_db()
        self.assertEqual(v1.text, "Nội dung bài viết v1 sơ sài.")
        self.assertEqual(self.item.versions.count(), 2)

    def test_validation_incomplete_checklist_cannot_submit_review(self):
        """
        Thiếu tiêu chí trong 4 checklist thì không cho chuyển Chủ duyệt (F04).
        """
        submit_content_version(user=self.writer, item=self.item, text="Bài viết v1")
        self.item.refresh_from_db()

        # Thiếu factual_accuracy
        with self.assertRaises(ValidationError) as ctx:
            submit_for_owner_review(
                user=self.editor,
                item=self.item,
                checklist={
                    "brief_compliance": True,
                    "factual_accuracy": False,
                    "voice_tone": True,
                    "cta_verified": True,
                },
            )
        self.assertIn("Độ chính xác theo tài liệu", str(ctx.exception))

    def test_permission_matrix_and_unauthorized_member_blocked(self):
        """
        Người không được phân công hoặc sai vai trò không thể cập nhật (Spec mục 3, 5).
        """
        # Publisher không có quyền nộp bài viết
        with self.assertRaises(PermissionDenied):
            submit_content_version(user=self.publisher, item=self.item, text="Publisher cố nộp bài")

        # Nộp v1 hợp lệ bởi người viết
        submit_content_version(user=self.writer, item=self.item, text="Bản v1 của người viết")
        self.item.refresh_from_db()

        # Writer không có quyền biên tập hoặc yêu cầu sửa
        with self.assertRaises(PermissionDenied):
            request_changes_decision(user=self.writer, item=self.item, reason="Cố tự trả về")

        with self.assertRaises(PermissionDenied):
            submit_for_owner_review(
                user=self.writer,
                item=self.item,
                checklist={"brief_compliance": True, "factual_accuracy": True, "voice_tone": True, "cta_verified": True},
            )

    def test_tenant_isolation_cross_workspace_and_inactive_membership_404(self):
        """
        Người ngoài workspace hoặc membership INACTIVE truy cập nhận 404 (Spec mục 3).
        """
        # Người ngoài workspace gọi URL bài viết -> 404
        self.client.force_login(self.outsider)
        url = reverse(
            "workspaces:item_detail",
            kwargs={"workspace_id": self.workspace.id, "package_id": self.pkg.id, "item_id": self.item.id},
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

        # Vô hiệu hóa membership của người viết -> 404 ngay ở request kế tiếp
        self.writer_membership.status = MembershipStatus.INACTIVE
        self.writer_membership.save()

        self.client.force_login(self.writer)
        resp_inactive = self.client.get(url)
        self.assertEqual(resp_inactive.status_code, 404)

    def test_cannot_submit_new_version_when_in_owner_review_ac08(self):
        """
        AC08: Bài đang chờ Chủ duyệt (OWNER_REVIEW), người viết không được lưu/nộp version mới.
        """
        # Đưa bài vào trạng thái OWNER_REVIEW
        submit_content_version(user=self.writer, item=self.item, text="Bài v1")
        self.item.refresh_from_db()
        submit_for_owner_review(
            user=self.editor,
            item=self.item,
            checklist={"brief_compliance": True, "factual_accuracy": True, "voice_tone": True, "cta_verified": True},
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.state, ContentItemState.OWNER_REVIEW)

        # Người viết cố tình gọi nộp version mới -> bị từ chối ValidationError
        with self.assertRaises(ValidationError):
            submit_content_version(user=self.writer, item=self.item, text="Cố nộp khi đang chờ Chủ duyệt")

    def test_blocked_item_behavior_ac12(self):
        """
        AC12: Bài bị chặn:
        - Vẫn cho lưu nháp (draft).
        - Từ chối nộp phiên bản (submit) hoặc chuyển bước.
        """
        self.item.blocked_reason = "Đang chờ đối tác xác nhận số liệu thống kê."
        self.item.blocked_by = self.owner
        self.item.blocked_at = timezone.now()
        self.item.save()

        # Lưu nháp thành công dù bị chặn
        saved_item = save_draft_content(
            user=self.writer,
            item=self.item,
            text="Đoạn nháp viết dở trong lúc chờ đối tác",
        )
        self.assertEqual(saved_item.draft_text, "Đoạn nháp viết dở trong lúc chờ đối tác")

        # Nộp bài biên tập -> Bị chặn
        with self.assertRaises(ValidationError) as ctx:
            submit_content_version(
                user=self.writer,
                item=self.item,
                text="Cố nộp bản hoàn chỉnh",
            )
        self.assertIn("đang bị chặn", str(ctx.exception))

    def test_optimistic_concurrency_control_409_ac10(self):
        """
        AC10: Hai người sửa cùng row_version:
        - Người thứ nhất ghi thành công.
        - Người thứ hai nhận 409 ConcurrencyConflictError, không mất dữ liệu âm thầm.
        """
        initial_row_version = self.item.row_version

        # Người 1 nộp thành công với row_version hiện tại
        submit_content_version(
            user=self.writer,
            item=self.item,
            text="Nội dung nộp bởi người thứ nhất",
            expected_row_version=initial_row_version,
        )
        self.item.refresh_from_db()
        self.assertGreater(self.item.row_version, initial_row_version)

        # Người 2 gửi thao tác với row_version cũ -> Bị xung đột 409
        with self.assertRaises(ConcurrencyConflictError):
            save_draft_content(
                user=self.writer,
                item=self.item,
                text="Nội dung người 2 gửi dựa trên bản cũ",
                expected_row_version=initial_row_version,
            )

    def test_idempotency_double_click_protection(self):
        """
        Kiểm tra tính an toàn khi request bị lặp / nhấp đúp với idempotency_key:
        Không tạo nhiều phiên bản hoặc quyết định trùng lặp.
        """
        idemp = "idemp_sub_123"
        v1, _ = submit_content_version(
            user=self.writer,
            item=self.item,
            text="Nội dung hoàn thành",
            idempotency_key=idemp,
        )
        # Thao tác lặp lại
        v2, _ = submit_content_version(
            user=self.writer,
            item=self.item,
            text="Nội dung hoàn thành",
            idempotency_key=idemp,
        )
        self.assertEqual(v1.id, v2.id)
        self.assertEqual(self.item.versions.count(), 1)

    def test_https_validation_for_reference_urls(self):
        """
        Chỉ chấp nhận URLs HTTPS hợp lệ; chặn scheme khác (Spec mục 4).
        """
        with self.assertRaises(ValidationError):
            submit_content_version(
                user=self.writer,
                item=self.item,
                text="Nội dung",
                reference_urls=["http://insecure-site.com"],
            )

        with self.assertRaises(ValidationError):
            submit_content_version(
                user=self.writer,
                item=self.item,
                text="Nội dung",
                reference_urls=["javascript:alert(1)"],
            )

    def test_my_tasks_view_filters_and_access(self):
        """
        Màn hình Việc của tôi (UI06): Hiển thị đúng công việc được giao của người dùng.
        """
        self.client.force_login(self.writer)
        url = reverse("workspaces:my_tasks", kwargs={"workspace_id": self.workspace.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bài 1: 5 bí quyết luyện IELTS Speaking")
        self.assertContains(resp, "Viết bài")

        # Kiểm tra lọc theo status=READY
        resp_filtered = self.client.get(url + "?status=READY")
        self.assertEqual(resp_filtered.status_code, 200)
        self.assertContains(resp_filtered, "Bài 1: 5 bí quyết luyện IELTS Speaking")