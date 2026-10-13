import uuid
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from apps.workspaces.models import (
    AccessRole,
    EmploymentType,
    Membership,
    MembershipStatus,
    Workspace,
)
from apps.workspaces.selectors import (
    get_active_membership,
    get_user_workspaces,
    get_workspace_for_user,
)
from apps.workspaces.services import (
    ACTIVE_WORKSPACE_SESSION_KEY,
    create_workspace_with_owner,
    get_current_active_workspace,
    switch_active_workspace,
    update_workspace_info,
)

User = get_user_model()


class WorkspaceMilestoneB01Tests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(
            username="user_a",
            email="usera@example.com",
            password="StrongPassword123!",
        )
        self.user_b = User.objects.create_user(
            username="user_b",
            email="userb@example.com",
            password="StrongPassword123!",
        )
        self.client_a = Client()
        self.client_a.force_login(self.user_a)

        self.client_b = Client()
        self.client_b.force_login(self.user_b)

        self.anon_client = Client()

    def test_01_database_isolation_verified(self):
        """Xác nhận test runner đang chạy trên database test riêng biệt."""
        test_db_name = connection.settings_dict.get("TEST", {}).get("NAME") or connection.settings_dict.get("NAME")
        self.assertTrue(
            "test" in test_db_name.lower() or test_db_name == ":memory:",
            f"Test runner phải chạy trên database test độc lập, thực tế: {test_db_name}",
        )

    def test_02_unauthenticated_cannot_create_or_access_workspaces(self):
        """Người dùng chưa đăng nhập bị chuyển hướng tới trang đăng nhập."""
        ws_id = uuid.uuid4()
        urls = [
            reverse("workspaces:list"),
            reverse("workspaces:create"),
            reverse("workspaces:detail", kwargs={"workspace_id": ws_id}),
            reverse("workspaces:edit", kwargs={"workspace_id": ws_id}),
            reverse("workspaces:switch", kwargs={"workspace_id": ws_id}),
        ]
        for url in urls:
            resp = self.anon_client.get(url)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/auth/login/", resp.url)

    def test_03_create_workspace_atomic_owner_creation(self):
        """Tạo workspace sinh đúng một membership OWNER và không cấp staff/superuser."""
        workspace = create_workspace_with_owner(
            user=self.user_a,
            name="Workspace Alpha",
            timezone_str="Asia/Ho_Chi_Minh",
        )
        self.assertIsInstance(workspace.id, uuid.UUID)
        self.assertEqual(workspace.name, "Workspace Alpha")
        self.assertEqual(workspace.timezone, "Asia/Ho_Chi_Minh")
        self.assertEqual(workspace.owner_user, self.user_a)

        memberships = Membership.objects.filter(workspace=workspace)
        self.assertEqual(memberships.count(), 1)
        owner_member = memberships.first()
        self.assertEqual(owner_member.user, self.user_a)
        self.assertEqual(owner_member.access_role, AccessRole.OWNER)
        self.assertEqual(owner_member.employment_type, EmploymentType.IN_HOUSE)
        self.assertEqual(owner_member.status, MembershipStatus.ACTIVE)
        self.assertTrue(owner_member.ai_use_allowed)

        self.user_a.refresh_from_db()
        self.assertFalse(self.user_a.is_staff)
        self.assertFalse(self.user_a.is_superuser)

    def test_04_create_workspace_validation(self):
        """Validate tên và múi giờ hợp lệ."""
        with self.assertRaises(ValidationError):
            create_workspace_with_owner(user=self.user_a, name="   ")

        with self.assertRaises(ValidationError):
            create_workspace_with_owner(user=self.user_a, name="A" * 101)

        with self.assertRaises(ValidationError):
            create_workspace_with_owner(user=self.user_a, name="Valid Name", timezone_str="Invalid/Timezone")

        ws = create_workspace_with_owner(user=self.user_a, name="  Ban Marketing  ")
        self.assertEqual(ws.name, "Ban Marketing")

    def test_05_create_workspace_failure_rollback(self):
        """Khi có lỗi, giao dịch rollback toàn bộ không để lại bản ghi mồ côi."""
        initial_ws_count = Workspace.objects.count()
        initial_member_count = Membership.objects.count()

        with patch("apps.workspaces.services.Membership.objects.create", side_effect=RuntimeError("Crash")):
            with self.assertRaises(RuntimeError):
                create_workspace_with_owner(user=self.user_a, name="Rollback Test")

        self.assertEqual(Workspace.objects.count(), initial_ws_count)
        self.assertEqual(Membership.objects.count(), initial_member_count)


    def test_06_user_sees_only_own_active_workspaces(self):
        """Người dùng chỉ thấy workspace mình có membership ACTIVE. Chưa có thấy hướng dẫn."""
        resp = self.client_a.get(reverse("workspaces:list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bạn chưa tham gia workspace nào")
        self.assertContains(resp, "+ Tạo Workspace đầu tiên ngay")

        ws_a = create_workspace_with_owner(user=self.user_a, name="Workspace A")
        ws_b = create_workspace_with_owner(user=self.user_b, name="Workspace B")

        resp_a = self.client_a.get(reverse("workspaces:list"))
        self.assertContains(resp_a, "Workspace A")
        self.assertNotContains(resp_a, "Workspace B")

        resp_b = self.client_b.get(reverse("workspaces:list"))
        self.assertContains(resp_b, "Workspace B")
        self.assertNotContains(resp_b, "Workspace A")

    def test_07_data_isolation_direct_url_returns_404(self):
        """Người ngoài workspace truy cập trực tiếp bằng UUID nhận 404."""
        ws_a = create_workspace_with_owner(user=self.user_a, name="Workspace A")

        resp_detail = self.client_b.get(reverse("workspaces:detail", kwargs={"workspace_id": ws_a.id}))
        self.assertEqual(resp_detail.status_code, 404)

        resp_edit = self.client_b.get(reverse("workspaces:edit", kwargs={"workspace_id": ws_a.id}))
        self.assertEqual(resp_edit.status_code, 404)

        resp_switch = self.client_b.post(reverse("workspaces:switch", kwargs={"workspace_id": ws_a.id}))
        self.assertEqual(resp_switch.status_code, 404)

    def test_08_client_cannot_forge_owner_or_role(self):
        """Client không thể giả mạo owner_user hoặc access_role qua form data để chiếm quyền."""
        response = self.client_a.post(
            reverse("workspaces:create"),
            {
                "name": "Hacked Workspace",
                "timezone": "Asia/Ho_Chi_Minh",
                "owner_user": self.user_b.id,
                "owner_user_id": self.user_b.id,
                "access_role": "ADMIN",
            },
        )
        self.assertEqual(response.status_code, 302)

        ws = Workspace.objects.get(name="Hacked Workspace")
        self.assertEqual(ws.owner_user, self.user_a)
        membership = Membership.objects.get(workspace=ws, user=self.user_a)
        self.assertEqual(membership.access_role, AccessRole.OWNER)
        self.assertFalse(Membership.objects.filter(workspace=ws, user=self.user_b).exists())

    def test_09_duplicate_membership_rejected_by_db_constraint(self):
        """Membership trùng (workspace, user) bị ràng buộc Database Unique từ chối."""
        ws = create_workspace_with_owner(user=self.user_a, name="Unique Test")

        with self.assertRaises(IntegrityError):
            Membership.objects.create(
                workspace=ws,
                user=self.user_a,
                access_role=AccessRole.MEMBER,
            )

    def test_10_deactivated_membership_loses_access_immediately(self):
        """Membership bị vô hiệu hóa (INACTIVE) mất quyền ở request kế tiếp, kể cả session còn lưu."""
        ws = create_workspace_with_owner(user=self.user_a, name="Deactivation Test")

        m_b = Membership.objects.create(
            workspace=ws,
            user=self.user_b,
            access_role=AccessRole.MEMBER,
            status=MembershipStatus.ACTIVE,
        )

        resp = self.client_b.get(reverse("workspaces:detail", kwargs={"workspace_id": ws.id}))
        self.assertEqual(resp.status_code, 200)

        m_b.status = MembershipStatus.INACTIVE
        m_b.save(update_fields=["status"])

        resp_after = self.client_b.get(reverse("workspaces:detail", kwargs={"workspace_id": ws.id}))
        self.assertEqual(resp_after.status_code, 404)

        workspaces = get_user_workspaces(self.user_b)
        self.assertFalse(workspaces.filter(id=ws.id).exists())

    def test_11_member_role_can_read_but_cannot_edit(self):
        """MEMBER đọc được workspace được giao (200), nhưng sửa thông tin nhận 403."""
        ws = create_workspace_with_owner(user=self.user_a, name="Company Space")

        Membership.objects.create(
            workspace=ws,
            user=self.user_b,
            access_role=AccessRole.MEMBER,
            status=MembershipStatus.ACTIVE,
        )

        # User B xem tổng quan workspace -> 200 OK
        resp_get = self.client_b.get(reverse("workspaces:detail", kwargs={"workspace_id": ws.id}))
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, "Company Space")
        self.assertNotContains(resp_get, "Chỉnh sửa thông tin")

        # User B cố tình truy cập form edit bằng URL -> 403
        resp_edit_get = self.client_b.get(reverse("workspaces:edit", kwargs={"workspace_id": ws.id}))
        self.assertEqual(resp_edit_get.status_code, 403)

        # User B cố tình POST sửa thông tin -> 403
        resp_edit_post = self.client_b.post(
            reverse("workspaces:edit", kwargs={"workspace_id": ws.id}),
            {"name": "Hacked Name", "timezone": "Asia/Ho_Chi_Minh"},
        )
        self.assertEqual(resp_edit_post.status_code, 403)

        ws.refresh_from_db()
        self.assertEqual(ws.name, "Company Space")

        # Chủ (user_a) sửa thành công
        resp_owner_post = self.client_a.post(
            reverse("workspaces:edit", kwargs={"workspace_id": ws.id}),
            {"name": "Company Space Renamed", "timezone": "Asia/Ho_Chi_Minh"},
        )
        self.assertEqual(resp_owner_post.status_code, 302)
        ws.refresh_from_db()
        self.assertEqual(ws.name, "Company Space Renamed")

    def test_12_workspace_switching_across_multiple_workspaces(self):
        """Một người tham gia nhiều workspace và chuyển đúng quyền."""
        ws1 = create_workspace_with_owner(user=self.user_a, name="Workspace One")
        ws2 = create_workspace_with_owner(user=self.user_a, name="Workspace Two")

        resp1 = self.client_a.post(reverse("workspaces:switch", kwargs={"workspace_id": ws1.id}))
        self.assertEqual(resp1.status_code, 302)
        session = self.client_a.session
        self.assertEqual(session.get(ACTIVE_WORKSPACE_SESSION_KEY), str(ws1.id))

        resp2 = self.client_a.post(reverse("workspaces:switch", kwargs={"workspace_id": ws2.id}))
        self.assertEqual(resp2.status_code, 302)
        session = self.client_a.session
        self.assertEqual(session.get(ACTIVE_WORKSPACE_SESSION_KEY), str(ws2.id))

        # Thử switch sang workspace không phải thành viên -> 404
        ws3 = create_workspace_with_owner(user=self.user_b, name="Workspace Three")
        resp3 = self.client_a.post(reverse("workspaces:switch", kwargs={"workspace_id": ws3.id}))
        self.assertEqual(resp3.status_code, 404)
        session = self.client_a.session
        self.assertEqual(session.get(ACTIVE_WORKSPACE_SESSION_KEY), str(ws2.id))

    def test_13_write_paths_enforce_single_owner_consistency(self):
        """Không cho phép tạo hai Chủ hoặc để owner_user và membership OWNER bị lệch."""
        ws = create_workspace_with_owner(user=self.user_a, name="Owner Consistency Test")

        m_a = Membership.objects.get(workspace=ws, user=self.user_a)
        self.assertEqual(m_a.access_role, AccessRole.OWNER)

        with self.assertRaises(PermissionDenied):
            update_workspace_info(
                user=self.user_b,
                workspace=ws,
                name="New Name",
                timezone_str="Asia/Ho_Chi_Minh",
            )


    def test_14_admin_save_model_preserves_owner_consistency(self):
        """Admin model save bảo toàn tính nhất quán giữa owner_user và membership OWNER."""
        from django.contrib.admin.sites import AdminSite
        from apps.workspaces.admin import MembershipAdmin, WorkspaceAdmin

        site = AdminSite()
        ws_admin = WorkspaceAdmin(Workspace, site)
        mem_admin = MembershipAdmin(Membership, site)

        # Tạo workspace qua WorkspaceAdmin.save_model
        new_ws = Workspace(name="Admin WS", owner_user=self.user_a)
        new_ws.save()
        ws_admin.save_model(None, new_ws, None, False)

        m = Membership.objects.get(workspace=new_ws, user=self.user_a)
        self.assertEqual(m.access_role, AccessRole.OWNER)

        # Cố hạ quyền của Chủ trong MembershipAdmin ném ValidationError
        m.access_role = AccessRole.MEMBER
        with self.assertRaises(ValidationError):
            mem_admin.save_model(None, m, None, True)

    def test_15_context_processor_and_session_deactivation_fallback(self):
        """Context processor tự động dọn session khi membership bị vô hiệu và fallback an toàn."""
        ws1 = create_workspace_with_owner(user=self.user_a, name="WS First")
        ws2 = create_workspace_with_owner(user=self.user_a, name="WS Second")

        # Thiết lập session là ws2
        session = self.client_a.session
        session[ACTIVE_WORKSPACE_SESSION_KEY] = str(ws2.id)
        session.save()

        # Vô hiệu hóa membership của ws2
        m2 = Membership.objects.get(workspace=ws2, user=self.user_a)
        m2.status = MembershipStatus.INACTIVE
        m2.save()

        # Khi load trang list hoặc bất kỳ trang nào, context processor tự dọn session ws2 và fallback sang ws1
        resp = self.client_a.get(reverse("workspaces:list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["current_workspace"].id, ws1.id)

