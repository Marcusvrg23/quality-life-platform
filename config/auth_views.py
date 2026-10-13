"""Session authentication and tenant entry points."""

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET, require_POST

from identity.models import Membership

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
        },
    )


class EmailLoginView(LoginView):
    authentication_form = EmailAuthenticationForm
    template_name = "identity/login.html"


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
        return render(request, "identity/no_access.html", status=403)
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
