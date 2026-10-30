"""Composição da persona por etapa.

A personalidade não é um bloco único: identidade, valores, estilo, limites e
convivência são montados sob demanda. Etapas internas (relatório e leitura)
usam uma versão compacta para não gastar contexto com o que não importa
naquele momento.
"""

from __future__ import annotations

from functools import lru_cache

from soleria.persona.convivencia import CONVIVENCIA
from soleria.persona.estilo import ESTILO, ESTILO_CURTO
from soleria.persona.identidade import IDENTIDADE, IDENTIDADE_CURTA
from soleria.persona.limites import LIMITES, LIMITES_CURTOS
from soleria.persona.valores import VALORES


@lru_cache(maxsize=16)
def persona(etapa="conversa", compacto=False):
    """Devolve a persona adequada à etapa.

    ``decisao`` e ``final`` recebem a persona completa, porque é ali que o
    tom e a iniciativa aparecem para o usuário. ``relatorio`` e ``leitura``
    recebem a versão compacta.
    """
    compacta = compacto or etapa in {
        "relatorio",
        "leitura",
        "resumo",
        "iniciativa",
    }
    if compacta:
        partes = (IDENTIDADE_CURTA, ESTILO_CURTO, LIMITES_CURTOS)
    else:
        partes = (IDENTIDADE, VALORES, ESTILO, LIMITES, CONVIVENCIA)
    return "\n\n".join(partes)


PERSONALIDADE = persona("conversa")


__all__ = ["PERSONALIDADE", "persona"]
