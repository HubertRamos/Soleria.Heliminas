"""Formatação de relatórios para os prompts do modelo.

Nada aqui escreve em disco: são apenas representações compactas de um
relatório ou de seus candidatos, respeitando um orçamento de caracteres.
"""

from soleria.reports.text import texto_curto


def formatar_candidatos(candidatos, compacto=False):
    """Resumo dos candidatos para o prompt do modelo.

    No modo ``compacto`` o bloco fica curto o bastante para caber no
    contexto reduzido do modelo local.
    """
    if not candidatos:
        return "Nenhum relatório parecido."

    blocos = []
    for pontuacao, relatorio in candidatos:
        if compacto:
            blocos.append(
                f"- id: {relatorio.id} | "
                f"título: {texto_curto(relatorio.titulo, limite=60)} | "
                f"resumo: {texto_curto(relatorio.resumo, limite=110)} | "
                f"similaridade: {pontuacao:.2f}"
            )
            continue

        secoes = [
            texto_curto(str(secao.get("titulo") or ""), limite=80)
            for secao in relatorio.secoes[:6]
            if isinstance(secao, dict) and secao.get("titulo")
        ]
        dominios = sorted(relatorio.dominios())[:5]
        blocos.append(
            f"- id: {relatorio.id}\n"
            f"  título: {texto_curto(relatorio.titulo, limite=100)}\n"
            f"  resumo: {texto_curto(relatorio.resumo, limite=240)}\n"
            f"  seções: {', '.join(secoes) or '—'}\n"
            f"  domínios: {', '.join(dominios) or '—'}\n"
            f"  similaridade: {pontuacao:.2f}"
        )
    return "\n".join(blocos)


def formatar_relatorio(relatorio, limite=None):
    """Conteúdo de um relatório para o modelo ler, dentro de um orçamento.

    Inclui o corpo das seções (não só os títulos) e as fontes, porque o
    objetivo aqui é responder a uma pergunta sobre o que já foi salvo.
    """
    limite = max(400, int(limite or 2400))
    partes = []
    restante = limite

    def adicionar(texto):
        nonlocal restante
        if not texto or restante <= 0:
            return False
        if len(texto) > restante:
            partes.append(texto[: max(0, restante - 1)].rstrip() + "…")
            restante = 0
            return False
        partes.append(texto)
        restante -= len(texto)
        return True

    adicionar(f"Relatório: {texto_curto(relatorio.titulo, limite=120)}\n")
    adicionar(f"Resumo: {texto_curto(relatorio.resumo, limite=500) or '—'}\n")

    if relatorio.secoes:
        adicionar("\nSeções:\n")
        for secao in relatorio.secoes:
            if not isinstance(secao, dict):
                continue
            titulo = texto_curto(str(secao.get("titulo") or ""), limite=100)
            conteudo = str(secao.get("conteudo") or "").strip()
            if not adicionar(f"\n## {titulo or 'Seção'}\n"):
                break
            if not adicionar(conteudo + "\n"):
                break
    else:
        adicionar("\nSem seções registradas.\n")

    if relatorio.fontes and restante > 0:
        adicionar("\nFontes:\n")
        for indice, fonte in enumerate(relatorio.fontes, start=1):
            if not isinstance(fonte, dict):
                continue
            # O rótulo precisa casar com as citações [n] do corpo.
            identificador = fonte.get("id")
            try:
                identificador = int(identificador)
            except (TypeError, ValueError):
                identificador = indice
            titulo = texto_curto(str(fonte.get("titulo") or ""), limite=100)
            url = str(fonte.get("url") or "")
            linha = f"[{identificador}] {titulo or url}"
            if url and url != titulo:
                linha += f" — {url}"
            if not adicionar(linha + "\n"):
                break

    return "".join(partes).strip()
