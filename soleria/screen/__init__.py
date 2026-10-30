"""Olhar a tela: captura, OCR e leitura da janela em foco.

O pacote não guarda imagens nem fala com a rede. A captura vira texto e a
imagem é descartada em seguida.
"""

from soleria.screen.capture import CapturaIndisponivel, capturar_tela
from soleria.screen.ocr import OCRIndisponivel, extrair_texto, normalizar_texto
from soleria.screen.observer import (
    Observacao,
    ObservadorTela,
    TelaIgnorada,
    TelaIndisponivel,
    impressao,
    mudanca,
    parece_soleria,
)
from soleria.screen.windows import Janela, janela_em_foco

__all__ = [
    "CapturaIndisponivel",
    "Janela",
    "OCRIndisponivel",
    "Observacao",
    "ObservadorTela",
    "TelaIgnorada",
    "TelaIndisponivel",
    "capturar_tela",
    "extrair_texto",
    "impressao",
    "janela_em_foco",
    "mudanca",
    "normalizar_texto",
    "parece_soleria",
]
