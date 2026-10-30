"""Captura da tela inteira sem depender de um servidor X.

No Wayland a forma correta é o portal ``org.freedesktop.portal.Screenshot``;
ele funciona no umbriel, no GNOME, no KDE e em outros compositores sem
pedir permissão a cada captura quando a opção é não interativa. Quando o
portal não está disponível, caem-se os utilitários usuais de cada ambiente.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from config import CAPTURA_TIMEOUT


class CapturaIndisponivel(RuntimeError):
    """Nenhum método de captura funcionou."""


def _png_valido(dados):
    return bool(dados) and dados[:8] == b"\x89PNG\r\n\x1a\n"


def _capturar_portal(timeout):
    """Pede uma captura ao xdg-desktop-portal via D-Bus.

    O portal grava um PNG temporário e devolve o ``file://`` no sinal de
    resposta. O arquivo é lido e apagado na hora: a imagem não fica no disco.
    """
    try:
        from dbus_next import Message, MessageType, Variant
        from dbus_next.aio import MessageBus
    except ImportError as erro:
        raise CapturaIndisponivel(
            "instale dbus-next para capturar pelo portal Wayland"
        ) from erro

    async def executar():
        barramento = await MessageBus().connect()
        fila = asyncio.Queue()

        def ao_mensagem(mensagem):
            if (
                mensagem.message_type == MessageType.SIGNAL
                and mensagem.interface == "org.freedesktop.portal.Request"
                and mensagem.member == "Response"
            ):
                fila.put_nowait((mensagem.path, mensagem.body))

        barramento.add_message_handler(ao_mensagem)
        try:
            retorno = await barramento.call(
                Message(
                    destination="org.freedesktop.portal.Desktop",
                    path="/org/freedesktop/portal/desktop",
                    interface="org.freedesktop.portal.Screenshot",
                    member="Screenshot",
                    signature="sa{sv}",
                    body=[
                        "",
                        {
                            "interactive": Variant("b", False),
                            "modal": Variant("b", False),
                        },
                    ],
                )
            )
            if (
                retorno.message_type != MessageType.METHOD_RETURN
                or not retorno.body
            ):
                raise CapturaIndisponivel(
                    "o portal recusou o pedido de captura"
                )

            caminho_pedido = retorno.body[0]
            while True:
                caminho, corpo = await asyncio.wait_for(
                    fila.get(), timeout=timeout
                )
                if caminho == caminho_pedido:
                    break

            resposta, resultados = corpo[0], corpo[1]
            if resposta != 0:
                raise CapturaIndisponivel(
                    "a captura foi cancelada ou negada"
                )
            uri = resultados.get("uri")
            valor = getattr(uri, "value", uri)
            if not valor:
                raise CapturaIndisponivel("o portal não devolveu o arquivo")
            arquivo = Path(unquote(urlparse(str(valor)).path))
            try:
                return arquivo.read_bytes()
            finally:
                try:
                    arquivo.unlink()
                except OSError:
                    pass
        finally:
            try:
                barramento.disconnect()
            except Exception:
                pass

    try:
        return asyncio.run(executar())
    except asyncio.TimeoutError as erro:
        raise CapturaIndisponivel("o portal demorou para capturar") from erro


def _rodar(comando, timeout):
    return subprocess.run(
        comando,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _diretorios_de_captura():
    candidatos = [
        os.getenv("XDG_PICTURES_DIR"),
        Path.home() / "Imagens",
        Path.home() / "Pictures",
    ]
    diretorios = []
    for candidato in candidatos:
        if not candidato:
            continue
        caminho = Path(os.path.expandvars(str(candidato))).expanduser()
        if caminho.is_dir() and caminho not in diretorios:
            diretorios.append(caminho)
    return diretorios


def _fotos_recentes():
    encontrados = {}
    for diretorio in _diretorios_de_captura():
        try:
            for arquivo in diretorio.glob("screenshot_*"):
                try:
                    encontrados[str(arquivo)] = arquivo.stat().st_mtime
                except OSError:
                    continue
        except OSError:
            continue
    return encontrados


def _capturar_noctalia(timeout):
    """Noctalia (usado no umbriel) salva em ~/Imagens.

    A captura é nossa, então o arquivo é apagado depois da leitura para não
    deixar o conteúdo da tela no disco.
    """
    if not shutil.which("noctalia"):
        raise CapturaIndisponivel("noctalia não encontrado")

    antes = _fotos_recentes()
    resultado = _rodar(
        ["noctalia", "msg", "screenshot-fullscreen"], timeout=timeout
    )
    if resultado.returncode != 0:
        raise CapturaIndisponivel("o noctalia não capturou a tela")

    limite = time.monotonic() + 3.0
    while time.monotonic() < limite:
        for caminho, mtime in _fotos_recentes().items():
            if antes.get(caminho) == mtime:
                continue
            arquivo = Path(caminho)
            try:
                dados = arquivo.read_bytes()
                arquivo.unlink()
                return dados
            except OSError:
                continue
        time.sleep(0.1)
    raise CapturaIndisponivel("o noctalia não informou o arquivo")


def _capturar_stdout(comando, timeout):
    resultado = _rodar(comando, timeout=timeout)
    if resultado.returncode != 0 or not _png_valido(resultado.stdout):
        raise CapturaIndisponivel(
            f"{comando[0]} não produziu uma imagem"
        )
    return resultado.stdout


def _capturar_arquivo(comando, timeout):
    descritor, caminho = tempfile.mkstemp(prefix="soleria-tela-", suffix=".png")
    os.close(descritor)
    try:
        resultado = _rodar(
            [parte.format(saida=caminho) for parte in comando],
            timeout=timeout,
        )
        dados = Path(caminho).read_bytes()
        if resultado.returncode != 0 or not _png_valido(dados):
            raise CapturaIndisponivel(
                f"{comando[0]} não produziu uma imagem"
            )
        return dados
    finally:
        try:
            Path(caminho).unlink()
        except OSError:
            pass


def _capturar_por_utilitario(timeout):
    metodos = []
    if shutil.which("noctalia"):
        metodos.append(lambda: _capturar_noctalia(timeout))
    if shutil.which("grim"):
        metodos.append(
            lambda: _capturar_stdout(["grim", "-t", "png", "-"], timeout)
        )
    if shutil.which("gnome-screenshot"):
        metodos.append(
            lambda: _capturar_arquivo(
                ["gnome-screenshot", "-f", "{saida}"], timeout
            )
        )
    if shutil.which("spectacle"):
        metodos.append(
            lambda: _capturar_arquivo(
                ["spectacle", "-b", "-n", "-o", "{saida}"], timeout
            )
        )
    if shutil.which("import"):
        metodos.append(
            lambda: _capturar_stdout(
                ["import", "-window", "root", "png:-"], timeout
            )
        )
    if shutil.which("scrot"):
        metodos.append(
            lambda: _capturar_arquivo(["scrot", "-o", "{saida}"], timeout)
        )

    erros = []
    for metodo in metodos:
        try:
            return metodo()
        except (CapturaIndisponivel, OSError, subprocess.SubprocessError) as erro:
            erros.append(str(erro))
    detalhe = f" ({'; '.join(erros)})" if erros else ""
    raise CapturaIndisponivel(
        "nenhum método de captura disponível" + detalhe
    )


def capturar_tela(timeout=CAPTURA_TIMEOUT):
    """Devolve o PNG da tela inteira, sem deixá-lo salvo."""
    erros = []

    try:
        dados = _capturar_portal(timeout)
        if _png_valido(dados):
            return dados
        erros.append("o portal devolveu um formato inesperado")
    except (CapturaIndisponivel, OSError, subprocess.SubprocessError) as erro:
        erros.append(str(erro))

    try:
        return _capturar_por_utilitario(timeout)
    except (CapturaIndisponivel, OSError, subprocess.SubprocessError) as erro:
        erros.append(str(erro))

    raise CapturaIndisponivel("; ".join(dict.fromkeys(erros)))


def motivo_indisponivel():
    """Explica por que a captura não funcionaria, ou ``None`` se funciona."""
    if shutil.which("noctalia") or shutil.which("grim"):
        return None
    if shutil.which("gnome-screenshot") or shutil.which("spectacle"):
        return None
    if shutil.which("import") or shutil.which("scrot"):
        return None
    try:
        import dbus_next  # noqa: F401
    except ImportError:
        return (
            "A captura de tela precisa do portal Wayland (dbus-next) ou de "
            "um utilitário como grim, noctalia ou gnome-screenshot."
        )
    return None
