FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Les dépendances d'abord : la couche est réutilisée tant que le fichier
# ne change pas. PyMuPDF est distribué sous forme de roue précompilée,
# aucun paquet système supplémentaire n'est nécessaire.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Exécution sans privilèges.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# Railway fournit $PORT ; 8000 sert de valeur de repli en local.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2 --timeout-keep-alive 120"]
