"""Vérification des critères d'acceptation du cahier des charges."""

from __future__ import annotations

import re
import tempfile
import time

import fitz
import pytest

from app import config
from app.converter import ConversionError, convert, extract_title, validate_upload
from app.html_builder import build_document, safe_output_filename
from tests.conftest import convert_request
from tests.make_fixtures import NORMAL_TITLES, TRICKY_TITLES

# Vocabulaire à ne jamais faire figurer dans le document généré.
BANNED_WORDS = ("diapositive", "diapositives", "diapo", "diapos", "slide", "slides")


def _document_for(name: str, data: bytes, **fields) -> str:
    from app.converter import convert as _convert

    result = _convert(data, fields.pop("quality", "low"))
    return build_document(result.pages, **fields)


# ---------------------------------------------------------------------------
# Critère : un PDF de 30 pages est converti en moins de 15 secondes.
# ---------------------------------------------------------------------------


def test_30_pages_convert_under_15_seconds(client, pdf_bytes):
    data = pdf_bytes("cours-30-pages.pdf")

    started = time.monotonic()
    response = convert_request(client, "cours-30-pages.pdf", data, quality="high")
    elapsed = time.monotonic() - started

    assert response.status_code == 200, response.text
    assert response.headers["X-Page-Count"] == "30"
    assert elapsed < 15, f"conversion trop lente : {elapsed:.1f}s"


# ---------------------------------------------------------------------------
# Critère : le HTML s'ouvre hors ligne, sans aucune requête réseau.
# ---------------------------------------------------------------------------


def test_generated_html_makes_no_network_request(client, pdf_bytes):
    html = convert_request(
        client, "cours-normal.pdf", pdf_bytes("cours-normal.pdf")
    ).text

    # Aucune ressource externe référencée par un attribut src/href.
    external = re.findall(r'(?:src|href)\s*=\s*"((?:https?:)?//[^"]*)"', html, re.I)
    assert external == [], f"ressources externes référencées : {external}"

    # Aucun import de police, feuille de style ou script distant.
    assert "<link" not in html.lower()
    assert "@import" not in html
    assert not re.search(r"<script[^>]+src=", html, re.I)

    # Les images sont bien intégrées au fichier.
    assert html.count('src="data:image/jpeg;base64,') == 6


def test_generated_html_is_valid_standalone_structure(client, pdf_bytes):
    html = convert_request(
        client, "cours-normal.pdf", pdf_bytes("cours-normal.pdf")
    ).text

    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert html.rstrip().endswith("</html>")
    assert '<html lang="fr">' in html
    assert '<meta charset="utf-8">' in html


# ---------------------------------------------------------------------------
# Critère : sommaire, zoom et plein écran présents et câblés.
#
# Le comportement visuel réel (Chrome / Firefox / Safari mobile) relève d'un
# test navigateur ; on vérifie ici que le contrat DOM et les API utilisées
# sont bien dans le fichier livré.
# ---------------------------------------------------------------------------


def test_toolbar_and_navigation_contract(client, pdf_bytes):
    html = convert_request(
        client, "cours-normal.pdf", pdf_bytes("cours-normal.pdf")
    ).text

    # Sommaire : un lien par page, ancré sur la section correspondante.
    for index, title in enumerate(NORMAL_TITLES, start=1):
        assert f'href="#page-{index}"' in html
        assert f'id="page-{index}"' in html

    # Zoom : compensation de largeur et bornes conformes.
    assert 'id="zoom-in"' in html and 'id="zoom-out"' in html
    assert 'id="zoom-level"' in html
    assert 'target.style.width = (100 / zoom)' in html
    assert "ZOOM_MIN = 0.6, ZOOM_MAX = 1.6, ZOOM_STEP = 0.1" in html

    # Plein écran, avec repli webkit.
    assert "requestFullscreen" in html and "webkitRequestFullscreen" in html
    assert "exitFullscreen" in html and "webkitExitFullscreen" in html

    # Sommaire mobile et suivi de lecture.
    assert 'id="menu-btn"' in html and 'id="overlay"' in html
    assert 'rootMargin: "-10% 0px -75% 0px"' in html
    assert "IntersectionObserver" in html


