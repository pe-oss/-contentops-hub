import datetime
import uuid
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AccountEmailIdentity
from apps.workspaces.models import (
    AccessRole,
    BrandProfile,
    ContentItem,
    ContentItemState,
    EmploymentType,
    Membership,
    MembershipStatus,
    Package,
    PackageStatus,
    PlanApproval,
    Task,
    TaskRole,
    TaskStatus,
    Workspace,
)
from apps.workspaces.selectors import (
    get_item_for_workspace,
    get_package_for_workspace,
    get_package_items,
    get_workspace_packages,
)
from apps.workspaces.services import (
    ConcurrencyConflictError,
    add_content_item,
    approve_plan,
    create_package,
    create_workspace_with_owner,
    save_brand_profile,
    update_content_item,
    update_package,
)

User = get_user_model()


class PackagesAndPlanningB04Tests(TestCase):
    def setUp(self):
        # 1. Chủ workspace 1 (Owner)
        self.owner = User.objects.create_user(
            username="owner_user",
            email="owner@example.com",
            password="StrongPassword123!",
        )
        self.owner.email_identity.mark_as_verified()

        # 2. Thành viên điều phối / Freelancer
        self.member_freelancer = User.objects.create_user(
            username="freelancer_user",
            email="freelancer@example.com",
            password="StrongPassword123!",
        )
        self.member_freelancer.email_identity.mark_as_verified()

        # 3. Thành viên xuất bản (Publisher)
        self.member_publisher = User.objects.create_user(
            username="publisher_user",
            email="publisher@example.com",
            password="StrongPassword123!",
        )
        self.member_publisher.email_identity.mark_as_verified()

        # 4. Người ngoài (Outsider)
        self.outsider = User.objects.create_user(
            username="outsider_user",
            email="outsider@example.com",
            password="StrongPassword123!",
        )
        self.outsider.email_identity.mark_as_verified()

        # 5. Workspace chính (theo dữ liệu mẫu mục 14)
        self.workspace = create_workspace_with_owner(
            user=self.owner,
            name="Trung tâm Anh ngữ mẫu",
            timezone_str="Asia/Ho_Chi_Minh",
        )
        self.owner_membership = Membership.objects.get(workspace=self.workspace, user=self.owner)

        self.freelancer_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.member_freelancer,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.FREELANCER,
            status=MembershipStatus.ACTIVE,
            ai_use_allowed=True,
        )

        self.publisher_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.member_publisher,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE,
            status=MembershipStatus.ACTIVE,
            ai_use_allowed=False,
        )

        # 6. Workspace thứ hai để test cách ly
        self.other_owner = User.objects.create_user(
            username="other_owner",
            email="other_owner@example.com",
            password="StrongPassword123!",
        )
        self.other_owner.email_identity.mark_as_verified()
        self.other_workspace = create_workspace_with_owner(
            user=self.other_owner,
            name="Doanh nghiệp khác",
            timezone_str="UTC",
        )
        self.other_owner_membership = Membership.objects.get(workspace=self.other_workspace, user=self.other_owner)

        self.today = timezone.now().date()
        self.start_date = self.today
        self.end_date = self.today + datetime.timedelta(days=30)

        # Tạo BrandProfile cho Workspace chính
        self.brand_profile = save_brand_profile(
            user=self.owner,
            workspace=self.workspace,
            name="Anh Ngữ Quốc Tế Mẫu",
            product_summary="Khóa học tiếng Anh giao tiếp và IELTS chuẩn quốc tế",
            target_audience="Học sinh cấp 3 và sinh viên chuẩn bị du học",
            tone_of_voice="Thân thiện, truyền cảm hứng, chuẩn mực học thuật",
            avoid_guidelines="Không cam kết đầu ra thần tốc không căn cứ",
            allowed_claims="Giáo trình chuẩn Cambridge",
            source_urls=["https://cambridge.example.com"],
        )

        self.client = Client()

    def test_database_test_isolation(self):
        """Xác nhận test runner chạy trên database test độc lập."""
        db_name = connection.settings_dict.get("NAME")
        self.assertTrue(
            "test" in db_name.lower(),
            f"Test phải chạy trên database test tách biệt. Hiện tại: {db_name}",
        )

    def test_create_package_success_and_validations(self):
        """Tạo gói thành công; kiểm tra validation ngày bắt đầu / kết thúc."""
        pkg = create_package(
            user=self.owner,
            workspace=self.workspace,
            name="Chiến dịch Khai giảng Mùa Thu",
            objective="Thu hút 50 học viên đăng ký khóa học IELTS mùa thu",
            coordinator_membership=self.freelancer_membership,
            start_date=self.start_date,
            end_date=self.end_date,
        )

        self.assertEqual(pkg.name, "Chiến dịch Khai giảng Mùa Thu")
        self.assertEqual(pkg.status, PackageStatus.DRAFT)
        self.assertEqual(pkg.channel, "FACEBOOK")
        self.assertEqual(pkg.plan_revision, 1)
        self.assertEqual(pkg.row_version, 1)

        # Ngày kết thúc trước ngày bắt đầu phải bị chặn
        with self.assertRaises(ValidationError):
            p_invalid = Package(
                workspace=self.workspace,
                name="Gói Lỗi",
                objective="Mục tiêu",
                coordinator_membership=self.freelancer_membership,
                start_date=self.today + datetime.timedelta(days=10),
                end_date=self.today,
            )
            p_invalid.full_clean()

    def test_create_content_items_and_deadline_sequence_validation(self):
        """
        Spec mục 4 & AC04: Hạn theo thứ tự viết <= biên tập <= duyệt <= đăng;
        lịch bài nằm trong khoảng gói; tối đa 50 bài/gói.
        """
        pkg = create_package(
            user=self.owner,
            workspace=self.workspace,
            name="Gói 3 bài Facebook",
            objective="Mục tiêu mẫu 3 bài",
            coordinator_membership=self.freelancer_membership,
            start_date=self.start_date,
            end_date=self.end_date,
        )

        base_time = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) + datetime.timedelta(days=2)

        # 1. Thêm bài hợp lệ
        item1 = add_content_item(
            user=self.owner,
            package=pkg,
            title="Bài 1: Bí quyết đạt IELTS 7.0+",
            brief="Hướng dẫn lộ trình 4 kỹ năng",
            cta="Đăng ký test trình độ miễn phí",
            writing_deadline=base_time + datetime.timedelta(days=1),
            editing_deadline=base_time + datetime.timedelta(days=2),
            review_deadline=base_time + datetime.timedelta(days=3),
            planned_publish_at=base_time + datetime.timedelta(days=4),
            writer_membership=self.freelancer_membership,
            editor_membership=self.freelancer_membership,
            publisher_membership=self.publisher_membership,
        )
        self.assertEqual(item1.title, "Bài 1: Bí quyết đạt IELTS 7.0+")
        self.assertEqual(item1.state, ContentItemState.TODO)

        # 2. Hạn sai thứ tự: viết > biên tập -> ValidationError (AC04)
        with self.assertRaises(ValidationError):
            add_content_item(
                user=self.owner,
                package=pkg,
                title="Bài lỗi deadline",
                brief="Brief lỗi",
                cta="",
                writing_deadline=base_time + datetime.timedelta(days=5),
                editing_deadline=base_time + datetime.timedelta(days=2),
                review_deadline=base_time + datetime.timedelta(days=6),
                planned_publish_at=base_time + datetime.timedelta(days=7),
                writer_membership=self.freelancer_membership,
                editor_membership=self.freelancer_membership,
                publisher_membership=self.publisher_membership,
            )

        # 3. Lịch bài nằm ngoài khoảng thời gian của gói
        with self.assertRaises(ValidationError):
            add_content_item(
                user=self.owner,
                package=pkg,
                title="Bài ngoài hạn gói",
                brief="Brief ngoài hạn",
                cta="",
                writing_deadline=base_time + datetime.timedelta(days=1),
                editing_deadline=base_time + datetime.timedelta(days=2),
                review_deadline=base_time + datetime.timedelta(days=3),
                planned_publish_at=base_time + datetime.timedelta(days=60),
                writer_membership=self.freelancer_membership,
                editor_membership=self.freelancer_membership,
                publisher_membership=self.publisher_membership,
            )

    def test_approve_plan_full_lifecycle_and_ac04(self):
        """
        Duyệt kế hoạch (F02, AC04):
        - Kế hoạch chưa có bài hoặc người thực hiện không hợp lệ bị từ chối.
        - Kế hoạch hợp lệ: lưu immutable plan snapshot, brand snapshot, chuyển DRAFT -> ACTIVE,
          và sinh đúng 3 nhiệm vụ (Task) cho mỗi bài.
        """
        pkg = create_package(
            user=self.owner,
            workspace=self.workspace,
            name="Gói Duyệt Thử Nghiệm",
            objective="Mục tiêu duyệt kế hoạch",
            coordinator_membership=self.freelancer_membership,
            start_date=self.start_date,
            end_date=self.end_date,
        )

        with self.assertRaises(ValidationError):
            approve_plan(user=self.owner, package=pkg)

        base_time = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) + datetime.timedelta(days=2)
        add_content_item(
            user=self.owner,
            package=pkg,
            title="Bài 1",
            brief="Brief 1",
            cta="CTA 1",
            writing_deadline=base_time + datetime.timedelta(days=1),
            editing_deadline=base_time + datetime.timedelta(days=2),
            review_deadline=base_time + datetime.timedelta(days=3),
            planned_publish_at=base_time + datetime.timedelta(days=4),
            writer_membership=self.freelancer_membership,
            editor_membership=self.freelancer_membership,
            publisher_membership=self.publisher_membership,
        )
        add_content_item(
            user=self.owner,
            package=pkg,
            title="Bài 2",
            brief="Brief 2",
            cta="CTA 2",
            writing_deadline=base_time + datetime.timedelta(days=2),
            editing_deadline=base_time + datetime.timedelta(days=3),
            review_deadline=base_time + datetime.timedelta(days=4),
            planned_publish_at=base_time + datetime.timedelta(days=5),
            writer_membership=self.freelancer_membership,
            editor_membership=self.freelancer_membership,
            publisher_membership=self.publisher_membership,
        )

        active_pkg, approval, tasks = approve_plan(user=self.owner, package=pkg)

        self.assertEqual(active_pkg.status, PackageStatus.ACTIVE)
        self.assertIsNotNone(active_pkg.brand_snapshot)
        self.assertEqual(active_pkg.brand_snapshot["brand_name"], "Anh Ngữ Quốc Tế Mẫu")
        self.assertEqual(approval.plan_revision, 1)
        self.assertEqual(len(approval.immutable_plan_snapshot["items"]), 2)

        self.assertEqual(len(tasks), 6)
        write_tasks = [t for t in tasks if t.role == TaskRole.WRITE]
        edit_tasks = [t for t in tasks if t.role == TaskRole.EDIT]
        pub_tasks = [t for t in tasks if t.role == TaskRole.PUBLISH]

        self.assertEqual(len(write_tasks), 2)
        self.assertEqual(len(edit_tasks), 2)
        self.assertEqual(len(pub_tasks), 2)

        for wt in write_tasks:
            self.assertEqual(wt.status, TaskStatus.READY)
        for et in edit_tasks:
            self.assertEqual(et.status, TaskStatus.WAITING)
        for pt in pub_tasks:
            self.assertEqual(pt.status, TaskStatus.WAITING)

    def test_approve_plan_idempotency_double_click_protection_ac05(self):
        """
        AC05: Nhấp duyệt kế hoạch hai lần cùng idempotency key:
        Chỉ một snapshot và một bộ nhiệm vụ duy nhất được tạo.
        """
        pkg = create_package(
            user=self.owner,
            workspace=self.workspace,
            name="Gói Idempotency",
            objective="Kiểm tra chống nhấp đôi",
            coordinator_membership=self.freelancer_membership,
            start_date=self.start_date,
            end_date=self.end_date,
        )
        base_time = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) + datetime.timedelta(days=2)
        add_content_item(
            user=self.owner,
            package=pkg,
            title="Bài Test AC05",
            brief="Brief AC05",
            cta="",
            writing_deadline=base_time + datetime.timedelta(days=1),
            editing_deadline=base_time + datetime.timedelta(days=2),
            review_deadline=base_time + datetime.timedelta(days=3),
            planned_publish_at=base_time + datetime.timedelta(days=4),
            writer_membership=self.freelancer_membership,
            editor_membership=self.freelancer_membership,
            publisher_membership=self.publisher_membership,
        )

        idempotency_key = "idemp_test_pkg_123"

        pkg1, approval1, tasks1 = approve_plan(user=self.owner, package=pkg, idempotency_key=idempotency_key)
        self.assertEqual(len(tasks1), 3)

        pkg2, approval2, tasks2 = approve_plan(user=self.owner, package=pkg, idempotency_key=idempotency_key)

        self.assertEqual(approval1.id, approval2.id)
        self.assertEqual(PlanApproval.objects.filter(package=pkg).count(), 1)
        self.assertEqual(Task.objects.filter(item__package=pkg).count(), 3)
    def test_brand_snapshot_isolation_after_plan_approval_ac15(self):
        """
        AC15: Sửa hồ sơ thương hiệu sau khi duyệt kế hoạch:
        Snapshot thương hiệu trong gói không tự thay đổi, đảm bảo tính toàn vẹn lịch sử.
        """
        pkg = create_package(
            user=self.owner,
            workspace=self.workspace,
            name="Gói Kiểm Tra Snapshot Brand",
            objective="Mục tiêu snapshot",
            coordinator_membership=self.freelancer_membership,
            start_date=self.start_date,
            end_date=self.end_date,
        )
        base_time = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) + datetime.timedelta(days=2)
        add_content_item(
            user=self.owner,
            package=pkg,
            title="Bài Test AC15",
            brief="Brief AC15",
            cta="",
            writing_deadline=base_time + datetime.timedelta(days=1),
            editing_deadline=base_time + datetime.timedelta(days=2),
            review_deadline=base_time + datetime.timedelta(days=3),
            planned_publish_at=base_time + datetime.timedelta(days=4),
            writer_membership=self.freelancer_membership,
            editor_membership=self.freelancer_membership,
            publisher_membership=self.publisher_membership,
        )

        active_pkg, _, _ = approve_plan(user=self.owner, package=pkg)
        self.assertEqual(active_pkg.brand_snapshot["brand_name"], "Anh Ngữ Quốc Tế Mẫu")
        self.assertEqual(active_pkg.brand_snapshot["revision"], 1)

        save_brand_profile(
            user=self.owner,
            workspace=self.workspace,
            name="Anh Ngữ Quốc Tế Mẫu THAY ĐỔI MỚI",
            product_summary="Sản phẩm mới sau cập nhật",
            target_audience="Khách hàng mới",
            expected_revision=1,
        )
        self.brand_profile.refresh_from_db()
        self.assertEqual(self.brand_profile.revision, 2)
        self.assertEqual(self.brand_profile.name, "Anh Ngữ Quốc Tế Mẫu THAY ĐỔI MỚI")

        active_pkg.refresh_from_db()
        self.assertEqual(active_pkg.brand_snapshot["brand_name"], "Anh Ngữ Quốc Tế Mẫu")
        self.assertEqual(active_pkg.brand_snapshot["revision"], 1)
    def test_tenant_isolation_cannot_assign_or_access_cross_workspace(self):
        """
        Phân quyền & Cách ly đa người thuê:
        - Không thể phân công thành viên thuộc workspace khác vào bài viết.
        - Người dùng workspace khác nhận 404 khi truy cập URL gói/bài của workspace này.
        """
        pkg = create_package(
            user=self.owner,
            workspace=self.workspace,
            name="Gói Isolation",
            objective="Mục tiêu cách ly",
            coordinator_membership=self.freelancer_membership,
            start_date=self.start_date,
            end_date=self.end_date,
        )
        base_time = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) + datetime.timedelta(days=2)

        with self.assertRaises(ValidationError):
            add_content_item(
                user=self.owner,
                package=pkg,
                title="Bài Hacked Member",
                brief="Brief hacked",
                cta="",
                writing_deadline=base_time + datetime.timedelta(days=1),
                editing_deadline=base_time + datetime.timedelta(days=2),
                review_deadline=base_time + datetime.timedelta(days=3),
                planned_publish_at=base_time + datetime.timedelta(days=4),
                writer_membership=self.other_owner_membership,
                editor_membership=self.freelancer_membership,
                publisher_membership=self.publisher_membership,
            )

        self.client.force_login(self.outsider)
        resp = self.client.get(reverse("workspaces:package_detail", kwargs={"workspace_id": self.workspace.id, "package_id": pkg.id}))
        self.assertEqual(resp.status_code, 404)

        self.client.force_login(self.other_owner)
        resp_other = self.client.get(reverse("workspaces:package_detail", kwargs={"workspace_id": self.workspace.id, "package_id": pkg.id}))
        self.assertEqual(resp_other.status_code, 404)

    def test_optimistic_concurrency_control_on_package_and_items(self):
        """
        AC10: Hai người sửa cùng row_version:
        Lần lưu thứ hai trả về ConcurrencyConflictError (HTTP 409), không mất dữ liệu âm thầm.
        """
        pkg = create_package(
            user=self.owner,
            workspace=self.workspace,
            name="Gói Concurrency",
            objective="Mục tiêu ban đầu",
            coordinator_membership=self.freelancer_membership,
            start_date=self.start_date,
            end_date=self.end_date,
        )
        self.assertEqual(pkg.row_version, 1)

        update_package(
            user=self.owner,
            package=pkg,
            name="Gói Concurrency Sửa Lần 1",
            objective="Mục tiêu sửa lần 1",
            coordinator_membership=self.freelancer_membership,
            start_date=self.start_date,
            end_date=self.end_date,
            expected_row_version=1,
        )
        pkg.refresh_from_db()
        self.assertEqual(pkg.row_version, 2)

        with self.assertRaises(ConcurrencyConflictError):
            update_package(
                user=self.owner,
                package=pkg,
                name="Gói Concurrency Sửa Lần 2 (Stale)",
                objective="Mục tiêu sửa lần 2",
                coordinator_membership=self.freelancer_membership,
                start_date=self.start_date,
                end_date=self.end_date,
                expected_row_version=1,
            )

        self.client.force_login(self.owner)
        url = reverse("workspaces:package_edit", kwargs={"workspace_id": self.workspace.id, "package_id": pkg.id})
        resp = self.client.post(
            url,
            {
                "name": "Tên Form Conflict",
                "objective": "Mục tiêu Form Conflict",
                "coordinator_membership": self.freelancer_membership.id,
                "start_date": self.start_date.isoformat(),
                "end_date": self.end_date.isoformat(),
                "expected_row_version": 1,
            },
        )
        self.assertEqual(resp.status_code, 409)
        self.assertContains(resp, "Xung đột phiên bản", status_code=409)

    def test_permission_matrix_and_member_role_checks(self):
        """
        Ma trận phân quyền B04:
        - Thành viên MEMBER (không phải điều phối) không được tạo gói -> 403
        - Thành viên MEMBER không được duyệt kế hoạch -> 403 (AC03)
        - Điều phối gói (MEMBER) được thêm bài khi gói DRAFT
        - Khi gói ACTIVE, điều phối không được sửa bài -> chỉ Chủ mới có quyền
        - Thành viên bị vô hiệu hóa (INACTIVE) -> 404
        """
        # 1. Member không phải Chủ thử tạo gói -> 403
        self.client.force_login(self.member_freelancer)
        url_create = reverse("workspaces:package_create", kwargs={"workspace_id": self.workspace.id})
        resp = self.client.get(url_create)
        self.assertEqual(resp.status_code, 403)

        # 2. Tạo gói nháp do Chủ tạo
        pkg = create_package(
            user=self.owner,
            workspace=self.workspace,
            name="Gói Phân Quyền",
            objective="Mục tiêu phân quyền",
            coordinator_membership=self.freelancer_membership,
            start_date=self.start_date,
            end_date=self.end_date,
        )

        # 3. Member tự gọi endpoint duyệt kế hoạch -> 403 (AC03)
        url_approve = reverse("workspaces:package_approve_plan", kwargs={"workspace_id": self.workspace.id, "package_id": pkg.id})
        resp_member_approve = self.client.post(url_approve)
        self.assertEqual(resp_member_approve.status_code, 403)

        # 4. Điều phối gói (MEMBER) thêm bài vào gói nháp -> Thành công
        base_time = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) + datetime.timedelta(days=2)
        url_add_item = reverse("workspaces:item_create", kwargs={"workspace_id": self.workspace.id, "package_id": pkg.id})
        resp_coord_add = self.client.post(
            url_add_item,
            {
                "title": "Bài do Điều phối thêm",
                "brief": "Brief hợp lệ",
                "cta": "CTA hợp lệ",
                "writing_deadline": (base_time + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
                "editing_deadline": (base_time + datetime.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
                "review_deadline": (base_time + datetime.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"),
                "planned_publish_at": (base_time + datetime.timedelta(days=4)).strftime("%Y-%m-%dT%H:%M"),
                "writer_membership": self.freelancer_membership.id,
                "editor_membership": self.freelancer_membership.id,
                "publisher_membership": self.publisher_membership.id,
            },
        )
        self.assertEqual(resp_coord_add.status_code, 302)
        item = ContentItem.objects.filter(package=pkg).first()
        self.assertIsNotNone(item)

        # 5. Chủ duyệt kế hoạch
        approve_plan(user=self.owner, package=pkg)
        pkg.refresh_from_db()
        self.assertEqual(pkg.status, PackageStatus.ACTIVE)

        # 6. Khi kế hoạch ACTIVE, Điều phối thử sửa bài -> 403 (Chỉ Chủ)
        url_edit_item = reverse("workspaces:item_edit", kwargs={"workspace_id": self.workspace.id, "package_id": pkg.id, "item_id": item.id})
        resp_coord_edit_active = self.client.post(
            url_edit_item,
            {
                "title": "Bài Điều phối sửa lén khi active",
                "brief": "Brief",
                "writing_deadline": (base_time + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
                "editing_deadline": (base_time + datetime.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
                "review_deadline": (base_time + datetime.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"),
                "planned_publish_at": (base_time + datetime.timedelta(days=4)).strftime("%Y-%m-%dT%H:%M"),
                "writer_membership": self.freelancer_membership.id,
                "editor_membership": self.freelancer_membership.id,
                "publisher_membership": self.publisher_membership.id,
                "expected_row_version": item.row_version,
            },
        )
        self.assertEqual(resp_coord_edit_active.status_code, 403)

        # 7. Vô hiệu hóa membership của thành viên -> Bị 404 ngay ở request tiếp theo
        self.freelancer_membership.status = MembershipStatus.INACTIVE
        self.freelancer_membership.save(update_fields=["status"])
        resp_inactive = self.client.get(reverse("workspaces:package_detail", kwargs={"workspace_id": self.workspace.id, "package_id": pkg.id}))
        self.assertEqual(resp_inactive.status_code, 404)

    def test_form_validation_and_input_retention(self):
        """Form Package & ContentItem trả về 400 và giữ lại dữ liệu khi lỗi validate."""
        self.client.force_login(self.owner)
        url_create_pkg = reverse("workspaces:package_create", kwargs={"workspace_id": self.workspace.id})

        # Gửi dữ liệu thiếu mục tiêu
        resp = self.client.post(
            url_create_pkg,
            {
                "name": "Tên gói giữ lại",
                "objective": "",  # Thiếu
                "coordinator_membership": self.freelancer_membership.id,
                "start_date": self.start_date.isoformat(),
                "end_date": self.end_date.isoformat(),
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "Trường này là bắt buộc.", status_code=400)
        self.assertContains(resp, "Tên gói giữ lại", status_code=400)



