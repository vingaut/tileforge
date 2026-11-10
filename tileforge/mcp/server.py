"""Serveur MCP de TileForge : outils exposés à un assistant.

Le protocole MCP (Model Context Protocol) est un JSON-RPC 2.0 sur entrée/sortie
standard, une ligne par message.  Ce module n'a **aucune dépendance externe** :
il n'utilise que la bibliothèque standard, ce qui permet de l'embarquer dans
l'application compilée.

Lancement :

    python -m tileforge --mcp

puis déclaration côté client (Claude Desktop, etc.) :

    {
      "mcpServers": {
        "tileforge": {
          "command": "/chemin/vers/.venv/bin/python",
          "args": ["-m", "tileforge", "--mcp"]
        }
      }
    }

Le serveur travaille sur des fichiers (ROM, projets, images) et renvoie des
chemins absolus vers les aperçus PNG : un assistant peut donc regarder les
images produites avant de décider de la suite.
"""

from __future__ import annotations

import json
import sys
import traceback
from collections.abc import Callable
from typing import Any

from ..version import APP_NAME, __version__

PROTOCOL_VERSION = "2024-11-05"


# ---------------------------------------------------------------------------
# Définition des outils
# ---------------------------------------------------------------------------


class Tool:
    def __init__(self, name: str, description: str, schema: dict,
                 function: Callable[..., Any]):
        self.name = name
        self.description = description
        self.schema = schema
        self.function = function

    def as_dict(self) -> dict:
        return {"name": self.name, "description": self.description,
                "inputSchema": self.schema}


def _obj(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties,
            "required": required or [], "additionalProperties": False}


_STR = {"type": "string"}
_INT = {"type": "integer"}
_BOOL = {"type": "boolean"}
_NUM = {"type": "number"}


