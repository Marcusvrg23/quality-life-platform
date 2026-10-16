"""The VAPID key command prints a usable pair and never writes a file (spec 13)."""

import base64
import os
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase
from py_vapid import Vapid

from wellbeing.management.commands.generate_vapid_keys import key_pair


def decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class GenerateVapidKeysTests(SimpleTestCase):
    def test_prints_environment_variables_for_a_valid_pair(self):
        before = set(os.listdir("."))
        out, err = StringIO(), StringIO()
        call_command(
            "generate_vapid_keys",
            subject="contato@quality.test",
            stdout=out,
            stderr=err,
        )
        lines = dict(line.split("=", 1) for line in out.getvalue().split())
        self.assertEqual(
            set(lines), {"VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_SUBJECT"}
        )
        self.assertEqual(lines["VAPID_SUBJECT"], "mailto:contato@quality.test")
        public = decode(lines["VAPID_PUBLIC_KEY"])
        self.assertEqual(len(public), 65)
        self.assertEqual(public[0], 0x04)
        self.assertEqual(len(decode(lines["VAPID_PRIVATE_KEY"])), 32)
        # pywebpush reads the private key in this form and derives the same public key.
        vapid = Vapid.from_string(private_key=lines["VAPID_PRIVATE_KEY"])
        self.assertEqual(
            vapid.public_key.public_numbers().x,
            int.from_bytes(public[1:33], "big"),
        )
        self.assertIn("Não guarde a chave privada", err.getvalue())
        self.assertEqual(set(os.listdir(".")), before)

    def test_every_run_is_a_new_pair(self):
        self.assertNotEqual(key_pair(), key_pair())
