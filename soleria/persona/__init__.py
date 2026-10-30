"""A persona e o motor emocional da Soleria.

Este pacote separa responsabilidades:

- :mod:`soleria.persona.identidade` — quem ela é;
- :mod:`soleria.persona.valores` — o que ela valoriza;
- :mod:`soleria.persona.estilo` — como ela fala;
- :mod:`soleria.persona.limites` — o que ela não faz;
- :mod:`soleria.persona.convivencia` — como ela se relaciona e toma
  iniciativa;
- :mod:`soleria.persona.lexico` — pistas afetivas lidas do texto;
- :mod:`soleria.persona.emotions` — estado emocional, appraisal e
  persistência;
- :mod:`soleria.persona.composer` — montagem por etapa.

O antigo ``personality.py`` continua funcionando como fachada.
"""

from soleria.persona.composer import PERSONALIDADE, persona
from soleria.persona.emotions import (
    EMOCOES,
    MAPA_EMOCOES,
    Avaliacao,
    Emocao,
    EstadoEmocional,
    MotorEmocional,
    classificar_texto,
)

__all__ = [
    "PERSONALIDADE",
    "persona",
    "EMOCOES",
    "MAPA_EMOCOES",
    "Avaliacao",
    "Emocao",
    "EstadoEmocional",
    "MotorEmocional",
    "classificar_texto",
]
