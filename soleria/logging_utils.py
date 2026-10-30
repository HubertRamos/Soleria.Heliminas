"""Registro de erros e eventos para diagnóstico local."""

import threading
import traceback
from datetime import datetime

from config import LOG

_lock = threading.Lock()


def _escrever(titulo: str, corpo: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            with open(LOG, "a", encoding="utf-8") as arquivo:
                agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                arquivo.write(f"\n===== {titulo} {agora} =====\n")
                arquivo.write(corpo)
                if not corpo.endswith("\n"):
                    arquivo.write("\n")
    except Exception:
        # O log nunca deve derrubar a aplicação.
        pass


def log_erro(erro) -> None:
    """Registra uma exceção (ou uma mensagem) no log local."""
    if isinstance(erro, BaseException):
        detalhe = "".join(traceback.format_exception(erro))
    else:
        detalhe = str(erro)
    _escrever("ERRO SOLERIA", detalhe)


def log_evento(mensagem: str) -> None:
    """Registra um evento informativo (início/parada do servidor, etc.)."""
    _escrever("EVENTO SOLERIA", str(mensagem))


def abrir_log():
    """Abre o log em modo append para redirecionar a saída do servidor.

    Retorna ``None`` se não for possível abrir; quem chama deve usar
    ``subprocess.DEVNULL`` nesse caso.
    """
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        return open(LOG, "a", encoding="utf-8", buffering=1)
    except OSError:
        return None
