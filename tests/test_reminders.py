"""Break reminders: owner-only settings per Membership
(docs/specs/13-pwa-lembretes.md, aceite 5)."""

from datetime import time

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from config.tenant import SESSION_ORGANIZATION_KEY
from identity.models import Membership, Organization, User
from wellbeing.models import ReminderSetting

PASSWORD = "reminder-test-password"
VALID = {
    "action": "activate",
    "interval_minutes": "90",
    "workday_start": "09:00",
    "workday_end": "17:30",
    "weekdays": ["1", "3", "5"],
}


class ReminderTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Empresa", slug="empresa")
        self.other_org = Organization.objects.create(name="Outra", slug="outra")
        self.owner = self.member("dono@empresa.test", Membership.Role.COLLABORATOR)
        self.colleague = self.member(
            "colega@empresa.test", Membership.Role.COLLABORATOR
        )
        self.manager = self.member(
            "gestor@empresa.test", Membership.Role.CORPORATE_MANAGER
        )

    def member(self, email, role, organization=None):
        user = User.objects.create_user(email, PASSWORD)
        Membership.objects.create(
            user=user, organization=organization or self.organization, role=role
        )
        return user

    def login(self, user, organization=None):
        self.client.force_login(user)
        if organization is not None:
            session = self.client.session
            session[SESSION_ORGANIZATION_KEY] = organization.pk
            session.save()

    def membership(self, user):
        return Membership.objects.get(user=user, organization=self.organization)

    def schedule(self):
        return self.client.get(reverse("wellbeing_reminder_schedule")).json()

    # Defaults and owner round trip -------------------------------------------

    def test_page_shows_defaults_and_fixed_texts(self):
        self.login(self.owner)
        response = self.client.get(reverse("wellbeing_reminders"))
        self.assertContains(response, "Ativar lembretes")
        self.assertContains(
            response,
            "Os lembretes aparecem enquanto o Quality Life estiver aberto no "
            "navegador ou no app da tela inicial. No iPhone, as notificações "
            "exigem o app adicionado à tela inicial e iOS 16.4 ou mais novo.",
        )
        self.assertContains(response, 'value="08:00"')
        self.assertContains(response, 'value="18:00"')
        self.assertFalse(ReminderSetting.objects.exists())
        self.assertEqual(
            self.schedule(),
            {
                "active": False,
                "interval": 60,
                "start": "08:00",
                "end": "18:00",
                "days": [1, 2, 3, 4, 5],
            },
        )

    def test_owner_saves_and_reads_back(self):
        self.login(self.owner)
        response = self.client.post(reverse("wellbeing_reminders"), VALID)
        self.assertRedirects(response, reverse("wellbeing_reminders"))
        setting = ReminderSetting.objects.get()
        self.assertEqual(setting.membership, self.membership(self.owner))
        self.assertTrue(setting.active)
        self.assertEqual(setting.interval_minutes, 90)
        self.assertEqual(setting.workday_start, time(9, 0))
        self.assertEqual(setting.workday_end, time(17, 30))
        self.assertEqual(setting.weekdays, "135")
        schedule = self.client.get(reverse("wellbeing_reminder_schedule"))
        self.assertEqual(schedule["Cache-Control"], "no-store, private")
        self.assertEqual(
            schedule.json(),
            {
                "active": True,
                "interval": 90,
                "start": "09:00",
                "end": "17:30",
                "days": [1, 3, 5],
            },
        )
        page = self.client.get(reverse("wellbeing_reminders"))
        self.assertContains(page, "Desativar lembretes")
        self.assertContains(page, 'value="17:30"')

    def test_owner_deactivates_and_keeps_choices(self):
        self.login(self.owner)
        self.client.post(reverse("wellbeing_reminders"), VALID)
        self.client.post(
            reverse("wellbeing_reminders"), {**VALID, "action": "deactivate"}
        )
        setting = ReminderSetting.objects.get()
        self.assertFalse(setting.active)
        self.assertEqual(setting.interval_minutes, 90)

    def test_save_keeps_active_state(self):
        self.login(self.owner)
        self.client.post(reverse("wellbeing_reminders"), VALID)
        self.client.post(
            reverse("wellbeing_reminders"),
            {**VALID, "action": "save", "interval_minutes": "120"},
        )
        setting = ReminderSetting.objects.get()
        self.assertTrue(setting.active)
        self.assertEqual(setting.interval_minutes, 120)

    def test_manager_also_has_own_reminders(self):
        self.login(self.manager)
        self.client.post(reverse("wellbeing_reminders"), VALID)
        self.assertEqual(
            ReminderSetting.objects.get().membership, self.membership(self.manager)
        )

    # Isolation -----------------------------------------------------------------

    def test_colleague_and_manager_never_see_owner_reminders(self):
        self.login(self.owner)
        self.client.post(reverse("wellbeing_reminders"), VALID)
        for user in (self.colleague, self.manager):
            self.login(user)
            self.assertFalse(self.schedule()["active"])
            page = self.client.get(reverse("wellbeing_reminders"))
            self.assertNotContains(page, 'value="17:30"')
            self.assertNotContains(page, "dono@empresa.test")
            self.client.post(
                reverse("wellbeing_reminders"), {**VALID, "action": "deactivate"}
            )
        self.assertTrue(
            ReminderSetting.objects.get(membership=self.membership(self.owner)).active
        )

    def test_client_cannot_choose_membership_or_user(self):
        self.login(self.colleague)
        owner_membership = self.membership(self.owner)
        self.client.post(
            reverse("wellbeing_reminders"),
            {**VALID, "membership": owner_membership.pk, "user": self.owner.pk},
        )
        self.assertFalse(
            ReminderSetting.objects.filter(membership=owner_membership).exists()
        )
        self.assertEqual(
            ReminderSetting.objects.get().membership, self.membership(self.colleague)
        )

    def test_same_person_has_separate_reminders_per_company(self):
        Membership.objects.create(
            user=self.owner,
            organization=self.other_org,
            role=Membership.Role.COLLABORATOR,
        )
        self.login(self.owner, self.organization)
        self.client.post(reverse("wellbeing_reminders"), VALID)
        self.login(self.owner, self.other_org)
        self.assertFalse(self.schedule()["active"])

    def test_forged_tenant_is_forbidden(self):
        for method, name, data in (
            ("get", "wellbeing_reminders", None),
            ("get", "wellbeing_reminder_schedule", None),
            ("post", "wellbeing_reminders", VALID),
        ):
            # A refused tenant is dropped from the session, so forge it again.
            self.login(self.owner, self.other_org)
            with self.subTest(name=name, method=method):
                response = getattr(self.client, method)(reverse(name), data)
                self.assertEqual(response.status_code, 403)
        self.assertFalse(ReminderSetting.objects.exists())

    def test_without_company_is_forbidden(self):
        root = User.objects.create_superuser("ql@quality.test", PASSWORD)
        self.login(root)
        self.assertEqual(
            self.client.get(reverse("wellbeing_reminders")).status_code, 403
        )
        self.assertEqual(
            self.client.get(reverse("wellbeing_reminder_schedule")).status_code, 403
        )

    def test_requires_login_and_csrf(self):
        self.assertEqual(
            self.client.get(reverse("wellbeing_reminders")).status_code, 302
        )
        self.assertEqual(
            self.client.get(reverse("wellbeing_reminder_schedule")).status_code, 302
        )
        csrf_client = self.client_class(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        response = csrf_client.post(reverse("wellbeing_reminders"), VALID)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ReminderSetting.objects.exists())

    # Validation ----------------------------------------------------------------

    def test_values_outside_options_are_rejected(self):
        self.login(self.owner)
        for invalid in (
            {"interval_minutes": "45"},
            {"interval_minutes": "abc"},
            {"weekdays": ["8"]},
            {"weekdays": ["0"]},
            {"weekdays": []},
            {"workday_start": "25:00"},
            {"workday_end": "manhã"},
            {"workday_start": "18:00", "workday_end": "08:00"},
            {
                "workday_start": "09:00",
                "workday_end": "10:00",
                "interval_minutes": "120",
            },
            {"action": "apagar"},
        ):
            with self.subTest(invalid=invalid):
                response = self.client.post(
                    reverse("wellbeing_reminders"), {**VALID, **invalid}
                )
                self.assertEqual(response.status_code, 400)
                self.assertFalse(ReminderSetting.objects.exists())

    def test_database_rejects_invalid_rows(self):
        membership = self.membership(self.owner)
        for invalid in (
            {"interval_minutes": 45},
            {"weekdays": ""},
            {"weekdays": "8"},
            {"weekdays": "531"},
            {"workday_start": time(18), "workday_end": time(8)},
        ):
            with (
                self.subTest(invalid=invalid),
                self.assertRaises(IntegrityError),
                transaction.atomic(),
            ):
                ReminderSetting.objects.create(membership=membership, **invalid)

    def test_get_only_schedule(self):
        self.login(self.owner)
        response = self.client.post(reverse("wellbeing_reminder_schedule"))
        self.assertEqual(response.status_code, 405)