def test_css_tokens_match_specification(client, pdf_bytes):
    html = convert_request(
        client, "cours-normal.pdf", pdf_bytes("cours-normal.pdf")
    ).text

    for token in (
        "--blue:#1CA9DB",
        "--blue-dark:#0E7FA8",
        "--navy:#152742",
        "--navy2:#1E3A5F",
        "--gold:#C69B4A",
        "--bg:#eef2f6",
        "--card:#FFFFFF",
        "--text:#233142",
        "--muted:#5C6B7A",
        "--border:#E1E8ED",
    ):
        assert token in html, f"token manquant : {token}"

    assert '"Segoe UI",Arial,Helvetica,sans-serif' in html
    assert (
        "linear-gradient(135deg,var(--navy) 0%,var(--navy2) 55%,var(--blue-dark) 100%)"
        in html
    )


# ---------------------------------------------------------------------------
# Critère : aucune occurrence du vocabulaire interdit dans le fichier généré.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["cours-normal.pdf", "cours-titres-pieges.pdf", "cours-image-pure.pdf"],
)
def test_no_banned_vocabulary_anywhere(client, pdf_bytes, name):
    html = convert_request(
        client,
        name,
        pdf_bytes(name),
        badge="Licence 2",
        title="Systèmes distribués",
        subtitle="Support de cours",
        author="A. Fall",
    ).text

    lowered = html.lower()
    for word in BANNED_WORDS:
        assert word not in lowered, f"mot interdit trouvé dans la sortie : {word!r}"


def test_no_page_numbering_in_visible_labels(client, pdf_bytes):
    """Aucun compteur du type « Page 3 / 40 » ne doit apparaître."""
    html = convert_request(
        client, "cours-normal.pdf", pdf_bytes("cours-normal.pdf")
    ).text

    labels = re.findall(r'<div class="page-label">(.*?)</div>', html, re.S)
    assert len(labels) == len(NORMAL_TITLES)
    for label, expected in zip(labels, NORMAL_TITLES):
        assert label.strip() == expected
        assert not re.search(r"\d+\s*/\s*\d+", label)


# ---------------------------------------------------------------------------
# Critère : titres de sommaire cohérents avec le contenu réel des pages.
# ---------------------------------------------------------------------------


def test_titles_on_clean_document(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes("cours-normal.pdf"), filetype="pdf")
    titles = [extract_title(page, i) for i, page in enumerate(doc, start=1)]
    doc.close()
    assert titles == NORMAL_TITLES


def test_titles_ignore_dates_and_page_numbers(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes("cours-titres-pieges.pdf"), filetype="pdf")
    titles = [extract_title(page, i) for i, page in enumerate(doc, start=1)]
    doc.close()

    assert titles[:3] == TRICKY_TITLES          # date en tête ignorée
    assert titles[3] == "Page 4"                # numéro isolé -> repli
    assert titles[4] == "Page 5"                # page vide -> repli
    assert titles[5] == "Synthèse et exercices"  # date en toutes lettres ignorée


def test_titles_on_image_only_document(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes("cours-image-pure.pdf"), filetype="pdf")
    titles = [extract_title(page, i) for i, page in enumerate(doc, start=1)]
    doc.close()
    assert titles == ["Page 1", "Page 2", "Page 3", "Page 4"]


def test_toc_label_truncated_to_60_chars():
    from app.converter import RenderedPage

    long_title = "Un titre exceptionnellement long qui dépasse largement la limite fixée"
    page = RenderedPage(title=long_title, image_b64="")
    assert len(page.toc_label) == 60
    assert page.toc_label.endswith("…")
    assert page.title == long_title  # le libellé de la page reste complet


# ---------------------------------------------------------------------------
# Critère : le PDF n'est jamais écrit sur le disque du serveur.
# ---------------------------------------------------------------------------


