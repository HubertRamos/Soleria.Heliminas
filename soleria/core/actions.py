"""Ações locais disparadas por linguagem natural.

Pedidos como "abre o Firefox no YouTube" ou "abre o VS Code na pasta
~/projetos" são reconhecidos antes de o modelo ser acionado. O módulo só
conhece aplicativos de uma lista fixa (que pode ser ampliada com
``SOLERIA_APPS``): nada de shell livre, para que uma frase ambígua não vire
execução de comandos arbitrários.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import unicodedata
import webbrowser
from dataclasses import dataclass

from config import APLICATIVOS_PERSONALIZADOS
from soleria.logging_utils import log_erro, log_evento

# Verbos aceitos no começo do pedido. A checagem é feita só nas primeiras
# palavras para não transformar uma conversa sobre aplicativos em ação.
_VERBOS = {
    "abre",
    "abra",
    "abrir",
    "abres",
    "inicia",
    "inicie",
    "iniciar",
    "executa",
    "execute",
    "executar",
    "lanca",
    "lance",
    "lancar",
    "roda",
    "rode",
    "rodar",
    "carrega",
    "carregue",
    "carregar",
    "entra",
    "entre",
    "entrar",
}
_MAX_PALAVRAS_VERBO = 6

_SAUDACAO = re.compile(
    r"^\s*(?:(?:soleria|ei|oi|ol[aá]|por favor)\b[\s,.:;!?\-–—]*)+",
    re.IGNORECASE,
)

_URL = re.compile(r"\bhttps?://[^\s<>\"']+", re.IGNORECASE)
_DOMINIO = re.compile(
    r"(?<![\w@.-])(?:www\.)?"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,}(?:/[^\s<>\"']*)?",
    re.IGNORECASE,
)

# Caminhos com ~, ./, ../ ou /. Espaços só são aceitos entre aspas.
_CAMINHO_INICIO = re.compile(r"""(?<![\w])(?:~|\.{1,2})?/[^\s"'<>|]+""")
_CAMINHO_RELATIVO = re.compile(
    r"""(?<![\w/])(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+/?"""
)
_CAMINHO_ASPAS = re.compile(r"""["']([^"'\n]+)["']""")

