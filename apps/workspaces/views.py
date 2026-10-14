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

from .forms import (
    ContentDraftForm, ContentItemForm, ContentSubmitForm,
    EditorVersionForm, PackageForm, RequestChangesForm, SubmitReviewForm,
    OwnerApproveItemForm, OwnerRequestChangesForm, WithdrawReviewForm,
    ReopenItemForm, CancelContentItemForm, BlockContentItemForm,
)
from .models import ContentItemState, PackageStatus, TaskRole, TaskStatus
from .selectors import (
    get_item_decisions,
    get_item_active_approval,
    get_item_approvals,
    get_item_for_workspace,
    get_item_tasks,
    get_item_versions,
    get_my_tasks_for_workspace,
    get_package_for_workspace,
    get_package_items,
    get_workspace_packages,
)
from .services import (
    add_content_item,
    owner_approve_item,
    owner_request_changes,
    withdraw_review,
    reopen_content_item,
    cancel_content_item,
    block_content_item,
    unblock_content_item,
    approve_plan,
    create_package,
    create_editor_version,
    format_brief_for_copy,
    request_changes_decision,
    save_draft_content,
    start_writing_task,
    submit_content_version,
    submit_for_owner_review,
    update_content_item,
    update_package,
)


def _render_item_detail(
    request,
    workspace,
    membership,
    package,
    item,
    context_extra=None,
    status=200,
):
    """Helper render màn hình chi tiết bài viết tác nghiệp (UI05)."""
    versions = get_item_versions(item)
    decisions = get_item_decisions(item)
    approvals = get_item_approvals(item)
    active_approval = get_item_active_approval(item)
    tasks = get_item_tasks(item)
    is_owner = (membership.access_role == AccessRole.OWNER)
    is_writer = (item.writer_membership_id == membership.id)
    is_editor = (item.editor_membership_id == membership.id)
    can_write = is_owner or is_writer
    can_edit = is_owner or is_editor
    brief_copy_text = format_brief_for_copy(item)

    default_urls_text = "\n".join(item.draft_reference_urls) if item.draft_reference_urls else ""
    ctx = {
        "workspace": workspace,
        "membership": membership,
        "package": package,
        "item": item,
        "versions": versions,
        "decisions": decisions,
        "approvals": approvals,
        "active_approval": active_approval,
        "tasks": tasks,
        "is_owner": is_owner,
        "is_writer": is_writer,
        "is_editor": is_editor,
        "can_write": can_write,
        "can_edit": can_edit,
        "brief_copy_text": brief_copy_text,
        "draft_form": ContentDraftForm(initial={
            "text": item.draft_text,
            "reference_urls_text": default_urls_text,
            "expected_row_version": item.row_version,
        }),
        "submit_form": ContentSubmitForm(initial={
            "text": item.draft_text,
            "reference_urls_text": default_urls_text,
            "expected_row_version": item.row_version,
            "idempotency_key": f"{item.id}_{item.row_version}",
        }),
        "editor_form": EditorVersionForm(initial={
            "text": item.latest_version.text if item.latest_version else item.draft_text,
            "expected_row_version": item.row_version,
        }),
        "request_changes_form": RequestChangesForm(initial={
            "expected_row_version": item.row_version,
        }),
        "submit_review_form": SubmitReviewForm(initial={
            "expected_row_version": item.row_version,
            "idempotency_key": f"review_{item.id}_{item.row_version}",
        }),
        "owner_approve_form": OwnerApproveItemForm(initial={
            "expected_version_id": item.latest_version_id,
            "expected_row_version": item.row_version,
            "idempotency_key": f"approve_{item.id}_{item.latest_version_id}",
        }),
        "owner_request_changes_form": OwnerRequestChangesForm(initial={
            "return_stage": "WRITING",
            "expected_row_version": item.row_version,
        }),
        "withdraw_review_form": WithdrawReviewForm(initial={
            "expected_row_version": item.row_version,
        }),
        "reopen_form": ReopenItemForm(initial={
            "expected_row_version": item.row_version,
        }),
        "cancel_form": CancelContentItemForm(initial={
            "expected_row_version": item.row_version,
        }),
        "block_form": BlockContentItemForm(initial={
            "expected_row_version": item.row_version,
        }),
    }
    if context_extra:
        ctx.update(context_extra)
    return render(request, "workspaces/item_detail.html", ctx, status=status)


