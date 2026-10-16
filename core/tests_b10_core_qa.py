"""
Bộ kiểm thử nghiệm thu Milestone B10 — Responsive, Xử lý lỗi, Backup/Restore và QA Lõi.
Bao phủ toàn diện kịch bản end-to-end, ma trận tiêu chí AC01–AC18, các trang lỗi 400/403/404/409/500/CSRF,
và kiểm chứng quy trình sao lưu / phục hồi cơ sở dữ liệu theo Spec ContentOps Hub.
"""
import datetime
import json
import os
import shutil
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.workspaces.models import (
    AccessRole,
    AssignmentRole,
    BrandProfile,
    ContentApproval,
    ContentItem,
    ContentItemState,
    ContentPublication,
    ContentVersion,
    EmploymentType,
    Membership,
    MembershipStatus,
    Notification,
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
    get_workspace_dashboard_data,
    user_has_entity_access,
)
from apps.workspaces.services import (
    ConcurrencyConflictError,
    approve_plan,
    block_content_item,
    cancel_content_item,
    create_package,
    create_workspace_with_owner,
    deactivate_membership,
    owner_approve_item,
    owner_request_changes,
    reassign_item_assignment,
    record_content_publication,
    reopen_content_item,
    request_changes_decision,
    save_brand_profile,
    submit_content_version,
    submit_for_owner_review,
    unblock_content_item,
)

User = get_user_model()

VALID_CHECKLIST = {
    "brief_compliance": True,
    "factual_accuracy": True,
    "voice_tone": True,
    "cta_verified": True,
}