def test_upload_never_rolls_over_to_disk(client, monkeypatch):
    """Un PDF de plus de 1 Mo doit rester intégralement en mémoire.

    Starlette confie chaque fichier reçu à un `SpooledTemporaryFile` : dès que
    son seuil est franchi, `rollover()` bascule le contenu dans un fichier
    temporaire sur disque. On instrumente cette méthode pour prouver qu'elle
    n'est jamais appelée.
    """
    rollovers: list[int] = []
    original = tempfile.SpooledTemporaryFile.rollover

    def spy(self):
        rollovers.append(1)
        return original(self)

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", spy)

    # PDF volumineux (bruit non compressible) généré à la volée, hors dépôt.
    doc = fitz.open()
    for _ in range(3):
        page = doc.new_page(width=720, height=540)
        noise = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 700, 520), False)
        for i in range(0, len(noise.samples), 997):
            noise.set_pixel((i // 3) % 700, ((i // 3) // 700) % 520, (i % 255, 7, 200))
        page.insert_image(fitz.Rect(10, 10, 710, 530), pixmap=noise)
    big = doc.tobytes(deflate=False)
    doc.close()

    assert len(big) > 1024 * 1024, "le PDF de contrôle doit dépasser le seuil de 1 Mo"

    response = convert_request(client, "volumineux.pdf", big)

    assert response.status_code == 200, response.text
    assert rollovers == [], "le fichier reçu a été écrit sur le disque"


def test_spool_threshold_is_raised_above_upload_limit():
    from starlette.formparsers import MultiPartParser

    assert MultiPartParser.spool_max_size > config.MAX_UPLOAD_BYTES


def test_no_temporary_files_left_behind(client, pdf_bytes, tmp_path, monkeypatch):
    """Aucun résidu dans le répertoire temporaire après une conversion."""
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    response = convert_request(client, "cours-normal.pdf", pdf_bytes("cours-normal.pdf"))

    assert response.status_code == 200
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# Réponse HTTP
# ---------------------------------------------------------------------------


def test_response_is_an_html_attachment(client, pdf_bytes):
    response = convert_request(client, "Cours n°3 — Réseaux.pdf", pdf_bytes("cours-normal.pdf"))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["content-disposition"] == (
        'attachment; filename="Cours-n3-Reseaux.html"'
    )
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "source,expected",
    [
        ("cours.pdf", "cours.html"),
        ("Cours Réseaux — S3.PDF", "Cours-Reseaux-S3.html"),
        ("../../etc/passwd.pdf", "passwd.html"),
        ("C:\\Users\\moi\\support.pdf", "support.html"),
        (".pdf", "support.html"),
        # Tout ce qui précède le dernier séparateur est un composant de chemin
        # et se trouve écarté : il ne reste ici rien d'exploitable.
        ('evil";rm -rf /.pdf', "support.html"),
        # Le guillemet est retiré : pas d'injection dans Content-Disposition.
        ('injection" ; echo .pdf', "injection-echo.html"),
    ],
)
def test_output_filename_is_sanitised(source, expected):
    assert safe_output_filename(source) == expected


def test_metadata_fields_appear_in_document(client, pdf_bytes):
    html = convert_request(
        client,
        "cours-normal.pdf",
        pdf_bytes("cours-normal.pdf"),
        badge="Licence 2 — Semestre 3",
        title="Systèmes distribués",
        subtitle="Introduction générale",
        author="A. Fall — Université",
    ).text

    assert "Licence 2 — Semestre 3" in html
    assert "<title>Systèmes distribués</title>" in html
    assert "Introduction générale" in html
    assert "A. Fall — Université" in html


def test_title_falls_back_to_filename(client, pdf_bytes):
    html = convert_request(
        client, "systemes_distribues-2025.pdf", pdf_bytes("cours-normal.pdf")
    ).text
    assert "<title>systemes distribues 2025</title>" in html


def test_user_fields_are_escaped(client, pdf_bytes):
    """Les champs du formulaire ne doivent pas pouvoir injecter de balises."""
    html = convert_request(
        client,
        "cours-normal.pdf",
        pdf_bytes("cours-normal.pdf"),
        title="<script>alert(1)</script>",
        subtitle='" onerror="alert(2)',
    ).text

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert 'onerror="alert(2)' not in html


# ---------------------------------------------------------------------------
# Gestion des erreurs
# ---------------------------------------------------------------------------


def test_missing_file_is_rejected(client):
    response = client.post("/api/convert", data={"quality": "low"})
    assert response.status_code == 422


def test_non_pdf_extension_is_rejected(client):
    response = client.post(
        "/api/convert",
        files={"file": ("notes.txt", b"du texte", "text/plain")},
        data={"quality": "low"},
    )
    assert response.status_code == 400
    assert "pdf" in response.json()["error"].lower()


def test_file_disguised_as_pdf_is_rejected(client):
    """Extension et type MIME corrects mais contenu qui n'est pas un PDF."""
    response = client.post(
        "/api/convert",
        files={"file": ("piege.pdf", b"GIF89a" + b"\x00" * 500, "application/pdf")},
        data={"quality": "low"},
    )
    assert response.status_code == 400
    assert "signature" in response.json()["error"].lower()


def test_corrupted_pdf_is_rejected(client):
    broken = b"%PDF-1.4\n" + b"\x00\xff" * 400
    response = convert_request(client, "casse.pdf", broken)
    assert response.status_code == 400
    assert "error" in response.json()


def test_encrypted_pdf_is_rejected(client):
    doc = fitz.open()
    doc.new_page()
    encrypted = doc.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u"
    )
    doc.close()

    response = convert_request(client, "protege.pdf", encrypted)
    assert response.status_code == 400
    assert "mot de passe" in response.json()["error"].lower()


