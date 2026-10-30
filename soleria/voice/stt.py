"""Transcrição de fala com faster-whisper."""

from config import IDIOMA_STT, MODELO_STT
from soleria.logging_utils import log_erro


class Transcritor:
    def __init__(self, modelo=MODELO_STT, idioma=IDIOMA_STT):
        from faster_whisper import WhisperModel

        self.modelo = WhisperModel(modelo, device="auto", compute_type="auto")
        self.idioma = idioma

    def transcrever(self, audio):
        if audio is None or len(audio) == 0:
            return ""
        try:
            segmentos, _ = self.modelo.transcribe(
                audio,
                language=self.idioma,
                beam_size=5,
                vad_filter=True,
            )
            return " ".join(seg.text.strip() for seg in segmentos).strip()
        except Exception as erro:
            log_erro(erro)
            return ""
