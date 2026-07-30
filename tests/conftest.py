"""Fixtures partagées : PDF d'exemple et client HTTP de test."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# L'authentification doit être désactivée par défaut pendant les tests ; les
# cas qui la testent rechargent l'application avec la variable positionnée.
os.environ.pop("TOOL_PASSWORD", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from tests.make_fixtures import build_all  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def fixtures() -> dict[str, Path]:
    """Garantit la présence des PDF d'exemple (les régénère si absents)."""
    return build_all(FIXTURES_DIR)


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def pdf_bytes():
    """Retourne le contenu d'un PDF d'exemple par son nom de fichier."""

    def _read(name: str) -> bytes:
        return (FIXTURES_DIR / name).read_bytes()

    return _read


def convert_request(client: TestClient, name: str, data: bytes, **fields):
    """Raccourci : poste un PDF sur /api/convert."""
    payload = {"quality": "low"}
    payload.update({k: v for k, v in fields.items() if v is not None})
    return client.post(
        "/api/convert",
        files={"file": (name, data, "application/pdf")},
        data=payload,
    )
