"""Push subscriptions per device and notification preferences
(docs/specs/13-pwa-lembretes.md, aceite 12): only the owner subscribes,
cancels and changes preferences; a forged tenant is 403."""

import json

from django.test import TestCase, override_settings
from django.urls import reverse

from config.tenant import SESSION_ORGANIZATION_KEY
from identity.models import Membership, Organization, User
from wellbeing.models import NotificationPreference, PushSubscription

PASSWORD = "push-test-password"
SUBSCRIPTION = {
    "endpoint": "https://push.example.test/send/abc123",
    "keys": {"p256dh": "BPubKeyForTheTest", "auth": "authSecretForTheTest"},
}


class PushEndpointTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Empresa", slug="empresa")
        self.other_org = Organization.objects.create(name="Outra", slug="outra")
        self.owner = self.member("dono@empresa.test")
        self.colleague = self.member("colega@empresa.test")

    def member(self, email, organization=None):
        user = User.objects.create_user(email, PASSWORD)
        Membership.objects.create(
            user=user,
            organization=organization or self.organization,
            role=Membership.Role.COLLABORATOR,
        )
        return user

    def login(self, user, organization=None):
        self.client.force_login(user)
        if organization is not None:
            session = self.client.session
            session[SESSION_ORGANIZATION_KEY] = organization.pk
            session.save()

    def membership(self, user, organization=None):
        return Membership.objects.get(
            user=user, organization=organization or self.organization
        )

    def post_json(self, name, payload, client=None, **extra):
        headers = {
            "HTTP_USER_AGENT": "Mozilla/5.0 (Linux; Android 14) Chrome/130 Mobile",
            **extra,
        }
        return (client or self.client).post(
            reverse(name),
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def subscribe(self, payload=SUBSCRIPTION, **extra):
        return self.post_json("wellbeing_push_subscribe", payload, **extra)

    def unsubscribe(self, endpoint=SUBSCRIPTION["endpoint"], **extra):
        return self.post_json(
            "wellbeing_push_unsubscribe", {"endpoint": endpoint}, **extra
        )

    def status(self, endpoint=SUBSCRIPTION["endpoint"]):
        return self.post_json("wellbeing_push_status", {"endpoint": endpoint})

    # Subscribe -------------------------------------------------------------------

    def test_owner_subscribes_device(self):
        self.login(self.owner)
        response = self.subscribe()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"status": "subscribed"})
        self.assertEqual(response["Cache-Control"], "no-store, private")
        subscription = PushSubscription.objects.get()
        self.assertEqual(subscription.membership, self.membership(self.owner))
        self.assertEqual(subscription.endpoint, SUBSCRIPTION["endpoint"])
        self.assertEqual(subscription.p256dh, "BPubKeyForTheTest")
        self.assertEqual(subscription.auth, "authSecretForTheTest")
        self.assertEqual(
            subscription.user_agent, "Mozilla/5.0 (Linux; Android 14) Chrome/130 Mobile"
        )
        self.assertIsNone(subscription.last_success_at)

    def test_same_device_again_updates_keys_without_duplicating(self):
        self.login(self.owner)
        self.subscribe()
        renewed = {**SUBSCRIPTION, "keys": {"p256dh": "BNewKey", "auth": "newAuth"}}
        response = self.subscribe(renewed, HTTP_USER_AGENT="x" * 300)
        self.assertEqual(response.status_code, 200)
        subscription = PushSubscription.objects.get()
        self.assertEqual(subscription.p256dh, "BNewKey")
        self.assertEqual(subscription.auth, "newAuth")
        self.assertEqual(len(subscription.user_agent), 120)

    def test_same_device_keeps_one_row_per_account(self):
        # Spec 13, aceite 23: turning one account off never touches the other.
        self.login(self.owner)
        self.subscribe()
        self.login(self.colleague)
        self.subscribe()
        self.assertEqual(
            set(PushSubscription.objects.values_list("membership", flat=True)),
            {self.membership(self.owner).pk, self.membership(self.colleague).pk},
        )
        self.assertEqual(self.unsubscribe().status_code, 200)
        self.assertEqual(
            PushSubscription.objects.get().membership, self.membership(self.owner)
        )
        self.login(self.owner)
        self.assertEqual(self.status().json(), {"registered": True})
        self.login(self.colleague)
        self.assertEqual(self.status().json(), {"registered": False})

    def test_subscribing_creates_the_agenda_with_defaults(self):
        self.login(self.owner)
        self.subscribe()
        setting = self.membership(self.owner).reminder_setting
        self.assertFalse(setting.active)
        self.assertEqual(setting.tips_interval_minutes, 60)

    def test_status_is_own_post_only_and_needs_an_endpoint(self):
        self.login(self.owner)
        self.assertEqual(self.status().json(), {"registered": False})
        self.assertEqual(self.status().status_code, 200)
        self.assertEqual(self.status()["Cache-Control"], "no-store, private")
        self.assertEqual(self.post_json("wellbeing_push_status", {}).status_code, 400)
        self.assertEqual(
            self.client.get(reverse("wellbeing_push_status")).status_code, 405
        )
        self.client.logout()
        self.assertEqual(self.status().status_code, 302)

    def test_same_person_has_separate_devices_per_company(self):
        Membership.objects.create(
            user=self.owner,
            organization=self.other_org,
            role=Membership.Role.COLLABORATOR,
        )
        self.login(self.owner, self.organization)
        self.subscribe()
        self.login(self.owner, self.other_org)
        self.subscribe(
            {**SUBSCRIPTION, "endpoint": "https://push.example.test/send/other"}
        )
        self.assertEqual(
            set(
                PushSubscription.objects.values_list(
                    "membership__organization", flat=True
                )
            ),
            {self.organization.pk, self.other_org.pk},
        )

    def test_client_cannot_choose_membership(self):
        self.login(self.colleague)
        owner_membership = self.membership(self.owner)
        self.subscribe({**SUBSCRIPTION, "membership": owner_membership.pk})
        self.assertEqual(
            PushSubscription.objects.get().membership, self.membership(self.colleague)
        )

    def test_invalid_payloads_are_refused(self):
        self.login(self.owner)
        for payload in (
            {},
            {"endpoint": "http://insecure.example/x", "keys": SUBSCRIPTION["keys"]},
            {"endpoint": "not a url", "keys": SUBSCRIPTION["keys"]},
            {
                "endpoint": "https://p.example/" + "a" * 1000,
                "keys": SUBSCRIPTION["keys"],
            },
            {"endpoint": SUBSCRIPTION["endpoint"], "keys": {"p256dh": "only"}},
            {"endpoint": SUBSCRIPTION["endpoint"], "keys": {"p256dh": "", "auth": "a"}},
            {"endpoint": SUBSCRIPTION["endpoint"], "keys": "nope"},
            [SUBSCRIPTION],
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.subscribe(payload).status_code, 400)
        response = self.client.post(
            reverse("wellbeing_push_subscribe"),
            data="{bad",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PushSubscription.objects.exists())

    # Unsubscribe -----------------------------------------------------------------

    def test_owner_cancels_own_device_only(self):
        self.login(self.owner)
        self.subscribe()
        self.login(self.colleague)
        self.subscribe(
            {**SUBSCRIPTION, "endpoint": "https://push.example.test/send/colleague"}
        )
        # The colleague cannot remove the owner's device.
        response = self.unsubscribe()
        self.assertEqual(response.status_code, 404)
        self.assertEqual(PushSubscription.objects.count(), 2)
        self.login(self.owner)
        response = self.unsubscribe()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "unsubscribed"})
        self.assertEqual(
            PushSubscription.objects.get().membership, self.membership(self.colleague)
        )
        self.assertEqual(self.unsubscribe().status_code, 404)
        self.assertEqual(self.unsubscribe("").status_code, 400)

    # Authorization ---------------------------------------------------------------

    def test_forged_tenant_is_forbidden(self):
        for name, payload in (
            ("wellbeing_push_subscribe", SUBSCRIPTION),
            ("wellbeing_push_unsubscribe", {"endpoint": SUBSCRIPTION["endpoint"]}),
        ):
            self.login(self.owner, self.other_org)
            with self.subTest(name=name):
                self.assertEqual(self.post_json(name, payload).status_code, 403)
        self.login(self.owner, self.other_org)
        response = self.client.post(
            reverse("wellbeing_notification_preferences"), {"pausas": "on"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(PushSubscription.objects.exists())
        self.assertFalse(NotificationPreference.objects.exists())

    def test_without_company_is_forbidden(self):
        root = User.objects.create_superuser("ql@quality.test", PASSWORD)
        self.login(root)
        self.assertEqual(self.subscribe().status_code, 403)
        self.assertEqual(self.unsubscribe().status_code, 403)

    def test_requires_login_csrf_and_post(self):
        self.assertEqual(self.subscribe().status_code, 302)
        self.assertEqual(self.unsubscribe().status_code, 302)
        csrf_client = self.client_class(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        self.assertEqual(self.subscribe(client=csrf_client).status_code, 403)
        self.assertEqual(self.unsubscribe(client=csrf_client).status_code, 403)
        self.assertEqual(
            csrf_client.post(
                reverse("wellbeing_notification_preferences"), {"pausas": "on"}
            ).status_code,
            403,
        )
        self.login(self.owner)
        for name in (
            "wellbeing_push_subscribe",
            "wellbeing_push_unsubscribe",
            "wellbeing_notification_preferences",
        ):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 405)
        self.assertFalse(PushSubscription.objects.exists())

    # Preferences -----------------------------------------------------------------

    def test_preferences_default_on_and_only_owner_changes(self):
        self.login(self.owner)
        page = self.client.get(reverse("wellbeing_reminders"))
        self.assertContains(page, "Lembretes de pausa")
        self.assertContains(page, "Dicas e datas especiais")
        self.assertContains(page, 'name="pausas" checked')
        self.assertContains(page, 'name="dicas" checked')
        self.assertFalse(NotificationPreference.objects.exists())
        response = self.client.post(
            reverse("wellbeing_notification_preferences"), {"pausas": "on"}
        )
        # assertRedirects would fetch the page and consume the message.
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("wellbeing_reminders"))
        preference = NotificationPreference.objects.get()
        self.assertEqual(preference.membership, self.membership(self.owner))
        self.assertTrue(preference.pausas)
        self.assertFalse(preference.dicas)
        page = self.client.get(reverse("wellbeing_reminders"))
        self.assertContains(page, "Preferências salvas.")
        self.assertContains(page, 'name="pausas" checked')
        self.assertNotContains(page, 'name="dicas" checked')
        # The colleague's own page and POST never touch the owner's row.
        self.login(self.colleague)
        self.assertContains(
            self.client.get(reverse("wellbeing_reminders")), 'name="dicas" checked'
        )
        self.client.post(reverse("wellbeing_notification_preferences"), {})
        preference.refresh_from_db()
        self.assertTrue(preference.pausas)
        self.assertEqual(NotificationPreference.objects.count(), 2)

    # Agenda ----------------------------------------------------------------------

    def test_agenda_tells_whether_the_server_can_push(self):
        self.login(self.owner)
        self.assertIsNone(
            self.client.get(reverse("wellbeing_reminder_schedule")).json()["push_key"]
        )
        with override_settings(
            VAPID_PUBLIC_KEY="BPublicKeyForTheTest",
            VAPID_PRIVATE_KEY="private",
            VAPID_SUBJECT="mailto:contato@example.test",
        ):
            agenda = self.client.get(reverse("wellbeing_reminder_schedule")).json()
        self.assertEqual(agenda["push_key"], "BPublicKeyForTheTest")
        self.assertNotIn("private", json.dumps(agenda))