@method_decorator(login_required, name="dispatch")
class ContentItemBlockView(View):
    """Báo bài viết bị chặn (Spec F07, 6.1, AC12, B06)."""
    def post(self, request, workspace_id, package_id, item_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        item = get_item_for_workspace(workspace, item_id)

        form = BlockContentItemForm(request.POST)
        if not form.is_valid():
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"block_form": form},
                status=400,
            )

        reason = form.cleaned_data.get("reason")
        exp_row = form.cleaned_data.get("expected_row_version")

        try:
            block_content_item(
                user=request.user,
                item=item,
                reason=reason,
                expected_row_version=exp_row,
            )
            messages.warning(request, "Đã đặt cờ chặn bài viết thành công!")
            return redirect("workspaces:item_detail", workspace_id=workspace.id, package_id=package.id, item_id=item.id)
        except ConcurrencyConflictError as exc:
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"block_form": form, "conflict_error": str(exc)},
                status=409,
            )
        except ValidationError as exc:
            err_msg = exc.message if hasattr(exc, "message") else str(exc)
            form.add_error(None, err_msg)
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"block_form": form},
                status=400,
            )


@method_decorator(login_required, name="dispatch")
class ContentItemUnblockView(View):
    """Giải quyết và gỡ chặn bài viết (Spec F07, 6.1, AC12, B06)."""
    def post(self, request, workspace_id, package_id, item_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        item = get_item_for_workspace(workspace, item_id)

        form = BlockContentItemForm(request.POST)
        resolution_note = form.cleaned_data.get("reason") if form.is_valid() else request.POST.get("reason", "")
        exp_row = request.POST.get("expected_row_version")

        try:
            unblock_content_item(
                user=request.user,
                item=item,
                resolution_note=resolution_note,
                expected_row_version=exp_row,
            )
            messages.success(request, "Đã gỡ chặn bài viết thành công!")
            return redirect("workspaces:item_detail", workspace_id=workspace.id, package_id=package.id, item_id=item.id)
        except ConcurrencyConflictError as exc:
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"block_form": form, "conflict_error": str(exc)},
                status=409,
            )
        except ValidationError as exc:
            err_msg = exc.message if hasattr(exc, "message") else str(exc)
            form.add_error(None, err_msg)
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"block_form": form},
                status=400,
            )

@method_decorator(login_required, name="dispatch")
class ContentItemOwnerApproveView(View):
    """Chủ workspace phê duyệt bài viết (F05, 6.1, AC07, B06)."""
    def post(self, request, workspace_id, package_id, item_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        item = get_item_for_workspace(workspace, item_id)

        form = OwnerApproveItemForm(request.POST)
        if not form.is_valid():
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"owner_approve_form": form},
                status=400,
            )

        expected_ver = form.cleaned_data.get("expected_version_id")
        exp_row = form.cleaned_data.get("expected_row_version")
        idemp = form.cleaned_data.get("idempotency_key")

        try:
            owner_approve_item(
                user=request.user,
                item=item,
                expected_version_id=expected_ver,
                expected_row_version=exp_row,
                idempotency_key=idemp,
            )
            messages.success(request, "Đã phê duyệt bài viết thành công!")
            return redirect("workspaces:item_detail", workspace_id=workspace.id, package_id=package.id, item_id=item.id)
        except ConcurrencyConflictError as exc:
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"owner_approve_form": form, "conflict_error": str(exc)},
                status=409,
            )
        except ValidationError as exc:
            err_msg = exc.message if hasattr(exc, "message") else str(exc)
            form.add_error(None, err_msg)
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"owner_approve_form": form},
                status=400,
            )


