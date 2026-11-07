#!/usr/bin/env python3
"""Génère la configuration MCP de TileForge pour un client LLM.

Le serveur MCP de TileForge est un serveur **stdio** : le client lance lui-même
la commande et parle JSON-RPC sur l'entrée/sortie standard. Il n'y a ni port ni
service à démarrer à la main.

Exemples :

    python tools/mcp_config.py                     # JSON pour Claude Desktop
    python tools/mcp_config.py --client cursor     # JSON pour Cursor
    python tools/mcp_config.py --client vscode     # JSON pour VS Code
    python tools/mcp_config.py --client claude-code  # commande CLI
    python tools/mcp_config.py --check             # teste le serveur

Le script utilise l'interpréteur Python courant et le dossier du dépôt comme
``cwd`` : la configuration produite est donc directement utilisable.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
#: Ne pas résoudre le lien symbolique : ``.venv/bin/python`` pointe vers le
#: Python système, qui n'a pas les dépendances du venv.
PYTHON = Path(sys.executable)

CLIENTS = ("claude", "cursor", "vscode", "claude-code", "generic")


def server_entry(python: Path, root: Path, mcp_dir: str = "",
                 include_cwd: bool = False) -> dict:
    entry = {
        "command": str(python),
        "args": ["-m", "tileforge", "--mcp"],
    }
    # ``cwd`` est utile à VS Code, mais n'est pas documenté par tous les
    # clients ; on ne l'ajoute que là où il est supporté.
    if include_cwd:
        entry["cwd"] = str(root)
    if mcp_dir:
        entry["env"] = {"TILEFORGE_MCP_DIR": str(Path(mcp_dir).expanduser())}
    return entry


def build_config(client: str, python: Path, root: Path, mcp_dir: str = "") -> dict:
    """Configuration sérialisable pour le client demandé."""
    entry = server_entry(python, root, mcp_dir,
                         include_cwd=(client == "vscode"))
    if client == "vscode":
        return {"servers": {"tileforge": {"type": "stdio", **entry}}}
    return {"mcpServers": {"tileforge": entry}}


def claude_code_command(python: Path, root: Path, mcp_dir: str = "") -> str:
    env = f"TILEFORGE_MCP_DIR={Path(mcp_dir).expanduser()} " if mcp_dir else ""
    return (f"{env}claude mcp add tileforge -- "
            f"{python} -m tileforge --mcp")


def check_server(python: Path, root: Path, timeout: float = 20.0) -> int:
    """Lance un mini-handshake MCP et vérifie que les outils sont exposés."""
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05"}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    payload = "".join(json.dumps(message) + "\n" for message in messages)
    try:
        result = subprocess.run(
            [str(python), "-m", "tileforge", "--mcp"], input=payload,
            capture_output=True, text=True, cwd=str(root), timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Échec du lancement : {exc}", file=sys.stderr)
        return 1
    tools = None
    version = None
    for line in result.stdout.splitlines():
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get("id") == 1:
            version = (message.get("result", {}).get("serverInfo", {})
                       .get("version"))
        elif message.get("id") == 2:
            tools = message.get("result", {}).get("tools")
    if tools is None:
        print("Le serveur n'a pas répondu à tools/list.", file=sys.stderr)
        if result.stderr.strip():
            print(result.stderr.strip()[-2000:], file=sys.stderr)
        return 1
    print(f"TileForge {version or '?'} — {len(tools)} outils MCP disponibles.")
    for tool in tools:
        print(f"  {tool['name']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Génère la configuration MCP de TileForge.")
    parser.add_argument("--client", default="claude", choices=CLIENTS,
                        help="client cible (défaut : claude)")
    parser.add_argument("--python", default=str(PYTHON),
                        help="interpréteur Python à utiliser")
    parser.add_argument("--root", default=str(ROOT),
                        help="dossier du dépôt TileForge")
    parser.add_argument("--mcp-dir", default="",
                        help="dossier des aperçus PNG (TILEFORGE_MCP_DIR)")
    parser.add_argument("--write", default="",
                        help="écrit la configuration dans ce fichier")
    parser.add_argument("--check", action="store_true",
                        help="lance un handshake MCP et liste les outils")
    parser.add_argument("--list-clients", action="store_true",
                        help="affiche les clients pris en charge")
    args = parser.parse_args(argv)

    if args.list_clients:
        print("\n".join(CLIENTS))
        return 0

    python = Path(args.python).expanduser()
    if not python.is_absolute():
        python = Path.cwd() / python
    root = Path(args.root).expanduser().resolve()
    if not python.exists():
        print(f"Python introuvable : {python}", file=sys.stderr)
        return 2

    if args.check:
        return check_server(python, root)

    if args.client == "claude-code":
        output = claude_code_command(python, root, args.mcp_dir)
    else:
        output = json.dumps(
            build_config(args.client, python, root, args.mcp_dir),
            ensure_ascii=False, indent=2)

    if args.write:
        target = Path(args.write).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output + "\n", encoding="utf-8")
        print(f"Configuration écrite dans {target}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
