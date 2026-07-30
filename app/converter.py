"""Rendu PDF -> images et extraction des titres, intégralement en mémoire.

Aucune fonction de ce module n'écrit sur le disque : le PDF est ouvert depuis
un `bytes` via `fitz.open(stream=...)` et les images sont produites sous forme
de `bytes` JPEG.
"""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass

import fitz  # PyMuPDF

from . import config

# Motifs de dates à ne jamais retenir comme titre : sur les supports de cours,
# le premier bloc de texte d'une page est souvent la date de la séance placée
# en en-tête, au-dessus du vrai titre.
_DATE_PATTERNS = (
    re.compile(r"^\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}$"),
    re.compile(r"^\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}$"),
    re.compile(
        r"^\d{1,2}\s+(janvier|février|fevrier|mars|avril|mai|juin|juillet|"
        r"août|aout|septembre|octobre|novembre|décembre|decembre)\s+\d{4}$",
        re.IGNORECASE,
    ),
)

# Bruit d'en-tête / pied de page : numéros isolés, "3/40", puces seules.
_NOISE_PATTERN = re.compile(r"^[\s\d/\-–—.,;:•·°*|]+$")

_TITLE_MIN_CHARS = 3
_TOC_LABEL_MAX_CHARS = 60


class ConversionError(Exception):
    """Erreur fonctionnelle, transformée en réponse JSON par la couche HTTP."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class RenderedPage:
    """Une page du PDF : son titre extrait et son image encodée en base64."""

    title: str
    image_b64: str

    @property
    def toc_label(self) -> str:
        """Libellé du sommaire, tronqué à 60 caractères."""
        if len(self.title) <= _TOC_LABEL_MAX_CHARS:
            return self.title
        return self.title[: _TOC_LABEL_MAX_CHARS - 1].rstrip() + "…"


@dataclass(frozen=True)
class ConversionResult:
    pages: list[RenderedPage]
    duration_seconds: float


def validate_upload(data: bytes, filename: str, content_type: str | None) -> None:
    """Valide le fichier reçu avant toute tentative d'ouverture.

    Le `content_type` annoncé par le navigateur est purement déclaratif : il
    sert de premier filtre, mais la validation qui fait foi porte sur la
    signature du fichier (`%PDF-`) puis sur l'ouverture effective par PyMuPDF.
    """
    if not data:
        raise ConversionError("Le fichier reçu est vide.")

    if len(data) > config.MAX_UPLOAD_BYTES:
        limit_mb = config.MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ConversionError(
            f"Fichier trop volumineux ({len(data) / 1024 / 1024:.1f} Mo). "
            f"La limite est de {limit_mb} Mo.",
            status_code=413,
        )

    if not filename.lower().endswith(".pdf"):
        raise ConversionError("Le fichier doit avoir l'extension .pdf.")

    if content_type and content_type.split(";")[0].strip().lower() not in {
        "application/pdf",
        "application/x-pdf",
        "application/octet-stream",
    }:
        raise ConversionError("Le type de fichier envoyé n'est pas un PDF.")

    # Signature PDF. Certains outils insèrent quelques octets parasites avant
    # l'en-tête, d'où la recherche sur le début du fichier plutôt qu'un
    # startswith strict.
    if b"%PDF-" not in data[:1024]:
        raise ConversionError("Ce fichier n'est pas un PDF valide (signature absente).")


def _open_document(data: bytes) -> fitz.Document:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # PyMuPDF remonte des exceptions variées
        raise ConversionError(f"PDF illisible ou corrompu ({exc}).") from exc

    if doc.needs_pass:
        doc.close()
        raise ConversionError(
            "Ce PDF est protégé par mot de passe. Retirez la protection avant conversion."
        )

    if doc.page_count == 0:
        doc.close()
        raise ConversionError("Ce PDF ne contient aucune page.")

    if doc.page_count > config.MAX_PAGES:
        page_count = doc.page_count
        doc.close()
        raise ConversionError(
            f"Ce PDF contient {page_count} pages, au-delà de la limite "
            f"de {config.MAX_PAGES} pages.",
            status_code=413,
        )

    return doc


def _looks_like_title(text: str) -> bool:
    """Un texte est un titre plausible s'il est substantiel et non-technique."""
    if len(text) < _TITLE_MIN_CHARS:
        return False
    if _NOISE_PATTERN.match(text):
        return False
    return not any(pattern.match(text) for pattern in _DATE_PATTERNS)


def extract_title(page: fitz.Page, page_number: int) -> str:
    """Retourne le titre de la page, ou `Page N` si aucun n'est exploitable.

    On lit les blocs via `get_text("dict")`, on les trie par position verticale
    puis horizontale, et on retient le premier bloc substantiel.
    """
    try:
        blocks = page.get_text("dict")["blocks"]
    except Exception:
        return f"Page {page_number}"

    text_blocks = [b for b in blocks if b.get("type") == 0 and b.get("lines")]
    # bbox = (x0, y0, x1, y1) : tri haut -> bas, puis gauche -> droite.
    text_blocks.sort(key=lambda b: (round(b["bbox"][1], 1), round(b["bbox"][0], 1)))

    for block in text_blocks:
        parts = [
            span.get("text", "")
            for line in block["lines"]
            for span in line.get("spans", [])
        ]
        # Un titre sur deux lignes doit rester lisible d'un seul tenant.
        text = " ".join("".join(parts).split())
        if _looks_like_title(text):
            return text

    return f"Page {page_number}"


def convert(pdf_bytes: bytes, quality: str) -> ConversionResult:
    """Convertit le PDF en pages images + titres. Tout reste en mémoire."""
    scale, jpeg_quality = config.QUALITY_PRESETS.get(
        quality, config.QUALITY_PRESETS[config.DEFAULT_QUALITY]
    )

    started = time.monotonic()
    doc = _open_document(pdf_bytes)
    matrix = fitz.Matrix(scale, scale)
    pages: list[RenderedPage] = []

    try:
        for index, page in enumerate(doc, start=1):
            if time.monotonic() - started > config.RENDER_TIMEOUT_SECONDS:
                raise ConversionError(
                    f"Le rendu a dépassé {config.RENDER_TIMEOUT_SECONDS:.0f} s "
                    f"(arrêt à la page {index}). Réessayez en qualité inférieure.",
                    status_code=504,
                )

            title = extract_title(page, index)
            try:
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                jpeg = pixmap.tobytes("jpeg", jpg_quality=jpeg_quality)
            except Exception as exc:
                raise ConversionError(
                    f"Échec du rendu de la page {index} ({exc})."
                ) from exc

            pages.append(
                RenderedPage(title=title, image_b64=base64.b64encode(jpeg).decode("ascii"))
            )
    finally:
        doc.close()

    return ConversionResult(pages=pages, duration_seconds=time.monotonic() - started)
