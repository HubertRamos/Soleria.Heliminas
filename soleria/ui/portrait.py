"""Renderização do retrato da Soleria no painel da TUI.

Concentra carregamento de imagens, rasterização em blocos, protocolo Kitty
e a montagem do painel lateral/topo. A :class:`~soleria.ui.chat.ChatUI`
herda o mixin e fornece o estado (expressão atual, histórico e caches).
"""

from PIL import Image, ImageEnhance, ImageFilter

from soleria.logging_utils import log_erro
from soleria.ui.kitty import (
    DIACRITICOS,
    PLACEHOLDER_KITTY,
    comandos_imagem_kitty,
    dimensoes_celula,
    png_bytes,
)
from soleria.ui.text import (
    achatar,
    centralizar,
    cortar_texto,
    largura_texto,
    quebrar_texto,
    terminal_24bit,
)
from soleria.ui.theme import (
    COR_PAINEL,
    EXPRESSOES,
    HUMORES,
    PASTA_EXPRESSOES,
)

FATOR_SUPERSAMPLE = 2
FUNDO_TERMINAL = (13, 18, 25)
ALPHA_MINIMO = 32
MAX_CACHE_RETRATO = 24

_BAYER_4x4 = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)


def aplicar_dither(pixel, x, y, forca=8):
    r, g, b = pixel[0], pixel[1], pixel[2]
    a = pixel[3] if len(pixel) == 4 else 255
    if a < ALPHA_MINIMO:
        return pixel
    limiar = (_BAYER_4x4[y % 4][x % 4] / 16.0 - 0.5) * forca
    return (
        max(0, min(255, int(r + limiar))),
        max(0, min(255, int(g + limiar))),
        max(0, min(255, int(b + limiar))),
        a,
    )


def cor_pixel(pixel):
    if len(pixel) == 4 and pixel[3] < ALPHA_MINIMO:
        return None

    r, g, b = pixel[0], pixel[1], pixel[2]
    a = pixel[3] if len(pixel) == 4 else 255
    if a < 255:
        fator = a / 255.0
        fr, fg_, fb = FUNDO_TERMINAL
        r = int(r * fator + fr * (1.0 - fator))
        g = int(g * fator + fg_ * (1.0 - fator))
        b = int(b * fator + fb * (1.0 - fator))
    return f"#{r:02x}{g:02x}{b:02x}"


def e_pixel_art(imagem, largura_alvo):
    if imagem.width < largura_alvo * 0.5:
        return True
    try:
        amostra = imagem.convert("RGB").resize(
            (64, 64), Image.Resampling.NEAREST
        )
        cores = amostra.getcolors(maxcolors=64 * 64)
        if cores and len(cores) < 32:
            return True
    except Exception:
        pass
    return False


