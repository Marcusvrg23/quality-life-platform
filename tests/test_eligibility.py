"""Allowed e-mail list and the access rules in identity.eligibility (spec 14)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from identity.eligibility import (
    add_allowed_emails,
    is_eligible,
    memberships_for_email,
    parse_emails,
    remove_allowed_email,
    set_allowed_email_role,
)
from identity.models import AllowedEmail, Membership, Organization, User

Role = Membership.Role
PASSWORD = "eligibility-test-password-27"


class ParseEmailsTests(TestCase):
    def test_accepts_every_separator_and_normalizes(self):
        text = "Ana@A.test, bruno@a.test;carla@a.test\n  dado@a.test \t eva@a.test\r\n"
        valid, invalid, repeated = parse_emails(text)
        self.assertEqual(
            valid,
            ["ana@a.test", "bruno@a.test", "carla@a.test", "dado@a.test", "eva@a.test"],
        )
        self.assertEqual(invalid, [])
        self.assertEqual(repeated, [])

    def test_reports_invalid_and_repeated_keeping_first(self):
        valid, invalid, repeated = parse_emails(
            "ana@a.test\nsem-arroba\nANA@a.test\nbruno@a.test,bruno@a.test\n@x"
        )
        self.assertEqual(valid, ["ana@a.test", "bruno@a.test"])
        self.assertEqual(invalid, ["sem-arroba", "@x"])
        self.assertEqual(repeated, ["ana@a.test", "bruno@a.test"])

    def test_empty_text(self):
        self.assertEqual(parse_emails(""), ([], [], []))
        self.assertEqual(parse_emails(None), ([], [], []))


class EligibilityTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Empresa A", slug="empresa-a")
        self.other_org = Organization.objects.create(name="Empresa B", slug="empresa-b")
        self.operator = User.objects.create_superuser("ql@quality.test", PASSWORD)

    def allow(self, email, organization=None, role=Role.COLLABORATOR):
        return AllowedEmail.objects.create(
            organization=organization or self.org,
            email=email,
            role=role,
            added_by=self.operator,
        )

    def membership(self, user, organization=None):
        return Membership.objects.get(user=user, organization=organization or self.org)


class AllowedEmailModelTests(EligibilityTestCase):
    def test_email_is_normalized_and_unique_per_company(self):
        entry = self.allow("  Ana@A.TEST ")
        self.assertEqual(entry.email, "ana@a.test")
        with self.assertRaises(IntegrityError), transaction.atomic():
            AllowedEmail.objects.create(organization=self.org, email="ANA@a.test")
        # The same e-mail may be allowed in another company.
        self.allow("ana@a.test", organization=self.other_org)
        self.assertEqual(AllowedEmail.objects.filter(email="ana@a.test").count(), 2)

    def test_database_refuses_other_roles(self):
        for role in (Role.ADMIN, Role.PROFESSIONAL, "ROOT"):
            with (
                self.subTest(role=role),
                self.assertRaises(IntegrityError),
                transaction.atomic(),
            ):
                AllowedEmail.objects.create(
                    organization=self.org, email=f"{role.lower()}@a.test", role=role
                )

    def test_add_allowed_emails_reports_already_listed(self):
        self.allow("ana@a.test")
        added, repeated = add_allowed_emails(
            self.org, ["ANA@a.test", "bruno@a.test"], Role.COLLABORATOR, self.operator
        )
        self.assertEqual([entry.email for entry in added], ["bruno@a.test"])
        self.assertEqual(repeated, ["ana@a.test"])
        self.assertEqual(added[0].added_by, self.operator)
        with self.assertRaises(ValueError):
            add_allowed_emails(self.org, ["x@a.test"], Role.ADMIN, self.operator)


class MembershipsForEmailTests(EligibilityTestCase):
    def test_unknown_user_or_unlisted_email_grants_nothing(self):
        self.allow("ana@a.test")
        self.assertEqual(memberships_for_email("ana@a.test"), [])
        user = User.objects.create_user("fora@a.test", PASSWORD)
        self.assertEqual(memberships_for_email(user.email), [])
        self.assertFalse(Membership.objects.filter(user=user).exists())
        self.assertFalse(is_eligible("fora@a.test"))
        self.assertTrue(is_eligible("ANA@a.test"))

    def test_creates_membership_with_the_listed_role(self):
        self.allow("ana@a.test")
        self.allow("gestora@a.test", role=Role.CORPORATE_MANAGER)
        ana = User.objects.create_user("Ana@A.test", PASSWORD)
        gestora = User.objects.create_user("gestora@a.test", PASSWORD)
        self.assertEqual(len(memberships_for_email("ANA@a.test")), 1)
        self.assertEqual(len(memberships_for_email(gestora.email)), 1)
        self.assertEqual(self.membership(ana).role, Role.COLLABORATOR)
        self.assertEqual(self.membership(gestora).role, Role.CORPORATE_MANAGER)
        self.assertTrue(self.membership(ana).is_active)

    def test_two_companies_give_two_memberships_and_inactive_company_none(self):
        self.allow("multi@a.test")
        self.allow(
            "multi@a.test", organization=self.other_org, role=Role.CORPORATE_MANAGER
        )
        closed = Organization.objects.create(
            name="Fechada", slug="fechada", is_active=False
        )
        self.allow("multi@a.test", organization=closed)
        user = User.objects.create_user("multi@a.test", PASSWORD)
        granted = memberships_for_email(user.email)
        self.assertEqual(
            sorted(m.organization.slug for m in granted), ["empresa-a", "empresa-b"]
        )
        self.assertEqual(
            self.membership(user, self.other_org).role, Role.CORPORATE_MANAGER
        )
        self.assertFalse(Membership.objects.filter(organization=closed).exists())
        self.assertFalse(is_eligible("only@fechada.test"))

    def test_reactivates_and_aligns_role_but_never_admin_or_superuser(self):
        self.allow("volta@a.test", role=Role.CORPORATE_MANAGER)
        self.allow("admin@a.test")
        self.allow(self.operator.email)
        volta = User.objects.create_user("volta@a.test", PASSWORD)
        Membership.objects.create(
            user=volta, organization=self.org, role=Role.COLLABORATOR, is_active=False
        )
        admin = User.objects.create_user("admin@a.test", PASSWORD)
        Membership.objects.create(user=admin, organization=self.org, role=Role.ADMIN)
        Membership.objects.create(
            user=self.operator, organization=self.org, role=Role.ADMIN, is_active=False
        )
        memberships_for_email(volta.email)
        memberships_for_email(admin.email)
        memberships_for_email(self.operator.email)
        self.assertEqual(self.membership(volta).role, Role.CORPORATE_MANAGER)
        self.assertTrue(self.membership(volta).is_active)
        self.assertEqual(self.membership(admin).role, Role.ADMIN)
        self.assertEqual(self.membership(self.operator).role, Role.ADMIN)
        self.assertFalse(self.membership(self.operator).is_active)

    def test_is_idempotent(self):
        self.allow("ana@a.test")
        ana = User.objects.create_user("ana@a.test", PASSWORD)
        memberships_for_email(ana.email)
        memberships_for_email(ana.email)
        self.assertEqual(Membership.objects.filter(user=ana).count(), 1)


class RemoveAndRoleTests(EligibilityTestCase):
    def test_remove_deactivates_membership_immediately(self):
        entry = self.allow("sai@a.test")
        user = User.objects.create_user("sai@a.test", PASSWORD)
        memberships_for_email(user.email)
        remove_allowed_email(entry, self.operator)
        self.assertFalse(AllowedEmail.objects.filter(pk=entry.pk).exists())
        self.assertFalse(self.membership(user).is_active)
        # Re-adding and signing in again restores the access.
        self.allow("sai@a.test")
        memberships_for_email(user.email)
        self.assertTrue(self.membership(user).is_active)

    def test_remove_touches_only_this_company(self):
        entry = self.allow("dois@a.test")
        self.allow("dois@a.test", organization=self.other_org)
        user = User.objects.create_user("dois@a.test", PASSWORD)
        memberships_for_email(user.email)
        remove_allowed_email(entry, self.operator)
        self.assertFalse(self.membership(user).is_active)
        self.assertTrue(self.membership(user, self.other_org).is_active)

    def test_remove_never_demotes_admin_or_superuser(self):
        admin = User.objects.create_user("admin@a.test", PASSWORD)
        Membership.objects.create(user=admin, organization=self.org, role=Role.ADMIN)
        Membership.objects.create(
            user=self.operator, organization=self.org, role=Role.ADMIN
        )
        admin_entry = self.allow("admin@a.test")
        root_entry = self.allow(self.operator.email, role=Role.CORPORATE_MANAGER)
        remove_allowed_email(admin_entry, self.operator)
        remove_allowed_email(root_entry, self.operator)
        self.assertTrue(self.membership(admin).is_active)
        self.assertTrue(self.membership(self.operator).is_active)
        self.assertEqual(self.membership(admin).role, Role.ADMIN)

    def test_role_change_updates_list_and_membership(self):
        entry = self.allow("promove@a.test")
        user = User.objects.create_user("promove@a.test", PASSWORD)
        memberships_for_email(user.email)
        set_allowed_email_role(entry, Role.CORPORATE_MANAGER, self.operator)
        entry.refresh_from_db()
        self.assertEqual(entry.role, Role.CORPORATE_MANAGER)
        self.assertEqual(self.membership(user).role, Role.CORPORATE_MANAGER)
        set_allowed_email_role(entry, Role.COLLABORATOR, self.operator)
        self.assertEqual(self.membership(user).role, Role.COLLABORATOR)
        with self.assertRaises(ValueError):
            set_allowed_email_role(entry, Role.ADMIN, self.operator)

    def test_role_change_never_touches_admin_membership(self):
        admin = User.objects.create_user("admin@a.test", PASSWORD)
        Membership.objects.create(user=admin, organization=self.org, role=Role.ADMIN)
        entry = self.allow("admin@a.test")
        set_allowed_email_role(entry, Role.CORPORATE_MANAGER, self.operator)
        self.assertEqual(self.membership(admin).role, Role.ADMIN)
