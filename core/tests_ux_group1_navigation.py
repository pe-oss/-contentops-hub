import datetime
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
    Package,
    PackageStatus,
)
from apps.workspaces.services import create_workspace_with_owner

User = get_user_model()


class UXGroup1NavigationTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(username="grp1_owner", email="owner@grp1.vn", password="password123")
        self.member = User.objects.create_user(username="grp1_member", email="member@grp1.vn", password="password123")
        self.outsider = User.objects.create_user(username="grp1_outsider", email="outsider@grp1.vn", password="password123")

        self.workspace = create_workspace_with_owner(
            user=self.owner,
            name="Workspace Group 1",
            timezone_str="Asia/Ho_Chi_Minh",
        )
        self.member_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.member,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE,
            status=MembershipStatus.ACTIVE,
        )

        now = timezone.now()
        self.package = Package.objects.create(
            workspace=self.workspace,
            name="Gói Tháng Này",
            objective="Mục tiêu gói test lịch",
            coordinator_membership=self.member_membership,
            start_date=now.date(),
            end_date=now.date() + datetime.timedelta(days=30),
            status=PackageStatus.ACTIVE,
        )

        # Bài 1 gán cho member
        self.item_member = ContentItem.objects.create(
            workspace=self.workspace,
            package=self.package,
            title="Bài viết của Member",
            brief="Yêu cầu viết bài 1",
            state=ContentItemState.WRITING,
            writer_membership=self.member_membership,
            editor_membership=self.member_membership,
            publisher_membership=self.member_membership,
            writing_deadline=now + datetime.timedelta(days=2),
            editing_deadline=now + datetime.timedelta(days=4),
            review_deadline=now + datetime.timedelta(days=6),
            planned_publish_at=now + datetime.timedelta(days=8),
        )

        # Bài 2 không gán cho member (gán cho owner)
        owner_mem = Membership.objects.get(workspace=self.workspace, user=self.owner)
        self.item_owner = ContentItem.objects.create(
            workspace=self.workspace,
            package=self.package,
            title="Bài viết riêng của Owner",
            brief="Yêu cầu viết bài 2",
            state=ContentItemState.WRITING,
            writer_membership=owner_mem,
            editor_membership=owner_mem,
            publisher_membership=owner_mem,
            writing_deadline=now + datetime.timedelta(days=2),
            editing_deadline=now + datetime.timedelta(days=4),
            review_deadline=now + datetime.timedelta(days=6),
            planned_publish_at=now + datetime.timedelta(days=8),
        )

    def test_calendar_view_owner_and_member(self):
        # 1. Owner vào xem lịch -> thấy cả 2 bài
        self.client.force_login(self.owner)
        url_cal = reverse("workspaces:calendar", kwargs={"workspace_id": self.workspace.id})
        resp = self.client.get(url_cal)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Lịch nội dung")
        self.assertContains(resp, "Bài viết của Member")
        self.assertContains(resp, "Bài viết riêng của Owner")
        self.assertContains(resp, "Hôm nay")

        # 2. Member chỉ thấy bài được giao hoặc trong gói điều phối (member là coord gói này nên thấy trong scope)
        self.client.force_login(self.member)
        resp_mem = self.client.get(url_cal)
        self.assertEqual(resp_mem.status_code, 200)

        # 3. Outsider không thuộc workspace -> 404
        self.client.force_login(self.outsider)
        resp_out = self.client.get(url_cal)
        self.assertEqual(resp_out.status_code, 404)

    def test_calendar_navigation_query_params(self):
        self.client.force_login(self.owner)
        url_cal = reverse("workspaces:calendar", kwargs={"workspace_id": self.workspace.id})
        resp = self.client.get(url_cal, {"year": 2026, "month": 12})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Tháng 12/2026")
        self.assertContains(resp, "Tháng 11/2026")
        self.assertContains(resp, "Tháng 1/2027")

    def test_overview_navigation_cleanups(self):
        self.client.force_login(self.owner)
        url_detail = reverse("workspaces:detail", kwargs={"workspace_id": self.workspace.id})
        resp = self.client.get(url_detail)
        self.assertEqual(resp.status_code, 200)

        # Kiểm tra tiêu đề Vùng 2
        self.assertContains(resp, "Vùng 2 — Bị chặn / Trễ hạn")

        # Kiểm tra hàng menu ngang lặp lại đã bị bỏ
        self.assertNotContains(resp, "← Workspaces</a>")
        self.assertNotContains(resp, "📋 Việc của tôi</a>")

        # Kiểm tra link lịch đúng route
        url_cal = reverse("workspaces:calendar", kwargs={"workspace_id": self.workspace.id})
        self.assertContains(resp, url_cal)

    def test_brand_and_settings_navigation(self):
        self.client.force_login(self.owner)
        url_edit = reverse("workspaces:edit", kwargs={"workspace_id": self.workspace.id})
        resp = self.client.get(url_edit)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Thông tin workspace")
        self.assertContains(resp, "Hồ sơ thương hiệu")

        url_brand = reverse("workspaces:brand_profile", kwargs={"workspace_id": self.workspace.id})
        resp_brand = self.client.get(url_brand)
        self.assertEqual(resp_brand.status_code, 200)
        self.assertContains(resp_brand, "Thông tin workspace")
        self.assertContains(resp_brand, "Hồ sơ thương hiệu")