@method_decorator(login_required, name="dispatch")
class ContentItemOwnerRequestChangesView(View):
    """Chủ workspace yêu cầu sửa và chỉ định bước trả về (F05, 6.1, B06)."""
    def post(self, request, workspace_id, package_id, item_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        item = get_item_for_workspace(workspace, item_id)

        form = OwnerRequestChangesForm(request.POST)
        if not form.is_valid():
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"owner_request_changes_form": form},
                status=400,
            )

        stage = form.cleaned_data.get("return_stage")
        reason = form.cleaned_data.get("reason")
        exp_row = form.cleaned_data.get("expected_row_version")

        try:
            owner_request_changes(
                user=request.user,
                item=item,
                return_stage=stage,
                reason=reason,
                expected_row_version=exp_row,
            )
            messages.success(request, f"Đã trả bài về bước {stage} để sửa lại!")
            return redirect("workspaces:item_detail", workspace_id=workspace.id, package_id=package.id, item_id=item.id)
        except ConcurrencyConflictError as exc:
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"owner_request_changes_form": form, "conflict_error": str(exc)},
                status=409,
            )
        except ValidationError as exc:
            err_msg = exc.message if hasattr(exc, "message") else str(exc)
            form.add_error(None, err_msg)
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"owner_request_changes_form": form},
                status=400,
            )


@method_decorator(login_required, name="dispatch")
class ContentItemWithdrawReviewView(View):
    """Biên tập viên hoặc Chủ rút gửi duyệt có lý do (F05, 6.1, B06)."""
    def post(self, request, workspace_id, package_id, item_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        item = get_item_for_workspace(workspace, item_id)

        form = WithdrawReviewForm(request.POST)
        if not form.is_valid():
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"withdraw_review_form": form},
                status=400,
            )

        reason = form.cleaned_data.get("reason")
        exp_row = form.cleaned_data.get("expected_row_version")

        try:
            withdraw_review(
                user=request.user,
                item=item,
                reason=reason,
                expected_row_version=exp_row,
            )
            messages.success(request, "Đã rút gửi duyệt thành công!")
            return redirect("workspaces:item_detail", workspace_id=workspace.id, package_id=package.id, item_id=item.id)
        except ConcurrencyConflictError as exc:
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"withdraw_review_form": form, "conflict_error": str(exc)},
                status=409,
            )
        except ValidationError as exc:
            err_msg = exc.message if hasattr(exc, "message") else str(exc)
            form.add_error(None, err_msg)
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"withdraw_review_form": form},
                status=400,
            )


@method_decorator(login_required, name="dispatch")
class ContentItemReopenView(View):
    """Chủ workspace mở lại bài viết (F05, F06, 6.1, AC09, B06)."""
    def post(self, request, workspace_id, package_id, item_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        item = get_item_for_workspace(workspace, item_id)

        form = ReopenItemForm(request.POST)
        if not form.is_valid():
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"reopen_form": form},
                status=400,
            )

        reason = form.cleaned_data.get("reason")
        exp_row = form.cleaned_data.get("expected_row_version")

        try:
            reopen_content_item(
                user=request.user,
                item=item,
                reason=reason,
                expected_row_version=exp_row,
            )
            messages.success(request, "Đã mở lại bài viết thành công!")
            return redirect("workspaces:item_detail", workspace_id=workspace.id, package_id=package.id, item_id=item.id)
        except ConcurrencyConflictError as exc:
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"reopen_form": form, "conflict_error": str(exc)},
                status=409,
            )
        except ValidationError as exc:
            err_msg = exc.message if hasattr(exc, "message") else str(exc)
            form.add_error(None, err_msg)
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"reopen_form": form},
                status=400,
            )


@method_decorator(login_required, name="dispatch")
class ContentItemCancelView(View):
    """Chủ workspace hủy bài viết có lý do (6.1, B06)."""
    def post(self, request, workspace_id, package_id, item_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        item = get_item_for_workspace(workspace, item_id)

        form = CancelContentItemForm(request.POST)
        if not form.is_valid():
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"cancel_form": form},
                status=400,
            )

        reason = form.cleaned_data.get("reason")
        exp_row = form.cleaned_data.get("expected_row_version")

        try:
            cancel_content_item(
                user=request.user,
                item=item,
                reason=reason,
                expected_row_version=exp_row,
            )
            messages.success(request, "Đã hủy bài viết thành công!")
            return redirect("workspaces:item_detail", workspace_id=workspace.id, package_id=package.id, item_id=item.id)
        except ConcurrencyConflictError as exc:
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"cancel_form": form, "conflict_error": str(exc)},
                status=409,
            )
        except ValidationError as exc:
            err_msg = exc.message if hasattr(exc, "message") else str(exc)
            form.add_error(None, err_msg)
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"cancel_form": form},
                status=400,
            )

