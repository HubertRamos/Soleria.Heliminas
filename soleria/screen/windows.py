"""Janela em foco, para dar contexto ao texto reconhecido.

No umbriel o comando ``umbriel windows`` marca a janela focada com ``*`` e
mostra o aplicativo, o título e a geometria. Em outros compositores há
caminhos alternativos; se nada responder, a observação segue só com o OCR.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Janela:
    aplicativo: str
    titulo: str

    @property
    def descricao(self):
        if self.aplicativo and self.titulo:
            return f"{self.aplicativo}: {self.titulo}"
        return self.titulo or self.aplicativo


def _executar(comando, timeout=3):
    try:
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if resultado.returncode != 0:
        return ""
    return resultado.stdout


def _limpar_titulo(titulo):
    titulo = str(titulo or "").strip()
    # O umbriel prefixa o workspace: "(24) Título da janela".
    return re.sub(r"^\(\d+\)\s*", "", titulo)


def _umbriel():
    if not shutil.which("umbriel"):
        return None
    for linha in _executar(["umbriel", "windows"]).splitlines():
        if not linha.startswith("*"):
            continue
        partes = linha[1:].split("\t")
        if len(partes) < 2:
            continue
        aplicativo = partes[0].strip()
        titulo = _limpar_titulo(partes[1])
        if aplicativo or titulo:
            return Janela(aplicativo, titulo)
    return None


def _hyprland():
    if not shutil.which("hyprctl"):
        return None
    try:
        dados = json.loads(_executar(["hyprctl", "activewindow", "-j"]))
    except (ValueError, TypeError):
        return None
    if not isinstance(dados, dict):
        return None
    aplicativo = str(dados.get("class") or dados.get("initialClass") or "")
    titulo = str(dados.get("title") or "")
    return Janela(aplicativo, titulo) if (aplicativo or titulo) else None


def _sway():
    if not shutil.which("swaymsg"):
        return None
    try:
        arvore = json.loads(_executar(["swaymsg", "-t", "get_tree", "-r"]))
    except (ValueError, TypeError):
        return None

    def procurar(no):
        if not isinstance(no, dict):
            return None
        if no.get("focused") and no.get("type") in {"con", "floating_con"}:
            return no
        for filho in no.get("nodes", []) + no.get("floating_nodes", []):
            achado = procurar(filho)
            if achado is not None:
                return achado
        return None

    no = procurar(arvore)
    if not no:
        return None
    aplicativo = str(no.get("app_id") or "")
    titulo = str(no.get("name") or "")
    return Janela(aplicativo, titulo) if (aplicativo or titulo) else None


def _x11():
    if not shutil.which("xdotool"):
        return None
    titulo = _executar(["xdotool", "getactivewindow", "getwindowname"]).strip()
    if not titulo:
        return None
    aplicativo = ""
    if shutil.which("xprop"):
        janela = _executar(["xdotool", "getactivewindow"]).strip()
        if janela:
            classe = _executar(["xprop", "-id", janela, "WM_CLASS"])
            achado = re.search(r'"([^"]+)"\s*,\s*"([^"]+)"', classe)
            if achado:
                aplicativo = achado.group(2)
    return Janela(aplicativo, titulo)


def janela_em_foco():
    """Devolve a janela em foco, ou ``None`` se o ambiente não informar."""
    for metodo in (_umbriel, _hyprland, _sway, _x11):
        try:
            janela = metodo()
        except Exception:
            continue
        if janela is not None:
            return janela
    return None
