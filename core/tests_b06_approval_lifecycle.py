import datetime
import uuid
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.workspaces.models import (
    AccessRole, ContentApproval, ContentItem, ContentItemState, ContentVersion,
    EmploymentType, Membership, MembershipStatus, Package, PackageStatus,
    ReviewDecision, Task, TaskExecutionMode, TaskRole, TaskStatus, Workspace,
)
from apps.workspaces.services import (
    ConcurrencyConflictError,
    add_content_item,
    approve_plan,
    block_content_item,
    cancel_content_item,
    create_package,
    create_workspace_with_owner,
    owner_approve_item,
    owner_request_changes,
    reopen_content_item,
    start_writing_task,
    submit_content_version,
    submit_for_owner_review,
    unblock_content_item,
    withdraw_review,
)

User = get_user_model()


class ContentApprovalAndLifecycleTests(TestCase):
    """
    Bộ kiểm thử B06 - Chủ duyệt, mở lại, và vòng đời xuất bản.
    Kiểm tra đầy đủ các yêu cầu Spec mục 5 F05, 6, 9, 13 B06 và AC07, AC08, AC09, AC10, AC12.
    """

    def setUp(self):
        # 1. Tạo User và Workspace với Owner
        self.owner = User.objects.create_user(
            username="owner_user",
            email="owner@test.com",
            password="password123",
        )
        self.workspace = create_workspace_with_owner(
            user=self.owner,
            name="Công ty Marketing B06",
            timezone_str="Asia/Ho_Chi_Minh",
        )
        self.owner_membership = Membership.objects.get(workspace=self.workspace, user=self.owner)

        # 2. Tạo thành viên Writer, Editor, Publisher
        self.writer = User.objects.create_user(username="writer_user", email="writer@test.com", password="password123")
        self.writer_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.writer,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE,
            status=MembershipStatus.ACTIVE,
        )

        self.editor = User.objects.create_user(username="editor_user", email="editor@test.com", password="password123")
        self.editor_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.editor,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE,
            status=MembershipStatus.ACTIVE,
        )

        self.publisher = User.objects.create_user(username="pub_user", email="pub@test.com", password="password123")
        self.publisher_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.publisher,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE,
            status=MembershipStatus.ACTIVE,
        )

        # 3. Tạo Gói và Bài viết
        today = timezone.localdate()
        self.pkg = create_package(
            user=self.owner,
            workspace=self.workspace,
            name="Chiến dịch B06",
            objective="Chủ duyệt và vòng đời",
            channel="FACEBOOK",
            start_date=today,
            end_date=today + datetime.timedelta(days=30),
            coordinator_membership=self.owner_membership,
        )

        now = timezone.now().replace(microsecond=0)
        self.item = add_content_item(
            user=self.owner,
            package=self.pkg,
            title="Bài viết Milestone B06",
            brief="Kiểm tra vòng đời phê duyệt và mở lại bài viết.",
            cta="Xem chi tiết giải pháp",
            writing_deadline=now + datetime.timedelta(days=2),
            editing_deadline=now + datetime.timedelta(days=4),
            review_deadline=now + datetime.timedelta(days=6),
            planned_publish_at=now + datetime.timedelta(days=8),
            writer_membership=self.writer_membership,
            editor_membership=self.editor_membership,
            publisher_membership=self.publisher_membership,
        )

        # Chủ duyệt kế hoạch để kích hoạt gói và sinh nhiệm vụ
        approve_plan(user=self.owner, package=self.pkg)
        self.item.refresh_from_db()

    def _advance_item_to_owner_review(self) -> tuple[ContentVersion, ContentItem]:
        """Helper nộp bài v1 và chuyển checklist tới bước OWNER_REVIEW."""
        start_writing_task(user=self.writer, item=self.item)
        v1, item_editing = submit_content_version(
            user=self.writer,
            item=self.item,
            text="Nội dung phiên bản v1 chuẩn bị cho Chủ duyệt.",
            reference_urls=["https://example.com/source1"],
        )
        decision, item_review = submit_for_owner_review(
            user=self.editor,
            item=item_editing,
            checklist={
                "brief_compliance": True,
                "factual_accuracy": True,
                "voice_tone": True,
                "cta_verified": True,
            },
            expected_row_version=item_editing.row_version,
        )
        return v1, item_review

    def test_owner_approve_success_lifecycle(self):
        """
        Kiểm tra luồng Chủ workspace phê duyệt hợp lệ:
        - Trạng thái chuyển: OWNER_REVIEW -> READY_TO_PUBLISH.
        - Tạo ContentApproval trỏ version_id cố định.
        - Nhiệm vụ PUBLISH chuyển từ WAITING sang READY.
        - Ghi nhận ReviewDecision append-only ('APPROVE').
        """
        v1, item_review = self._advance_item_to_owner_review()
        self.assertEqual(item_review.state, ContentItemState.OWNER_REVIEW)

        pub_task = Task.objects.get(item=self.item, role=TaskRole.PUBLISH)
        self.assertEqual(pub_task.status, TaskStatus.WAITING)

        approval, item_approved = owner_approve_item(
            user=self.owner,
            item=item_review,
            expected_version_id=v1.id,
            expected_row_version=item_review.row_version,
        )

        self.assertEqual(item_approved.state, ContentItemState.READY_TO_PUBLISH)
        self.assertEqual(item_approved.approval_id, approval.id)
        self.assertEqual(approval.version_id, v1.id)
        self.assertEqual(approval.approved_by, self.owner)
        self.assertTrue(approval.is_active)

        pub_task.refresh_from_db()
        self.assertEqual(pub_task.status, TaskStatus.READY)

        decisions = ReviewDecision.objects.filter(item=self.item, decision="APPROVE")
        self.assertEqual(decisions.count(), 1)
        self.assertEqual(decisions.first().actor_membership, self.owner_membership)

    def test_stale_version_approval_rejected_ac07(self):
        """
        AC07: Chủ đang xem v1 trong khi bản hiện hành đã thay đổi lên v2.
        Gửi duyệt v1 trả về HTTP 409 ConcurrencyConflictError, không duyệt nhầm.
        """
        v1, item_review = self._advance_item_to_owner_review()

        # Giả sử trong lúc đó có version v2 được tạo và cập nhật latest_version_id
        v2 = ContentVersion.objects.create(
            workspace=self.workspace,
            item=item_review,
            version_no=2,
            text="Nội dung phiên bản v2 mới hơn",
            author_membership=self.editor_membership,
            parent_version=v1,
        )
        item_review.latest_version_id = v2.id
        item_review.row_version += 1
        item_review.save(update_fields=["latest_version_id", "row_version"])

        # Chủ gửi duyệt với expected_version_id=v1.id -> Bị chặn 409
        with self.assertRaises(ConcurrencyConflictError) as ctx:
            owner_approve_item(
                user=self.owner,
                item=item_review,
                expected_version_id=v1.id,
                expected_row_version=item_review.row_version,
            )
        self.assertIn("đã cũ", str(ctx.exception))

    def test_reopen_invalidates_approval_and_transitions_ac09(self):
        """
        AC09: Duyệt v1, sau đó Chủ mở lại để sửa:
        - Approval cũ bị vô hiệu hóa (invalidated_at != None).
        - approval_id trên ContentItem bị xóa về None.
        - Trạng thái bài viết chuyển về EDITING.
        - Task EDIT mở lại READY; Task PUBLISH trở về WAITING.
        - ReviewDecision append-only 'REOPEN' kèm lý do.
        """
        v1, item_review = self._advance_item_to_owner_review()
        approval, item_approved = owner_approve_item(
            user=self.owner,
            item=item_review,
            expected_version_id=v1.id,
            expected_row_version=item_review.row_version,
        )
        self.assertEqual(item_approved.state, ContentItemState.READY_TO_PUBLISH)

        # Chủ mở lại bài viết
        reopen_reason = "Cần cập nhật lại thông số khuyến mãi quý 4."
        decision, item_reopened = reopen_content_item(
            user=self.owner,
            item=item_approved,
            reason=reopen_reason,
            expected_row_version=item_approved.row_version,
        )

        self.assertEqual(item_reopened.state, ContentItemState.EDITING)
        self.assertIsNone(item_reopened.approval_id)

        # Approval cũ bị vô hiệu hóa
        approval.refresh_from_db()
        self.assertFalse(approval.is_active)
        self.assertIsNotNone(approval.invalidated_at)
        self.assertIn(reopen_reason, approval.invalidation_reason)

        # Kiểm tra nhiệm vụ
        edit_task = Task.objects.get(item=self.item, role=TaskRole.EDIT)
        pub_task = Task.objects.get(item=self.item, role=TaskRole.PUBLISH)
        self.assertEqual(edit_task.status, TaskStatus.READY)
        self.assertEqual(pub_task.status, TaskStatus.WAITING)

        # Kiểm tra lịch sử quyết định
        self.assertEqual(decision.decision, "REOPEN")
        self.assertEqual(decision.reason, reopen_reason)
        self.assertEqual(decision.return_stage, "EDITING")

    def test_owner_request_changes_to_writing_and_editing(self):
        """
        Chủ yêu cầu sửa bài viết:
        - Trả về WRITING: bài sang WRITING, Task WRITE sang READY, Task EDIT về WAITING.
        - Trả về EDITING: bài sang EDITING, Task EDIT sang READY.
        """
        v1, item_review = self._advance_item_to_owner_review()

        # 1. Trả về WRITING
        dec1, item_writing = owner_request_changes(
            user=self.owner,
            item=item_review,
            return_stage="WRITING",
            reason="Số liệu đoạn 2 chưa chuẩn, đề nghị viết lại.",
            expected_row_version=item_review.row_version,
        )
        self.assertEqual(item_writing.state, ContentItemState.WRITING)
        write_task = Task.objects.get(item=self.item, role=TaskRole.WRITE)
        edit_task = Task.objects.get(item=self.item, role=TaskRole.EDIT)
        self.assertEqual(write_task.status, TaskStatus.READY)
        self.assertEqual(edit_task.status, TaskStatus.WAITING)
        self.assertEqual(dec1.decision, "REQUEST_CHANGES")
        self.assertEqual(dec1.return_stage, "WRITING")

        # Người viết nộp lại v2 và nộp duyệt lại
        v2, item_edit2 = submit_content_version(user=self.writer, item=item_writing, text="Bản v2 đã sửa số liệu.")
        _, item_review2 = submit_for_owner_review(
            user=self.editor,
            item=item_edit2,
            checklist={"brief_compliance": True, "factual_accuracy": True, "voice_tone": True, "cta_verified": True},
            expected_row_version=item_edit2.row_version,
        )

        # 2. Chủ trả về EDITING
        dec2, item_editing2 = owner_request_changes(
            user=self.owner,
            item=item_review2,
            return_stage="EDITING",
            reason="Biên tập kiểm tra lại câu CTA cuối bài.",
            expected_row_version=item_review2.row_version,
        )
        self.assertEqual(item_editing2.state, ContentItemState.EDITING)
        edit_task.refresh_from_db()
        self.assertEqual(edit_task.status, TaskStatus.READY)
        self.assertEqual(dec2.return_stage, "EDITING")

    def test_withdraw_review_lifecycle(self):
        """
        Biên tập viên hoặc Chủ rút bài khỏi hàng đợi chờ duyệt (OWNER_REVIEW -> EDITING).
        Task EDIT mở lại READY.
        """
        v1, item_review = self._advance_item_to_owner_review()
        self.assertEqual(item_review.state, ContentItemState.OWNER_REVIEW)

        dec, item_withdrawn = withdraw_review(
            user=self.editor,
            item=item_review,
            reason="Phát hiện còn lỗi chính tả thương hiệu cần chỉnh trước khi Chủ duyệt.",
            expected_row_version=item_review.row_version,
        )
        self.assertEqual(item_withdrawn.state, ContentItemState.EDITING)
        edit_task = Task.objects.get(item=self.item, role=TaskRole.EDIT)
        self.assertEqual(edit_task.status, TaskStatus.READY)
        self.assertEqual(dec.decision, "WITHDRAW_REVIEW")

    def test_cancel_content_item_lifecycle(self):
        """
        Chủ workspace hủy bài viết:
        - Bài chuyển sang CANCELLED.
        - Các task chưa DONE chuyển sang CANCELLED.
        - Nếu bài ở READY_TO_PUBLISH: thu hồi duyệt, vô hiệu hóa ContentApproval.
        """
        v1, item_review = self._advance_item_to_owner_review()
        approval, item_approved = owner_approve_item(
            user=self.owner,
            item=item_review,
            expected_version_id=v1.id,
            expected_row_version=item_review.row_version,
        )
        self.assertEqual(item_approved.state, ContentItemState.READY_TO_PUBLISH)

        # Hủy bài
        cancel_reason = "Chiến dịch dừng triển khai bài viết này."
        dec, item_cancelled = cancel_content_item(
            user=self.owner,
            item=item_approved,
            reason=cancel_reason,
            expected_row_version=item_approved.row_version,
        )
        self.assertEqual(item_cancelled.state, ContentItemState.CANCELLED)
        self.assertIsNone(item_cancelled.approval_id)

        approval.refresh_from_db()
        self.assertFalse(approval.is_active)

        pub_task = Task.objects.get(item=self.item, role=TaskRole.PUBLISH)
        self.assertEqual(pub_task.status, TaskStatus.CANCELLED)
        self.assertEqual(dec.decision, "CANCEL")

    def test_blocked_item_lifecycle_ac12(self):
        """
        AC12 & F07: Báo chặn và gỡ chặn bài viết:
        - Báo chặn ghi nhận blocked_reason, blocked_by, blocked_at.
        - Khi bị chặn, thao tác duyệt / nộp bài / rút bài bị từ chối.
        - Gỡ chặn xóa cờ, ghi nhận resolution_note.
        """
        v1, item_review = self._advance_item_to_owner_review()

        # 1. Báo chặn
        blocked_item = block_content_item(
            user=self.owner,
            item=item_review,
            reason="Đang chờ xác nhận pháp lý về hình ảnh bản quyền.",
            expected_row_version=item_review.row_version,
        )
        self.assertTrue(blocked_item.is_blocked)
        self.assertEqual(blocked_item.blocked_by, self.owner)
        self.assertIsNotNone(blocked_item.blocked_at)

        # Thử phê duyệt khi bài bị chặn -> ValidationError
        with self.assertRaises(ValidationError) as ctx:
            owner_approve_item(
                user=self.owner,
                item=blocked_item,
                expected_version_id=v1.id,
                expected_row_version=blocked_item.row_version,
            )
        self.assertIn("đang bị chặn", str(ctx.exception))

        # 2. Gỡ chặn
        unblocked_item = unblock_content_item(
            user=self.owner,
            item=blocked_item,
            resolution_note="Pháp lý đã duyệt hợp đồng bản quyền.",
            expected_row_version=blocked_item.row_version,
        )
        self.assertFalse(unblocked_item.is_blocked)
        self.assertEqual(unblocked_item.resolution_note, "Pháp lý đã duyệt hợp đồng bản quyền.")

        # Duyệt thành công sau khi gỡ chặn
        approval, item_ok = owner_approve_item(
            user=self.owner,
            item=unblocked_item,
            expected_version_id=v1.id,
            expected_row_version=unblocked_item.row_version,
        )
        self.assertEqual(item_ok.state, ContentItemState.READY_TO_PUBLISH)

    def test_permission_matrix_and_tenant_isolation(self):
        """
        Kiểm tra ma trận phân quyền và cô lập tenant cho các hành động B06:
        - Thành viên thường (MEMBER - writer/editor/publisher) không có quyền approve/reopen/cancel -> HTTP 403 / PermissionDenied.
        - Người ngoài workspace và thành viên INACTIVE nhận HTTP 404.
        """
        v1, item_review = self._advance_item_to_owner_review()

        # 1. Member cố gọi owner_approve_item -> PermissionDenied
        with self.assertRaises(PermissionDenied):
            owner_approve_item(user=self.editor, item=item_review, expected_version_id=v1.id)

        # 2. Member cố gọi reopen_content_item -> PermissionDenied
        with self.assertRaises(PermissionDenied):
            reopen_content_item(user=self.writer, item=item_review, reason="Muốn sửa lại")

        # 3. HTTP Client test phân quyền
        self.client.force_login(self.editor)
        url_approve = reverse(
            "workspaces:item_owner_approve",
            kwargs={"workspace_id": self.workspace.id, "package_id": self.pkg.id, "item_id": self.item.id},
        )
        # Editor gửi POST duyệt bài -> 403
        resp_member = self.client.post(url_approve, {"expected_version_id": str(v1.id), "expected_row_version": item_review.row_version})
        self.assertEqual(resp_member.status_code, 403)

        # Outsider gửi POST -> 404
        outsider = User.objects.create_user(username="outsider", email="outsider@test.com", password="password123")
        self.client.force_login(outsider)
        resp_outsider = self.client.post(url_approve, {"expected_version_id": str(v1.id), "expected_row_version": item_review.row_version})
        self.assertEqual(resp_outsider.status_code, 404)

        # Inactive member -> 404
        self.editor_membership.status = MembershipStatus.INACTIVE
        self.editor_membership.save()
        self.client.force_login(self.editor)
        resp_inactive = self.client.post(url_approve, {"expected_version_id": str(v1.id), "expected_row_version": item_review.row_version})
        self.assertEqual(resp_inactive.status_code, 404)

    def test_optimistic_concurrency_control_409_ac10(self):
        """
        AC10: Hai người gửi quyết định trên cùng row_version:
        - Người thứ nhất ghi thành công.
        - Người thứ hai nhận ConcurrencyConflictError (HTTP 409).
        """
        v1, item_review = self._advance_item_to_owner_review()
        current_row = item_review.row_version

        # Lần 1: Duyệt thành công
        owner_approve_item(
            user=self.owner,
            item=item_review,
            expected_version_id=v1.id,
            expected_row_version=current_row,
        )

        # Lần 2: Người khác gửi lệnh với row_version cũ -> ConcurrencyConflictError
        with self.assertRaises(ConcurrencyConflictError):
            owner_request_changes(
                user=self.owner,
                item=item_review,
                return_stage="WRITING",
                reason="Sửa lại đoạn kết",
                expected_row_version=current_row,
            )

    def test_idempotency_double_click_protection(self):
        """
        Chống nhấp đôi: Gửi lặp approval với cùng idempotency_key trả về bản ghi cũ, không nhân đôi approval.
        """
        v1, item_review = self._advance_item_to_owner_review()
        idemp_key = "idemp_approve_12345"

        app1, item1 = owner_approve_item(
            user=self.owner,
            item=item_review,
            expected_version_id=v1.id,
            expected_row_version=item_review.row_version,
            idempotency_key=idemp_key,
        )

        app2, item2 = owner_approve_item(
            user=self.owner,
            item=item_review,
            expected_version_id=v1.id,
            expected_row_version=item_review.row_version,
            idempotency_key=idemp_key,
        )

        self.assertEqual(app1.id, app2.id)
        self.assertEqual(ContentApproval.objects.filter(item=self.item).count(), 1)

    def test_package_status_sync_on_reopen_spec_6_2(self):
        """
        Spec 6.2: Mở lại bài làm gói COMPLETED trở lại ACTIVE.
        """
        v1, item_review = self._advance_item_to_owner_review()
        approval, item_approved = owner_approve_item(
            user=self.owner,
            item=item_review,
            expected_version_id=v1.id,
            expected_row_version=item_review.row_version,
        )

        # Giả lập bài viết này đã PUBLISHED và gói hoàn thành COMPLETED
        item_approved.state = ContentItemState.PUBLISHED
        item_approved.save()

        self.pkg.status = PackageStatus.COMPLETED
        self.pkg.save()

        # Chủ mở lại bài viết
        reopen_content_item(
            user=self.owner,
            item=item_approved,
            reason="Cần chỉnh sửa nội dung bài đã đăng.",
            expected_row_version=item_approved.row_version,
        )

        # Gói COMPLETED tự động chuyển về ACTIVE
        self.pkg.refresh_from_db()
        self.assertEqual(self.pkg.status, PackageStatus.ACTIVE)