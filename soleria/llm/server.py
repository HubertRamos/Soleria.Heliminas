"""Gerenciamento do processo llama-server."""

import os
import subprocess
import threading
import time
import urllib.request

from config import (
    BASE_URL,
    CAMADAS_GPU,
    CONTEXTO,
    HOST,
    LLAMA_DIR,
    LLAMA_SERVER,
    MODELO,
    PORTA,
    TEMPO_INICIALIZACAO,
)
from soleria.logging_utils import abrir_log, log_erro, log_evento


class LlamaServer:
    """Inicia o llama-server sob demanda e o encerra quando fica ocioso."""

    def __init__(self):
        self.processo = None
        self.iniciado_por_nos = False

        # Protege o estado compartilhado (processo/último uso).
        self.lock = threading.RLock()
        # Garante que apenas uma thread tente iniciar o servidor.
        self._startup_lock = threading.Lock()
        # Evita iniciar um novo processo enquanto o anterior é encerrado.
        self._parando = threading.Event()
        self._parada_concluida = threading.Event()
        self._parada_concluida.set()

        self.ultimo_uso = time.monotonic()
        self.ocupado = False

    # ------------------------------------------------------------------
    # Atividade / ociosidade
    # ------------------------------------------------------------------

    def marcar_atividade(self):
        """Atualiza o timestamp de último uso (thread-safe e barato)."""
        self.ultimo_uso = time.monotonic()

    def marcar_ocupado(self, ocupado: bool):
        with self.lock:
            self.ocupado = ocupado
            self.ultimo_uso = time.monotonic()

    def tempo_ocioso(self):
        return time.monotonic() - self.ultimo_uso

    def esta_ocupado(self):
        return self.ocupado

    def esta_pronto(self):
        """True quando o modelo já está no ar, sem iniciá-lo.

        A iniciativa própria não deve subir o modelo só para puxar assunto:
        se ele foi encerrado por inatividade, a conversa também acabou.
        """
        with self.lock:
            processo = self.processo
            if processo is not None and processo.poll() is None:
                return True
        return self.api_pronta(timeout=0.5)

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def api_pronta(self, timeout=2.0):
        try:
            req = urllib.request.Request(
                f"{BASE_URL}/models",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resposta:
                return getattr(resposta, "status", 200) == 200
        except Exception:
            return False

    def iniciar(self):
        """Garante que o servidor esteja no ar. Retorna True/False."""
        with self._startup_lock:
            # Se outro fluxo está encerrando o modelo, espere terminar.
            if self._parando.is_set():
                self._parada_concluida.wait(timeout=15)
            if self._parando.is_set():
                return False

            if self.api_pronta():
                return not self._parando.is_set()

            processo = self._obter_ou_iniciar_processo()
            if processo is None and self._parando.is_set():
                # A parada começou entre o teste acima e a inicialização;
                # espere e tente mais uma vez.
                self._parada_concluida.wait(timeout=15)
                if self._parando.is_set():
                    return False
                processo = self._obter_ou_iniciar_processo()
            if processo is None:
                return False

            return self._aguardar_api(processo)

    def _obter_ou_iniciar_processo(self):
        with self.lock:
            if self._parando.is_set():
                return None

            if self.processo is not None:
                if self.processo.poll() is None:
                    # Já estamos iniciando; apenas aguarde a API.
                    return self.processo
                self._limpar_processo()

            if not LLAMA_SERVER.is_file():
                log_erro(
                    FileNotFoundError(f"llama-server não encontrado: {LLAMA_SERVER}")
                )
                return None
            if not MODELO.is_file():
                log_erro(FileNotFoundError(f"Modelo GGUF não encontrado: {MODELO}"))
                return None

            try:
                processo = self._iniciar_processo()
            except Exception as erro:
                log_erro(erro)
                self._limpar_processo()
                return None

            if self._parando.is_set():
                # O encerramento começou enquanto o processo subia.
                orfao = processo
                self._limpar_processo()
            else:
                self.processo = processo
                self.iniciado_por_nos = True
                orfao = None
                log_evento(f"llama-server iniciado (pid {processo.pid})")

        if orfao is not None:
            self._encerrar_processo(orfao)
            return None

        return processo

    def _iniciar_processo(self):
        ambiente = os.environ.copy()
        biblioteca = str(LLAMA_DIR / "build" / "bin")
        ambiente["LD_LIBRARY_PATH"] = (
            biblioteca + ":" + ambiente.get("LD_LIBRARY_PATH", "")
        )

        destino_log = abrir_log()
        proprio_log = destino_log is not None
        if destino_log is None:
            destino_log = subprocess.DEVNULL

        try:
            return subprocess.Popen(
                [
                    str(LLAMA_SERVER),
                    "-m",
                    str(MODELO),
                    "-c",
                    str(CONTEXTO),
                    # A aplicação serializa as respostas (o llama-server é
                    # usado por uma requisição de cada vez). Sem isso, o
                    # llama.cpp divide o contexto entre 4 slots por padrão,
                    # e cada resposta só enxerga 1/4 do contexto configurado.
                    "--parallel",
                    "1",
                    "-ngl",
                    str(CAMADAS_GPU),
                    "--host",
                    HOST,
                    "--port",
                    str(PORTA),
                    "--jinja",
                ],
                cwd=str(LLAMA_DIR),
                env=ambiente,
                stdin=subprocess.DEVNULL,
                stdout=destino_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        finally:
            # O filho tem a própria cópia do descritor; não precisamos
            # manter o arquivo aberto no processo pai.
            if proprio_log:
                destino_log.close()

    def _aguardar_api(self, processo):
        inicio = time.monotonic()
        while time.monotonic() - inicio < TEMPO_INICIALIZACAO:
            if self.api_pronta(timeout=1.0):
                log_evento("llama-server pronto")
                return True

            with self.lock:
                atual = self.processo

            if atual is not processo:
                # Outra thread/rotina encerrou o processo.
                return False

            if processo.poll() is not None:
                codigo = processo.returncode
                log_evento(
                    f"llama-server terminou durante a inicialização (código {codigo})"
                )
                with self.lock:
                    if self.processo is processo:
                        self._limpar_processo()
                return False

            time.sleep(0.5)

        log_evento(f"llama-server não respondeu em {TEMPO_INICIALIZACAO}s; encerrando")
        proprio = False
        with self.lock:
            if self.processo is processo:
                proprio = self.iniciado_por_nos
                self._limpar_processo()
        if proprio:
            self._encerrar_processo(processo)
        return False

    def _limpar_processo(self):
        """Chame com ``self.lock`` adquirido."""
        self.processo = None
        self.iniciado_por_nos = False

    @staticmethod
    def _encerrar_processo(processo, timeout=10):
        if processo is None:
            return
        try:
            if processo.poll() is not None:
                return
            processo.terminate()
            try:
                processo.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                processo.kill()
                try:
                    processo.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    log_evento("llama-server não encerrou após SIGKILL")
        except Exception as erro:
            log_erro(erro)

    def encerrar(self):
        """Encerra o servidor somente se ele foi iniciado por esta aplicação."""
        with self.lock:
            if self._parando.is_set():
                # Outra thread já está encerrando; espere de verdade em vez
                # de retornar com o processo ainda vivo.
                aguardar = True
                processo = None
            else:
                aguardar = False
                processo = self.processo
                if processo is None or not self.iniciado_por_nos:
                    return
                self._parando.set()
                self._parada_concluida.clear()
                self._limpar_processo()

        if aguardar:
            self._parada_concluida.wait(timeout=15)
            return

        try:
            self._encerrar_processo(processo)
            log_evento("llama-server encerrado")
        finally:
            self._parando.clear()
            self._parada_concluida.set()