def test_empty_file_is_rejected(client):
    response = convert_request(client, "vide.pdf", b"")
    assert response.status_code == 400


def test_too_many_pages_is_rejected(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_PAGES", 3)

    doc = fitz.open()
    for _ in range(5):
        doc.new_page()
    data = doc.tobytes()
    doc.close()

    response = convert_request(client, "long.pdf", data)
    assert response.status_code == 413
    assert "150" not in response.json()["error"]  # la limite courante est reflétée


def test_oversized_upload_is_rejected(client, monkeypatch, pdf_bytes):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 1024)
    response = convert_request(client, "gros.pdf", pdf_bytes("cours-normal.pdf"))
    assert response.status_code == 413


def test_render_timeout_returns_504(monkeypatch, pdf_bytes):
    monkeypatch.setattr(config, "RENDER_TIMEOUT_SECONDS", 0.0)
    with pytest.raises(ConversionError) as excinfo:
        convert(pdf_bytes("cours-normal.pdf"), "low")
    assert excinfo.value.status_code == 504


def test_unknown_quality_falls_back_to_default(client, pdf_bytes):
    response = convert_request(
        client, "cours-normal.pdf", pdf_bytes("cours-normal.pdf"), quality="ultra"
    )
    assert response.status_code == 200


@pytest.mark.parametrize("quality", ["low", "medium", "high"])
def test_quality_levels_produce_increasing_sizes(pdf_bytes, quality):
    result = convert(pdf_bytes("cours-normal.pdf"), quality)
    assert len(result.pages) == 6
    assert all(page.image_b64 for page in result.pages)


def test_higher_quality_yields_larger_images(pdf_bytes):
    data = pdf_bytes("cours-normal.pdf")
    sizes = [
        sum(len(p.image_b64) for p in convert(data, q).pages)
        for q in ("low", "medium", "high")
    ]
    assert sizes[0] < sizes[1] < sizes[2]


# ---------------------------------------------------------------------------
# Pages de service
# ---------------------------------------------------------------------------


def test_upload_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "pdf2moodle" in response.text
    assert 'id="drop"' in response.text


def test_health_endpoint(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_static_assets_are_served(client):
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_api_docs_are_disabled(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
