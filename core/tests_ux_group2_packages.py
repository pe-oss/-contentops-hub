import datetime
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.workspaces.models import (
    AccessRole,
    EmploymentType,
    Membership,
    MembershipStatus,
    Package,
    PackageStatus,
)
from apps.workspaces.services import create_workspace_with_owner

User = get_user_model()


class UXGroup2PackageFormTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(username="grp2_owner", email="owner@grp2.vn", password="password123")
        self.coordinator = User.objects.create_user(username="grp2_coord", email="coord@grp2.vn", password="password123")
        self.member = User.objects.create_user(username="grp2_member", email="member@grp2.vn", password="password123")
        self.outsider = User.objects.create_user(username="grp2_outsider", email="outsider@grp2.vn", password="password123")

        self.workspace = create_workspace_with_owner(
            user=self.owner,
            name="Workspace Group 2",
            timezone_str="Asia/Ho_Chi_Minh",
        )
        self.owner_membership = Membership.objects.get(workspace=self.workspace, user=self.owner)
        self.coord_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.coordinator,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE,
            status=MembershipStatus.ACTIVE,
        )
        self.member_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.member,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.FREELANCER,
            status=MembershipStatus.ACTIVE,
        )

        today = timezone.now().date()
        self.package = Package.objects.create(
            workspace=self.workspace,
            name="Chiến dịch Hiện tại",
            objective="Mục tiêu gói ban đầu",
            coordinator_membership=self.coord_membership,
            start_date=today,
            end_date=today + datetime.timedelta(days=14),
            status=PackageStatus.DRAFT,
        )

    def test_package_create_ui_structure(self):
        """Kiểm tra cấu trúc form tạo gói: header, workflow 3 bước, 3 nhóm fieldset, nút 'Tạo gói nháp'."""
        self.client.force_login(self.owner)
        url = reverse("workspaces:package_create", kwargs={"workspace_id": self.workspace.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        # 1. Header & Breadcrumb
        self.assertIn("← Gói content", content)
        self.assertIn("Tạo Gói nội dung mới", content)
        self.assertIn("Khởi tạo kế hoạch chiến dịch nội dung", content)

        # 2. Workflow indicator 3 bước
        self.assertIn("package-workflow-steps", content)
        self.assertIn("Tạo gói nháp", content)
        self.assertIn("Thêm bài / Phân công", content)
        self.assertIn("Duyệt kế hoạch", content)

        # 3. 3 nhóm fieldset
        self.assertIn("1. Thông tin gói", content)
        self.assertIn("2. Thời gian thực hiện", content)
        self.assertIn("3. Người phụ trách", content)

        # 4. Input fields & Layout
        self.assertIn('name="name"', content)
        self.assertIn('name="objective"', content)
        self.assertIn('name="channel"', content)
    def test_package_edit_ui_structure(self):
        """Kiểm tra cấu trúc form sửa gói: header, 3 nhóm, hidden version, nút 'Lưu thay đổi'."""
        self.client.force_login(self.owner)
        url = reverse("workspaces:package_edit", kwargs={"workspace_id": self.workspace.id, "package_id": self.package.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("← Gói content", content)
        self.assertIn("Chỉnh sửa Gói nội dung", content)
        self.assertIn("1. Thông tin gói", content)
        self.assertIn("2. Thời gian thực hiện", content)
        self.assertIn("3. Người phụ trách", content)
        self.assertIn("responsive-two-cols", content)
        self.assertIn('name="expected_row_version"', content)
        self.assertIn("Lưu thay đổi", content)
        self.assertIn("Hủy", content)

    def test_package_create_success_creates_draft_package(self):
        """Tạo gói thành công tạo ra trạng thái DRAFT và chuyển hướng đến trang chi tiết gói."""
        self.client.force_login(self.owner)
        url = reverse("workspaces:package_create", kwargs={"workspace_id": self.workspace.id})
        today = timezone.now().date()
        payload = {
            "name": "Chiến dịch Mùa Hè 2026",
            "objective": "Tăng trưởng nhận diện thương hiệu trên Facebook",
            "coordinator_membership": str(self.coord_membership.id),
            "start_date": today.isoformat(),
            "end_date": (today + datetime.timedelta(days=20)).isoformat(),
            "channel": "FACEBOOK",
        }
        response = self.client.post(url, data=payload)

        new_pkg = Package.objects.filter(name="Chiến dịch Mùa Hè 2026").first()
        self.assertIsNotNone(new_pkg)
        self.assertEqual(new_pkg.status, PackageStatus.DRAFT)
        self.assertEqual(new_pkg.coordinator_membership, self.coord_membership)
        self.assertRedirects(
            response,
            reverse("workspaces:package_detail", kwargs={"workspace_id": self.workspace.id, "package_id": new_pkg.id}),
        )

    def test_package_create_validation_error_preserves_input(self):
        """Khi dữ liệu không hợp lệ (ngày kết thúc < ngày bắt đầu), form trả về status 400 và giữ lại dữ liệu đã nhập."""
        self.client.force_login(self.owner)
        url = reverse("workspaces:package_create", kwargs={"workspace_id": self.workspace.id})
        today = timezone.now().date()
        payload = {
            "name": "Gói lỗi ngày",
            "objective": "Mục tiêu hợp lệ nhưng ngày bị đảo lộn",
            "coordinator_membership": str(self.coord_membership.id),
            "start_date": (today + datetime.timedelta(days=10)).isoformat(),
            "end_date": today.isoformat(),
            "channel": "FACEBOOK",
        }
        response = self.client.post(url, data=payload)

        self.assertEqual(response.status_code, 400)
        content = response.content.decode("utf-8")
        self.assertIn("Ngày kết thúc không được trước ngày bắt đầu", content)
        self.assertIn("Gói lỗi ngày", content)
        self.assertIn("Mục tiêu hợp lệ nhưng ngày bị đảo lộn", content)

    def test_package_edit_success(self):
        """Sửa gói thành công cập nhật tên, mục tiêu và người điều phối."""
        self.client.force_login(self.owner)
        url = reverse("workspaces:package_edit", kwargs={"workspace_id": self.workspace.id, "package_id": self.package.id})
        today = timezone.now().date()
        payload = {
            "name": "Chiến dịch Đã Cập Nhật",
            "objective": "Mục tiêu mới sắc nét hơn",
            "coordinator_membership": str(self.owner_membership.id),
            "start_date": today.isoformat(),
            "end_date": (today + datetime.timedelta(days=30)).isoformat(),
            "channel": "FACEBOOK",
            "expected_row_version": self.package.row_version,
        }
        response = self.client.post(url, data=payload)

        self.package.refresh_from_db()
        self.assertEqual(self.package.name, "Chiến dịch Đã Cập Nhật")
        self.assertEqual(self.package.objective, "Mục tiêu mới sắc nét hơn")
        self.assertEqual(self.package.coordinator_membership, self.owner_membership)
        self.assertRedirects(
            response,
            reverse("workspaces:package_detail", kwargs={"workspace_id": self.workspace.id, "package_id": self.package.id}),
        )

    def test_package_create_and_edit_permission_denied_for_non_owner(self):
        """Chỉ Owner mới có quyền tạo và sửa gói. Coordinator và Member nhận lỗi 403."""
        self.client.force_login(self.coordinator)
        create_url = reverse("workspaces:package_create", kwargs={"workspace_id": self.workspace.id})
        resp = self.client.get(create_url)
        self.assertEqual(resp.status_code, 403)

        edit_url = reverse("workspaces:package_edit", kwargs={"workspace_id": self.workspace.id, "package_id": self.package.id})
        resp = self.client.get(edit_url)
        self.assertEqual(resp.status_code, 403)

        self.client.force_login(self.member)
        resp = self.client.get(create_url)
        self.assertEqual(resp.status_code, 403)
