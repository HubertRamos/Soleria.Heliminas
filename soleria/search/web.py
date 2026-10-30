"""Pesquisa web com DDGS."""

import re
from urllib.parse import urlsplit

from ddgs import DDGS

from config import (
    MAX_CARACTERES_CONSULTA,
    MAX_CARACTERES_FONTES,
    MAX_CARACTERES_RESUMO,
    MAX_RESULTADOS_BUSCA,
    TIMEOUT_PESQUISA,
)
from soleria.logging_utils import log_erro
from soleria.search.pages import ler_paginas, notificar_progresso

_MAX_TITULO = 200
_MAX_URL = 500

# Conteúdo de página é dado externo. Neutraliza comandos internos que
# apareçam no texto para o modelo não confundi-los com instruções.
_COMANDO_FONTE = re.compile(
    r"\[\[\s*(?:PESQUISAR|PERGUNTAR|RELAT[ÓO]RIO|NOVO)\s*:",
    re.IGNORECASE,
)


def _neutralizar_comandos(texto):
    return _COMANDO_FONTE.sub("[[comando removido:", texto or "")


def _texto(valor, padrao="", limite=None):
    if not isinstance(valor, str):
        return padrao
    texto = " ".join(valor.split())
    if limite and len(texto) > limite:
        texto = texto[: limite - 1].rstrip() + "…"
    return texto or padrao


def _url_valida(url):
    try:
        partes = urlsplit(url)
    except ValueError:
        return False
    return partes.scheme in {"http", "https"} and bool(partes.netloc)


def _normalizar_resultados(resultados, limite):
    """Converte o retorno do DDGS em fontes limpas e sem duplicatas."""
    fontes = []
    vistos = set()

    for item in resultados or ():
        if not isinstance(item, dict):
            continue

        url = _texto(item.get("href") or item.get("url"), limite=_MAX_URL)
        if not url or not _url_valida(url):
            continue

        chave = url.split("#", 1)[0].rstrip("/")
        if chave in vistos:
            continue
        vistos.add(chave)

        fontes.append(
            {
                "titulo": _texto(
                    item.get("title"),
                    "Título indisponível",
                    _MAX_TITULO,
                ),
                "url": url,
                "resumo": _texto(
                    item.get("body") or item.get("snippet"),
                    "Resumo indisponível",
                    MAX_CARACTERES_RESUMO,
                ),
            }
        )

        if len(fontes) >= limite:
            break

    return fontes


def pesquisar_web(
    pergunta,
    max_resultados=MAX_RESULTADOS_BUSCA,
    ao_progresso=None,
    cancelado=None,
):
    """Pesquisa na web, abre os links e devolve fontes normalizadas."""
    consulta = _texto(pergunta, limite=MAX_CARACTERES_CONSULTA)
    if not consulta:
        return []

    try:
        with DDGS(timeout=max(1, int(TIMEOUT_PESQUISA))) as pesquisa:
            resultados = pesquisa.text(
                consulta,
                region="br-pt",
                max_results=max(1, max_resultados),
            )
        fontes = _normalizar_resultados(resultados, max(1, max_resultados))
    except Exception as erro:
        log_erro(erro)
        return []

    if not fontes:
        notificar_progresso(ao_progresso, "nenhum resultado encontrado")
        return []

    notificar_progresso(
        ao_progresso, f"{len(fontes)} resultado(s) encontrado(s)"
    )

    if cancelado is not None and cancelado.is_set():
        return fontes

    return ler_paginas(
        fontes, ao_progresso=ao_progresso, cancelado=cancelado
    )


def formatar_fontes(fontes, limite=MAX_CARACTERES_FONTES):
    """Formata as fontes para o prompt de resposta final.

    O total é limitado para não estourar o contexto do modelo. A primeira
    fonte sempre entra; as seguintes são acrescentadas enquanto couberem.
    """
    limite = max(500, int(limite or MAX_CARACTERES_FONTES))
    blocos = []
    total = 0

    for i, fonte in enumerate(fontes, start=1):
        linhas = [
            f"Fonte {i}",
            f"Título: {_neutralizar_comandos(fonte.get('titulo') or '')}",
            f"URL: {_neutralizar_comandos(fonte.get('url') or '')}",
        ]
        if fonte.get("conteudo"):
            linhas.append(
                "Conteúdo da página:\n"
                f"{_neutralizar_comandos(fonte['conteudo'])}"
            )
        else:
            linhas.append(
                f"Resumo: {_neutralizar_comandos(fonte.get('resumo') or '')}"
            )

        bloco = "\n".join(linhas)
        if blocos and total + len(bloco) + 2 > limite:
            break
        if not blocos and len(bloco) > limite:
            # A primeira fonte sempre entra, mas não pode sozinha estourar
            # o orçamento. O corte preserva título e URL no início.
            bloco = bloco[: max(300, limite)].rstrip() + "…"
        blocos.append(bloco)
        total += len(bloco) + 2

    return "\n\n".join(blocos)
