"""
Bộ kiểm thử Milestone B08 — Đổi người phân công, thu hồi thành viên và hoàn thiện ngoại lệ.
Spec tham chiếu: Bản 1.1 · 12/10/2026 (mục 3.1, 3.2, 5 F07, 6.1, 6.2, 6.3, 7 UI03/UI05, 9, 10, 13 B08, 14 AC10, AC11, AC12).
"""
import uuid
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.workspaces.models import (
    AccessRole,
    AssignmentHistory,
    AssignmentRole,
    ContentItem,
    ContentItemState,
    ContentVersion,
    EmploymentType,
    Membership,
    MembershipStatus,
    Package,
    PackageStatus,
    Task,
    TaskRole,
    TaskStatus,
)
from apps.workspaces.services import (
    ConcurrencyConflictError,
    add_content_item,
    approve_plan,
    block_content_item,
    cancel_content_item,
    create_package,
    create_workspace_with_owner,
    deactivate_membership,
    reassign_item_assignment,
    start_writing_task,
    submit_content_version,
)

User = get_user_model()


class ReassignmentAndDeactivationB08Tests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner_b08", email="owner_b08@test.com", password="password123",
        )
        self.workspace = create_workspace_with_owner(
            user=self.owner, name="Doanh nghiệp Bàn giao B08", timezone_str="Asia/Ho_Chi_Minh",
        )
        self.owner_membership = Membership.objects.get(workspace=self.workspace, user=self.owner)

        self.coordinator = User.objects.create_user(
            username="coord_b08", email="coord_b08@test.com", password="password123",
        )
        self.coordinator_membership = Membership.objects.create(
            workspace=self.workspace, user=self.coordinator, access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE, status=MembershipStatus.ACTIVE,
        )

        self.writer = User.objects.create_user(username="writer_b08", email="writer_b08@test.com", password="password123")
        self.writer_membership = Membership.objects.create(
            workspace=self.workspace, user=self.writer, access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.FREELANCER, status=MembershipStatus.ACTIVE,
        )

        self.editor = User.objects.create_user(username="editor_b08", email="editor_b08@test.com", password="password123")
        self.editor_membership = Membership.objects.create(
            workspace=self.workspace, user=self.editor, access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.FREELANCER, status=MembershipStatus.ACTIVE,
        )

        self.publisher = User.objects.create_user(username="pub_b08", email="pub_b08@test.com", password="password123")
        self.publisher_membership = Membership.objects.create(
            workspace=self.workspace, user=self.publisher, access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE, status=MembershipStatus.ACTIVE,
        )

        self.replacement = User.objects.create_user(username="replace_b08", email="replace_b08@test.com", password="password123")
        self.replacement_membership = Membership.objects.create(
            workspace=self.workspace, user=self.replacement, access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE, status=MembershipStatus.ACTIVE,
        )

        self.now = timezone.now()
        self.pkg = create_package(
            user=self.owner, workspace=self.workspace, name="Gói B08",
            objective="Mục tiêu", channel="FACEBOOK",
            start_date=self.now.date(), end_date=(self.now + timedelta(days=30)).date(),
            coordinator_membership=self.coordinator_membership,
        )

        self.item = add_content_item(
            user=self.owner, package=self.pkg, title="Bài B08",
            brief="Brief", cta="CTA",
            writing_deadline=self.now + timedelta(days=2),
            editing_deadline=self.now + timedelta(days=5),
            review_deadline=self.now + timedelta(days=7),
            planned_publish_at=self.now + timedelta(days=10),
            writer_membership=self.writer_membership,
            editor_membership=self.editor_membership,
            publisher_membership=self.publisher_membership,
        )

        self.pkg, self.approval, self.tasks = approve_plan(user=self.owner, package=self.pkg)
        self.item.refresh_from_db()

        self.other_owner = User.objects.create_user(username="other_owner_b08", email="other_b08@test.com", password="password123")
        self.other_workspace = create_workspace_with_owner(user=self.other_owner, name="Workspace Khác")
        self.other_member = User.objects.create_user(username="other_member_b08", email="other_m_b08@test.com", password="password123")
        self.other_membership = Membership.objects.create(
            workspace=self.other_workspace,
            user=self.other_member,
            access_role=AccessRole.MEMBER,
            status=MembershipStatus.ACTIVE,
        )

    def test_reassign_write_role_synchronizes_content_item_and_task(self):
        """Đổi người viết: cập nhật writer_membership và Task WRITE. Task status không reset."""
        task_write = Task.objects.get(item=self.item, role=TaskRole.WRITE)
        self.assertEqual(task_write.assignee_membership, self.writer_membership)
        self.assertEqual(task_write.status, TaskStatus.READY)

        history, updated_item = reassign_item_assignment(
            user=self.owner, item=self.item, role=TaskRole.WRITE,
            new_assignee_membership=self.replacement_membership,
            reason="Người viết cũ bận đột xuất, bàn giao cho nhân sự mới.",
            expected_row_version=self.item.row_version,
        )

        self.assertEqual(updated_item.writer_membership, self.replacement_membership)
        task_write.refresh_from_db()
        self.assertEqual(task_write.assignee_membership, self.replacement_membership)
        self.assertEqual(task_write.status, TaskStatus.READY)
        self.assertEqual(history.role, AssignmentRole.WRITE)
        self.assertEqual(history.previous_assignee, self.writer_membership)
        self.assertEqual(history.new_assignee, self.replacement_membership)
        self.assertEqual(history.reassigned_by, self.owner)

    def test_reassign_edit_and_publish_roles(self):
        """Đổi người biên tập và xuất bản: đồng bộ Task EDIT và PUBLISH tương ứng."""
        task_edit = Task.objects.get(item=self.item, role=TaskRole.EDIT)
        h1, it1 = reassign_item_assignment(
            user=self.owner, item=self.item, role=TaskRole.EDIT,
            new_assignee_membership=self.replacement_membership,
            reason="Đổi biên tập viên chuyên môn sâu hơn.",
            expected_row_version=self.item.row_version,
        )
        self.assertEqual(it1.editor_membership, self.replacement_membership)
        task_edit.refresh_from_db()
        self.assertEqual(task_edit.assignee_membership, self.replacement_membership)
        self.assertEqual(task_edit.status, TaskStatus.WAITING)

        task_pub = Task.objects.get(item=it1, role=TaskRole.PUBLISH)
        h2, it2 = reassign_item_assignment(
            user=self.owner, item=it1, role=TaskRole.PUBLISH,
            new_assignee_membership=self.replacement_membership,
            reason="Bàn giao người xuất bản.",
            expected_row_version=it1.row_version,
        )
        self.assertEqual(it2.publisher_membership, self.replacement_membership)
        task_pub.refresh_from_db()
        self.assertEqual(task_pub.assignee_membership, self.replacement_membership)
        self.assertEqual(task_pub.status, TaskStatus.WAITING)

    def test_reassign_by_package_coordinator_allowed_in_own_package(self):
        """Điều phối viên được gán cho gói có quyền đổi người trong gói phụ trách (Spec 3.1)."""
        history, updated_item = reassign_item_assignment(
            user=self.coordinator, item=self.item, role=TaskRole.WRITE,
            new_assignee_membership=self.replacement_membership,
            reason="Điều phối viên sắp xếp lại người viết.",
            expected_row_version=self.item.row_version,
        )
        self.assertEqual(updated_item.writer_membership, self.replacement_membership)
        self.assertEqual(history.reassigned_by, self.coordinator)

    def test_reassign_coordinator_denied_in_other_package(self):
        """Điều phối viên không phụ trách gói khác thì bị từ chối PermissionDenied."""
        pkg2 = create_package(
            user=self.owner, workspace=self.workspace, name="Gói 2",
            objective="Mục tiêu", channel="FACEBOOK",
            start_date=self.now.date(), end_date=(self.now + timedelta(days=20)).date(),
            coordinator_membership=self.owner_membership,
        )
        item2 = add_content_item(
            user=self.owner, package=pkg2, title="Bài gói 2", brief="Brief", cta="CTA",
            writing_deadline=self.now + timedelta(days=2), editing_deadline=self.now + timedelta(days=4),
            review_deadline=self.now + timedelta(days=6), planned_publish_at=self.now + timedelta(days=8),
            writer_membership=self.writer_membership, editor_membership=self.editor_membership,
            publisher_membership=self.publisher_membership,
        )
        with self.assertRaises(PermissionDenied):
            reassign_item_assignment(
                user=self.coordinator, item=item2, role=TaskRole.WRITE,
                new_assignee_membership=self.replacement_membership,
                reason="Thử đổi người ở gói khác", expected_row_version=item2.row_version,
            )

    def test_reassign_by_regular_member_denied(self):
        """Thành viên thường (kể cả writer/editor của bài) không có quyền đổi người (Spec 3.1)."""
        with self.assertRaises(PermissionDenied):
            reassign_item_assignment(
                user=self.writer, item=self.item, role=TaskRole.WRITE,
                new_assignee_membership=self.replacement_membership,
                reason="Tự bàn giao việc", expected_row_version=self.item.row_version,
            )
    def test_reassign_outsider_and_inactive_actor_denied(self):
        """Người dùng ngoài workspace hoặc thành viên bị INACTIVE bị từ chối đổi người."""
        with self.assertRaises(PermissionDenied):
            reassign_item_assignment(
                user=self.other_member, item=self.item, role=TaskRole.WRITE,
                new_assignee_membership=self.replacement_membership,
                reason="Outsider thử đổi người", expected_row_version=self.item.row_version,
            )

        self.coordinator_membership.status = MembershipStatus.INACTIVE
        self.coordinator_membership.save(update_fields=["status"])
        with self.assertRaises(PermissionDenied):
            reassign_item_assignment(
                user=self.coordinator, item=self.item, role=TaskRole.WRITE,
                new_assignee_membership=self.replacement_membership,
                reason="Inactive coordinator thử đổi", expected_row_version=self.item.row_version,
            )

    def test_reassign_new_assignee_invalid_workspace_or_inactive_or_same_rejected(self):
        """Người nhận mới phải thuộc cùng workspace, đang ACTIVE, và khác người hiện tại."""
        with self.assertRaises(ValidationError) as ctx1:
            reassign_item_assignment(
                user=self.owner, item=self.item, role=TaskRole.WRITE,
                new_assignee_membership=self.other_membership,
                reason="Giao cho người workspace khác", expected_row_version=self.item.row_version,
            )
        self.assertIn("cùng workspace", str(ctx1.exception))

        self.replacement_membership.status = MembershipStatus.INACTIVE
        self.replacement_membership.save(update_fields=["status"])
        with self.assertRaises(ValidationError) as ctx2:
            reassign_item_assignment(
                user=self.owner, item=self.item, role=TaskRole.WRITE,
                new_assignee_membership=self.replacement_membership,
                reason="Giao cho người đã bị vô hiệu", expected_row_version=self.item.row_version,
            )
        self.assertIn("ACTIVE", str(ctx2.exception))
        self.replacement_membership.status = MembershipStatus.ACTIVE
        self.replacement_membership.save(update_fields=["status"])

        with self.assertRaises(ValidationError) as ctx3:
            reassign_item_assignment(
                user=self.owner, item=self.item, role=TaskRole.WRITE,
                new_assignee_membership=self.writer_membership,
                reason="Đổi cho chính người hiện tại", expected_row_version=self.item.row_version,
            )
        self.assertIn("khác người đang chịu trách nhiệm", str(ctx3.exception))

    def test_reassign_missing_reason_and_cancelled_item_rejected(self):
        """Thiếu lý do hoặc bài đã CANCELLED thì bị từ chối ValidationError."""
        with self.assertRaises(ValidationError):
            reassign_item_assignment(
                user=self.owner, item=self.item, role=TaskRole.WRITE,
                new_assignee_membership=self.replacement_membership,
                reason="", expected_row_version=self.item.row_version,
            )

        cancel_content_item(user=self.owner, item=self.item, reason="Hủy bài kiểm thử")
        self.item.refresh_from_db()
        with self.assertRaises(ValidationError) as ctx:
            reassign_item_assignment(
                user=self.owner, item=self.item, role=TaskRole.WRITE,
                new_assignee_membership=self.replacement_membership,
                reason="Thử đổi người cho bài đã hủy", expected_row_version=self.item.row_version,
            )
        self.assertIn("đã bị hủy", str(ctx.exception))

    def test_reassign_occ_conflict_409_ac10(self):
        """Optimistic Concurrency Control: Lệch expected_row_version trả 409 (AC10)."""
        stale_version = self.item.row_version - 1
        with self.assertRaises(ConcurrencyConflictError):
            reassign_item_assignment(
                user=self.owner, item=self.item, role=TaskRole.WRITE,
                new_assignee_membership=self.replacement_membership,
                reason="OCC mismatch test", expected_row_version=stale_version,
            )
        self.item.refresh_from_db()
        self.assertEqual(self.item.writer_membership, self.writer_membership)

    def test_reassign_idempotency_ac10(self):
        """Khóa Idempotency Key: Request gửi lặp trả về bản ghi cũ, không nhân bản (AC10)."""
        idemp = f"reassign_test_{uuid.uuid4()}"
        row_v_before = self.item.row_version
        h1, it1 = reassign_item_assignment(
            user=self.owner, item=self.item, role=TaskRole.WRITE,
            new_assignee_membership=self.replacement_membership,
            reason="Lần bấm thứ nhất", expected_row_version=row_v_before, idempotency_key=idemp,
        )
        h2, it2 = reassign_item_assignment(
            user=self.owner, item=self.item, role=TaskRole.WRITE,
            new_assignee_membership=self.replacement_membership,
            reason="Lần bấm thứ hai lặp lại", expected_row_version=row_v_before, idempotency_key=idemp,
        )
        self.assertEqual(h1.id, h2.id)
        self.assertEqual(AssignmentHistory.objects.filter(item=self.item, idempotency_key=idemp).count(), 1)
        self.item.refresh_from_db()
        self.assertEqual(self.item.row_version, row_v_before + 1)

    def test_reassign_preserves_historical_authors_versions_and_decisions(self):
        """Bàn giao không sửa author ContentVersion, không sinh phiên bản hay quyết định tự động."""
        start_writing_task(user=self.writer, item=self.item)
        self.item.refresh_from_db()
        v1, _ = submit_content_version(
            user=self.writer, item=self.item, text="Nội dung ban đầu của người viết cũ",
            expected_row_version=self.item.row_version,
        )
        self.item.refresh_from_db()
        self.assertEqual(v1.author_membership, self.writer_membership)
        version_count_before = ContentVersion.objects.filter(item=self.item).count()

        reassign_item_assignment(
            user=self.owner, item=self.item, role=TaskRole.WRITE,
            new_assignee_membership=self.replacement_membership,
            reason="Bàn giao sau khi đã có draft v1", expected_row_version=self.item.row_version,
        )
        v1.refresh_from_db()
        self.assertEqual(v1.author_membership, self.writer_membership)
        self.assertEqual(ContentVersion.objects.filter(item=self.item).count(), version_count_before)

    def test_reassign_preserves_blocker_state_ac12(self):
        """Bài BLOCKED vẫn đổi được người; cờ bị chặn được giữ nguyên, không tự gỡ blocker (AC12)."""
        block_content_item(
            user=self.writer, item=self.item, reason="Thiếu thông tin thương hiệu",
            expected_row_version=self.item.row_version,
        )
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_blocked)

        reassign_item_assignment(
            user=self.owner, item=self.item, role=TaskRole.WRITE,
            new_assignee_membership=self.replacement_membership,
            reason="Bàn giao người viết khi đang bị chặn", expected_row_version=self.item.row_version,
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.writer_membership, self.replacement_membership)
        self.assertTrue(self.item.is_blocked)
        self.assertEqual(self.item.blocked_reason, "Thiếu thông tin thương hiệu")

    def test_deactivate_member_with_no_open_tasks_success(self):
        """Thu hồi thành viên không còn nhiệm vụ mở thì thành công trực tiếp."""
        deactivate_membership(user=self.owner, workspace=self.workspace, membership=self.replacement_membership)
        self.replacement_membership.refresh_from_db()
        self.assertEqual(self.replacement_membership.status, MembershipStatus.INACTIVE)

    def test_deactivate_member_with_open_tasks_without_replacement_rejected_ac11(self):
        """Thành viên có nhiệm vụ mở nhưng không có người thay thế bị từ chối ValidationError (AC11)."""
        task_write = Task.objects.get(item=self.item, role=TaskRole.WRITE)
        self.assertEqual(task_write.status, TaskStatus.READY)

        with self.assertRaises(ValidationError) as ctx:
            deactivate_membership(
                user=self.owner, workspace=self.workspace, membership=self.writer_membership,
            )
        self.assertIn("trách nhiệm mở", str(ctx.exception))
        self.assertIn("AC11", str(ctx.exception))

        self.writer_membership.refresh_from_db()
        self.assertEqual(self.writer_membership.status, MembershipStatus.ACTIVE)
        task_write.refresh_from_db()
        self.assertEqual(task_write.assignee_membership, self.writer_membership)

    def test_deactivate_member_with_open_tasks_reassigns_atomically_ac11(self):
        """Thu hồi thành viên có nhiệm vụ mở: bàn giao nguyên tử cho người thay thế và vô hiệu hóa (AC11)."""
        task_write = Task.objects.get(item=self.item, role=TaskRole.WRITE)
        self.assertEqual(task_write.assignee_membership, self.writer_membership)

        deactivate_membership(
            user=self.owner,
            workspace=self.workspace,
            membership=self.writer_membership,
            replacement_membership=self.replacement_membership,
            reason="Nhân viên nghỉ việc, chuyển giao trách nhiệm",
        )

        self.writer_membership.refresh_from_db()
        self.assertEqual(self.writer_membership.status, MembershipStatus.INACTIVE)
        task_write.refresh_from_db()
        self.assertEqual(task_write.assignee_membership, self.replacement_membership)
        self.item.refresh_from_db()
        self.assertEqual(self.item.writer_membership, self.replacement_membership)

        history = AssignmentHistory.objects.filter(item=self.item, role=AssignmentRole.WRITE).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.previous_assignee, self.writer_membership)
        self.assertEqual(history.new_assignee, self.replacement_membership)
        self.assertIn("Nhân viên nghỉ việc", history.reason)

    def test_deactivate_member_reassigns_to_owner(self):
        """Chủ workspace có thể tạm chuyển giao trách nhiệm mở cho chính mình (Spec 3.2)."""
        deactivate_membership(
            user=self.owner,
            workspace=self.workspace,
            membership=self.writer_membership,
            replacement_membership=self.owner_membership,
            reason="Chủ workspace tạm thời tiếp quản công việc viết bài",
        )
        self.writer_membership.refresh_from_db()
        self.assertEqual(self.writer_membership.status, MembershipStatus.INACTIVE)
        self.item.refresh_from_db()
        self.assertEqual(self.item.writer_membership, self.owner_membership)
    def test_deactivate_member_reassigns_unstarted_draft_items_and_package_coord(self):
        """Bàn giao bài viết ở gói DRAFT (chưa sinh task) và quyền điều phối gói khi thu hồi (AC11)."""
        pkg_draft = create_package(
            user=self.owner, workspace=self.workspace, name="Gói Nháp",
            objective="Mục tiêu nháp", channel="FACEBOOK",
            start_date=self.now.date(), end_date=(self.now + timedelta(days=15)).date(),
            coordinator_membership=self.coordinator_membership,
        )
        item_draft = add_content_item(
            user=self.owner, package=pkg_draft, title="Bài nháp", brief="Brief", cta="CTA",
            writing_deadline=self.now + timedelta(days=2), editing_deadline=self.now + timedelta(days=4),
            review_deadline=self.now + timedelta(days=6), planned_publish_at=self.now + timedelta(days=8),
            writer_membership=self.writer_membership, editor_membership=self.editor_membership,
            publisher_membership=self.publisher_membership,
        )

        deactivate_membership(
            user=self.owner, workspace=self.workspace, membership=self.coordinator_membership,
            replacement_membership=self.replacement_membership, reason="Điều phối viên nghỉ việc",
        )
        self.coordinator_membership.refresh_from_db()
        self.assertEqual(self.coordinator_membership.status, MembershipStatus.INACTIVE)
        pkg_draft.refresh_from_db()
        self.assertEqual(pkg_draft.coordinator_membership, self.replacement_membership)
        self.pkg.refresh_from_db()
        self.assertEqual(self.pkg.coordinator_membership, self.replacement_membership)

    def test_deactivate_member_invalid_replacement_rejected(self):
        """Người nhận thay thế bị INACTIVE, khác workspace, hoặc chính người bị thu hồi thì bị từ chối."""
        self.replacement_membership.status = MembershipStatus.INACTIVE
        self.replacement_membership.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            deactivate_membership(
                user=self.owner, workspace=self.workspace, membership=self.writer_membership,
                replacement_membership=self.replacement_membership,
            )

        with self.assertRaises(ValidationError):
            deactivate_membership(
                user=self.owner, workspace=self.workspace, membership=self.writer_membership,
                replacement_membership=self.other_membership,
            )

        with self.assertRaises(ValidationError):
            deactivate_membership(
                user=self.owner, workspace=self.workspace, membership=self.writer_membership,
                replacement_membership=self.writer_membership,
            )

    def test_deactivate_owner_strictly_prevented(self):
        """Tuyệt đối không cho phép vô hiệu hóa Chủ workspace (Single Owner guard)."""
        with self.assertRaises(ValidationError) as ctx:
            deactivate_membership(
                user=self.owner, workspace=self.workspace, membership=self.owner_membership,
            )
        self.assertIn("Không thể vô hiệu hóa Chủ", str(ctx.exception))

    def test_deactivated_member_loses_workspace_access_immediately(self):
        """Thành viên bị vô hiệu hóa lập tức bị từ chối truy cập (404 / inactive) (Spec 3.2)."""
        client = self.client
        client.force_login(self.writer)

        resp_before = client.get(reverse("workspaces:detail", kwargs={"workspace_id": self.workspace.id}))
        self.assertEqual(resp_before.status_code, 200)

        deactivate_membership(
            user=self.owner, workspace=self.workspace, membership=self.writer_membership,
            replacement_membership=self.replacement_membership, reason="Offboarding",
        )

        resp_after = client.get(reverse("workspaces:detail", kwargs={"workspace_id": self.workspace.id}))
        self.assertEqual(resp_after.status_code, 404)

    def test_view_reassign_post_success_and_validations(self):
        """Kiểm thử View HTTP POST ContentItemReassignView: 302 chuyển hướng, 400 validation, 409 conflict."""
        client = self.client
        client.force_login(self.owner)

        reassign_url = reverse(
            "workspaces:item_assignments",
            kwargs={"workspace_id": self.workspace.id, "package_id": self.pkg.id, "item_id": self.item.id},
        )

        # 1. POST thành công -> 302 redirect
        resp_ok = client.post(
            reassign_url,
            {
                "role": TaskRole.WRITE,
                "new_assignee": str(self.replacement_membership.id),
                "reason": "View test reassign",
                "expected_row_version": self.item.row_version,
            },
        )
        self.assertEqual(resp_ok.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.writer_membership, self.replacement_membership)

        # 2. POST thiếu lý do -> 400 Bad Request
        resp_err = client.post(
            reassign_url,
            {
                "role": TaskRole.EDIT,
                "new_assignee": str(self.replacement_membership.id),
                "reason": "",
                "expected_row_version": self.item.row_version,
            },
        )
        self.assertEqual(resp_err.status_code, 400)

        # 3. POST sai row_version -> 409 Conflict
        resp_409 = client.post(
            reassign_url,
            {
                "role": TaskRole.EDIT,
                "new_assignee": str(self.replacement_membership.id),
                "reason": "Lý do đúng nhưng version sai",
                "expected_row_version": self.item.row_version - 1,
            },
        )
        self.assertEqual(resp_409.status_code, 409)

    def test_view_member_deactivate_get_and_post(self):
        """Kiểm thử View HTTP MemberDeactivateView: GET hiển thị danh sách việc cần chuyển, POST vô hiệu."""
        client = self.client
        client.force_login(self.owner)

        deactivate_url = reverse(
            "workspaces:member_deactivate",
            kwargs={"workspace_id": self.workspace.id, "membership_id": self.writer_membership.id},
        )

        # 1. GET -> 200 OK và chứa thông tin nhiệm vụ mở
        resp_get = client.get(deactivate_url)
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, "Bài B08")

        # 2. POST thiếu replacement khi còn việc mở -> 400
        resp_bad = client.post(deactivate_url, {"replacement_membership": "", "reason": "Thiếu người"})
        self.assertEqual(resp_bad.status_code, 400)

        # 3. POST có replacement -> 302 redirect
        resp_post = client.post(
            deactivate_url,
            {
                "replacement_membership": str(self.replacement_membership.id),
                "reason": "View test deactivation",
            },
        )
        self.assertEqual(resp_post.status_code, 302)
        self.writer_membership.refresh_from_db()
        self.assertEqual(self.writer_membership.status, MembershipStatus.INACTIVE)