def _build_tools() -> list[Tool]:
    from . import tools as T

    return [
        Tool("tileforge_inspect_file",
             "Analyse un fichier (ROM, banque, projet) : taille, en-tête SNES ou "
             "Mega Drive, titre, et si c'est une image.",
             _obj({"path": _STR, "archive_member": _STR}, ["path"]),
             T.inspect_file),

        Tool("tileforge_list_archive",
             "Liste les fichiers d'une archive zip/7z (ROMs, notices, disques) "
             "et indique le membre choisi par défaut. À utiliser avant "
             "d'analyser une ROM archivée : passez ensuite archive_member aux "
             "autres outils.",
             _obj({"path": _STR}, ["path"]), T.list_archive),

        Tool("tileforge_list_tile_formats",
             "Liste les formats de tuiles connus (SNES, Mega Drive, Atari ST, "
             "Amiga, CPC…).",
             _obj({}), T.list_tile_formats),

        Tool("tileforge_list_systems",
             "Liste les machines du catalogue (résolutions, couleurs, tailles de "
             "tuile).",
             _obj({"family": {**_STR, "enum": ["console", "computer", "arcade", ""]}}),
             T.list_systems),

        Tool("tileforge_read_palette",
             "Lit une palette directement dans un fichier (BGR555 SNES, 0BGR Mega "
             "Drive, 0RGB Atari ST) et renvoie les couleurs RGB.",
             _obj({"path": _STR, "offset": _INT,
                   "kind": {**_STR, "enum": ["snes", "megadrive", "atari_st", "raw8"]},
                   "count": _INT, "archive_member": _STR},
                  ["path", "offset"]), T.read_palette),

        Tool("tileforge_cartography",
             "Cartographie une ROM : plateforme reconnue à l'en-tête, zones "
             "classées par entropie (vide, données, code, compressé) et tables "
             "de pointeurs probables. À appeler avant de chercher des graphismes.",
             _obj({"path": _STR, "window": _INT, "archive_member": _STR},
                  ["path"]), T.cartography),

        Tool("tileforge_disassemble",
             "Désassemble du code 6502 (NES, C64, Apple II) ou 65816 (SNES). "
             "Avec « entry », suit "
             "le fil d'exécution depuis une adresse processeur (0x8000 = reset "
             "d'une ROM LoROM) au lieu de désassembler linéairement : c'est ce "
             "qui distingue le code des données.",
             _obj({"path": _STR, "offset": _INT, "count": _INT,
                   "entry": _INT, "layout": _STR, "cpu": _STR,
                   "base": _INT, "archive_member": _STR}, ["path"]),
             T.disassemble),

        Tool("tileforge_scan_graphics",
             "Cherche des graphismes dans un fichier : essaie les décompresseurs "
             "et les données brutes, note chaque candidat et écrit un aperçu PNG "
             "pour chacun. C'est l'outil à utiliser pour une ROM inconnue.",
             _obj({"path": _STR, "start": _INT, "end": _INT,
                   "tile_format": _STR, "compression": _STR,
                   "min_size": _INT, "max_size": _INT, "threshold": _NUM,
                   "limit": _INT, "preview": _BOOL, "budget": _NUM,
                   "structured_only": _BOOL, "extended": _BOOL,
                   "workers": _INT, "archive_member": _STR}, ["path"]),
             T.scan_graphics),

        Tool("tileforge_list_emulator_cores",
             "Liste les cœurs libretro installés (RetroArch, paquets système) : "
             "chemin, nom et machine devinée. Aucun cœur n'est fourni avec "
             "TileForge ; installez celui de votre console.",
             _obj({"extra_paths": {"type": "array", "items": _STR}}),
             T.list_emulator_cores),

        Tool("tileforge_emulator_memory",
             "Exécute une ROM dans un émulateur libretro pendant N trames, puis "
             "lit la RAM système et la VRAM : les graphismes y sont déjà "
             "décompressés. Écrit un instantané (régions .bin + manifeste JSON) "
             "et, avec scan=true, balaye la mémoire comme une banque brute. "
             "C'est la voie de secours quand le compresseur du jeu est inconnu.",
             _obj({"core": _STR, "rom": _STR, "frames": _INT, "buttons": _STR,
                   "output": _STR, "name": _STR, "screenshot": _BOOL,
                   "scan": _BOOL, "tile_format": _STR, "compression": _STR,
                   "budget": _NUM, "limit": _INT, "extended": _BOOL,
                   "archive_member": _STR, "system_dir": _STR},
                  ["core", "rom"]),
             T.emulator_memory),

        Tool("tileforge_identify_format",
             "Devine le format de tuiles d'un bloc inconnu : taille, profondeur, "
             "disposition. Chaque format candidat est comparé à son plancher de "
             "bruit ; le classement renvoie une marge, pas une note brute.",
             _obj({"path": _STR, "offset": _INT, "length": _INT,
                   "formats": {"type": "array", "items": _STR},
                   "archive_member": _STR}, ["path"]),
             T.identify_format),

        Tool("tileforge_preview_tiles",
             "Décode une plage d'octets en tuiles et écrit un PNG : sert à "
             "vérifier un offset, un format ou une compression.",
             _obj({"path": _STR, "offset": _INT, "tile_format": _STR,
                   "compression": _STR, "palette": _STR, "palette_offset": _INT,
                   "palette_kind": _STR, "count": _INT, "per_row": _INT,
                   "output": _STR, "archive_member": _STR}, ["path"]),
             T.preview_tiles),

        Tool("tileforge_open_bank",
             "Ouvre une banque de tuiles dans le projet du serveur : ROM, offset, "
             "format de tuile, compression et palette. Les appels suivants "
             "(auto-assemblage, atlas) travaillent sur ce projet.",
             _obj({"path": _STR, "offset": _INT, "tile_format": _STR,
                   "compression": _STR, "count": _INT, "per_row": _INT,
                   "palette": _STR, "palette_offset": _INT, "palette_kind": _STR,
                   "archive_member": _STR}, ["path"]), T.open_bank),

        Tool("tileforge_project_info",
             "Résume le projet ouvert : nombre de tuiles, grille, sprites "
             "validés, atlas.",
             _obj({}), T.project_info),

        Tool("tileforge_list_tiles",
             "Liste les tuiles du projet avec leur indice de stockage et leur "
             "rectangles.",
             _obj({"offset": _INT, "limit": _INT}), T.list_tiles),

        Tool("tileforge_auto_assemble",
             "Classe des assemblages automatiques pour un groupe de tuiles et "
             "renvoie les meilleurs avec leur coût.",
             _obj({"cols": _INT, "rows": _INT, "group": _INT,
                   "method": _STR, "limit": _INT}, []), T.auto_assemble),

        Tool("tileforge_render_sprite",
             "Compose un sprite à partir d'une liste de tuiles (ordre = cases de "
             "la grille) et écrit un PNG.",
             _obj({"tiles": {"type": "array", "items": _INT},
                   "cols": _INT, "rows": _INT, "output": _STR}, ["tiles"]),
             T.render_sprite),

        Tool("tileforge_validate_sprite",
             "Ajoute un sprite au projet (et à l'atlas) à partir d'un assemblage "
             "renvoyé par auto_assemble.",
             _obj({"cols": _INT, "rows": _INT,
                   "tiles": {"type": "array", "items": _INT},
                   "name": _STR}, ["tiles"]), T.validate_sprite),

        Tool("tileforge_save_project",
             "Enregistre le projet courant au format .tileforge.json.",
             _obj({"path": _STR}, ["path"]), T.save_project),

        Tool("tileforge_export_atlas",
             "Écrit l'atlas des sprites validés en PNG.",
             _obj({"path": _STR}, ["path"]), T.export_atlas),

        Tool("tileforge_open_disk",
             "Ouvre une image de disquette Amiga (ADF, ADZ, HDF) et liste son "
             "arborescence. Les checksums invalides sont signalés mais ne "
             "bloquent pas l'ouverture : une bonne partie du catalogue Amiga "
             "est protégée (Copylock). Les IPF/DMS sont détectés et expliqués.",
             _obj({"path": _STR, "archive_member": _STR}, ["path"]),
             T.open_disk),

        Tool("tileforge_extract_disk_file",
             "Extrait un fichier d'un disque Amiga vers le dossier de travail "
             "et renvoie son chemin, sa taille et ses avertissements.",
             _obj({"path": _STR, "node_path": _STR, "output": _STR,
                   "archive_member": _STR}, ["path", "node_path"]),
             T.extract_disk_file),

        Tool("tileforge_decompress_nested",
             "Descend récursivement dans les formats imbriqués (Imploder, RNC, "
             "hunk) : rescane chaque bloc décompressé et écrit les résultats. "
             "C'est ce qui débloque les planches de sprites cachées dans un "
             "exécutable recompressé.",
             _obj({"path": _STR, "offset": _INT, "max_depth": _INT,
                   "key": _INT, "archive_member": _STR}, ["path"]),
             T.decompress_nested),

        Tool("tileforge_amiga_screen",
             "Rend un écran Amiga planaire (row-major ou plane-major) avec "
             "largeur, hauteur, plans et pas de ligne libres. Sans géométrie, "
             "la détecte par cohérence de voisinage ; signale les plans vides "
             "et le bourrage de fin de ligne.",
             _obj({"path": _STR, "offset": _INT, "width": _INT,
                   "height": _INT, "planes": _INT, "layout": _STR,
                   "stride": _INT, "palette_offset": _INT,
                   "palette_count": _INT, "output": _STR,
                   "archive_member": _STR}, ["path"]),
             T.amiga_screen),

        Tool("tileforge_amiga_sprites",
             "Découpe une planche Amiga en sprites par composantes connexes, "
             "détecte la grille et les copies pré-décalées, puis écrit une "
             "planche PNG RGBA (index 0 transparent).",
             _obj({"path": _STR, "offset": _INT, "width": _INT,
                   "height": _INT, "planes": _INT, "layout": _STR,
                   "stride": _INT, "palette_offset": _INT,
                   "palette_count": _INT, "min_area": _INT,
                   "close_radius": _INT, "columns": _INT, "output": _STR,
                   "archive_member": _STR}, ["path"]),
             T.amiga_sprites),

        Tool("tileforge_amiga_analyze",
             "Analyse un binaire Amiga : table des hunks (segments, adresses "
             "de chargement, relogements), listes copper (plans, palette, "
             "géométrie) et blocs imbriqués à décompresser.",
             _obj({"path": _STR, "offset": _INT, "archive_member": _STR},
                  ["path"]), T.amiga_analyze),
    ]


