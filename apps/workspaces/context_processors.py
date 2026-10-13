from .selectors import get_user_workspaces
from .services import get_current_active_workspace


def workspace_context(request):
    """
    Cung cấp context workspace hiện tại và danh sách workspace cho mọi template.
    Luôn kiểm tra quyền thực tế qua service trên mỗi request.
    """
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {
            "current_workspace": None,
            "current_membership": None,
            "user_workspaces": [],
        }

    workspace, membership = get_current_active_workspace(request)
    workspaces = get_user_workspaces(request.user)

    return {
        "current_workspace": workspace,
        "current_membership": membership,
        "user_workspaces": workspaces,
    }
