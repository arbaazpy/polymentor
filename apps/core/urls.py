from django.urls import path

from apps.aggregation import views as turn_views
from apps.core import pages, views

urlpatterns = [
    path("", pages.home, name="home"),
    path("t/<uuid:turn_id>", pages.turn_detail, name="turn_detail"),
    path("experts", pages.experts, name="experts"),
    path("healthz", views.healthz, name="healthz"),
    path("v1/turns/stream", turn_views.turn_stream, name="turn_stream"),
    path("v1/turns/<uuid:turn_id>/feedback", turn_views.turn_feedback, name="turn_feedback"),
    path("v1/admin/mine", turn_views.admin_mine, name="admin_mine"),
]