_EXTENSOES_ARQUIVO = {
    "bmp",
    "css",
    "csv",
    "doc",
    "docx",
    "gif",
    "gz",
    "html",
    "jpeg",
    "jpg",
    "js",
    "json",
    "kra",
    "log",
    "md",
    "mkv",
    "mov",
    "mp3",
    "mp4",
    "odp",
    "ods",
    "odt",
    "ogg",
    "pdf",
    "png",
    "ppt",
    "pptx",
    "psd",
    "py",
    "rar",
    "sh",
    "svg",
    "tar",
    "tif",
    "tiff",
    "ts",
    "tsx",
    "txt",
    "wav",
    "webm",
    "webp",
    "xcf",
    "xls",
    "xlsx",
    "xml",
    "zip",
}
_ARQUIVO_SOLTO = re.compile(
    r"(?<![\w/.-])([A-Za-z0-9_.-]+\.(?:"
    + "|".join(sorted(_EXTENSOES_ARQUIVO, key=len, reverse=True))
    + r"))\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Site:
    chave: str
    rotulo: str
    aliases: tuple[str, ...]
    url: str


@dataclass(frozen=True)
class Aplicativo:
    chave: str
    rotulo: str
    aliases: tuple[str, ...]
    executaveis: tuple[str, ...]
    # Editores de terminal precisam ser abertos dentro de um emulador.
    terminal: bool = False
    # Alternativas de terminal usadas quando nenhum executável gráfico
    # da lista principal está instalado.
    alternativas_terminal: tuple[str, ...] = ()


@dataclass(frozen=True)
class PedidoAcao:
    aplicativo: Aplicativo | None = None
    site: Site | None = None
    url: str | None = None
    caminho: str | None = None

    @property
    def alvo(self):
        return self.url or self.caminho


SITES = (
    Site(
        "youtube",
        "YouTube",
        ("youtube", "you tube"),
        "https://www.youtube.com",
    ),
    Site(
        "google-maps",
        "Google Maps",
        ("google maps", "google-maps", "maps google"),
        "https://maps.google.com",
    ),
    Site("google", "Google", ("google",), "https://www.google.com"),
    Site("gmail", "Gmail", ("gmail",), "https://mail.google.com"),
    Site("github", "GitHub", ("github",), "https://github.com"),
    Site("gitlab", "GitLab", ("gitlab",), "https://gitlab.com"),
    Site(
        "wikipedia",
        "Wikipédia",
        ("wikipedia", "wikipédia", "wiki"),
        "https://pt.wikipedia.org",
    ),
    Site(
        "whatsapp",
        "WhatsApp",
        ("whatsapp", "whats app"),
        "https://web.whatsapp.com",
    ),
    Site(
        "instagram",
        "Instagram",
        ("instagram", "insta"),
        "https://www.instagram.com",
    ),
    Site(
        "facebook",
        "Facebook",
        ("facebook", "face"),
        "https://www.facebook.com",
    ),
    Site("twitter", "Twitter", ("twitter",), "https://twitter.com"),
    Site("x", "X", ("x.com",), "https://x.com"),
    Site("netflix", "Netflix", ("netflix",), "https://www.netflix.com"),
    Site("spotify", "Spotify", ("spotify",), "https://open.spotify.com"),
    Site("twitch", "Twitch", ("twitch",), "https://www.twitch.tv"),
    Site("reddit", "Reddit", ("reddit",), "https://www.reddit.com"),
    Site("linkedin", "LinkedIn", ("linkedin",), "https://www.linkedin.com"),
    Site(
        "chatgpt",
        "ChatGPT",
        ("chatgpt", "chat gpt"),
        "https://chatgpt.com",
    ),
    Site(
        "duckduckgo",
        "DuckDuckGo",
        ("duckduckgo",),
        "https://duckduckgo.com",
    ),
)

_APLICATIVOS_PADRAO = (
    Aplicativo(
        "firefox-dev",
        "Firefox Developer Edition",
        ("firefox developer edition", "firefox developer", "firefox dev"),
        ("firefox-developer-edition", "firefox-developer-edition-bin"),
    ),
    Aplicativo(
        "firefox",
        "Firefox",
        ("firefox", "mozilla firefox", "mozilla"),
        ("firefox", "firefox-bin"),
    ),
    Aplicativo(
        "chrome",
        "Google Chrome",
        ("google chrome", "chrome", "google-chrome"),
        ("google-chrome-stable", "google-chrome"),
    ),
    Aplicativo(
        "chromium",
        "Chromium",
        ("chromium",),
        ("chromium", "chromium-browser"),
    ),
    Aplicativo(
        "brave",
        "Brave",
        ("brave browser", "brave"),
        ("brave-browser", "brave"),
    ),
    Aplicativo(
        "edge",
        "Microsoft Edge",
        ("microsoft edge", "edge"),
        ("microsoft-edge-stable", "microsoft-edge"),
    ),
    Aplicativo("opera", "Opera", ("opera",), ("opera",)),
    Aplicativo(
        "vivaldi",
        "Vivaldi",
        ("vivaldi",),
        ("vivaldi", "vivaldi-stable"),
    ),
    Aplicativo(
        "editor",
        "editor de código",
        ("editor de codigo", "editor", "codigo"),
        (
            "code",
            "code-oss",
            "codium",
            "cursor",
            "zed",
            "subl",
            "sublime_text",
            "kate",
            "gedit",
            "geany",
            "atom",
        ),
        alternativas_terminal=("nvim", "vim", "micro", "hx", "nano"),
    ),
    Aplicativo(
        "nvim",
        "Neovim",
        ("neovim", "nvim"),
        ("nvim",),
        terminal=True,
    ),
    Aplicativo(
        "vim",
        "Vim",
        ("vim",),
        ("vim",),
        terminal=True,
    ),
    Aplicativo(
        "micro",
        "micro",
        ("micro",),
        ("micro",),
        terminal=True,
    ),
    Aplicativo(
        "nano",
        "nano",
        ("nano",),
        ("nano",),
        terminal=True,
    ),
    Aplicativo(
        "helix",
        "Helix",
        ("helix", "hx"),
        ("hx", "helix"),
        terminal=True,
    ),
    Aplicativo(
        "vscode",
        "VS Code",
        ("visual studio code", "vs code", "vscode", "codigo", "code"),
        ("code", "code-oss"),
    ),
    Aplicativo(
        "vscodium",
        "VSCodium",
        ("vscodium",),
        ("codium", "vscodium"),
    ),
    Aplicativo("cursor", "Cursor", ("cursor",), ("cursor",)),
    Aplicativo("zed", "Zed", ("zed",), ("zed",)),
    Aplicativo(
        "sublime",
        "Sublime Text",
        ("sublime text", "sublime", "subl"),
        ("subl", "sublime_text"),
    ),
    Aplicativo("kate", "Kate", ("kate",), ("kate",)),
    Aplicativo("gedit", "gedit", ("gedit",), ("gedit",)),
    Aplicativo("geany", "Geany", ("geany",), ("geany",)),
    Aplicativo("atom", "Atom", ("atom",), ("atom",)),
    Aplicativo(
        "pycharm",
        "PyCharm",
        ("pycharm",),
        ("pycharm", "pycharm-professional", "pycharm-community"),
    ),
    Aplicativo(
        "intellij",
        "IntelliJ IDEA",
        ("intellij idea", "intellij", "idea"),
        ("idea", "idea.sh"),
    ),
    Aplicativo(
        "android-studio",
        "Android Studio",
        ("android studio",),
        ("android-studio", "studio.sh"),
    ),
    Aplicativo(
        "gerenciador",
        "Gerenciador de Arquivos",
        (
            "gerenciador de arquivos",
            "gerenciador",
            "explorador de arquivos",
            "explorador",
            "arquivos",
        ),
        (
            "nautilus",
            "dolphin",
            "thunar",
            "nemo",
            "pcmanfm-qt",
            "pcmanfm",
            "caja",
            "xdg-open",
        ),
    ),
    Aplicativo("nautilus", "Nautilus", ("nautilus",), ("nautilus",)),
    Aplicativo("dolphin", "Dolphin", ("dolphin",), ("dolphin",)),
    Aplicativo("thunar", "Thunar", ("thunar",), ("thunar",)),
    Aplicativo("nemo", "Nemo", ("nemo",), ("nemo",)),
    Aplicativo(
        "pcmanfm",
        "PCManFM",
        ("pcmanfm",),
        ("pcmanfm", "pcmanfm-qt"),
    ),
    Aplicativo("caja", "Caja", ("caja",), ("caja",)),
    Aplicativo(
        "gimp",
        "GIMP",
        ("gimp", "gimp 2"),
        ("gimp", "gimp-2.10"),
    ),
    Aplicativo("krita", "Krita", ("krita",), ("krita",)),
    Aplicativo("inkscape", "Inkscape", ("inkscape",), ("inkscape",)),
    Aplicativo("pinta", "Pinta", ("pinta",), ("pinta",)),
    Aplicativo(
        "navegador",
        "navegador padrão",
        ("navegador", "navegador padrao", "browser"),
        (),
    ),
)

_MSG_DESLIGADO = (
    "As ações no sistema estão desligadas. Ligue em F2 › Abrir aplicativos."
)

# Emuladores de terminal, do mais provável ao menos comum. O comando do
# editor é acrescentado depois das opções de execução de cada um.
_TERMINAIS = (
    ("kitty", ()),
    ("alacritty", ("-e",)),
    ("foot", ()),
    ("ghostty", ("-e",)),
    ("wezterm", ("start", "--")),
    ("gnome-terminal", ("--",)),
    ("konsole", ("-e",)),
    ("xfce4-terminal", ("-x",)),
    ("terminator", ("-x",)),
    ("tilix", ("-e",)),
    ("xterm", ("-e",)),
    ("urxvt", ("-e",)),
    ("st", ("-e",)),
)


def _dobrar(texto):
    """Minúsculas sem acentos, para comparar frases e aliases."""
    decomposto = unicodedata.normalize("NFD", str(texto or "").casefold())
    return "".join(
        caractere
        for caractere in decomposto
        if unicodedata.category(caractere) != "Mn"
    )


def _aplicativos_personalizados(bruto):
    """Converte ``alias=executável`` em aplicativos extras."""
    itens = []
    vistos = set()
    for parte in re.split(r"[;,]", str(bruto or "")):
        if "=" not in parte:
            continue
        alias, executavel = (item.strip() for item in parte.split("=", 1))
        if not alias or not executavel:
            continue
        chave = f"personalizado:{_dobrar(alias)}"
        if chave in vistos:
            continue
        vistos.add(chave)
        itens.append(
            Aplicativo(
                chave,
                alias[:1].upper() + alias[1:],
                (_dobrar(alias),),
                (executavel,),
            )
        )
    return tuple(itens)


APLICATIVOS = _APLICATIVOS_PADRAO + _aplicativos_personalizados(
    APLICATIVOS_PERSONALIZADOS
)


def _limpar_texto(texto):
    return " ".join(str(texto or "").split())


def _tem_verbo(texto):
    palavras = re.findall(r"[a-z0-9]+", texto)
    return any(
        palavra in _VERBOS
        for palavra in palavras[:_MAX_PALAVRAS_VERBO]
    )


def _primeiro_alias(texto, itens):
    """Alias que aparece primeiro; em empate, o mais longo vence."""
    melhor = None
    for item in itens:
        for alias in item.aliases:
            encontrado = re.search(
                rf"(?<![\w-]){re.escape(alias)}(?![\w-])", texto
            )
            if encontrado is None:
                continue
            posicao = (encontrado.start(), -len(alias))
            if melhor is None or posicao < melhor[0]:
                melhor = (posicao, item, encontrado)
    if melhor is None:
        return None, None
    return melhor[1], melhor[2]


def _parece_arquivo(texto):
    base = texto.rsplit("/", 1)[-1]
    if "." not in base:
        return False
    return base.rsplit(".", 1)[-1].casefold() in _EXTENSOES_ARQUIVO


def _parece_site(texto):
    host = texto.split("/", 1)[0]
    if "." not in host:
        return False
    tld = host.rsplit(".", 1)[-1].casefold()
    return tld not in _EXTENSOES_ARQUIVO


def _extrair_alvo(texto):
    """Separa o destino do pedido: URL, caminho ou nenhum.

    Devolve ``(url, caminho, inicio, fim)``.
    """
    encontrado = _URL.search(texto)
    if encontrado is not None:
        bruta = encontrado.group(0).rstrip(".,;:!?)]}'\"")
        return bruta, None, encontrado.start(), encontrado.end()

    encontrado = _CAMINHO_ASPAS.search(texto)
    if encontrado is not None:
        valor = encontrado.group(1).strip()
        if _URL.fullmatch(valor):
            return valor, None, encontrado.start(), encontrado.end()
        if valor:
            return None, valor, encontrado.start(), encontrado.end()

    for encontrado in (_CAMINHO_INICIO.search(texto),):
        if encontrado is not None:
            valor = encontrado.group(0).rstrip(".,;:!?)]}'\"")
            if valor:
                return None, valor, encontrado.start(), encontrado.end()

    for encontrado in _DOMINIO.finditer(texto):
        bruta = encontrado.group(0).rstrip(".,;:!?)]}'\"")
        if _parece_site(bruta):
            return (
                f"https://{bruta}",
                None,
                encontrado.start(),
                encontrado.end(),
            )

    encontrado = _CAMINHO_RELATIVO.search(texto)
    if encontrado is not None:
        valor = encontrado.group(0).rstrip(".,;:!?)]}'\"")
        if valor:
            return None, valor, encontrado.start(), encontrado.end()

    encontrado = _ARQUIVO_SOLTO.search(texto)
    if encontrado is not None:
        valor = encontrado.group(1)
        return None, valor, encontrado.start(), encontrado.end()

    return None, None, None, None


def _sem_span(texto, inicio, fim):
    return f"{texto[:inicio]} {texto[fim:]}".strip()


def detectar_pedido(texto):
    """Reconhece um pedido de abrir aplicativo, site ou caminho.

    Devolve :class:`PedidoAcao` ou ``None``. Pedidos sobre relatórios são
    ignorados aqui: eles pertencem ao fluxo de leitura da Soleria.
    """
    limpo = _SAUDACAO.sub("", _limpar_texto(texto))
    if not limpo:
        return None

    dobrado = _dobrar(limpo)
    if not _tem_verbo(dobrado):
        return None
    if re.search(r"\brelat[oó]rios?\b", dobrado):
        return None

    url, caminho, inicio, fim = _extrair_alvo(limpo)
    trabalho = (
        _sem_span(limpo, inicio, fim)
        if (url is not None or caminho is not None)
        else limpo
    )
    trabalho = _dobrar(trabalho)

    aplicativo, encontrado = _primeiro_alias(trabalho, APLICATIVOS)
    if encontrado is not None:
        trabalho = _sem_span(
            trabalho, encontrado.start(), encontrado.end()
        )

    site = None
    if url is None and caminho is None:
        site, encontrado = _primeiro_alias(trabalho, SITES)
        if encontrado is not None:
            url = site.url

    if aplicativo is None and url is None and caminho is None:
        return None
    return PedidoAcao(
        aplicativo=aplicativo,
        site=site,
        url=url,
        caminho=caminho,
    )


def _resolver_comando(aplicativo):
    return _resolver_primeiro(aplicativo.executaveis)


def _resolver_primeiro(executaveis):
    for linha in executaveis:
        try:
            partes = shlex.split(linha)
        except ValueError:
            continue
        if not partes:
            continue
        caminho = shutil.which(partes[0])
        if caminho:
            return (caminho, *partes[1:])
    return None


def _resolver_terminal():
    for nome, opcoes in _TERMINAIS:
        caminho = shutil.which(nome)
        if caminho:
            return (caminho, *opcoes)
    return None


def _caminho_expandido(caminho):
    return os.path.expandvars(os.path.expanduser(str(caminho)))


def _abrir_programa(comando, alvo=None, cwd=None):
    if isinstance(comando, str):
        comando = (comando,)
    argumentos = list(comando)
    if alvo:
        argumentos.append(alvo)
    try:
        subprocess.Popen(
            argumentos,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
            cwd=cwd,
        )
        return True
    except (OSError, subprocess.SubprocessError) as erro:
        log_erro(erro)
        return False


def _abrir_no_navegador(url):
    try:
        return bool(webbrowser.open(url, new=2))
    except Exception as erro:
        log_erro(erro)
        return False


def _abrir_com_xdg_open(caminho):
    executavel = shutil.which("xdg-open")
    if not executavel:
        return False
    return _abrir_programa((executavel,), caminho)


def _abrir_no_terminal(pedido, aplicativo, editor, caminho):
    """Abre um editor de terminal já no diretório pedido."""
    terminal = _resolver_terminal()
    if terminal is None:
        return (
            f"Não encontrei um terminal instalado para abrir o "
            f"{aplicativo.rotulo}."
        )

    argumentos = list(terminal) + list(editor)
    cwd = os.path.expanduser("~")
    if caminho:
        if os.path.isdir(caminho):
            cwd = caminho
        else:
            cwd = os.path.dirname(caminho) or cwd
            argumentos.append(os.path.abspath(caminho))

    log_evento(
        f"Ação: abrindo {aplicativo.rotulo} no terminal em {cwd}"
    )
    if _abrir_programa(argumentos, cwd=cwd):
        return _mensagem_sucesso(pedido, aplicativo)
    return (
        f"Não consegui abrir o {aplicativo.rotulo}. "
        "Os detalhes estão no log."
    )


def _destino(pedido):
    if pedido.site is not None:
        return f"o {pedido.site.rotulo}"
    if pedido.caminho:
        return f"o caminho {pedido.caminho}"
    if pedido.url:
        return pedido.url
    return "o link"


def _mensagem_sucesso(pedido, aplicativo):
    if aplicativo is not None and aplicativo.chave != "navegador":
        navegador = f"o {aplicativo.rotulo}"
    else:
        navegador = "o navegador padrão"
    if pedido.site is not None:
        return f"Abri {navegador} no {pedido.site.rotulo}."
    if pedido.caminho:
        return f"Abri {navegador} em {pedido.caminho}."
    if pedido.url:
        return f"Abri {navegador} em {pedido.url}."
    return f"Abri {navegador}."


def _resolver_alvo(pedido, aplicativo):
    """Devolve o argumento a passar ao aplicativo, já expandido."""
    if pedido.caminho:
        return _caminho_expandido(pedido.caminho)
    if pedido.url:
        return pedido.url
    if aplicativo is not None and aplicativo.chave == "gerenciador":
        return os.path.expanduser("~")
    return None


def executar(pedido, ativo=True):
    """Executa o pedido reconhecido e devolve a mensagem para o chat."""
    if pedido is None:
        return None
    if not ativo:
        return _MSG_DESLIGADO

    caminho = (
        _caminho_expandido(pedido.caminho) if pedido.caminho else None
    )
    if caminho is not None and not os.path.exists(caminho):
        return f"Não encontrei o caminho {pedido.caminho}."

    aplicativo = pedido.aplicativo
    if aplicativo is None or aplicativo.chave == "navegador":
        if pedido.url and _abrir_no_navegador(pedido.url):
            log_evento(f"Ação: abrindo {pedido.url} no navegador padrão")
            return _mensagem_sucesso(pedido, aplicativo)
        if caminho and _abrir_com_xdg_open(caminho):
            log_evento(f"Ação: abrindo {caminho} no aplicativo padrão")
            return _mensagem_sucesso(pedido, aplicativo)
        if pedido.url or caminho:
            return (
                f"Não consegui abrir {_destino(pedido)} no aplicativo "
                "padrão. Os detalhes estão no log."
            )
        return "Não consegui abrir o navegador padrão."

    if aplicativo.terminal:
        editor = _resolver_comando(aplicativo)
        if editor is None:
            return f"Não encontrei o {aplicativo.rotulo} instalado."
        return _abrir_no_terminal(pedido, aplicativo, editor, caminho)

    alvo = _resolver_alvo(pedido, aplicativo)
    comando = _resolver_comando(aplicativo)
    if comando is None and aplicativo.alternativas_terminal:
        editor = _resolver_primeiro(
            aplicativo.alternativas_terminal
        )
        if editor is not None:
            return _abrir_no_terminal(
                pedido, aplicativo, editor, caminho
            )
    if comando is None:
        if caminho and _abrir_com_xdg_open(caminho):
            log_evento(
                f"Ação: {aplicativo.rotulo} ausente; abrindo o caminho no "
                "aplicativo padrão"
            )
            return (
                f"Não encontrei o {aplicativo.rotulo} instalado; "
                f"abri {_destino(pedido)} no aplicativo padrão."
            )
        if pedido.url and _abrir_no_navegador(pedido.url):
            log_evento(
                f"Ação: {aplicativo.rotulo} ausente; abrindo o link no "
                "navegador padrão"
            )
            return (
                f"Não encontrei o {aplicativo.rotulo} instalado; "
                f"abri {_destino(pedido)} no navegador padrão."
            )
        return f"Não encontrei o {aplicativo.rotulo} instalado."

    log_evento(
        f"Ação: abrindo {aplicativo.rotulo}"
        + (f" em {alvo}" if alvo else "")
    )
    if _abrir_programa(comando, alvo):
        return _mensagem_sucesso(pedido, aplicativo)

    if caminho and _abrir_com_xdg_open(caminho):
        return (
            f"Não consegui abrir o {aplicativo.rotulo}; "
            f"abri {_destino(pedido)} no aplicativo padrão."
        )
    if pedido.url and _abrir_no_navegador(pedido.url):
        return (
            f"Não consegui abrir o {aplicativo.rotulo}; "
            f"abri {_destino(pedido)} no navegador padrão."
        )
    return (
        f"Não consegui abrir o {aplicativo.rotulo}. "
        "Os detalhes estão no log."
    )


__all__ = [
    "APLICATIVOS",
    "SITES",
    "Aplicativo",
    "PedidoAcao",
    "Site",
    "detectar_pedido",
    "executar",
]
