"""Detecção de intenções em linguagem natural.

O modelo decide a maior parte do fluxo, mas alguns pedidos precisam ser
reconhecidos antes: "leia o relatório de X" deve consultar a memória local
em vez de disparar uma pesquisa na internet. As regras são propositalmente
simples e determinísticas.
"""

import re

from config import MAX_CARACTERES_CONSULTA


def pedido_de_leitura(texto):
    """True quando o usuário quer consultar um relatório já salvo.

    Diferente de "pesquise sobre X": aqui a intenção é lembrar de uma
    conversa anterior ou abrir um relatório existente. Por isso o fluxo de
    leitura acontece antes de qualquer pesquisa na internet.
    """
    texto = " ".join(str(texto or "").split())
    if not texto:
        return False

    minusculo = texto.casefold()
    # Pedido explícito de internet vence: o usuário quer fontes novas.
    if re.search(r"\b(?:internet|web|google)\b", minusculo):
        return False

    tem_relatorio = bool(re.search(r"\brelat[óo]rios?\b", minusculo))
    verbo_leitura = bool(
        re.search(
            r"\b(?:leia|l[êe]|ler|resuma|resumir|mostre|mostra|mostrar|"
            r"abra|abrir|consulte|consultar|recupere|recuperar|reveja|rever|"
            r"conte|contar|fale|falar|busque|buscar|busca|procure|procurar|"
            r"procura)\b",
            minusculo,
        )
    )

    # "procure sobre relatórios financeiros" é uma pesquisa na web sobre
    # relatórios, não um pedido para ler um relatório salvo.
    if re.search(
        r"\b(?:procura|procure|procurar|busca|busque|buscar)\b\s+"
        r"(?:sobre|a respeito de|acerca de)\s+"
        r"(?:relat[óo]rios\b|(?:os|as)\s+relat[óo]rios\b)",
        minusculo,
    ):
        return False

    if tem_relatorio and verbo_leitura:
        return True
    if tem_relatorio and re.search(
        r"\b(?:o que|qual|quais|conte[úu]do|tem|h[áa]|existe|existem)\b",
        minusculo,
    ):
        return True

    if re.search(
        r"\b(?:lembra|lembras|recorda|recordas|recordar)\b", minusculo
    ):
        if re.search(
            r"\b(?:a gente|n[óo]s|conversamos|falamos|discutimos|tratamos|"
            r"falou|conversou|relat[óo]rio)\b",
            minusculo,
        ):
            return True

    if re.search(
        r"\b(?:aquela vez|daquela vez|naquela vez|a vez que|outra vez|"
        r"anteriormente)\b",
        minusculo,
    ):
        if re.search(
            r"\b(?:falamos|conversamos|discutimos|tratamos|falou|conversou|"
            r"discutiu|tratou|falei|contei|contou|falando|conversando|"
            r"discutindo|tratando|pesquisamos|pesquisando|estava|estavamos|"
            r"est[áa]vamos)\b",
            minusculo,
        ):
            return True

    if re.search(
        r"\b(?:o que|sobre o que|do que)\b", minusculo
    ) and re.search(r"\b(?:a gente|n[óo]s)\b", minusculo):
        if re.search(
            r"\b(?:falamos|conversamos|discutimos|tratamos|falou|conversou|"
            r"discutiu|tratou|falando|conversando|discutindo|tratando)\b",
            minusculo,
        ):
            return True

    if re.search(
        r"\b(?:assunto|conversa|relat[óo]rio)\b", minusculo
    ) and re.search(r"\b(?:a gente|n[óo]s)\b", minusculo):
        if re.search(
            r"\b(?:falamos|conversamos|discutimos|tratamos|falou|conversou|"
            r"discutiu|tratou)\b",
            minusculo,
        ):
            return True

    if re.search(
        r"\b(?:procura|procure|procurar|busca|busque|buscar)\b", minusculo
    ):
        if re.search(
            r"\b(?:aquela vez|a gente|n[óo]s|conversamos|falamos|"
            r"discutimos|relat[óo]rio|aquele assunto|aquela conversa|"
            r"aquilo)\b",
            minusculo,
        ):
            return True

    return False


