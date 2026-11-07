# Connecter un LLM au MCP de TileForge

TileForge expose un serveur **MCP** (Model Context Protocol) en **stdio** : le
client LLM lance lui-même la commande, puis échange du JSON-RPC 2.0 sur
l'entrée/sortie standard. Il n'y a **ni port à ouvrir ni serveur à démarrer à la
main** : si `python -m tileforge --mcp` fonctionne dans un terminal, le client
peut le lancer.

## 1. Vérifier l'installation

Depuis le dépôt :

```bash
cd /path/to/tileforge
.venv/bin/python -m tileforge --selftest
.venv/bin/python tools/mcp_config.py --check
```

La seconde commande fait un vrai handshake MCP et doit afficher :

```
TileForge 1.4.0 — 20 outils MCP disponibles.
  tileforge_inspect_file
  tileforge_list_archive
  ...
```

Si elle échoue avec `ModuleNotFoundError: numpy`, c'est que le Python utilisé
n'est pas celui du venv. Le générateur de configuration règle ce problème.

## 1 bis. Découverte automatique par projet

Le dépôt contient déjà trois configurations de projet :

| Client | Fichier | Découverte |
|---|---|---|
| Claude Code | `.mcp.json` | oui, au lancement dans le dossier du projet |
| VS Code | `.vscode/mcp.json` | oui, puis **MCP: List Servers ▸ tileforge ▸ Start** |
| Cursor | `.cursor/mcp.json` | oui, au rechargement de la fenêtre |

Elles utilisent le Python relatif `.venv/bin/python` (ou
`${workspaceFolder}/.venv/bin/python` pour VS Code). Si vous ouvrez le dépôt
TileForge comme espace de travail, le client découvre donc le serveur sans
configuration supplémentaire. **Claude Desktop ne fait pas de découverte de
projet** : il faut passer par le fichier global ci-dessous.

## 2. Générer la configuration

```bash
python tools/mcp_config.py                    # Claude Desktop (JSON)
python tools/mcp_config.py --client cursor    # Cursor
python tools/mcp_config.py --client vscode    # VS Code
python tools/mcp_config.py --client claude-code
python tools/mcp_config.py --write ~/.config/Claude/claude_desktop_config.json
```

Le script utilise l'interpréteur courant **sans résoudre le lien symbolique**
(`.venv/bin/python` reste le Python du venv, pas `/usr/bin/python3`) et peut
ajouter `TILEFORGE_MCP_DIR` pour les aperçus PNG. Le champ `cwd` n'est ajouté
que pour VS Code, qui le documente ; les autres clients n'en ont pas besoin
avec un chemin de Python absolu.

Exemple produit :

```json
{
  "mcpServers": {
    "tileforge": {
      "command": "/path/to/tileforge/.venv/bin/python",
      "args": ["-m", "tileforge", "--mcp"]
    }
  }
}
```

## 3. Claude Desktop

Fichier de configuration :

| Système | Chemin |
|---|---|
| Linux | `~/.config/Claude/claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

Collez le JSON de `tools/mcp_config.py`, puis **quittez et relancez Claude
Desktop**. L'icône d'outils doit proposer les vingt outils `tileforge_*`.
Demandez par exemple :

> Liste les fichiers de cette archive, scanne la ROM et ouvre la meilleure
> banque de tuiles.

## 4. Claude Code

```bash
claude mcp add tileforge -- \
  /path/to/tileforge/.venv/bin/python -m tileforge --mcp
