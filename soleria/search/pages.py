"""Leitura e extração de texto das páginas encontradas na pesquisa."""

import ipaddress
import re
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from config import (
    MAX_BYTES_PAGINA,
    MAX_CARACTERES_PAGINA,
    MAX_PAGINAS,
    TIMEOUT_PAGINA,
)
from soleria.logging_utils import log_erro

_AGENTE = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Soleria/1.0"
)

_TIPOS_ACEITOS = (
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "application/json",
)

_TAGS_IGNORADAS = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "canvas",
    "iframe",
    "object",
    "embed",
    "form",
    "button",
    "nav",
    "header",
    "footer",
    "aside",
}

_TAGS_BLOCO = {
    "p",
    "div",
    "br",
    "li",
    "ul",
    "ol",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "tr",
    "td",
    "th",
    "table",
    "section",
    "article",
    "main",
    "blockquote",
    "pre",
    "hr",
    "figure",
    "figcaption",
    "dd",
    "dt",
}


def notificar_progresso(callback, texto):
    """Envia uma mensagem de progresso sem deixar a UI derrubar a busca."""
    if not callback:
        return
    try:
        callback(texto)
    except Exception as erro:
        log_erro(erro)


def _limpar_texto(texto):
    texto = (texto or "").replace("\r\n", "\n").replace("\r", "\n")
    texto = re.sub(r"[ \t\f\v]+", " ", texto)
    texto = re.sub(r" *\n *", "\n", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


class _ExtratorHTML(HTMLParser):
    """Extrai o texto visível e o título de uma página HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._partes = []
        self._titulo = []
        self._ignorar = 0
        self._em_titulo = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _TAGS_IGNORADAS:
            self._ignorar += 1
            return
        if self._ignorar:
            return
        if tag == "title":
            self._em_titulo = True
            return
        if tag in _TAGS_BLOCO:
            self._partes.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _TAGS_IGNORADAS:
            if self._ignorar:
                self._ignorar -= 1
            return
        if self._ignorar:
            return
        if tag == "title":
            self._em_titulo = False
            return
        if tag in _TAGS_BLOCO:
            self._partes.append("\n")

    def handle_data(self, data):
        if self._ignorar:
            return
        if self._em_titulo:
            self._titulo.append(data)
            return
        if data.strip():
            self._partes.append(data)

    @property
    def titulo(self):
        return _limpar_texto(" ".join(self._titulo))

    @property
    def texto(self):
        return _limpar_texto("".join(self._partes))


def _decodificar(corpo, content_type):
    """Decodifica o corpo usando o charset do cabeçalho, com fallbacks."""
    charset = None
    match = re.search(
        r"charset\s*=\s*[\"']?([\w.-]+)", content_type or "", re.IGNORECASE
    )
    if match:
        charset = match.group(1)

    for codificacao in (charset, "utf-8", "latin-1"):
        if not codificacao:
            continue
        try:
            return corpo.decode(codificacao)
        except (LookupError, UnicodeDecodeError):
            continue
    return corpo.decode("utf-8", errors="replace")


def _tipo_aceito(content_type):
    tipo = (content_type or "").split(";", 1)[0].strip().lower()
    if not tipo:
        # Sem Content-Type: tenta interpretar como HTML.
        return True
    return any(
        tipo == aceito or tipo.startswith(aceito + "+")
        for aceito in _TIPOS_ACEITOS
    )


def _extrair_texto(corpo, content_type):
    """Devolve ``(texto, titulo)`` a partir do corpo bruto."""
    if not _tipo_aceito(content_type):
        return "", ""

    tipo = (content_type or "").split(";", 1)[0].strip().lower()
    texto = _decodificar(corpo, content_type)

    if tipo in {"text/plain", "application/json"}:
        return _limpar_texto(texto), ""

    extrator = _ExtratorHTML()
    try:
        extrator.feed(texto)
        extrator.close()
    except Exception as erro:
        log_erro(erro)
        return "", ""
    return extrator.texto, extrator.titulo


def _url_permitida(url):
    """Aceita apenas HTTP(S) público, evitando endereços locais/privados."""
    try:
        partes = urlsplit(url)
    except ValueError:
        return False

    if partes.scheme not in {"http", "https"} or not partes.hostname:
        return False

    host = partes.hostname.lower().rstrip(".")
    if "%" in host:
        return False
    if host == "localhost" or host.endswith(
        (".local", ".internal", ".lan", ".home")
    ):
        return False

    try:
        endereco = ipaddress.ip_address(host)
    except ValueError:
        return True

    return not (
        endereco.is_private
        or endereco.is_loopback
        or endereco.is_link_local
        or endereco.is_reserved
        or endereco.is_unspecified
        or endereco.is_multicast
    )


class _RedirecionadorSeguro(HTTPRedirectHandler):
    """Impede que um redirecionamento leve a leitura para a rede local."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _url_permitida(newurl):
            raise ValueError("redirecionamento bloqueado")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_ABRIDOR = build_opener(_RedirecionadorSeguro())


def _abrir(pedido, timeout):
    """Ponto único de abertura de URL (facilita testes offline)."""
    return _ABRIDOR.open(pedido, timeout=timeout)


def ler_pagina(url, timeout=None, max_caracteres=None):
    """Abre uma URL e devolve ``{"titulo", "conteudo"}`` ou ``None``."""
    if not _url_permitida(url):
        return None

    limite = max(50, int(max_caracteres or MAX_CARACTERES_PAGINA))
    limite_bytes = max(1024, int(MAX_BYTES_PAGINA))
    pedido = Request(
        url,
        headers={
            "User-Agent": _AGENTE,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            "Accept-Encoding": "identity",
        },
    )

    try:
        with _abrir(
            pedido, max(1.0, float(timeout or TIMEOUT_PAGINA))
        ) as resposta:
            content_type = resposta.headers.get("Content-Type", "")
            if not _tipo_aceito(content_type):
                return None
            corpo = resposta.read(limite_bytes + 1)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        # Links que não abrem são comuns; o status da UI já informa.
        return None
    except Exception as erro:
        log_erro(erro)
        return None

    if len(corpo) > limite_bytes:
        corpo = corpo[:limite_bytes]

    texto, titulo = _extrair_texto(corpo, content_type)
    if not texto:
        return None

    if len(texto) > limite:
        texto = texto[: limite - 1].rstrip() + "…"

    return {"titulo": titulo, "conteudo": texto}


def ler_paginas(
    fontes,
    limite=None,
    ao_progresso=None,
    cancelado=None,
):
    """Acrescenta o conteúdo das primeiras páginas às fontes da pesquisa.

    As fontes originais são preservadas. Quando a leitura falha, a fonte
    continua apenas com o resumo do buscador.
    """
    fontes = list(fontes or ())
    limite = MAX_PAGINAS if limite is None else int(limite)
    if limite <= 0 or not fontes:
        return fontes

    resultado = []
    for indice, fonte in enumerate(fontes):
        if cancelado is not None and cancelado.is_set():
            resultado.extend(fontes[indice:])
            break

        if indice >= limite:
            resultado.append(fonte)
            continue

        host = urlsplit(fonte.get("url", "")).hostname or "link"
        notificar_progresso(
            ao_progresso, f"abrindo link {indice + 1}/{limite}: {host}"
        )

        pagina = ler_pagina(fonte.get("url", ""))
        if pagina and pagina.get("conteudo"):
            nova = dict(fonte)
            nova["conteudo"] = pagina["conteudo"]
            if (
                not fonte.get("titulo")
                or fonte.get("titulo") == "Título indisponível"
            ) and pagina.get("titulo"):
                nova["titulo"] = pagina["titulo"]
            resultado.append(nova)
            notificar_progresso(
                ao_progresso, f"link {indice + 1}/{limite} lido: {host}"
            )
        else:
            resultado.append(fonte)
            notificar_progresso(
                ao_progresso,
                f"link {indice + 1}/{limite} indisponível: {host}",
            )

    return resultado
