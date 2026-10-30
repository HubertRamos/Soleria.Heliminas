"""Fala das respostas do chat (fora do modo de conversa contínua)."""

from __future__ import annotations

import threading

from soleria.logging_utils import log_erro

from .speech import Falante
from .tts import Sintetizador


class FalaRespostas:
    """Fala as respostas do chat, com streaming opcional.

    O sintetizador é criado sob demanda: quem não liga a fala nunca paga
    o custo de importar/carregar os motores de TTS.
    """

    def __init__(self, obter_motor=None, ao_erro=None):
        self._obter_motor = obter_motor or (lambda: "padrao")
        self.ao_erro = ao_erro

        self._sintetizador = None
        self._motor_atual = object()
        self._falante = None
        self._streaming = True
        self._lock = threading.RLock()
        self._erro_avisado = False

    # ------------------------------------------------------------------
    # API usada pelo chat
    # ------------------------------------------------------------------

    def iniciar(self, streaming=True):
        """Prepara uma resposta. Retorna False se o TTS não carregar."""
        self.parar()
        try:
            sintetizador = self._obter_sintetizador()
        except Exception as erro:
            self._falha(erro)
            return False

        falante = Falante(sintetizador)
        with self._lock:
            self._falante = falante
            self._streaming = bool(streaming)
        return True

    def adicionar(self, trecho):
        falante = self._falante_atual()
        if falante is not None:
            falante.adicionar(trecho)

    def limpar(self):
        """Descarta a fala parcial (usado quando a resposta vira pesquisa)."""
        falante = self._falante_atual()
        if falante is not None:
            falante.limpar()

    def finalizar(self, texto=None):
        """Termina de enfileirar a fala sem bloquear o chat."""
        falante = self._falante_atual()
        if falante is None:
            return
        try:
            if texto and not self._streaming:
                falante.adicionar(texto)
            falante.finalizar()
        except Exception as erro:
            log_erro(erro)

    def parar(self):
        with self._lock:
            falante = self._falante
            self._falante = None
            sintetizador = self._sintetizador
        if falante is not None:
            try:
                falante.parar()
            except Exception as erro:
                log_erro(erro)
        if sintetizador is not None:
            try:
                sintetizador.parar()
            except Exception:
                pass

    def reconfigurar(self):
        """Esquece o motor atual para que a próxima fala use a nova escolha."""
        self.parar()
        with self._lock:
            self._sintetizador = None
            self._motor_atual = object()
            self._erro_avisado = False

    def fechar(self):
        self.parar()
        with self._lock:
            self._sintetizador = None

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _falante_atual(self):
        with self._lock:
            return self._falante

    def _obter_sintetizador(self):
        motor = str(self._obter_motor() or "").strip()
        if motor == "padrao":
            motor = ""

        with self._lock:
            if self._sintetizador is not None and motor == self._motor_atual:
                return self._sintetizador
            anterior = self._sintetizador
            self._sintetizador = None

        if anterior is not None:
            try:
                anterior.parar()
            except Exception:
                pass

        sintetizador = Sintetizador(motor=motor or None)
        with self._lock:
            self._sintetizador = sintetizador
            self._motor_atual = motor
            self._erro_avisado = False
        return sintetizador

    def _falha(self, erro):
        log_erro(erro)
        with self._lock:
            avisar = not self._erro_avisado
            self._erro_avisado = True
        if avisar and self.ao_erro:
            try:
                self.ao_erro(
                    "Não consegui carregar a voz das respostas. "
                    "Instale edge-tts, piper-tts ou pyttsx3."
                )
            except Exception as erro_aviso:
                log_erro(erro_aviso)


__all__ = ["FalaRespostas"]
