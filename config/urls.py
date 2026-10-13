"""Root URL configuration for the Django foundation."""

from django.contrib import admin
from django.contrib.auth.views import (
    PasswordResetCompleteView,
    PasswordResetConfirmView,
)
from django.urls import include, path, reverse_lazy

from identity import views as identity_views

from .auth_views import (
    EmailLoginView,
    SessionLogoutView,
    ShellPasswordChangeView,
    app_home,
    organization_home,
    select_organization,
)
from .exercise_views import exercises
from .legal_views import privacy, privacy_revoke, privacy_settings, terms
from .lesson_views import lessons
from .views import foundation, health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", EmailLoginView.as_view(), name="login"),
    path("logout/", SessionLogoutView.as_view(), name="logout"),
    path("app/", app_home, name="app"),
    path("app/exercises/", exercises, name="exercises"),
    path("app/aulas/", lessons, name="lessons"),
    path("app/assessment/", include("assessments.urls")),
    path("app/report/", include("reports.urls")),
    path("app/equipe/", identity_views.team, name="team"),
    path(
        "app/equipe/membros/<int:membership_id>/status/",
        identity_views.team_member_status,
        name="team_member_status",
    ),
    path(
        "app/equipe/convites/",
        identity_views.team_invitations_create,
        name="team_invitations_create",
    ),
    path(
        "app/equipe/convites/<int:invitation_id>/revogar/",
        identity_views.team_invitation_revoke,
        name="team_invitation_revoke",
    ),
    path("app/privacidade/", privacy_settings, name="privacy_settings"),
    path("app/privacidade/revogar/", privacy_revoke, name="privacy_revoke"),
    path("privacidade/", privacy, name="privacy"),
    path("termos/", terms, name="terms"),
    path("app/senha/", ShellPasswordChangeView.as_view(), name="password_change"),
    path(
        "convite/<str:token>/",
        identity_views.accept_invitation,
        name="accept_invitation",
    ),
    path(
        "senha/redefinir/<uidb64>/<token>/",
        PasswordResetConfirmView.as_view(
            template_name="identity/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "senha/redefinida/",
        PasswordResetCompleteView.as_view(
            template_name="identity/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path("app/select-organization/", select_organization, name="select_organization"),
    path("app/organizations/<slug:slug>/", organization_home, name="organization_home"),
    path("", foundation, name="foundation"),
    path("health/", health, name="health"),
]
