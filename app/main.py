"""Application FastAPI : page d'upload + endpoint de conversion.

Traitement entièrement synchrone et en mémoire. Ni le PDF reçu ni le HTML
produit ne touchent le disque du serveur.
"""

from __future__ import annotations

import logging
import secrets
from pathlib import Path

from starlette.formparsers import MultiPartParser

from . import config

# --------------------------------------------------------------------------
# À FAIRE AVANT TOUTE GESTION DE REQUÊTE.
#
# Starlette stocke chaque fichier reçu dans un `SpooledTemporaryFile` dont le
# seuil de débordement (`spool_max_size`) vaut 1 Mo : au-delà, le contenu est
# écrit dans le répertoire temporaire du système. Pour un diaporama de cours,
# cela signifierait écrire systématiquement le PDF sur disque, ce que l'on
# veut précisément éviter. Le seuil n'est pas exposé en paramètre, seulement
# en attribut de classe : on le relève au-dessus de la taille maximale
# acceptée pour que l'upload reste intégralement en mémoire vive.
# --------------------------------------------------------------------------
MultiPartParser.spool_max_size = config.MAX_UPLOAD_BYTES + 1024 * 1024

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse, Response  # noqa: E402
from fastapi.security import HTTPBasic, HTTPBasicCredentials  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

from . import html_builder  # noqa: E402
from .converter import ConversionError, convert, validate_upload  # noqa: E402

logger = logging.getLogger("pdf2moodle")

_BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

app = FastAPI(
    title="pdf2moodle",
    description="Convertit un PDF de cours en page HTML autonome pour Moodle.",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.mount("/static", StaticFiles(directory=str(_BASE_DIR / "static")), name="static")


# --------------------------------------------------------------------- auth

_basic = HTTPBasic(auto_error=False)


def require_auth(credentials: HTTPBasicCredentials | None = Depends(_basic)) -> None:
    """Authentification HTTP Basic, active seulement si TOOL_PASSWORD est défini."""
    if not config.auth_enabled():
        return

    unauthorized = HTTPException(
        status_code=401,
        detail="Authentification requise.",
        headers={"WWW-Authenticate": 'Basic realm="pdf2moodle"'},
    )
    if credentials is None:
        raise unauthorized

    # compare_digest des deux côtés : pas de court-circuit sur le nom d'utilisateur.
    user_ok = secrets.compare_digest(credentials.username, config.TOOL_USERNAME)
    pass_ok = secrets.compare_digest(credentials.password, config.TOOL_PASSWORD)
    if not (user_ok and pass_ok):
        raise unauthorized


# ------------------------------------------------------------------ erreurs


@app.exception_handler(ConversionError)
async def _conversion_error_handler(_: Request, exc: ConversionError) -> JSONResponse:
    return JSONResponse({"error": exc.message}, status_code=exc.status_code)


# -------------------------------------------------------------------- routes


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, _: None = Depends(require_auth)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "max_mb": config.MAX_UPLOAD_BYTES // (1024 * 1024),
            "max_pages": config.MAX_PAGES,
        },
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Sonde de disponibilité, volontairement hors authentification."""
    return {"status": "ok"}


@app.post("/api/convert")
async def api_convert(
    request: Request,
    file: UploadFile = File(...),
    badge: str = Form(""),
    title: str = Form(""),
    subtitle: str = Form(""),
    author: str = Form(""),
    quality: str = Form(config.DEFAULT_QUALITY),
    _: None = Depends(require_auth),
) -> Response:
    """Convertit le PDF reçu et renvoie le HTML autonome en pièce jointe."""

    # Refus immédiat sur l'annonce de taille, avant même de lire le corps.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > config.MAX_UPLOAD_BYTES:
        limit_mb = config.MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ConversionError(
            f"Fichier trop volumineux. La limite est de {limit_mb} Mo.",
            status_code=413,
        )

    if quality not in config.QUALITY_PRESETS:
        quality = config.DEFAULT_QUALITY

    source_name = file.filename or "support.pdf"
    pdf_bytes = await file.read()
    try:
        validate_upload(pdf_bytes, source_name, file.content_type)
        result = convert(pdf_bytes, quality)

        document = html_builder.build_document(
            result.pages,
            title=title,
            badge=badge,
            subtitle=subtitle,
            author=author,
            fallback_title=html_builder.title_from_filename(source_name),
        )
    finally:
        # Libération explicite du tampon d'upload dès que possible.
        await file.close()
        del pdf_bytes

    # Métriques anonymes uniquement : jamais de nom de fichier ni de contenu.
    logger.info(
        "conversion ok pages=%d quality=%s duration=%.2fs output=%dKB",
        len(result.pages),
        quality,
        result.duration_seconds,
        len(document.encode("utf-8")) // 1024,
    )

    filename = html_builder.safe_output_filename(source_name)
    return Response(
        content=document.encode("utf-8"),
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Page-Count": str(len(result.pages)),
            "Cache-Control": "no-store",
        },
    )
