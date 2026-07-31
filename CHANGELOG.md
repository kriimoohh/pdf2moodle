# Journal des modifications

## 2026-07-31

### Mise en production

Première mise en ligne sur O2Switch (cPanel + Passenger), avec certificat
Let's Encrypt et authentification HTTP Basic.

Trois problèmes que seul le déploiement réel a révélés, tous corrigés :

- **Le point d'entrée Passenger se chargeait lui-même.** cPanel génère son
  propre `passenger_wsgi.py`, dont l'unique rôle est de charger le « fichier de
  démarrage » déclaré. Déclarer `passenger_wsgi.py` comme fichier de démarrage
  provoquait donc une `RecursionError` et une erreur 500. Le point d'entrée
  s'appelle désormais `wsgi_entry.py`, et `tests/test_wsgi_entry.py` couvre ce
  chemin — il traverse `a2wsgi` et non uvicorn, et n'avait aucun test.

- **ModSecurity bloquait tout envoi de fichier**, quels que soient le contenu,
  l'extension et la taille. Le symptôme était trompeur : rejet en `406`, puis
  redirection interne vers `/406.shtml` routée vers l'application, qui répondait
  légitimement `404`. Désactivé sur le seul sous-domaine concerné, les autres
  domaines du compte conservant ModSecurity.

- **Le code source était lisible publiquement.** Passenger impose que la racine
  du site soit la racine du code ; le serveur web servait donc les fichiers du
  dépôt en statique, **sans passer par l'authentification de l'application**.
  Corrigé par `deploy/o2switch.htaccess`, désormais versionné.

### Documentation

- Ajout d'une section d'utilisation : choix de la qualité, dépôt sur Moodle en
  ressource « Fichier », taille maximale d'envoi et mode d'affichage.
- Documentation des pièges de déploiement ci-dessus, pour qu'un redéploiement
  ne les rencontre pas.
- Mention du stockage en clair des identifiants dans le `.htaccess` par cPanel,
  et de la réécriture de ce fichier à chaque modification de l'application.

## 2026-07-30

### Version initiale

- Conversion PDF vers page HTML autonome, entièrement en mémoire : ni le PDF
  reçu ni le HTML produit ne touchent le disque du serveur.
- Extraction du titre de chaque page, avec exclusion des dates et des numéros
  isolés, et repli sur `Page N`.
- Document produit sans numérotation ni vocabulaire de présentation : sommaire
  latéral, zoom, plein écran, suivi de lecture, le tout sans dépendance externe.
- Page d'envoi avec glisser-déposer, progression, aperçu et téléchargement.
- Authentification HTTP Basic optionnelle, activée par `TOOL_PASSWORD`.
- Suite de tests couvrant les critères d'acceptation, dont le comportement réel
  du document dans un navigateur.
- Deux chemins de déploiement outillés : Passenger (O2Switch) et Docker
  (Railway).
