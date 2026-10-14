from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/django/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("v1/", include("apps.experts.urls")),
]
