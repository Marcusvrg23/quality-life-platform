"""Wellbeing pages under /app/ (docs/specs/11-bem-estar.md)."""

from django.urls import path

from . import views

urlpatterns = [
    path("ginastica/", views.gym, name="wellbeing_gym"),
    path("meditacao/", views.meditation, name="wellbeing_meditation"),
    path("relaxamento/", views.relax, name="wellbeing_relax"),
    path("progresso/", views.progress, name="wellbeing_progress"),
    path("pratica/registrar/", views.record, name="wellbeing_record"),
]
