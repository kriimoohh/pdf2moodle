"""Configuration centrale, pilotée par variables d'environnement."""

from __future__ import annotations

import os

# --- Limites d'entrée -------------------------------------------------------

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024
MAX_PAGES = int(os.getenv("MAX_PAGES", "150"))

# Budget de temps pour le rendu. Le traitement étant synchrone dans la requête
# HTTP, on préfère rendre un 504 explicite plutôt que de laisser le proxy
# couper la connexion sans message exploitable.
RENDER_TIMEOUT_SECONDS = float(os.getenv("RENDER_TIMEOUT_SECONDS", "120"))

# --- Qualité de rendu -------------------------------------------------------
#
# Chaque palier associe un facteur d'échelle PyMuPDF (matrice de zoom) et une
# qualité JPEG. Le facteur d'échelle domine le poids final du fichier : à 2.2
# une page A4 paysage fait ~2200px de large, ce qui reste net en plein écran.

QUALITY_PRESETS: dict[str, tuple[float, int]] = {
    "low": (1.2, 72),
    "medium": (1.6, 82),
    "high": (2.2, 88),
}
DEFAULT_QUALITY = "medium"

# --- Sécurité ---------------------------------------------------------------
#
# Si TOOL_PASSWORD est défini, toutes les routes passent derrière une
# authentification HTTP Basic. Vide ou absent => outil ouvert (usage local).

TOOL_PASSWORD = os.getenv("TOOL_PASSWORD", "")
TOOL_USERNAME = os.getenv("TOOL_USERNAME", "moodle")


def auth_enabled() -> bool:
    return bool(TOOL_PASSWORD)
