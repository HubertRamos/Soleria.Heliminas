"""Comandos internos trocados entre o modelo e o Python.

O modelo devolve marcadores como ``[[PESQUISAR: ...]]``; este módulo é o
único lugar que conhece a sintaxe deles. Nada aqui depende da UI, do
servidor ou do repositório de relatórios.
"""

import re

from config import MAX_CARACTERES_CONSULTA, MAX_CARACTERES_PERGUNTA

PADRAO_PESQUISA = re.compile(
    r"\[\[\s*PESQUISAR\s*:\s*(.*?)\s*\]\]", re.IGNORECASE | re.DOTALL
)
PADRAO_PERGUNTA = re.compile(
    r"\[\[\s*PERGUNTAR\s*:\s*(.*?)\s*\]\]", re.IGNORECASE | re.DOTALL
)
PADRAO_RELATORIO = re.compile(
    r"\[\[\s*RELAT[ÓO]RIO\s*:\s*(.*?)\s*\]\]",
    re.IGNORECASE | re.DOTALL,
)
PADRAO_NOVO = re.compile(
    r"\[\[\s*NOVO\s*:\s*(.*?)\s*\]\]", re.IGNORECASE | re.DOTALL
)

# Verbos que indicam um pedido explícito de pesquisa. Nesse caso não
# aceitamos uma resposta direta do modelo: ele pode saber a resposta, mas o
# usuário pediu fontes e um relatório.
PADRAO_PEDIDO_PESQUISA = re.compile(
    r"\b(?:pesquis(?:e|ar|a|ou)|procur(?:e|ar|a|ou)|"
    r"busc(?:e|ar|a|ou)|consult(?:e|ar|a|ou)|"
    r"verific(?:e|ar|a|ou)|confir(?:a|ir|ou))\b",
    re.IGNORECASE,
)


def _normalizar_comando(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def extrair_consulta(texto):
    """Extrai e normaliza o comando de pesquisa, se existir."""
    match = PADRAO_PESQUISA.search(texto or "")
    if not match:
        return None
    consulta = _normalizar_comando(match.group(1))
    if not consulta:
        return None
    return consulta[:MAX_CARACTERES_CONSULTA]


def extrair_pergunta(texto):
    """Extrai e normaliza o comando de esclarecimento, se existir."""
    match = PADRAO_PERGUNTA.search(texto or "")
    if not match:
        return None
    pergunta = _normalizar_comando(match.group(1))
    if not pergunta:
        return None
    return pergunta[:MAX_CARACTERES_PERGUNTA]


def extrair_relatorio(texto):
    """Extrai o id do relatório que o modelo escolheu atualizar."""
    match = PADRAO_RELATORIO.search(texto or "")
    if not match:
        return None
    identificador = _normalizar_comando(match.group(1)).strip("`'\"")
    return identificador[:120] or None


def extrair_novo(texto):
    """Extrai o título do relatório novo que o modelo propôs."""
    match = PADRAO_NOVO.search(texto or "")
    if not match:
        return None
    titulo = _normalizar_comando(match.group(1)).strip("`'\"")
    return titulo[:100] or None


def limpar_comandos(texto):
    """Remove comandos internos que não devem chegar ao usuário."""
    texto = PADRAO_PESQUISA.sub("", texto or "")
    texto = PADRAO_PERGUNTA.sub("", texto)
    texto = PADRAO_RELATORIO.sub("", texto)
    texto = PADRAO_NOVO.sub("", texto)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def ultima_mensagem_usuario(mensagens):
    """Texto da última mensagem do usuário, ou string vazia."""
    for mensagem in reversed(list(mensagens or [])):
        if mensagem.get("role") == "user":
            return str(mensagem.get("content") or "").strip()
    return ""


def pedido_explicito_de_pesquisa(mensagens):
    """True quando o usuário mandou pesquisar, buscar, verificar etc."""
    return bool(
        PADRAO_PEDIDO_PESQUISA.search(ultima_mensagem_usuario(mensagens))
    )


def consulta_do_pedido(texto):
    """Transforma "pesquise sobre X na internet" em uma consulta "X"."""
    consulta = re.sub(
        r"^\s*(?:por favor[, ]*)?", "", texto or "", flags=re.IGNORECASE
    )
    consulta = PADRAO_PEDIDO_PESQUISA.sub("", consulta, count=1)
    consulta = re.sub(
        r"^\s*(?:na|no|pela|pelo)?\s*(?:internet|web|google)\b",
        "",
        consulta,
        flags=re.IGNORECASE,
    )
    consulta = re.sub(
        r"^\s*(?:sobre|a respeito de|acerca de|por|de)\b",
        "",
        consulta,
        flags=re.IGNORECASE,
    )
    consulta = re.sub(r"\s+", " ", consulta).strip(" .,;:!?")
    return (consulta or (texto or "").strip())[:MAX_CARACTERES_CONSULTA]


# Aliases privados usados pelo orquestrador e por testes antigos.
_ultima_mensagem_usuario = ultima_mensagem_usuario
_pedido_explicito_de_pesquisa = pedido_explicito_de_pesquisa
_consulta_do_pedido = consulta_do_pedido
