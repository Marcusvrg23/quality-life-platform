"""Identity and adversarial tenant authorization tests on PostgreSQL."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from config.tenant import (
    SESSION_ORGANIZATION_KEY,
    get_active_membership,
    get_user_organizations,
    require_active_membership,
    user_has_role,
)
from identity.admin import UserCreationForm
from identity.models import Membership, Organization

User = get_user_model()


class IdentityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="Member@Example.COM", password="strong-test-password-123"
        )
        self.organization_a = Organization.objects.create(
            name="Empresa A", slug="empresa-a"
        )
        self.organization_b = Organization.objects.create(
            name="Empresa B", slug="empresa-b"
        )

    def membership(
        self, *, user=None, organization=None, role=Membership.Role.COLLABORATOR
    ):
        return Membership.objects.create(
            user=user or self.user,
            organization=organization or self.organization_a,
            role=role,
        )

    def test_email_is_login_identifier_and_password_is_hashed(self):
        self.assertEqual(User.USERNAME_FIELD, "email")
        self.assertEqual(self.user.email, "member@example.com")
        self.assertNotEqual(self.user.password, "strong-test-password-123")
        self.assertTrue(self.user.check_password("strong-test-password-123"))
        self.assertFalse(self.user.check_password("incorrect"))
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertTrue(self.user.is_active)
        self.assertIsNotNone(self.user.created_at)

    def test_login_valid_and_case_insensitive(self):
        response = self.client.post(
            reverse("login"),
            {"username": "MEMBER@EXAMPLE.COM", "password": "strong-test-password-123"},
        )
        self.assertRedirects(response, reverse("app"), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_login_invalid_has_generic_error(self):
        for email in ("Member@Example.COM", "unknown@example.com"):
            with self.subTest(email=email):
                response = self.client.post(
                    reverse("login"),
                    {"username": email, "password": "wrong-password"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Email ou senha inválidos.")
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.post(
            reverse("login"),
            {"username": self.user.email, "password": "strong-test-password-123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_post_and_ends_session(self):
        self.membership()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertRedirects(
            self.client.get(reverse("app")),
            f"{reverse('login')}?next={reverse('app')}",
        )

    def test_anonymous_is_denied_all_tenant_routes(self):
        for url in (
            reverse("app"),
            reverse("organization_home", args=[self.organization_a.slug]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)
        self.assertEqual(
            self.client.post(reverse("select_organization")).status_code, 302
        )

    def test_user_without_membership_has_safe_denial(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("app"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Sem acesso", status_code=403)
        self.assertEqual(
            self.client.get(
                reverse("organization_home", args=[self.organization_a.slug])
            ).status_code,
            403,
        )

    def test_inactive_membership_denied(self):
        membership = self.membership()
        membership.is_active = False
        membership.save()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("app")).status_code, 403)
        self.assertEqual(
            self.client.get(
                reverse("organization_home", args=[self.organization_a.slug])
            ).status_code,
            403,
        )
        self.assertIsNone(get_active_membership(self.user, self.organization_a))

    def test_inactive_organization_denied(self):
        self.membership()
        self.organization_a.is_active = False
        self.organization_a.save()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("app")).status_code, 403)
        self.assertEqual(
            self.client.get(
                reverse("organization_home", args=[self.organization_a.slug])
            ).status_code,
            403,
        )
        self.assertQuerySetEqual(get_user_organizations(self.user), [])

    def test_each_role_requires_own_membership_for_another_tenant(self):
        for role in (
            Membership.Role.COLLABORATOR,
            Membership.Role.CORPORATE_MANAGER,
            Membership.Role.PROFESSIONAL,
        ):
            with self.subTest(role=role):
                Membership.objects.all().delete()
                self.membership(role=role)
                self.client.force_login(self.user)
                self.assertContains(self.client.get(reverse("app")), "Empresa A")
                self.assertEqual(
                    self.client.get(
                        reverse("organization_home", args=[self.organization_b.slug])
                    ).status_code,
                    403,
                )
                self.assertFalse(user_has_role(self.user, self.organization_b, role))

    def test_single_membership_enters_its_organization(self):
        membership = self.membership(role=Membership.Role.PROFESSIONAL)
        self.client.force_login(self.user)
        response = self.client.get(reverse("app"))
        self.assertContains(response, self.organization_a.name)
        self.assertEqual(
            self.client.session[SESSION_ORGANIZATION_KEY], self.organization_a.pk
        )
        self.assertEqual(
            require_active_membership(self.user, self.organization_a), membership
        )
        self.assertTrue(
            user_has_role(self.user, self.organization_a, Membership.Role.PROFESSIONAL)
        )

    def test_multiple_memberships_require_explicit_selection(self):
        self.membership()
        self.membership(organization=self.organization_b)
        self.client.force_login(self.user)
        response = self.client.get(reverse("app"))
        self.assertTemplateUsed(response, "identity/select_organization.html")
        self.assertNotIn(SESSION_ORGANIZATION_KEY, self.client.session)
        response = self.client.post(
            reverse("select_organization"), {"organization": self.organization_b.slug}
        )
        self.assertRedirects(response, reverse("app"), fetch_redirect_response=False)
        self.assertContains(self.client.get(reverse("app")), self.organization_b.name)

    def test_organization_parameter_tampering_denied(self):
        self.membership()
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("select_organization"),
            {"organization": self.organization_b.slug, "role": Membership.Role.ADMIN},
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotEqual(
            self.client.session.get(SESSION_ORGANIZATION_KEY), self.organization_b.pk
        )

    def test_foreign_and_unknown_organization_slugs_have_same_denial(self):
        self.membership()
        self.client.force_login(self.user)
        for slug in (self.organization_b.slug, "unknown-company"):
            with self.subTest(slug=slug):
                self.assertEqual(
                    self.client.get(
                        reverse("organization_home", args=[slug])
                    ).status_code,
                    403,
                )

    def test_session_cannot_switch_tenant_without_membership(self):
        self.membership()
        self.client.force_login(self.user)
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = self.organization_b.pk
        session.save()
        self.assertEqual(self.client.get(reverse("app")).status_code, 403)
        self.assertNotIn(SESSION_ORGANIZATION_KEY, self.client.session)

    def test_revoked_membership_invalidates_existing_session_context(self):
        membership = self.membership()
        self.client.force_login(self.user)
        self.client.get(reverse("app"))
        membership.is_active = False
        membership.save()
        self.assertEqual(self.client.get(reverse("app")).status_code, 403)

    def test_user_cannot_escalate_own_role(self):
        membership = self.membership()
        self.client.force_login(self.user)
        self.client.post(
            reverse("select_organization"),
            {"organization": self.organization_a.slug, "role": Membership.Role.ADMIN},
        )
        membership.refresh_from_db()
        self.assertEqual(membership.role, Membership.Role.COLLABORATOR)
        self.assertFalse(
            user_has_role(self.user, self.organization_a, Membership.Role.ADMIN)
        )

    def test_open_redirect_next_is_rejected(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": self.user.email,
                "password": "strong-test-password-123",
                "next": "https://attacker.example/steal",
            },
        )
        self.assertRedirects(response, reverse("app"), fetch_redirect_response=False)

    def test_csrf_protects_login_and_tenant_switch(self):
        csrf_client = Client(enforce_csrf_checks=True)
        credentials = {
            "username": self.user.email,
            "password": "strong-test-password-123",
        }
        self.assertEqual(
            csrf_client.post(reverse("login"), credentials).status_code, 403
        )
        response = csrf_client.get(reverse("login"))
        token = response.cookies["csrftoken"].value
        self.assertEqual(
            csrf_client.post(
                reverse("login"), credentials, HTTP_X_CSRFTOKEN=token
            ).status_code,
            302,
        )
        self.membership()
        self.assertEqual(
            csrf_client.post(
                reverse("select_organization"),
                {"organization": self.organization_a.slug},
            ).status_code,
            403,
        )

    def test_admin_and_superuser_do_not_bypass_tenant_membership(self):
        superuser = User.objects.create_superuser(
            email="root@example.com", password="strong-test-password-123"
        )
        self.client.force_login(superuser)
        self.assertEqual(self.client.get(reverse("app")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)

        self.membership(role=Membership.Role.ADMIN)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("app")), "Empresa A")
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)

    def test_staff_with_model_permissions_cannot_access_identity_admin(self):
        membership = self.membership()
        staff = User.objects.create_user(
            email="staff@example.com",
            password="strong-test-password-123",
            is_staff=True,
        )
        staff.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="identity")
        )
        self.client.force_login(staff)
        for url in (
            reverse("admin:identity_user_changelist"),
            reverse("admin:identity_user_change", args=[staff.pk]),
            reverse("admin:identity_user_add"),
            reverse("admin:identity_organization_changelist"),
            reverse("admin:identity_membership_changelist"),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("admin:identity_user_change", args=[staff.pk]),
                {"email": staff.email, "is_staff": "on", "is_superuser": "on"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("admin:identity_membership_change", args=[membership.pk]),
                {"role": Membership.Role.ADMIN, "is_active": "on"},
            ).status_code,
            403,
        )
        staff.refresh_from_db()
        membership.refresh_from_db()
        self.assertFalse(staff.is_superuser)
        self.assertEqual(membership.role, Membership.Role.COLLABORATOR)

    def test_admin_user_creation_form_hashes_password(self):
        form = UserCreationForm(
            data={
                "email": "new@example.com",
                "password1": "strong-test-password-123",
                "password2": "strong-test-password-123",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        created = form.save()
        self.assertNotEqual(created.password, "strong-test-password-123")
        self.assertTrue(created.check_password("strong-test-password-123"))

    def test_email_case_insensitive_uniqueness_is_database_enforced(self):
        other = User.objects.create_user(
            email="other@example.com", password="strong-test-password-123"
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=other.pk).update(email="MEMBER@EXAMPLE.COM")

    def test_duplicate_membership_is_database_enforced(self):
        self.membership()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.membership()

    def test_invalid_role_is_database_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.membership(role="OWNER")
