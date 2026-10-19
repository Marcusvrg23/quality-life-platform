"""'Enviar notificação de teste' on Lembretes (docs/specs/13-pwa-lembretes.md,
aceite 20): one generic push to the caller's own devices, now; clear messages
when the server has no keys or the person has no device. pywebpush is
simulated."""

import json
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from config.tenant import SESSION_ORGANIZATION_KEY
from identity.models import Membership, Organization, User
from wellbeing import notifications
from wellbeing.models import NotificationPreference, PushSubscription

PASSWORD = "push-test-password-20"
VAPID = {
    "VAPID_PUBLIC_KEY": "public-key-for-the-test",
    "VAPID_PRIVATE_KEY": "private-key-for-the-test",
    "VAPID_SUBJECT": "mailto:contato@example.test",
}
NO_VAPID = {"VAPID_PUBLIC_KEY": "", "VAPID_PRIVATE_KEY": "", "VAPID_SUBJECT": ""}
URL = "/app/lembretes/push/teste/"


def member(email, organization):
    user = User.objects.create_user(email, PASSWORD)
    return Membership.objects.create(
        user=user, organization=organization, role=Membership.Role.COLLABORATOR
    )


def device(membership, name="a"):
    return PushSubscription.objects.create(
        membership=membership,
        endpoint=f"https://push.example.test/{membership.pk}-{name}",
        p256dh="p256dh",
        auth="auth",
    )


class PushTestButtonTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.organization = Organization.objects.create(
            name="Empresa", slug="empresa-20"
        )
        self.membership = member("pessoa@empresa.test", self.organization)
        self.client.force_login(self.membership.user)
        patcher = mock.patch.object(notifications, "webpush")
        self.webpush = patcher.start()
        self.addCleanup(patcher.stop)

    def post(self):
        return self.client.post(URL, follow=True)

    def test_route_login_and_method(self):
        self.assertEqual(reverse("wellbeing_push_test"), URL)
        self.assertEqual(self.client.get(URL).status_code, 405)
        self.client.logout()
        response = self.client.post(URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_reminders_page_has_the_button(self):
        response = self.client.get(reverse("wellbeing_reminders"))
        self.assertContains(response, f'action="{URL}"')
        self.assertContains(response, "Enviar notificação de teste")

    @override_settings(**NO_VAPID)
    def test_server_without_keys_says_so_and_sends_nothing(self):
        device(self.membership)
        response = self.post()
        self.assertContains(response, "Este servidor ainda não envia notificações")
        self.webpush.assert_not_called()

    @override_settings(**VAPID)
    def test_without_a_device_asks_to_activate_first(self):
        response = self.post()
        self.assertContains(
            response, "Nenhum aparelho recebendo notificações nesta conta."
        )
        self.webpush.assert_not_called()

    @override_settings(**VAPID)
    def test_sends_a_generic_test_to_every_own_device_only(self):
        device(self.membership, "celular")
        device(self.membership, "notebook")
        device(member("outra@empresa.test", self.organization))
        response = self.post()
        self.assertContains(response, "Notificação de teste enviada para 2 aparelhos.")
        self.assertEqual(self.webpush.call_count, 2)
        endpoints = {
            call.kwargs["subscription_info"]["endpoint"]
            for call in self.webpush.call_args_list
        }
        self.assertEqual(
            endpoints,
            {
                f"https://push.example.test/{self.membership.pk}-celular",
                f"https://push.example.test/{self.membership.pk}-notebook",
            },
        )
        payload = json.loads(self.webpush.call_args.kwargs["data"])
        self.assertEqual(payload["title"], "Teste da Quality Life")
        self.assertEqual(
            payload["body"],
            "Se você está vendo isto, as notificações estão funcionando.",
        )
        self.assertEqual(payload["url"], reverse("wellbeing_reminders"))

    @override_settings(**VAPID)
    def test_one_test_per_minute(self):
        device(self.membership)
        self.post()
        response = self.post()
        self.assertContains(response, "Teste enviado há pouco. Aguarde um minuto.")
        self.assertEqual(self.webpush.call_count, 1)

    @override_settings(**VAPID)
    def test_breaks_turned_off_explains_why_nothing_arrived(self):
        device(self.membership)
        NotificationPreference.objects.create(membership=self.membership, pausas=False)
        response = self.post()
        self.assertContains(response, "A notificação não foi entregue.")
        self.webpush.assert_not_called()

    @override_settings(**VAPID)
    def test_forged_tenant_is_forbidden(self):
        device(self.membership)
        other = Organization.objects.create(name="Outra", slug="outra-20")
        session = self.client.session
        session[SESSION_ORGANIZATION_KEY] = other.pk
        session.save()
        self.assertEqual(self.client.post(URL).status_code, 403)
        self.webpush.assert_not_called()
