"""Motores de síntese de fala (Edge, Piper e pyttsx3)."""

import asyncio
import time
from pathlib import Path

import numpy as np

from config import MOTOR_TTS, PIPER_VOZ
from soleria.logging_utils import log_erro, log_evento

from .config import (
    EDGE_ESPERA,
    EDGE_TENTATIVAS,
    EDGE_VOZ,
    EDGE_VOZ_ALT,
    _MOTORES_TTS,
)


# ----------------------------------------------------------------------
# TTS — Edge
# ----------------------------------------------------------------------


class MotorEdge:
    NOME = "edge"
    # O próprio motor repete a requisição e alterna a voz; a fachada não
    # precisa repetir tudo de novo antes de cair para o Piper.
    TENTATIVAS_INTERNAS = True

    def __init__(self, voz=EDGE_VOZ):
        import edge_tts

        self._edge_tts = edge_tts
        self._voz = voz
        self._vozes = [voz]
        if EDGE_VOZ_ALT and EDGE_VOZ_ALT != voz:
            self._vozes.append(EDGE_VOZ_ALT)

    def falar(self, texto):
        if not texto:
            return

        ultimo_erro = None
        for tentativa in range(EDGE_TENTATIVAS):
            voz = self._vozes[tentativa % len(self._vozes)]
            try:
                asyncio.run(self._falar_async(texto, voz))
                return
            except Exception as erro:
                ultimo_erro = erro
                if tentativa + 1 < EDGE_TENTATIVAS:
                    time.sleep(EDGE_ESPERA * (2**tentativa))

        # Não registre o traceback aqui: a fachada Sintetizador registra
        # uma mensagem curta e tenta o próximo motor. O log ficava cheio
        # de pilhas do edge_tts para falhas passageiras.
        raise RuntimeError(
            f"Edge TTS falhou após {EDGE_TENTATIVAS} tentativa(s): "
            f"{ultimo_erro}"
        ) from ultimo_erro

    async def _falar_async(self, texto, voz=None):
        import io

        import sounddevice as sd
        from pydub import AudioSegment

        communicate = self._edge_tts.Communicate(texto, voz or self._voz)
        audio_data = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.extend(chunk["data"])

        if not audio_data:
            raise RuntimeError("Edge TTS não retornou áudio.")

        segmento = AudioSegment.from_file(io.BytesIO(bytes(audio_data)))
        amostras = np.array(segmento.get_array_of_samples())

        if segmento.sample_width == 2:
            amostras = amostras.astype(np.int16)
        elif segmento.sample_width == 1:
            amostras = ((amostras.astype(np.int16) - 128) * 256).astype(
                np.int16
            )
        else:
            amostras = (amostras >> 16).astype(np.int16)

        if segmento.channels == 2:
            amostras = (
                amostras.reshape((-1, 2)).mean(axis=1).astype(np.int16)
            )

        sd.play(amostras, samplerate=segmento.frame_rate)
        sd.wait()

    def parar(self):
        try:
            import sounddevice as sd

            sd.stop()
        except Exception:
            pass


# ----------------------------------------------------------------------
# TTS — Piper
# ----------------------------------------------------------------------


class MotorPiper:
    NOME = "piper"

    def __init__(self, caminho_piper):
        from piper.voice import PiperVoice

        caminho = Path(caminho_piper) if caminho_piper else None
        if caminho is None or not caminho.is_file():
            raise FileNotFoundError(f"Voz Piper não encontrada: {caminho}")
        self._voz = PiperVoice.load(str(caminho))

    def falar(self, texto):
        if not texto:
            return
        import sounddevice as sd

        chunks = list(self._voz.synthesize(texto))
        if not chunks:
            raise RuntimeError("Piper não retornou áudio.")

        taxa = chunks[0].sample_rate
        amostras = np.concatenate(
            [np.asarray(c.audio_int16_array) for c in chunks]
        )
        sd.play(amostras, taxa)
        sd.wait()

    def parar(self):
        try:
            import sounddevice as sd

            sd.stop()
        except Exception:
            pass


# ----------------------------------------------------------------------
# TTS — pyttsx3
# ----------------------------------------------------------------------