class PortraitMixin:
    """Métodos de retrato usados por :class:`ChatUI`."""

    # ------------------------------------------------------------------
    # Caches e carregamento
    # ------------------------------------------------------------------

    def _podar_cache(self):
        if len(self._retrato_cache) > MAX_CACHE_RETRATO:
            self._retrato_cache.clear()
        if len(self._retrato_render_cache) > MAX_CACHE_RETRATO:
            self._retrato_render_cache.clear()
        if len(self._kitty_cache) > MAX_CACHE_RETRATO:
            self._kitty_cache.clear()

    def _novo_id_imagem(self):
        self._id_imagem = (self._id_imagem + 1) % 0xFFFFFF
        return max(1, self._id_imagem)

    def _carregar_original(self, expressao):
        """Imagem original em RGBA, usada pelo protocolo do Kitty."""
        if expressao in self._originais_cache:
            return self._originais_cache[expressao]

        nome_arquivo, _cor = EXPRESSOES.get(expressao, EXPRESSOES["NORMAL"])
        caminho = PASTA_EXPRESSOES / nome_arquivo
        try:
            with Image.open(caminho) as origem:
                imagem = origem.convert("RGBA")
        except Exception as erro:
            log_erro(erro)
            imagem = None

        self._originais_cache[expressao] = imagem
        return imagem

    @staticmethod
    def _dimensoes_celula(imagem, largura_max, altura_max):
        return dimensoes_celula(
            imagem,
            largura_max,
            altura_max,
            fator_supersample=FATOR_SUPERSAMPLE,
        )

    def _linhas_imagem_kitty(self, largura, altura):
        """Células com placeholders que o Kitty troca pela imagem."""
        chave = (self.expressao_atual, largura, altura)
        if chave in self._kitty_cache:
            return self._kitty_cache[chave]

        original = self._carregar_original(self.expressao_atual)
        if original is None:
            return None

        id_imagem = self._novo_id_imagem()
        escape = comandos_imagem_kitty(
            id_imagem, png_bytes(original), largura, altura
        )
        estilo = f"bg:{COR_PAINEL} fg:#{id_imagem:06x}"

        linhas = []
        for linha_cel in range(altura):
            partes = []
            if linha_cel == 0:
                # O escape é injetado antes da primeira célula, sem ocupar
                # espaço, e transmite/posiciona a imagem.
                partes.append(("[ZeroWidthEscape]", escape))
            marca = DIACRITICOS[linha_cel % len(DIACRITICOS)]
            partes.append((estilo, PLACEHOLDER_KITTY + marca))
            for _ in range(largura - 1):
                # Sem diacríticos, cada célula herda a coluna anterior.
                partes.append((estilo, PLACEHOLDER_KITTY))
            linhas.append(partes)

        self._podar_cache()
        self._kitty_cache[chave] = linhas
        return linhas

    def _enquadrar_imagem(self, brutas, img_w, frame_w):
        """Centraliza as linhas da imagem dentro da moldura lateral."""
        pad_total = max(0, frame_w - 4 - img_w)
        pad_esq = pad_total // 2
        pad_dir = pad_total - pad_esq

        linhas_img = []
        for linha in brutas:
            composta = [
                ("class:painel", " "),
                ("class:borda", "│ "),
                ("class:painel", " " * pad_esq),
            ]
            composta.extend(linha)
            composta.append(("class:painel", " " * pad_dir + " "))
            composta.append(("class:borda", "│"))
            linhas_img.append(composta)
        return linhas_img

    def _carregar_imagem(self, nome_expressao, largura_cel, altura_cel):
        """Carrega a expressão preservando a proporção dentro da caixa."""
        chave = (nome_expressao, largura_cel, altura_cel)
        if chave in self._retrato_cache:
            return self._retrato_cache[chave]

        nome_arquivo, _cor = EXPRESSOES[nome_expressao]
        caminho = PASTA_EXPRESSOES / nome_arquivo
        if not caminho.is_file():
            log_erro(FileNotFoundError(f"Expressão não encontrada: {caminho}"))
            self._retrato_cache[chave] = None
            return None

        try:
            # ``convert`` força o carregamento; fechar o arquivo evita
            # descritores abertos por tempo indefinido.
            with Image.open(caminho) as origem:
                imagem = origem.convert("RGBA")

            pixel_art = e_pixel_art(imagem, largura_cel)

            # Cada célula do terminal usa 2x4 pixels no supersample (2 na
            # horizontal e 2 blocos de meia-altura na vertical).
            max_w = max(2, largura_cel * FATOR_SUPERSAMPLE)
            max_h = max(4, altura_cel * FATOR_SUPERSAMPLE * 2)
            escala = min(max_w / imagem.width, max_h / imagem.height)

            alvo_w = max(2, int(imagem.width * escala))
            alvo_h = max(4, int(imagem.height * escala))
            alvo_w -= alvo_w % FATOR_SUPERSAMPLE
            alvo_h -= alvo_h % (FATOR_SUPERSAMPLE * 2)
            alvo_w = max(2, alvo_w)
            alvo_h = max(4, alvo_h)

            if pixel_art:
                imagem = imagem.resize(
                    (alvo_w, alvo_h), Image.Resampling.NEAREST
                )
            else:
                imagem = imagem.resize(
                    (alvo_w, alvo_h), Image.Resampling.LANCZOS
                )
                imagem = imagem.filter(
                    ImageFilter.UnsharpMask(
                        radius=1.5, percent=90, threshold=2
                    )
                )
                imagem = ImageEnhance.Brightness(imagem).enhance(1.05)

                if terminal_24bit():
                    pixels = imagem.load()
                    w, h = imagem.size
                    for yy in range(h):
                        for xx in range(w):
                            pixels[xx, yy] = aplicar_dither(
                                pixels[xx, yy], xx, yy, forca=8
                            )

            self._podar_cache()
            self._retrato_cache[chave] = imagem
            return imagem
        except Exception as erro:
            log_erro(erro)
            self._retrato_cache[chave] = None
            return None

    # ------------------------------------------------------------------
    # Rasterização
    # ------------------------------------------------------------------

    @staticmethod
    def _rasterizar_linhas(
        imagem,
        prefixo="",
        sufixo="",
        largura_borda_esq=0,
        largura_borda_dir=0,
        estilo_borda=None,
    ):
        if imagem.mode != "RGBA":
            imagem = imagem.convert("RGBA")

        colunas = imagem.width // FATOR_SUPERSAMPLE
        linhas_celulas = imagem.height // (FATOR_SUPERSAMPLE * 2)
        if colunas <= 0 or linhas_celulas <= 0:
            return []

        # BOX reduz cada bloco 2x2 supersampleado a um pixel. Isso é
        # equivalente à média manual, mas delegado ao Pillow (bem mais
        # rápido que chamar getpixel quatro vezes por célula).
        reduzida = imagem.resize(
            (colunas, linhas_celulas * 2), Image.Resampling.BOX
        )
        # ``get_flattened_data`` substitui ``getdata`` no Pillow 13+.
        obter_dados = getattr(
            reduzida, "get_flattened_data", reduzida.getdata
        )
        pixels = list(obter_dados())

        linhas = []
        for linha_cel in range(linhas_celulas):
            partes = []
            if prefixo:
                partes.append(("", prefixo))
            if largura_borda_esq and estilo_borda:
                partes.append((estilo_borda, "│ "))

            base = linha_cel * 2 * colunas
            for coluna_cel in range(colunas):
                cor_sup = pixels[base + coluna_cel]
                cor_inf = pixels[base + colunas + coluna_cel]
                fg = cor_pixel(cor_sup)
                bg = cor_pixel(cor_inf)

                if fg is None and bg is None:
                    partes.append(("", " "))
                elif fg is None:
                    partes.append((f"bg:{bg}", " "))
                elif bg is None:
                    partes.append((f"fg:{fg}", "▀"))
                else:
                    partes.append((f"fg:{fg} bg:{bg}", "▀"))

            if sufixo:
                partes.append(("", sufixo))
            if largura_borda_dir and estilo_borda:
                partes.append((estilo_borda, " │"))
            linhas.append(partes)

        return linhas

    @classmethod
    def _rasterizar(
        cls,
        imagem,
        prefixo="",
        largura_borda_esq=0,
        largura_borda_dir=0,
        estilo_borda=None,
    ):
        linhas = cls._rasterizar_linhas(
            imagem,
            prefixo=prefixo,
            largura_borda_esq=largura_borda_esq,
            largura_borda_dir=largura_borda_dir,
            estilo_borda=estilo_borda,
        )

        partes = []
        for linha in linhas:
            partes.extend(linha)
            partes.append(("", "\n"))
        return partes

    # ------------------------------------------------------------------
    # Painel
    # ------------------------------------------------------------------

    def _estilo_humor(self):
        return f"class:humor_{self.expressao_atual.lower()}"

    def _borda_superior_lateral(self, frame_w):
        prefixo = [
            ("class:borda_acento", "╭"),
            ("class:borda", "─ "),
            ("class:titulo_painel", "◆ SOLERIA"),
            ("class:borda", " "),
        ]
        sufixo = [
            ("class:borda", " "),
            (self._estilo_humor(), "●"),
            ("class:borda", " ─╮"),
        ]
        usado = 1 + 2 + 9 + 1 + 1 + 1 + 3
        dashes = frame_w - usado
        if dashes >= 1:
            return (
                prefixo
                + [("class:borda", "─" * dashes)]
                + sufixo
            )

        # Painéis muito estreitos: mantenha a moldura sem o rótulo.
        if frame_w >= 14:
            return [
                ("class:borda_acento", "╭"),
                ("class:borda", "─ "),
                ("class:titulo_painel", "◆ SOLERIA"),
                ("class:borda", " " + "─" * (frame_w - 14) + "╮"),
            ]

        return [
            ("class:borda_acento", "╭"),
            ("class:borda", "─" * max(1, frame_w - 2)),
            ("class:borda_acento", "╮"),
        ]

    def _borda_superior_topo(self, frame_w):
        humor = HUMORES.get(self.expressao_atual, "—")
        prefixo = [
            ("class:borda_acento", "╭"),
            ("class:borda", "─ "),
            ("class:titulo_painel", "◆ SOLERIA"),
            ("class:borda", " · "),
        ]
        usado = 1 + 2 + 9 + 3 + largura_texto(humor) + 2
        dashes = frame_w - usado
        if dashes < 0:
            return [
                ("class:borda_acento", "╭"),
                ("class:borda", "─" * max(1, frame_w - 2)),
                ("class:borda_acento", "╮"),
            ]
        return (
            prefixo
            + [(self._estilo_humor(), humor)]
            + [
                ("class:borda", " " + "─" * dashes),
                ("class:borda_acento", "╮"),
            ]
        )

    def _borda_inferior(self, frame_w):
        return [
            ("class:painel", " "),
            ("class:borda", "╰"),
            ("class:borda", "─" * max(1, frame_w - 2)),
            ("class:borda", "╯"),
        ]

    def _linha_vazia_painel(self, frame_w):
        return [
            ("class:painel", " "),
            ("class:borda", "│"),
            ("class:painel", " " * max(0, frame_w - 2)),
            ("class:borda", "│"),
        ]

    def _linha_humor(self, frame_w):
        humor = f"● {HUMORES.get(self.expressao_atual, '—')}"
        conteudo = max(1, frame_w - 4)
        sobra = max(0, conteudo - largura_texto(humor))
        esquerda = " " * (sobra // 2)
        direita = " " * (sobra - sobra // 2)
        return [
            ("class:painel", " "),
            ("class:borda", "│ "),
            ("class:painel", esquerda),
            (self._estilo_humor(), humor),
            ("class:painel", direita + " "),
            ("class:borda", "│"),
        ]

    def _texto_agora(self):
        with self._lock:
            historico = list(self.historico)
            transmitindo = self._indice_stream is not None

        if self._status_atual:
            return self._status_atual

        for remetente, texto in reversed(historico):
            if remetente.startswith("Soleria") and (texto or "").strip():
                resumo = " ".join(texto.split())
                if len(resumo) > 180:
                    resumo = "…" + resumo[-180:]
                return f"“{resumo}”"

        if transmitindo:
            return "pensando…"

        for remetente, texto in reversed(historico):
            if (texto or "").strip():
                resumo = " ".join(texto.split())
                if len(resumo) > 120:
                    resumo = "…" + resumo[-120:]
                return f"{remetente}: {resumo}"

        return "pronta para conversar"

    def _linhas_rodape(self, frame_w, max_linhas):
        largura = max(8, frame_w - 2)
        texto = self._texto_agora()
        quebrado = quebrar_texto(texto, largura)
        if len(quebrado) > max_linhas:
            quebrado = quebrado[:max_linhas]
            quebrado[-1] = cortar_texto(quebrado[-1] + "…", largura)

        linhas = [[("class:rotulo_painel", " agora")]]
        for linha in quebrado:
            linhas.append([("class:fala_atual", " " + linha)])
        return linhas

    def _montar_painel_lateral(self, frame_w, altura):
        chave = (self.expressao_atual, frame_w, altura)
        if chave in self._retrato_render_cache:
            return self._retrato_render_cache[chave]

        rodape_linhas = 2 if altura >= 19 else 1 if altura >= 14 else 0
        reserva = 1 + rodape_linhas if rodape_linhas else 0
        img_h_max = max(2, altura - 5 - reserva)
        img_w_max = max(6, frame_w - 6)

        brutas = None
        img_w = 0
        if self._kitty:
            original = self._carregar_original(self.expressao_atual)
            if original is not None:
                img_w, img_h = self._dimensoes_celula(
                    original, img_w_max, img_h_max
                )
                brutas = self._linhas_imagem_kitty(img_w, img_h)

        if brutas is not None:
            linhas_img = self._enquadrar_imagem(brutas, img_w, frame_w)
        else:
            imagem = self._carregar_imagem(
                self.expressao_atual, img_w_max, img_h_max
            )

            if imagem is None:
                largura = max(4, frame_w - 4)
                texto = centralizar(
                    f"[ {self.expressao_atual} ]", largura
                )[0]
                linhas_img = [
                    [
                        ("class:painel", " "),
                        ("class:borda", "│ "),
                        ("class:msg_sistema", texto),
                        ("class:borda", " │"),
                    ]
                ]
            else:
                img_w = imagem.width // FATOR_SUPERSAMPLE
                brutas = self._rasterizar_linhas(imagem)
                linhas_img = self._enquadrar_imagem(
                    brutas, img_w, frame_w
                )

        linhas = [
            [("class:painel", " ")] + self._borda_superior_lateral(frame_w),
            self._linha_vazia_painel(frame_w),
        ]
        linhas.extend(linhas_img)
        linhas.append(self._linha_vazia_painel(frame_w))
        linhas.append(self._linha_humor(frame_w))
        linhas.append(self._borda_inferior(frame_w))

        self._podar_cache()
        self._retrato_render_cache[chave] = (linhas, rodape_linhas)
        return self._retrato_render_cache[chave]

    def _renderizar_retrato_lateral(self, dimensoes):
        largura = max(12, dimensoes["largura_painel"])
        altura = max(6, dimensoes["altura_painel"])
        frame_w = max(12, largura - 2)

        base, rodape_linhas = self._montar_painel_lateral(frame_w, altura)
        total = len(base) + (1 + rodape_linhas if rodape_linhas else 0)
        pad_topo = max(0, (altura - total) // 2)

        linhas = [[] for _ in range(pad_topo)]
        linhas.extend(base)
        if rodape_linhas:
            linhas.append([])
            linhas.extend(self._linhas_rodape(frame_w, rodape_linhas))
        return achatar(linhas)

    def _tarja_retrato(self, largura):
        """Versão de uma linha do painel, para terminais muito baixos."""
        humor = HUMORES.get(self.expressao_atual, "—")
        partes = [
            ("class:painel", " "),
            ("class:titulo_painel", "◆ SOLERIA"),
            ("class:borda", " · "),
            (self._estilo_humor(), f"● {humor}"),
            ("class:painel", " "),
        ]
        usado = sum(largura_texto(t) for _s, t in partes)
        if usado < largura:
            partes.append(("class:painel", " " * (largura - usado)))
        return partes

    def _renderizar_retrato_topo(self, dimensoes):
        largura = max(20, dimensoes["largura_painel"])
        altura = max(1, dimensoes["altura_painel"])
        if altura < 4:
            return self._tarja_retrato(largura)

        frame_w = max(16, largura - 2)
        inner_h = max(1, altura - 2)

        img_h_max = max(1, inner_h)
        img_w_max = max(4, min(inner_h * 2, frame_w - 18))

        img_linhas = None
        img_w = 0
        if self._kitty:
            original = self._carregar_original(self.expressao_atual)
            if original is not None:
                img_w, img_h = self._dimensoes_celula(
                    original, img_w_max, img_h_max
                )
                img_linhas = self._linhas_imagem_kitty(img_w, img_h)

        if img_linhas is None:
            imagem = self._carregar_imagem(
                self.expressao_atual, img_w_max, img_h_max
            )

            if imagem is None:
                img_linhas = [
                    [
                        (
                            "class:msg_sistema",
                            centralizar(
                                f"[ {self.expressao_atual} ]", img_w_max
                            )[0],
                        )
                    ]
                ]
                img_w = min(img_w_max, 18)
            else:
                img_linhas = self._rasterizar_linhas(imagem)
                img_w = imagem.width // FATOR_SUPERSAMPLE

        right_w = max(6, frame_w - img_w - 6)
        texto_agora = self._texto_agora()
        texto_linhas = []
        if inner_h >= 2:
            texto_linhas.append([("class:rotulo_painel", "agora")])
        restante = max(1, inner_h - len(texto_linhas))
        quebrado = quebrar_texto(texto_agora, max(6, right_w))
        if len(quebrado) > restante:
            quebrado = quebrado[:restante]
            quebrado[-1] = cortar_texto(
                quebrado[-1] + "…", max(6, right_w)
            )
        for linha in quebrado:
            texto_linhas.append([("class:fala_atual", linha)])

        pad_img = max(0, (inner_h - len(img_linhas)) // 2)
        pad_txt = max(0, (inner_h - len(texto_linhas)) // 2)

        linhas = [
            [("class:painel", " ")] + self._borda_superior_topo(frame_w)
        ]
        for indice in range(inner_h):
            pos_img = indice - pad_img
            pos_txt = indice - pad_txt
            frag_img = (
                img_linhas[pos_img]
                if 0 <= pos_img < len(img_linhas)
                else [("class:painel", " " * img_w)]
            )
            frag_txt = (
                texto_linhas[pos_txt]
                if 0 <= pos_txt < len(texto_linhas)
                else [("class:painel", " " * right_w)]
            )

            linha = [
                ("class:painel", " "),
                ("class:borda", "│ "),
            ]
            linha.extend(frag_img)
            usado_img = sum(largura_texto(t) for _s, t in frag_img)
            if usado_img < img_w:
                linha.append(("class:painel", " " * (img_w - usado_img)))
            linha.append(("class:painel", "  "))
            linha.extend(frag_txt)
            usado_txt = sum(largura_texto(t) for _s, t in frag_txt)
            if usado_txt < right_w:
                linha.append(
                    ("class:painel", " " * (right_w - usado_txt))
                )
            linha.append(("class:painel", " "))
            linha.append(("class:borda", "│"))
            linhas.append(linha)

        linhas.append(self._borda_inferior(frame_w))
        return achatar(linhas)

    def _renderizar_retrato(self):
        try:
            dimensoes = self._dimensoes_layout()
            if dimensoes["modo"] == "lateral":
                return self._renderizar_retrato_lateral(dimensoes)
            return self._renderizar_retrato_topo(dimensoes)
        except Exception as erro:
            log_erro(erro)
            return [("class:msg_sistema", " retrato indisponível ")]


# Aliases privados mantidos para compatibilidade.
_aplicar_dither = aplicar_dither
_cor_pixel = cor_pixel
_e_pixel_art = e_pixel_art
