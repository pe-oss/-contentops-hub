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