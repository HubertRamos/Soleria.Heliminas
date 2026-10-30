"""Junta captura, OCR e janela em foco numa observação única.

A decisão de quando olhar e o que fazer com o comentário fica com o
orquestrador (:mod:`soleria.app`); aqui só se produz o retrato textual da
tela e se decide quando ele não deve nem ser enviado ao modelo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from config import TELA_APPS_OCULTOS, TELA_MAX_CARACTERES, OCR_IDIOMAS
from soleria.logging_utils import log_evento
from soleria.screen.capture import (
    CapturaIndisponivel,
    capturar_tela,
    motivo_indisponivel as captura_indisponivel,
)
from soleria.screen.ocr import (
    OCRIndisponivel,
    extrair_texto,
    motivo_indisponivel as ocr_indisponivel,
)
from soleria.screen.windows import Janela, janela_em_foco

# Aplicativos de terminal: só neles vale a pena desconfiar que o texto é a
# própria interface da Soleria.
TERMINAIS = {
    "kitty",
    "alacritty",
    "foot",
    "wezterm",
    "ghostty",
    "konsole",
    "gnome-terminal",
    "xfce4-terminal",
    "xterm",
    "st",
    "terminator",
    "tilix",
}

# Marcadores da TUI. Três deles juntos significam que a captura é a própria
# conversa; um ou dois podem aparecer em páginas e anotações sobre a Soleria.
_MARCADORES_SOLERIA = (
    "ctrl+p comandos",
    "tab falar",
    "enter enviar",
    "◆ soleria",
    "ia local · privada",
    "○ pronta",
)


class TelaIndisponivel(RuntimeError):
    """A captura ou o OCR falharam; pode valer avisar o usuário."""


class TelaIgnorada(RuntimeError):
    """Não é hora ou não faz sentido olhar esta tela."""


@dataclass(frozen=True)
class Observacao:
    aplicativo: str
    titulo: str
    texto: str
    impressao: frozenset = field(default_factory=frozenset)

    @property
    def janela(self):
        return Janela(self.aplicativo, self.titulo)


def impressao(texto):
    """Conjunto de palavras usado para medir o que mudou na tela."""
    palavras = re.findall(r"[^\W_]+", str(texto or "").casefold())
    return frozenset(palavra for palavra in palavras if len(palavra) >= 3)


def mudanca(anterior, atual):
    """Fração de palavras que mudou entre duas impressões (0 a 1)."""
    anterior = anterior or frozenset()
    atual = atual or frozenset()
    if not anterior and not atual:
        return 0.0
    if not anterior or not atual:
        return 1.0
    uniao = anterior | atual
    if not uniao:
        return 0.0
    return 1.0 - (len(anterior & atual) / len(uniao))


def parece_soleria(texto):
    achados = sum(
        1 for marcador in _MARCADORES_SOLERIA if marcador in texto.casefold()
    )
    return achados >= 3


def _foco_na_soleria(janela):
    if janela is None:
        return False
    if janela.aplicativo.casefold() not in TERMINAIS:
        return False
    # O ChatUI marca o título da própria janela como "Soleria" ao iniciar.
    return janela.titulo.strip().casefold().startswith("soleria")


def _parece_segredo(texto):
    """Evita comentar linhas que claramente carregam credenciais."""
    padrao = re.compile(
        r"(senha|password|passwd|token|api[_-]?key|secret)\s*[:=]\s*\S+",
        re.IGNORECASE,
    )
    return bool(padrao.search(texto or ""))


class ObservadorTela:
    """Uma olhada na tela: captura, OCR, janela em foco e filtros."""

    def __init__(
        self,
        idiomas=OCR_IDIOMAS,
        limite=TELA_MAX_CARACTERES,
        ocultos=TELA_APPS_OCULTOS,
    ):
        self.idiomas = idiomas
        self.limite = max(200, int(limite))
        self.ocultos = {str(item).casefold() for item in ocultos}

    def disponivel(self):
        motivo = captura_indisponivel() or ocr_indisponivel()
        return (motivo is None, motivo)

    def observar(self):
        disponivel, motivo = self.disponivel()
        if not disponivel:
            raise TelaIndisponivel(motivo or "captura ou OCR indisponíveis")

        janela = janela_em_foco()
        if janela and janela.aplicativo.casefold() in self.ocultos:
            raise TelaIgnorada(
                f"{janela.aplicativo} está na lista de aplicativos ignorados"
            )
        if _foco_na_soleria(janela):
            raise TelaIgnorada("o foco está na própria conversa da Soleria")

        try:
            png = capturar_tela()
            texto = extrair_texto(png, self.limite, idiomas=self.idiomas)
        except (CapturaIndisponivel, OCRIndisponivel) as erro:
            raise TelaIndisponivel(str(erro)) from erro

        texto = str(texto or "").strip()
        if not texto:
            raise TelaIgnorada("não havia texto legível na tela")

        if not (janela and janela.titulo.strip()) and parece_soleria(texto):
            # Sem título não dá para saber qual janela está em foco; aí os
            # marcadores da própria TUI são a única pista disponível.
            raise TelaIgnorada("a tela mostra a própria conversa da Soleria")

        if _parece_segredo(texto):
            log_evento("Tela: captura descartada por conter credenciais")
            raise TelaIgnorada("a tela parece conter senhas ou tokens")

        return Observacao(
            aplicativo=janela.aplicativo if janela else "",
            titulo=janela.titulo if janela else "",
            texto=texto,
            impressao=impressao(texto),
        )
