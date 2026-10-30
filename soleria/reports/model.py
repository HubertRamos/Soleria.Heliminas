"""Modelo de um relatório carregado do disco."""

from pathlib import Path

from soleria.reports.paths import ARQUIVO_DADOS, ARQUIVO_HTML
from soleria.reports.text import (
    MAX_CONSULTA,
    MAX_TAG,
    MAX_TITULO,
    agora_iso,
    dominio,
    extrair_citacoes,
    normalizar_url,
    remapear_citacoes,
    texto_curto,
    tokens,
    url_valida,
)


class Relatorio:
    """Um relatório carregado do disco.

    O dicionário ``dados`` é a fonte de verdade e é gravado em
    ``dados.json``. A classe expõe apenas leituras e as operações de
    atualização de seções/fontes.
    """

    @staticmethod
    def _lista(valor):
        """Lista de dados; qualquer outro tipo vira lista vazia."""
        return valor if isinstance(valor, list) else []

    @staticmethod
    def _id_numerico(fonte):
        """ID da fonte como inteiro; ``None`` quando ausente ou inválido.

        Relatórios antigos podem ter IDs não numéricos ou nem ter o campo;
        nesse caso o renderizador usa a posição na lista como âncora.
        """
        if not isinstance(fonte, dict):
            return None
        valor = fonte.get("id")
        if valor is None or valor == "":
            return None
        try:
            return int(valor)
        except (TypeError, ValueError):
            return None

    def __init__(self, caminho, dados):
        self.caminho = Path(caminho)
        self.dados = dados

    @property
    def id(self):
        return str(self.dados.get("id") or self.caminho.name)

    @property
    def titulo(self):
        return str(self.dados.get("titulo") or self.id)

    @property
    def resumo(self):
        return str(self.dados.get("resumo") or "")

    @property
    def secoes(self):
        return self._lista(self.dados.get("secoes"))

    @property
    def fontes(self):
        return self._lista(self.dados.get("fontes"))

    @property
    def tags(self):
        return self._lista(self.dados.get("tags"))

    @property
    def atualizado(self):
        return str(self.dados.get("atualizado") or "")

    def caminho_dados(self):
        return self.caminho / ARQUIVO_DADOS

    def caminho_html(self):
        return self.caminho / ARQUIVO_HTML

    def texto_busca(self, incluir_conteudo=False):
        """Texto usado para comparar o relatório com uma consulta nova.

        O corpo das seções só entra quando a busca é uma lembrança/leitura.
        Na criação de relatórios, usar o corpo inteiro deixaria qualquer
        palavra comum do texto parecer um assunto em comum.
        """
        partes = [self.titulo, self.resumo, " ".join(str(tag) for tag in self.tags)]
        for secao in self.secoes:
            if not isinstance(secao, dict):
                continue
            partes.append(str(secao.get("titulo") or ""))
            partes.append(str(secao.get("consulta") or ""))
            if incluir_conteudo:
                partes.append(str(secao.get("conteudo") or ""))
        for fonte in self.fontes:
            if not isinstance(fonte, dict):
                continue
            partes.append(str(fonte.get("titulo") or ""))
            partes.append(str(fonte.get("dominio") or ""))
        return " ".join(partes)

    def dominios(self):
        dominios = set()
        for fonte in self.fontes:
            if not isinstance(fonte, dict):
                continue
            valor = str(
                fonte.get("dominio") or dominio(fonte.get("url"))
            ).casefold()
            if valor:
                dominios.add(valor)
        return dominios

    def _mesclar_fontes(self, fontes, agora):
        """Acrescenta fontes novas e devolve o mapa índice local -> ID global."""
        if not isinstance(self.dados.get("fontes"), list):
            self.dados["fontes"] = []

        existentes = {
            normalizar_url(fonte.get("url")): fonte
            for fonte in self.fontes
            if isinstance(fonte, dict) and fonte.get("url")
        }
        posicoes = {
            normalizar_url(fonte.get("url")): indice
            for indice, fonte in enumerate(self.fontes, start=1)
            if isinstance(fonte, dict) and fonte.get("url")
        }
        proximo = max(
            len(self.fontes),
            max(
                (
                    self._id_numerico(fonte) or 0
                    for fonte in self.fontes
                ),
                default=0,
            ),
        ) + 1
        mapa = {}

        for indice, fonte in enumerate(fontes or (), start=1):
            if not isinstance(fonte, dict):
                continue
            url = str(fonte.get("url") or "").strip()
            if not url_valida(url):
                continue

            chave = normalizar_url(url)
            atual = existentes.get(chave)
            if atual is not None:
                # O renderizador numera fontes sem ``id`` pela posição na
                # lista; use essa posição para a citação continuar válida.
                identificador = self._id_numerico(atual)
                if identificador is None:
                    identificador = posicoes.get(chave, indice)
                mapa[indice] = identificador
                titulo = texto_curto(fonte.get("titulo"), limite=200)
                if titulo and (
                    not atual.get("titulo")
                    or atual.get("titulo") == "Título indisponível"
                ):
                    atual["titulo"] = titulo
                continue

            nova = {
                "id": proximo,
                "titulo": texto_curto(
                    fonte.get("titulo") or dominio(url) or "Fonte",
                    limite=200,
                ),
                "url": url,
                "dominio": dominio(url),
                "acessado": agora,
            }
            self.dados["fontes"].append(nova)
            existentes[chave] = nova
            mapa[indice] = proximo
            proximo += 1

        return mapa

    def adicionar_secao(
        self,
        secao_titulo,
        consulta,
        conteudo,
        fontes,
        agora=None,
    ):
        """Acrescenta uma seção, mescla fontes e renumera as citações."""
        agora = agora or agora_iso()
        if not isinstance(self.dados.get("secoes"), list):
            self.dados["secoes"] = []

        mapa = self._mesclar_fontes(fontes or [], agora)
        conteudo = remapear_citacoes(conteudo, mapa).strip()
        if not conteudo:
            conteudo = (
                "A pesquisa não trouxe detalhes suficientes para esta seção."
            )

        secao = {
            "titulo": texto_curto(
                secao_titulo or consulta or "Pesquisa",
                "Pesquisa",
                MAX_TITULO,
            ),
            "consulta": texto_curto(consulta, "", MAX_CONSULTA),
            "criado": agora,
            "conteudo": conteudo,
            "citacoes": extrair_citacoes(conteudo),
        }
        self.dados["secoes"].append(secao)
        self.dados["atualizado"] = agora

        tags = [
            str(tag).strip()
            for tag in (self.dados.get("tags") or [])
            if str(tag).strip()
        ]
        for tag in sorted(tokens(f"{secao_titulo or ''} {consulta or ''}")):
            if tag not in tags:
                tags.append(tag[:MAX_TAG])
        self.dados["tags"] = tags[:16]

        return secao
