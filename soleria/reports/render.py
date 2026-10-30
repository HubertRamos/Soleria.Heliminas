"""Renderização dos relatórios e do catálogo em HTML.

O conteúdo escrito pelo modelo é tratado como Markdown simples: primeiro
escapamos todo o HTML, depois aplicamos apenas a formatação que nós mesmos
geramos. Assim uma página externa não consegue injetar scripts no relatório.
"""

import html
import re
from datetime import datetime

from soleria.reports.styles import CSS as _CSS


def formatar_data(valor, com_hora=True):
    """Converte uma data ISO em algo legível; devolve o valor original se falhar."""
    if not valor:
        return ""
    try:
        data = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return str(valor)
    formato = "%d/%m/%Y às %H:%M" if com_hora else "%d/%m/%Y"
    return data.strftime(formato)


def _plural(quantidade, singular, plural):
    return f"{quantidade} {singular if quantidade == 1 else plural}"


def _escapar(texto):
    return html.escape(str(texto or ""), quote=True)


def _lista_de_dicts(valor):
    """Listas vindas de ``dados.json`` podem estar corrompidas/editadas."""
    if not isinstance(valor, list):
        return []
    return [item for item in valor if isinstance(item, dict)]


def _inline(texto, urls_permitidas=None):
    """Formata negrito, itálico, código, links seguros e citações."""
    texto = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", texto)
    texto = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", texto)
    texto = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", texto)

    def _link(match):
        rotulo, url = match.group(1), match.group(2)
        if not re.match(r"^https?://", url, re.IGNORECASE):
            return rotulo
        if urls_permitidas is not None:
            bruta = html.unescape(url)
            if bruta not in urls_permitidas:
                return rotulo
        return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{rotulo}</a>'

    texto = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        _link,
        texto,
        flags=re.IGNORECASE,
    )

    def _citacao(match):
        numeros = re.findall(r"\d+", match.group(1))
        return " ".join(
            f'<a class="citacao" href="#fonte-{numero}">[{numero}]</a>'
            for numero in numeros
        )

    # O lookbehind evita transformar de novo o texto de um link recém-criado.
    texto = re.sub(r"(?<!>)\[(\d+(?:\s*,\s*\d+)*)\]", _citacao, texto)
    return texto


def markdown_para_html(texto, urls_permitidas=None):
    """Converte um subconjunto de Markdown em HTML já escapado."""
    if not texto:
        return ""

    texto = _escapar(texto).replace("\r\n", "\n").replace("\r", "\n")
    linhas = texto.split("\n")

    saida = []
    paragrafo = []
    lista = None
    citacao = []
    codigo = None

    def inline(valor):
        return _inline(valor, urls_permitidas)

    def fechar_paragrafo():
        if paragrafo:
            saida.append("<p>" + inline(" ".join(paragrafo)) + "</p>")
            paragrafo.clear()

    def fechar_lista():
        nonlocal lista
        if lista:
            saida.append(f"</{lista}>")
            lista = None

    def fechar_citacao():
        if citacao:
            saida.append(
                "<blockquote><p>" + inline(" ".join(citacao)) + "</p></blockquote>"
            )
            citacao.clear()

    def fechar_tudo():
        fechar_paragrafo()
        fechar_lista()
        fechar_citacao()

    for linha in linhas:
        limpa = linha.strip()

        if codigo is not None:
            if limpa.startswith("```"):
                saida.append("<pre><code>" + "\n".join(codigo) + "</code></pre>")
                codigo = None
            else:
                codigo.append(linha)
            continue

        if limpa.startswith("```"):
            fechar_tudo()
            codigo = []
            continue

        if not limpa:
            fechar_tudo()
            continue

        titulo = re.match(r"^(#{1,6})\s+(.+)$", limpa)
        if titulo:
            fechar_tudo()
            # O título da seção já é um <h2>; o conteúdo começa em <h3>.
            nivel = min(6, max(3, len(titulo.group(1))))
            saida.append(f"<h{nivel}>{inline(titulo.group(2).strip())}</h{nivel}>")
            continue

        if re.match(r"^([-*_])\1{2,}$", limpa):
            fechar_tudo()
            saida.append("<hr>")
            continue

        item = re.match(r"^[-*+]\s+(.+)$", limpa)
        if item:
            fechar_paragrafo()
            fechar_citacao()
            if lista != "ul":
                fechar_lista()
                saida.append("<ul>")
                lista = "ul"
            saida.append("<li>" + inline(item.group(1)) + "</li>")
            continue

        item = re.match(r"^\d+[.)]\s+(.+)$", limpa)
        if item:
            fechar_paragrafo()
            fechar_citacao()
            if lista != "ol":
                fechar_lista()
                saida.append("<ol>")
                lista = "ol"
            saida.append("<li>" + inline(item.group(1)) + "</li>")
            continue

        citado = re.match(r"^(?:>|&gt;)\s?(.*)$", limpa)
        if citado:
            fechar_paragrafo()
            fechar_lista()
            citacao.append(citado.group(1))
            continue

        fechar_lista()
        fechar_citacao()
        paragrafo.append(limpa)

    if codigo is not None:
        saida.append("<pre><code>" + "\n".join(codigo) + "</code></pre>")
    fechar_tudo()

    return "\n".join(saida)


