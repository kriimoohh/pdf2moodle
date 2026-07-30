# pdf2moodle

Convertit un PDF de cours en **une page HTML autonome**, prête à déposer comme
ressource « Fichier » sur Moodle.

Le fichier produit ne dépend d'aucune ressource externe : styles, script et
images sont intégrés au fichier, qui s'ouvre donc hors ligne. Il embarque un
sommaire latéral, un zoom, un mode plein écran et un suivi de lecture.

**Rien n'est conservé sur le serveur.** Le PDF reçu et le HTML produit ne sont
jamais écrits sur disque : tout le traitement se fait en mémoire et le résultat
est renvoyé directement dans la réponse HTTP.

---

## Démarrage rapide

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

L'interface est sur <http://127.0.0.1:8000>.

Lancer les tests :

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/playwright install chromium   # pour les tests navigateur
.venv/bin/pytest -q
```

`tests/test_browser.py` ouvre le document produit dans Chromium — en `file://`,
donc exactement comme un fichier téléchargé depuis Moodle — et vérifie le zoom,
le sommaire, le suivi de lecture et le panneau mobile. Ces tests sont ignorés
automatiquement si Playwright n'est pas installé.

---

## Configuration

Tout se règle par variables d'environnement ; les valeurs par défaut
conviennent à un usage courant.

| Variable | Défaut | Rôle |
|---|---|---|
| `TOOL_PASSWORD` | *(vide)* | Si défini, protège l'outil par authentification HTTP Basic. Vide = accès libre. |
| `TOOL_USERNAME` | `moodle` | Nom d'utilisateur associé. |
| `MAX_UPLOAD_MB` | `50` | Taille maximale du PDF accepté. |
| `MAX_PAGES` | `150` | Nombre maximal de pages. |
| `RENDER_TIMEOUT_SECONDS` | `120` | Budget de rendu ; au-delà, réponse `504`. |

> Sur un sous-domaine public, **définissez `TOOL_PASSWORD`**. Sans lui, l'outil
> est ouvert à tous.

---

## API

### `POST /api/convert`

`multipart/form-data` :

| Champ | Obligatoire | Description |
|---|---|---|
| `file` | oui | Le PDF (50 Mo / 150 pages maximum). |
| `badge` | non | Petite étiquette au-dessus du titre. |
| `title` | non | Titre du document. À défaut, déduit du nom du fichier. |
| `subtitle` | non | Sous-titre. |
| `author` | non | Ligne d'auteur. |
| `quality` | non | `low` \| `medium` \| `high` (défaut `medium`). |

Réponse : le HTML en pièce jointe
(`Content-Disposition: attachment`, `Content-Type: text/html`), avec un
en-tête `X-Page-Count`.

Les paliers de qualité correspondent aux facteurs d'échelle PyMuPDF
`1.2` / `1.6` / `2.2` et aux qualités JPEG `72` / `82` / `88`.

En cas d'échec, la réponse est un JSON `{"error": "…"}` avec un code adapté :

| Code | Cas |
|---|---|
| `400` | Fichier absent, non-PDF, vide, corrompu ou protégé par mot de passe. |
| `413` | Fichier trop volumineux ou trop de pages. |
| `422` | Champ `file` manquant dans la requête. |
| `504` | Budget de rendu dépassé. |

### `GET /healthz`

Sonde de disponibilité, volontairement accessible sans authentification.

---

## Déploiement

### Option A — O2Switch (cPanel + Passenger)

1. **Sous-domaine.** Dans cPanel → *Domaines*, créez `pdf2moodle.sakai.sn`
   pointant vers un répertoire dédié, par exemple `~/apps/pdf2moodle`.

2. **Application Python.** cPanel → *Setup Python App* → *Create Application* :
   - Version de Python : **3.12** (ou la plus récente proposée)
   - *Application root* : `pdf2moodle`
   - *Application URL* : le sous-domaine créé
   - *Application startup file* : **`wsgi_entry.py`**
   - *Application Entry point* : `application`

   > **Ne déclarez pas `passenger_wsgi.py` comme fichier de démarrage.** cPanel
   > génère ce fichier lui-même, avec pour seul rôle de charger le fichier de
   > démarrage déclaré. Le désigner revient à le faire se charger lui-même :
   > `RecursionError` et erreur 500 au démarrage. D'où le nom `wsgi_entry.py`.

   Notez la commande `source .../bin/activate` affichée par cPanel : elle
   contient le chemin de l'environnement virtuel créé pour vous.

3. **Code et dépendances.** Déposez le dépôt dans `apps/pdf2moodle`
   (Git ou envoi de fichiers), puis en SSH :

   ```bash
   source ~/virtualenv/apps/pdf2moodle/3.12/bin/activate
   cd ~/apps/pdf2moodle
   pip install -r requirements.txt
   ```

   `pymupdf` s'installe depuis une roue précompilée : ni compilateur, ni
   `poppler-utils`, ni autre binaire système n'est requis.

4. **Variables d'environnement.** Toujours dans *Setup Python App*, section
   *Environment variables*, ajoutez au minimum :

   ```
   TOOL_PASSWORD = <un mot de passe solide>
   TOOL_USERNAME = <votre identifiant>
   ```

5. **Limite d'envoi côté serveur web.** Créez un `.htaccess` à la racine du
   sous-domaine — la limite applicative de FastAPI ne dispense pas de celle du
   serveur, qui rejette la requête plus tôt et sans consommer de mémoire :

   ```apache
   # 50 Mo, aligné sur MAX_UPLOAD_MB
   LimitRequestBody 52428800
   ```

