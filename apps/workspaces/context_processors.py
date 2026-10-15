from .selectors import get_unread_notifications_count, get_user_workspaces
from .services import get_current_active_workspace


def workspace_context(request):
    """
    Cung cấp context workspace hiện tại và danh sách workspace cho mọi template.
    Luôn kiểm tra quyền thực tế qua service trên mỗi request.
    Cung cấp unread_notifications_count tuân thủ quyền hiện tại (Spec mục 8, B09).
    """
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {
            "current_workspace": None,
            "current_membership": None,
            "user_workspaces": [],
            "unread_notifications_count": 0,
        }

    workspace, membership = get_current_active_workspace(request)
    workspaces = get_user_workspaces(request.user)
    unread_count = get_unread_notifications_count(request.user, workspace=workspace)

    return {
        "current_workspace": workspace,
        "current_membership": membership,
        "user_workspaces": workspaces,
        "unread_notifications_count": unread_count,
    }