# ---------------------------------------------------------------------------
# Serveur
# ---------------------------------------------------------------------------


class McpServer:
    def __init__(self, stdin=None, stdout=None):
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.tools = {tool.name: tool for tool in _build_tools()}
        self.initialized = False

    # -- transport ----------------------------------------------------------

    def log(self, message: str) -> None:
        print(f"[tileforge-mcp] {message}", file=sys.stderr, flush=True)

    def send(self, payload: dict) -> None:
        self.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.stdout.flush()

    def error(self, request_id, code: int, message: str) -> None:
        self.send({"jsonrpc": "2.0", "id": request_id,
                   "error": {"code": code, "message": message}})

    def serve_forever(self) -> int:
        self.log(f"{APP_NAME} {__version__} — serveur MCP prêt ({len(self.tools)} outils)")
        for line in self.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                self.log(f"message illisible : {exc}")
                continue
            try:
                self.handle(message)
            except Exception:
                self.log(traceback.format_exc())
        return 0

    # -- protocole ----------------------------------------------------------

    def handle(self, message) -> None:
        if isinstance(message, list):
            for item in message:
                self.handle(item)
            return
        if not isinstance(message, dict):
            return
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}

        if method is None:
            return                                  # réponse du client
        if request_id is None:
            # notification : pas de réponse
            if method == "notifications/initialized":
                self.initialized = True
            return

        if method == "initialize":
            self.send({"jsonrpc": "2.0", "id": request_id, "result": {
                "protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
                "capabilities": {"tools": {"listChanged": False},
                                 "resources": {"subscribe": False,
                                               "listChanged": False}},
                "serverInfo": {"name": "tileforge", "version": __version__},
                "instructions": (
                    "TileForge découpe et recompose des sprites de jeux 8/16 bits. "
                    "Commencez par tileforge_inspect_file, puis "
                    "tileforge_scan_graphics sur une ROM inconnue : chaque "
                    "candidat renvoie un aperçu PNG à regarder. "
                    "tileforge_open_bank charge ensuite la banque choisie et "
                    "tileforge_auto_assemble propose des assemblages. Pour un "
                    "jeu Amiga, ouvrez le disque avec tileforge_open_disk, "
                    "descendez les blocs avec tileforge_decompress_nested, puis "
                    "rendez l'écran avec tileforge_amiga_screen."),
            }})
            return

        if method == "ping":
            self.send({"jsonrpc": "2.0", "id": request_id, "result": {}})
            return

        if method == "tools/list":
            self.send({"jsonrpc": "2.0", "id": request_id, "result": {
                "tools": [tool.as_dict() for tool in self.tools.values()]}})
            return

        if method == "tools/call":
            self.call_tool(request_id, params)
            return

        if method == "resources/list":
            self.send({"jsonrpc": "2.0", "id": request_id,
                       "result": {"resources": []}})
            return

        if method == "prompts/list":
            self.send({"jsonrpc": "2.0", "id": request_id,
                       "result": {"prompts": []}})
            return

        self.error(request_id, -32601, f"méthode inconnue : {method}")

    def call_tool(self, request_id, params: dict) -> None:
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        tool = self.tools.get(name)
        if tool is None:
            self.error(request_id, -32602, f"outil inconnu : {name}")
            return
        try:
            result = tool.function(**arguments)
        except TypeError as exc:
            self.error(request_id, -32602, f"arguments invalides : {exc}")
            return
        except Exception as exc:
            self.send({"jsonrpc": "2.0", "id": request_id, "result": {
                "content": [{"type": "text", "text": f"Erreur : {exc}"}],
                "isError": True}})
            return
        self.send({"jsonrpc": "2.0", "id": request_id, "result": {
            "content": [{"type": "text", "text": _format_result(result)}],
            "isError": False}})


def _format_result(result) -> str:
    """Rend un résultat lisible par un modèle : texte + JSON."""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        images = [v for k, v in result.items() if k.endswith("_png")]
        text = {k: v for k, v in result.items() if not k.endswith("_png")}
        body = json.dumps(text, ensure_ascii=False, indent=1)
        if images:
            body += "\n\nAperçus : " + ", ".join(str(i) for i in images)
        return body
    return json.dumps(result, ensure_ascii=False, indent=1)


def main(argv: list[str] | None = None) -> int:
    return McpServer().serve_forever()


if __name__ == "__main__":
    sys.exit(main())
