"""Preparação do texto e fala em streaming."""

import queue
import re
import threading

from soleria.logging_utils import log_erro

from .config import LIMITE_TRECHO_FALA

_FIM_FRASE = re.compile(r"[.!?…]+[)\]}»\"'”’*_]*\s+")
_QUEBRA_LINHA = re.compile(r"\n\s*")
_COMANDO_INTERNO = re.compile(
    r"\[\[\s*(?:PESQUISAR|PERGUNTAR)", re.IGNORECASE
)

_URL = re.compile(
    r"https?://[^\s<>\"']+[^\s<>\"'.,;:!?)\]}”,]",
    re.IGNORECASE,
)
_MARKDOWN = re.compile(r"[*_`]+")
_CABECALHO = re.compile(r"^\s*#{1,6}\s+")
_VIRGULA_NUMERICA = re.compile(r"(?<=\d),(?=\d)")


def _tem_conteudo_falavel(texto):
    """Evita mandar ao TTS trechos só com pontuação/emoji/símbolos.

    O Edge TTS responde ``NoAudioReceived`` para esse tipo de trecho.
    """
    return any(caractere.isalnum() for caractere in texto)


def _preparar_fala(texto):
    """Simplifica o texto para o TTS sem alterar o que aparece na tela.

    URLs viram "link" (o Edge TTS costuma falhar em URLs sozinhas) e
    marcações de Markdown são removidas. Vírgulas entre números viram
    "vírgula" para o texto ser lido corretamente.
    """
    texto = _URL.sub("link", texto)
    texto = _CABECALHO.sub("", texto)
    texto = _MARKDOWN.sub("", texto)
    texto = _VIRGULA_NUMERICA.sub(" vírgula ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def extrair_frase(texto, limite=LIMITE_TRECHO_FALA):
    """Separa a primeira frase falável de ``texto``.

    Retorna ``(frase, resto)``. Sem uma frase completa, devolve
    ``(None, texto)``. Textos muito longos sem pontuação são cortados no
    último espaço para a fala não ficar parada esperando o fim.
    """
    if not texto:
        return None, texto or ""

    match = _FIM_FRASE.search(texto)
    if match:
        fim = match.end()
        frase = texto[:fim].strip()
        if frase:
            return frase, texto[fim:]
        return None, texto[fim:]

    match = _QUEBRA_LINHA.search(texto)
    if match:
        fim = match.end()
        frase = texto[:fim].strip()
        if frase:
            return frase, texto[fim:]

    if len(texto) >= limite:
        corte = texto.rfind(" ", 0, limite)
        if corte <= 0:
            corte = limite
        frase = texto[:corte].strip()
        if frase:
            return frase, texto[corte:].lstrip()

    return None, texto


class Falante:
    """Fala um texto que ainda está sendo gerado.

    O modelo chama :meth:`adicionar` a cada trecho recebido. A classe
    acumula o texto, separa frases completas e entrega cada uma a uma
    thread de fala. Assim a primeira frase pode ser ouvida enquanto o
    restante da resposta ainda está sendo escrito.
    """

    def __init__(self, sintetizador, ao_falar=None):
        self._sintetizador = sintetizador
        self._ao_falar = ao_falar
        self._fila = queue.Queue()
        self._buffer = ""
        self._liberado = False
        self._geracao = 0
        self._lock = threading.Lock()
        self._parado = threading.Event()
        self._thread = threading.Thread(
            target=self._loop, name="soleria-fala", daemon=True
        )
        self._thread.start()

    # ------------------------------------------------------------------
    # API usada pelo stream do modelo
    # ------------------------------------------------------------------

    def adicionar(self, trecho):
        if not trecho or self._parado.is_set():
            return

        with self._lock:
            if self._parado.is_set():
                return

            self._buffer += trecho

            # Comandos internos nunca devem ser falados. Se um deles
            # aparecer depois de um começo de resposta, descartamos a
            # partir dele; o callback de reset logo em seguida limpa o
            # restante.
            comando = _COMANDO_INTERNO.search(self._buffer)
            if comando:
                self._buffer = self._buffer[: comando.start()]

            if not self._liberado and not self._liberar():
                return

            self._separar()

    def finalizar(self):
        """Fala o que sobrou no buffer, mesmo sem pontuação final."""
        with self._lock:
            if self._parado.is_set():
                self._buffer = ""
                return
            if not self._liberado and not self._liberar():
                self._buffer = ""
                return
            texto = _preparar_fala(self._buffer)
            self._buffer = ""
            if texto and _tem_conteudo_falavel(texto):
                self._enfileirar(texto)

    def limpar(self):
        """Descarta o texto pendente (usado quando o modelo vai pesquisar)."""
        with self._lock:
            self._buffer = ""
            self._liberado = False
            self._geracao += 1
        self._esvaziar()
        self._interromper()

    def aguardar(self):
        """Bloqueia até todas as frases enfileiradas serem faladas."""
        if not self._parado.is_set():
            self._fila.join()

    def parar(self):
        with self._lock:
            self._parado.set()
            self._buffer = ""
            self._geracao += 1
        self._esvaziar()
        self._interromper()

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _liberar(self):
        """Espera o começo da resposta para descartar comandos de pesquisa."""
        texto = self._buffer.lstrip()
        if not texto:
            return False
        if texto.startswith("[["):
            return False
        if texto.startswith("[") and len(texto) < 4:
            return False
        self._liberado = True
        return True

    def _separar(self):
        """Chame com ``self._lock`` adquirido."""
        while True:
            frase, resto = extrair_frase(self._buffer)
            if frase is None:
                # ``extrair_frase`` pode pular pontuação solta no começo
                # (por exemplo, "! Tudo bem?"); nesse caso continua.
                if resto != self._buffer:
                    self._buffer = resto
                    continue
                return
            self._buffer = resto
            frase = _preparar_fala(frase)
            if frase and _tem_conteudo_falavel(frase):
                self._enfileirar(frase)

    def _enfileirar(self, frase):
        """Chame com ``self._lock`` adquirido (ou durante a finalização)."""
        self._fila.put((self._geracao, frase))

    def _esvaziar(self):
        while True:
            try:
                self._fila.get_nowait()
            except queue.Empty:
                return
            else:
                self._fila.task_done()

    def _interromper(self):
        try:
            self._sintetizador.parar()
        except Exception as erro:
            log_erro(erro)

    def _agrupar(self, geracao, frase):
        """Junta frases já enfileiradas para reduzir pausas entre elas."""
        while len(frase) < LIMITE_TRECHO_FALA:
            try:
                outra_geracao, outra = self._fila.get_nowait()
            except queue.Empty:
                break

            try:
                if outra_geracao == geracao and outra:
                    frase = f"{frase} {outra}".strip()
            finally:
                # Cada item consumido precisa ser contabilizado, mesmo
                # quando pertence a uma geração já descartada.
                self._fila.task_done()
        return frase

    def _loop(self):
        while not self._parado.is_set():
            try:
                geracao, frase = self._fila.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                if self._parado.is_set():
                    break
                if geracao != self._geracao:
                    # O texto foi descartado por um reset/parada enquanto
                    # esta frase esperava na fila.
                    continue
                frase = self._agrupar(geracao, frase)
                if geracao != self._geracao:
                    continue
                if self._ao_falar:
                    try:
                        self._ao_falar()
                    except Exception as erro:
                        log_erro(erro)
                self._sintetizador.falar(frase)
            except Exception as erro:
                log_erro(erro)
            finally:
                self._fila.task_done()
