"""Entrada de voz por push-to-talk (tecla Tab).

Diferente do modo de voz contínuo, aqui cada gravação é isolada: a
primeira tecla abre o microfone, a fala termina no silêncio (ou quando o
usuário aperta Tab de novo) e o texto transcrito vai para a linha de
entrada do chat.
"""

from __future__ import annotations

import threading

from soleria.logging_utils import log_erro

from .listener import Ouvinte
from .stt import Transcritor


class EntradaVoz:
    def __init__(
        self,
        ao_texto,
        ao_status=None,
        ao_aviso=None,
        ao_fim=None,
    ):
        self.ao_texto = ao_texto
        self.ao_status = ao_status
        self.ao_aviso = ao_aviso
        self.ao_fim = ao_fim

        self._ouvinte = None
        self._transcritor = None
        self._thread = None
        self._lock = threading.RLock()
        self._ativo = threading.Event()
        self._finalizar = threading.Event()
        self._cancelado = threading.Event()
        self._manter = threading.Event()

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    @property
    def ativo(self):
        return self._ativo.is_set()

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def iniciar(self, manter=False):
        """Começa uma gravação. Retorna False se já havia uma em curso.

        ``manter`` evita que o silêncio encerre a gravação enquanto o
        usuário segura a tecla; é desligado quando ele solta (ou quando a
        UI conclui que foi só um toque).
        """
        with self._lock:
            if self._ativo.is_set():
                return False
            self._ativo.set()
            self._finalizar.clear()
            self._cancelado.clear()
            if manter:
                self._manter.set()
            else:
                self._manter.clear()
            self._thread = threading.Thread(
                target=self._loop, name="soleria-ptt", daemon=True
            )
            self._thread.start()
            return True

    def manter(self, ativo):
        """Impede (ou volta a permitir) que o silêncio pare a gravação."""
        if ativo:
            self._manter.set()
        else:
            self._manter.clear()

    def finalizar(self):
        """Pede para parar de gravar e transcrever o que já foi captado."""
        self._finalizar.set()

    def cancelar(self):
        """Descarta a gravação atual sem transcrever."""
        self._cancelado.set()
        self._finalizar.set()
        self._manter.clear()
        ouvinte = self._ouvinte
        if ouvinte is not None:
            try:
                # Fecha o stream e faz o laço de captura retornar.
                ouvinte.parar()
            except Exception as erro:
                log_erro(erro)

    def fechar(self):
        self.cancelar()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

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

    def _aviso(self, texto):
        if not self.ao_aviso:
            return
        try:
            self.ao_aviso(texto)
        except Exception as erro:
            log_erro(erro)

    def _fim(self):
        if not self.ao_fim:
            return
        try:
            self.ao_fim()
        except Exception as erro:
            log_erro(erro)

    def _loop(self):
        try:
            self._status("carregando transcrição...")
            if self._transcritor is None:
                self._transcritor = Transcritor()

            if self._cancelado.is_set():
                return

            if self._ouvinte is None:
                self._ouvinte = Ouvinte()

            if not self._ouvinte.iniciar():
                self._aviso(
                    "Não consegui abrir o microfone. Verifique se o "
                    "PipeWire/PulseAudio está respondendo."
                )
                return

            self._status("gravando… fale agora")
            audio = self._ouvinte.gravar_ate_silencio(
                callback_estado=self._status,
                deve_parar=lambda: (
                    self._finalizar.is_set()
                    or self._cancelado.is_set()
                    or not self._ativo.is_set()
                ),
                manter_gravando=lambda: self._manter.is_set(),
            )

            if self._cancelado.is_set() or audio is None:
                if audio is None and not self._cancelado.is_set():
                    self._aviso(
                        "Não ouvi nada. Aperte Tab e fale um pouco mais alto."
                    )
                return

            self._status("transcrevendo...")
            texto = self._transcritor.transcrever(audio)

            if self._cancelado.is_set():
                return

            if texto and self.ao_texto:
                try:
                    self.ao_texto(texto)
                except Exception as erro:
                    log_erro(erro)
                    self._aviso("Não consegui inserir o texto transcrito.")
            elif not texto:
                self._aviso("Não entendi o áudio. Tente de novo.")

        except Exception as erro:
            log_erro(erro)
            self._aviso("Não consegui gravar sua voz. Veja o log.")
        finally:
            if self._ouvinte is not None:
                try:
                    self._ouvinte.parar()
                except Exception:
                    pass
            self._ativo.clear()
            self._manter.clear()
            self._fim()


__all__ = ["EntradaVoz"]
