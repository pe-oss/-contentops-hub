import datetime
import uuid
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, IntegrityError, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AccountEmailIdentity
from apps.accounts.services import normalize_email
from apps.workspaces.models import (
    AccessRole,
    EmploymentType,
    Invitation,
    Membership,
    MembershipStatus,
    Workspace,
)
from apps.workspaces.selectors import (
    get_invitation_by_id_for_workspace,
    get_invitation_by_token,
    get_membership_by_id_for_workspace,
    get_workspace_for_user,
    get_workspace_invitations,
    get_workspace_members,
)
from apps.workspaces.services import (
    ACTIVE_WORKSPACE_SESSION_KEY,
    accept_workspace_invitation,
    create_workspace_invitation,
    create_workspace_with_owner,
    deactivate_membership,
    get_current_active_workspace,
    reactivate_membership,
    resend_workspace_invitation,
    revoke_workspace_invitation,
    update_member_settings,
)

User = get_user_model()


class WorkspaceMilestoneB02Tests(TestCase):
    def setUp(self):
        # 1. Owner User
        self.owner = User.objects.create_user(
            username="owner_user",
            email="owner@example.com",
            password="StrongPassword123!",
        )
        self.owner.email_identity.mark_as_verified()

        # 2. Member User (Nội bộ)
        self.member = User.objects.create_user(
            username="member_user",
            email="member@example.com",
            password="StrongPassword123!",
        )
        self.member.email_identity.mark_as_verified()

        # 3. Invitee User (Đã xác minh email trùng lời mời)
        self.invitee_verified = User.objects.create_user(
            username="invitee_verified",
            email="freelancer@example.com",
            password="StrongPassword123!",
        )
        self.invitee_verified.email_identity.mark_as_verified()

        # 4. Invitee User (Chưa xác minh email)
        self.invitee_unverified = User.objects.create_user(
            username="invitee_unverified",
            email="unverified@example.com",
            password="StrongPassword123!",
        )
        # unverified: verified_at is None by default

        # 5. Outside User (Người ngoài, có email khác)
        self.outsider = User.objects.create_user(
            username="outsider_user",
            email="outsider@example.com",
            password="StrongPassword123!",
        )
        self.outsider.email_identity.mark_as_verified()

        self.workspace = create_workspace_with_owner(
            user=self.owner,
            name="Workspace Kiểm Thử B02",
            timezone_str="Asia/Ho_Chi_Minh",
        )

        self.member_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.member,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE,
            status=MembershipStatus.ACTIVE,
            ai_use_allowed=False,
        )

        self.owner_client = Client()
        self.owner_client.force_login(self.owner)

        self.member_client = Client()
        self.member_client.force_login(self.member)

        self.invitee_verified_client = Client()
        self.invitee_verified_client.force_login(self.invitee_verified)

        self.invitee_unverified_client = Client()
        self.invitee_unverified_client.force_login(self.invitee_unverified)

        self.outsider_client = Client()
        self.outsider_client.force_login(self.outsider)

        self.anon_client = Client()

    def test_01_database_isolation_verified(self):
        """Xác nhận test runner đang chạy trên database test riêng biệt."""
        test_db_name = connection.settings_dict.get("TEST", {}).get("NAME") or connection.settings_dict.get("NAME")
        self.assertTrue(
            "test" in test_db_name.lower() or test_db_name == ":memory:",
            f"Test runner phải chạy trên database test độc lập, thực tế: {test_db_name}",
        )

    def test_02_permission_matrix_owner_vs_member_vs_outsider(self):
        """Ma trận quyền B02 cho các thao tác."""
        members_url = reverse("workspaces:members", kwargs={"workspace_id": self.workspace.id})
        invite_url = reverse("workspaces:invite", kwargs={"workspace_id": self.workspace.id})

        res_owner = self.owner_client.get(members_url)
        self.assertEqual(res_owner.status_code, 200)
        self.assertContains(res_owner, "+ Mời thành viên")

        res_invite_get = self.owner_client.get(invite_url)
        self.assertEqual(res_invite_get.status_code, 200)

        res_member = self.member_client.get(members_url)
        self.assertEqual(res_member.status_code, 200)
        self.assertNotContains(res_member, "+ Mời thành viên")

        res_member_invite = self.member_client.get(invite_url)
        self.assertEqual(res_member_invite.status_code, 403)

        res_outsider = self.outsider_client.get(members_url)
        self.assertEqual(res_outsider.status_code, 404)

        res_outsider_invite = self.outsider_client.get(invite_url)
        self.assertEqual(res_outsider_invite.status_code, 404)

    def test_03_create_invitation_success_and_token_hashed(self):
        """Tạo lời mời thành công, token lưu dạng hash SHA-256."""
        invitation, raw_token = create_workspace_invitation(
            user=self.owner,
            workspace=self.workspace,
            email="  Freelancer@Example.COM  ",
            employment_type=EmploymentType.FREELANCER,
            ai_use_allowed=True,
            send_email=False,
        )

        self.assertEqual(invitation.email, "freelancer@example.com")
        self.assertEqual(invitation.employment_type, EmploymentType.FREELANCER)
        self.assertTrue(invitation.ai_use_allowed)
        self.assertEqual(invitation.access_role, AccessRole.MEMBER)
        self.assertNotEqual(invitation.token_hash, raw_token)
        self.assertEqual(len(invitation.token_hash), 64)
        self.assertIsNone(invitation.accepted_at)
        self.assertIsNone(invitation.revoked_at)
        self.assertTrue(invitation.is_pending)

        diff_days = (invitation.expires_at - timezone.now()).days
        self.assertIn(diff_days, [6, 7])

    def test_04_create_invitation_owner_role_forbidden(self):
        """Không cho phép tạo lời mời cho vai trò OWNER."""
        with self.assertRaises(ValidationError):
            inv = Invitation(
                workspace=self.workspace,
                email="someone@example.com",
                token_hash="a" * 64,
                access_role=AccessRole.OWNER,
                expires_at=timezone.now() + datetime.timedelta(days=7),
            )
            inv.full_clean()

    def test_05_create_invitation_duplicate_pending_rejected(self):
        """Không cho phép gửi hai lời mời đang chờ xử lý cho cùng một email."""
        create_workspace_invitation(
            user=self.owner,
            workspace=self.workspace,
            email="freelancer@example.com",
            send_email=False,
        )

        with self.assertRaises(ValidationError) as ctx:
            create_workspace_invitation(
                user=self.owner,
                workspace=self.workspace,
                email="freelancer@example.com",
                send_email=False,
            )
        self.assertIn("email", ctx.exception.message_dict)

    def test_06_cannot_invite_existing_active_or_deactivated_member(self):
        """Không cho phép mời người đã là thành viên (kể cả ACTIVE hoặc INACTIVE)."""
        # 1. Active member
        with self.assertRaises(ValidationError) as ctx:
            create_workspace_invitation(
                user=self.owner,
                workspace=self.workspace,
                email=self.member.email,
                send_email=False,
            )
        self.assertIn("đang hoạt động", str(ctx.exception))

        # 2. Deactivated member
        deactivate_membership(user=self.owner, workspace=self.workspace, membership=self.member_membership)
        with self.assertRaises(ValidationError) as ctx2:
            create_workspace_invitation(
                user=self.owner,
                workspace=self.workspace,
                email=self.member.email,
                send_email=False,
            )
        self.assertIn("vô hiệu hóa", str(ctx2.exception))


    def test_07_email_sent_on_commit_and_smtp_error_resilience(self):
        """Lỗi gửi mail không làm rollback lời mời đã tạo."""
        with patch("django.core.mail.send_mail", side_effect=Exception("SMTP Connection Error")):
            invitation, raw_token = create_workspace_invitation(
                user=self.owner,
                workspace=self.workspace,
                email="freelancer@example.com",
                send_email=True,
            )
            self.assertIsNotNone(invitation.pk)
            self.assertTrue(Invitation.objects.filter(pk=invitation.pk).exists())

    def test_08_resend_cooldown_and_revocation(self):
        """Gửi lại có cooldown 60s; sau khi thu hồi không thể nhận hoặc gửi lại."""
        invitation, raw_token = create_workspace_invitation(
            user=self.owner,
            workspace=self.workspace,
            email="freelancer@example.com",
            send_email=False,
        )

        with self.assertRaises(ValidationError) as ctx:
            resend_workspace_invitation(
                user=self.owner,
                invitation=invitation,
                send_email=False,
            )
        self.assertIn("giây", str(ctx.exception))

        invitation.last_sent_at = timezone.now() - datetime.timedelta(seconds=65)
        invitation.save(update_fields=["last_sent_at"])

        old_hash = invitation.token_hash
        new_token = resend_workspace_invitation(
            user=self.owner,
            invitation=invitation,
            send_email=False,
        )
        invitation.refresh_from_db()
        self.assertNotEqual(invitation.token_hash, old_hash)

        revoke_workspace_invitation(user=self.owner, invitation=invitation)
        invitation.refresh_from_db()
        self.assertTrue(invitation.is_revoked)

        with self.assertRaises(ValidationError):
            resend_workspace_invitation(
                user=self.owner,
                invitation=invitation,
                send_email=False,
            )

    def test_09_accept_requires_login_and_verified_email(self):
        """Nhận lời mời yêu cầu đăng nhập và xác minh email."""
        invitation, raw_token = create_workspace_invitation(
            user=self.owner,
            workspace=self.workspace,
            email="freelancer@example.com",
            send_email=False,
        )
        accept_url = reverse("workspaces:invitation_accept", kwargs={"token": raw_token})

        res_anon = self.anon_client.get(accept_url)
        self.assertEqual(res_anon.status_code, 302)
        self.assertIn(reverse("accounts:login"), res_anon.url)
        self.assertIn(f"next={accept_url}", res_anon.url)

        inv_unver, raw_unver = create_workspace_invitation(
            user=self.owner,
            workspace=self.workspace,
            email="unverified@example.com",
            send_email=False,
        )
        accept_unver_url = reverse("workspaces:invitation_accept", kwargs={"token": raw_unver})

        res_unver = self.invitee_unverified_client.get(accept_unver_url)
        self.assertEqual(res_unver.status_code, 200)
        self.assertContains(res_unver, "Cần xác minh email")

    def test_10_accept_mismatched_email_blocked(self):
        """Tài khoản có email khác không được chấp nhận lời mời."""
        invitation, raw_token = create_workspace_invitation(
            user=self.owner,
            workspace=self.workspace,
            email="freelancer@example.com",
            send_email=False,
        )
        accept_url = reverse("workspaces:invitation_accept", kwargs={"token": raw_token})

        res_mismatch = self.outsider_client.get(accept_url)
        self.assertEqual(res_mismatch.status_code, 200)
        self.assertContains(res_mismatch, "Tài khoản không khớp email được mời")

        res_post_mismatch = self.outsider_client.post(accept_url)
        self.assertEqual(res_post_mismatch.status_code, 200)
        self.assertContains(res_post_mismatch, "không khớp")


    def test_11_accept_happy_path_creates_membership_and_sets_session(self):
        """Nhận lời mời thành công, tạo membership ACTIVE, thiết lập session."""
        invitation, raw_token = create_workspace_invitation(
            user=self.owner,
            workspace=self.workspace,
            email="freelancer@example.com",
            employment_type=EmploymentType.FREELANCER,
            ai_use_allowed=True,
            send_email=False,
        )
        accept_url = reverse("workspaces:invitation_accept", kwargs={"token": raw_token})

        res_get = self.invitee_verified_client.get(accept_url)
        self.assertEqual(res_get.status_code, 200)
        self.assertContains(res_get, self.workspace.name)

        res_post = self.invitee_verified_client.post(accept_url)
        self.assertEqual(res_post.status_code, 302)
        self.assertRedirects(res_post, reverse("workspaces:detail", kwargs={"workspace_id": self.workspace.id}))

        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.accepted_at)
        self.assertTrue(invitation.is_accepted)

        membership = Membership.objects.get(workspace=self.workspace, user=self.invitee_verified)
        self.assertEqual(membership.access_role, AccessRole.MEMBER)
        self.assertEqual(membership.employment_type, EmploymentType.FREELANCER)
        self.assertTrue(membership.ai_use_allowed)
        self.assertEqual(membership.status, MembershipStatus.ACTIVE)

        self.assertEqual(
            self.invitee_verified_client.session.get(ACTIVE_WORKSPACE_SESSION_KEY),
            str(self.workspace.id),
        )

    def test_12_token_single_use_expired_revoked_and_invalid(self):
        """Ràng buộc token: dùng 1 lần, hết hạn, đã thu hồi, giả mạo."""
        invitation, raw_token = create_workspace_invitation(
            user=self.owner,
            workspace=self.workspace,
            email="freelancer@example.com",
            send_email=False,
        )
        accept_url = reverse("workspaces:invitation_accept", kwargs={"token": raw_token})

        # 1. Nhận lần 1
        accept_workspace_invitation(user=self.invitee_verified, raw_token=raw_token)

        # 2. Dùng lại lần 2
        res_reuse = self.invitee_verified_client.get(accept_url)
        self.assertEqual(res_reuse.status_code, 200)
        self.assertContains(res_reuse, "đã được chấp nhận trước đó")

        # 3. Hết hạn
        inv_exp, raw_exp = create_workspace_invitation(
            user=self.owner,
            workspace=self.workspace,
            email="expired@example.com",
            send_email=False,
        )
        inv_exp.expires_at = timezone.now() - datetime.timedelta(hours=1)
        inv_exp.save(update_fields=["expires_at"])
        res_exp = self.invitee_verified_client.get(reverse("workspaces:invitation_accept", kwargs={"token": raw_exp}))
        self.assertContains(res_exp, "đã hết hạn")

        # 4. Đã thu hồi
        inv_rev, raw_rev = create_workspace_invitation(
            user=self.owner,
            workspace=self.workspace,
            email="revoked@example.com",
            send_email=False,
        )
        revoke_workspace_invitation(user=self.owner, invitation=inv_rev)
        res_rev = self.invitee_verified_client.get(reverse("workspaces:invitation_accept", kwargs={"token": raw_rev}))
        self.assertContains(res_rev, "đã bị thu hồi")

        # 5. Token không tồn tại
        res_fake = self.invitee_verified_client.get(reverse("workspaces:invitation_accept", kwargs={"token": "fake-token-12345"}))
        self.assertEqual(res_fake.status_code, 404)


    def test_13_owner_protection_guards(self):
        """Bảo vệ Chủ workspace không bị vô hiệu hóa hoặc hạ quyền."""
        owner_membership = Membership.objects.get(workspace=self.workspace, user=self.owner)

        with self.assertRaises(ValidationError) as ctx:
            deactivate_membership(user=self.owner, workspace=self.workspace, membership=owner_membership)
        self.assertIn("Không thể vô hiệu hóa Chủ", str(ctx.exception))

        with self.assertRaises(ValidationError) as ctx2:
            update_member_settings(
                user=self.owner,
                workspace=self.workspace,
                membership=owner_membership,
                employment_type=EmploymentType.FREELANCER,
                ai_use_allowed=False,
            )
        self.assertIn("Không thể sửa vai trò", str(ctx2.exception))

    def test_14_immediate_permission_effect_on_deactivation(self):
        """Hiệu lực tức thì: thành viên bị vô hiệu nhận ngay 404 ở request kế tiếp."""
        session = self.member_client.session
        session[ACTIVE_WORKSPACE_SESSION_KEY] = str(self.workspace.id)
        session.save()

        res_before = self.member_client.get(reverse("workspaces:detail", kwargs={"workspace_id": self.workspace.id}))
        self.assertEqual(res_before.status_code, 200)

        deactivate_membership(user=self.owner, workspace=self.workspace, membership=self.member_membership)

        res_after = self.member_client.get(reverse("workspaces:detail", kwargs={"workspace_id": self.workspace.id}))
        self.assertEqual(res_after.status_code, 404)

        with self.assertRaises(Exception):
            get_workspace_for_user(self.member, self.workspace.id)

    def test_15_member_settings_update_by_owner(self):
        """Chủ cập nhật employment_type và ai_use_allowed của thành viên."""
        update_member_settings(
            user=self.owner,
            workspace=self.workspace,
            membership=self.member_membership,
            employment_type=EmploymentType.FREELANCER,
            ai_use_allowed=True,
        )
        self.member_membership.refresh_from_db()
        self.assertEqual(self.member_membership.employment_type, EmploymentType.FREELANCER)
        self.assertTrue(self.member_membership.ai_use_allowed)

    def test_16_reactivate_member_by_owner(self):
        """Chủ có thể kích hoạt lại thành viên đã bị vô hiệu hóa."""
        deactivate_membership(user=self.owner, workspace=self.workspace, membership=self.member_membership)
        self.member_membership.refresh_from_db()
        self.assertEqual(self.member_membership.status, MembershipStatus.INACTIVE)

        reactivate_membership(user=self.owner, workspace=self.workspace, membership=self.member_membership)
        self.member_membership.refresh_from_db()
        self.assertEqual(self.member_membership.status, MembershipStatus.ACTIVE)


    def test_17_invitation_revoked_before_accept_is_blocked(self):
        """Lời mời bị thu hồi thì không thể chấp nhận được nữa."""
        invitation, raw_token = create_workspace_invitation(
            user=self.owner,
            workspace=self.workspace,
            email="freelancer@example.com",
            send_email=False,
        )
        revoke_workspace_invitation(user=self.owner, invitation=invitation)
        with self.assertRaises(ValidationError) as ctx:
            accept_workspace_invitation(user=self.invitee_verified, raw_token=raw_token)
        self.assertIn("thu hồi", str(ctx.exception))


