from django.urls import path

from apps.experts import views

urlpatterns = [
    path("ask", views.ask, name="ask"),
    path("ask/stream", views.ask_stream, name="ask_stream"),
]
