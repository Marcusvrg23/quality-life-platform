"""Team management by corporate managers and public invitation acceptance."""

from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
    require_POST,
)

from config.tenant import SESSION_ORGANIZATION_KEY, resolve_tenant_context

from .eligibility import add_allowed_emails, parse_emails, remove_allowed_email
from .forms import AllowedEmailsForm, InvitationQuantityForm, InvitationSignupForm
from .invitations import find_invitation, issue_invitations
from .models import AllowedEmail, Invitation, Membership, User

TEAM_ROLES = (Membership.Role.CORPORATE_MANAGER, Membership.Role.ADMIN)
ROLE_LABELS = {
    Membership.Role.COLLABORATOR: "Colaborador",
    Membership.Role.CORPORATE_MANAGER: "Gestor",
    Membership.Role.PROFESSIONAL: "Profissional",
    Membership.Role.ADMIN: "Administrador",
}
INVALID_INVITATION_MESSAGE = (
    "Este convite não está disponível. Peça um novo link ao gestor da sua empresa."
)
EXISTING_ACCOUNT_MESSAGE = (
    "Este e-mail já tem conta. Entre com sua senha e abra o link de novo."
)
INACTIVE_MEMBERSHIP_MESSAGE = (
    "Seu acesso a esta empresa está desativado. Fale com o gestor da sua empresa."
)
WHATSAPP_TEXT = (
    "Acesse {site} e clique em Continuar com o Google usando o e-mail que você "
    "passou ao RH."
)


def whatsapp_message(request):
    """Ready-to-send text telling listed people how to get in."""
    text = WHATSAPP_TEXT.format(site=request.build_absolute_uri("/"))
    return {"text": text, "url": "https://wa.me/?text=" + quote(text, safe="")}


def emails_added_messages(request, added, invalid, repeated):
    """One success line with the count, plus what was ignored and why."""
    count = len(added)
    messages.success(
        request,
        f"{count} e-mail{'s' if count != 1 else ''} liberado{'s' if count != 1 else ''}.",
    )
    if invalid:
        messages.warning(
            request, "Ignorados por serem inválidos: " + ", ".join(invalid) + "."
        )
    if repeated:
        messages.warning(
            request, "Ignorados por estarem repetidos: " + ", ".join(repeated) + "."
        )


def allowed_entries(organization):
    return [
        {"entry": entry, "role_label": ROLE_LABELS.get(entry.role, entry.role)}
        for entry in AllowedEmail.objects.filter(organization=organization).order_by(
            "email", "pk"
        )
    ]


def _team_tenant(request):
    """Only managers and admins of the active company manage its team."""
    tenant = resolve_tenant_context(request)
    if tenant is None or tenant.role not in TEAM_ROLES:
        raise PermissionDenied("Team unavailable.")
    return tenant


def invitation_link(request, organization, token):
    url = request.build_absolute_uri(reverse("accept_invitation", args=[token]))
    text = f"Convite para a Quality Life da empresa {organization.name}: {url}"
    return {"url": url, "whatsapp": "https://wa.me/?text=" + quote(text, safe="")}


def _render_team(request, tenant, *, form=None, links=None, status=200):
    memberships = (
        Membership.objects.filter(organization=tenant.organization)
        .select_related("user")
        .order_by("-is_active", "user__email")
    )
    members = [
        {
            "membership": membership,
            "role_label": ROLE_LABELS.get(membership.role, membership.role),
            "can_toggle": membership.role == Membership.Role.COLLABORATOR
            and membership.user_id != request.user.pk,
        }
        for membership in memberships
    ]
    return render(
        request,
        "identity/team.html",
        {
            "tenant": tenant,
            "members": members,
            "form": form or InvitationQuantityForm(),
            "links": links or [],
            "emails_form": AllowedEmailsForm(),
            "allowed": allowed_entries(tenant.organization),
            "whatsapp": whatsapp_message(request),
        },
        status=status,
    )


@never_cache
@login_required
@require_GET
def team(request):
    tenant = resolve_tenant_context(request)
    if tenant is None:
        return redirect("app")
    if tenant.role not in TEAM_ROLES:
        raise PermissionDenied("Team unavailable.")
    return _render_team(request, tenant)


@login_required
@require_POST
def team_member_status(request, membership_id):
    tenant = _team_tenant(request)
    membership = get_object_or_404(
        Membership.objects.select_related("user"),
        pk=membership_id,
        organization=tenant.organization,
    )
    if (
        membership.user_id == request.user.pk
        or membership.role != Membership.Role.COLLABORATOR
    ):
        raise PermissionDenied("Only other collaborators can be changed.")
    value = request.POST.get("ativo")
    if value not in ("0", "1"):
        return HttpResponseBadRequest("Valor inválido.")
    membership.is_active = value == "1"
    membership.save(update_fields=["is_active", "updated_at"])
    action = "reativado" if membership.is_active else "desativado"
    messages.success(request, f"{membership.user.email} foi {action}.")
    return redirect("team")


