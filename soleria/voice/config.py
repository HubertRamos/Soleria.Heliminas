"""Constantes e ajustes do modo de voz."""

import os

from config import (
    FALA_TRECHO_MAX,
    IDIOMA_STT,
    MODELO_STT,
    MOTOR_TTS,
    PIPER_VOZ,
)

# ----------------------------------------------------------------------
# Captura de áudio
# ----------------------------------------------------------------------

TAXA_AMOSTRAGEM = 16000
BLOCO_AMOSTRAS = 512
LIMIAR_ENERGIA = 0.02
SILENCIO_SEGUNDOS = 0.8
FALA_MINIMA_SEGUNDOS = 0.3
BUFFER_MAXIMO_SEGUNDOS = 30

# ----------------------------------------------------------------------
# TTS
# ----------------------------------------------------------------------

EDGE_VOZ = os.getenv("SOLERIA_EDGE_VOICE", "pt-BR-ThalitaNeural")
EDGE_VOZ_ALT = os.getenv(
    "SOLERIA_EDGE_VOICE_FALLBACK", "pt-BR-FranciscaNeural"
)


def _env_int_local(nome, padrao):
    try:
        return int(os.getenv(nome, str(padrao)))
    except (TypeError, ValueError):
        return padrao


def _env_float_local(nome, padrao):
    try:
        return float(os.getenv(nome, str(padrao)))
    except (TypeError, ValueError):
        return padrao


# O Edge TTS às vezes devolve NoAudioReceived de forma passageira
# (limite de requisições/instabilidade do serviço). Tentamos de novo,
# alternando a voz, antes de cair para o Piper/pyttsx3.
EDGE_TENTATIVAS = max(1, _env_int_local("SOLERIA_EDGE_RETRIES", 2))
EDGE_ESPERA = max(0.0, _env_float_local("SOLERIA_EDGE_RETRY_DELAY", 0.8))

_MOTORES_TTS = ("edge", "piper", "pyttsx3")

# ----------------------------------------------------------------------
# Fala em streaming
# ----------------------------------------------------------------------

LIMITE_TRECHO_FALA = max(60, FALA_TRECHO_MAX)

# Reexportados para quem preferir ajustar tudo por este módulo.
__all__ = [
    "BLOCO_AMOSTRAS",
    "BUFFER_MAXIMO_SEGUNDOS",
    "EDGE_ESPERA",
    "EDGE_TENTATIVAS",
    "EDGE_VOZ",
    "EDGE_VOZ_ALT",
    "FALA_MINIMA_SEGUNDOS",
    "FALA_TRECHO_MAX",
    "IDIOMA_STT",
    "LIMIAR_ENERGIA",
    "LIMITE_TRECHO_FALA",
    "MODELO_STT",
    "MOTOR_TTS",
    "PIPER_VOZ",
    "SILENCIO_SEGUNDOS",
    "TAXA_AMOSTRAGEM",
]
