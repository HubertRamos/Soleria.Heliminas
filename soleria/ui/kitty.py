"""Protocolo gráfico do Kitty (e compatíveis) para o retrato.

O Kitty desenha a imagem em resolução nativa através de placeholders
Unicode: um caractere privado marca cada célula e o terminal desenha a
imagem por cima, acompanhando o texto. Fora do Kitty, a TUI cai nos blocos
Unicode.
"""

import base64
import io
import os

PLACEHOLDER_KITTY = "\U0010EEEE"

DIACRITICOS = tuple(
    chr(int(codigo, 16))
    for codigo in (
        "0305 030D 030E 0310 0312 033D 033E 033F "
        "0346 034A 034B 034C 0350 0351 0352 0357 "
        "035B 0363 0364 0365 0366 0367 0368 0369 "
        "036A 036B 036C 036D 036E 036F 0483 0484 "
        "0485 0486 0487 0592 0593 0594 0595 0597 "
        "0598 0599 059C 059D 059E 059F 05A0 05A1 "
        "05A8 05A9 05AB 05AC 05AF 05C4 0610 0611 "
        "0612 0613 0614 0615 0616 0617 0657 0658 "
        "0659 065A 065B 065D 065E 06D6 06D7 06D8 "
        "06D9 06DA 06DB 06DC 06DF 06E0 06E1 06E2 "
        "06E4 06E7 06E8 06EB 06EC 0730 0732 0733 "
        "0735 0736 073A 073D 073F 0740 0741 0743 "
        "0745 0747 0749 074A 07EB 07EC 07ED 07EE "
        "07EF 07F0 07F1 07F3 0816 0817 0818 0819 "
        "081B 081C 081D 081E 081F 0820 0821 0822 "
        "0823 0825 0826 0827 0829 082A 082B 082C "
        "082D 0951 0953 0954 0F82 0F83 0F86 0F87 "
        "135D 135E 135F 17DD 193A 1A17 1A75 1A76 "
        "1A77 1A78 1A79 1A7A 1A7B 1A7C 1B6B 1B6D "
        "1B6E 1B6F 1B70 1B71 1B72 1B73 1CD0 1CD1 "
        "1CD2 1CDA 1CDB 1CE0 1DC0 1DC1 1DC3 1DC4 "
        "1DC5 1DC6 1DC7 1DC8 1DC9 1DCB 1DCC 1DD1 "
        "1DD2 1DD3 1DD4 1DD5 1DD6 1DD7 1DD8 1DD9 "
        "1DDA 1DDB 1DDC 1DDD 1DDE 1DDF 1DE0 1DE1 "
        "1DE2 1DE3 1DE4 1DE5 1DE6 1DFE 20D0 20D1 "
        "20D4 20D5 20D6 20D7 20DB 20DC 20E1 20E7 "
        "20E9 20F0 2CEF 2CF0 2CF1 2DE0 2DE1 2DE2 "
        "2DE3 2DE4 2DE5 2DE6 2DE7 2DE8 2DE9 2DEA "
        "2DEB 2DEC 2DED 2DEE 2DEF 2DF0 2DF1 2DF2 "
        "2DF3 2DF4 2DF5 2DF6 2DF7 2DF8 2DF9 2DFA "
        "2DFB 2DFC 2DFD 2DFE 2DFF A66F A67C A67D "
        "A6F0 A6F1 A8E0 A8E1 A8E2 A8E3 A8E4 A8E5 "
        "A8E6 A8E7 A8E8 A8E9 A8EA A8EB A8EC A8ED "
        "A8EE A8EF A8F0 A8F1 AAB0 AAB2 AAB3 AAB7 "
        "AAB8 AABE AABF AAC1 FE20 FE21 FE22 FE23 "
        "FE24 FE25 FE26 10A0F 10A38 1D185 1D186 1D187 "
        "1D188 1D189 1D1AA 1D1AB 1D1AC 1D1AD 1D242 1D243 "
        "1D244 "
    ).split()
)


def usar_imagem_kitty(modo, ambiente=None):
    """Decide se o retrato usa o protocolo gráfico do Kitty."""
    ambiente = os.environ if ambiente is None else ambiente
    modo = (modo or "").strip().casefold()
    if modo in {"blocos", "block", "blocks", "off", "0", "nao", "não"}:
        return False
    if modo in {"kitty", "1", "on", "sim", "true"}:
        # Forçado: funciona também dentro do tmux (com passthrough).
        return True
    if modo not in {"auto", ""}:
        return False
    if ambiente.get("TMUX"):
        # Sem passthrough explícito o tmux engoliria os escapes e os
        # placeholders apareceriam como quadradinhos.
        return False
    if ambiente.get("KITTY_WINDOW_ID"):
        return True
    if "kitty" in ambiente.get("TERM", "").casefold():
        return True
    return ambiente.get("TERM_PROGRAM", "").casefold() in {
        "kitty",
        "ghostty",
    }


def escape_kitty(controle, payload=None, ambiente=None):
    """Monta um comando do protocolo gráfico, com passthrough no tmux."""
    sequencia = f"\x1b_G{controle}"
    if payload:
        sequencia += ";" + payload
    sequencia += "\x1b\\"
    ambiente = os.environ if ambiente is None else ambiente
    if ambiente.get("TMUX"):
        sequencia = (
            "\x1bPtmux;" + sequencia.replace("\x1b", "\x1b\x1b") + "\x1b\\"
        )
    return sequencia


def png_bytes(imagem):
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return buffer.getvalue()


def comandos_imagem_kitty(id_imagem, dados_png, colunas, linhas):
    """Transmite o PNG e cria o posicionamento virtual usado pelas células."""
    texto = base64.b64encode(dados_png).decode("ascii")
    pedacos = [texto[i:i + 4096] for i in range(0, len(texto), 4096)]
    comandos = []
    for indice, pedaco in enumerate(pedacos or [""]):
        if indice == 0:
            controle = f"a=t,f=100,q=2,i={id_imagem}"
            if len(pedacos) > 1:
                controle += ",m=1"
        else:
            controle = "m=0" if indice == len(pedacos) - 1 else "m=1"
        comandos.append(escape_kitty(controle, pedaco))
    comandos.append(
        escape_kitty(
            f"a=p,U=1,q=2,i={id_imagem},c={colunas},r={linhas}"
        )
    )
    return "".join(comandos)


def dimensoes_celula(imagem, largura_max, altura_max, fator_supersample=2):
    """Tamanho em células que preserva a proporção da imagem.

    O mesmo critério do raster em blocos: 2 pixels por coluna e 4 por
    linha, o que corresponde às células tipicamente duas vezes mais altas
    que largas.
    """
    largura_px = max(1.0, imagem.width / fator_supersample)
    altura_px = max(1.0, imagem.height / (fator_supersample * 2))
    escala = min(largura_max / largura_px, altura_max / altura_px)
    return (
        max(1, int(largura_px * escala)),
        max(1, int(altura_px * escala)),
    )


# Aliases privados mantidos para compatibilidade.
_PLACEHOLDER_KITTY = PLACEHOLDER_KITTY
_DIACRITICOS = DIACRITICOS
_usar_imagem_kitty = usar_imagem_kitty
_escape_kitty = escape_kitty
_png_bytes = png_bytes
_comandos_imagem_kitty = comandos_imagem_kitty
_dimensoes_celula = dimensoes_celula
