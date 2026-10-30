"""Utilitários de texto, identificadores e URLs dos relatórios.

Este módulo é puro: não toca no disco nem conhece o modelo de dados. Ele
concentra as regras de slug, limpeza de Markdown, resumo, tokens e citações
que eram compartilhadas pelo armazenamento e pela formatação dos prompts.
"""

import re
import unicodedata
from datetime import datetime
from urllib.parse import urlsplit

from config import MAX_CARACTERES_RESUMO_RELATORIO

MAX_TITULO = 120
MAX_CONSULTA = 300
MAX_TAG = 40

_PALAVRAS_VAZIAS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "da", "do",
    "das", "dos", "em", "no", "na", "nos", "nas", "por", "para", "com",
    "sem", "sobre", "entre", "que", "qual", "quais", "quando", "onde",
    "como", "porque", "porquê", "e", "ou", "mas", "se", "ao", "aos",
    "à", "às", "é", "são", "foi", "ser", "ter", "tem", "há", "ha",
    "mais", "menos", "muito", "muita", "muitos", "muitas", "já", "ja",
    "não", "nao", "sim", "the", "of", "and", "to", "in", "is", "are",
    "for", "with", "on", "at", "by", "from", "this", "that", "it",
    "an", "be", "or", "seu", "sua", "seus", "suas", "meu", "minha",
    "este", "esta", "esse", "essa", "isso", "aquilo", "ele", "ela",
    "eles", "elas", "você", "voce", "vocês", "voces", "nós", "nos",
    "eu", "tu", "lhe", "lhes", "atual", "atuais", "hoje", "agora",
}


def agora_iso():
    """Data/hora local em ISO, no mesmo formato usado nos metadados."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def slugificar(titulo, limite=60):
    """Transforma um título em um identificador seguro para pasta."""
    texto = unicodedata.normalize("NFKD", str(titulo or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.casefold()
    texto = re.sub(r"[^a-z0-9]+", "-", texto)
    texto = re.sub(r"-{2,}", "-", texto).strip("-")
    if len(texto) > limite:
        texto = texto[:limite].rstrip("-")
    return texto or "relatorio"


def texto_curto(valor, padrao="", limite=MAX_TITULO):
    """Normaliza espaços e corta um texto de metadado."""
    if not isinstance(valor, str):
        return padrao
    texto = " ".join(valor.split())
    if limite and len(texto) > limite:
        texto = texto[: limite - 1].rstrip() + "…"
    return texto or padrao


def texto_puro(texto):
    """Remove marcações leves para usar em resumos e metadados."""
    texto = str(texto or "")
    texto = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", texto)
    texto = re.sub(r"\[(\d+(?:\s*,\s*\d+)*)\](?!\()", "", texto)
    texto = re.sub(r"[*_`>#]+", "", texto)
    return re.sub(r"\s+", " ", texto).strip()


def resumo_do_texto(texto, limite=MAX_CARACTERES_RESUMO_RELATORIO):
    """Resume um texto cortando preferencialmente no fim de uma frase."""
    puro = texto_puro(texto)
    if len(puro) <= limite:
        return puro
    corte = puro[:limite]
    ponto = max(
        corte.rfind(". "), corte.rfind("! "), corte.rfind("? ")
    )
    if ponto > 80:
        corte = corte[: ponto + 1]
    corte = corte.rstrip()
    if not corte.endswith((".", "!", "?")):
        corte += "…"
    return corte


def tokens(texto):
    """Palavras significativas, sem acentos e sem palavras vazias."""
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    ).casefold()

    encontrados = set()
    for token in re.findall(r"[a-z0-9]{3,}", texto):
        if token in _PALAVRAS_VAZIAS:
            continue
        if token.isdigit() and len(token) != 4:
            continue
        encontrados.add(token)
    return encontrados


def normalizar_url(url):
    """Chave de deduplicação: sem fragmento e sem barra final."""
    return str(url or "").split("#", 1)[0].rstrip("/")


def url_valida(url):
    try:
        partes = urlsplit(str(url or ""))
    except ValueError:
        return False
    return partes.scheme in {"http", "https"} and bool(partes.netloc)


def dominio(url):
    try:
        host = urlsplit(str(url or "")).netloc.casefold()
    except ValueError:
        return ""
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    host = host.split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def remapear_citacoes(texto, mapa):
    """Troca as citações [1] da pesquisa pelos IDs globais do relatório."""
    def substituir(match):
        numeros = [int(numero) for numero in re.findall(r"\d+", match.group(1))]
        novos = []
        for numero in numeros:
            global_id = mapa.get(numero)
            if global_id and global_id not in novos:
                novos.append(global_id)
        if not novos:
            return ""
        return "[" + ", ".join(str(numero) for numero in novos) + "]"

    return re.sub(
        r"\[(\d+(?:\s*,\s*\d+)*)\](?!\()", substituir, str(texto or "")
    )


def extrair_citacoes(texto):
    encontrados = set()
    for bloco in re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", str(texto or "")):
        encontrados.update(int(numero) for numero in re.findall(r"\d+", bloco))
    return sorted(encontrados)


# Compatibilidade com os nomes privados usados pelo restante do pacote.
_texto = texto_curto
_texto_puro = texto_puro
_resumo_do_texto = resumo_do_texto
_tokens = tokens
_normalizar_url = normalizar_url
_url_valida = url_valida
_dominio = dominio
_remapear_citacoes = remapear_citacoes
_extrair_citacoes = extrair_citacoes
