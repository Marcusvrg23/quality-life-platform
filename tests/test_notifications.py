"""General notification channel (docs/specs/13-pwa-lembretes.md, aceite 15 e 16):
``notify()`` reaches every device of the Membership, respects the person's
preference and the daily limits, never leaves the active tenant and logs only
ids. pywebpush is simulated; no request leaves the test."""

import json
from unittest import mock

from django.test import TestCase, override_settings
from pywebpush import WebPushException

from identity.models import Membership, Organization, User
from wellbeing import notifications
from wellbeing.models import (
    NotificationDelivery,
    NotificationPreference,
    PushSubscription,
)

PASSWORD = "notify-test-password"
VAPID = {
    "VAPID_PUBLIC_KEY": "public-key-for-the-test",
    "VAPID_PRIVATE_KEY": "private-key-for-the-test",
    "VAPID_SUBJECT": "mailto:contato@example.test",
}
NO_VAPID = {"VAPID_PUBLIC_KEY": "", "VAPID_PRIVATE_KEY": "", "VAPID_SUBJECT": ""}
TITLE = "Hora da pausa"
BODY = "Que tal alguns minutos de Ginástica Laboral?"
URL = "/app/ginastica/"


def failure(status):
    response = mock.Mock(status_code=status, text="", headers={})
    return WebPushException("push service refused", response=response)


def failing_only(endpoint, status):
    """A fake webpush that refuses one endpoint and accepts the others."""

    def send(subscription_info, **kwargs):
        if subscription_info["endpoint"] == endpoint:
            raise failure(status)
        return mock.Mock(status_code=201)

    return send


