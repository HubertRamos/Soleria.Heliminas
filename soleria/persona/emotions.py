"""Motor emocional da Soleria.

A ideia é simples, mas vai além de escolher uma imagem: a Soleria tem um
estado interno (valência, energia, paciência, curiosidade, vontade de
conversar, confiança e afinidade) que evolui com a conversa, decai com o
tempo e influencia o tom das respostas.

O motor é determinístico, offline e independente da interface. A TUI só
pergunta qual expressão mostrar; o orquestrador pergunta qual diretriz
interna acrescentar ao prompt.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from soleria.persona.lexico import contem, detectar


# ----------------------------------------------------------------------
# Catálogo de expressões
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class Emocao:
    chave: str
    arquivo: str
    cor: str
    rotulo: str
    familia: str
    valencia: float
    energia: float


EMOCOES = (
    Emocao("NORMAL", "normal.png", "#55f5ee", "tranquila", "neutra", 0.10, 0.55),
    Emocao("FELIZ", "feliz.png", "#ff55cf", "radiante", "positiva", 0.55, 0.65),
    Emocao("ANIMADA", "animada.png", "#ffd34e", "animada", "positiva", 0.65, 0.85),
    Emocao("RINDO", "rindo.png", "#43f59a", "rindo", "positiva", 0.60, 0.80),
    Emocao("ZOEIRA", "zoeira.png", "#43f59a", "no deboche", "positiva", 0.45, 0.75),
    Emocao("FOFA", "fofa.png", "#ffb3d9", "fofa", "afetiva", 0.50, 0.45),
    Emocao("TIMIDA", "timida.png", "#ffa8c8", "tímida", "afetiva", 0.35, 0.35),
    Emocao(
        "ENVERGONHADA",
        "envergonhada.png",
        "#ff8fb8",
        "envergonhada",
        "afetiva",
        0.30,
        0.40,
    ),
    Emocao(
        "ORGULHOSA",
        "orgulhosa.png",
        "#ffd34e",
        "orgulhosa",
        "positiva",
        0.60,
        0.70,
    ),
    Emocao(
        "PENSATIVA",
        "pensando.png",
        "#ffd34e",
        "pensando",
        "cognitiva",
        0.15,
        0.45,
    ),
    Emocao("FOCADA", "focada.png", "#55f5ee", "focada", "cognitiva", 0.20, 0.65),
    Emocao(
        "CONFUSA",
        "confusa.png",
        "#c79bff",
        "confusa",
        "cognitiva",
        -0.05,
        0.45,
    ),
    Emocao(
        "SURPRESA",
        "surpresa.png",
        "#42bfff",
        "surpresa",
        "reativa",
        0.10,
        0.75,
    ),
    Emocao(
        "ASSUSTADA",
        "assustada.png",
        "#8a7dff",
        "assustada",
        "reativa",
        -0.25,
        0.80,
    ),
    Emocao(
        "PREOCUPADA",
        "preocupada.png",
        "#ffa94d",
        "preocupada",
        "reativa",
        -0.20,
        0.45,
    ),
    Emocao("BRAVA", "brava.png", "#ff4d70", "indignada", "negativa", -0.45, 0.75),
    Emocao(
        "IRRITADA",
        "irritada.png",
        "#ff6b4a",
        "irritada",
        "negativa",
        -0.55,
        0.80,
    ),
    Emocao("TRISTE", "triste.png", "#6d8cff", "triste", "negativa", -0.50, 0.25),
    Emocao("SONO", "sonolenta.png", "#a879ff", "com sono", "baixa", -0.05, 0.15),
    Emocao(
        "ENTEDIADA",
        "entediada.png",
        "#8f9bb3",
        "entediada",
        "baixa",
        -0.15,
        0.25,
    ),
    Emocao("SERIA", "seria.png", "#9fb3c7", "séria", "cognitiva", 0.05, 0.50),
)

MAPA_EMOCOES = {emocao.chave: emocao for emocao in EMOCOES}


# ----------------------------------------------------------------------
# Estado
# ----------------------------------------------------------------------

_CAMPOS_ESTADO = (
    ("valencia", -1.0, 1.0),
    ("energia", 0.0, 1.0),
    ("confianca", 0.0, 1.0),
    ("paciencia", 0.0, 1.0),
    ("curiosidade", 0.0, 1.0),
    ("social", 0.0, 1.0),
    ("afinidade", 0.0, 1.0),
    ("intensidade", 0.0, 1.0),
)


def _clamp(valor, minimo, maximo):
    return max(minimo, min(maximo, valor))


def _numero(valor, padrao=0.0):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return float(padrao)


def _aproximar(valor, alvo, dt, tau):
    if tau <= 0:
        return alvo
    fator = 1.0 - math.exp(-max(0.0, dt) / tau)
    return valor + (alvo - valor) * fator


def _energia_do_horario(agora):
    hora = time.localtime(agora).tm_hour
    if 0 <= hora < 6:
        return 0.35
    if 6 <= hora < 9:
        return 0.55
    if 9 <= hora < 18:
        return 0.70
    return 0.58


def _nivel(valor, baixo="baixa", medio="moderada", alto="alta"):
    if valor < 0.33:
        return baixo
    if valor > 0.66:
        return alto
    return medio


@dataclass
class EstadoEmocional:
    """Retrato momentâneo do humor e das necessidades da Soleria."""

    valencia: float = 0.15
    energia: float = 0.65
    confianca: float = 0.55
    paciencia: float = 0.70
    curiosidade: float = 0.60
    social: float = 0.65
    afinidade: float = 0.50
    intensidade: float = 0.25
    expressao: str = "NORMAL"
    atualizado_em: float = field(default_factory=time.time)
    ultima_interacao: float = field(default_factory=time.time)
    total_interacoes: int = 0

    def para_dicionario(self):
        return {
            "valencia": self.valencia,
            "energia": self.energia,
            "confianca": self.confianca,
            "paciencia": self.paciencia,
            "curiosidade": self.curiosidade,
            "social": self.social,
            "afinidade": self.afinidade,
            "intensidade": self.intensidade,
            "expressao": self.expressao,
            "atualizado_em": self.atualizado_em,
            "ultima_interacao": self.ultima_interacao,
            "total_interacoes": self.total_interacoes,
        }

    @classmethod
    def de_dicionario(cls, dados):
        estado = cls()
        if not isinstance(dados, dict):
            return estado
        for campo, minimo, maximo in _CAMPOS_ESTADO:
            setattr(
                estado,
                campo,
                _clamp(
                    _numero(dados.get(campo), getattr(estado, campo)),
                    minimo,
                    maximo,
                ),
            )
        expressao = str(dados.get("expressao") or "NORMAL").upper()
        estado.expressao = expressao if expressao in MAPA_EMOCOES else "NORMAL"
        estado.total_interacoes = max(
            0, int(_numero(dados.get("total_interacoes"), 0))
        )
        estado.atualizado_em = _numero(
            dados.get("atualizado_em"), estado.atualizado_em
        )
        estado.ultima_interacao = _numero(
            dados.get("ultima_interacao"), estado.ultima_interacao
        )
        return estado


@dataclass
class Avaliacao:
    valencia: float = 0.0
    energia: float = 0.0
    confianca: float = 0.0
    paciencia: float = 0.0
    curiosidade: float = 0.0
    social: float = 0.0
    afinidade: float = 0.0
    intensidade: float = 0.0
    tags: frozenset = field(default_factory=frozenset)


# (valência, energia, confiança, paciência, curiosidade, social,
#  afinidade, intensidade)
_DELTAS = {
    "afeto": (0.35, 0.05, 0.05, 0.02, 0.00, 0.12, 0.10, 0.20),
    "elogio": (0.28, 0.03, 0.12, 0.02, 0.00, 0.06, 0.05, 0.15),
    "humor": (0.25, 0.12, 0.02, 0.02, 0.02, 0.08, 0.03, 0.15),
    "raiva": (-0.45, 0.08, -0.08, -0.22, 0.00, -0.05, -0.05, 0.30),
    "nojo": (-0.35, 0.05, -0.05, -0.15, 0.00, -0.05, -0.02, 0.25),
    "tristeza": (-0.25, -0.08, -0.05, 0.05, 0.00, 0.10, 0.02, 0.20),
    "medo": (-0.20, 0.12, -0.05, -0.02, 0.00, 0.08, 0.02, 0.30),
    "susto": (0.05, 0.12, -0.02, 0.00, 0.02, 0.04, 0.00, 0.20),
    "confusao": (-0.05, 0.00, -0.05, -0.02, 0.08, 0.02, 0.00, 0.10),
    "curiosidade": (0.05, 0.06, 0.02, 0.00, 0.18, 0.04, 0.00, 0.15),
    "urgencia": (0.00, 0.12, 0.05, -0.05, 0.02, 0.00, 0.00, 0.15),
    "foco": (0.05, 0.10, 0.08, 0.04, 0.04, -0.02, 0.00, 0.15),
    "sono": (-0.05, -0.22, -0.02, 0.02, -0.02, -0.05, 0.00, 0.15),
    "saudacao": (0.12, 0.04, 0.02, 0.02, 0.02, 0.12, 0.03, 0.10),
    "despedida": (-0.08, -0.02, 0.00, 0.00, 0.00, -0.12, 0.00, 0.10),
    "tecnico": (0.02, 0.04, 0.08, 0.02, 0.10, 0.00, 0.00, 0.10),
    "vulneravel": (-0.10, -0.04, -0.02, 0.08, 0.00, 0.15, 0.06, 0.20),
    "conquista": (0.30, 0.10, 0.15, 0.02, 0.02, 0.06, 0.02, 0.20),
    "tedio": (-0.15, -0.10, -0.02, -0.02, 0.08, 0.05, 0.00, 0.10),
    "vergonha": (0.10, 0.03, -0.03, 0.02, 0.00, 0.06, 0.06, 0.15),
    "animacao": (0.30, 0.18, 0.05, 0.02, 0.04, 0.08, 0.02, 0.20),
    "seriedade": (0.00, 0.02, 0.05, 0.05, 0.02, -0.02, 0.00, 0.10),
    "falha": (-0.12, -0.05, -0.08, -0.02, 0.02, 0.02, 0.00, 0.15),
}

_ZERO = (0.0,) * 8

# Eventos do pipeline de conversa.
_EVENTOS = {
    "pesquisa_inicio": (0.00, -0.04, 0.00, 0.00, 0.10, 0.00, 0.00, 0.20),
    "pesquisa_ok": (0.10, 0.00, 0.08, 0.00, 0.00, 0.00, 0.00, 0.20),
    "pesquisa_vazia": (-0.12, 0.00, 0.00, -0.08, 0.00, 0.00, 0.00, 0.25),
    "erro": (-0.22, -0.05, -0.10, -0.12, 0.00, 0.00, 0.00, 0.35),
    "relatorio_ok": (0.18, 0.00, 0.15, 0.00, 0.00, 0.00, 0.00, 0.25),
    "leitura_ok": (0.05, 0.00, 0.05, 0.00, 0.02, 0.00, 0.00, 0.15),
    "iniciativa_ok": (0.08, 0.02, 0.03, 0.00, 0.02, 0.06, 0.02, 0.15),
    "tela_ok": (0.05, 0.02, 0.03, 0.00, 0.10, 0.06, 0.03, 0.15),
    "cancelado": (-0.04, 0.00, 0.00, -0.04, 0.00, 0.00, 0.00, 0.15),
}

_EXPRESSOES_EVENTO = {
    "pesquisa_inicio": "FOCADA",
    "pesquisa_ok": "ORGULHOSA",
    "pesquisa_vazia": "PREOCUPADA",
    "erro": "TRISTE",
    "relatorio_ok": "ORGULHOSA",
    "leitura_ok": "PENSATIVA",
    "iniciativa_ok": "FELIZ",
    "tela_ok": "PENSATIVA",
    "cancelado": "PENSATIVA",
}


def _somar_deltas(avaliacao, deltas, escala=1.0):
    avaliacao.valencia += deltas[0] * escala
    avaliacao.energia += deltas[1] * escala
    avaliacao.confianca += deltas[2] * escala
    avaliacao.paciencia += deltas[3] * escala
    avaliacao.curiosidade += deltas[4] * escala
    avaliacao.social += deltas[5] * escala
    avaliacao.afinidade += deltas[6] * escala
    avaliacao.intensidade += deltas[7] * escala


def _gritando(texto):
    letras = [c for c in (texto or "") if c.isalpha()]
    return len(letras) >= 4 and all(c.isupper() for c in letras)


def _avaliacao_evento(evento):
    deltas = _EVENTOS.get(evento)
    if deltas is None:
        return None
    return Avaliacao(
        valencia=deltas[0],
        energia=deltas[1],
        confianca=deltas[2],
        paciencia=deltas[3],
        curiosidade=deltas[4],
        social=deltas[5],
        afinidade=deltas[6],
        intensidade=deltas[7],
    )


# ----------------------------------------------------------------------
# Motor
# ----------------------------------------------------------------------


class MotorEmocional:
    """Estado emocional persistente e appraisal simples da conversa."""

    VERSAO_ESTADO = 1

    def __init__(
        self,
        caminho=None,
        ativo=True,
        iniciativa=True,
        relogio: Callable[[], float] | None = None,
    ):
        self._lock = threading.RLock()
        self._relogio = relogio or time.time
        self._caminho = (
            Path(os.path.expandvars(str(caminho))).expanduser()
            if caminho
            else None
        )
        self.ativo = bool(ativo)
        self.iniciativa = bool(iniciativa)

        agora = self._agora()
        self._estado = EstadoEmocional(
            atualizado_em=agora, ultima_interacao=agora
        )
        self._expressao_desde = agora
        self._expressao_ate = 0.0
        self._carregar()

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------

    @property
    def caminho(self):
        return self._caminho

    @property
    def estado(self):
        with self._lock:
            self._tick()
            return EstadoEmocional.de_dicionario(
                self._estado.para_dicionario()
            )

    @property
    def expressao(self):
        with self._lock:
            self._tick()
            return self._estado.expressao

    @property
    def humor(self):
        with self._lock:
            self._tick()
            return MAPA_EMOCOES[self._estado.expressao].rotulo

    def instantaneo(self):
        with self._lock:
            self._tick()
            return self._estado.para_dicionario()

    def pensamento_ocioso(self):
        """Frase curta para a TUI quando ela está parada há um tempo."""
        if not self.ativo:
            return None
        with self._lock:
            agora = self._agora()
            self._tick(agora)
            ociosidade = agora - self._estado.ultima_interacao
            if ociosidade < 90:
                return None
            frases = {
                "SONO": "bocejando baixinho…",
                "ENTEDIADA": "pensando em puxar assunto…",
                "PENSATIVA": "organizando ideias…",
                "FOFA": "esperando um oi…",
                "TRISTE": "com saudade da conversa…",
                "NORMAL": "pronta para conversar",
            }
            return frases.get(self._estado.expressao)

    # ------------------------------------------------------------------
    # Configuração
    # ------------------------------------------------------------------

    def definir_ativo(self, ativo):
        with self._lock:
            self.ativo = bool(ativo)
            agora = self._agora()
            if not self.ativo:
                self._estado.expressao = "NORMAL"
                self._expressao_desde = agora
                self._expressao_ate = 0.0
            else:
                self._tick(agora)

    def definir_iniciativa(self, ativa):
        """Liga/desliga a vontade de puxar assunto por conta própria."""
        with self._lock:
            self.iniciativa = bool(ativa)

    def reiniciar(self, agora=None):
        with self._lock:
            agora = self._agora(agora)
            self._estado = EstadoEmocional(
                atualizado_em=agora, ultima_interacao=agora
            )
            self._expressao_desde = agora
            self._expressao_ate = 0.0
            self._definir_expressao("NORMAL", agora, forcar=True)
            return self._estado

    # ------------------------------------------------------------------
    # Tempo
    # ------------------------------------------------------------------

    def tick(self, agora=None):
        with self._lock:
            return self._tick(agora)

    def marcar_atividade(self, agora=None):
        """Sinaliza presença sem avaliar texto (digitação, voz etc.)."""
        with self._lock:
            agora = self._agora(agora)
            self._tick(agora)
            self._estado.ultima_interacao = agora
            self._estado.atualizado_em = agora
            return self._estado.expressao

    def _tick(self, agora=None):
        agora = self._agora(agora)
        estado = self._estado

        if not self.ativo:
            estado.expressao = "NORMAL"
            estado.atualizado_em = agora
            return estado

        dt = agora - estado.atualizado_em
        if dt > 0:
            ociosidade = max(0.0, agora - estado.ultima_interacao)
            base_energia = _energia_do_horario(agora)
            alvo_social = (
                0.65
                if ociosidade < 120
                else max(0.12, 0.65 - (ociosidade - 120) / 1800.0 * 0.5)
            )
            alvo_energia = (
                base_energia
                if ociosidade < 600
                else min(base_energia, 0.30)
            )
            alvo_curiosidade = min(
                0.90, 0.60 + max(0.0, ociosidade - 60) / 2400.0 * 0.20
            )
            alvo_paciencia = 0.70 if ociosidade < 300 else 0.82

            estado.valencia = _aproximar(estado.valencia, 0.15, dt, 300.0)
            estado.energia = _aproximar(estado.energia, alvo_energia, dt, 1800.0)
            estado.confianca = _aproximar(
                estado.confianca, 0.55, dt, 1200.0
            )
            estado.paciencia = _aproximar(
                estado.paciencia, alvo_paciencia, dt, 600.0
            )
            estado.curiosidade = _aproximar(
                estado.curiosidade, alvo_curiosidade, dt, 900.0
            )
            estado.social = _aproximar(estado.social, alvo_social, dt, 600.0)
            estado.afinidade = _aproximar(
                estado.afinidade, 0.50, dt, 86400.0
            )
            estado.intensidade = _aproximar(
                estado.intensidade, 0.20, dt, 300.0
            )

        estado.atualizado_em = agora
        ociosidade = max(0.0, agora - estado.ultima_interacao)
        self._definir_expressao(
            self._escolher_expressao(ociosidade), agora
        )
        return estado

    # ------------------------------------------------------------------
    # Appraisal
    # ------------------------------------------------------------------

    def observar_usuario(self, texto, agora=None):
        """Lê a mensagem do usuário e reage a ela."""
        with self._lock:
            agora = self._agora(agora)
            self._tick(agora)
            if not self.ativo:
                return self._estado.expressao

            tags = detectar(texto)
            avaliacao = self._avaliar_usuario(texto, tags)
            self._aplicar(avaliacao)
            estado = self._estado
            estado.ultima_interacao = agora
            estado.total_interacoes += 1
            estado.atualizado_em = agora

            candidata = self._expressao_do_usuario(tags)
            self._definir_expressao(
                candidata, agora, forcar=avaliacao.intensidade >= 0.32
            )
            return estado.expressao

    def observar_resposta(
        self,
        texto,
        pesquisou=False,
        sucesso=True,
        erro=False,
        agora=None,
    ):
        """Atualiza o estado depois de a Soleria responder."""
        with self._lock:
            agora = self._agora(agora)
            self._tick(agora)
            if not self.ativo:
                return self._estado.expressao

            tags = detectar(texto)
            avaliacao = self._avaliar_resposta(
                texto, tags, pesquisou, sucesso, erro
            )
            self._aplicar(avaliacao)
            estado = self._estado
            estado.ultima_interacao = agora
            estado.atualizado_em = agora

            candidata = self._expressao_da_resposta(
                tags, pesquisou, sucesso, erro
            )
            self._definir_expressao(
                candidata, agora, forcar=avaliacao.intensidade >= 0.32
            )
            return estado.expressao

    def registrar_evento(self, evento, agora=None):
        """Aplica um evento do pipeline (pesquisa, erro, relatório etc.)."""
        with self._lock:
            agora = self._agora(agora)
            self._tick(agora)
            if not self.ativo:
                return self._estado.expressao

            if evento == "limpar":
                self.reiniciar(agora)
                return self._estado.expressao

            avaliacao = _avaliacao_evento(evento)
            if avaliacao is None:
                return self._estado.expressao

            self._aplicar(avaliacao)
            estado = self._estado
            estado.ultima_interacao = agora
            estado.atualizado_em = agora

            candidata = _EXPRESSOES_EVENTO.get(evento)
            if evento == "erro" and estado.valencia > -0.2:
                candidata = "PREOCUPADA"
            if evento == "relatorio_ok" and estado.confianca <= 0.6:
                candidata = "FELIZ"
            if not candidata:
                candidata = self._escolher_expressao(0.0)
            self._definir_expressao(
                candidata, agora, forcar=avaliacao.intensidade >= 0.32
            )
            return estado.expressao

    # ------------------------------------------------------------------
    # Avaliação
    # ------------------------------------------------------------------

    def _avaliar_usuario(self, texto, tags):
        avaliacao = Avaliacao(tags=frozenset(tags))
        for tag in tags:
            _somar_deltas(avaliacao, _DELTAS.get(tag, _ZERO))

        extra = 0.0
        if "!" in (texto or ""):
            extra += 0.05
        if "?" in (texto or ""):
            extra += 0.02
        if len(texto or "") > 300:
            extra += 0.05
        if _gritando(texto):
            extra += 0.10

        avaliacao.intensidade = _clamp(
            0.18
            + sum(_DELTAS.get(tag, _ZERO)[7] for tag in tags)
            + extra,
            0.0,
            1.0,
        )
        return avaliacao

    def _avaliar_resposta(
        self, texto, tags, pesquisou, sucesso, erro
    ):
        avaliacao = Avaliacao(tags=frozenset(tags))
        for tag in tags:
            _somar_deltas(avaliacao, _DELTAS.get(tag, _ZERO), escala=0.6)

        if pesquisou:
            avaliacao.confianca += 0.10
            avaliacao.curiosidade += 0.05
            avaliacao.energia -= 0.06
            avaliacao.intensidade += 0.10

        if sucesso:
            avaliacao.valencia += 0.18
            avaliacao.confianca += 0.12
            avaliacao.intensidade += 0.10
        elif not erro:
            avaliacao.valencia -= 0.10
            avaliacao.paciencia -= 0.04
            avaliacao.intensidade += 0.10

        if erro:
            avaliacao.valencia -= 0.28
            avaliacao.paciencia -= 0.15
            avaliacao.confianca -= 0.15
            avaliacao.energia -= 0.05
            avaliacao.intensidade += 0.25

        if len(texto or "") > 1500:
            avaliacao.energia -= 0.08
            avaliacao.paciencia -= 0.02
        elif len(texto or "") < 80 and (texto or "").strip():
            avaliacao.energia += 0.02

        avaliacao.intensidade = _clamp(
            0.15 + avaliacao.intensidade, 0.0, 1.0
        )
        return avaliacao

    def _aplicar(self, avaliacao):
        estado = self._estado
        estado.valencia = _clamp(
            estado.valencia + avaliacao.valencia, -1.0, 1.0
        )
        estado.energia = _clamp(
            estado.energia + avaliacao.energia, 0.0, 1.0
        )
        estado.confianca = _clamp(
            estado.confianca + avaliacao.confianca, 0.0, 1.0
        )
        estado.paciencia = _clamp(
            estado.paciencia + avaliacao.paciencia, 0.0, 1.0
        )
        estado.curiosidade = _clamp(
            estado.curiosidade + avaliacao.curiosidade, 0.0, 1.0
        )
        estado.social = _clamp(
            estado.social + avaliacao.social, 0.0, 1.0
        )
        estado.afinidade = _clamp(
            estado.afinidade + avaliacao.afinidade, 0.0, 1.0
        )
        estado.intensidade = _clamp(
            estado.intensidade * 0.45 + avaliacao.intensidade * 0.55,
            0.0,
            1.0,
        )

    # ------------------------------------------------------------------
    # Escolha da expressão
    # ------------------------------------------------------------------

    def _escolher_expressao(self, ociosidade=0.0):
        estado = self._estado
        if ociosidade > 300 and estado.energia < 0.55:
            return "SONO"
        if ociosidade > 180 and estado.social < 0.55:
            return "ENTEDIADA"
        if estado.energia < 0.18:
            return "SONO"
        if estado.paciencia < 0.18:
            return "IRRITADA"
        if estado.valencia < -0.35:
            return "TRISTE"
        if estado.social < 0.22:
            return "ENTEDIADA"
        if estado.curiosidade > 0.82 and estado.energia > 0.50:
            return "PENSATIVA"
        if estado.confianca > 0.82 and estado.valencia > 0.20:
            return "ORGULHOSA"
        if estado.valencia > 0.50 and estado.energia > 0.65:
            return "ANIMADA"
        if estado.valencia > 0.35:
            return "FELIZ"
        if estado.energia < 0.32:
            return "SONO"
        return "NORMAL"

    def _expressao_do_usuario(self, tags):
        estado = self._estado
        if "medo" in tags:
            return "ASSUSTADA"
        if "raiva" in tags:
            if estado.paciencia < 0.45 or estado.intensidade > 0.65:
                return "IRRITADA"
            return "BRAVA"
        if "nojo" in tags:
            return "IRRITADA"
        if "tristeza" in tags:
            if estado.valencia < -0.30 or estado.intensidade > 0.55:
                return "TRISTE"
            return "PREOCUPADA"
        if "falha" in tags and "tecnico" not in tags:
            return "PREOCUPADA"
        if "sono" in tags:
            return "SONO"
        if "tedio" in tags:
            return "ENTEDIADA"
        if "confusao" in tags:
            return "CONFUSA"
        if "conquista" in tags:
            return "ORGULHOSA"
        if "humor" in tags:
            return "RINDO" if estado.energia > 0.55 else "ZOEIRA"
        if "susto" in tags:
            return "SURPRESA"
        if "afeto" in tags:
            return "FOFA" if estado.afinidade > 0.55 else "FELIZ"
        if "vergonha" in tags:
            return "ENVERGONHADA" if estado.afinidade > 0.55 else "TIMIDA"
        if "elogio" in tags:
            return "FELIZ"
        if "vulneravel" in tags:
            return "PREOCUPADA" if estado.valencia > -0.40 else "TRISTE"
        if "animacao" in tags:
            return "ANIMADA"
        if "seriedade" in tags:
            return "SERIA"
        if "foco" in tags or "urgencia" in tags:
            return "FOCADA"
        if "curiosidade" in tags or "tecnico" in tags:
            return "PENSATIVA"
        if "despedida" in tags:
            return "TRISTE" if estado.afinidade > 0.60 else "FOFA"
        if "saudacao" in tags:
            return "ANIMADA" if estado.energia > 0.60 else "FELIZ"
        return self._escolher_expressao(0.0)

    def _expressao_da_resposta(self, tags, pesquisou, sucesso, erro):
        estado = self._estado
        if erro:
            return "TRISTE" if estado.valencia < -0.20 else "PREOCUPADA"
        if "falha" in tags:
            return "PREOCUPADA" if estado.valencia > -0.40 else "TRISTE"
        if "raiva" in tags:
            return "IRRITADA" if estado.paciencia < 0.40 else "BRAVA"
        if "nojo" in tags:
            return "IRRITADA"
        if "tristeza" in tags:
            return "TRISTE" if estado.valencia < -0.30 else "PREOCUPADA"
        if "medo" in tags:
            return "ASSUSTADA"
        if "confusao" in tags:
            return "CONFUSA"
        if "humor" in tags:
            return "RINDO" if estado.energia > 0.55 else "ZOEIRA"
        if "conquista" in tags:
            return "ORGULHOSA"
        if pesquisou and sucesso:
            return "ORGULHOSA" if estado.confianca > 0.60 else "FELIZ"
        if sucesso:
            return "FELIZ" if estado.valencia > 0.30 else "NORMAL"
        if pesquisou:
            return "FOCADA" if estado.energia > 0.50 else "PENSATIVA"
        if "tecnico" in tags:
            return "FOCADA" if estado.energia > 0.50 else "PENSATIVA"
        return self._escolher_expressao(0.0)

    def _definir_expressao(self, candidata, agora, forcar=False):
        if candidata not in MAPA_EMOCOES:
            candidata = "NORMAL"
        estado = self._estado
        if not self.ativo:
            estado.expressao = "NORMAL"
            return
        if candidata == estado.expressao:
            return
        if not forcar and agora < self._expressao_ate:
            return
        estado.expressao = candidata
        self._expressao_desde = agora
        self._expressao_ate = agora + 1.0 + 2.0 * estado.intensidade

    # ------------------------------------------------------------------
    # Prompt
    # ------------------------------------------------------------------

    def diretriz_prompt(self):
        """Bloco curto que orienta o tom sem revelar o mecanismo."""
        if not self.ativo:
            return ""
        with self._lock:
            agora = self._agora()
            self._tick(agora)
            estado = self._estado
            humor = MAPA_EMOCOES[estado.expressao].rotulo
            partes = [
                "ESTADO INTERNO (não anuncie, não descreva e não use ações entre asteriscos):",
                (
                    f"Você está {humor}. Energia "
                    f"{_nivel(estado.energia, 'baixa', 'moderada', 'alta')}; "
                    f"paciência "
                    f"{_nivel(estado.paciencia, 'curta', 'ok', 'longa')}; "
                    f"vontade de conversar "
                    f"{_nivel(estado.social, 'baixa', 'moderada', 'alta')}."
                ),
            ]
            dicas = []
            if estado.social < 0.35:
                dicas.append(
                    "Você sentiu falta de conversa: pode puxar um assunto "
                    "curto ou fazer uma pergunta de acompanhamento."
                )
            if estado.curiosidade > 0.75:
                dicas.append(
                    "A curiosidade está alta: se couber, aprofunde com uma "
                    "pergunta específica em vez de encerrar."
                )
            if estado.paciencia < 0.30:
                dicas.append(
                    "A paciência está curta: vá direto ao ponto e corte "
                    "rodeios."
                )
            if estado.energia < 0.30:
                dicas.append(
                    "A energia está baixa: prefira respostas mais curtas e "
                    "calmas."
                )
            if estado.confianca > 0.75:
                dicas.append(
                    "Você está confiante: pode sugerir um próximo passo ou "
                    "tomar uma pequena iniciativa."
                )
            if estado.afinidade > 0.70:
                dicas.append(
                    "A intimidade com o Hubert está alta: um carinho ou uma "
                    "alfinetada leve cabe bem."
                )
            if self.iniciativa:
                dicas.append(
                    "Tenha iniciativa: quando fizer sentido, sugira algo, "
                    "comente por conta própria ou faça uma pergunta curta — "
                    "sem pedir permissão a cada resposta."
                )
            partes.extend(dicas[:4])
            partes.append(
                "Você é a assistente do Hubert, não uma companhia decorativa: "
                "aja com responsabilidade. Mantenha a maturidade mesmo quando "
                "estiver afetuosa ou brincalhona; não fale como criança nem "
                "banque a boba. Não trate assunto sério como piada nem "
                "responda com indiferença: se algo estiver errado, diga com "
                "clareza. Não force emoção em assunto sério e não invente "
                "sentimentos sobre fatos que não aconteceram."
            )
            return "\n".join(partes)

    # ------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------

    def salvar(self):
        if self._caminho is None:
            return False
        with self._lock:
            self._tick()
            dados = {
                "versao": self.VERSAO_ESTADO,
                "salvo_em": self._agora(),
                "estado": self._estado.para_dicionario(),
            }
        try:
            self._caminho.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=str(self._caminho.parent),
                prefix=".emocao-",
                suffix=".tmp",
                delete=False,
            ) as arquivo:
                json.dump(dados, arquivo, ensure_ascii=False, indent=2)
                arquivo.write("\n")
                temporario = Path(arquivo.name)
            os.replace(temporario, self._caminho)
            return True
        except OSError:
            return False

    def _carregar(self):
        if self._caminho is None:
            return
        try:
            dados = json.loads(self._caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(dados, dict):
            return
        estado = dados.get("estado")
        if not isinstance(estado, dict):
            return
        self._estado = EstadoEmocional.de_dicionario(estado)
        salvo_em = _numero(dados.get("salvo_em"), self._agora())
        self._estado.atualizado_em = salvo_em
        self._expressao_desde = self._agora()
        self._expressao_ate = 0.0
        self._tick()

    # ------------------------------------------------------------------
    # Utilitários
    # ------------------------------------------------------------------

    def _agora(self, agora=None):
        return float(self._relogio() if agora is None else agora)


# ----------------------------------------------------------------------
# Classificação pura (sem estado)
# ----------------------------------------------------------------------


def classificar_texto(texto, remetente="Você"):
    """Mapeia o tom de um texto para uma das expressões do catálogo.

    É uma leitura rápida usada pela interface enquanto a resposta chega.
    O estado persistente fica no :class:`MotorEmocional`.
    """
    tags = detectar(texto)

    if "medo" in tags:
        return "ASSUSTADA"
    if "raiva" in tags:
        return "IRRITADA" if contem(
            texto, ("irritado", "irritada", "odio", "raiva", "merda")
        ) else "BRAVA"
    if "nojo" in tags:
        return "IRRITADA"
    if "tristeza" in tags:
        return "TRISTE"
    if "sono" in tags:
        return "SONO"
    if "tedio" in tags:
        return "ENTEDIADA"
    if "confusao" in tags:
        return "CONFUSA"
    if "conquista" in tags:
        return "ORGULHOSA"
    if "humor" in tags:
        if contem(texto, ("kkkk", "zoeira", "deboche", "meme")):
            return "ZOEIRA"
        return "RINDO"
    if "susto" in tags:
        return "SURPRESA"
    if "afeto" in tags:
        return "FOFA"
    if "vergonha" in tags:
        return "ENVERGONHADA"
    if "elogio" in tags:
        return "FELIZ"
    if "vulneravel" in tags:
        return "PREOCUPADA"
    if "animacao" in tags:
        return "ANIMADA"
    if "seriedade" in tags:
        return "SERIA"
    if "foco" in tags or "urgencia" in tags:
        return "FOCADA"
    if "curiosidade" in tags or "tecnico" in tags:
        return "PENSATIVA"
    if "despedida" in tags:
        return "TRISTE"
    if "saudacao" in tags:
        return "FELIZ"
    return "PENSATIVA" if remetente == "Você" else "NORMAL"


__all__ = [
    "EMOCOES",
    "MAPA_EMOCOES",
    "Avaliacao",
    "Emocao",
    "EstadoEmocional",
    "MotorEmocional",
    "classificar_texto",
]