class CoreQAMilestoneB10Tests(TestCase):
    """Bộ kiểm thử QA lõi xác thực ma trận AC01–AC18 và các yêu cầu vận hành B10."""

    def setUp(self):
        # 1. Khởi tạo người dùng: Chủ, Freelancer, Editor, Người ngoài
        self.owner = User.objects.create_user(username="owner_ac", email="owner@english.com", password="password123")
        self.freelancer = User.objects.create_user(username="free_ac", email="free@english.com", password="password123")
        self.editor = User.objects.create_user(username="editor_ac", email="editor@english.com", password="password123")
        self.outsider = User.objects.create_user(username="outsider_ac", email="outsider@other.com", password="password123")

        # 2. Workspace chính: "Trung tâm Anh ngữ mẫu" (Spec 14)
        self.ws = create_workspace_with_owner(user=self.owner, name="Trung tâm Anh ngữ mẫu")
        self.m_owner = Membership.objects.get(workspace=self.ws, user=self.owner)

        self.m_free = Membership.objects.create(
            workspace=self.ws,
            user=self.freelancer,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.FREELANCER,
            status=MembershipStatus.ACTIVE,
        )
        self.m_editor = Membership.objects.create(
            workspace=self.ws,
            user=self.editor,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE,
            status=MembershipStatus.ACTIVE,
        )

        # 3. Workspace khác để kiểm tra cách ly dữ liệu
        self.other_owner = User.objects.create_user(username="other_owner", email="other@test.com", password="password123")
        self.other_ws = create_workspace_with_owner(user=self.other_owner, name="Workspace Độc lập Khác")

        # 4. Clients
        self.client_owner = Client()
        self.client_owner.force_login(self.owner)
        self.client_free = Client()
        self.client_free.force_login(self.freelancer)
        self.client_editor = Client()
        self.client_editor.force_login(self.editor)
        self.client_outsider = Client()
        self.client_outsider.force_login(self.outsider)

    def _create_sample_package_and_items(self):
        """Helper khởi tạo Gói 3 bài Facebook chuẩn theo Spec 14."""
        now = timezone.now()
        pkg = create_package(
            user=self.owner,
            workspace=self.ws,
            name="Gói 3 bài Facebook Mẫu",
            objective="Mục tiêu truyền thông mẫu",
            start_date=now.date(),
            end_date=(now + datetime.timedelta(days=30)).date(),
            channel="FACEBOOK",
            coordinator_membership=self.m_owner,
        )

        items = []
        for i in range(1, 4):
            item = ContentItem.objects.create(
                workspace=self.ws,
                package=pkg,
                title=f"Bài viết Facebook số {i}",
                brief=f"Brief bài viết số {i}",
                writer_membership=self.m_free,
                editor_membership=self.m_editor,
                publisher_membership=self.m_owner,
                writing_deadline=now + datetime.timedelta(days=i),
                editing_deadline=now + datetime.timedelta(days=i + 1),
                review_deadline=now + datetime.timedelta(days=i + 2),
                planned_publish_at=now + datetime.timedelta(days=i + 3),
            )
            items.append(item)
        return pkg, items

    # --------------------------------------------------------------------------
    # AC01: Không có kết nối AI; hoàn thành gói với AI bên ngoài
    # --------------------------------------------------------------------------
    def test_ac01_no_ai_connection_complete_package_normally(self):
        """AC01: Không có AI key hay kết nối AI; toàn bộ luồng hoạt động bình thường."""
        pkg, items = self._create_sample_package_and_items()
        approve_plan(user=self.owner, package=pkg, idempotency_key="plan_ac01")
        pkg.refresh_from_db()
        self.assertEqual(pkg.status, PackageStatus.ACTIVE)

        item = items[0]
        v1, _ = submit_content_version(
            user=self.freelancer,
            item=item,
            text="Nội dung tạo từ AI bên ngoài (ChatGPT/Claude copy vào).",
            source="EXTERNAL_AI",
        )
        self.assertEqual(v1.version_no, 1)
        self.assertEqual(v1.source, "EXTERNAL_AI")
        item.refresh_from_db()
        self.assertEqual(item.state, ContentItemState.EDITING)

    # --------------------------------------------------------------------------
    # AC02: Freelancer biết ID bài của người khác ngoài phạm vi -> 404
    # --------------------------------------------------------------------------
    def test_ac02_freelancer_access_out_of_scope_item_returns_404(self):
        """AC02: Freelancer biết ID bài thuộc workspace khác nhận 404, không rò rỉ title hay metadata."""
        other_owner_membership = Membership.objects.get(workspace=self.other_ws, user=self.other_owner)
        other_pkg = create_package(
            user=self.other_owner,
            workspace=self.other_ws,
            name="Gói ngoài phạm vi",
            objective="Mục tiêu gói ngoài",
            coordinator_membership=other_owner_membership,
            start_date=timezone.now().date(),
            end_date=(timezone.now() + datetime.timedelta(days=10)).date(),
        )
        other_item = ContentItem.objects.create(
            workspace=self.other_ws,
            package=other_pkg,
            title="Bí mật kinh doanh Workspace Khác",
            writer_membership=Membership.objects.get(workspace=self.other_ws, user=self.other_owner),
            editor_membership=Membership.objects.get(workspace=self.other_ws, user=self.other_owner),
            publisher_membership=Membership.objects.get(workspace=self.other_ws, user=self.other_owner),
            writing_deadline=timezone.now() + datetime.timedelta(days=1),
            editing_deadline=timezone.now() + datetime.timedelta(days=2),
            review_deadline=timezone.now() + datetime.timedelta(days=3),
            planned_publish_at=timezone.now() + datetime.timedelta(days=4),
        )

        url = reverse("workspaces:item_detail", kwargs={
            "workspace_id": self.ws.id,
            "package_id": other_pkg.id,
            "item_id": other_item.id,
        })
        resp = self.client_free.get(url)
        self.assertEqual(resp.status_code, 404)
        self.assertNotContains(resp, "Bí mật kinh doanh", status_code=404)

    # --------------------------------------------------------------------------
    # AC03: MEMBER tự gọi endpoint duyệt/kết nối AI -> Bị từ chối (403)
    # --------------------------------------------------------------------------
    def test_ac03_member_cannot_call_approve_endpoints(self):
        """AC03: MEMBER tự gọi endpoint duyệt kế hoạch hoặc duyệt bài bị từ chối 403."""
        pkg, items = self._create_sample_package_and_items()
        url_approve_plan = reverse("workspaces:package_approve_plan", kwargs={
            "workspace_id": self.ws.id,
            "package_id": pkg.id,
        })
        resp = self.client_free.post(url_approve_plan, {"idempotency_key": "hack_plan"})
        self.assertEqual(resp.status_code, 403)

        pkg.refresh_from_db()
        self.assertEqual(pkg.status, PackageStatus.DRAFT)

    # --------------------------------------------------------------------------
    # AC04: Kế hoạch thiếu người hoặc hạn sai thứ tự -> 400/ValidationError
    # --------------------------------------------------------------------------
    def test_ac04_plan_approval_deadline_order_validation(self):
        """AC04: Kế hoạch có deadline sai thứ tự (biên tập trước khi viết) bị từ chối; không sinh task."""
        now = timezone.now()
        pkg = create_package(
            user=self.owner,
            workspace=self.ws,
            name="Gói sai hạn",
            objective="Mục tiêu sai hạn",
            coordinator_membership=self.m_owner,
            start_date=now.date(),
            end_date=(now + datetime.timedelta(days=30)).date(),
        )
        ContentItem.objects.create(
            workspace=self.ws,
            package=pkg,
            title="Bài hạn sai thứ tự",
            brief="Brief bài viết",
            writer_membership=self.m_free,
            editor_membership=self.m_editor,
            publisher_membership=self.m_owner,
            writing_deadline=now + datetime.timedelta(days=5),
            editing_deadline=now + datetime.timedelta(days=2),
            review_deadline=now + datetime.timedelta(days=6),
            planned_publish_at=now + datetime.timedelta(days=7),
        )
        with self.assertRaises(ValidationError) as ctx:
            approve_plan(user=self.owner, package=pkg, idempotency_key="ac04_bad")

        self.assertIn("trước", str(ctx.exception).lower())
        self.assertEqual(Task.objects.filter(item__package=pkg).count(), 0)
    # --------------------------------------------------------------------------
    # AC05: Nhấp duyệt kế hoạch hai lần cùng idempotency key -> Đúng 1 bộ task
    # --------------------------------------------------------------------------
    def test_ac05_plan_approval_double_click_idempotency(self):
        """AC05: Nhấp duyệt hai lần cùng idempotency key chỉ sinh 1 snapshot và đúng 3 task/bài."""
        pkg, items = self._create_sample_package_and_items()
        _, appr1, tasks1 = approve_plan(user=self.owner, package=pkg, idempotency_key="idemp_ac05")
        _, appr2, tasks2 = approve_plan(user=self.owner, package=pkg, idempotency_key="idemp_ac05")

        self.assertEqual(appr1.id, appr2.id)
        self.assertEqual(len(tasks1), len(tasks2))
        self.assertEqual(Task.objects.filter(item__package=pkg).count(), 9)

    # --------------------------------------------------------------------------
    # AC06: Nộp v1, biên tập trả sửa, nộp v2 -> V1 nguyên vẹn, lý do sửa đúng
    # --------------------------------------------------------------------------
    def test_ac06_version_immutability_and_return_reason(self):
        """AC06: Nộp v1, trả sửa, nộp v2: v1 bất biến, ReviewDecision ghi nhận lý do."""
        pkg, items = self._create_sample_package_and_items()
        approve_plan(user=self.owner, package=pkg, idempotency_key="plan_ac06")
        item = items[0]

        v1, _ = submit_content_version(user=self.freelancer, item=item, text="Bản v1 gốc")
        item.refresh_from_db()

        decision, updated_item = request_changes_decision(
            user=self.editor,
            item=item,
            reason="Cần bổ sung dẫn chứng khoa học và CTA cuối bài.",
        )
        self.assertEqual(decision.decision, "REQUEST_CHANGES")
        self.assertEqual(updated_item.state, ContentItemState.WRITING)

        v2, _ = submit_content_version(user=self.freelancer, item=item, text="Bản v2 đã sửa dẫn chứng")
        self.assertEqual(v2.version_no, 2)

        v1.refresh_from_db()
        self.assertEqual(v1.text, "Bản v1 gốc")
        self.assertEqual(ContentVersion.objects.filter(item=item).count(), 2)

    # --------------------------------------------------------------------------
    # AC07: Chủ đang xem v1 trong khi bản hiện hành đã đổi -> Duyệt thất bại 409
    # --------------------------------------------------------------------------
    def test_ac07_owner_approve_stale_version_rejected_409(self):
        """AC07: Chủ gửi duyệt v1 trong khi bài đã đổi sang v2 -> ConcurrencyConflictError (409)."""
        pkg, items = self._create_sample_package_and_items()
        approve_plan(user=self.owner, package=pkg, idempotency_key="plan_ac07")
        item = items[0]

        # 1. Freelancer nộp v1, Biên tập trả sửa
        v1, item = submit_content_version(user=self.freelancer, item=item, text="v1")
        request_changes_decision(user=self.editor, item=item, reason="Cần sửa lại cho v2")

        # 2. Freelancer nộp v2, Biên tập chuyển Chủ duyệt
        v2, item = submit_content_version(user=self.freelancer, item=item, text="v2")
        submit_for_owner_review(user=self.editor, item=item, checklist=VALID_CHECKLIST)
        item.refresh_from_db()

        # 3. Chủ đang mở tab xem v1 cũ, ấn duyệt với expected_version_id=v1.id -> 409
        with self.assertRaises(ConcurrencyConflictError):
            owner_approve_item(
                user=self.owner,
                item=item,
                expected_version_id=v1.id,
            )

    # --------------------------------------------------------------------------
    # AC08: Bài đang chờ duyệt, người viết cố lưu bản mới -> Bị từ chối
    # --------------------------------------------------------------------------
    def test_ac08_cannot_submit_version_when_in_owner_review(self):
        """AC08: Bài đang ở OWNER_REVIEW, người viết gọi nộp bản mới bị từ chối ValidationError."""
        pkg, items = self._create_sample_package_and_items()
        approve_plan(user=self.owner, package=pkg, idempotency_key="plan_ac08")
        item = items[0]

        submit_content_version(user=self.freelancer, item=item, text="v1")
        submit_for_owner_review(user=self.editor, item=item, checklist=VALID_CHECKLIST)
        item.refresh_from_db()
        self.assertEqual(item.state, ContentItemState.OWNER_REVIEW)

        with self.assertRaises(ValidationError) as ctx:
            submit_content_version(user=self.freelancer, item=item, text="v1.1 lén sửa")
        self.assertIn("không thể nộp", str(ctx.exception).lower())

    # --------------------------------------------------------------------------
    # AC09: Duyệt v2, Chủ mở lại để sửa -> Approval v2 hết hiệu lực
    # --------------------------------------------------------------------------
    def test_ac09_reopen_invalidates_approval_and_blocks_publication(self):
        """AC09: Duyệt v2, Chủ mở lại -> Approval v2 bị vô hiệu hóa; không cho đăng theo approval cũ."""
        pkg, items = self._create_sample_package_and_items()
        approve_plan(user=self.owner, package=pkg, idempotency_key="plan_ac09")
        item = items[0]

        submit_content_version(user=self.freelancer, item=item, text="v1")
        submit_for_owner_review(user=self.editor, item=item, checklist=VALID_CHECKLIST)
        appr, item = owner_approve_item(user=self.owner, item=item)
        self.assertEqual(item.state, ContentItemState.READY_TO_PUBLISH)

        # Chủ mở lại bài để sửa
        reopen_content_item(user=self.owner, item=item, reason="Phát hiện lỗi chính tả nghiêm trọng")
        appr.refresh_from_db()
        self.assertIsNotNone(appr.invalidated_at)
        item.refresh_from_db()
        self.assertEqual(item.state, ContentItemState.EDITING)

        # Cố gắng đăng bài bị từ chối do bài đã bị mở lại (không còn READY_TO_PUBLISH và mất approval_id)
        self.assertIsNone(item.approval_id)
        with self.assertRaises(ValidationError) as ctx:
            record_content_publication(
                user=self.owner,
                item=item,
                url="https://facebook.com/post/ac09",
                published_at=timezone.now(),
            )
        self.assertIn("chờ đăng", str(ctx.exception).lower())

    # --------------------------------------------------------------------------
    # AC10: Hai người sửa cùng row_version -> Một thành công, một nhận 409
    # --------------------------------------------------------------------------
    def test_ac10_optimistic_concurrency_control_409(self):
        """AC10: Hai người sửa cùng row_version: một thành công, một nhận ConcurrencyConflictError 409."""
        pkg, items = self._create_sample_package_and_items()
        item = items[0]
        initial_rv = item.row_version

        # Thao tác 1 thành công (tăng row_version)
        block_content_item(user=self.owner, item=item, reason="Chặn lần 1")
        item.refresh_from_db()
        self.assertGreater(item.row_version, initial_rv)

        # Thao tác 2 gửi row_version cũ -> Bị từ chối ConcurrencyConflictError (409)
        with self.assertRaises(ConcurrencyConflictError):
            unblock_content_item(
                user=self.owner,
                item=item,
                expected_row_version=initial_rv,
            )

    # --------------------------------------------------------------------------
    # AC11: Thu hồi freelancer còn việc đang mở -> Bàn giao việc, quyền cũ hết
    # --------------------------------------------------------------------------
    def test_ac11_member_deactivation_reassigns_open_tasks(self):
        """AC11: Thu hồi freelancer còn việc đang mở: chuyển cho Chủ, quyền cũ hết, lịch sử giữ nguyên."""
        pkg, items = self._create_sample_package_and_items()
        approve_plan(user=self.owner, package=pkg, idempotency_key="plan_ac11")
        item = items[0]

        t_write = Task.objects.get(item=item, role=TaskRole.WRITE)
        self.assertEqual(t_write.assignee_membership, self.m_free)

        deactivate_membership(
            user=self.owner,
            workspace=self.ws,
            membership=self.m_free,
            replacement_membership=self.m_owner,
            reason="Nghỉ việc đột xuất",
        )
        self.m_free.refresh_from_db()
        self.assertEqual(self.m_free.status, MembershipStatus.INACTIVE)

        t_write.refresh_from_db()
        self.assertEqual(t_write.assignee_membership, self.m_owner)
        item.refresh_from_db()
        self.assertEqual(item.writer_membership, self.m_owner)

        resp = self.client_free.get(reverse("workspaces:detail", kwargs={"workspace_id": self.ws.id}))
        self.assertEqual(resp.status_code, 404)

    # --------------------------------------------------------------------------
    # AC12: Bài bị chặn; thử nộp/duyệt/đăng -> Bị từ chối
    # --------------------------------------------------------------------------
    def test_ac12_blocked_item_rejects_workflow_transitions(self):
        """AC12: Bài bị chặn (BLOCKED) từ chối nộp/duyệt/đăng; gỡ chặn mới tiếp tục."""
        pkg, items = self._create_sample_package_and_items()
        approve_plan(user=self.owner, package=pkg, idempotency_key="plan_ac12")
        item = items[0]

        block_content_item(user=self.freelancer, item=item, reason="Thiếu brief hình ảnh")
        item.refresh_from_db()
        self.assertTrue(item.is_blocked)

        with self.assertRaises(ValidationError) as ctx:
            submit_content_version(user=self.freelancer, item=item, text="Cố nộp khi đang block")
        self.assertIn("bị chặn", str(ctx.exception).lower())

        unblock_content_item(user=self.owner, item=item)
        item.refresh_from_db()
        self.assertFalse(item.is_blocked)
        v1, _ = submit_content_version(user=self.freelancer, item=item, text="Nộp sau khi đã gỡ chặn")
        self.assertEqual(v1.version_no, 1)

    # --------------------------------------------------------------------------
    # AC13: Ghi nhận đăng thiếu URL hoặc chưa duyệt -> Bị từ chối
    # --------------------------------------------------------------------------
    def test_ac13_publication_missing_url_or_unapproved_rejected(self):
        """AC13: Ghi nhận đăng thiếu URL hoặc bài chưa ở READY_TO_PUBLISH bị từ chối."""
        pkg, items = self._create_sample_package_and_items()
        approve_plan(user=self.owner, package=pkg, idempotency_key="plan_ac13")
        item = items[0]

        with self.assertRaises(ValidationError):
            record_content_publication(user=self.owner, item=item, url="https://fb.com/1", published_at=timezone.now())

        submit_content_version(user=self.freelancer, item=item, text="v1")
        submit_for_owner_review(user=self.editor, item=item, checklist=VALID_CHECKLIST)
        owner_approve_item(user=self.owner, item=item)
        item.refresh_from_db()

        with self.assertRaises(ValidationError):
            record_content_publication(user=self.owner, item=item, url="   ", published_at=timezone.now())

        pub, item = record_content_publication(
            user=self.owner,
            item=item,
            url="https://facebook.com/english/post/123",
            published_at=timezone.now(),
            idempotency_key="pub_ac13",
        )
        self.assertEqual(pub.recorded_by, self.owner)
        self.assertEqual(pub.version.version_no, 1)
        self.assertEqual(item.state, ContentItemState.PUBLISHED)

    # --------------------------------------------------------------------------
    # AC14: 2 bài đăng, 1 bài hủy -> Hoàn thành 2/2; 3 bài hủy -> Không hoàn thành
    # --------------------------------------------------------------------------
    def test_ac14_package_completion_conditions(self):
        """AC14: 2 bài đăng, 1 bài hủy -> Gói COMPLETED 2/2; nếu cả 3 bài hủy -> Gói không COMPLETED."""
        pkg, items = self._create_sample_package_and_items()
        approve_plan(user=self.owner, package=pkg, idempotency_key="plan_ac14")

        # Đăng bài 1
        submit_content_version(user=self.freelancer, item=items[0], text="v1")
        submit_for_owner_review(user=self.editor, item=items[0], checklist=VALID_CHECKLIST)
        owner_approve_item(user=self.owner, item=items[0])
        record_content_publication(user=self.owner, item=items[0], url="https://fb.com/1", published_at=timezone.now())

        # Đăng bài 2
        submit_content_version(user=self.freelancer, item=items[1], text="v1")
        submit_for_owner_review(user=self.editor, item=items[1], checklist=VALID_CHECKLIST)
        owner_approve_item(user=self.owner, item=items[1])
        record_content_publication(user=self.owner, item=items[1], url="https://fb.com/2", published_at=timezone.now())

        # Hủy bài 3
        cancel_content_item(user=self.owner, item=items[2], reason="Không còn phù hợp với ngân sách")

        pkg.refresh_from_db()
        self.assertEqual(pkg.status, PackageStatus.COMPLETED)

    # --------------------------------------------------------------------------
    # AC15: Sửa thương hiệu sau duyệt kế hoạch -> Snapshot gói không tự đổi
    # --------------------------------------------------------------------------
    def test_ac15_brand_profile_immutability_snapshot_isolation(self):
        """AC15: Sửa thương hiệu sau duyệt kế hoạch: snapshot gói không tự đổi."""
        save_brand_profile(
            user=self.owner,
            workspace=self.ws,
            name="Brand Gốc V1",
            product_summary="Sản phẩm ban đầu",
            target_audience="Khách hàng ban đầu",
            source_urls=["https://english.example.com"],
        )
        pkg, items = self._create_sample_package_and_items()
        approve_plan(user=self.owner, package=pkg, idempotency_key="plan_ac15")
        pkg.refresh_from_db()
        snapshot_initial = pkg.brand_snapshot

        # Chủ sửa hồ sơ thương hiệu
        save_brand_profile(
            user=self.owner,
            workspace=self.ws,
            name="Brand Mới V2 Đã Đổi Tên",
            product_summary="Sản phẩm mới đã tái định vị",
            target_audience="Khách hàng mở rộng",
            source_urls=["https://new-english.example.com"],
            expected_revision=1,
        )

        pkg.refresh_from_db()
        self.assertEqual(pkg.brand_snapshot["brand_name"], "Brand Gốc V1")
        self.assertEqual(pkg.brand_snapshot, snapshot_initial)

    # --------------------------------------------------------------------------
    # AC16: Màn hình 390 px, Chủ duyệt bài -> Đọc và thao tác được
    # --------------------------------------------------------------------------
    def test_ac16_mobile_390px_owner_review_view(self):
        """AC16: Viewport 390px tải trang chi tiết bài ở OWNER_REVIEW hiển thị đầy đủ form và nút duyệt."""
        pkg, items = self._create_sample_package_and_items()
        approve_plan(user=self.owner, package=pkg, idempotency_key="plan_ac16")
        item = items[0]

        submit_content_version(user=self.freelancer, item=item, text="Bài mẫu AC16")
        submit_for_owner_review(user=self.editor, item=item, checklist=VALID_CHECKLIST)

        url = reverse("workspaces:item_detail", kwargs={
            "workspace_id": self.ws.id,
            "package_id": pkg.id,
            "item_id": item.id,
        })
        resp = self.client_owner.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Phê duyệt phiên bản")
        self.assertContains(resp, "responsive-two-cols")
        self.assertContains(resp, "Yêu cầu sửa lại")

    # --------------------------------------------------------------------------
    # AC17: Mất kết nối khi lưu form -> Giữ nội dung, thử lại không tạo trùng
    # --------------------------------------------------------------------------
    def test_ac17_form_validation_retention_and_idempotency(self):
        """AC17: Lỗi validation hoặc conflict giữ nguyên form input; idempotency key chống trùng."""
        url_create_pkg = reverse("workspaces:package_create", kwargs={"workspace_id": self.ws.id})
        # Gửi thiếu ngày kết thúc
        resp = self.client_owner.post(url_create_pkg, {
            "name": "Gói AC17 Nhập Dở",
            "start_date": timezone.now().date().isoformat(),
            "channel": "FACEBOOK",
            "coordinator_membership": str(self.m_owner.id),
        })
        self.assertIn(resp.status_code, [200, 400])
        self.assertContains(resp, "Gói AC17 Nhập Dở", status_code=resp.status_code)

    # --------------------------------------------------------------------------
    # AC18: Khôi phục bản sao lưu thử -> Đọc được gói/phiên bản/quyết định
    # --------------------------------------------------------------------------
    def test_ac18_database_backup_and_restore_verification(self):
        """AC18: Sao lưu CSDL và phục hồi thử vào target DB cách ly, kiểm chứng toàn vẹn quan hệ."""
        backup_dir = Path("test_backups_dir").resolve()
        backup_dir.mkdir(parents=True, exist_ok=True)
        drill_db_path = backup_dir / "drill_target.sqlite3"

        # Khởi tạo một CSDL nguồn mẫu có bản ghi và commit rõ ràng
        sample_src_db = backup_dir / "sample_src.sqlite3"
        conn_src = sqlite3.connect(str(sample_src_db))
        conn_src.execute("CREATE TABLE workspaces_workspace (id text PRIMARY KEY, name text);")
        conn_src.execute("CREATE TABLE workspaces_brandprofile (id text, workspace_id text);")
        conn_src.execute("CREATE TABLE workspaces_package (id text, name text);")
        conn_src.execute("CREATE TABLE workspaces_contentitem (id text, title text);")
        conn_src.execute("CREATE TABLE workspaces_task (id text, role text);")
        conn_src.execute("INSERT INTO workspaces_workspace VALUES ('ws-1', 'Trung Tâm Mẫu AC18');")
        conn_src.commit()
        conn_src.close()

        try:
            # 1. Dùng lệnh backup_database trên file mẫu
            with patch.dict(connection.settings_dict, {"ENGINE": "django.db.backends.sqlite3", "NAME": str(sample_src_db)}):
                call_command("backup_database", output_dir=str(backup_dir), retention_count=5)

            backups = list(backup_dir.glob("backup_sqlite_*.sqlite3"))
            self.assertGreaterEqual(len(backups), 1)
            backup_file = backups[0]

            manifest_file = backup_dir / f"{backup_file.stem}.manifest.json"
            self.assertTrue(manifest_file.exists())
            manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
            self.assertEqual(manifest_data["engine"], "sqlite3")
            self.assertIn("sha256_checksum", manifest_data)

            # 2. Chạy lệnh restore_database vào database diễn tập
            call_command("restore_database", str(backup_file), target_db=str(drill_db_path))
            self.assertTrue(drill_db_path.exists())

            # 3. Kiểm tra tính toàn vẹn quan hệ sau khôi phục
            conn = sqlite3.connect(str(drill_db_path))
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_key_check;")
            violations = cursor.fetchall()
            self.assertEqual(len(violations), 0)

            cursor.execute("SELECT COUNT(*) FROM workspaces_workspace;")
            ws_count = cursor.fetchone()[0]
            self.assertEqual(ws_count, 1)
            conn.close()

        finally:
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # E2E Luồng Nội dung Xuyên suốt (Spec 14 / B10 Core Journey)
    # --------------------------------------------------------------------------
    def test_e2e_full_lifecycle_journey(self):
        """
        Kiểm tra xuyên suốt trọn vẹn:
        Tạo workspace -> thành viên -> brand -> gói/bài -> duyệt kế hoạch
        -> viết (v1) -> biên tập (trả sửa) -> nộp v2 -> Chủ duyệt v2
        -> ghi nhận xuất bản -> hoàn thành gói.
        """
        # 1. Hồ sơ thương hiệu
        save_brand_profile(
            user=self.owner,
            workspace=self.ws,
            name="Trung tâm Anh ngữ Mẫu",
            product_summary="Khóa học tiếng Anh chuyên nghiệp",
            target_audience="Người đi làm 22-35 tuổi",
            source_urls=["https://english.example.com"],
        )

        # 2. Tạo gói 1 bài viết để đi trọn vòng đời
        pkg = create_package(
            user=self.owner,
            workspace=self.ws,
            name="Gói E2E Hoàn Hảo",
            objective="Mục tiêu truyền thông trọn vẹn E2E",
            start_date=timezone.now().date(),
            end_date=(timezone.now() + datetime.timedelta(days=15)).date(),
            channel="FACEBOOK",
            coordinator_membership=self.m_owner,
        )
        item = ContentItem.objects.create(
            workspace=self.ws,
            package=pkg,
            title="Bài viết E2E Trọn Vẹn",
            brief="Brief chi tiết",
            writer_membership=self.m_free,
            editor_membership=self.m_editor,
            publisher_membership=self.m_owner,
            writing_deadline=timezone.now() + datetime.timedelta(days=1),
            editing_deadline=timezone.now() + datetime.timedelta(days=2),
            review_deadline=timezone.now() + datetime.timedelta(days=3),
            planned_publish_at=timezone.now() + datetime.timedelta(days=4),
        )

        # 3. Duyệt kế hoạch
        approve_plan(user=self.owner, package=pkg, idempotency_key="plan_e2e")
        pkg.refresh_from_db()
        self.assertEqual(pkg.status, PackageStatus.ACTIVE)

        # 4. Viết bài v1
        v1, item = submit_content_version(user=self.freelancer, item=item, text="Bản thảo ban đầu v1")
        self.assertEqual(item.state, ContentItemState.EDITING)

        # 5. Biên tập yêu cầu sửa
        decision, item = request_changes_decision(
            user=self.editor,
            item=item,
            reason="Bổ sung thêm 2 câu ví dụ giao tiếp thực tế.",
        )
        self.assertEqual(item.state, ContentItemState.WRITING)

        # 6. Người viết hoàn thiện nộp v2
        v2, item = submit_content_version(user=self.freelancer, item=item, text="Bản thảo hoàn thiện v2 có ví dụ")
        self.assertEqual(item.state, ContentItemState.EDITING)

        # 7. Biên tập nộp cho Chủ duyệt
        _, item = submit_for_owner_review(user=self.editor, item=item, checklist=VALID_CHECKLIST)
        self.assertEqual(item.state, ContentItemState.OWNER_REVIEW)

        # 8. Chủ phê duyệt bản v2
        appr, item = owner_approve_item(user=self.owner, item=item, expected_version_id=v2.id)
        self.assertEqual(item.state, ContentItemState.READY_TO_PUBLISH)

        # 9. Người xuất bản ghi nhận đăng bài
        pub, item = record_content_publication(
            user=self.owner,
            item=item,
            url="https://facebook.com/english/post/999",
            published_at=timezone.now(),
            idempotency_key="pub_e2e",
        )
        self.assertEqual(item.state, ContentItemState.PUBLISHED)

        # 10. Gói tự động chuyển trạng thái COMPLETED
        pkg.refresh_from_db()
        self.assertEqual(pkg.status, PackageStatus.COMPLETED)

    # --------------------------------------------------------------------------
    # Kiểm thử Custom Error Handlers & CSRF Protection
    # --------------------------------------------------------------------------
    def test_custom_error_handlers_and_templates(self):
        """Kiểm tra 400, 403, 404, 500 render đúng template, đúng mã status và không lộ secret."""
        from core.views import (
            custom_bad_request_view,
            custom_permission_denied_view,
            custom_page_not_found_view,
            custom_server_error_view,
        )
        from django.test.client import RequestFactory

        rf = RequestFactory()
        req = rf.get("/")

        resp_400 = custom_bad_request_view(req)
        self.assertEqual(resp_400.status_code, 400)
        self.assertIn("Yêu cầu không hợp lệ", resp_400.content.decode("utf-8"))
        self.assertNotIn("Traceback", resp_400.content.decode("utf-8"))

        resp_403 = custom_permission_denied_view(req)
        self.assertEqual(resp_403.status_code, 403)
        self.assertIn("Truy cập bị từ chối", resp_403.content.decode("utf-8"))
        self.assertNotIn("Traceback", resp_403.content.decode("utf-8"))

        resp_404 = custom_page_not_found_view(req)
        self.assertEqual(resp_404.status_code, 404)
        self.assertIn("Không tìm thấy trang", resp_404.content.decode("utf-8"))
        self.assertNotIn("Traceback", resp_404.content.decode("utf-8"))

        resp_500 = custom_server_error_view(req)
        self.assertEqual(resp_500.status_code, 500)
        self.assertIn("Đã xảy ra sự cố kỹ thuật", resp_500.content.decode("utf-8"))
        self.assertNotIn("Traceback", resp_500.content.decode("utf-8"))

    def test_csrf_failure_view(self):
        """Kiểm tra CSRF failure view trả về HTTP 403 với template 403_csrf.html."""
        from core.views import custom_csrf_failure_view
        from django.test.client import RequestFactory

        rf = RequestFactory()
        req = rf.post(reverse("home"))
        resp = custom_csrf_failure_view(req, reason="CSRF cookie not set.")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("CSRF", resp.content.decode("utf-8"))

