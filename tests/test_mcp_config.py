"""Tests du générateur de configuration MCP.

Le but est de vérifier la chaîne réelle : le JSON produit pointe vers le Python
du venv, et un handshake MCP aboutit aux vingt outils.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "mcp_config.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, cwd=ROOT)


def test_config_claude():
    result = _run()
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    server = config["mcpServers"]["tileforge"]
    assert server["args"] == ["-m", "tileforge", "--mcp"]
    assert Path(server["command"]).name.startswith("python")
    # Le Python du venv ne doit pas être résolu vers le Python système.
    assert ".venv" in server["command"] or Path(server["command"]) == Path(
        sys.executable)


def test_config_vscode():
    result = _run("--client", "vscode")
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    server = config["servers"]["tileforge"]
    assert server["type"] == "stdio"
    assert server["args"] == ["-m", "tileforge", "--mcp"]


def test_config_claude_code():
    result = _run("--client", "claude-code")
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("claude mcp add tileforge --")
    assert "-m tileforge --mcp" in result.stdout


def test_configs_de_projet():
    """Les fichiers de projet permettent la découverte automatique."""
    root = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    assert root["mcpServers"]["tileforge"]["args"] == [
        "-m", "tileforge", "--mcp"]
    vscode = json.loads((ROOT / ".vscode" / "mcp.json").read_text(
        encoding="utf-8"))
    assert vscode["servers"]["tileforge"]["type"] == "stdio"
    cursor = json.loads((ROOT / ".cursor" / "mcp.json").read_text(
        encoding="utf-8"))
    assert cursor["mcpServers"]["tileforge"]["command"].endswith("python")


def test_handshake_mcp():
    result = _run("--check")
    assert result.returncode == 0, result.stderr
    assert "26 outils MCP disponibles" in result.stdout
    assert "tileforge_list_archive" in result.stdout
    assert "tileforge_open_disk" in result.stdout
    assert "tileforge_amiga_sprites" in result.stdout
    assert "tileforge_emulator_memory" in result.stdout
