from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from apps.payments.views import pricing_view
from apps.workspaces.views import (
    InvitationAcceptView,
    MyTasksRedirectView,
    NotificationListView,
    NotificationReadAllView,
    NotificationReadView,
)

from .views import dashboard

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    path("pricing/", pricing_view, name="pricing"),
    path("dashboard/", dashboard, name="dashboard"),
    path("auth/", include("apps.accounts.urls")),
    path("workspaces/", include("apps.workspaces.urls")),
    path("invitations/accept/<str:token>/", InvitationAcceptView.as_view(), name="root_invitation_accept"),
    path("notifications/", NotificationListView.as_view(), name="notifications"),
    path("notifications/read-all/", NotificationReadAllView.as_view(), name="notification_read_all"),
    path("notifications/<uuid:notification_id>/read/", NotificationReadView.as_view(), name="notification_read"),
    path("tasks/mine/", MyTasksRedirectView.as_view(), name="tasks_mine"),
    path("payments/", include("apps.payments.urls")),
]

# Custom Error Handlers (Spec B10)
handler400 = "core.views.custom_bad_request_view"
handler403 = "core.views.custom_permission_denied_view"
handler404 = "core.views.custom_page_not_found_view"
handler500 = "core.views.custom_server_error_view"
from django.conf import settings
if settings.DEBUG or getattr(settings, "TEST_MODE", False):
    from core.views import test_auto_login
    urlpatterns.append(path("test-auto-login/<int:user_id>/", test_auto_login, name="test_auto_login"))
    from core.views import test_trigger_error
    urlpatterns.append(path("test-trigger-error/<int:code>/", test_trigger_error, name="test_trigger_error"))


