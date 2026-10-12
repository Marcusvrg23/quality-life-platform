"""Corporate manager report pages."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.executive_report, name="executive_report"),
]