@method_decorator(login_required, name="dispatch")
class ContentItemDetailView(View):
    """Màn hình chi tiết bài viết & tác nghiệp nội dung (Spec UI05, F03, F04, B05)."""
    def get(self, request, workspace_id, package_id, item_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        item = get_item_for_workspace(workspace, item_id)
        return _render_item_detail(request, workspace, membership, package, item)


@method_decorator(login_required, name="dispatch")
class ContentItemStartWritingView(View):
    """Bắt đầu nhiệm vụ viết bài (TODO -> WRITING)."""
    def post(self, request, workspace_id, package_id, item_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        item = get_item_for_workspace(workspace, item_id)

        try:
            start_writing_task(user=request.user, item=item)
            messages.success(request, "Đã bắt đầu thực hiện bài viết!")
        except (ValidationError, PermissionDenied) as exc:
            err_msg = exc.message if hasattr(exc, "message") else str(exc)
            messages.error(request, f"Không thể bắt đầu: {err_msg}")

        return redirect("workspaces:item_detail", workspace_id=workspace.id, package_id=package.id, item_id=item.id)


@method_decorator(login_required, name="dispatch")
class ContentItemSaveDraftView(View):
    """Lưu bản nháp bài viết (F03, AC12)."""
    def post(self, request, workspace_id, package_id, item_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        item = get_item_for_workspace(workspace, item_id)

        form = ContentDraftForm(request.POST)
        if not form.is_valid():
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"draft_form": form},
                status=400,
            )

        raw_urls = form.cleaned_data.get("reference_urls_text", "")
        urls_list = [u.strip() for u in raw_urls.splitlines() if u.strip()]
        exp_row = form.cleaned_data.get("expected_row_version")

        try:
            save_draft_content(
                user=request.user,
                item=item,
                text=form.cleaned_data.get("text", ""),
                reference_urls=urls_list,
                expected_row_version=exp_row,
            )
            messages.success(request, "Đã lưu bản nháp thành công!")
            return redirect("workspaces:item_detail", workspace_id=workspace.id, package_id=package.id, item_id=item.id)
        except ConcurrencyConflictError as exc:
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"draft_form": form, "conflict_error": str(exc)},
                status=409,
            )
        except ValidationError as exc:
            err_msg = exc.message if hasattr(exc, "message") else str(exc)
            form.add_error(None, err_msg)
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"draft_form": form},
                status=400,
            )


@method_decorator(login_required, name="dispatch")
class ContentItemSubmitVersionView(View):
    """Người viết nộp bài hoàn thành cho Biên tập (F03, AC06, AC08, AC10, AC12)."""
    def post(self, request, workspace_id, package_id, item_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        item = get_item_for_workspace(workspace, item_id)

        form = ContentSubmitForm(request.POST)
        if not form.is_valid():
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"submit_form": form},
                status=400,
            )

        raw_urls = form.cleaned_data.get("reference_urls_text", "")
        urls_list = [u.strip() for u in raw_urls.splitlines() if u.strip()]
        exp_row = form.cleaned_data.get("expected_row_version")
        idemp = form.cleaned_data.get("idempotency_key", "")

        try:
            submit_content_version(
                user=request.user,
                item=item,
                text=form.cleaned_data.get("text", ""),
                reference_urls=urls_list,
                source=form.cleaned_data.get("source"),
                expected_row_version=exp_row,
                idempotency_key=idemp,
            )
            messages.success(request, "Đã nộp bài viết cho Biên tập thành công!")
            return redirect("workspaces:item_detail", workspace_id=workspace.id, package_id=package.id, item_id=item.id)
        except ConcurrencyConflictError as exc:
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"submit_form": form, "conflict_error": str(exc)},
                status=409,
            )
        except ValidationError as exc:
            err_msg = exc.message if hasattr(exc, "message") else str(exc)
            form.add_error(None, err_msg)
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"submit_form": form},
                status=400,
            )


