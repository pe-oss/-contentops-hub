import uuid
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from .forms import WorkspaceCreateForm, WorkspaceUpdateForm
from .models import AccessRole, Membership, MembershipStatus
from .selectors import get_user_workspaces, get_workspace_for_user
from .services import create_workspace_with_owner, switch_active_workspace, update_workspace_info


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