class WorkspaceConcurrencyB02Tests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="concurrency_owner",
            email="c_owner@example.com",
            password="StrongPassword123!",
        )
        self.owner.email_identity.mark_as_verified()

        self.invitee = User.objects.create_user(
            username="concurrency_invitee",
            email="c_invitee@example.com",
            password="StrongPassword123!",
        )
        self.invitee.email_identity.mark_as_verified()

        self.workspace = create_workspace_with_owner(
            user=self.owner,
            name="Workspace Concurrency B02",
        )

    def test_concurrent_accept_requests(self):
        """Hai yêu cầu chấp nhận lời mời song song: chỉ một thành công, không tạo membership trùng."""
        import concurrent.futures

        invitation, raw_token = create_workspace_invitation(
            user=self.owner,
            workspace=self.workspace,
            email="c_invitee@example.com",
            send_email=False,
        )

        results = []
        errors = []

        def try_accept():
            from django.db import close_old_connections

            close_old_connections()
            try:
                ws, memb = accept_workspace_invitation(user=self.invitee, raw_token=raw_token)
                results.append(memb.id)
            except Exception as e:
                errors.append(e)
            finally:
                close_old_connections()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(try_accept), executor.submit(try_accept)]
            concurrent.futures.wait(futures)

        # Đúng một yêu cầu thành công và một yêu cầu bị từ chối
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        # Ràng buộc DB: chỉ có duy nhất 1 membership
        self.assertEqual(
            Membership.objects.filter(workspace=self.workspace, user=self.invitee).count(),
            1,
        )