def assunto_da_lembranca(texto):
    """Isola o tema de um pedido de lembrança.

    "procura sobre aquela vez que falamos de energia solar" vira
    "energia solar"; "leia o relatório de custos" vira "custos".
    """
    limpo = " ".join(str(texto or "").split())
    limpo = re.sub(
        r"^(?:soleria|ei|oi|ol[áa]|por favor)[,:\s]+",
        "",
        limpo,
        flags=re.IGNORECASE,
    )

    padroes = (
        r"\brelat[óo]rios?\s+(?:sobre|a respeito de|acerca de|de|do|da)\s+"
        r"(.+)$",
        r"\b(?:falando|conversando|discutindo|tratando|falamos|conversamos|"
        r"discutimos|tratamos|falou|conversou|discutiu|tratou|falei|contei|"
        r"contou|pesquisamos|pesquisando)\b.*?\b(?:sobre|a respeito de|"
        r"acerca de|de|do|da)\s+(.+)$",
        r"\b(?:lembra|lembras|recorda|recordas)\b.*?\b(?:sobre|a respeito de|"
        r"acerca de|de|do|da)\s+(.+)$",
        r"\b(?:procura|procure|procurar|busca|busque|buscar)\b.*?\b"
        r"(?:sobre|a respeito de|acerca de|de|do|da)\s+(.+)$",
        r"\b(?:sobre|a respeito de|acerca de)\s+(.+)$",
        r"\brelat[óo]rios?\s+(.+)$",
    )
    for padrao in padroes:
        encontrado = re.search(padrao, limpo, re.IGNORECASE | re.DOTALL)
        if not encontrado:
            continue
        assunto = encontrado.group(1).strip(" .,;:!?\"'")
        assunto = re.sub(r"\s+", " ", assunto)
        # "aquele assunto que a gente conversou" -> "aquele assunto".
        assunto = re.sub(
            r"\s+que\s+(?:a gente|n[óo]s|eu|voc[êe])\b.*$",
            "",
            assunto,
            flags=re.IGNORECASE,
        ).strip()
        assunto = re.sub(
            r"^(?:(?:o|a|os|as|um|uma|uns|umas)\b\s*)+",
            "",
            assunto,
            flags=re.IGNORECASE,
        ).strip()
        if assunto:
            return assunto[:MAX_CARACTERES_CONSULTA]

    resto = re.sub(
        r"\b(?:soleria|ei|oi|ol[áa]|por favor|me|voc[êe]|pode|poderia|"
        r"quero|gostaria|leia|l[êe]|ler|resuma|resumir|mostre|mostra|mostrar|"
        r"abra|abrir|consulte|consultar|recupere|recuperar|reveja|rever|"
        r"conte|contar|fale|falar|busque|buscar|busca|procure|procurar|"
        r"procura|relat[óo]rios?|aquela|aquele|daquela|naquela|vez|que|"
        r"a gente|n[óo]s|estava|estavamos|est[áa]vamos|falando|conversando|"
        r"discutindo|tratando|falamos|conversamos|discutimos|tratamos|"
        r"falou|conversou|discutiu|tratou|falei|contei|contou|pesquisou|"
        r"sobre|a respeito de|"
        r"acerca de|de|do|da|dos|das)\b",
        " ",
        limpo,
        flags=re.IGNORECASE,
    )
    resto = re.sub(r"\s+", " ", resto).strip(" .,;:!?\"'")
    resto = re.sub(
        r"^(?:(?:o|a|os|as|um|uma|uns|umas|de|do|da|dos|das|sobre|que)\b\s*)+",
        "",
        resto,
        flags=re.IGNORECASE,
    ).strip()
    return resto[:MAX_CARACTERES_CONSULTA]


_pedido_de_leitura = pedido_de_leitura
_assunto_da_lembranca = assunto_da_lembranca
