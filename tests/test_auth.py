"""Protection par mot de passe (activée uniquement si TOOL_PASSWORD est défini)."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def protected_client(monkeypatch) -> TestClient:
    """Recharge l'application avec l'authentification activée."""
    monkeypatch.setenv("TOOL_PASSWORD", "s3cret")
    monkeypatch.setenv("TOOL_USERNAME", "prof")

    from app import config, main

    importlib.reload(config)
    importlib.reload(main)
    yield TestClient(main.app)

    # Restaure l'état par défaut pour les autres modules de test.
    monkeypatch.delenv("TOOL_PASSWORD", raising=False)
    monkeypatch.delenv("TOOL_USERNAME", raising=False)
    importlib.reload(config)
    importlib.reload(main)


def test_auth_disabled_by_default(client):
    assert client.get("/").status_code == 200


def test_anonymous_access_is_refused(protected_client):
    response = protected_client.get("/")
    assert response.status_code == 401
    assert "Basic" in response.headers["www-authenticate"]


def test_wrong_password_is_refused(protected_client):
    assert protected_client.get("/", auth=("prof", "mauvais")).status_code == 401


def test_wrong_username_is_refused(protected_client):
    assert protected_client.get("/", auth=("autre", "s3cret")).status_code == 401


def test_valid_credentials_are_accepted(protected_client):
    assert protected_client.get("/", auth=("prof", "s3cret")).status_code == 200


def test_convert_endpoint_is_protected(protected_client, pdf_bytes):
    files = {"file": ("cours.pdf", pdf_bytes("cours-normal.pdf"), "application/pdf")}

    assert protected_client.post("/api/convert", files=files).status_code == 401

    ok = protected_client.post(
        "/api/convert", files=files, data={"quality": "low"}, auth=("prof", "s3cret")
    )
    assert ok.status_code == 200


def test_health_endpoint_stays_public(protected_client):
    """La sonde doit rester joignable sans authentification."""
    assert protected_client.get("/healthz").status_code == 200