class MotorPyttsx3:
    NOME = "pyttsx3"

    def __init__(self):
        import pyttsx3

        self._engine = pyttsx3.init()
        self._engine.setProperty("rate", 170)
        self._escolher_voz_feminina()

    def _escolher_voz_feminina(self):
        try:
            vozes = self._engine.getProperty("voices")
        except Exception:
            return

        def idioma_de(v):
            return " ".join(
                (l.decode() if isinstance(l, bytes) else l)
                for l in (v.languages or [])
            ).lower()

        for v in vozes:
            nome = (v.name or "").lower()
            vid = (v.id or "").lower()
            if ("pt" in idioma_de(v) or "portugu" in nome) and (
                "fem" in nome
                or "f1" in vid
                or "f2" in vid
                or "f3" in vid
            ):
                self._engine.setProperty("voice", v.id)
                return

        for v in vozes:
            if "pt" in idioma_de(v):
                vid = v.id or ""
                if "espeak" in vid.lower() and "+" not in vid:
                    self._engine.setProperty("voice", vid + "+f3")
                else:
                    self._engine.setProperty("voice", vid)
                return

        for v in vozes:
            vid = (v.id or "").lower()
            if "pt" in vid:
                self._engine.setProperty(
                    "voice", v.id + ("+f3" if "+" not in v.id else "")
                )
                return

    def falar(self, texto):
        if not texto:
            return
        self._engine.say(texto)
        self._engine.runAndWait()

    def parar(self):
        try:
            self._engine.stop()
        except Exception:
            pass


# ----------------------------------------------------------------------
# Fachada
# ----------------------------------------------------------------------


def _construir_motor(nome, caminho_piper):
    if nome == "edge":
        return MotorEdge(EDGE_VOZ)
    if nome == "piper":
        return MotorPiper(caminho_piper or PIPER_VOZ)
    if nome == "pyttsx3":
        return MotorPyttsx3()
    raise ValueError(f"Motor TTS desconhecido: {nome}")


class Sintetizador:
    """Tenta os motores em ordem e troca de motor se um falhar em runtime."""

    def __init__(self, caminho_piper=None, motor=None):
        self._motores = []
        self._indice = 0
        self.motor = None
        self.nome_motor = None

        preferido = (
            motor
            if motor in _MOTORES_TTS
            else (MOTOR_TTS if MOTOR_TTS in _MOTORES_TTS else _MOTORES_TTS[0])
        )
        ordem = [preferido] + [m for m in _MOTORES_TTS if m != preferido]

        for nome in ordem:
            try:
                motor = _construir_motor(nome, caminho_piper)
            except Exception as erro:
                log_erro(
                    RuntimeError(f"Motor TTS '{nome}' indisponível: {erro}")
                )
                continue
            self._motores.append((nome, motor))

        if not self._motores:
            raise RuntimeError(
                "Nenhum motor TTS pôde ser carregado. "
                "Instale edge-tts, piper-tts ou pyttsx3."
            )

        self._selecionar(0)

    def _selecionar(self, indice):
        self._indice = indice
        self.nome_motor, self.motor = self._motores[indice]

    def falar(self, texto):
        if not texto:
            return False

        total = len(self._motores)
        for deslocamento in range(total):
            indice = (self._indice + deslocamento) % total
            nome, motor = self._motores[indice]

            # O motor preferido ganha uma segunda chance: falhas do Edge
            # TTS costumam ser passageiras (limite de requisições). Se o
            # motor já repete internamente (Edge), uma tentativa basta.
            tentativas = 2 if indice == self._indice else 1
            if getattr(motor, "TENTATIVAS_INTERNAS", False):
                tentativas = 1
            for tentativa in range(tentativas):
                try:
                    motor.falar(texto)
                    # Não troca a voz preferida por causa de uma falha
                    # passageira: o outro motor vale só para esta frase
                    # e o preferido é tentado de novo na próxima.
                    return True
                except Exception as erro:
                    if tentativa + 1 == tentativas:
                        resumo = (
                            texto
                            if len(texto) <= 80
                            else texto[:77] + "…"
                        )
                        # Se ainda há outro motor para tentar, isso é uma
                        # falha transitória com fallback: registre como
                        # evento, não como erro com pilha.
                        if deslocamento + 1 < total:
                            log_evento(
                                f"TTS '{nome}' falhou em {resumo!r}: "
                                f"{erro}; tentando o próximo motor."
                            )
                        else:
                            log_erro(
                                RuntimeError(
                                    f"Falha no motor TTS '{nome}' "
                                    f"em {resumo!r}: {erro}"
                                )
                            )
                if tentativa + 1 < tentativas:
                    time.sleep(0.5)

        return False

    def parar(self):
        # Com o fallback por frase, qualquer motor pode estar falando.
        for _nome, motor in self._motores:
            try:
                motor.parar()
            except Exception:
                pass
