"""Print a fresh VAPID key pair as environment variables (spec 13).

Nothing is written to disk: the output goes into the hosting panel (Square
Cloud) and never into the repository. Changing the pair invalidates every
device subscription; devices subscribe again on their next visit to the
reminders screen.
"""

from cryptography.hazmat.primitives import serialization
from django.core.management.base import BaseCommand
from py_vapid import Vapid, b64urlencode


def key_pair():
    """(public, private) in the base64url form PushManager and pywebpush use."""
    vapid = Vapid()
    vapid.generate_keys()
    public = b64urlencode(
        vapid.public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
    )
    private = b64urlencode(
        vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    )
    return public, private


class Command(BaseCommand):
    help = (
        "Generate the VAPID key pair for Web Push and print the environment "
        "variables to configure; nothing is saved."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--subject",
            default="contato@example.com",
            help="Contact e-mail for VAPID_SUBJECT (mailto:).",
        )

    def handle(self, *args, **options):
        public, private = key_pair()
        self.stdout.write(f"VAPID_PUBLIC_KEY={public}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={private}")
        self.stdout.write(f"VAPID_SUBJECT=mailto:{options['subject']}")
        self.stderr.write(
            "Cole as três variáveis no ambiente da hospedagem e reinicie o app. "
            "Não guarde a chave privada no repositório nem em mensagens."
        )
