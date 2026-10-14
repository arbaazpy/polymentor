from django.urls import path

from apps.core import views

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
]
