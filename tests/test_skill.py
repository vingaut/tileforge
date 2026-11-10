"""Tests de la compétence agent et des fiches de cas.

La compétence `tileforge-rea` est versionnée avec le dépôt : elle doit rester
découvrable (frontmatter valide) et ses références ne doivent pas disparaître.
Les fiches de cas sont la mémoire des extractions : un index sans fichier, ou
un modèle absent, casserait la promesse « ne pas repartir de zéro ».
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".dsh" / "skills" / "tileforge-rea"


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), path
    end = text.find("\n---\n", 4)
    assert end > 0, path
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip('"')
    return fields


def test_competence_presente_et_valide():
    path = SKILL / "SKILL.md"
    assert path.exists(), path
    fields = _frontmatter(path)
    assert fields.get("name") == "tileforge-rea"
    assert fields.get("description")
    assert fields.get("whenToUse")
    body = path.read_text(encoding="utf-8")
    assert "tileforge_open_disk" in body
    assert "rea_describe" in body


def test_references_de_la_competence():
    for name in ("tool-map.md", "platforms.md", "repo-workflow.md"):
        path = SKILL / "references" / name
        assert path.exists(), path
        assert path.stat().st_size > 500, path


def test_fiches_de_cas():
    folder = ROOT / "docs" / "cases"
    assert (folder / "README.md").exists()
    assert (folder / "TEMPLATE.md").exists()
    assert (folder / "zelda-nes.md").exists()
    assert (folder / "project-x-amiga.md").exists()
    index = (folder / "README.md").read_text(encoding="utf-8")
    for name in ("zelda-nes.md", "project-x-amiga.md", "TEMPLATE.md"):
        assert name in index, name
