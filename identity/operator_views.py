"""Quality Life operator panel: superusers only; everyone else gets a 404."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from config.tenant import SESSION_ORGANIZATION_KEY

from .forms import OrganizationCreateForm
from .invitations import issue_invitations
from .models import Membership, Organization
from .operator import create_organization, enter_as_admin, set_organization_active
from .views import invitation_link


def operator_required(view):
    """Hide the panel from anyone who is not a superuser, before any other check."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise Http404("Page not found.")
        return view(request, *args, **kwargs)

    return wrapper


def _companies():
    active = Q(memberships__is_active=True)
    return Organization.objects.annotate(
        collaborators=Count(
            "memberships",
            filter=active & Q(memberships__role=Membership.Role.COLLABORATOR),
        ),
        managers=Count(
            "memberships",
            filter=active & Q(memberships__role=Membership.Role.CORPORATE_MANAGER),
        ),
    ).order_by("name", "pk")


def _render_panel(request, *, form=None, manager_link=None, status=200):
    return render(
        request,
        "identity/operator_panel.html",
        {
            "tenant": None,
            "companies": _companies(),
            "form": form or OrganizationCreateForm(),
            "manager_link": manager_link,
        },
        status=status,
    )


@operator_required
@never_cache
@require_GET
def operator_panel(request):
    return _render_panel(request)


@operator_required
@require_POST
def operator_organization_create(request):
    form = OrganizationCreateForm(request.POST)
    if not form.is_valid():
        return _render_panel(request, form=form, status=400)
    organization = create_organization(form.cleaned_data["name"], request.user)
    messages.success(request, f"Empresa {organization.name} criada.")
    return redirect("operator_panel")


@operator_required
@require_POST
def operator_organization_status(request, organization_id):
    organization = get_object_or_404(Organization, pk=organization_id)
    value = request.POST.get("ativo")
    if value not in ("0", "1"):
        return HttpResponseBadRequest("Valor inválido.")
    set_organization_active(organization, value == "1", request.user)
    action = "reativada" if value == "1" else "desativada"
    messages.success(request, f"Empresa {organization.name} {action}.")
    return redirect("operator_panel")


@operator_required
@never_cache
@require_POST
def operator_manager_invitation(request, organization_id):
    """Render the new link in this response only; it is never stored."""
    organization = get_object_or_404(Organization, pk=organization_id, is_active=True)
    (token,) = issue_invitations(
        organization, request.user, 1, role=Membership.Role.CORPORATE_MANAGER
    )
    link = invitation_link(request, organization, token)
    return _render_panel(request, manager_link={"organization": organization, **link})


@operator_required
@require_POST
def operator_enter(request, organization_id):
    organization = get_object_or_404(Organization, pk=organization_id, is_active=True)
    if request.POST.get("confirmar") != "1":
        return HttpResponseBadRequest("Confirme a entrada como administrador.")
    enter_as_admin(request.user, organization)
    request.session[SESSION_ORGANIZATION_KEY] = organization.pk
    return redirect("app")
