"""Point d'entrée WSGI pour Passenger (cPanel « Setup Python App », O2Switch).

Passenger parle WSGI, FastAPI parle ASGI. On interpose `a2wsgi.ASGIMiddleware`,
qui exécute l'application ASGI dans une boucle d'événements dédiée au sein du
processus Passenger.

Cette approche est préférée au lancement d'uvicorn en sous-processus : pas de
port à réserver, pas de second processus à surveiller, et Passenger conserve la
maîtrise du cycle de vie (arrêt, rechargement, montée en charge).

CE FICHIER NE DOIT PAS S'APPELER `passenger_wsgi.py`.
cPanel génère lui-même un `passenger_wsgi.py` dont le seul rôle est de charger
le « fichier de démarrage » déclaré pour l'application, puis d'en exporter
`application`. Déclarer `passenger_wsgi.py` comme fichier de démarrage le fait
donc se charger lui-même : `RecursionError` au démarrage et erreur 500. Le
fichier de démarrage doit porter un autre nom — celui-ci.

Il doit exposer une variable nommée `application`.
"""

import os
import sys
from pathlib import Path

# Le répertoire de l'application doit être importable quel que soit le
# répertoire de travail choisi par Passenger.
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# cPanel installe les dépendances dans un environnement virtuel dédié. Si le
# chemin est fourni, on l'ajoute avant l'import de l'application.
VENV_SITE_PACKAGES = os.getenv("PDF2MOODLE_SITE_PACKAGES")
if VENV_SITE_PACKAGES and Path(VENV_SITE_PACKAGES).is_dir():
    sys.path.insert(0, VENV_SITE_PACKAGES)

from a2wsgi import ASGIMiddleware  # noqa: E402

from app.main import app as asgi_app  # noqa: E402

application = ASGIMiddleware(asgi_app)
