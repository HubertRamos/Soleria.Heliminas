"""Paleta de comandos e menu de configurações da TUI.

A paleta imita o seletor de comandos do VS Code: um painel flutuante no
centro da tela, com busca, navegação por setas e Enter para executar. O
mesmo painel, em outro modo, mostra as preferências que podem ser
alternadas sem reiniciar a Soleria.

A :class:`~soleria.ui.chat.ChatUI` herda este mixin e fornece as ações,
o estado da conversa e a aplicação do prompt_toolkit.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import Condition
from prompt_toolkit.layout import (
    ConditionalContainer,
    Dimension,
    Float,
    HSplit,
    Window,
)
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.widgets import Frame

from soleria.settings import DEFINICOES, rotulo_valor
from soleria.ui.text import cortar_texto, largura_texto

LARGURA_MENU_MAX = 82
LARGURA_MENU_MIN = 42


@dataclass(frozen=True)
class Comando:
    id: str
    titulo: str
    descricao: str = ""
    atalho: str = ""
    grupo: str = ""
    acao: object = None


def _sem_acento(texto):
    decomposto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()


def filtrar_comandos(comandos, consulta):
    """Filtra por palavras da busca, ignorando acentos e maiúsculas."""
    termos = _sem_acento(consulta).split()
    if not termos:
        return list(comandos)

    resultado = []
    for comando in comandos:
        alvo = _sem_acento(
            f"{comando.titulo} {comando.descricao} {comando.grupo}"
        )
        if all(termo in alvo for termo in termos):
            resultado.append(comando)
    return resultado


class MenuMixin:
    """Estado, desenho e atalhos dos painéis flutuantes."""

    # ------------------------------------------------------------------
    # Construção (chamada pelo __init__ da ChatUI)
    # ------------------------------------------------------------------

    def preparar_menu(self):
        self._menu = None
        self._menu_indice = 0
        self._menu_rolagem = 0
        self._menu_aviso = None

        self._menu_filtro = Buffer(
            name="menu-filtro",
            multiline=False,
            on_text_changed=self._ao_filtrar_menu,
        )
        self._menu_filtro_window = Window(
            BufferControl(buffer=self._menu_filtro),
            height=1,
            style="class:menu_filtro",
        )

        self._menu_lista_control = FormattedTextControl(
            text=self._renderizar_lista_menu
        )
        self._menu_lista_window = Window(
            self._menu_lista_control,
            height=Dimension(weight=1),
            style="class:menu_lista",
            wrap_lines=False,
        )

        self._menu_config_control = FormattedTextControl(
            text=self._renderizar_lista_config,
            focusable=True,
            show_cursor=False,
        )
        self._menu_config_window = Window(
            self._menu_config_control,
            height=Dimension(weight=1),
            style="class:menu_lista",
            wrap_lines=False,
        )

        self._menu_dica_window = Window(
            FormattedTextControl(self._renderizar_dica_config),
            height=1,
            style="class:menu_dica",
            wrap_lines=False,
        )

        corpo = HSplit(
            [
                ConditionalContainer(
                    self._menu_filtro_window,
                    filter=Condition(lambda: self._menu == "comandos"),
                ),
                ConditionalContainer(
                    Window(height=1, char="─", style="class:menu_regua"),
                    filter=Condition(lambda: self._menu == "comandos"),
                ),
                ConditionalContainer(
                    self._menu_lista_window,
                    filter=Condition(lambda: self._menu == "comandos"),
                ),
                ConditionalContainer(
                    self._menu_config_window,
                    filter=Condition(lambda: self._menu == "config"),
                ),
                ConditionalContainer(
                    self._menu_dica_window,
                    filter=Condition(lambda: self._menu == "config"),
                ),
                Window(
                    FormattedTextControl(self._renderizar_ajuda_menu),
                    height=1,
                    style="class:menu_ajuda",
                    wrap_lines=False,
                ),
            ],
            style="class:menu_corpo",
        )

        self._menu_frame = Frame(
            corpo,
            title=lambda: self._titulo_menu(),
            style="class:menu",
        )
        self._menu_float = Float(
            self._menu_frame,
            width=lambda: self._largura_menu(),
            height=lambda: self._altura_menu(),
        )
        self._menu_float_ativo = False

    def atalhos_menu(self, kb):
        """Registra os atalhos globais do menu na KeyBindings da aplicação."""
        menu_aberto = Condition(lambda: self._menu is not None)
        no_menu = ~menu_aberto

        @kb.add("c-p")
        def _abrir_paleta(event):
            if self._menu == "comandos":
                self.fechar_menu()
            else:
                self.abrir_paleta()

        @kb.add("f2")
        def _abrir_config(event):
            if self._menu == "config":
                self.fechar_menu()
            else:
                self.abrir_config()

        @kb.add("escape", filter=menu_aberto)
        def _fechar(event):
            self.fechar_menu()

        @kb.add("up", filter=menu_aberto)
        def _subir(event):
            self._mover_menu(-1)

        @kb.add("down", filter=menu_aberto)
        def _descer(event):
            self._mover_menu(1)

        @kb.add("pageup", filter=menu_aberto)
        def _subir_pagina(event):
            self._mover_menu(-5)

        @kb.add("pagedown", filter=menu_aberto)
        def _descer_pagina(event):
            self._mover_menu(5)

        @kb.add("enter", filter=menu_aberto)
        def _confirmar(event):
            self._confirmar_menu()

        @kb.add(" ", filter=Condition(lambda: self._menu == "config"))
        def _alternar(event):
            self._confirmar_menu()

        @kb.add("left", filter=Condition(lambda: self._menu == "config"))
        def _escolha_anterior(event):
            self._ciclar_config(-1)

        @kb.add("right", filter=Condition(lambda: self._menu == "config"))
        def _proxima_escolha(event):
            self._ciclar_config(1)

        @kb.add("c-c", filter=menu_aberto)
        def _cancelar_menu(event):
            self.fechar_menu()

        return no_menu

    # ------------------------------------------------------------------
    # Abrir / fechar / navegar
    # ------------------------------------------------------------------

    @property
    def menu_aberto(self):
        return self._menu is not None

    def abrir_paleta(self):
        self._menu = "comandos"
        self._menu_indice = 0
        self._menu_rolagem = 0
        self._menu_aviso = None
        try:
            self._menu_filtro.reset()
        except Exception:
            pass
        self._exibir_menu(True)
        self._focar_menu()
        self._invalidate_throttled(forcar=True)

    def abrir_config(self):
        self._menu = "config"
        self._menu_indice = 0
        self._menu_rolagem = 0
        self._menu_aviso = None
        self._exibir_menu(True)
        self._focar_menu()
        self._invalidate_throttled(forcar=True)

    def fechar_menu(self):
        if self._menu is None:
            return
        self._menu = None
        self._exibir_menu(False)
        try:
            self.app.layout.focus(self.entrada_window)
        except Exception:
            pass
        self._invalidate_throttled(forcar=True)

    def _exibir_menu(self, mostrar):
        try:
            floats = self.float_container.floats
        except AttributeError:
            return
        if mostrar and not self._menu_float_ativo:
            floats.append(self._menu_float)
            self._menu_float_ativo = True
        elif not mostrar and self._menu_float_ativo:
            try:
                floats.remove(self._menu_float)
            except ValueError:
                pass
            self._menu_float_ativo = False
        try:
            self.float_container.modal = bool(mostrar)
        except AttributeError:
            pass

    def _focar_menu(self):
        alvo = (
            self._menu_config_window
            if self._menu == "config"
            else self._menu_filtro_window
        )
        try:
            self.app.layout.focus(alvo)
        except Exception:
            # A Application pode ainda não existir em testes de layout.
            pass

    def _mover_menu(self, delta):
        total = len(self._itens_menu())
        if total == 0:
            return
        self._menu_aviso = None
        self._menu_indice = max(0, min(total - 1, self._menu_indice + delta))
        self._invalidate_throttled(forcar=True)

    def _confirmar_menu(self):
        if self._menu == "config":
            self._alternar_config()
            return

        comando = self._comando_atual()
        if comando is None:
            return
        if comando.id != "config":
            self.fechar_menu()
        if callable(comando.acao):
            try:
                comando.acao()
            except Exception as erro:
                from soleria.logging_utils import log_erro

                log_erro(erro)
                if self.menu_aberto:
                    self._avisar_menu("Não consegui executar esse comando.")
                else:
                    self.adicionar_externo(
                        "Sistema", "Não consegui executar esse comando."
                    )

    def _alternar_config(self):
        definicao = self._definicao_atual()
        if definicao is None:
            return
        if definicao.tipo == "bool":
            valor = self.preferencias.alternar(definicao.chave)
        else:
            valor = self.preferencias.ciclar(definicao.chave, 1)
        self._aplicar_config(definicao.chave, valor)

    def _ciclar_config(self, direcao):
        definicao = self._definicao_atual()
        if definicao is None or definicao.tipo != "escolha":
            return
        valor = self.preferencias.ciclar(definicao.chave, direcao)
        self._aplicar_config(definicao.chave, valor)

    def _aplicar_config(self, chave, valor):
        if self.ao_mudar_config:
            try:
                resposta = self.ao_mudar_config(chave, valor)
            except Exception as erro:
                from soleria.logging_utils import log_erro

                log_erro(erro)
                resposta = "Não consegui aplicar essa configuração."
            if resposta:
                self._avisar_menu(resposta)
        self._invalidate_throttled(forcar=True)

    def _avisar_menu(self, texto):
        self._menu_aviso = texto
        self._invalidate_throttled(forcar=True)

    def _ao_filtrar_menu(self, _buffer):
        self._menu_indice = 0
        self._menu_rolagem = 0
        self._invalidate_throttled(forcar=True)

    # ------------------------------------------------------------------
    # Itens
    # ------------------------------------------------------------------

    def _itens_menu(self):
        if self._menu == "config":
            return list(DEFINICOES)
        return filtrar_comandos(
            self._comandos_menu(), self._menu_filtro.text
        )

    def _comando_atual(self):
        itens = self._itens_menu()
        if not itens:
            return None
        indice = max(0, min(len(itens) - 1, self._menu_indice))
        return itens[indice]

    def _definicao_atual(self):
        itens = self._itens_menu()
        if not itens:
            return None
        indice = max(0, min(len(itens) - 1, self._menu_indice))
        return itens[indice]

    def _comandos_menu(self):
        """Sobrescrito pela ChatUI com as ações concretas."""
        return []

    # ------------------------------------------------------------------
    # Dimensões
    # ------------------------------------------------------------------

    def _largura_menu(self):
        colunas = self._dimensoes_layout()["colunas"]
        largura = min(
            LARGURA_MENU_MAX, max(LARGURA_MENU_MIN, colunas - 4)
        )
        # Em terminais estreitos o painel precisa caber com uma margem.
        return max(20, min(largura, colunas - 2))

    def _altura_menu(self):
        linhas = self._dimensoes_layout()["linhas"]
        if self._menu == "config":
            desejada = len(DEFINICOES) + 6
        else:
            desejada = len(self._itens_menu()) + 7
        return max(5, min(linhas - 2, desejada))

    def _visiveis_lista(self):
        altura = self._altura_menu()
        if self._menu == "config":
            return max(1, altura - 4)
        return max(1, altura - 5)

    def _ajustar_rolagem(self, total, visiveis):
        if total <= visiveis:
            self._menu_rolagem = 0
            return 0
        if self._menu_indice < self._menu_rolagem:
            self._menu_rolagem = self._menu_indice
        elif self._menu_indice >= self._menu_rolagem + visiveis:
            self._menu_rolagem = self._menu_indice - visiveis + 1
        self._menu_rolagem = max(0, min(self._menu_rolagem, total - visiveis))
        return self._menu_rolagem

    def _largura_linha_menu(self):
        # O Frame desenha uma borda de cada lado.
        return max(20, self._largura_menu() - 4)

    # ------------------------------------------------------------------
    # Desenho
    # ------------------------------------------------------------------

    def _titulo_menu(self):
        if self._menu == "config":
            texto = " CONFIGURAÇÕES "
        else:
            texto = " COMANDOS "
        return [("class:menu_titulo", "◆ SOLERIA ·" + texto)]

    def _renderizar_lista_menu(self):
        itens = self._itens_menu()
        largura = self._largura_linha_menu()

        if not itens:
            return [("class:menu_vazio", "  nenhum comando encontrado")]

        visiveis = self._visiveis_lista()
        inicio = self._ajustar_rolagem(len(itens), visiveis)
        fragmentos = []
        for posicao in range(inicio, min(len(itens), inicio + visiveis)):
            comando = itens[posicao]
            selecionado = posicao == self._menu_indice
            marcador = "▸ " if selecionado else "  "
            atalho = comando.atalho or ""
            espaco = max(
                1,
                largura
                - largura_texto(marcador)
                - largura_texto(atalho)
                - 1,
            )
            titulo = cortar_texto(
                comando.titulo,
                max(8, espaco - 2),
            )
            preenchimento = " " * max(
                1,
                espaco - largura_texto(titulo),
            )
            linha = f"{marcador}{titulo}{preenchimento}{atalho}"
            estilo = (
                "class:menu_item_ativo"
                if selecionado
                else "class:menu_item"
            )
            if fragmentos:
                fragmentos.append(("", "\n"))
            fragmentos.append((estilo, linha[:largura]))
        return fragmentos

    def _renderizar_lista_config(self):
        largura = self._largura_linha_menu()
        visiveis = self._visiveis_lista()
        inicio = self._ajustar_rolagem(len(DEFINICOES), visiveis)
        fragmentos = []

        for posicao in range(inicio, min(len(DEFINICOES), inicio + visiveis)):
            definicao = DEFINICOES[posicao]
            selecionado = posicao == self._menu_indice
            marcador = "▸ " if selecionado else "  "
            if definicao.tipo == "bool":
                ligado = bool(self.preferencias.obter(definicao.chave))
                caixa = "[x]" if ligado else "[ ]"
                valor = "ligado" if ligado else "desligado"
            else:
                caixa = "‹ ›"
                valor = rotulo_valor(
                    definicao.chave,
                    self.preferencias.obter(definicao.chave),
                )
            prefixo = f"{marcador}{caixa} "
            espaco = max(
                1,
                largura
                - largura_texto(prefixo)
                - largura_texto(valor)
                - 1,
            )
            rotulo = cortar_texto(
                definicao.rotulo,
                max(8, espaco - 2),
            )
            preenchimento = " " * max(
                1, espaco - largura_texto(rotulo)
            )
            linha = f"{prefixo}{rotulo}{preenchimento}{valor}"
            estilo = (
                "class:menu_item_ativo"
                if selecionado
                else "class:menu_item"
            )
            if fragmentos:
                fragmentos.append(("", "\n"))
            fragmentos.append((estilo, linha[:largura]))

        return fragmentos

    def _renderizar_dica_config(self):
        definicao = self._definicao_atual()
        if definicao is None:
            return []
        texto = definicao.descricao
        if definicao.reinicia:
            texto += "  ·  aplica no próximo início"
        return [
            (
                "class:menu_dica",
                cortar_texto("  " + texto, self._largura_linha_menu()),
            )
        ]

    def _renderizar_ajuda_menu(self):
        largura = self._largura_linha_menu()
        if self._menu == "config":
            texto = (
                "  ↑↓ navegar   ·   Enter/Espaço alternar   ·   "
                "←→ escolher   ·   Esc fechar"
            )
        else:
            texto = (
                "  digite para filtrar   ·   ↑↓ escolher   ·   "
                "Enter executar   ·   Esc fechar"
            )
        if getattr(self, "_menu_aviso", None):
            return [
                (
                    "class:menu_aviso",
                    cortar_texto("  " + self._menu_aviso, largura),
                )
            ]
        return [("class:menu_ajuda", cortar_texto(texto, largura))]


__all__ = ["Comando", "MenuMixin", "filtrar_comandos"]
