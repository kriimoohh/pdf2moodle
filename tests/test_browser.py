"""Comportement réel du document généré, dans un navigateur.

Ces tests couvrent le critère d'acceptation portant sur le sommaire, le zoom
et le plein écran, que la seule inspection du HTML ne peut pas prouver.

Ils sont ignorés si Playwright n'est pas installé :

    pip install playwright && playwright install chromium
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright", reason="Playwright non installé")

from playwright.sync_api import sync_playwright  # noqa: E402

from app.converter import convert  # noqa: E402
from app.html_builder import build_document  # noqa: E402

MOBILE = {"width": 390, "height": 780}
DESKTOP = {"width": 1400, "height": 900}


@pytest.fixture(scope="module")
def document_url(tmp_path_factory, request) -> str:
    """Écrit le document généré sur disque et retourne son URL `file://`.

    L'ouverture en `file://` reproduit exactement la situation d'un fichier
    téléchargé depuis Moodle et ouvert hors ligne.
    """
    fixtures = request.path.parent / "fixtures"
    pages = convert((fixtures / "cours-normal.pdf").read_bytes(), "low").pages
    html = build_document(
        pages,
        title="Systèmes distribués",
        badge="Licence 2",
        subtitle="Introduction générale",
        author="A. Fall",
    )
    path = tmp_path_factory.mktemp("doc") / "document.html"
    path.write_text(html, encoding="utf-8")
    return path.as_uri()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch()
        yield instance
        instance.close()


def _open(browser, url: str, viewport: dict):
    """Ouvre le document en collectant erreurs JS et requêtes réseau."""
    page = browser.new_page(viewport=viewport)
    errors: list[str] = []
    remote: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on(
        "request",
        lambda r: remote.append(r.url) if not r.url.startswith("file:") else None,
    )
    page.goto(url)
    page.wait_for_timeout(500)
    return page, errors, remote


def test_document_opens_offline_without_errors(browser, document_url):
    page, errors, remote = _open(browser, document_url, DESKTOP)

    assert errors == [], f"erreurs JS : {errors}"
    assert remote == [], f"requêtes réseau émises : {remote}"
    assert page.locator("#toc a").count() == 6
    assert page.locator(".page-block").count() == 6
    # Les images sont réellement décodées, pas seulement présentes.
    assert page.locator("img.page-img").first.evaluate("img => img.naturalWidth") > 0
    page.close()


def test_zoom_scales_and_compensates_width(browser, document_url):
    page, _, _ = _open(browser, document_url, DESKTOP)
    target = page.locator("#zoom-target")

    page.click("#zoom-in")
    page.click("#zoom-in")
    assert page.locator("#zoom-level").inner_text() == "120%"
    assert target.evaluate("e => e.style.transform") == "scale(1.2)"
    # Compensation de largeur : 100 / 1.2
    assert target.evaluate("e => e.style.width").startswith("83.3")

    # Aucun débordement horizontal, quel que soit le niveau.
    assert not page.evaluate(
        "() => document.documentElement.scrollWidth > window.innerWidth"
    )

    page.click("#zoom-level")
    assert page.locator("#zoom-level").inner_text() == "100%"
    page.close()


def test_zoom_stays_within_bounds(browser, document_url):
    page, _, _ = _open(browser, document_url, DESKTOP)

    for _ in range(14):
        page.click("#zoom-in")
    assert page.locator("#zoom-level").inner_text() == "160%"

    for _ in range(22):
        page.click("#zoom-out")
    assert page.locator("#zoom-level").inner_text() == "60%"
    page.close()


def test_toc_link_navigates_to_matching_section(browser, document_url):
    page, _, _ = _open(browser, document_url, DESKTOP)

    page.click('#toc a[href="#page-3"]')
    page.wait_for_timeout(800)

    assert page.locator("#page-3").evaluate(
        "e => { const r = e.getBoundingClientRect();"
        "       return r.top > -50 && r.top < window.innerHeight / 2; }"
    )
    page.close()


def test_scroll_spy_highlights_current_section(browser, document_url):
    page, _, _ = _open(browser, document_url, DESKTOP)

    page.evaluate("() => document.getElementById('page-4').scrollIntoView()")
    page.wait_for_timeout(700)

    active = page.locator("#toc a.active")
    assert active.count() == 1
    assert active.first.get_attribute("href") == "#page-4"
    page.close()


def test_fullscreen_button_calls_the_api(browser, document_url):
    """Le plein écran réel n'est pas disponible sans interface ; on vérifie
    que le bouton appelle bien l'API du navigateur."""
    page, _, _ = _open(browser, document_url, DESKTOP)

    page.evaluate(
        "() => { window.__fs = 0;"
        "        document.documentElement.requestFullscreen = () => {"
        "          window.__fs++; return Promise.resolve(); }; }"
    )
    page.click("#fs-btn")
    assert page.evaluate("() => window.__fs") == 1
    page.close()


def test_sidebar_is_hidden_and_toggles_on_mobile(browser, document_url):
    page, _, _ = _open(browser, document_url, MOBILE)

    # Hors écran au chargement : translation de la largeur de la colonne.
    assert "-280" in page.evaluate(
        "() => getComputedStyle(document.getElementById('sidebar')).transform"
    )
    assert page.locator("#menu-btn").is_visible()

    page.click("#menu-btn")
    page.wait_for_timeout(400)
    assert page.locator("#sidebar").evaluate("e => e.classList.contains('open')")
    assert page.locator("#overlay").evaluate("e => e.classList.contains('open')")

    # Un appui sur la zone libre à droite de la colonne referme le panneau.
    page.mouse.click(350, 400)
    page.wait_for_timeout(400)
    assert not page.locator("#sidebar").evaluate("e => e.classList.contains('open')")
    page.close()


def test_sidebar_is_always_visible_on_desktop(browser, document_url):
    page, _, _ = _open(browser, document_url, DESKTOP)

    assert page.locator("#sidebar").is_visible()
    assert not page.locator("#menu-btn").is_visible()
    page.close()
