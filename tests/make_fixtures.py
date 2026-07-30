"""Génère les PDF de test versionnés dans `tests/fixtures/`.

Exécuter après modification pour régénérer :  python -m tests.make_fixtures
"""

from __future__ import annotations

from pathlib import Path

import fitz

FIXTURES_DIR = Path(__file__).parent / "fixtures"

PAGE_SIZE = (720, 540)  # 4:3, format habituel d'un export de présentation


def _new_doc() -> fitz.Document:
    return fitz.open()


def _add_page(doc: fitz.Document) -> fitz.Page:
    return doc.new_page(width=PAGE_SIZE[0], height=PAGE_SIZE[1])


def _text(page: fitz.Page, x: float, y: float, value: str, size: int = 12) -> None:
    page.insert_text((x, y), value, fontsize=size, fontname="helv")


# --------------------------------------------------------------------------
# 1. Support « propre » : un titre net en haut de chaque page.
# --------------------------------------------------------------------------

NORMAL_TITLES = [
    "Introduction aux systèmes distribués",
    "Modèles de cohérence",
    "Le théorème CAP",
    "Réplication et tolérance aux pannes",
    "Consensus : Paxos et Raft",
    "Étude de cas : stockage clé-valeur",
]


def build_normal(path: Path) -> None:
    doc = _new_doc()
    for index, title in enumerate(NORMAL_TITLES, start=1):
        page = _add_page(doc)
        _text(page, 48, 80, title, size=26)
        _text(page, 48, 140, "Point clé numéro un de cette partie.", size=14)
        _text(page, 48, 170, "Point clé numéro deux, avec un peu de détail.", size=14)
        _text(page, 620, 510, str(index), size=10)
    doc.save(str(path))
    doc.close()


# --------------------------------------------------------------------------
# 2. Support « piégeux » : dates en tête de page, numéros isolés, page vide.
#    Vérifie que l'extraction ne retient pas la date placée au-dessus du titre.
# --------------------------------------------------------------------------

TRICKY_TITLES = [
    "Rappels sur les graphes",
    "Parcours en largeur",
    "Parcours en profondeur",
]


def build_tricky(path: Path) -> None:
    doc = _new_doc()

    # Pages où une date est le bloc le plus haut, avant le vrai titre.
    for offset, title in enumerate(TRICKY_TITLES):
        page = _add_page(doc)
        _text(page, 48, 40, f"1{offset}/03/2025", size=11)
        _text(page, 48, 100, title, size=26)
        _text(page, 48, 160, "Contenu de la partie.", size=14)

    # Page dont le seul texte est un numéro : doit retomber sur « Page 4 ».
    page = _add_page(doc)
    _text(page, 350, 500, "4", size=11)

    # Page totalement vide : doit retomber sur « Page 5 ».
    _add_page(doc)

    # Page dont le premier bloc est une date en toutes lettres.
    page = _add_page(doc)
    _text(page, 48, 40, "14 mars 2025", size=11)
    _text(page, 48, 100, "Synthèse et exercices", size=26)

    doc.save(str(path))
    doc.close()


# --------------------------------------------------------------------------
# 3. Support « image pure » : aucune couche texte, uniquement des tracés.
#    Toutes les pages doivent retomber sur « Page N ».
# --------------------------------------------------------------------------


def build_image_only(path: Path) -> None:
    doc = _new_doc()
    for index in range(4):
        page = _add_page(doc)
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(40, 40, 680, 500))
        shape.finish(color=(0.08, 0.15, 0.26), fill=(0.93, 0.95, 0.97), width=2)
        for step in range(5):
            top = 90 + step * 70
            shape.draw_rect(fitz.Rect(80, top, 80 + 90 * (index + step % 3 + 1), top + 40))
            shape.finish(color=None, fill=(0.11, 0.66, 0.86))
        shape.commit()
    doc.save(str(path))
    doc.close()


# --------------------------------------------------------------------------
# 4. Support volumineux : 30 pages, pour le critère de durée (< 15 s).
# --------------------------------------------------------------------------


def build_large(path: Path, page_count: int = 30) -> None:
    doc = _new_doc()
    for index in range(1, page_count + 1):
        page = _add_page(doc)
        _text(page, 48, 80, f"Chapitre {index} — Notions fondamentales", size=24)
        for line in range(8):
            _text(page, 48, 140 + line * 26, f"Ligne de contenu numéro {line + 1}.", size=13)
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(430, 130, 680, 400))
        shape.finish(color=(0.11, 0.66, 0.86), fill=(0.88, 0.94, 0.98), width=1.5)
        shape.commit()
    doc.save(str(path))
    doc.close()


BUILDERS = {
    "cours-normal.pdf": build_normal,
    "cours-titres-pieges.pdf": build_tricky,
    "cours-image-pure.pdf": build_image_only,
    "cours-30-pages.pdf": build_large,
}


def build_all(directory: Path = FIXTURES_DIR) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    built = {}
    for name, builder in BUILDERS.items():
        path = directory / name
        if not path.exists():
            builder(path)
        built[name] = path
    return built


if __name__ == "__main__":
    for name, path in build_all().items():
        print(f"{name}: {path.stat().st_size / 1024:.0f} Ko")
