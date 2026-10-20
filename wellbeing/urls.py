"""Wellbeing pages under /app/ (docs/specs/11-bem-estar.md, 13-pwa-lembretes.md)."""

from django.urls import path

from . import assistant_views, views

urlpatterns = [
    path("assistente/", assistant_views.assistant_page, name="wellbeing_assistant"),
    path(
        "assistente/mensagem/",
        assistant_views.assistant_message,
        name="wellbeing_assistant_message",
    ),
    path("ginastica/", views.gym, name="wellbeing_gym"),
    path("meditacao/", views.meditation, name="wellbeing_meditation"),
    path("relaxamento/", views.relax, name="wellbeing_relax"),
    path("progresso/", views.progress, name="wellbeing_progress"),
    path("pratica/registrar/", views.record, name="wellbeing_record"),
    path("lembretes/", views.reminders, name="wellbeing_reminders"),
    path(
        "lembretes/agenda/",
        views.reminder_schedule,
        name="wellbeing_reminder_schedule",
    ),
    path(
        "lembretes/push/inscrever/",
        views.push_subscribe,
        name="wellbeing_push_subscribe",
    ),
    path(
        "lembretes/push/estado/",
        views.push_status,
        name="wellbeing_push_status",
    ),
    path(
        "lembretes/push/cancelar/",
        views.push_unsubscribe,
        name="wellbeing_push_unsubscribe",
    ),
    path(
        "lembretes/push/teste/",
        views.push_test,
        name="wellbeing_push_test",
    ),
    path(
        "lembretes/notificacoes/",
        views.notification_preferences,
        name="wellbeing_notification_preferences",
    ),
]
