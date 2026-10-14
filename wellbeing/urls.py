"""Wellbeing pages under /app/ (docs/specs/11-bem-estar.md)."""

from django.urls import path

from . import views

urlpatterns = [
    path("pratica/registrar/", views.record, name="wellbeing_record"),
]
