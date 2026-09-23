"""Employee assessment pages."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.hub, name="assessment_hub"),
    path("start/", views.start, name="assessment_start"),
    path("<int:assessment_id>/", views.detail, name="assessment_detail"),
    path(
        "<int:assessment_id>/question/<int:question_id>/",
        views.question,
        name="assessment_question",
    ),
    path("<int:assessment_id>/review/", views.review, name="assessment_review"),
    path("<int:assessment_id>/complete/", views.complete, name="assessment_complete"),
    path(
        "<int:assessment_id>/completed/", views.completed, name="assessment_completed"
    ),
]
