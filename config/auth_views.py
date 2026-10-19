"""Session authentication and tenant entry points."""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from identity import google
from identity.eligibility import memberships_for_email
from identity.models import Membership
from wellbeing.services import first_name, greeting, personal_progress

from . import tips_calendar, wellbeing_catalog
from .calendar_highlights import active_highlight
from .forms import EmailAuthenticationForm
from .recommendations import build_recommendation
from .tenant import (
    SESSION_ORGANIZATION_KEY,
    active_memberships,
    context_for_membership,
    require_membership_for_slug,
    resolve_tenant_context,
)
from .views import SALES_EMAIL_PLACEHOLDER


def _render_home(request: HttpRequest, tenant) -> HttpResponse:
    return render(
        request,
        "identity/app.html",
        {
            "tenant": tenant,
            "recommendation": (
                build_recommendation(request.user, tenant.organization)
                if tenant.role == Membership.Role.COLLABORATOR
                else None
            ),
            "highlight": active_highlight(),
            "greeting": greeting(),
            "first_name": first_name(request.user, tenant.organization),
            "tip": (
                tips_calendar.tip_to_show(timezone.localdate())
                or wellbeing_catalog.tip_of_the_day(timezone.localdate())
            ),
            "progress": personal_progress(request.user, tenant.organization),
        },
    )


class EmailLoginView(LoginView):
    authentication_form = EmailAuthenticationForm
    template_name = "identity/login.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["google_enabled"] = google.enabled()
        return context

    def form_valid(self, form):
        # The allowed e-mail list applies to password sign-in too (spec 14).
        memberships_for_email(form.get_user().email)
        return super().form_valid(form)


class SessionLogoutView(LogoutView):
    next_page = "login"


class ShellPasswordChangeView(SuccessMessageMixin, PasswordChangeView):
    """Own-account password change; the tenant only feeds the shell menu."""

    template_name = "identity/password_change.html"
    success_url = reverse_lazy("password_change")
    success_message = "Senha alterada com sucesso."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context["tenant"] = resolve_tenant_context(self.request)
        except PermissionDenied:
            context["tenant"] = None
        return context


@login_required
@require_GET
def app_home(request: HttpRequest) -> HttpResponse:
    context = resolve_tenant_context(request)
    if context is not None:
        return _render_home(request, context)

    memberships = list(active_memberships(request.user))
    if not memberships:
        if request.user.is_superuser:
            return redirect("operator_panel")
        sales_email = getattr(settings, "QL_SALES_EMAIL", "") or SALES_EMAIL_PLACEHOLDER
        return render(
            request,
            "identity/no_access.html",
            {"sales_email": sales_email},
            status=403,
        )
    return render(
        request, "identity/select_organization.html", {"memberships": memberships}
    )


@login_required
@require_POST
def select_organization(request: HttpRequest) -> HttpResponse:
    slug = request.POST.get("organization", "")
    membership = require_membership_for_slug(request.user, slug)
    request.session[SESSION_ORGANIZATION_KEY] = membership.organization_id
    return redirect("app")


@login_required
@require_GET
def organization_home(request: HttpRequest, slug: str) -> HttpResponse:
    membership = require_membership_for_slug(request.user, slug)
    return _render_home(request, context_for_membership(membership))
