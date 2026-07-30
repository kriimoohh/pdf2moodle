"""Assemblage du document HTML autonome.

Le fichier produit n'émet aucune requête réseau : styles, script et images
sont tous intégrés au fichier (images en data-URI base64).
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .converter import RenderedPage

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_DOCUMENT_TEMPLATE = "document.html.j2"

# L'échappement automatique est indispensable : badge, titre, sous-titre et
# auteur viennent d'un formulaire public et sont réinjectés dans le HTML.
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "j2"], default_for_string=True),
    trim_blocks=True,
    lstrip_blocks=True,
)

_DEFAULT_TITLE = "Support de cours"
_FIELD_MAX_CHARS = 300


def _clean(value: str | None, max_chars: int = _FIELD_MAX_CHARS) -> str:
    """Normalise un champ du formulaire (espaces, caractères de contrôle)."""
    if not value:
        return ""
    text = " ".join(str(value).split())
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")
    return text[:max_chars]


def build_document(
    pages: list[RenderedPage],
    *,
    title: str | None = None,
    badge: str | None = None,
    subtitle: str | None = None,
    author: str | None = None,
    fallback_title: str = _DEFAULT_TITLE,
) -> str:
    """Rend le document complet et retourne le HTML sous forme de chaîne."""
    return _env.get_template(_DOCUMENT_TEMPLATE).render(
        pages=pages,
        doc_title=_clean(title) or _clean(fallback_title) or _DEFAULT_TITLE,
        badge=_clean(badge, 80),
        subtitle=_clean(subtitle),
        author=_clean(author, 160),
    )


def safe_output_filename(source_filename: str) -> str:
    """Dérive un nom de fichier HTML sûr à partir du nom du PDF d'origine.

    On retire tout séparateur de chemin et tout caractère susceptible de poser
    problème dans un en-tête `Content-Disposition` ou sur un système de
    fichiers, y compris chez le destinataire du fichier.
    """
    stem = Path(source_filename.replace("\\", "/")).name
    if stem.lower().endswith(".pdf"):
        stem = stem[:-4]

    # Translittération ASCII : évite les en-têtes HTTP non-ASCII.
    stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")

    return f"{stem[:120] or 'support'}.html"


def title_from_filename(source_filename: str) -> str:
    """Titre de repli lisible, déduit du nom du PDF."""
    stem = Path(source_filename.replace("\\", "/")).name
    if stem.lower().endswith(".pdf"):
        stem = stem[:-4]
    return " ".join(stem.replace("_", " ").replace("-", " ").split()) or _DEFAULT_TITLE