@login_required
@require_POST
def team_emails_add(request):
    """Managers clear collaborators only; the role is never taken from the form."""
    tenant = _team_tenant(request)
    form = AllowedEmailsForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Cole ao menos um e-mail.")
        return redirect("team")
    valid, invalid, repeated = parse_emails(form.cleaned_data["emails"])
    added, already = add_allowed_emails(
        tenant.organization, valid, Membership.Role.COLLABORATOR, request.user
    )
    emails_added_messages(request, added, invalid, repeated + already)
    return redirect("team")


@login_required
@require_POST
def team_email_remove(request, entry_id):
    """Only collaborator entries of the active company; anything else is 404."""
    tenant = _team_tenant(request)
    entry = get_object_or_404(
        AllowedEmail,
        pk=entry_id,
        organization=tenant.organization,
        role=Membership.Role.COLLABORATOR,
    )
    email = entry.email
    remove_allowed_email(entry, request.user)
    messages.success(request, f"{email} foi removido da lista e perdeu o acesso.")
    return redirect("team")


@never_cache
@login_required
@require_POST
def team_invitations_create(request):
    """Render the new links in this response only; they are never stored."""
    tenant = _team_tenant(request)
    form = InvitationQuantityForm(request.POST)
    if not form.is_valid():
        return _render_team(request, tenant, form=form, status=400)
    tokens = issue_invitations(
        tenant.organization, request.user, form.cleaned_data["quantidade"]
    )
    links = [invitation_link(request, tenant.organization, t) for t in tokens]
    return _render_team(request, tenant, links=links)


@login_required
@require_POST
def team_invitation_revoke(request, invitation_id):
    tenant = _team_tenant(request)
    # Conditional UPDATE: never revokes a used invite, even if accepted concurrently.
    revoked = Invitation.objects.filter(
        pk=invitation_id,
        organization=tenant.organization,
        role=Membership.Role.COLLABORATOR,
        used_at__isnull=True,
        revoked_at__isnull=True,
    ).update(revoked_at=timezone.now())
    if not revoked:
        raise Http404("Invitation unavailable.")
    messages.success(request, "Convite revogado.")
    return redirect("team")


def _invalid_invitation(request):
    """One generic page for every unusable link; never says why."""
    return render(
        request,
        "identity/invitation_invalid.html",
        {"message": INVALID_INVITATION_MESSAGE},
        status=404,
    )


def _render_accept(request, invitation, status=200, **context):
    return render(
        request,
        "identity/invitation_accept.html",
        {"invitation": invitation, **context},
        status=status,
    )


def _existing_account(request, invitation, form):
    login_url = f"{reverse('login')}?next={quote(request.path)}"
    return _render_accept(
        request,
        invitation,
        form=form,
        existing_account_message=EXISTING_ACCOUNT_MESSAGE,
        login_url=login_url,
    )


def _join(request, token, *, form=None):
    """Consume the invite at most once: the row stays locked until commit."""
    with transaction.atomic():
        invitation = find_invitation(token, lock=True)
        if invitation is None:
            return _invalid_invitation(request)
        organization = invitation.organization
        user = request.user if request.user.is_authenticated else None
        if user is None:
            try:
                with transaction.atomic():
                    user = User.objects.create_user(
                        form.cleaned_data["email"], form.cleaned_data["password1"]
                    )
            except IntegrityError:
                return _existing_account(request, invitation, form)
        membership = Membership.objects.filter(
            user=user, organization=organization
        ).first()
        if membership is not None and not membership.is_active:
            return _render_accept(
                request,
                invitation,
                status=403,
                inactive_message=INACTIVE_MEMBERSHIP_MESSAGE,
            )
        if membership is None:
            try:
                with transaction.atomic():
                    Membership.objects.create(
                        user=user, organization=organization, role=invitation.role
                    )
            except IntegrityError:
                # Joined concurrently through another invite: keep this one unused.
                pass
            else:
                invitation.used_at = timezone.now()
                invitation.used_by = user
                invitation.save(update_fields=["used_at", "used_by"])
    if not request.user.is_authenticated:
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session[SESSION_ORGANIZATION_KEY] = organization.pk
    return redirect("app")


@never_cache
@require_http_methods(["GET", "POST"])
def accept_invitation(request, token):
    invitation = find_invitation(token)
    if invitation is None:
        return _invalid_invitation(request)
    if request.user.is_authenticated:
        if request.method == "POST":
            return _join(request, token)
        return _render_accept(request, invitation)
    form = InvitationSignupForm(request.POST if request.method == "POST" else None)
    if form.is_bound and form.is_valid():
        if User.objects.filter(email__iexact=form.cleaned_data["email"]).exists():
            return _existing_account(request, invitation, form)
        return _join(request, token, form=form)
    return _render_accept(request, invitation, form=form)
