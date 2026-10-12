from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from apps.payments.views import pricing_view

from .views import dashboard

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    path("pricing/", pricing_view, name="pricing"),
    path("dashboard/", dashboard, name="dashboard"),
    path("auth/", include("apps.accounts.urls")),
    path("payments/", include("apps.payments.urls")),
]