@method_decorator(login_required, name="dispatch")
class ContentItemEditorVersionView(View):
    """Biên tập viên tạo phiên bản chỉnh sửa mới (F04, AC06)."""
    def post(self, request, workspace_id, package_id, item_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        item = get_item_for_workspace(workspace, item_id)

        form = EditorVersionForm(request.POST)
        if not form.is_valid():
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"editor_form": form},
                status=400,
            )

        raw_urls = form.cleaned_data.get("reference_urls_text", "")
        urls_list = [u.strip() for u in raw_urls.splitlines() if u.strip()]
        exp_row = form.cleaned_data.get("expected_row_version")

        try:
            create_editor_version(
                user=request.user,
                item=item,
                text=form.cleaned_data.get("text", ""),
                reference_urls=urls_list,
                expected_row_version=exp_row,
            )
            messages.success(request, "Đã tạo phiên bản chỉnh sửa mới thành công!")
            return redirect("workspaces:item_detail", workspace_id=workspace.id, package_id=package.id, item_id=item.id)
        except ConcurrencyConflictError as exc:
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"editor_form": form, "conflict_error": str(exc)},
                status=409,
            )
        except ValidationError as exc:
            err_msg = exc.message if hasattr(exc, "message") else str(exc)
            form.add_error(None, err_msg)
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"editor_form": form},
                status=400,
            )


@method_decorator(login_required, name="dispatch")
class ContentItemRequestChangesView(View):
    """Biên tập viên yêu cầu người viết sửa lại (F04, AC06)."""
    def post(self, request, workspace_id, package_id, item_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        item = get_item_for_workspace(workspace, item_id)

        form = RequestChangesForm(request.POST)
        if not form.is_valid():
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"request_changes_form": form},
                status=400,
            )

        exp_row = form.cleaned_data.get("expected_row_version")
        reason = form.cleaned_data.get("reason", "")

        try:
            request_changes_decision(
                user=request.user,
                item=item,
                reason=reason,
                expected_row_version=exp_row,
            )
            messages.success(request, "Đã yêu cầu người viết sửa lại bài!")
            return redirect("workspaces:item_detail", workspace_id=workspace.id, package_id=package.id, item_id=item.id)
        except ConcurrencyConflictError as exc:
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"request_changes_form": form, "conflict_error": str(exc)},
                status=409,
            )
        except ValidationError as exc:
            err_msg = exc.message if hasattr(exc, "message") else str(exc)
            form.add_error(None, err_msg)
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"request_changes_form": form},
                status=400,
            )


@method_decorator(login_required, name="dispatch")
class ContentItemSubmitReviewView(View):
    """Biên tập viên đánh dấu hoàn tất checklist và nộp Chủ duyệt (F04, 6.1)."""
    def post(self, request, workspace_id, package_id, item_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        item = get_item_for_workspace(workspace, item_id)

        form = SubmitReviewForm(request.POST)
        if not form.is_valid():
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"submit_review_form": form},
                status=400,
            )

        exp_row = form.cleaned_data.get("expected_row_version")
        idemp = form.cleaned_data.get("idempotency_key", "")
        checklist = {
            "brief_compliance": form.cleaned_data.get("brief_compliance"),
            "factual_accuracy": form.cleaned_data.get("factual_accuracy"),
            "voice_tone": form.cleaned_data.get("voice_tone"),
            "cta_verified": form.cleaned_data.get("cta_verified"),
        }

        try:
            submit_for_owner_review(
                user=request.user,
                item=item,
                checklist=checklist,
                expected_row_version=exp_row,
                idempotency_key=idemp,
            )
            messages.success(request, "Đã nộp bài cho Chủ workspace phê duyệt thành công!")
            return redirect("workspaces:item_detail", workspace_id=workspace.id, package_id=package.id, item_id=item.id)
        except ConcurrencyConflictError as exc:
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"submit_review_form": form, "conflict_error": str(exc)},
                status=409,
            )
        except ValidationError as exc:
            err_msg = exc.message if hasattr(exc, "message") else str(exc)
            form.add_error(None, err_msg)
            return _render_item_detail(
                request, workspace, membership, package, item,
                context_extra={"submit_review_form": form},
                status=400,
            )


