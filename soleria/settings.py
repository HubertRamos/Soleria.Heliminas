"""Preferências de execução da Soleria.

As configurações ficam num JSON simples para poderem ser alteradas pelo
menu de configurações da TUI sem reiniciar o programa. Os padrões vêm de
:mod:`config` (e, portanto, das variáveis de ambiente); o arquivo guarda os
valores atuais.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import (
    ACOES_ATIVAS,
    EMOCOES_ATIVAS,
    IMAGEM_RETRATO,
    PROATIVAS_ATIVAS,
    RELATORIOS_ATIVOS,
    TELA_ATIVA,
)

CAMINHO_PADRAO = Path.home() / ".config" / "soleria" / "preferencias.json"

_MOTORES = ("padrao", "edge", "piper", "pyttsx3")


@dataclass(frozen=True)
class Definicao:
    chave: str
    rotulo: str
    tipo: str
    descricao: str
    padrao: Any
    opcoes: tuple[str, ...] = ()
    # Algumas opções só passam a valer no próximo início do programa.
    reinicia: bool = False


DEFINICOES = (
    Definicao(
        "falar_respostas",
        "Falar as respostas",
        "bool",
        "A Soleria fala em voz alta as respostas do chat.",
        False,
    ),
    Definicao(
        "falar_streaming",
        "Falar enquanto gera",
        "bool",
        "Começa a falar antes de a resposta terminar de ser escrita.",
        True,
    ),
    Definicao(
        "tts_motor",
        "Motor de voz",
        "escolha",
        "Motor usado para falar. 'padrão' segue o configurado no ambiente.",
        "padrao",
        opcoes=_MOTORES,
    ),
    Definicao(
        "voz_auto_enviar",
        "Enviar ao transcrever",
        "bool",
        "Manda a mensagem sozinho depois de gravar com Tab.",
        False,
    ),
    Definicao(
        "relatorios",
        "Relatórios nas pesquisas",
        "bool",
        "Cria e atualiza relatórios em HTML durante as pesquisas.",
        bool(RELATORIOS_ATIVOS),
    ),
    Definicao(
        "acoes",
        "Abrir aplicativos",
        "bool",
        "Permite pedidos como 'abre o Firefox no YouTube'. Só aplicativos "
        "e sites conhecidos são aceitos.",
        bool(ACOES_ATIVAS),
    ),
    Definicao(
        "emocoes",
        "Estado emocional",
        "bool",
        "A Soleria mantém um humor interno que evolui com a conversa.",
        bool(EMOCOES_ATIVAS),
    ),
    Definicao(
        "proativas",
        "Iniciativa própria",
        "bool",
        "A Soleria pode puxar assunto sozinha após um tempo de silêncio.",
        bool(PROATIVAS_ATIVAS),
    ),
    Definicao(
        "tela",
        "Olhar a tela",
        "bool",
        "De tempos em tempos, lê a tela via OCR e comenta o que você "
        "está fazendo. A imagem não é guardada nem enviada para fora.",
        bool(TELA_ATIVA),
    ),
    Definicao(
        "expressoes",
        "Expressões no retrato",
        "bool",
        "O retrato acompanha o estado emocional da Soleria.",
        True,
    ),
    Definicao(
        "retrato",
        "Retrato no terminal",
        "escolha",
        "Como desenhar o retrato: automático, Kitty ou blocos.",
        IMAGEM_RETRATO,
        opcoes=("auto", "kitty", "blocos"),
        reinicia=True,
    ),
)

_POR_CHAVE = {definicao.chave: definicao for definicao in DEFINICOES}

_ROTULOS_ESCOLHA = {
    "padrao": "padrão",
    "auto": "automático",
    "kitty": "Kitty",
    "blocos": "blocos",
}


def definicao(chave: str) -> Definicao:
    return _POR_CHAVE[chave]


def rotulo_valor(chave: str, valor: Any) -> str:
    if chave == "tts_motor":
        return _ROTULOS_ESCOLHA.get(str(valor), str(valor))
    if chave == "retrato":
        return _ROTULOS_ESCOLHA.get(str(valor), str(valor))
    return str(valor)


def _padroes() -> dict[str, Any]:
    return {definicao.chave: definicao.padrao for definicao in DEFINICOES}


def _normalizar(chave: str, valor: Any) -> Any:
    """Valida e converte um valor carregado do JSON ou vindo da TUI."""
    definicao_ = _POR_CHAVE.get(chave)
    if definicao_ is None:
        return valor

    if definicao_.tipo == "bool":
        if isinstance(valor, str):
            return valor.strip().casefold() in {"1", "true", "sim", "yes", "on"}
        return bool(valor)

    if definicao_.tipo == "escolha":
        valor = str(valor)
        if valor in definicao_.opcoes:
            return valor
        return definicao_.padrao

    return valor


class Preferencias:
    """Leitor/gravador thread-safe das preferências do usuário."""

    def __init__(self, caminho=None):
        caminho = caminho or os.getenv("SOLERIA_PREFS") or CAMINHO_PADRAO
        self.caminho = Path(os.path.expandvars(str(caminho))).expanduser()
        self._lock = threading.RLock()
        self._valores = _padroes()
        self._carregar()

    # ------------------------------------------------------------------
    # Leitura e escrita
    # ------------------------------------------------------------------

    def _carregar(self):
        try:
            dados = json.loads(self.caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(dados, dict):
            return
        for chave, valor in dados.items():
            if chave in _POR_CHAVE:
                self._valores[chave] = _normalizar(chave, valor)

    def _salvar(self):
        try:
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
            # Guarda só o que diverge do padrão: se um padrão mudar numa
            # versão nova, quem nunca mexeu naquela opção acompanha.
            dados = {
                chave: valor
                for chave, valor in self._valores.items()
                if chave in _POR_CHAVE
                and valor != _POR_CHAVE[chave].padrao
            }
            conteudo = json.dumps(
                dados, ensure_ascii=False, indent=2, sort_keys=True
            )
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=str(self.caminho.parent),
                prefix=".preferencias-",
                suffix=".tmp",
                delete=False,
            ) as arquivo:
                arquivo.write(conteudo + "\n")
                temporario = Path(arquivo.name)
            os.replace(temporario, self.caminho)
        except OSError:
            # Sem permissão de escrita o menu continua funcionando na
            # sessão atual; só não persiste.
            pass

    def obter(self, chave: str, padrao=None):
        with self._lock:
            if chave in self._valores:
                return self._valores[chave]
            if chave in _POR_CHAVE:
                return _POR_CHAVE[chave].padrao
            return padrao

    def definir(self, chave: str, valor):
        if chave not in _POR_CHAVE:
            raise KeyError(f"Preferência desconhecida: {chave}")
        with self._lock:
            self._valores[chave] = _normalizar(chave, valor)
            self._salvar()
            return self._valores[chave]

    def alternar(self, chave: str):
        with self._lock:
            atual = self.obter(chave)
            return self.definir(chave, not bool(atual))

    def ciclar(self, chave: str, direcao: int = 1):
        definicao_ = _POR_CHAVE.get(chave)
        if definicao_ is None or definicao_.tipo != "escolha":
            return self.obter(chave)
        with self._lock:
            atual = str(self.obter(chave))
            try:
                indice = definicao_.opcoes.index(atual)
            except ValueError:
                indice = 0
            novo = definicao_.opcoes[
                (indice + (1 if direcao >= 0 else -1)) % len(definicao_.opcoes)
            ]
            return self.definir(chave, novo)

    def restaurar(self):
        with self._lock:
            self._valores = _padroes()
            self._salvar()

    def instantaneo(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._valores)


__all__ = [
    "CAMINHO_PADRAO",
    "DEFINICOES",
    "Definicao",
    "Preferencias",
    "definicao",
    "rotulo_valor",
]
