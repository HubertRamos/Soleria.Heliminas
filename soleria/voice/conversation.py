"""Orquestra o ciclo ouvir → transcrever → responder → falar."""

import threading
import time
from pathlib import Path

from config import PIPER_VOZ
from soleria.logging_utils import log_erro

from .listener import Ouvinte
from .speech import Falante
from .stt import Transcritor
from .tts import Sintetizador


class ConversaVoz:
    def __init__(
        self,
        processar,
        ao_transcrever=None,
        ao_responder=None,
        ao_status=None,
        ao_encerrar=None,
        caminho_piper=None,
    ):
        self.processar = processar
        self.ao_transcrever = ao_transcrever
        self.ao_responder = ao_responder
        self.ao_status = ao_status
        self.ao_encerrar = ao_encerrar

        if caminho_piper:
            self._caminho_piper = str(caminho_piper)
        else:
            padrao = Path(PIPER_VOZ)
            self._caminho_piper = str(padrao) if padrao.is_file() else None

        self.ouvinte = None
        self.transcritor = None
        self.sintetizador = None
        self._falante = None

        self._thread = None
        self._ativo = threading.Event()
        self._pronto = threading.Event()
        self._erro_inicializacao = None

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def iniciar(self):
        if self._thread is not None and self._thread.is_alive():
            return
        # Uma tentativa anterior pode ter falhado; o novo ciclo precisa
        # começar sem o erro antigo, senão ``aguardar_pronto`` mentiria.
        self._erro_inicializacao = None
        self._ativo.set()
        self._pronto.clear()
        self._thread = threading.Thread(
            target=self._loop, name="soleria-voz", daemon=True
        )
        self._thread.start()

    def aguardar_pronto(self, timeout=60):
        pronto = self._pronto.wait(timeout=timeout)
        return pronto and not self._erro_inicializacao

    def parar(self, aguardar=False, timeout=2.0):
        self._ativo.clear()

        if self.ouvinte is not None:
            self.ouvinte.parar()
        if self._falante is not None:
            self._falante.parar()
        if self.sintetizador is not None:
            self.sintetizador.parar()

        if aguardar and self._thread is not None:
            self._thread.join(timeout=timeout)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _status(self, texto):
        if not self.ao_status:
            return
        try:
            self.ao_status(texto)
        except Exception as erro:
            log_erro(erro)

    def _encerrar(self, motivo=None):
        if not self.ao_encerrar:
            return
        try:
            self.ao_encerrar(motivo)
        except Exception as erro:
            log_erro(erro)

    def _inicializar(self):
        self._status("carregando modelos de voz...")

        try:
            self.transcritor = Transcritor()
        except Exception as erro:
            log_erro(erro)
            self._erro_inicializacao = (
                "Não consegui carregar o modelo Whisper. "
                "Instale faster-whisper e verifique o log."
            )
            return False

        if not self._ativo.is_set():
            return False

        self._status("carregando sintetizador...")
        try:
            self.sintetizador = Sintetizador(self._caminho_piper)
        except Exception as erro:
            log_erro(erro)
            self._erro_inicializacao = (
                "Não consegui carregar nenhum motor de voz. "
                "Instale edge-tts, piper-tts ou pyttsx3."
            )
            return False

        self._status(f"TTS: {self.sintetizador.nome_motor}")

        if not self._ativo.is_set():
            return False

        self._status("abrindo microfone...")
        self.ouvinte = Ouvinte()
        if not self.ouvinte.iniciar():
            self._erro_inicializacao = (
                "Não consegui abrir o microfone. "
                "Verifique se portaudio está instalado e se o "
                "PipeWire/PulseAudio está respondendo."
            )
            return False

        if not self._ativo.is_set():
            self.ouvinte.parar()
            return False

        self._status("ouvindo...")
        return True

    def _loop(self):
        motivo = None
        try:
            pronto = self._inicializar()
            self._pronto.set()

            if not pronto:
                if self._erro_inicializacao:
                    self._status(self._erro_inicializacao)
                    motivo = self._erro_inicializacao
                return

            self._status("ouvindo...")

            while self._ativo.is_set():
                audio = self.ouvinte.gravar_ate_silencio(
                    callback_estado=self._status
                )
                if not self._ativo.is_set():
                    break

                if audio is None:
                    self._status("ouvindo...")
                    continue

                texto = self.transcritor.transcrever(audio)
                if not self._ativo.is_set():
                    break

                if not texto:
                    self._status("não entendi, tenta de novo")
                    time.sleep(0.3)
                    self._status("ouvindo...")
                    continue

                if self.ao_transcrever:
                    try:
                        self.ao_transcrever(texto)
                    except Exception as erro:
                        log_erro(erro)

                self._status("pensando...")

                # O microfone fica desligado durante a geração e a fala
                # para a própria voz da Soleria não ser captada.
                self.ouvinte.parar()

                falante = Falante(
                    self.sintetizador,
                    ao_falar=lambda: self._status("falando..."),
                )
                self._falante = falante

                try:
                    try:
                        resposta = self.processar(
                            texto,
                            ao_trecho=falante.adicionar,
                            ao_reset=falante.limpar,
                        ) or ""
                    except Exception as erro:
                        log_erro(erro)
                        resposta = (
                            "Tive um problema ao processar sua mensagem."
                        )
                    finally:
                        # Fala o último trecho que não terminou em
                        # pontuação (se a geração tiver terminado).
                        falante.finalizar()

                    if resposta and self.ao_responder:
                        try:
                            self.ao_responder(resposta)
                        except Exception as erro:
                            log_erro(erro)

                    if resposta:
                        self._status("falando...")
                        falante.aguardar()
                finally:
                    falante.parar()
                    self._falante = None

                if self._ativo.is_set():
                    if not self.ouvinte.iniciar():
                        motivo = (
                            "Perdi o acesso ao microfone. "
                            "O modo de voz foi encerrado."
                        )
                        break
                    self.ouvinte.esvaziar()
                    self._status("ouvindo...")

        except Exception as erro:
            log_erro(erro)
            motivo = "O modo de voz foi encerrado por um erro inesperado."
        finally:
            if self.ouvinte is not None:
                self.ouvinte.parar()
            if self.sintetizador is not None:
                self.sintetizador.parar()
            self._ativo.clear()
            self._pronto.set()
            self._encerrar(motivo)
