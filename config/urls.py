"""Root URL configuration for the Django foundation."""

from django.urls import path

from .views import foundation, health

urlpatterns = [
    path("", foundation, name="foundation"),
    path("health/", health, name="health"),
]
