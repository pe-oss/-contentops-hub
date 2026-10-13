import uuid
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from apps.accounts.services import normalize_email
from .forms import (
    BrandProfileForm,
    MemberUpdateForm,
    WorkspaceCreateForm,
    WorkspaceInvitationForm,
    WorkspaceUpdateForm,
)
from .models import AccessRole, BrandProfile, EmploymentType, Invitation, Membership, MembershipStatus
from .selectors import (
    get_brand_profile,
    get_invitation_by_id_for_workspace,
    get_invitation_by_token,
    get_membership_by_id_for_workspace,
    get_user_workspaces,
    get_workspace_for_user,
    get_workspace_invitations,
    get_workspace_members,
)
from .services import (
    ConcurrencyConflictError,
    accept_workspace_invitation,
    create_workspace_invitation,
    create_workspace_with_owner,
    deactivate_membership,
    reactivate_membership,
    resend_workspace_invitation,
    revoke_workspace_invitation,
    save_brand_profile,
    switch_active_workspace,
    update_member_settings,
    update_workspace_info,
)


@method_decorator(login_required, name="dispatch")
class WorkspaceListView(View):
    def get(self, request):
        workspaces = get_user_workspaces(request.user)
        return render(
            request,
            "workspaces/workspace_list.html",
            {
                "workspaces": workspaces,
            },
        )


@method_decorator(login_required, name="dispatch")
class WorkspaceCreateView(View):
    def get(self, request):
        form = WorkspaceCreateForm()
        return render(
            request,
            "workspaces/workspace_form.html",
            {
                "form": form,
            },
        )

    def post(self, request):
        form = WorkspaceCreateForm(request.POST)
        if form.is_valid():
            workspace = create_workspace_with_owner(
                user=request.user,
                name=form.cleaned_data["name"],
                timezone_str=form.cleaned_data["timezone"],
            )
            # Tự động chọn workspace mới tạo vào session
            request.session["active_workspace_id"] = str(workspace.id)
            messages.success(request, f"Đã tạo workspace '{workspace.name}' thành công!")
            return redirect("workspaces:detail", workspace_id=workspace.id)

        return render(
            request,
            "workspaces/workspace_form.html",
            {
                "form": form,
            },
        )


@method_decorator(login_required, name="dispatch")
class WorkspaceDetailView(View):
    def get(self, request, workspace_id):
        # get_workspace_for_user trả về 404 nếu không tồn tại hoặc user không phải thành viên active
        workspace, membership = get_workspace_for_user(request.user, workspace_id)

        # Cập nhật session active workspace
        request.session["active_workspace_id"] = str(workspace.id)

        # Thống kê thành viên của workspace
        members_count = Membership.objects.filter(
            workspace=workspace,
            status=MembershipStatus.ACTIVE,
        ).count()

        return render(
            request,
            "workspaces/workspace_detail.html",
            {
                "workspace": workspace,
                "membership": membership,
                "members_count": members_count,
                "is_owner": membership.access_role == AccessRole.OWNER,
            },
        )


