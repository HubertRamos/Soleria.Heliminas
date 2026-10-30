"""Captura do microfone com detecção de fala por energia (VAD)."""

import queue
import threading
import time

import numpy as np

from soleria.logging_utils import log_erro

from .config import (
    BLOCO_AMOSTRAS,
    BUFFER_MAXIMO_SEGUNDOS,
    FALA_MINIMA_SEGUNDOS,
    LIMIAR_ENERGIA,
    SILENCIO_SEGUNDOS,
    TAXA_AMOSTRAGEM,
)


class Ouvinte:
    def __init__(self):
        self._fila = queue.Queue(maxsize=100)
        self._parar = threading.Event()
        self._stream = None
        self._aberto = False
        self._ultimo_aviso = 0.0
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status):
        if status:
            # O callback de áudio roda em tempo real; evita escrever no
            # log a cada bloco se o driver insistir no mesmo aviso.
            agora = time.monotonic()
            if agora - self._ultimo_aviso >= 10:
                self._ultimo_aviso = agora
                log_erro(RuntimeError(f"Áudio: {status}"))
        bloco = indata[:, 0].copy()
        try:
            self._fila.put_nowait(bloco)
        except queue.Full:
            # Descarta o bloco mais antigo para não atrasar o áudio atual.
            try:
                self._fila.get_nowait()
            except queue.Empty:
                pass
            try:
                self._fila.put_nowait(bloco)
            except queue.Full:
                pass

    def iniciar(self):
        with self._lock:
            if self._aberto:
                return True
            try:
                import sounddevice as sd

                self._parar.clear()
                self._stream = sd.InputStream(
                    samplerate=TAXA_AMOSTRAGEM,
                    blocksize=BLOCO_AMOSTRAS,
                    channels=1,
                    dtype="float32",
                    callback=self._callback,
                )
                self._stream.start()
                self._aberto = True
                return True
            except Exception as erro:
                log_erro(erro)
                self._fechar_stream()
                self._aberto = False
                return False

    def _fechar_stream(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def parar(self):
        with self._lock:
            self._parar.set()
            self._fechar_stream()
            self._aberto = False

    def esvaziar(self):
        while True:
            try:
                self._fila.get_nowait()
            except queue.Empty:
                return

    def gravar_ate_silencio(
        self, callback_estado=None, deve_parar=None, manter_gravando=None
    ):
        if not self._aberto:
            return None

        self.esvaziar()

        blocos = []
        total_amostras = 0
        falando = False
        amostras_silencio = 0
        amostras_fala = 0
        max_amostras = TAXA_AMOSTRAGEM * BUFFER_MAXIMO_SEGUNDOS
        silencio_alvo = int(TAXA_AMOSTRAGEM * SILENCIO_SEGUNDOS)
        fala_minima = int(TAXA_AMOSTRAGEM * FALA_MINIMA_SEGUNDOS)

        if callback_estado:
            callback_estado("ouvindo...")

        while not self._parar.is_set():
            if deve_parar is not None and deve_parar():
                break

            try:
                bloco = self._fila.get(timeout=0.5)
            except queue.Empty:
                continue

            energia = float(np.sqrt(np.mean(np.square(bloco))))
            fala = energia > LIMIAR_ENERGIA

            if fala:
                if not falando:
                    falando = True
                    if callback_estado:
                        callback_estado("te ouvindo...")
                amostras_silencio = 0
                amostras_fala += len(bloco)
                blocos.append(bloco)
                total_amostras += len(bloco)
            elif falando:
                # Enquanto a tecla está pressionada, uma pausa não encerra
                # a gravação: o usuário pode estar pensando.
                if manter_gravando is not None and manter_gravando():
                    amostras_silencio = 0
                    continue
                amostras_silencio += len(bloco)
                blocos.append(bloco)
                total_amostras += len(bloco)
                if amostras_silencio >= silencio_alvo:
                    break

            if total_amostras > max_amostras:
                break

        if self._parar.is_set() or not blocos or amostras_fala < fala_minima:
            return None

        if callback_estado:
            callback_estado("transcrevendo...")

        return np.concatenate(blocos)