claude mcp list
```

La commande exacte est affichée par :

```bash
python tools/mcp_config.py --client claude-code
```

## 5. Cursor

Fichier global `~/.cursor/mcp.json`, ou projet `.cursor/mcp.json` :

```json
{
  "mcpServers": {
    "tileforge": {
      "command": "/path/to/tileforge/.venv/bin/python",
      "args": ["-m", "tileforge", "--mcp"]
    }
  }
}
```

Rechargez la fenêtre (ou redémarrez Cursor), puis vérifiez dans les réglages
MCP que `tileforge` est **vert** et que les outils sont listés.

## 6. VS Code

VS Code (1.102+) utilise une clé `servers` et un `type` explicite. Fichier
`.vscode/mcp.json` du projet :

```json
{
  "servers": {
    "tileforge": {
      "type": "stdio",
      "command": "/path/to/tileforge/.venv/bin/python",
      "args": ["-m", "tileforge", "--mcp"],
      "cwd": "/path/to/tileforge"
    }
  }
}
```

Puis **Command Palette ▸ MCP: List Servers ▸ tileforge ▸ Start**. Le même JSON
est produit par `python tools/mcp_config.py --client vscode`.

## 7. Cline, Roo Code, Continue…

Ces clients acceptent en général la forme `mcpServers` :

```json
{
  "mcpServers": {
    "tileforge": {
      "command": "/path/to/tileforge/.venv/bin/python",
      "args": ["-m", "tileforge", "--mcp"]
    }
  }
}
```

Pour Continue, la configuration peut être en YAML :

```yaml
mcpServers:
  - name: tileforge
    command: /path/to/tileforge/.venv/bin/python
    args: ["-m", "tileforge", "--mcp"]
    cwd: /path/to/tileforge
```

## 8. Ce que le modèle peut faire

Les vingt outils couvrent toute la chaîne :

| Étape | Outils |
|---|---|
| Ouvrir une archive | `tileforge_list_archive`, puis `archive_member` sur les autres outils |
| Inspecter | `tileforge_inspect_file`, `tileforge_cartography`, `tileforge_identify_format` |
| Chercher | `tileforge_scan_graphics` (brut + compressé, budget, `extended`) |
| Lire une banque | `tileforge_preview_tiles`, `tileforge_open_bank`, `tileforge_read_palette` |
| Assembler | `tileforge_list_tiles`, `tileforge_auto_assemble`, `tileforge_render_sprite`, `tileforge_validate_sprite` |
| Exporter | `tileforge_save_project`, `tileforge_export_atlas` |
| Émulation | `tileforge_list_emulator_cores`, `tileforge_emulator_memory` |
| Désassembler | `tileforge_disassemble` |

Chaque outil renvoie du JSON **et le chemin d'un PNG** : le modèle peut ouvrir
l'aperçu avant de décider. Les chemins de fichiers doivent être **absolus** :
le `cwd` du client n'est pas forcément celui du dépôt.

Exemples de demandes :

> Ouvre `~/roms/jeu.zip`, liste les membres, scanne la ROM avec le format
> `snes_4bpp` et ouvre la meilleure banque.

> Exécute ce jeu dans `snes9x_libretro.so` pendant 600 trames, lis la VRAM et
> cherche les tuiles ; si le score est faible, essaie `gba_4bpp`.

> Ouvre la banque, propose un assemblage 2 × 4 des huit premières tuiles,
> rends-le en PNG et valide-le.

## 9. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `ModuleNotFoundError: numpy` | le client lance le Python système, pas le venv | utilisez la commande de `tools/mcp_config.py` |
| Aucun outil visible | serveur non lancé ou JSON invalide | `python tools/mcp_config.py --check`, puis relancez le client |
| Le serveur démarre puis se ferme | le client n'envoie pas `initialize` | vérifiez la config du client (transport stdio) |
| Recherche trop longue | ROM de plusieurs Mo | passez `budget` à `tileforge_scan_graphics`, ou `structured_only=true` |
| Aperçus introuvables | dossier de travail | définissez `TILEFORGE_MCP_DIR` dans `env` |
| Archive non lue | membre ambigu | appelez `tileforge_list_archive`, puis `archive_member` |

Le serveur écrit ses journaux sur **stderr** ; stdout ne contient que le
JSON-RPC. C'est normal de ne rien voir dans le terminal quand tout va bien.

## 10. Sécurité

Le serveur lit et écrit des fichiers avec vos droits. Ne connectez que des
clients de confiance, et gardez les ROMs et les projets dans des dossiers que
vous contrôlez. Il n'y a pas d'authentification réseau : le transport stdio
signifie que le client lance un processus local, pas qu'il se connecte à un
service exposé.