@method_decorator(login_required, name="dispatch")
class WorkspaceUpdateView(View):
    def get(self, request, workspace_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        if membership.access_role != AccessRole.OWNER:
            raise PermissionDenied("Chỉ Chủ workspace mới có quyền sửa thông tin workspace.")

        form = WorkspaceUpdateForm(
            initial={
                "name": workspace.name,
                "timezone": workspace.timezone,
            }
        )
        return render(
            request,
            "workspaces/workspace_edit.html",
            {
                "workspace": workspace,
                "form": form,
            },
        )

    def post(self, request, workspace_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        if membership.access_role != AccessRole.OWNER:
            raise PermissionDenied("Chỉ Chủ workspace mới có quyền sửa thông tin workspace.")

        form = WorkspaceUpdateForm(request.POST)
        if form.is_valid():
            update_workspace_info(
                user=request.user,
                workspace=workspace,
                name=form.cleaned_data["name"],
                timezone_str=form.cleaned_data["timezone"],
            )
            messages.success(request, f"Đã cập nhật thông tin workspace '{workspace.name}'.")
            return redirect("workspaces:detail", workspace_id=workspace.id)

        return render(
            request,
            "workspaces/workspace_edit.html",
            {
                "workspace": workspace,
                "form": form,
            },
        )


@method_decorator(login_required, name="dispatch")
class WorkspaceSwitchView(View):
    def post(self, request, workspace_id):
        workspace = switch_active_workspace(request, workspace_id)
        messages.info(request, f"Đã chuyển sang workspace '{workspace.name}'.")
        return redirect("workspaces:detail", workspace_id=workspace.id)

    def get(self, request, workspace_id):
        # Hỗ trợ cả chuyển qua liên kết GET tiện dụng cho thanh điều hướng
        workspace = switch_active_workspace(request, workspace_id)
        messages.info(request, f"Đã chuyển sang workspace '{workspace.name}'.")
        return redirect("workspaces:detail", workspace_id=workspace.id)



@method_decorator(login_required, name="dispatch")
class BrandProfileView(View):
    """
    Xem và chỉnh sửa hồ sơ thương hiệu của Workspace theo Spec B03 (mục 3.1, 4, 7 UI02, 10, 14):
    - GET: Hiển thị hồ sơ thương hiệu.
      - OWNER: Xem form đầy đủ và có thể chỉnh sửa; cảnh báo revision.
      - MEMBER: Chế độ chỉ đọc (read-only) để tham khảo, không có nút sửa.
      - Outsider: Nhận 404 Not Found (get_workspace_for_user).
    - POST: Cập nhật hồ sơ thương hiệu.
      - OWNER: Cập nhật thành công -> tăng revision, thông báo và redirect.
      - MEMBER: Nhận 403 Forbidden.
      - Outsider: Nhận 404 Not Found.
      - Xung đột đồng thời (ConcurrencyConflictError): Nhận 409 Conflict, giữ nguyên dữ liệu đã nhập.
    """

    def get(self, request, workspace_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        brand_profile = get_brand_profile(workspace)
        is_owner = membership.access_role == AccessRole.OWNER

        initial_data = {}
        if brand_profile:
            initial_data = {
                "name": brand_profile.name,
                "product_summary": brand_profile.product_summary,
                "target_audience": brand_profile.target_audience,
                "tone_of_voice": brand_profile.tone_of_voice,
                "avoid_guidelines": brand_profile.avoid_guidelines,
                "allowed_claims": brand_profile.allowed_claims,
                "source_urls": "\n".join(brand_profile.source_urls or []),
                "expected_revision": brand_profile.revision,
            }
        else:
            initial_data = {
                "name": workspace.name,
                "expected_revision": 0,
            }

        form = BrandProfileForm(initial=initial_data)

        return render(
            request,
            "workspaces/brand_profile.html",
            {
                "workspace": workspace,
                "membership": membership,
                "brand_profile": brand_profile,
                "form": form,
                "is_owner": is_owner,
            },
        )

    def post(self, request, workspace_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        is_owner = membership.access_role == AccessRole.OWNER

        if not is_owner:
            raise PermissionDenied("Chỉ Chủ workspace mới có quyền cập nhật hồ sơ thương hiệu.")

        form = BrandProfileForm(request.POST)
        if not form.is_valid():
            brand_profile = get_brand_profile(workspace)
            return render(
                request,
                "workspaces/brand_profile.html",
                {
                    "workspace": workspace,
                    "membership": membership,
                    "brand_profile": brand_profile,
                    "form": form,
                    "is_owner": is_owner,
                },
                status=400,
            )

        expected_revision = form.cleaned_data.get("expected_revision")
        try:
            brand_profile = save_brand_profile(
                user=request.user,
                workspace=workspace,
                name=form.cleaned_data["name"],
                product_summary=form.cleaned_data["product_summary"],
                target_audience=form.cleaned_data["target_audience"],
                tone_of_voice=form.cleaned_data.get("tone_of_voice", ""),
                avoid_guidelines=form.cleaned_data.get("avoid_guidelines", ""),
                allowed_claims=form.cleaned_data.get("allowed_claims", ""),
                source_urls=form.cleaned_data.get("source_urls", []),
                expected_revision=expected_revision,
            )
            messages.success(
                request,
                f"Đã lưu hồ sơ thương hiệu thành công (Phiên bản {brand_profile.revision}).",
            )
            return redirect("workspaces:brand_profile", workspace_id=workspace.id)
        except ConcurrencyConflictError as exc:
            brand_profile = get_brand_profile(workspace)
            form.add_error(None, str(exc))
            # Cập nhật lại expected_revision mới cho form
            if brand_profile:
                form.fields["expected_revision"].initial = brand_profile.revision
            return render(
                request,
                "workspaces/brand_profile.html",
                {
                    "workspace": workspace,
                    "membership": membership,
                    "brand_profile": brand_profile,
                    "form": form,
                    "is_owner": is_owner,
                    "conflict_error": str(exc),
                },
                status=409,
            )
        except ValidationError as exc:
            brand_profile = get_brand_profile(workspace)
            form.add_error(None, exc)
            return render(
                request,
                "workspaces/brand_profile.html",
                {
                    "workspace": workspace,
                    "membership": membership,
                    "brand_profile": brand_profile,
                    "form": form,
                    "is_owner": is_owner,
                },
                status=400,
            )


@method_decorator(login_required, name="dispatch")
class WorkspaceMembersView(View):
    def get(self, request, workspace_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        members = get_workspace_members(workspace)
        is_owner = membership.access_role == AccessRole.OWNER

        invitations = None
        if is_owner:
            invitations = get_workspace_invitations(workspace)

        return render(
            request,
            "workspaces/workspace_members.html",
            {
                "workspace": workspace,
                "membership": membership,
                "is_owner": is_owner,
                "members": members,
                "invitations": invitations,
            },
        )


@method_decorator(login_required, name="dispatch")
class WorkspaceInviteView(View):
    def get(self, request, workspace_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        if membership.access_role != AccessRole.OWNER:
            raise PermissionDenied("Chỉ Chủ workspace mới có quyền gửi lời mời.")

        form = WorkspaceInvitationForm()
        return render(
            request,
            "workspaces/workspace_invite.html",
            {
                "workspace": workspace,
                "membership": membership,
                "form": form,
            },
        )

    def post(self, request, workspace_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        if membership.access_role != AccessRole.OWNER:
            raise PermissionDenied("Chỉ Chủ workspace mới có quyền gửi lời mời.")

        form = WorkspaceInvitationForm(request.POST)
        if form.is_valid():
            try:
                invitation, raw_token = create_workspace_invitation(
                    user=request.user,
                    workspace=workspace,
                    email=form.cleaned_data["email"],
                    employment_type=form.cleaned_data["employment_type"],
                    ai_use_allowed=form.cleaned_data["ai_use_allowed"],
                    request=request,
                )
                accept_path = reverse("workspaces:invitation_accept", kwargs={"token": raw_token})
                accept_url = request.build_absolute_uri(accept_path)
                messages.success(request, f"Đã tạo lời mời cho {invitation.email} thành công!")
                return render(
                    request,
                    "workspaces/workspace_invite_success.html",
                    {
                        "workspace": workspace,
                        "invitation": invitation,
                        "accept_url": accept_url,
                    },
                )
            except ValidationError as err:
                if hasattr(err, "message_dict"):
                    for field, msgs in err.message_dict.items():
                        for msg in msgs:
                            form.add_error(field if field in form.fields else None, msg)
                else:
                    form.add_error(None, err.message)

        return render(
            request,
            "workspaces/workspace_invite.html",
            {
                "workspace": workspace,
                "membership": membership,
                "form": form,
            },
        )


@method_decorator(login_required, name="dispatch")
class WorkspaceInvitationRevokeView(View):
    def post(self, request, workspace_id, invitation_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        if membership.access_role != AccessRole.OWNER:
            raise PermissionDenied("Chỉ Chủ workspace mới có quyền thu hồi lời mời.")

        invitation = get_invitation_by_id_for_workspace(workspace, invitation_id)
        try:
            revoke_workspace_invitation(user=request.user, invitation=invitation)
            messages.success(request, f"Đã thu hồi lời mời gửi tới {invitation.email}.")
        except (ValidationError, PermissionDenied) as err:
            messages.error(request, str(err))

        return redirect("workspaces:members", workspace_id=workspace.id)


@method_decorator(login_required, name="dispatch")
class WorkspaceInvitationResendView(View):
    def post(self, request, workspace_id, invitation_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        if membership.access_role != AccessRole.OWNER:
            raise PermissionDenied("Chỉ Chủ workspace mới có quyền gửi lại lời mời.")

        invitation = get_invitation_by_id_for_workspace(workspace, invitation_id)
        try:
            raw_token = resend_workspace_invitation(
                user=request.user,
                invitation=invitation,
                request=request,
            )
            accept_path = reverse("workspaces:invitation_accept", kwargs={"token": raw_token})
            accept_url = request.build_absolute_uri(accept_path)
            messages.success(
                request,
                f"Đã làm mới và gửi lại lời mời tới {invitation.email}. Link mới: {accept_url}",
            )
        except (ValidationError, PermissionDenied) as err:
            messages.error(request, str(err))

        return redirect("workspaces:members", workspace_id=workspace.id)

@method_decorator(login_required, name="dispatch")
class MemberEditView(View):
    def get(self, request, workspace_id, membership_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        if membership.access_role != AccessRole.OWNER:
            raise PermissionDenied("Chỉ Chủ workspace mới có quyền sửa cài đặt thành viên.")

        target = get_membership_by_id_for_workspace(workspace, membership_id)
        if target.access_role == AccessRole.OWNER:
            messages.error(request, "Không thể sửa cài đặt của Chủ workspace.")
            return redirect("workspaces:members", workspace_id=workspace.id)

        form = MemberUpdateForm(
            initial={
                "employment_type": target.employment_type,
                "ai_use_allowed": target.ai_use_allowed,
            }
        )
        return render(
            request,
            "workspaces/member_edit.html",
            {
                "workspace": workspace,
                "target_member": target,
                "form": form,
            },
        )

    def post(self, request, workspace_id, membership_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        if membership.access_role != AccessRole.OWNER:
            raise PermissionDenied("Chỉ Chủ workspace mới có quyền sửa cài đặt thành viên.")

        target = get_membership_by_id_for_workspace(workspace, membership_id)
        if target.access_role == AccessRole.OWNER:
            messages.error(request, "Không thể sửa cài đặt của Chủ workspace.")
            return redirect("workspaces:members", workspace_id=workspace.id)

        form = MemberUpdateForm(request.POST)
        if form.is_valid():
            try:
                update_member_settings(
                    user=request.user,
                    workspace=workspace,
                    membership=target,
                    employment_type=form.cleaned_data["employment_type"],
                    ai_use_allowed=form.cleaned_data["ai_use_allowed"],
                )
                messages.success(request, f"Đã cập nhật cài đặt cho thành viên {target.user.username}.")
                return redirect("workspaces:members", workspace_id=workspace.id)
            except (ValidationError, PermissionDenied) as err:
                messages.error(request, str(err))

        return render(
            request,
            "workspaces/member_edit.html",
            {
                "workspace": workspace,
                "target_member": target,
                "form": form,
            },
        )


@method_decorator(login_required, name="dispatch")
class MemberDeactivateView(View):
    def post(self, request, workspace_id, membership_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        if membership.access_role != AccessRole.OWNER:
            raise PermissionDenied("Chỉ Chủ workspace mới có quyền vô hiệu hóa thành viên.")

        target = get_membership_by_id_for_workspace(workspace, membership_id)
        try:
            deactivate_membership(user=request.user, workspace=workspace, membership=target)
            messages.success(request, f"Đã vô hiệu hóa thành viên {target.user.username}.")
        except (ValidationError, PermissionDenied) as err:
            messages.error(request, str(err))

        return redirect("workspaces:members", workspace_id=workspace.id)


@method_decorator(login_required, name="dispatch")
class MemberReactivateView(View):
    def post(self, request, workspace_id, membership_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        if membership.access_role != AccessRole.OWNER:
            raise PermissionDenied("Chỉ Chủ workspace mới có quyền kích hoạt lại thành viên.")

        target = get_membership_by_id_for_workspace(workspace, membership_id)
        try:
            reactivate_membership(user=request.user, workspace=workspace, membership=target)
            messages.success(request, f"Đã kích hoạt lại thành viên {target.user.username}.")
        except (ValidationError, PermissionDenied) as err:
            messages.error(request, str(err))

        return redirect("workspaces:members", workspace_id=workspace.id)



class InvitationAcceptView(View):
    """
    Trang tiếp nhận và chấp nhận lời mời tham gia workspace.
    Không yêu cầu người dùng đã là thành viên.
    Xử lý:
    - Token không hợp lệ / không tìm thấy: Báo lỗi an toàn (404).
    - Chưa đăng nhập: Redirect về login kèm ?next= (chống open redirect).
    - Đã đăng nhập nhưng email chưa xác minh: Báo cần xác minh email.
    - Đã đăng nhập nhưng email không khớp: Báo tài khoản không khớp.
    - Lời mời đã nhận / thu hồi / hết hạn: Báo lỗi tương ứng.
    - POST: Thực hiện nhận lời mời trong transaction atomic có lock DB.
    """

    def get(self, request, token):
        invitation = get_invitation_by_token(token)
        if not invitation:
            raise Http404("Lời mời không tồn tại hoặc đường dẫn không hợp lệ.")

        # Kiểm tra trạng thái lời mời trước (nếu đã dùng/thu hồi/hết hạn thì báo ngay)
        if invitation.is_accepted or invitation.is_revoked or invitation.is_expired:
            return render(
                request,
                "workspaces/invitation_invalid.html",
                {
                    "invitation": invitation,
                },
            )

        if not request.user.is_authenticated:
            # Chống open redirect bằng cách kiểm tra path
            next_url = request.path
            if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                next_url = "/"
            return redirect(f"{reverse('accounts:login')}?next={next_url}")

        # Kiểm tra xác minh email identity
        try:
            identity = request.user.email_identity
        except (AttributeError, AccountEmailIdentity.DoesNotExist):
            identity = None

        if not identity or not identity.is_verified:
            return render(
                request,
                "workspaces/invitation_unverified.html",
                {
                    "invitation": invitation,
                    "user_email": request.user.email,
                },
            )

        # Kiểm tra email khớp
        user_email = normalize_email(identity.normalized_email)
        if user_email != invitation.email:
            return render(
                request,
                "workspaces/invitation_mismatch.html",
                {
                    "invitation": invitation,
                    "current_user_email": user_email,
                },
            )

        return render(
            request,
            "workspaces/invitation_accept.html",
            {
                "invitation": invitation,
                "token": token,
            },
        )

    def post(self, request, token):
        invitation = get_invitation_by_token(token)
        if not invitation:
            raise Http404("Lời mời không tồn tại hoặc đường dẫn không hợp lệ.")

        if not request.user.is_authenticated:
            raise PermissionDenied("Yêu cầu đăng nhập để chấp nhận lời mời.")

        if invitation.is_accepted or invitation.is_revoked or invitation.is_expired:
            return render(
                request,
                "workspaces/invitation_invalid.html",
                {
                    "invitation": invitation,
                },
            )

        try:
            workspace, membership = accept_workspace_invitation(
                user=request.user,
                raw_token=token,
            )
            # Tự động chọn workspace vừa tham gia vào session
            request.session["active_workspace_id"] = str(workspace.id)
            messages.success(request, f"Chào mừng bạn gia nhập workspace '{workspace.name}'!")
            return redirect("workspaces:detail", workspace_id=workspace.id)
        except ValidationError as err:
            err_msg = err.message if hasattr(err, "message") else str(err)
            messages.error(request, err_msg)
            return render(
                request,
                "workspaces/invitation_invalid.html",
                {
                    "invitation": invitation,
                    "error_message": err_msg,
                },
            )

