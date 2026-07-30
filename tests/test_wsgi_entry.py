"""Point d'entrée WSGI utilisé par Passenger (O2Switch).

Ce chemin est distinct de celui d'uvicorn : il traverse `a2wsgi`. Il mérite ses
propres tests, une erreur ici ne se voyant qu'une fois déployé.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest

from wsgi_entry import application

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def call_wsgi(method: str, path: str, body: bytes = b"", content_type: str = ""):
    """Invoque l'application WSGI comme le ferait Passenger."""
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "SERVER_NAME": "pdf2moodle.sakai.sn",
        "SERVER_PORT": "443",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "HTTP_HOST": "pdf2moodle.sakai.sn",
        "wsgi.url_scheme": "https",
        "wsgi.input": io.BytesIO(body),
        "wsgi.errors": io.BytesIO(),
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": content_type,
    }
    captured: dict = {}

    def start_response(status, headers, exc_info=None):
        captured["status"] = int(status.split()[0])
        captured["headers"] = {k.lower(): v for k, v in headers}

    payload = b"".join(application(environ, start_response))
    return captured["status"], captured["headers"], payload


def _multipart(pdf: bytes, filename: str, **fields) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    chunks = [
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode()
        + pdf
        + b"\r\n"
    ]
    for key, value in fields.items():
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n'
            f"{value}\r\n".encode()
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def test_entry_point_exposes_a_wsgi_callable():
    """Passenger attend une variable `application` appelable."""
    assert callable(application)


def test_entry_point_is_not_named_passenger_wsgi():
    """cPanel génère son propre `passenger_wsgi.py` qui charge ce fichier.

    Si le fichier de démarrage s'appelait `passenger_wsgi.py`, le chargeur se
    chargerait lui-même : `RecursionError` et erreur 500 au démarrage.
    """
    import wsgi_entry

    name = Path(wsgi_entry.__file__).name
    assert name != "passenger_wsgi.py"
    assert not (Path(wsgi_entry.__file__).parent / "passenger_wsgi.py").exists()


def test_health_endpoint_through_wsgi():
    status, _, body = call_wsgi("GET", "/healthz")
    assert status == 200
    assert b'"ok"' in body


def test_upload_page_through_wsgi():
    status, headers, body = call_wsgi("GET", "/")
    assert status == 200
    assert headers["content-type"].startswith("text/html")
    assert b"pdf2moodle" in body


def test_static_assets_through_wsgi():
    status, _, body = call_wsgi("GET", "/static/app.css")
    assert status == 200
    assert b"--navy:#152742" in body


def test_full_conversion_through_wsgi():
    """Le chemin réellement emprunté en production, de bout en bout."""
    pdf = (FIXTURES_DIR / "cours-normal.pdf").read_bytes()
    body, content_type = _multipart(
        pdf, "cours-normal.pdf", quality="low", title="Systèmes distribués"
    )

    status, headers, payload = call_wsgi("POST", "/api/convert", body, content_type)

    assert status == 200
    assert headers["content-disposition"] == 'attachment; filename="cours-normal.html"'
    assert headers["x-page-count"] == "6"

    html = payload.decode("utf-8")
    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert html.count('src="data:image/jpeg;base64,') == 6
    for word in ("diapositive", "diapo", "slide"):
        assert word not in html.lower()


def test_error_response_through_wsgi():
    body, content_type = _multipart(b"pas un pdf", "faux.pdf", quality="low")
    status, headers, payload = call_wsgi("POST", "/api/convert", body, content_type)

    assert status == 400
    assert headers["content-type"].startswith("application/json")
    assert b"error" in payload


@pytest.mark.parametrize("path", ["/docs", "/openapi.json"])
def test_api_docs_disabled_through_wsgi(path):
    status, _, _ = call_wsgi("GET", path)
    assert status == 404
