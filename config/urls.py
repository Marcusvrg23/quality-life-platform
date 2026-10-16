"""Root URL configuration for the Django foundation."""

from django.contrib import admin
from django.contrib.auth.views import (
    PasswordResetCompleteView,
    PasswordResetConfirmView,
)
from django.urls import include, path, reverse_lazy

from identity import google as google_views
from identity import operator_views
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
from .pwa_views import install_app, manifest, offline, service_worker
from .views import health, home

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", EmailLoginView.as_view(), name="login"),
    path("logout/", SessionLogoutView.as_view(), name="logout"),
    # Google sign-in: only these two allauth routes exist (spec 14).
    path("accounts/google/login/", google_views.google_login, name="google_login"),
    path(
        "accounts/google/login/callback/",
        google_views.google_callback,
        name="google_callback",
    ),
    path("app/", app_home, name="app"),
    path("app/exercises/", exercises, name="exercises"),
    path("app/aulas/", lessons, name="lessons"),
    path("app/instalar/", install_app, name="install_app"),
    path("app/assessment/", include("assessments.urls")),
    path("app/report/", include("reports.urls")),
    path("app/", include("wellbeing.urls")),
    path("app/equipe/", identity_views.team, name="team"),
    path(
        "app/equipe/membros/<int:membership_id>/status/",
        identity_views.team_member_status,
        name="team_member_status",
    ),
    path("app/equipe/emails/", identity_views.team_emails_add, name="team_emails_add"),
    path(
        "app/equipe/emails/<int:entry_id>/remover/",
        identity_views.team_email_remove,
        name="team_email_remove",
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
    path("app/painel/", operator_views.operator_panel, name="operator_panel"),
    path(
        "app/painel/empresas/",
        operator_views.operator_organization_create,
        name="operator_organization_create",
    ),
    path(
        "app/painel/empresas/<int:organization_id>/status/",
        operator_views.operator_organization_status,
        name="operator_organization_status",
    ),
    path(
        "app/painel/empresas/<int:organization_id>/emails/",
        operator_views.operator_organization_emails,
        name="operator_organization_emails",
    ),
    path(
        "app/painel/empresas/<int:organization_id>/emails/liberar/",
        operator_views.operator_email_add,
        name="operator_email_add",
    ),
    path(
        "app/painel/empresas/<int:organization_id>/emails/<int:entry_id>/remover/",
        operator_views.operator_email_remove,
        name="operator_email_remove",
    ),
    path(
        "app/painel/empresas/<int:organization_id>/emails/<int:entry_id>/papel/",
        operator_views.operator_email_role,
        name="operator_email_role",
    ),
    path(
        "app/painel/empresas/<int:organization_id>/convite-gestor/",
        operator_views.operator_manager_invitation,
        name="operator_manager_invitation",
    ),
    path(
        "app/painel/empresas/<int:organization_id>/entrar/",
        operator_views.operator_enter,
        name="operator_enter",
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
    path("", home, name="home"),
    path("health/", health, name="health"),
    path("manifest.webmanifest", manifest, name="manifest"),
    path("sw.js", service_worker, name="service_worker"),
    path("offline/", offline, name="offline"),
]
