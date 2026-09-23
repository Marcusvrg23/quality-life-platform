"""Session authentication and tenant entry points."""

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from .forms import EmailAuthenticationForm
from .tenant import (
    SESSION_ORGANIZATION_KEY,
    active_memberships,
    context_for_membership,
    require_membership_for_slug,
    resolve_tenant_context,
)


class EmailLoginView(LoginView):
    authentication_form = EmailAuthenticationForm
    template_name = "identity/login.html"


class SessionLogoutView(LogoutView):
    next_page = "login"


@login_required
@require_GET
def app_home(request: HttpRequest) -> HttpResponse:
    context = resolve_tenant_context(request)
    if context is not None:
        return render(request, "identity/app.html", {"tenant": context})

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
    return render(
        request,
        "identity/app.html",
        {"tenant": context_for_membership(membership)},
    )
