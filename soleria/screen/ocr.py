"""Reconhecimento de texto (OCR) da captura de tela.

Usa o ``tesseract`` instalado no sistema, sem rede e sem guardar a imagem.
Se o binário ou o pacote de português não estiverem disponíveis, o motivo é
devolvido para a interface em vez de derrubar o chat.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from functools import lru_cache

from config import OCR_IDIOMAS, OCR_TIMEOUT
from soleria.logging_utils import log_evento


class OCRIndisponivel(RuntimeError):
    """O OCR não pode ser executado nesta máquina."""


@lru_cache(maxsize=1)
def _idiomas_instalados():
    if not shutil.which("tesseract"):
        return frozenset()
    try:
        resultado = subprocess.run(
            ["tesseract", "--list-langs"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    if resultado.returncode != 0:
        return frozenset()
    idiomas = set()
    for linha in resultado.stdout.splitlines():
        linha = linha.strip()
        if linha and " " not in linha and not linha.endswith(":"):
            idiomas.add(linha)
    return frozenset(idiomas)


@lru_cache(maxsize=8)
def _escolher_idiomas(preferidos):
    instalados = _idiomas_instalados()
    pedidos = [
        item.strip()
        for item in str(preferidos or "").split("+")
        if item.strip()
    ]
    escolhidos = [idioma for idioma in pedidos if idioma in instalados]
    if escolhidos:
        if len(escolhidos) < len(pedidos):
            log_evento(
                "OCR: idiomas ausentes: "
                + ", ".join(i for i in pedidos if i not in escolhidos)
            )
        return "+".join(escolhidos)
    if "eng" in instalados:
        log_evento("OCR: usando inglês porque o idioma pedido não existe")
        return "eng"
    return ""


def _limpar_linha(linha):
    linha = " ".join(str(linha or "").split())
    if len(linha) < 2:
        return ""
    if not any(caractere.isalnum() for caractere in linha):
        return ""
    return linha


def normalizar_texto(texto, limite):
    """Limpa o ruído típico do OCR sem perder o conteúdo útil."""
    if limite <= 0:
        return ""
    linhas = []
    for linha in str(texto or "").splitlines():
        linha = _limpar_linha(linha)
        if not linha:
            continue
        # OCR de tela costuma repetir a mesma linha em colunas vizinhas.
        if linhas and _normalizar_chave(linhas[-1]) == _normalizar_chave(
            linha
        ):
            continue
        linhas.append(linha)

    limpo = "\n".join(linhas)
    if len(limpo) <= limite:
        return limpo
    corte = limpo[:limite]
    if "\n" in corte:
        corte = corte.rsplit("\n", 1)[0]
    return corte.rstrip() + "\n(… texto cortado)"


def _normalizar_chave(texto):
    return re.sub(r"\W+", "", str(texto or "").casefold())


def disponivel():
    return bool(shutil.which("tesseract")) and bool(_idiomas_instalados())


def motivo_indisponivel():
    if not shutil.which("tesseract"):
        return (
            "O OCR da tela precisa do tesseract. No Arch/CachyOS: "
            "sudo pacman -S tesseract tesseract-data-por"
        )
    if not _idiomas_instalados():
        return (
            "O tesseract está instalado, mas sem idioma utilizável. "
            "Instale tesseract-data-por (ou tesseract-data-eng)."
        )
    return None


def extrair_texto(png, limite, idiomas=OCR_IDIOMAS, timeout=OCR_TIMEOUT):
    """Devolve o texto visível na imagem PNG, ou string vazia."""
    if not disponivel():
        raise OCRIndisponivel(motivo_indisponivel() or "OCR indisponível")

    idioma = _escolher_idiomas(idiomas)
    comando = [
        "tesseract",
        "stdin",
        "stdout",
        "--psm",
        "3",
        "--dpi",
        "96",
    ]
    if idioma:
        comando[3:3] = ["-l", idioma]

    ambiente = dict(os.environ)
    # O tesseract usa OpenMP; com o modelo local rodando, deixar todos os
    # núcleos para ele atrasaria a resposta que está sendo gerada.
    ambiente.setdefault("OMP_THREAD_LIMIT", "4")

    try:
        resultado = subprocess.run(
            comando,
            input=bytes(png),
            capture_output=True,
            timeout=timeout,
            check=False,
            env=ambiente,
        )
    except (OSError, subprocess.SubprocessError) as erro:
        raise OCRIndisponivel(f"o tesseract falhou: {erro}") from erro

    if resultado.returncode != 0:
        detalhe = resultado.stderr.decode("utf-8", "replace").strip()
        raise OCRIndisponivel(
            "o tesseract não leu a imagem"
            + (f" ({detalhe[:160]})" if detalhe else "")
        )

    texto = resultado.stdout.decode("utf-8", "replace")
    return normalizar_texto(texto, limite)
