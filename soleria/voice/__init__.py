"""Conversa por voz: STT (faster-whisper) + TTS (Edge, Piper ou pyttsx3) + VAD."""

from .config import (
    BLOCO_AMOSTRAS,
    BUFFER_MAXIMO_SEGUNDOS,
    EDGE_ESPERA,
    EDGE_TENTATIVAS,
    EDGE_VOZ,
    EDGE_VOZ_ALT,
    FALA_MINIMA_SEGUNDOS,
    FALA_TRECHO_MAX,
    IDIOMA_STT,
    LIMIAR_ENERGIA,
    LIMITE_TRECHO_FALA,
    MODELO_STT,
    MOTOR_TTS,
    PIPER_VOZ,
    SILENCIO_SEGUNDOS,
    TAXA_AMOSTRAGEM,
)
from .conversation import ConversaVoz
from .input import EntradaVoz
from .listener import Ouvinte
from .reply import FalaRespostas
from .speech import Falante, extrair_frase
from .stt import Transcritor
from .tts import MotorEdge, MotorPiper, MotorPyttsx3, Sintetizador

__all__ = [
    "BLOCO_AMOSTRAS",
    "BUFFER_MAXIMO_SEGUNDOS",
    "ConversaVoz",
    "EDGE_ESPERA",
    "EDGE_TENTATIVAS",
    "EDGE_VOZ",
    "EDGE_VOZ_ALT",
    "EntradaVoz",
    "FALA_MINIMA_SEGUNDOS",
    "FALA_TRECHO_MAX",
    "FalaRespostas",
    "Falante",
    "IDIOMA_STT",
    "LIMIAR_ENERGIA",
    "LIMITE_TRECHO_FALA",
    "MODELO_STT",
    "MOTOR_TTS",
    "MotorEdge",
    "MotorPiper",
    "MotorPyttsx3",
    "Ouvinte",
    "PIPER_VOZ",
    "SILENCIO_SEGUNDOS",
    "Sintetizador",
    "TAXA_AMOSTRAGEM",
    "Transcritor",
    "extrair_frase",
]