6. **Redémarrage.** Bouton *Restart* de *Setup Python App*, puis vérifiez :

   ```bash
   curl https://pdf2moodle.sakai.sn/healthz
   ```

**Pourquoi `a2wsgi` plutôt qu'uvicorn en sous-processus ?** Passenger pilote
des applications WSGI ; `a2wsgi.ASGIMiddleware` fait tourner l'application ASGI
dans une boucle d'événements du processus Passenger lui-même. Aucun port à
réserver, aucun second processus à surveiller, et Passenger garde la maîtrise
des arrêts et redémarrages. Le lancement d'uvicorn en sous-processus fonctionne
aussi mais laisse des processus orphelins lors des rechargements.

### Option B — Railway

1. **Projet.** *New Project* → *Deploy from GitHub repo* → ce dépôt.
   Le `Dockerfile` et `railway.json` fournis sont détectés automatiquement ;
   `railway.json` déclare la sonde `/healthz`.

2. **Variables.** Onglet *Variables* :

   ```
   TOOL_PASSWORD = <un mot de passe solide>
   TOOL_USERNAME = <votre identifiant>
   ```

   `PORT` est injecté par Railway, ne le définissez pas.

3. **Domaine.** *Settings* → *Networking* → *Custom Domain* :
   `pdf2moodle.sakai.sn`, puis créez chez O2Switch l'enregistrement **CNAME**
   indiqué par Railway. Le certificat TLS est émis automatiquement.

4. **Limite d'envoi.** Le routeur Railway accepte les corps volumineux ;
   la limite de 50 Mo est appliquée par l'application (`MAX_UPLOAD_MB`).

---

## Structure du projet

```
pdf2moodle/
├── app/
│   ├── config.py                 limites, paliers de qualité, authentification
│   ├── converter.py              rendu PyMuPDF et extraction des titres
│   ├── html_builder.py           assemblage du document autonome
│   ├── main.py                   application FastAPI et routes
│   ├── templates/
│   │   ├── index.html            page d'envoi
│   │   └── document.html.j2      gabarit du document produit
│   └── static/                   styles et script de la page d'envoi
├── tests/
│   ├── fixtures/                 PDF d'exemple (générés, versionnés)
│   ├── make_fixtures.py          génération des PDF d'exemple
│   ├── test_acceptance.py        critères d'acceptation
│   ├── test_browser.py           comportement réel dans Chromium
│   └── test_auth.py              protection par mot de passe
├── wsgi_entry.py                 point d'entrée Passenger (O2Switch)
├── Dockerfile / railway.json / Procfile
└── requirements.txt
```

---

## Extraction des titres

Le titre de chaque page provient de `page.get_text("dict")` : les blocs de
texte sont triés de haut en bas, puis de gauche à droite, et le premier bloc
*substantiel* est retenu.

Sont écartés :

- les blocs de moins de 3 caractères ;
- les dates (`12/03/2025`, `2025-03-12`, `14 mars 2025`) — sur un support de
  cours, la date de séance est souvent placée **au-dessus** du vrai titre ;
- les blocs composés uniquement de chiffres et de ponctuation (numéros de page,
  `3/40`, puces isolées).

Si aucun bloc ne convient — page sans couche texte, page vide — le titre
retombe sur `Page N`. Dans le sommaire, les titres sont tronqués à
60 caractères ; le libellé au-dessus de chaque image reste complet.

---

## Le document produit

- **Sommaire** fixe à gauche (280 px), numéroté en CSS, avec suivi de la
  lecture par `IntersectionObserver`. En dessous de 900 px de large il devient
  un panneau coulissant ouvert par le bouton ☰.
- **Zoom** de 60 % à 160 % par paliers de 10 %. La largeur du conteneur est
  compensée (`width: 100/niveau %`) pour qu'aucun débordement horizontal
  n'apparaisse. Un clic sur l'indicateur revient à 100 %.
- **Plein écran** via `requestFullscreen()`, avec repli `webkit` pour Safari.
- **Impression** : barre d'outils et sommaire masqués, pages non coupées.

Chaque page porte **uniquement son titre extrait** : aucun compteur, aucune
numérotation, et aucun vocabulaire de présentation — ni dans le texte visible,
ni dans les attributs `alt`, ni dans le code. C'est vérifié automatiquement par
`test_no_banned_vocabulary_anywhere`.

---

## Confidentialité

- Le PDF reçu reste **en mémoire vive** du début à la fin.
  Starlette confie normalement les fichiers reçus à un `SpooledTemporaryFile`
  dont le seuil de débordement est de 1 Mo — au-delà, le contenu part sur le
  disque. `app/main.py` relève ce seuil au-dessus de la taille maximale
  acceptée pour que cela n'arrive jamais. Le test
  `test_upload_never_rolls_over_to_disk` instrumente `rollover()` et vérifie
  qu'elle n'est jamais appelée avec un PDF de plus de 1 Mo.
- Les journaux ne contiennent que des métriques anonymes : nombre de pages,
  palier de qualité, durée, taille de sortie. Jamais de nom de fichier, jamais
  de contenu.
- La réponse porte `Cache-Control: no-store`.

## Validation des entrées

Le `Content-Type` annoncé par le navigateur n'est qu'un premier filtre : il est
déclaratif et falsifiable. La validation qui fait foi porte sur la signature du
fichier (`%PDF-`), puis sur son ouverture effective par PyMuPDF. Les PDF
chiffrés sont refusés avec un message explicite.

Les champs du formulaire sont échappés à l'insertion dans le document, et le
nom du fichier de sortie est translittéré en ASCII puis filtré — ce qui écarte
aussi bien la traversée de répertoire que l'injection dans l'en-tête
`Content-Disposition`.
