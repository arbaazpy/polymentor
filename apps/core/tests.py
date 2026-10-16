"""Deployment-shape tests: health probe, HTTPS-only cookies, admin login."""

from __future__ import annotations

import re

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

PROD = {
    "DEBUG": False,
    "ALLOWED_HOSTS": ["polymentor.onrender.com"],
    "CSRF_TRUSTED_ORIGINS": ["https://polymentor.onrender.com"],
    "SECURE_PROXY_SSL_HEADER": ("HTTP_X_FORWARDED_PROTO", "https"),
    "SECURE_SSL_REDIRECT": True,
    "SESSION_COOKIE_SECURE": True,
    "CSRF_COOKIE_SECURE": True,
}
HTTPS = {"HTTP_HOST": "polymentor.onrender.com", "HTTP_X_FORWARDED_PROTO": "https"}


@pytest.mark.django_db
@override_settings(**PROD)
def test_healthz_bypasses_host_validation_and_https_redirect():
    resp = Client().get("/healthz", HTTP_HOST="10.0.0.7:10000")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.django_db
@override_settings(**PROD)
def test_plain_http_redirects_and_unknown_host_is_rejected():
    assert Client().get("/", HTTP_HOST="polymentor.onrender.com").status_code == 301
    assert Client().get("/", HTTP_HOST="evil.example").status_code == 400


@pytest.mark.django_db
@override_settings(**PROD)
def test_admin_login_over_https_with_csrf():
    get_user_model().objects.create_superuser("admin", "a@example.com", "TestPass-123")
    client = Client(enforce_csrf_checks=True)
    page = client.get("/admin/login/", **HTTPS)
    assert page.status_code == 200
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode())[1]
    resp = client.post(
        "/admin/login/?next=/admin/",
        {"username": "admin", "password": "TestPass-123", "csrfmiddlewaretoken": token},
        HTTP_REFERER="https://polymentor.onrender.com/admin/login/",
        **HTTPS,
    )
    assert resp.status_code == 302 and resp["Location"] == "/admin/"
    for path in [
        "/admin/",
        "/admin/polymentor_sessions/turn/",
        "/admin/feedback/feedback/",
        "/admin/feedback/learnedexemplar/",
        "/admin/experts/expertversion/",
    ]:
        assert client.get(path, **HTTPS).status_code == 200, path
