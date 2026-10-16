from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
]

if settings.ENABLE_RAW_ASK:
    urlpatterns.append(path("v1/", include("apps.experts.urls")))
