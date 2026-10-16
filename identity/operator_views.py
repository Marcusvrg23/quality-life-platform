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

from .eligibility import (
    add_allowed_emails,
    parse_emails,
    remove_allowed_email,
    set_allowed_email_role,
)
from .forms import OperatorAllowedEmailsForm, OrganizationCreateForm
from .invitations import issue_invitations
from .models import ALLOWED_EMAIL_ROLES, AllowedEmail, Membership, Organization
from .operator import create_organization, enter_as_admin, set_organization_active
from .views import (
    ROLE_LABELS,
    allowed_entries,
    emails_added_messages,
    invitation_link,
    whatsapp_message,
)

LIST_ROLES = {role.value for role in ALLOWED_EMAIL_ROLES}


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
    # distinct: two joins (memberships, allowed_emails) would multiply rows.
    return Organization.objects.annotate(
        collaborators=Count(
            "memberships",
            filter=active & Q(memberships__role=Membership.Role.COLLABORATOR),
            distinct=True,
        ),
        managers=Count(
            "memberships",
            filter=active & Q(memberships__role=Membership.Role.CORPORATE_MANAGER),
            distinct=True,
        ),
        allowed=Count("allowed_emails", distinct=True),
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
    """One-screen wizard: company, collaborator e-mails and manager e-mails."""
    form = OrganizationCreateForm(request.POST)
    if not form.is_valid():
        return _render_panel(request, form=form, status=400)
    organization = create_organization(form.cleaned_data["name"], request.user)
    managers, invalid_m, repeated_m = parse_emails(form.cleaned_data["managers"])
    collaborators, invalid_c, repeated_c = parse_emails(
        form.cleaned_data["collaborators"]
    )
    # An e-mail in both boxes is the manager.
    collaborators = [email for email in collaborators if email not in managers]
    added_m, _ = add_allowed_emails(
        organization, managers, Membership.Role.CORPORATE_MANAGER, request.user
    )
    added_c, _ = add_allowed_emails(
        organization, collaborators, Membership.Role.COLLABORATOR, request.user
    )
    messages.success(
        request,
        f"Empresa {organization.name} criada com {len(added_c)} colaborador"
        f"{'es' if len(added_c) != 1 else ''} e {len(added_m)} gestor"
        f"{'es' if len(added_m) != 1 else ''}.",
    )
    emails_added_messages(
        request, added_c + added_m, invalid_c + invalid_m, repeated_c + repeated_m
    )
    return redirect("operator_organization_emails", organization.pk)


def _render_emails(request, organization, *, form=None, status=200):
    other = {
        Membership.Role.COLLABORATOR: Membership.Role.CORPORATE_MANAGER,
        Membership.Role.CORPORATE_MANAGER: Membership.Role.COLLABORATOR,
    }
    entries = [
        {
            **item,
            "other_role": other[item["entry"].role],
            "toggle_label": "Tornar gestor"
            if item["entry"].role == Membership.Role.COLLABORATOR
            else "Voltar a colaborador",
        }
        for item in allowed_entries(organization)
    ]
    return render(
        request,
        "identity/operator_emails.html",
        {
            "tenant": None,
            "organization": organization,
            "entries": entries,
            "form": form or OperatorAllowedEmailsForm(),
            "whatsapp": whatsapp_message(request),
            "role_labels": ROLE_LABELS,
        },
        status=status,
    )


@operator_required
@never_cache
@require_GET
def operator_organization_emails(request, organization_id):
    organization = get_object_or_404(Organization, pk=organization_id)
    return _render_emails(request, organization)


@operator_required
@require_POST
def operator_email_add(request, organization_id):
    organization = get_object_or_404(Organization, pk=organization_id)
    form = OperatorAllowedEmailsForm(request.POST)
    if not form.is_valid():
        return _render_emails(request, organization, form=form, status=400)
    valid, invalid, repeated = parse_emails(form.cleaned_data["emails"])
    added, already = add_allowed_emails(
        organization, valid, form.cleaned_data["papel"], request.user
    )
    emails_added_messages(request, added, invalid, repeated + already)
    return redirect("operator_organization_emails", organization.pk)


def _entry(organization_id, entry_id):
    return get_object_or_404(
        AllowedEmail.objects.select_related("organization"),
        pk=entry_id,
        organization_id=organization_id,
    )


@operator_required
@require_POST
def operator_email_remove(request, organization_id, entry_id):
    entry = _entry(organization_id, entry_id)
    email = entry.email
    remove_allowed_email(entry, request.user)
    messages.success(request, f"{email} foi removido da lista e perdeu o acesso.")
    return redirect("operator_organization_emails", organization_id)


@operator_required
@require_POST
def operator_email_role(request, organization_id, entry_id):
    """'Tornar gestor' / 'Voltar a colaborador' on a listed person."""
    entry = _entry(organization_id, entry_id)
    role = request.POST.get("papel")
    if role not in LIST_ROLES:
        return HttpResponseBadRequest("Papel inválido.")
    set_allowed_email_role(entry, role, request.user)
    messages.success(request, f"{entry.email} agora é {ROLE_LABELS[role].lower()}.")
    return redirect("operator_organization_emails", organization_id)


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