@override_settings(**VAPID)
class NotifyTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Empresa", slug="empresa")
        self.user = User.objects.create_user("maria.souza@empresa.test", PASSWORD)
        self.membership = Membership.objects.create(
            user=self.user,
            organization=self.organization,
            role=Membership.Role.COLLABORATOR,
        )
        self.phone = self.device("https://push.example/phone", "Android")
        self.laptop = self.device("https://push.example/laptop", "Chrome")

    def device(self, endpoint, agent, membership=None):
        return PushSubscription.objects.create(
            membership=membership or self.membership,
            endpoint=endpoint,
            p256dh="p256dh-" + agent,
            auth="auth-" + agent,
            user_agent=agent,
        )

    def notify(self, category="pausas", **overrides):
        with mock.patch.object(notifications, "webpush") as webpush:
            webpush.side_effect = overrides.pop("side_effect", None)
            sent = notifications.notify(
                overrides.pop("membership", self.membership),
                category,
                overrides.pop("title", TITLE),
                overrides.pop("body", BODY),
                overrides.pop("url", URL),
                **overrides,
            )
        return sent, webpush

    # Delivery -------------------------------------------------------------------

    def test_sends_to_every_device_of_the_membership(self):
        sent, webpush = self.notify()
        self.assertEqual(sent, 2)
        self.assertEqual(webpush.call_count, 2)
        endpoints = set()
        for call in webpush.call_args_list:
            info = call.kwargs["subscription_info"]
            endpoints.add(info["endpoint"])
            self.assertEqual(set(info["keys"]), {"p256dh", "auth"})
            self.assertEqual(
                json.loads(call.kwargs["data"]),
                {"title": TITLE, "body": BODY, "url": URL, "tag": "ql-pausas"},
            )
            self.assertEqual(
                call.kwargs["vapid_private_key"], "private-key-for-the-test"
            )
            self.assertEqual(
                call.kwargs["vapid_claims"], {"sub": "mailto:contato@example.test"}
            )
        self.assertEqual(endpoints, {self.phone.endpoint, self.laptop.endpoint})
        delivery = NotificationDelivery.objects.get()
        self.assertEqual(delivery.membership, self.membership)
        self.assertEqual(delivery.category, "pausas")
        self.assertEqual(delivery.devices, 2)
        self.phone.refresh_from_db()
        self.assertIsNotNone(self.phone.last_success_at)

    def test_other_memberships_devices_are_never_reached(self):
        other_org = Organization.objects.create(name="Outra", slug="outra")
        colleague = Membership.objects.create(
            user=User.objects.create_user("colega@empresa.test", PASSWORD),
            organization=self.organization,
            role=Membership.Role.COLLABORATOR,
        )
        same_person_elsewhere = Membership.objects.create(
            user=self.user, organization=other_org, role=Membership.Role.COLLABORATOR
        )
        self.device("https://push.example/colleague", "C", colleague)
        self.device("https://push.example/elsewhere", "E", same_person_elsewhere)
        sent, webpush = self.notify()
        self.assertEqual(sent, 2)
        reached = {
            call.kwargs["subscription_info"]["endpoint"]
            for call in webpush.call_args_list
        }
        self.assertEqual(reached, {self.phone.endpoint, self.laptop.endpoint})

    def test_without_devices_sends_nothing_and_records_nothing(self):
        PushSubscription.objects.all().delete()
        sent, webpush = self.notify()
        self.assertEqual(sent, 0)
        webpush.assert_not_called()
        self.assertFalse(NotificationDelivery.objects.exists())

    # Preference and limits ------------------------------------------------------

    def test_disabled_category_sends_nothing(self):
        NotificationPreference.objects.create(membership=self.membership, dicas=False)
        sent, webpush = self.notify("dicas", title="Dica do dia", body="Alongue-se.")
        self.assertEqual(sent, 0)
        webpush.assert_not_called()
        # The other category still works.
        sent, webpush = self.notify("pausas")
        self.assertEqual(sent, 2)
        NotificationPreference.objects.filter(membership=self.membership).update(
            pausas=False
        )
        sent, webpush = self.notify("pausas")
        self.assertEqual(sent, 0)
        webpush.assert_not_called()

    def test_tips_have_no_daily_limit(self):
        # Paced by each person's own interval (spec 17, aceite 5).
        for body in ("Beba água.", "Respire fundo.", "Alongue-se."):
            sent, _ = self.notify("dicas", title="Dica", body=body)
            self.assertEqual(sent, 2)
        self.assertEqual(
            NotificationDelivery.objects.filter(category="dicas").count(), 3
        )

    def test_breaks_have_no_daily_limit(self):
        for _ in range(3):
            sent, _ = self.notify("pausas")
            self.assertEqual(sent, 2)

    # Tenant and account state ---------------------------------------------------

    def test_inactive_membership_or_organization_sends_nothing(self):
        Membership.objects.filter(pk=self.membership.pk).update(is_active=False)
        self.membership.refresh_from_db()
        sent, webpush = self.notify()
        self.assertEqual(sent, 0)
        webpush.assert_not_called()
        Membership.objects.filter(pk=self.membership.pk).update(is_active=True)
        Organization.objects.filter(pk=self.organization.pk).update(is_active=False)
        self.membership = Membership.objects.get(pk=self.membership.pk)
        sent, webpush = self.notify()
        self.assertEqual(sent, 0)
        webpush.assert_not_called()
        self.assertFalse(NotificationDelivery.objects.exists())

    # Expired devices and failures -----------------------------------------------

    def test_expired_subscription_is_deleted(self):
        for status in (404, 410):
            with self.subTest(status=status):
                gone = self.device(f"https://push.example/gone-{status}", "Old")
                sent, _ = self.notify(side_effect=failing_only(gone.endpoint, status))
                self.assertEqual(sent, 2)
                self.assertFalse(PushSubscription.objects.filter(pk=gone.pk).exists())
        self.assertEqual(PushSubscription.objects.count(), 2)

    def test_other_failures_keep_the_subscription(self):
        sent, _ = self.notify(side_effect=failure(500))
        self.assertEqual(sent, 0)
        self.assertEqual(PushSubscription.objects.count(), 2)
        self.assertFalse(NotificationDelivery.objects.exists())
        sent, _ = self.notify(side_effect=OSError("network down"))
        self.assertEqual(sent, 0)
        self.assertEqual(PushSubscription.objects.count(), 2)

    # Content and configuration --------------------------------------------------

    def test_text_must_be_generic(self):
        for title, body in (
            ("Maria, hora da pausa", BODY),
            (TITLE, "Sua nota subiu para 82"),
            (TITLE, "Olá maria.souza@empresa.test"),
            (TITLE, "Seu pilar Sono está baixo"),
            ("Resultado da avaliação", BODY),
        ):
            with (
                self.subTest(title=title, body=body),
                self.assertRaises(notifications.NotGeneric),
            ):
                self.notify(title=title, body=body)
        for url in ("https://outro.site/x", "//outro.site/x", "app/ginastica/"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.notify(url=url)
        with self.assertRaises(ValueError):
            self.notify("promocoes")
        self.assertFalse(NotificationDelivery.objects.exists())

    @override_settings(**NO_VAPID)
    def test_without_vapid_nothing_is_sent_and_nothing_breaks(self):
        self.assertFalse(notifications.push_configured())
        sent, webpush = self.notify()
        self.assertEqual(sent, 0)
        webpush.assert_not_called()
        self.assertFalse(NotificationDelivery.objects.exists())
        self.assertEqual(PushSubscription.objects.count(), 2)

    def test_logs_carry_ids_and_counts_only(self):
        with self.assertLogs("wellbeing.notifications", level="INFO") as logs:
            self.notify()
            self.notify(side_effect=failure(410))
        output = "\n".join(logs.output)
        self.assertIn(f"membership={self.membership.pk}", output)
        self.assertIn("devices=2", output)
        self.assertNotIn("maria", output.lower())
        self.assertNotIn("@", output)
        self.assertNotIn(TITLE, output)
