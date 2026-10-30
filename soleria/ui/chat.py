"""Interface TUI com prompt_toolkit.

O desenho do retrato vive em :mod:`soleria.ui.portrait`, as utilidades de
texto em :mod:`soleria.ui.text`, o tema em :mod:`soleria.ui.theme` e o
motor emocional em :mod:`soleria.persona.emotions` (com o adaptador
:mod:`soleria.ui.expressions`). Este módulo cuida do layout, do histórico,
do status e da entrada do usuário.
"""

import random
import shutil
import threading
import time

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    Dimension,
    DynamicContainer,
    FloatContainer,
    HSplit,
    Layout,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.output import ColorDepth
from prompt_toolkit.styles import Style

from config import IMAGEM_RETRATO, INTERVALO_INVALIDATE
from soleria.logging_utils import log_erro
from soleria.settings import Preferencias
from soleria.ui.expressions import classificar_expressao
from soleria.ui.menu import Comando, MenuMixin
from soleria.ui.kitty import (
    DIACRITICOS as _DIACRITICOS,
    PLACEHOLDER_KITTY as _PLACEHOLDER_KITTY,
    comandos_imagem_kitty as _comandos_imagem_kitty,
    escape_kitty as _escape_kitty,
    usar_imagem_kitty,
)
from soleria.ui.portrait import (
    FATOR_SUPERSAMPLE,
    PortraitMixin,
    aplicar_dither as _aplicar_dither,
    cor_pixel as _cor_pixel,
    e_pixel_art as _e_pixel_art,
)
from soleria.ui.text import (
    achatar as _achatar,
    contem as _contem,
    cortar_texto as _cortar_texto,
    largura_texto as _largura_texto,
    quebrar_texto as _quebrar_texto,
)
from soleria.ui.theme import (
    EXPRESSOES,
    FRAMES_STATUS as _FRAMES_STATUS,
    HUMORES,
    PASTA_EXPRESSOES,
    construir_estilos,
)

LARGURA_MIN_CHAT = 38
LARGURA_MIN_PAINEL = 18
LARGURA_MAX_PAINEL = 48

INTERVALO_RECLASSIFICAR = 40

_COMANDOS_SAIR = {"/sair", "/exit", "/quit"}


def _usar_imagem_kitty():
    """Decide se o retrato usa o protocolo gráfico do Kitty."""
    return usar_imagem_kitty(IMAGEM_RETRATO)


