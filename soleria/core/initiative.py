"""Mensagens de iniciativa contextual.

A Soleria só puxa assunto quando há um gancho concreto na conversa. O
modelo recebe a conversa recente, os assuntos que ficaram em aberto e a
última iniciativa; se nada for realmente contextual, devolve silêncio.

Este módulo não conhece a interface nem o servidor: ele monta o pedido e
valida a resposta. A decisão de *quando* tentar fica em :mod:`soleria.app`.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from config import MAX_CARACTERES_PROATIVA
from soleria.core.commands import limpar_comandos
from soleria.core.context import conversa_compacta, limitar_bloco

MARCADOR_SILENCIO = "[[SILENCIO]]"

_MAX_TOPICOS = 4
_MAX_TOPICO = 140
_MAX_HISTORICO = 900

# Perguntas e planos que costumam render um gancho para depois.
_GANCHOS = re.compile(
    r"\b(?:como|por que|porque|o que|qual|quais|quando|onde|quem|"
    r"sera que|funciona|funcionar|aprender|entender|explica|explicar|"
    r"preciso|quero|pensei|estou|vou|tenho|planejo|pretendo)\b"
)

_DESPEDIDA = re.compile(
    r"\b(?:ate logo|ate mais|tchau|falou|fui|ja volto|ate amanha|"
    r"nos vemos|boa noite|bom descanso)\b"
)

_SAUDACAO_INICIAL = re.compile(
    r"^(?:oi|ola|ei|opa|e ai|bom dia|boa tarde|boa noite)\b[\s,!.]*"
)

_GENERICAS = {
    "tudo bem",
    "tudo bom",
    "como voce esta",
    "como voce ta",
    "como vai",
    "posso ajudar",
    "em que posso ajudar",
    "estou aqui se precisar",
    "estou por aqui",
    "quer conversar",
    "o que voce quer falar",
    "alguma novidade",
    "ta ai",
    "voce esta ai",
    "so passando para dar um oi",
    "so queria saber como voce esta",
    "me conta uma novidade",
}


def _sem_acento(texto):
    decomposto = unicodedata.normalize("NFKD", texto or "")
    return "".join(
        caractere
        for caractere in decomposto
        if not unicodedata.combining(caractere)
    ).casefold()


def _normalizar(texto):
    return " ".join(_sem_acento(texto).split())


def _e_generica(texto):
    """True para mensagens que não usam nada da conversa."""
    normal = re.sub(r"[^a-z0-9\s]", " ", _normalizar(texto))
    normal = " ".join(normal.split())
    if not normal:
        return True
    sem_saudacao = _SAUDACAO_INICIAL.sub("", normal).strip()
    if not sem_saudacao:
        return True
    return sem_saudacao in _GENERICAS


def _e_despedida(texto):
    normal = _normalizar(texto)
    if not normal or len(normal) > 180:
        return False
    return bool(_DESPEDIDA.search(normal))


def _parecida(texto, referencia):
    """Evita repetir a mesma iniciativa com outras palavras."""
    if not referencia:
        return False
    atual = re.sub(r"[^a-z0-9\s]", " ", _normalizar(texto))
    anterior = re.sub(r"[^a-z0-9\s]", " ", _normalizar(referencia))
    atual = " ".join(atual.split())
    anterior = " ".join(anterior.split())
    if not atual or not anterior:
        return False
    if atual == anterior:
        return True
    if min(len(atual), len(anterior)) >= 12 and (
        atual in anterior or anterior in atual
    ):
        return True
    return SequenceMatcher(None, atual, anterior).ratio() >= 0.82


def _truncar(texto, limite):
    if limite <= 0:
        return ""
    if len(texto) <= limite:
        return texto
    corte = texto[:limite]
    fim_frase = re.search(r"[.!?](?=[^.!?]*$)", corte)
    if fim_frase and fim_frase.end() >= limite * 0.5:
        return corte[: fim_frase.end()].strip()
    if " " in corte:
        corte = corte.rsplit(" ", 1)[0]
    return corte.rstrip(" ,;:-") + "…"


def assuntos_em_aberto(mensagens):
    """Frases recentes do usuário que podem render uma retomada.

    A extração é determinística e conservadora: perguntas, planos e
    explicações. Ela não decide a mensagem; só dá ao modelo os ganchos
    concretos para evitar um assunto aleatório.
    """
    topicos = []
    vistos = set()
    for mensagem in list(mensagens or [])[-8:]:
        if mensagem.get("role") != "user":
            continue
        texto = str(mensagem.get("content") or "")
        for frase in re.split(r"(?<=[.!?])\s+|\n+", texto):
            frase = " ".join(frase.split()).strip(" .,;:!?\"'")
            if len(frase) < 8:
                continue
            normal = _normalizar(frase)
            if "?" not in frase and not _GANCHOS.search(normal):
                continue
            if _e_generica(frase) or _e_despedida(frase):
                continue
            chave = normal[:120]
            if chave in vistos:
                continue
            vistos.add(chave)
            topicos.append(frase[:_MAX_TOPICO])
    # O mais recente primeiro: é o gancho com maior chance de ainda estar
    # vivo na cabeça do Hubert.
    return list(reversed(topicos[-_MAX_TOPICOS:]))


def montar_pedido_iniciativa(
    mensagens, assuntos=None, ultima_proativa=None
):
    """Monta o pedido que faz o modelo escolher entre falar e calar."""
    historico = limitar_bloco(
        conversa_compacta(
            mensagens, limite=6, max_caracteres=200
        ),
        _MAX_HISTORICO,
    )
    if assuntos is None:
        assuntos = assuntos_em_aberto(mensagens)

    if assuntos:
        topicos = "\n".join(f"- {assunto}" for assunto in assuntos)
    else:
        topicos = "- (nenhum assunto claramente em aberto; prefira silêncio)"

    partes = [
        "Conversa recente (mais antiga primeiro):",
        "<conversa>",
        historico or "(sem histórico)",
        "</conversa>",
        "",
        "Ganchos concretos que podem ter ficado em aberto:",
        topicos,
    ]
    if ultima_proativa:
        partes.extend(
            [
                "",
                "Sua última iniciativa foi:",
                f'"{_truncar(str(ultima_proativa), 200)}"',
                "Não repita essa ideia.",
            ]
        )
    partes.extend(
        [
            "",
            "Decida agora: responda apenas [[SILENCIO]] ou escreva uma "
            "mensagem curta que só faça sentido por causa dessa conversa.",
        ]
    )
    return "\n".join(partes)


def extrair_iniciativa(texto, ultima_proativa=None):
    """Valida a saída do modelo e devolve ``None`` quando é silêncio.

    Também rejeita saudações genéricas, respostas vazias e repetições da
    última iniciativa. Uma mensagem longa é cortada numa fronteira de frase.
    """
    bruto = str(texto or "").strip()
    if not bruto:
        return None
    if re.search(r"\[\s*SIL[EÊ]NCIO\s*\]", bruto, re.IGNORECASE):
        return None

    limpo = limpar_comandos(bruto)
    limpo = re.sub(r"\[\[.*?\]\]", "", limpo, flags=re.DOTALL)
    limpo = limpo.strip().strip("\"'“”‘’")
    limpo = " ".join(limpo.split())
    if not limpo:
        return None
    if _e_generica(limpo) or _e_despedida(limpo):
        return None
    if len(limpo.split()) < 3:
        return None
    if _parecida(limpo, ultima_proativa):
        return None

    return _truncar(limpo, max(80, int(MAX_CARACTERES_PROATIVA)))


def motivo_para_silencio(mensagens):
    """Motivos determinísticos para nem chamar o modelo.

    Devolve uma descrição curta quando não é hora de puxar assunto e
    ``None`` quando a conversa está em um ponto seguro para tentar.
    """
    mensagens = list(mensagens or [])
    if len(mensagens) < 2:
        return "conversa curta"

    ultima = mensagens[-1]
    if ultima.get("role") != "assistant":
        return "há uma mensagem sem resposta"

    texto = str(ultima.get("content") or "").strip()
    if not texto:
        return "resposta vazia"
    if "[cancelado]" in texto.casefold():
        return "resposta cancelada"
    if texto.endswith("?"):
        return "pergunta sem resposta"
    if _e_despedida(texto):
        return "despedida"

    # Se o usuário se despediu e a Soleria só respondeu, não insista.
    for mensagem in reversed(mensagens[:-1]):
        if mensagem.get("role") == "user":
            if _e_despedida(str(mensagem.get("content") or "")):
                return "despedida do usuário"
            break

    return None


__all__ = [
    "MARCADOR_SILENCIO",
    "assuntos_em_aberto",
    "extrair_iniciativa",
    "montar_pedido_iniciativa",
    "motivo_para_silencio",
]