@method_decorator(login_required, name="dispatch")
class MyTasksView(View):
    """Màn hình Việc của tôi (UI06, Spec F03, B05)."""
    def get(self, request, workspace_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        status_filter = request.GET.get("status", "").strip()
        tasks = get_my_tasks_for_workspace(workspace, request.user, status_filter=status_filter or None)

        return render(
            request,
            "workspaces/my_tasks.html",
            {
                "workspace": workspace,
                "membership": membership,
                "tasks": tasks,
                "status_filter": status_filter,
            },
        )
@method_decorator(login_required, name="dispatch")
class PackageListView(View):
    def get(self, request, workspace_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        packages = get_workspace_packages(workspace)
        is_owner = membership.access_role == AccessRole.OWNER

        return render(
            request,
            "workspaces/package_list.html",
            {
                "workspace": workspace,
                "membership": membership,
                "is_owner": is_owner,
                "packages": packages,
            },
        )


@method_decorator(login_required, name="dispatch")
class PackageCreateView(View):
    def get(self, request, workspace_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        if membership.access_role != AccessRole.OWNER:
            raise PermissionDenied("Chỉ Chủ workspace mới có quyền tạo Gói nội dung.")

        form = PackageForm(workspace=workspace, initial={"coordinator_membership": membership})
        return render(
            request,
            "workspaces/package_create.html",
            {
                "workspace": workspace,
                "membership": membership,
                "form": form,
            },
        )

    def post(self, request, workspace_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        if membership.access_role != AccessRole.OWNER:
            raise PermissionDenied("Chỉ Chủ workspace mới có quyền tạo Gói nội dung.")

        form = PackageForm(request.POST, workspace=workspace)
        if not form.is_valid():
            return render(
                request,
                "workspaces/package_create.html",
                {
                    "workspace": workspace,
                    "membership": membership,
                    "form": form,
                },
                status=400,
            )

        try:
            package = create_package(
                user=request.user,
                workspace=workspace,
                name=form.cleaned_data["name"],
                objective=form.cleaned_data["objective"],
                coordinator_membership=form.cleaned_data["coordinator_membership"],
                start_date=form.cleaned_data["start_date"],
                end_date=form.cleaned_data["end_date"],
                channel=form.cleaned_data.get("channel") or "FACEBOOK",
            )
            messages.success(request, f"Đã tạo gói nội dung '{package.name}' thành công.")
            return redirect("workspaces:package_detail", workspace_id=workspace.id, package_id=package.id)
        except ValidationError as exc:
            form.add_error(None, exc)
            return render(
                request,
                "workspaces/package_create.html",
                {
                    "workspace": workspace,
                    "membership": membership,
                    "form": form,
                },
                status=400,
            )


@method_decorator(login_required, name="dispatch")
class PackageDetailView(View):
    def get(self, request, workspace_id, package_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        items = get_package_items(package)
        is_owner = membership.access_role == AccessRole.OWNER
        is_coordinator = package.coordinator_membership_id == membership.id

        can_edit_items = is_owner or (is_coordinator and package.is_draft)

        return render(
            request,
            "workspaces/package_detail.html",
            {
                "workspace": workspace,
                "membership": membership,
                "package": package,
                "items": items,
                "is_owner": is_owner,
                "is_coordinator": is_coordinator,
                "can_edit_items": can_edit_items,
            },
        )


@method_decorator(login_required, name="dispatch")
class PackageUpdateView(View):
    def get(self, request, workspace_id, package_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        if membership.access_role != AccessRole.OWNER:
            raise PermissionDenied("Chỉ Chủ workspace mới có quyền sửa Gói nội dung.")

        package = get_package_for_workspace(workspace, package_id)
        form = PackageForm(
            workspace=workspace,
            initial={
                "name": package.name,
                "objective": package.objective,
                "coordinator_membership": package.coordinator_membership,
                "start_date": package.start_date,
                "end_date": package.end_date,
                "channel": package.channel,
                "expected_row_version": package.row_version,
            },
        )
        return render(
            request,
            "workspaces/package_edit.html",
            {
                "workspace": workspace,
                "membership": membership,
                "package": package,
                "form": form,
            },
        )

    def post(self, request, workspace_id, package_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        if membership.access_role != AccessRole.OWNER:
            raise PermissionDenied("Chỉ Chủ workspace mới có quyền sửa Gói nội dung.")

        package = get_package_for_workspace(workspace, package_id)
        form = PackageForm(request.POST, workspace=workspace)
        if not form.is_valid():
            return render(
                request,
                "workspaces/package_edit.html",
                {
                    "workspace": workspace,
                    "membership": membership,
                    "package": package,
                    "form": form,
                },
                status=400,
            )

        expected_row_version = form.cleaned_data.get("expected_row_version")
        try:
            update_package(
                user=request.user,
                package=package,
                name=form.cleaned_data["name"],
                objective=form.cleaned_data["objective"],
                coordinator_membership=form.cleaned_data["coordinator_membership"],
                start_date=form.cleaned_data["start_date"],
                end_date=form.cleaned_data["end_date"],
                expected_row_version=expected_row_version,
            )
            messages.success(request, f"Đã cập nhật gói '{package.name}' thành công.")
            return redirect("workspaces:package_detail", workspace_id=workspace.id, package_id=package.id)
        except ConcurrencyConflictError as exc:
            form.add_error(None, str(exc))
            return render(
                request,
                "workspaces/package_edit.html",
                {
                    "workspace": workspace,
                    "membership": membership,
                    "package": package,
                    "form": form,
                    "conflict_error": str(exc),
                },
                status=409,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
            return render(
                request,
                "workspaces/package_edit.html",
                {
                    "workspace": workspace,
                    "membership": membership,
                    "package": package,
                    "form": form,
                },
                status=400,
            )
@method_decorator(login_required, name="dispatch")
class ContentItemCreateView(View):
    def get(self, request, workspace_id, package_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        is_owner = membership.access_role == AccessRole.OWNER
        is_coordinator = package.coordinator_membership_id == membership.id

        if not is_owner and not is_coordinator:
            raise PermissionDenied("Chỉ Chủ workspace hoặc Người điều phối mới có quyền thêm bài viết.")

        form = ContentItemForm(
            workspace=workspace,
            package=package,
            initial={
                "writer_membership": membership,
                "editor_membership": membership,
                "publisher_membership": membership,
            },
        )
        return render(
            request,
            "workspaces/item_create.html",
            {
                "workspace": workspace,
                "membership": membership,
                "package": package,
                "form": form,
            },
        )

    def post(self, request, workspace_id, package_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        is_owner = membership.access_role == AccessRole.OWNER
        is_coordinator = package.coordinator_membership_id == membership.id

        if not is_owner and not is_coordinator:
            raise PermissionDenied("Chỉ Chủ workspace hoặc Người điều phối mới có quyền thêm bài viết.")

        form = ContentItemForm(request.POST, workspace=workspace, package=package)
        if not form.is_valid():
            return render(
                request,
                "workspaces/item_create.html",
                {
                    "workspace": workspace,
                    "membership": membership,
                    "package": package,
                    "form": form,
                },
                status=400,
            )

        try:
            item = add_content_item(
                user=request.user,
                package=package,
                title=form.cleaned_data["title"],
                brief=form.cleaned_data["brief"],
                cta=form.cleaned_data.get("cta", ""),
                writing_deadline=form.cleaned_data["writing_deadline"],
                editing_deadline=form.cleaned_data["editing_deadline"],
                review_deadline=form.cleaned_data["review_deadline"],
                planned_publish_at=form.cleaned_data["planned_publish_at"],
                writer_membership=form.cleaned_data["writer_membership"],
                editor_membership=form.cleaned_data["editor_membership"],
                publisher_membership=form.cleaned_data["publisher_membership"],
            )
            messages.success(request, f"Đã thêm bài viết '{item.title}' vào kế hoạch.")
            return redirect("workspaces:package_detail", workspace_id=workspace.id, package_id=package.id)
        except ValidationError as exc:
            form.add_error(None, exc)
            return render(
                request,
                "workspaces/item_create.html",
                {
                    "workspace": workspace,
                    "membership": membership,
                    "package": package,
                    "form": form,
                },
                status=400,
            )
@method_decorator(login_required, name="dispatch")
class ContentItemUpdateView(View):
    def get(self, request, workspace_id, package_id, item_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        item = get_item_for_workspace(workspace, item_id)
        is_owner = membership.access_role == AccessRole.OWNER
        is_coordinator = package.coordinator_membership_id == membership.id

        if package.status == PackageStatus.ACTIVE:
            if not is_owner:
                raise PermissionDenied("Khi kế hoạch đã duyệt, chỉ Chủ workspace mới có quyền sửa bài viết.")
        else:
            if not is_owner and not is_coordinator:
                raise PermissionDenied("Chỉ Chủ workspace hoặc Người điều phối mới có quyền sửa bài viết.")

        form = ContentItemForm(
            workspace=workspace,
            package=package,
            initial={
                "title": item.title,
                "brief": item.brief,
                "cta": item.cta,
                "writing_deadline": item.writing_deadline,
                "editing_deadline": item.editing_deadline,
                "review_deadline": item.review_deadline,
                "planned_publish_at": item.planned_publish_at,
                "writer_membership": item.writer_membership,
                "editor_membership": item.editor_membership,
                "publisher_membership": item.publisher_membership,
                "expected_row_version": item.row_version,
            },
        )
        return render(
            request,
            "workspaces/item_edit.html",
            {
                "workspace": workspace,
                "membership": membership,
                "package": package,
                "item": item,
                "form": form,
            },
        )

    def post(self, request, workspace_id, package_id, item_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        package = get_package_for_workspace(workspace, package_id)
        item = get_item_for_workspace(workspace, item_id)
        is_owner = membership.access_role == AccessRole.OWNER
        is_coordinator = package.coordinator_membership_id == membership.id

        if package.status == PackageStatus.ACTIVE:
            if not is_owner:
                raise PermissionDenied("Khi kế hoạch đã duyệt, chỉ Chủ workspace mới có quyền sửa bài viết.")
        else:
            if not is_owner and not is_coordinator:
                raise PermissionDenied("Chỉ Chủ workspace hoặc Người điều phối mới có quyền sửa bài viết.")

        form = ContentItemForm(request.POST, workspace=workspace, package=package)
        if not form.is_valid():
            return render(
                request,
                "workspaces/item_edit.html",
                {
                    "workspace": workspace,
                    "membership": membership,
                    "package": package,
                    "item": item,
                    "form": form,
                },
                status=400,
            )

        expected_row_version = form.cleaned_data.get("expected_row_version")
        try:
            update_content_item(
                user=request.user,
                item=item,
                title=form.cleaned_data["title"],
                brief=form.cleaned_data["brief"],
                cta=form.cleaned_data.get("cta", ""),
                writing_deadline=form.cleaned_data["writing_deadline"],
                editing_deadline=form.cleaned_data["editing_deadline"],
                review_deadline=form.cleaned_data["review_deadline"],
                planned_publish_at=form.cleaned_data["planned_publish_at"],
                writer_membership=form.cleaned_data["writer_membership"],
                editor_membership=form.cleaned_data["editor_membership"],
                publisher_membership=form.cleaned_data["publisher_membership"],
                expected_row_version=expected_row_version,
            )
            messages.success(request, f"Đã cập nhật bài viết '{item.title}'.")
            return redirect("workspaces:package_detail", workspace_id=workspace.id, package_id=package.id)
        except ConcurrencyConflictError as exc:
            form.add_error(None, str(exc))
            return render(
                request,
                "workspaces/item_edit.html",
                {
                    "workspace": workspace,
                    "membership": membership,
                    "package": package,
                    "item": item,
                    "form": form,
                    "conflict_error": str(exc),
                },
                status=409,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
            return render(
                request,
                "workspaces/item_edit.html",
                {
                    "workspace": workspace,
                    "membership": membership,
                    "package": package,
                    "item": item,
                    "form": form,
                },
                status=400,
            )
@method_decorator(login_required, name="dispatch")
class PackageApprovePlanView(View):
    def post(self, request, workspace_id, package_id):
        workspace, membership = get_workspace_for_user(request.user, workspace_id)
        if membership.access_role != AccessRole.OWNER:
            raise PermissionDenied("Chỉ Chủ workspace mới có quyền duyệt kế hoạch.")

        package = get_package_for_workspace(workspace, package_id)
        idempotency_key = request.POST.get("idempotency_key", "").strip()

        try:
            approve_plan(
                user=request.user,
                package=package,
                idempotency_key=idempotency_key,
            )
            messages.success(request, f"Đã phê duyệt kế hoạch cho gói '{package.name}'. Nhiệm vụ đã được khởi tạo!")
        except (ValidationError, PermissionDenied) as exc:
            err_msg = exc.message if hasattr(exc, "message") else str(exc)
            messages.error(request, f"Không thể duyệt kế hoạch: {err_msg}")

        return redirect("workspaces:package_detail", workspace_id=workspace.id, package_id=package.id)




