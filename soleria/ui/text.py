"""Utilidades de texto e largura de terminal.

A TUI precisa medir caracteres largos (emojis, CJK), quebrar palavras
longas e centralizar conteúdo sem depender do prompt_toolkit fora daqui.
"""

import os

from prompt_toolkit.utils import get_cwidth


def contem(texto, palavras):
    return any(palavra in texto for palavra in palavras)


def largura_texto(texto):
    """Largura real no terminal (emojis e caracteres largos contam 2)."""
    return sum(get_cwidth(caractere) for caractere in texto)


def cortar_texto(texto, largura):
    if largura_texto(texto) <= largura:
        return texto

    saida = []
    usado = 0
    for caractere in texto:
        passo = get_cwidth(caractere)
        if usado + passo > max(1, largura - 1):
            break
        saida.append(caractere)
        usado += passo
    return "".join(saida).rstrip() + "…"


def quebrar_texto(texto, largura):
    """Quebra texto preservando parágrafos, espaços e palavras longas."""
    largura = max(4, largura)
    linhas = []

    for paragrafo in (
        (texto or "").replace("\t", "    ").replace("\r", "").split("\n")
    ):
        if not paragrafo:
            linhas.append("")
            continue

        resto = paragrafo
        while True:
            usado = 0
            corte = 0
            ultimo_espaco = -1
            for indice, caractere in enumerate(resto):
                passo = get_cwidth(caractere)
                if usado + passo > largura:
                    break
                usado += passo
                corte = indice + 1
                if caractere == " ":
                    ultimo_espaco = indice

            # O restante inteiro cabe nesta linha.
            if corte >= len(resto):
                linhas.append(resto)
                break

            if ultimo_espaco > 0:
                corte = ultimo_espaco
            corte = max(1, corte)

            linhas.append(resto[:corte].rstrip())
            resto = resto[corte:].lstrip()

    return linhas or [""]


def centralizar(texto, largura):
    sobra = max(0, largura - largura_texto(texto))
    esquerda = sobra // 2
    return " " * esquerda + texto, " " * (sobra - esquerda)


def achatar(linhas):
    """Converte uma matriz de fragmentos em uma lista para o prompt_toolkit."""
    partes = []
    for indice, linha in enumerate(linhas):
        if indice:
            partes.append(("", "\n"))
        partes.extend(linha)
    return partes


def terminal_24bit():
    return os.environ.get("COLORTERM", "").lower() in {"truecolor", "24bit"}


# Aliases privados mantidos para compatibilidade.
_contem = contem
_largura_texto = largura_texto
_cortar_texto = cortar_texto
_quebrar_texto = quebrar_texto
_centralizar = centralizar
_achatar = achatar
_terminal_24bit = terminal_24bit
