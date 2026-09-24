"""Seed only the isolated, explicitly enabled demonstration dataset."""

import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from assessments.models import (
    Pillar,
    Question,
    QuestionnairePillar,
    QuestionnaireVersion,
    QuestionOption,
)
from assessments.services import publish_questionnaire, validate_questionnaire
from identity.models import Membership, Organization

DEMO_SLUG = "quality-life-demonstracao"
DEMO_NAME = "Quality Life — Demonstração"
DEMO_CODE = "quality-life-demo-nao-oficial"
DEMO_TITLE = "DEMONSTRAÇÃO — NÃO É QUESTIONÁRIO OFICIAL"
DEMO_EMAILS = tuple(f"demo{i}@example.com" for i in range(1, 4))
DEMO_QUESTIONS = {
    "physical_health": "Como você percebeu seu bem-estar físico recentemente?",
    "preventive_behavior": "Com que frequência você reservou tempo para cuidados preventivos?",
    "physical_activity": "Com que frequência você incluiu movimento em sua rotina?",
    "nutrition_hydration": "Com que frequência você cuidou da alimentação e hidratação?",
    "relationships": "Com que frequência você teve interações positivas com outras pessoas?",
    "mental_emotional_health": "Com que frequência você encontrou espaço para cuidar das emoções?",
    "ergonomics_workplace": "Com que frequência seu espaço de trabalho favoreceu o conforto?",
    "sleep_recovery": "Com que frequência você teve descanso suficiente?",
    "work_life_balance": "Com que frequência você conseguiu equilibrar trabalho e vida pessoal?",
}
DEMO_OPTIONS = (
    ("nunca", "Nunca", 0),
    ("raramente", "Raramente", 25),
    ("as-vezes", "Às vezes", 50),
    ("frequentemente", "Frequentemente", 75),
    ("sempre", "Sempre", 100),
)


class Command(BaseCommand):
    help = "Create the isolated, explicitly enabled Quality Life demonstration data."

    def handle(self, *args, **options):
        if (
            os.environ.get("QUALITY_LIFE_DEMO_SEED_ENABLED", "").strip().lower()
            != "true"
        ):
            raise CommandError("QUALITY_LIFE_DEMO_SEED_ENABLED=true is required.")

        password = os.environ.get("QUALITY_LIFE_DEMO_PASSWORD", "")
        if not password:
            raise CommandError("QUALITY_LIFE_DEMO_PASSWORD is required.")
        try:
            for email in DEMO_EMAILS:
                validate_password(password, user=get_user_model()(email=email))
        except ValidationError as exc:
            raise CommandError("QUALITY_LIFE_DEMO_PASSWORD is invalid.") from exc

        with transaction.atomic():
            self._seed(password)
        self.stdout.write(self.style.SUCCESS("Demo data ready."))

    def _seed(self, password):
        pillars = list(Pillar.objects.order_by("display_order"))
        if (
            len(pillars) != 9
            or {pillar.code for pillar in pillars} != set(DEMO_QUESTIONS)
            or any(not pillar.is_active for pillar in pillars)
        ):
            raise CommandError("Exactly the nine active approved pillars are required.")

        organization = Organization.objects.filter(slug=DEMO_SLUG).first()
        if organization:
            if organization.name != DEMO_NAME or not organization.is_active:
                raise CommandError("Demo organization slug is already in use.")
        else:
            organization = Organization.objects.create(name=DEMO_NAME, slug=DEMO_SLUG)

        questionnaire = QuestionnaireVersion.objects.filter(
            code=DEMO_CODE, version=1
        ).first()
        if questionnaire:
            if (
                questionnaire.title != DEMO_TITLE
                or questionnaire.scoring_version != "v1"
                or questionnaire.status != QuestionnaireVersion.Status.PUBLISHED
                or questionnaire.pillars.count() != 9
                or Question.objects.filter(
                    questionnaire_pillar__questionnaire=questionnaire
                ).count()
                != 9
                or QuestionOption.objects.filter(
                    question__questionnaire_pillar__questionnaire=questionnaire
                ).count()
                != 45
            ):
                raise CommandError(
                    "Existing demo questionnaire does not match the seed."
                )
            validate_questionnaire(questionnaire)
        else:
            questionnaire = QuestionnaireVersion.objects.create(
                code=DEMO_CODE,
                version=1,
                title=DEMO_TITLE,
                scoring_version="v1",
            )
            for pillar in pillars:
                configured = QuestionnairePillar.objects.create(
                    questionnaire=questionnaire,
                    pillar=pillar,
                    display_order=pillar.display_order,
                    weight=1,
                )
                question = Question.objects.create(
                    questionnaire_pillar=configured,
                    code=f"demo-{pillar.code}",
                    text=f"DEMO — {DEMO_QUESTIONS[pillar.code]}",
                    display_order=1,
                    weight=1,
                )
                for order, (code, label, score) in enumerate(DEMO_OPTIONS, start=1):
                    QuestionOption.objects.create(
                        question=question,
                        code=code,
                        label=label,
                        score_value=score,
                        display_order=order,
                    )
            publish_questionnaire(questionnaire.pk)

        User = get_user_model()
        for email in DEMO_EMAILS:
            user = User.objects.filter(email__iexact=email).first()
            if user:
                membership = Membership.objects.filter(
                    user=user, organization=organization
                ).first()
                if (
                    not membership
                    or membership.role != Membership.Role.COLLABORATOR
                    or not membership.is_active
                    or not user.is_active
                    or user.is_staff
                    or user.is_superuser
                    or not user.check_password(password)
                    or Membership.objects.filter(user=user)
                    .exclude(organization=organization)
                    .exists()
                ):
                    raise CommandError(
                        "A reserved demo email belongs to another account."
                    )
            else:
                user = User.objects.create_user(email=email, password=password)
                Membership.objects.create(
                    user=user,
                    organization=organization,
                    role=Membership.Role.COLLABORATOR,
                )
        if Membership.objects.filter(organization=organization).count() != 3:
            raise CommandError("Demo organization has unexpected memberships.")
