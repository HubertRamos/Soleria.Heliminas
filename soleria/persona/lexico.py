"""Vocabulário afetivo usado para ler o tom da conversa.

O detector é intencionalmente simples e offline: procura pistas de afeto,
humor, irritação, cansaço, curiosidade e outros sinais. Ele não tenta
"adivinhar" sentimentos profundos; só dá ao motor emocional material para
reagir de forma consistente.
"""

from __future__ import annotations

import re
import unicodedata

# Termos já normalizados (sem acento, minúsculos) para comparação.
LEXICOS = {
    "afeto": (
        "te amo",
        "te adoro",
        "amo voce",
        "gosto de voce",
        "voce e incrivel",
        "minha favorita",
        "melhor assistente",
        "confio em voce",
        "carinho",
        "saudade",
        "meu bem",
        "minha linda",
    ),
    "elogio": (
        "obrigado",
        "obrigada",
        "parabens",
        "mandou bem",
        "muito bom",
        "perfeito",
        "amei",
        "adorei",
        "otimo",
        "otima",
        "excelente",
        "genial",
        "linda",
        "fofa",
        "inteligente",
        "genio",
        "arrasou",
        "boa",
        "maravilhosa",
    ),
    "humor": (
        "kkkk",
        "haha",
        "rsrs",
        "rsrsrs",
        "😂",
        "🤣",
        "piada",
        "meme",
        "zoeira",
        "brincadeira",
        "sarcasmo",
        "deboche",
        "engracado",
        "engracada",
        "rindo",
    ),
    "raiva": (
        "idiota",
        "burra",
        "inutil",
        "lixo",
        "cala a boca",
        "odeio",
        "raiva",
        "irritado",
        "irritada",
        "absurdo",
        "ridiculo",
        "ridicula",
        "merda",
        "porcaria",
        "chata",
        "ninguem te perguntou",
    ),
    "nojo": (
        "nojo",
        "nojento",
        "nojenta",
        "que asco",
        "eca",
    ),
    "tristeza": (
        "triste",
        "chorando",
        "chorei",
        "sozinho",
        "sozinha",
        "desanimado",
        "desanimada",
        "deprimido",
        "deprimida",
        "vazio",
        "sem esperanca",
        "cansado de tudo",
        "cansada de tudo",
    ),
    "medo": (
        "medo",
        "assustador",
        "assustadora",
        "assustada",
        "assustado",
        "socorro",
        "panico",
        "terror",
        "tenho medo",
    ),
    "susto": (
        "surpresa",
        "caramba",
        "uau",
        "inacreditavel",
        "nao acredito",
        "que isso",
        "meu deus",
        "nossa",
    ),
    "confusao": (
        "nao entendi",
        "confuso",
        "confusa",
        "como assim",
        "nao sei",
        "nao faco ideia",
        "perdido",
        "perdida",
        "bugou",
    ),
    "curiosidade": (
        "por que",
        "porque",
        "como funciona",
        "o que e",
        "explica",
        "me explica",
        "analisa",
        "analise",
        "pesquisa",
        "descobre",
        "curiosidade",
        "sera que",
        "quero saber",
        "me conta",
        "como assim",
    ),
    "urgencia": (
        "urgente",
        "agora",
        "rapido",
        "rapida",
        "depressa",
        "corre",
        "pra ontem",
        "nao posso esperar",
    ),
    "foco": (
        "foco",
        "focar",
        "focado",
        "focada",
        "concentra",
        "concentracao",
    ),
    "sono": (
        "com sono",
        "cansad",
        "dormir",
        "boa noite",
        "zzz",
        "acordei cedo",
        "sem dormir",
        "exausto",
        "exausta",
        "sonolento",
        "sonolenta",
    ),
    "saudacao": (
        "oi",
        "ola",
        "bom dia",
        "boa tarde",
        "boa noite",
        "e ai",
        "eai",
        "hey",
        "salve",
    ),
    "despedida": (
        "tchau",
        "ate logo",
        "ate mais",
        "vou sair",
        "fui",
        "boa noite",
        "ate amanha",
    ),
    "tecnico": (
        "codigo",
        "erro",
        "bug",
        "debug",
        "python",
        "funcao",
        "api",
        "terminal",
        "arquivo",
        "git",
        "teste",
        "compilar",
        "instalar",
        "script",
    ),
    "vulneravel": (
        "desculpa",
        "desculpe",
        "foi mal",
        "me ajuda",
        "nao sei o que fazer",
        "perdido",
        "perdida",
        "preciso de voce",
        "estou mal",
        "meu dia foi ruim",
        "cansado",
        "cansada",
    ),
    "conquista": (
        "consegui",
        "funcionou",
        "deu certo",
        "ganhei",
        "aprovei",
        "terminei",
        "finalizei",
        "conquista",
        "vitoria",
    ),
    "tedio": (
        "tedio",
        "entediado",
        "entediada",
        "nada pra fazer",
        "sem nada",
        "chato",
    ),
    "vergonha": (
        "vergonha",
        "timido",
        "timida",
        "envergonhado",
        "envergonhada",
        "corada",
        "fofo",
        "fofa",
    ),
    "animacao": (
        "animacao",
        "animado",
        "animada",
        "empolgado",
        "empolgada",
        "que legal",
        "adorei isso",
    ),
    "seriedade": (
        "que serio",
        "serissimo",
        "seriedade",
        "estou serio",
        "estou seria",
    ),
    "falha": (
        "nao consegui",
        "nao deu",
        "falhei",
        "falhou",
        "deu erro",
        "sem sucesso",
    ),
}


def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos, preservando emojis e pontuação."""
    decomposto = unicodedata.normalize("NFKD", (texto or "").casefold())
    return "".join(
        caractere
        for caractere in decomposto
        if not unicodedata.combining(caractere)
    )


def _contem_termo(texto_normalizado: str, termo: str) -> bool:
    termo = normalizar(termo)
    if not termo:
        return False
    # Palavras muito curtas precisam de fronteira para "oi" não casar
    # dentro de "foi", por exemplo.
    if termo.isalpha() and len(termo) <= 3:
        padrao = rf"(?<!\w){re.escape(termo)}(?!\w)"
        return re.search(padrao, texto_normalizado) is not None
    return termo in texto_normalizado


def contem(texto: str, termos) -> bool:
    texto_normalizado = normalizar(texto)
    return any(
        _contem_termo(texto_normalizado, termo) for termo in termos
    )


def detectar(texto: str) -> frozenset[str]:
    """Devolve o conjunto de pistas encontradas no texto."""
    texto_normalizado = normalizar(texto)
    return frozenset(
        tag
        for tag, termos in LEXICOS.items()
        if any(
            _contem_termo(texto_normalizado, termo) for termo in termos
        )
    )


__all__ = ["LEXICOS", "contem", "detectar", "normalizar"]