class ChatUI(PortraitMixin, MenuMixin):
    def __init__(
        self,
        ao_enviar,
        ao_limpar=None,
        ao_digitar=None,
        ao_alternar_voz=None,
        ao_abrir_relatorios=None,
        ao_olhar_tela=None,
        ao_gravar_voz=None,
        ao_cancelar_gravacao=None,
        ao_parar_gravacao=None,
        ao_manter_gravacao=None,
        ao_mudar_config=None,
        preferencias=None,
        retrato=None,
        emocoes=None,
    ):
        self.ao_enviar = ao_enviar
        self.ao_limpar = ao_limpar
        self.ao_digitar = ao_digitar
        self.ao_alternar_voz = ao_alternar_voz
        self.ao_abrir_relatorios = ao_abrir_relatorios
        self.ao_olhar_tela = ao_olhar_tela
        self.ao_gravar_voz = ao_gravar_voz
        self.ao_cancelar_gravacao = ao_cancelar_gravacao
        self.ao_parar_gravacao = ao_parar_gravacao
        self.ao_manter_gravacao = ao_manter_gravacao
        self.ao_mudar_config = ao_mudar_config
        self.preferencias = preferencias or Preferencias()
        self.emocoes = emocoes
        self._voz_ativa = False
        self._voz_status = None
        self._observando = False
        self._observando_status = None
        self._gravando = False
        self._gravacao_status = None
        self._tab_modo = None
        self._tab_ultimo = 0.0
        self._tab_geracao = 0

        self.historico = []
        self._lock = threading.RLock()
        self._indice_stream = None
        self._pedido_atual = 0
        self._cancelado = threading.Event()
        self._status_atual = None
        self._ultimo_invalidate = 0.0
        self._invalidate_lock = threading.Lock()

        self.expressao_atual = "NORMAL"
        self._retrato_cache = {}
        self._retrato_render_cache = {}
        self._chars_desde_classificacao = 0
        self._retrato_ampliado = False
        self._pensamento_ocioso = None

        # Imagem em resolução nativa no Kitty (com fallback para blocos).
        self._kitty = usar_imagem_kitty(retrato or IMAGEM_RETRATO)
        self._kitty_cache = {}
        self._originais_cache = {}
        self._id_imagem = random.randrange(0x10000, 0xFF0000)

        # Rolagem do histórico (linhas acima do fim) e cache do texto já
        # quebrado na largura atual.
        self._scroll_historico = 0
        self._versao_historico = 0
        self._cache_hist = (None, [])

        self.buffer_entrada = Buffer(
            name="entrada",
            multiline=False,
            accept_handler=self._ao_aceitar,
            on_text_changed=self._ao_mudar_texto,
        )

        # Paleta de comandos e menu de configurações (flutuantes no centro).
        self.preparar_menu()

        self.historico_control = FormattedTextControl(
            text=self._renderizar_historico
        )
        self.historico_window = Window(
            self.historico_control,
            height=Dimension(weight=1),
            style="class:historico",
        )

        self.status_control = FormattedTextControl(
            text=self._renderizar_status
        )
        self.status_window = Window(
            self.status_control, height=1, style="class:status"
        )

        self.entrada_window = Window(
            BufferControl(buffer=self.buffer_entrada),
            height=1,
            style="class:entrada",
        )
        self.prompt_entrada = Window(
            FormattedTextControl([("class:prompt_entrada", " › ")]),
            width=3,
            height=1,
        )
        self.entrada_linha = VSplit(
            [self.prompt_entrada, self.entrada_window],
            height=1,
            style="class:entrada",
        )

        self.area_chat = HSplit(
            [
                self.historico_window,
                self.status_window,
                Window(height=1, char="─", style="class:regua"),
                self.entrada_linha,
            ],
            style="class:area_chat",
        )

        self.retrato_control = FormattedTextControl(
            text=self._renderizar_retrato
        )
        self.painel_window = Window(
            self.retrato_control,
            width=lambda: self._dimensoes_layout()["largura_painel"],
            height=lambda: self._dimensoes_layout()["altura_painel"],
            style="class:painel",
        )
        self.divisor_vertical = Window(
            width=1, char="│", style="class:divisor"
        )
        self.divisor_horizontal = Window(
            height=1, char="─", style="class:divisor"
        )

        self._layout_lateral = VSplit(
            [self.painel_window, self.divisor_vertical, self.area_chat],
            style="class:raiz",
        )
        self._layout_topo = HSplit(
            [self.painel_window, self.divisor_horizontal, self.area_chat],
            style="class:raiz",
        )
        self.conteudo = DynamicContainer(self._montar_corpo)

        corpo = HSplit(
            [
                Window(
                    FormattedTextControl(self._renderizar_barra_titulo),
                    height=1,
                    style="class:barra_titulo",
                ),
                self.conteudo,
            ],
            style="class:raiz",
        )

        kb = KeyBindings()

        # A paleta e a configuração registram seus atalhos aqui. O filtro
        # devolvido desliga os atalhos normais enquanto o menu está aberto.
        sem_menu = self.atalhos_menu(kb)

        @kb.add("c-c", filter=sem_menu)
        def _cancelar(event):
            if not self._cancelar_pedido():
                event.app.current_buffer.reset()

        @kb.add("c-d")
        def _sair(event):
            event.app.exit()

        @kb.add("c-l", filter=sem_menu)
        def _limpar(event):
            self._limpar_tudo()

        @kb.add("tab", filter=sem_menu)
        def _gravar_voz(event):
            self._ao_tab()

        @kb.add("f3", filter=sem_menu)
        def _alternar(event):
            self._alternar_painel()

        @kb.add(
            "escape",
            filter=Condition(
                lambda: self._gravando and not self.menu_aberto
            ),
        )
        def _cancelar_gravacao(event):
            self._cancelar_gravacao_atual()

        @kb.add("pageup", filter=sem_menu)
        def _subir(event):
            self._rolar_historico(1)

        @kb.add("pagedown", filter=sem_menu)
        def _descer(event):
            self._rolar_historico(-1)

        self.float_container = FloatContainer(content=corpo, floats=[])

        self.app = Application(
            layout=Layout(
                self.float_container, focused_element=self.entrada_window
            ),
            key_bindings=kb,
            full_screen=True,
            style=Style.from_dict(construir_estilos()),
            mouse_support=False,
            refresh_interval=0.25,
            # O id da imagem viaja na cor de primeiro plano; truecolor
            # garante que o Kitty receba o valor exato.
            color_depth=ColorDepth.TRUE_COLOR if self._kitty else None,
        )

    # ------------------------------------------------------------------
    # API pública para o modo voz / encerramento
    # ------------------------------------------------------------------

    def adicionar_externo(self, remetente, texto):
        self._adicionar(remetente, texto)
        if remetente.startswith("Soleria"):
            self._pensamento_ocioso = None
            if self.emocoes is not None:
                self.sincronizar_emocao()
            else:
                self._definir_expressao(
                    self._classificar_expressao(texto, "Soleria")
                )

    def definir_indicador_voz(self, ativo, status=None):
        self._voz_ativa = ativo
        self._voz_status = status
        self._invalidate_throttled(forcar=True)

    def definir_observando(self, ativo, status=None):
        """Mostra/limpa o indicador de olhada na tela."""
        self._observando = bool(ativo)
        self._observando_status = status if ativo else None
        self._invalidate_throttled(forcar=True)

    def definir_gravacao(self, ativo, status=None):
        """Mostra/limpa o indicador de gravação do push-to-talk."""
        self._gravando = bool(ativo)
        self._gravacao_status = status if ativo else None
        if not self._gravando:
            self._tab_geracao += 1
            self._tab_modo = None
            self._manter_gravacao(False)
        self._invalidate_throttled(forcar=True)

    def definir_texto_entrada(self, texto, enviar=False):
        """Coloca o texto transcrito na linha de entrada.

        Quando ``enviar`` é verdadeiro, a mensagem é aceita como se o
        usuário tivesse apertado Enter. O texto é anexado ao que já estava
        digitado, para não apagar uma pergunta em andamento.
        """
        def aplicar():
            atual = self.buffer_entrada.text
            texto_limpo = (texto or "").strip()
            if not texto_limpo:
                return
            if atual.strip():
                novo = f"{atual.rstrip()} {texto_limpo}"
            else:
                novo = texto_limpo
            self.buffer_entrada.text = novo
            self.buffer_entrada.cursor_position = len(novo)
            if enviar:
                self.buffer_entrada.validate_and_handle()

        self._executar_na_ui(aplicar)

    def atualizar_preferencias(self):
        """Reaplica preferências que mudam o que já está na tela."""
        if not self.preferencias.obter("expressoes"):
            self._definir_expressao("NORMAL")
        elif self.emocoes is not None:
            self.sincronizar_emocao()
        self._invalidate_throttled(forcar=True)

    def sincronizar_emocao(self):
        """Puxa do motor a expressão atual, sem recriar o estado."""
        if self.emocoes is None:
            return self.expressao_atual
        try:
            expressao = self.emocoes.expressao
        except Exception as erro:
            log_erro(erro)
            return self.expressao_atual
        self._definir_expressao(expressao)
        return self.expressao_atual

    def atualizar_ocio(self):
        """Avança o tempo do motor e atualiza retrato e pensamento ocioso."""
        if self.emocoes is None:
            return
        try:
            self.emocoes.tick()
            pensamento = self.emocoes.pensamento_ocioso()
        except Exception as erro:
            log_erro(erro)
            return
        self.sincronizar_emocao()
        if pensamento != self._pensamento_ocioso:
            self._pensamento_ocioso = pensamento
            self._invalidate_throttled(forcar=True)

    def pode_receber_proativa(self):
        """True quando a tela está num ponto seguro para uma iniciativa.

        Evita interromper digitação, gravação, voz, menu, streaming ou uma
        pergunta da própria Soleria que ainda está sem resposta.
        """
        lock = getattr(self, "_lock", None)
        if lock is None:
            return self._pode_receber_proativa_sem_lock()
        with lock:
            return self._pode_receber_proativa_sem_lock()

    def _pode_receber_proativa_sem_lock(self):
        if getattr(self, "_menu", None) is not None:
            return False
        if getattr(self, "_gravando", False):
            return False
        if getattr(self, "_voz_ativa", False):
            return False
        if getattr(self, "_indice_stream", None) is not None:
            return False

        buffer = getattr(self, "buffer_entrada", None)
        if buffer is not None and buffer.text.strip():
            return False

        historico = getattr(self, "historico", None) or []
        if not historico:
            return False
        remetente, texto = historico[-1]
        if not str(remetente).startswith("Soleria"):
            return False
        texto = str(texto or "").strip()
        if not texto or "[cancelado]" in texto.casefold():
            return False
        if texto.endswith("?"):
            return False
        return True

    def pode_comentar_tela(self, manual=False):
        """True quando a tela está livre para uma observação espontânea.

        Diferente da iniciativa, pode acontecer antes de qualquer conversa.
        Nunca interrompe digitação, menu, voz, gravação ou uma resposta.
        ``manual`` libera o caso em que a última mensagem é do usuário,
        porque aí o pedido partiu dele.
        """
        lock = getattr(self, "_lock", None)
        if lock is None:
            return self._pode_comentar_tela_sem_lock(manual)
        with lock:
            return self._pode_comentar_tela_sem_lock(manual)

    def _pode_comentar_tela_sem_lock(self, manual=False):
        if getattr(self, "_menu", None) is not None:
            return False
        if getattr(self, "_gravando", False):
            return False
        if getattr(self, "_voz_ativa", False):
            return False
        if getattr(self, "_indice_stream", None) is not None:
            return False

        buffer = getattr(self, "buffer_entrada", None)
        if buffer is not None and buffer.text.strip():
            return False

        historico = getattr(self, "historico", None) or []
        if not historico:
            return True
        remetente, _ = historico[-1]
        if str(remetente).startswith("Soleria"):
            return True
        return bool(manual)

    # Janelas do push-to-talk. O terminal não informa quando a tecla é
    # solta; a repetição automática de Tab é usada como sinal de que ela
    # continua pressionada. Sem repetição, o silêncio (ou outro Tab)
    # encerra a gravação.
    ESPERA_REPETICAO_TAB = 1.0
    ESPERA_SOLTAR_TAB = 0.35

    def _ao_tab(self):
        if not self.ao_gravar_voz:
            self.adicionar_externo(
                "Sistema", "A gravação por voz não está disponível."
            )
            return

        if not self._gravando:
            self._tab_modo = "aguardando"
            self._tab_ultimo = time.monotonic()
            self._alternar_gravacao()
            if not self._gravando:
                self._tab_modo = None
                return
            self._manter_gravacao(True)
            self._iniciar_monitor_tab()
            return

        if self._tab_modo in {"aguardando", "segurando"}:
            # A repetição automática da tecla chegou: o usuário está
            # segurando Tab. Cada repetição adia o fim da gravação.
            self._tab_modo = "segurando"
            self._tab_ultimo = time.monotonic()
            return

        # Toque simples já resolvido (ou gravação iniciada por outro
        # caminho): o Tab seguinte encerra imediatamente.
        self._alternar_gravacao()

    def _iniciar_monitor_tab(self):
        self._tab_geracao += 1
        threading.Thread(
            target=self._monitorar_tab,
            args=(self._tab_geracao,),
            name="soleria-tab",
            daemon=True,
        ).start()

    def _monitorar_tab(self, geracao):
        while self._tab_geracao == geracao and self._gravando:
            modo = self._tab_modo
            if modo == "aguardando":
                espera = self.ESPERA_REPETICAO_TAB
                if time.monotonic() - self._tab_ultimo >= espera:
                    # Foi um toque, ou o terminal não repete a tecla:
                    # volta ao comportamento por silêncio/segundo Tab.
                    self._tab_modo = "toque"
                    self._manter_gravacao(False)
                    return
            elif modo == "segurando":
                espera = self.ESPERA_SOLTAR_TAB
                if time.monotonic() - self._tab_ultimo >= espera:
                    self._tab_modo = None
                    self._finalizar_gravacao()
                    return
            else:
                return
            time.sleep(0.05)

    def _manter_gravacao(self, manter):
        if not self.ao_manter_gravacao:
            return
        try:
            self.ao_manter_gravacao(bool(manter))
        except Exception as erro:
            log_erro(erro)

    def _finalizar_gravacao(self):
        if self.ao_parar_gravacao:
            try:
                self.ao_parar_gravacao()
            except Exception as erro:
                log_erro(erro)
            return
        if self.ao_gravar_voz:
            try:
                self.ao_gravar_voz()
            except Exception as erro:
                log_erro(erro)

    def _alternar_gravacao(self):
        if self.ao_gravar_voz:
            try:
                self.ao_gravar_voz()
            except Exception as erro:
                log_erro(erro)
                self.adicionar_externo(
                    "Sistema", "Não consegui iniciar a gravação."
                )
            return
        self.adicionar_externo(
            "Sistema", "A gravação por voz não está disponível."
        )

    def _cancelar_gravacao_atual(self):
        if not self._gravando:
            return
        if self.ao_cancelar_gravacao:
            try:
                self.ao_cancelar_gravacao()
            except Exception as erro:
                log_erro(erro)
        self.definir_gravacao(False)

    # ------------------------------------------------------------------
    # Paleta de comandos
    # ------------------------------------------------------------------

    def _comandos_menu(self):
        falando = bool(self.preferencias.obter("falar_respostas"))
        rotulo_fala = (
            "Parar de falar as respostas"
            if falando
            else "Falar as respostas"
        )
        voz_ligada = self._voz_ativa
        return [
            Comando(
                "config",
                "Configurações…",
                "Abrir o menu de preferências da Soleria.",
                "F2",
                "Sistema",
                self.abrir_config,
            ),
            Comando(
                "fala",
                rotulo_fala,
                "Liga/desliga a fala das respostas no chat.",
                "",
                "Voz",
                self._alternar_fala_respostas,
            ),
            Comando(
                "voz",
                "Desligar o modo de voz" if voz_ligada else "Ligar o modo de voz",
                "Conversa contínua por voz (microfone + fala).",
                "/voz",
                "Voz",
                self._alternar_modo_voz,
            ),
            Comando(
                "limpar",
                "Limpar conversa",
                "Apaga o histórico que aparece na tela.",
                "Ctrl+L",
                "Conversa",
                self._limpar_tudo,
            ),
            Comando(
                "retrato",
                "Ampliar/reduzir o retrato",
                "Alterna o tamanho do painel lateral.",
                "F3",
                "Interface",
                self._alternar_painel,
            ),
            Comando(
                "relatorios",
                "Abrir catálogo de relatórios",
                "Abre a pasta de relatórios no navegador.",
                "/relatorios",
                "Relatórios",
                self._abrir_relatorios,
            ),
            Comando(
                "olhar",
                "Olhar a tela",
                "Captura a tela agora e comenta o que você está fazendo.",
                "/olhar",
                "Tela",
                self._olhar_tela,
            ),
            Comando(
                "sair",
                "Sair da Soleria",
                "Encerra o programa.",
                "Ctrl+D",
                "Sistema",
                lambda: self.app.exit(),
            ),
        ]

    def _alternar_fala_respostas(self):
        valor = self.preferencias.alternar("falar_respostas")
        if self.ao_mudar_config:
            try:
                self.ao_mudar_config("falar_respostas", valor)
            except Exception as erro:
                log_erro(erro)
        estado = "ligada" if valor else "desligada"
        self.adicionar_externo("Sistema", f"Fala das respostas {estado}.")

    def _alternar_modo_voz(self):
        if self.ao_alternar_voz:
            self.ao_alternar_voz()

    def _abrir_relatorios(self):
        if self.ao_abrir_relatorios:
            self.ao_abrir_relatorios()

    def _olhar_tela(self):
        if self.ao_olhar_tela:
            self.ao_olhar_tela()

    def parar(self):
        """Solicita o encerramento da aplicação de forma thread-safe."""
        def sair():
            try:
                self.app.exit()
            except Exception:
                # Já encerrada ou ainda não iniciada.
                pass

        loop = getattr(self.app, "loop", None)
        try:
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(sair)
            else:
                sair()
        except Exception as erro:
            log_erro(erro)

    # ------------------------------------------------------------------
    # Barra de título
    # ------------------------------------------------------------------

    def _renderizar_barra_titulo(self):
        humor = HUMORES.get(self.expressao_atual, "—")
        humor_estilo = f"class:humor_{self.expressao_atual.lower()}"

        partes = [
            ("class:marca", " ◆ "),
            ("class:marca_nome", "SOLERIA"),
            ("class:marca_sub", "   IA local"),
            ("class:barra_dica", "   ·   "),
            (humor_estilo, f"● {humor}"),
        ]

        if self._gravando:
            partes.append(("class:barra_dica", "   ·   "))
            partes.append(
                (
                    "class:gravando",
                    f"🎙 {self._gravacao_status or 'gravando…'}",
                )
            )

        if self._voz_ativa:
            partes.append(("class:barra_dica", "   ·   "))
            partes.append(
                ("class:status_ativo", f"🎙 {self._voz_status or 'voz'}")
            )

        if self._observando:
            partes.append(("class:barra_dica", "   ·   "))
            partes.append(
                (
                    "class:status_ativo",
                    f"👁 {self._observando_status or 'olhando a tela…'}",
                )
            )

        if self._indice_stream is not None:
            partes.append(("class:barra_dica", "   ·   "))
            estado = self._status_atual or "pensando…"
            partes.append(("class:status_ativo", f"● {estado}"))

        # A dica fica alinhada à direita quando há espaço. Em terminais
        # baixos o painel já é uma tarja e não há o que ampliar.
        dimensoes = self._dimensoes_layout()
        if self._gravando:
            dica = "Solte Tab · Esc cancelar"
        elif self.menu_aberto:
            dica = "Esc fechar"
        else:
            dica = "Ctrl+P comandos"
        mostrar_dica = dimensoes["altura_painel"] >= 4
        largura_atual = sum(_largura_texto(t) for _s, t in partes)
        espaco = (
            dimensoes["colunas"] - largura_atual - _largura_texto(dica) - 2
        )
        if mostrar_dica and espaco > 1:
            partes.append(("class:barra_titulo", " " * espaco))
            partes.append(("class:barra_dica", dica + " "))

        return partes

    # ------------------------------------------------------------------
    # Layout responsivo
    # ------------------------------------------------------------------

    def _dimensoes_layout(self):
        tamanho = shutil.get_terminal_size((80, 24))
        colunas = max(30, tamanho.columns)
        linhas = max(7, tamanho.lines)
        altura_corpo = max(3, linhas - 1)

        if colunas >= 60 and linhas >= 12:
            modo = "lateral"
            fracao = 0.40 if self._retrato_ampliado else 0.32
            largura_painel = int(colunas * fracao)
            largura_painel = max(LARGURA_MIN_PAINEL, largura_painel)
            largura_painel = min(largura_painel, LARGURA_MAX_PAINEL)
            largura_painel = min(
                largura_painel, max(14, colunas - LARGURA_MIN_CHAT - 1)
            )
            largura_chat = max(20, colunas - largura_painel - 1)
            altura_painel = altura_corpo
            altura_historico = max(2, altura_corpo - 3)
        else:
            modo = "topo"
            if altura_corpo >= 10:
                if self._retrato_ampliado:
                    alvo = min(14, altura_corpo // 2)
                else:
                    alvo = min(9, altura_corpo // 3)
                altura_painel = max(4, alvo)
                altura_painel = min(
                    altura_painel, max(4, altura_corpo - 5)
                )
            else:
                # Terminais muito baixos: mantenha só uma tarja com o
                # nome e o humor dela para não esmagar a conversa.
                altura_painel = 1
            largura_painel = colunas
            largura_chat = colunas
            altura_historico = max(
                1, altura_corpo - altura_painel - 1 - 3
            )

        return {
            "modo": modo,
            "colunas": colunas,
            "linhas": linhas,
            "largura_painel": largura_painel,
            "altura_painel": altura_painel,
            "largura_chat": largura_chat,
            "altura_historico": altura_historico,
        }

    def _montar_corpo(self):
        if self._dimensoes_layout()["modo"] == "lateral":
            return self._layout_lateral
        return self._layout_topo

    def _alternar_painel(self):
        self._retrato_ampliado = not self._retrato_ampliado
        self._invalidate_throttled(forcar=True)

    def _rolar_historico(self, direcao):
        dimensoes = self._dimensoes_layout()
        largura = max(20, dimensoes["largura_chat"])
        altura = max(1, dimensoes["altura_historico"])
        linhas = self._linhas_historico(largura)
        maximo = max(0, len(linhas) - altura)
        passo = max(1, altura - 2)
        self._scroll_historico = min(
            maximo, max(0, self._scroll_historico + direcao * passo)
        )
        self._invalidate_throttled(forcar=True)

    # ------------------------------------------------------------------
    # Callbacks internos
    # ------------------------------------------------------------------

    def _ao_mudar_texto(self, buffer):
        if self.ao_digitar:
            try:
                self.ao_digitar()
            except Exception as erro:
                log_erro(erro)
        if self.emocoes is not None:
            try:
                self.emocoes.marcar_atividade()
            except Exception as erro:
                log_erro(erro)
        if self._pensamento_ocioso:
            self._pensamento_ocioso = None
            self._invalidate_throttled(forcar=True)

    # ------------------------------------------------------------------
    # Expressões
    # ------------------------------------------------------------------

    def _definir_expressao(self, nome):
        try:
            expressoes_ativas = self.preferencias.obter("expressoes")
        except AttributeError:
            expressoes_ativas = True
        if not expressoes_ativas:
            nome = "NORMAL"
        nome = nome if nome in EXPRESSOES else "NORMAL"
        if nome == self.expressao_atual:
            return
        self.expressao_atual = nome
        self._chars_desde_classificacao = 0
        self._invalidate_throttled(forcar=True)

    @staticmethod
    def _classificar_expressao(texto, remetente="Você"):
        return classificar_expressao(texto, remetente)

    # ------------------------------------------------------------------
    # Histórico / status
    # ------------------------------------------------------------------

    def _snapshot_historico(self):
        with self._lock:
            return list(self.historico)

    def _marcar_historico_alterado(self):
        self._versao_historico += 1
        self._cache_hist = (None, [])

    def _linhas_vazio(self, largura):
        centro = max(0, (largura - 9) // 2)
        margem = " " * centro
        return [
            [],
            [("class:marca", margem + "◆")],
            [("class:marca_nome", margem + "SOLERIA")],
            [
                (
                    "class:marca_sub",
                    " " * max(0, (largura - 38) // 2)
                    + "IA local · privada · no seu terminal",
                )
            ],
            [],
            [
                (
                    "class:texto_fraco",
                    " " * max(0, (largura - 34) // 2)
                    + "Diga alguma coisa para começar.",
                )
            ],
        ]

    def _bloco_historico(self, remetente, texto, largura, transmitindo):
        linhas = [[]]

        if remetente.startswith("Você"):
            rotulo = "▸ " + remetente.upper()
            estilo_rotulo = "class:rotulo_voce"
            estilo_barra = "class:barra_voce"
            estilo_corpo = "class:corpo_voce"
        elif remetente.startswith("Soleria"):
            rotulo = "◆ " + remetente.upper()
            estilo_rotulo = "class:rotulo_soleria"
            estilo_barra = "class:barra_soleria"
            estilo_corpo = "class:corpo_soleria"
        else:
            rotulo = "· " + remetente.upper()
            estilo_rotulo = "class:rotulo_sistema"
            estilo_barra = "class:barra_sistema"
            estilo_corpo = "class:corpo_sistema"

        linhas.append([(estilo_rotulo, "  " + rotulo)])
        largura_util = max(10, largura - 8)
        texto = (texto or "").strip()

        if not texto:
            if transmitindo:
                linhas.append(
                    [
                        (estilo_barra, "  │ "),
                        ("class:cursor_ia", "▌"),
                    ]
                )
            else:
                linhas.append(
                    [
                        (estilo_barra, "  │ "),
                        ("class:texto_fraco", "…"),
                    ]
                )
            return linhas

        quebradas = _quebrar_texto(texto, largura_util)
        for indice, linha in enumerate(quebradas):
            fragmentos = [
                (estilo_barra, "  │ "),
                (estilo_corpo, linha),
            ]
            if transmitindo and indice == len(quebradas) - 1:
                fragmentos.append(("class:cursor_ia", "▌"))
            linhas.append(fragmentos)

        return linhas

    def _linhas_historico(self, largura):
        chave = (
            largura,
            self._versao_historico,
            self._indice_stream,
        )
        if self._cache_hist[0] == chave:
            return self._cache_hist[1]

        historico = self._snapshot_historico()
        linhas = []
        if not historico:
            linhas = self._linhas_vazio(largura)
        else:
            for indice, (remetente, texto) in enumerate(historico):
                linhas.extend(
                    self._bloco_historico(
                        remetente,
                        texto,
                        largura,
                        transmitindo=indice == self._indice_stream,
                    )
                )

        self._cache_hist = (chave, linhas)
        return linhas

    def _renderizar_historico(self):
        dimensoes = self._dimensoes_layout()
        largura = max(20, dimensoes["largura_chat"])
        altura = max(1, dimensoes["altura_historico"])
        linhas = self._linhas_historico(largura)

        maximo = max(0, len(linhas) - altura)
        self._scroll_historico = min(self._scroll_historico, maximo)

        if not self.historico and not self._scroll_historico:
            # Boas-vindas no centro da área de conversa.
            pad_topo = max(0, (altura - len(linhas)) // 2)
            visiveis = [[] for _ in range(pad_topo)] + linhas
        elif self._scroll_historico:
            fim = max(0, len(linhas) - self._scroll_historico)
            inicio = max(0, fim - altura)
            visiveis = linhas[inicio:fim]
        else:
            visiveis = linhas[-altura:]

        if len(visiveis) < altura:
            visiveis = [[] for _ in range(altura - len(visiveis))] + visiveis

        return _achatar(visiveis)

    def _renderizar_status(self):
        largura = self._dimensoes_layout()["largura_chat"]

        if self._scroll_historico > 0:
            texto = (
                f"  ↑ {self._scroll_historico} linhas acima   ·   "
                "PgDn para voltar ao fim"
            )
            return [
                ("class:status_aviso", _cortar_texto(texto, largura))
            ]

        if self._gravando:
            frame = _FRAMES_STATUS[
                int(time.monotonic() * 10) % len(_FRAMES_STATUS)
            ]
            texto = (
                f"  {frame} 🎙 {self._gravacao_status or 'gravando…'}"
                "   ·   Solte Tab para parar   ·   Esc cancelar"
            )
            return [
                ("class:gravando", _cortar_texto(texto, largura))
            ]

        if self._indice_stream is not None or self._status_atual:
            frame = _FRAMES_STATUS[
                int(time.monotonic() * 10) % len(_FRAMES_STATUS)
            ]
            texto = f"  {frame} {self._status_atual or 'pensando…'}"
            return [
                ("class:status_ativo", _cortar_texto(texto, largura))
            ]

        if self._voz_ativa:
            texto = (
                f"  ◉ ouvindo   ·   {self._voz_status or 'voz ativa'}"
            )
            return [
                ("class:status_ativo", _cortar_texto(texto, largura))
            ]

        if self._pensamento_ocioso:
            texto = f"  ○ {self._pensamento_ocioso}"
            return [
                ("class:status_ocio", _cortar_texto(texto, largura))
            ]

        if largura >= 64:
            texto = (
                "  ○ pronta   ·   Enter enviar   ·   Tab falar   ·   "
                "Ctrl+P comandos"
            )
        elif largura >= 40:
            texto = "  ○ pronta   ·   Tab falar   ·   Ctrl+P comandos"
        else:
            texto = "  ○ pronta"

        return [
            ("class:status_ocio", _cortar_texto(texto, largura))
        ]

    def _executar_na_ui(self, funcao):
        if threading.current_thread() is threading.main_thread():
            funcao()
            return

        loop = getattr(self.app, "loop", None)
        try:
            if loop is not None and loop.is_running() and not loop.is_closed():
                loop.call_soon_threadsafe(funcao)
                return
        except Exception:
            pass

        # Ainda não há loop (início/encerramento): executa direto.
        funcao()

    def _invalidate_throttled(self, forcar=False):
        agora = time.monotonic()
        with self._invalidate_lock:
            if not (
                forcar
                or (agora - self._ultimo_invalidate) >= INTERVALO_INVALIDATE
            ):
                return
            self._ultimo_invalidate = agora

        def aplicar():
            try:
                self.app.invalidate()
            except Exception as erro:
                log_erro(erro)

        self._executar_na_ui(aplicar)

    # ------------------------------------------------------------------
    # Manipulação do histórico
    # ------------------------------------------------------------------

    def _adicionar(self, remetente, texto):
        with self._lock:
            self.historico.append((remetente, texto))
        self._marcar_historico_alterado()
        self._invalidate_throttled(forcar=True)

    def _atualizar_stream(self, trecho, pedido, indice):
        with self._lock:
            if (
                self._pedido_atual != pedido
                or self._indice_stream != indice
                or indice >= len(self.historico)
            ):
                return
            remetente, atual = self.historico[indice]
            novo_texto = atual + trecho
            self.historico[indice] = (remetente, novo_texto)

        self._marcar_historico_alterado()
        self._chars_desde_classificacao += len(trecho)
        if self._chars_desde_classificacao >= INTERVALO_RECLASSIFICAR:
            self._chars_desde_classificacao = 0
            nova = self._classificar_expressao(novo_texto, "Soleria")
            if nova != self.expressao_atual:
                self._definir_expressao(nova)

        self._invalidate_throttled()

    def _reset_stream(self, pedido, indice):
        with self._lock:
            if (
                self._pedido_atual != pedido
                or self._indice_stream != indice
                or indice >= len(self.historico)
            ):
                return
            self.historico[indice] = ("Soleria", "")
        self._marcar_historico_alterado()
        self._chars_desde_classificacao = 0
        self._invalidate_throttled(forcar=True)

    def _marcar_cancelado(self, pedido=None, indice=None):
        with self._lock:
            if pedido is None:
                pedido = self._pedido_atual
            if indice is None:
                indice = self._indice_stream
            if (
                self._pedido_atual != pedido
                or self._indice_stream != indice
                or indice is None
                or indice >= len(self.historico)
            ):
                return
            remetente, atual = self.historico[indice]
            if not atual.endswith("[cancelado]"):
                marca = "[cancelado]" if not atual else " [cancelado]"
                self.historico[indice] = (remetente, atual + marca)
        self._marcar_historico_alterado()
        self._invalidate_throttled(forcar=True)

    def _cancelar_pedido(self):
        with self._lock:
            if self._indice_stream is None:
                return False
            evento = self._cancelado
            pedido = self._pedido_atual
            indice = self._indice_stream

        evento.set()
        self._marcar_cancelado(pedido, indice)
        self._status_atual = "cancelando…"
        self._invalidate_throttled(forcar=True)
        return True

    def _limpar_tudo(self):
        self._cancelar_pedido()
        with self._lock:
            self.historico.clear()
            self._indice_stream = None
            self._pedido_atual += 1
            self._cancelado = threading.Event()

        self._marcar_historico_alterado()
        self._scroll_historico = 0
        self._status_atual = None
        self._pensamento_ocioso = None
        self._definir_expressao("NORMAL")
        if self.ao_limpar:
            try:
                self.ao_limpar()
            except Exception as erro:
                log_erro(erro)
        self._invalidate_throttled(forcar=True)

    # ------------------------------------------------------------------
    # Entrada do usuário
    # ------------------------------------------------------------------

    def _ao_aceitar(self, buffer):
        texto = buffer.text.strip()
        if not texto:
            buffer.reset()
            return

        # Mandar a mensagem encerra a gravação em andamento; o texto
        # transcrito já foi colocado no buffer pelo fluxo de voz.
        if self._gravando:
            self._cancelar_gravacao_atual()

        comando = texto.casefold()
        if comando in _COMANDOS_SAIR:
            buffer.reset()
            self.app.exit()
            return

        if comando == "/limpar":
            buffer.reset()
            self._limpar_tudo()
            return

        if comando == "/voz":
            buffer.reset()
            if self.ao_alternar_voz:
                self.ao_alternar_voz()
            return

        if comando == "/relatorios":
            buffer.reset()
            if self.ao_abrir_relatorios:
                self.ao_abrir_relatorios()
            return

        if comando in {"/olhar", "/tela"}:
            buffer.reset()
            if self.ao_olhar_tela:
                self.ao_olhar_tela()
            else:
                self.adicionar_externo(
                    "Sistema", "Olhar a tela não está disponível."
                )
            return

        if comando in {"/config", "/configuracoes", "/configurações"}:
            buffer.reset()
            self.abrir_config()
            return

        if comando in {"/comandos", "/paleta"}:
            buffer.reset()
            self.abrir_paleta()
            return

        if self._indice_stream is not None:
            # Não descarte o que o usuário digitou: mantém no buffer e
            # avisa que é preciso esperar a resposta atual.
            self._status_atual = "aguarde a resposta atual…"
            self._invalidate_throttled(forcar=True)
            return True

        buffer.reset()
        self._pensamento_ocioso = None
        self._definir_expressao(
            self._classificar_expressao(texto, "Você")
        )
        self._status_atual = None
        self._chars_desde_classificacao = 0

        with self._lock:
            self._pedido_atual += 1
            pedido = self._pedido_atual
            cancelado = threading.Event()
            self._cancelado = cancelado

            self.historico.append(("Você", texto))
            self.historico.append(("Soleria", ""))
            indice = len(self.historico) - 1
            self._indice_stream = indice

        self._scroll_historico = 0
        self._marcar_historico_alterado()
        self._invalidate_throttled(forcar=True)

        threading.Thread(
            target=self._processar,
            args=(texto, pedido, indice, cancelado),
            name="soleria-resposta",
            daemon=True,
        ).start()

    def _processar(self, texto, pedido, indice, cancelado):
        def ativo():
            return (
                self._pedido_atual == pedido
                and self._indice_stream == indice
                and not cancelado.is_set()
            )

        def callback_stream(trecho):
            if ativo():
                self._atualizar_stream(trecho, pedido, indice)

        def callback_status(texto_status):
            if ativo():
                self._status_atual = texto_status
                self._invalidate_throttled(forcar=True)

        def callback_reset():
            if ativo():
                self._reset_stream(pedido, indice)

        try:
            resposta = self.ao_enviar(
                texto,
                callback_stream,
                callback_status,
                callback_reset,
                cancelado,
            )
        except Exception as erro:
            log_erro(erro)
            resposta = "Erro inesperado ao processar a mensagem."

        with self._lock:
            atual = (
                self._pedido_atual == pedido
                and self._indice_stream == indice
            )

        if not atual:
            # A conversa foi limpa ou outra requisição assumiu.
            return

        if cancelado.is_set():
            self._marcar_cancelado(pedido, indice)
            with self._lock:
                if self._indice_stream == indice:
                    self._definir_expressao("NORMAL")
        elif resposta:
            if self.emocoes is not None:
                self.sincronizar_emocao()
                expressao = self.expressao_atual
            else:
                expressao = self._classificar_expressao(resposta, "Soleria")
            with self._lock:
                if (
                    self._pedido_atual == pedido
                    and self._indice_stream == indice
                ):
                    self._definir_expressao(expressao)
                    if indice < len(self.historico):
                        self.historico[indice] = ("Soleria", resposta)
                        self._marcar_historico_alterado()

        with self._lock:
            if (
                self._pedido_atual == pedido
                and self._indice_stream == indice
            ):
                # Só limpa o status/stream se esta requisição ainda é a
                # atual; uma nova pode ter começado nesse intervalo.
                self._status_atual = None
                self._indice_stream = None
        self._invalidate_throttled(forcar=True)

    def run(self):
        self._definir_titulo_terminal()
        self.app.run()

    @staticmethod
    def _definir_titulo_terminal():
        """Marca a janela do terminal para a Soleria não se olhar no OCR.

        O título é a única pista portátil de qual janela hospeda esta TUI:
        o observador de tela compara esse valor com a janela em foco.
        """
        import sys

        try:
            sys.stdout.write("\x1b]2;Soleria\x07")
            sys.stdout.flush()
        except (OSError, ValueError):
            pass


__all__ = [
    "ChatUI",
    "EXPRESSOES",
    "HUMORES",
    "PASTA_EXPRESSOES",
    "FATOR_SUPERSAMPLE",
    "_aplicar_dither",
    "_comandos_imagem_kitty",
    "_contem",
    "_cor_pixel",
    "_cortar_texto",
    "_DIACRITICOS",
    "_e_pixel_art",
    "_escape_kitty",
    "_largura_texto",
    "_PLACEHOLDER_KITTY",
    "_quebrar_texto",
    "_usar_imagem_kitty",
]
