"""Adaptador da TUI para a classificação emocional.

A leitura de tom e o catálogo de expressões vivem em
:mod:`soleria.persona.emotions`. Este módulo existe para que a interface
continue tendo um ponto de entrada simples, sem conhecer o motor persistente.
"""

from soleria.persona.emotions import classificar_texto


def classificar_expressao(texto, remetente="Você"):
    """Devolve a expressão que combina com o tom de ``texto``."""
    return classificar_texto(texto, remetente)


_classificar_expressao = classificar_expressao

__all__ = ["classificar_expressao"]
