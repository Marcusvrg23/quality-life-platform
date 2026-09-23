# ruff: noqa: RUF012 - Django migration metadata convention.

from django.db import migrations

PILLARS = (
    ("physical_health", "Saúde Física"),
    ("preventive_behavior", "Comportamento Preventivo"),
    ("physical_activity", "Atividade Física"),
    ("nutrition_hydration", "Alimentação e Hidratação"),
    ("relationships", "Relacionamentos"),
    ("mental_emotional_health", "Saúde Mental e Emocional"),
    ("ergonomics_workplace", "Ergonomia e Ambiente de Trabalho"),
    ("sleep_recovery", "Sono e Recuperação"),
    ("work_life_balance", "Equilíbrio Vida × Trabalho"),
)


def create_pillars(apps, schema_editor):
    Pillar = apps.get_model("assessments", "Pillar")
    for order, (code, name) in enumerate(PILLARS, start=1):
        Pillar.objects.create(code=code, name=name, display_order=order)


def remove_pillars(apps, schema_editor):
    Pillar = apps.get_model("assessments", "Pillar")
    Pillar.objects.filter(code__in=[code for code, _ in PILLARS]).delete()


class Migration(migrations.Migration):
    dependencies = [("assessments", "0001_initial")]
    operations = [migrations.RunPython(create_pillars, remove_pillars)]