def _documento(titulo, corpo):
    return (
        "<!doctype html>\n"
        '<html lang="pt-BR">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_escapar(titulo)}</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        '<main class="wrap">\n'
        f"{corpo}\n"
        "</main>\n"
        "</body>\n"
        "</html>\n"
    )


def renderizar_relatorio(dados):
    """Monta o HTML de um relatório a partir do dicionário de dados."""
    dados = dados or {}
    titulo = dados.get("titulo") or "Relatório"
    resumo = dados.get("resumo") or ""
    secoes = _lista_de_dicts(dados.get("secoes"))
    fontes = _lista_de_dicts(dados.get("fontes"))
    criado = formatar_data(dados.get("criado"))
    atualizado = formatar_data(dados.get("atualizado"))

    itens_sumario = "".join(
        f'<li><a href="#secao-{i}">'
        f"{_escapar(secao.get('titulo') or 'Pesquisa')}</a></li>"
        for i, secao in enumerate(secoes, start=1)
    )
    sumario = ""
    if itens_sumario:
        sumario = (
            '<nav class="sumario" aria-label="Sumário">'
            "<h2>Neste relatório</h2>"
            f"<ol>{itens_sumario}</ol>"
            "</nav>"
        )

    blocos = []
    urls_permitidas = {str(fonte.get("url")) for fonte in fontes if fonte.get("url")}
    for i, secao in enumerate(secoes, start=1):
        titulo_secao = secao.get("titulo") or "Pesquisa"
        consulta = secao.get("consulta") or ""
        data = formatar_data(secao.get("criado"))
        meta = " · ".join(
            parte
            for parte in (
                f"Consulta: {_escapar(consulta)}" if consulta else "",
                _escapar(data) if data else "",
            )
            if parte
        )
        conteudo = markdown_para_html(
            secao.get("conteudo") or "",
            urls_permitidas=urls_permitidas,
        )
        if not conteudo:
            conteudo = (
                "<p>Esta pesquisa não trouxe detalhes suficientes para "
                "serem registrados.</p>"
            )
        blocos.append(
            f'<section class="secao" id="secao-{i}">'
            f"<h2>{_escapar(titulo_secao)}</h2>"
            f'<p class="meta">{meta}</p>'
            f"{conteudo}"
            "</section>"
        )

    if fontes:
        itens_fontes = []
        for indice, fonte in enumerate(fontes, start=1):
            # IDs novos são inteiros; relatórios antigos podem ter ids
            # ausentes ou inválidos, então a âncora cai na posição.
            identificador = fonte.get("id")
            try:
                identificador = int(identificador)
            except (TypeError, ValueError):
                identificador = indice
            titulo_fonte = (
                fonte.get("titulo") or fonte.get("dominio") or f"Fonte {indice}"
            )
            url = fonte.get("url") or ""
            dominio = fonte.get("dominio") or ""
            acessado = formatar_data(fonte.get("acessado"))
            if url:
                rotulo = (
                    f'<a href="{_escapar(url)}" target="_blank" '
                    f'rel="noopener noreferrer">'
                    f"{_escapar(titulo_fonte)}</a>"
                )
            else:
                rotulo = _escapar(titulo_fonte)
            extras = []
            if dominio:
                extras.append(f'<span class="dominio">{_escapar(dominio)}</span>')
            if acessado:
                extras.append(
                    f'<span class="acessado">acessado em {_escapar(acessado)}</span>'
                )
            itens_fontes.append(
                f'<li id="fonte-{_escapar(identificador)}">'
                f"{rotulo}{''.join(extras)}</li>"
            )
        fontes_html = '<ol class="fontes">' + "".join(itens_fontes) + "</ol>"
    else:
        fontes_html = '<p class="vazio">Nenhuma fonte registrada.</p>'

    partes_resumo = []
    if resumo:
        partes_resumo.append(
            f'<p class="resumo">{_inline(_escapar(resumo), urls_permitidas)}</p>'
        )
    if criado or atualizado:
        datas = []
        if criado:
            datas.append(f"Criado em {_escapar(criado)}")
        if atualizado and atualizado != criado:
            datas.append(f"Atualizado em {_escapar(atualizado)}")
        partes_resumo.append(f'<p class="datas">{" · ".join(datas)}</p>')
    partes_resumo.append(
        f'<p class="contagem">'
        f"{_plural(len(secoes), 'seção', 'seções')} · "
        f"{_plural(len(fontes), 'fonte', 'fontes')}</p>"
    )

    corpo = (
        '<a class="voltar" href="../index.html">← Todos os relatórios</a>'
        '<header class="capa">'
        '<p class="marca">Soleria · Relatório</p>'
        f"<h1>{_escapar(titulo)}</h1>"
        f"{''.join(partes_resumo)}"
        "</header>"
        f"{sumario}"
        f"{''.join(blocos)}"
        '<section class="secao" id="fontes">'
        "<h2>Fontes consultadas</h2>"
        f"{fontes_html}"
        "</section>"
        "<footer>Gerado pela Soleria · arquivo local, sem scripts.</footer>"
    )
    return _documento(titulo, corpo)


