"""Compatibilidade: a personalidade agora vive em :mod:`soleria.persona`.

O texto completo continua disponível como ``PERSONALIDADE`` para imports
antigos, mas a composição por etapa e o motor emocional ficam no pacote
:mod:`soleria.persona`.
"""

from soleria.persona import PERSONALIDADE

__all__ = ["PERSONALIDADE"]
