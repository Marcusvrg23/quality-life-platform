"""Root URL configuration for the Django foundation."""

from django.contrib import admin
from django.urls import path

from .auth_views import (
    EmailLoginView,
    SessionLogoutView,
    app_home,
    organization_home,
    select_organization,
)
from .views import foundation, health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", EmailLoginView.as_view(), name="login"),
    path("logout/", SessionLogoutView.as_view(), name="logout"),
    path("app/", app_home, name="app"),
    path("app/select-organization/", select_organization, name="select_organization"),
    path("app/organizations/<slug:slug>/", organization_home, name="organization_home"),
    path("", foundation, name="foundation"),
    path("health/", health, name="health"),
]