def renderizar_catalogo(relatorios):
    """Monta o catálogo que lista todos os relatórios."""
    relatorios = [
        item for item in (relatorios or ()) if isinstance(item, dict)
    ]
    cartoes = []
    for dados in relatorios:
        identificador = dados.get("id") or ""
        titulo = dados.get("titulo") or identificador or "Relatório"
        resumo = dados.get("resumo") or "Sem resumo."
        secoes = _lista_de_dicts(dados.get("secoes"))
        fontes = _lista_de_dicts(dados.get("fontes"))
        atualizado = formatar_data(dados.get("atualizado"))
        meta = (
            f"{_plural(len(secoes), 'seção', 'seções')} · "
            f"{_plural(len(fontes), 'fonte', 'fontes')}"
        )
        if atualizado:
            meta += f" · atualizado em {atualizado}"
        cartoes.append(
            f'<a class="cartao" href="./{_escapar(identificador)}/index.html">'
            f"<h2>{_escapar(titulo)}</h2>"
            f"<p>{_escapar(resumo)}</p>"
            f'<p class="meta">{_escapar(meta)}</p>'
            "</a>"
        )

    if cartoes:
        grade = f'<div class="grade">{"".join(cartoes)}</div>'
    else:
        grade = (
            '<p class="vazio">Ainda não há relatórios. '
            "Peça uma pesquisa para a Soleria.</p>"
        )

    corpo = (
        '<header class="capa">'
        '<p class="marca">Soleria · Relatórios</p>'
        "<h1>Relatórios</h1>"
        '<p class="resumo">Pesquisas organizadas por assunto. '
        "Cada arquivo tem o resumo, as seções e as fontes consultadas.</p>"
        f'<p class="contagem">'
        f"{_plural(len(relatorios), 'relatório', 'relatórios')}</p>"
        "</header>"
        f"{grade}"
        "<footer>Gerado pela Soleria · arquivos locais, sem scripts.</footer>"
    )
    return _documento("Relatórios da Soleria", corpo)
