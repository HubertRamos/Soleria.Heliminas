"""Armazenamento e catálogo dos relatórios em HTML.

Cada relatório mora em ``<pasta>/<id>/`` com dois arquivos:

- ``index.html``: o relatório que o usuário abre;
- ``dados.json``: o conteúdo estruturado e os metadados usados para
  atualizar o relatório e para procurar assuntos parecidos.

O catálogo geral fica em ``<pasta>/index.html``. As regras de texto ficam
em :mod:`soleria.reports.text`, o modelo em :mod:`soleria.reports.model` e
a formatação de prompts em :mod:`soleria.reports.format`.
"""

import json
import os
from pathlib import Path

from config import (
    LIMIAR_RELATORIO,
    MAX_CANDIDATOS_RELATORIO,
    MAX_CARACTERES_RESUMO_RELATORIO,
    PASTA_RELATORIOS,
)
from soleria.logging_utils import log_erro, log_evento
# Reexportados para o catálogo e para imports antigos.
from soleria.reports.format import formatar_candidatos, formatar_relatorio
from soleria.reports.model import Relatorio
from soleria.reports.paths import ARQUIVO_DADOS, ARQUIVO_HTML, VERSAO_DADOS
from soleria.reports.render import renderizar_catalogo, renderizar_relatorio
from soleria.reports.text import (
    MAX_CONSULTA as _MAX_CONSULTA,
    MAX_TAG as _MAX_TAG,
    MAX_TITULO as _MAX_TITULO,
    agora_iso,
    dominio,
    normalizar_url,
    resumo_do_texto,
    slugificar,
    texto_curto,
    texto_puro,
    tokens,
    url_valida,
)

# Nomes privados mantidos para compatibilidade com código/testes antigos.
_texto = texto_curto
_texto_puro = texto_puro
_resumo_do_texto = resumo_do_texto
_tokens = tokens
_normalizar_url = normalizar_url
_url_valida = url_valida
_dominio = dominio


def _escrever_texto(caminho, texto):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_name(caminho.name + ".tmp")
    temporario.write_text(texto, encoding="utf-8")
    os.replace(temporario, caminho)


def _escrever_json(caminho, dados):
    _escrever_texto(
        caminho, json.dumps(dados, ensure_ascii=False, indent=2) + "\n"
    )


class RepositorioRelatorios:
    """Acesso à pasta de relatórios e ao catálogo."""

    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir or PASTA_RELATORIOS).expanduser()

    @property
    def caminho_catalogo(self):
        return self.base_dir / ARQUIVO_HTML

    def garantir_base(self):
        self.base_dir.mkdir(parents=True, exist_ok=True)
        return self.base_dir

    def listar(self):
        if not self.base_dir.is_dir():
            return []

        relatorios = []
        for caminho in sorted(
            self.base_dir.iterdir(), key=lambda item: item.name
        ):
            if not caminho.is_dir():
                continue
            arquivo = caminho / ARQUIVO_DADOS
            if not arquivo.is_file():
                continue
            try:
                dados = json.loads(arquivo.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as erro:
                log_erro(erro)
                continue
            if not isinstance(dados, dict):
                continue

            dados.setdefault("id", caminho.name)
            dados.setdefault("titulo", dados["id"])
            dados.setdefault("resumo", "")
            dados.setdefault("secoes", [])
            dados.setdefault("fontes", [])
            dados.setdefault("tags", [])
            relatorios.append(Relatorio(caminho, dados))

        relatorios.sort(
            key=lambda relatorio: relatorio.atualizado, reverse=True
        )
        return relatorios

    def carregar(self, id_relatorio):
        identificador = slugificar(id_relatorio)
        caminho = self.base_dir / identificador
        arquivo = caminho / ARQUIVO_DADOS
        if not arquivo.is_file():
            return None
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as erro:
            log_erro(erro)
            return None
        if not isinstance(dados, dict):
            return None
        dados.setdefault("id", identificador)
        dados.setdefault("titulo", identificador)
        dados.setdefault("resumo", "")
        dados.setdefault("secoes", [])
        dados.setdefault("fontes", [])
        dados.setdefault("tags", [])
        return Relatorio(caminho, dados)

    def _id_unico(self, base):
        self.garantir_base()
        candidato = base
        contador = 2
        while (self.base_dir / candidato / ARQUIVO_DADOS).exists():
            sufixo = f"-{contador}"
            candidato = base[: 60 - len(sufixo)].rstrip("-") + sufixo
            contador += 1
        return candidato

    def criar(
        self,
        *,
        titulo,
        resumo="",
        consulta="",
        secao_titulo=None,
        conteudo="",
        fontes=None,
        tags=None,
    ):
        titulo = texto_curto(
            titulo or consulta or "Relatório", "Relatório", 90
        )
        identificador = self._id_unico(slugificar(titulo))
        agora = agora_iso()
        caminho = self.garantir_base() / identificador

        dados = {
            "versao": VERSAO_DADOS,
            "id": identificador,
            "titulo": titulo,
            "criado": agora,
            "atualizado": agora,
            "resumo": texto_puro(resumo)[:MAX_CARACTERES_RESUMO_RELATORIO],
            "tags": [],
            "secoes": [],
            "fontes": [],
        }
        relatorio = Relatorio(caminho, dados)
        relatorio.adicionar_secao(
            secao_titulo=secao_titulo or consulta or "Pesquisa",
            consulta=consulta,
            conteudo=conteudo,
            fontes=fontes,
            agora=agora,
        )

        if not dados["resumo"]:
            dados["resumo"] = resumo_do_texto(conteudo)
        if tags:
            atuais = list(dados.get("tags") or [])
            for tag in tags:
                valor = texto_curto(str(tag), limite=_MAX_TAG)
                if valor and valor not in atuais:
                    atuais.append(valor)
            dados["tags"] = atuais[:16]

        self.salvar(relatorio)
        log_evento(f"Relatório criado: {caminho}")
        return relatorio

    def atualizar(
        self,
        relatorio,
        *,
        resumo="",
        consulta="",
        secao_titulo=None,
        conteudo="",
        fontes=None,
    ):
        agora = agora_iso()
        resumo = texto_puro(resumo)[:MAX_CARACTERES_RESUMO_RELATORIO]
        if resumo:
            relatorio.dados["resumo"] = resumo

        relatorio.adicionar_secao(
            secao_titulo=secao_titulo or consulta or "Pesquisa",
            consulta=consulta,
            conteudo=conteudo,
            fontes=fontes,
            agora=agora,
        )

        if not relatorio.dados.get("resumo"):
            relatorio.dados["resumo"] = resumo_do_texto(conteudo)

        self.salvar(relatorio)
        log_evento(f"Relatório atualizado: {relatorio.caminho}")
        return relatorio

    def salvar(self, relatorio):
        relatorio.dados["atualizado"] = (
            relatorio.dados.get("atualizado") or agora_iso()
        )
        _escrever_json(relatorio.caminho_dados(), relatorio.dados)
        _escrever_texto(
            relatorio.caminho_html(),
            renderizar_relatorio(relatorio.dados),
        )
        # O catálogo é auxiliar: uma falha nele não pode fazer o relatório
        # recém-gravado parecer perdido para o usuário.
        try:
            self.gerar_catalogo()
        except Exception as erro:
            log_erro(erro)

    def gerar_catalogo(self):
        self.garantir_base()
        relatorios = [relatorio.dados for relatorio in self.listar()]
        _escrever_texto(
            self.caminho_catalogo,
            renderizar_catalogo(relatorios),
        )
        return self.caminho_catalogo

    def garantir_catalogo(self):
        return self.gerar_catalogo()

    def candidatos(
        self,
        consulta,
        fontes=None,
        limite=None,
        limiar=None,
        incluir_conteudo=False,
    ):
        """Relatórios que provavelmente combinam com a pesquisa nova.

        A pontuação combina palavras significativas da consulta com os
        metadados de cada relatório e um bônus por domínios em comum. Com
        ``incluir_conteudo=True``, o corpo das seções também entra na busca
        (usado para lembrar de conversas antigas). O modelo só recebe os
        candidatos acima do limiar; se nenhum passar, a pesquisa vira um
        relatório novo.
        """
        limite = max(1, int(limite or MAX_CANDIDATOS_RELATORIO))
        limiar = LIMIAR_RELATORIO if limiar is None else float(limiar)

        tokens_consulta = tokens(consulta)
        tokens_extras = set()
        dominios_novos = set()

        for fonte in fontes or ():
            if not isinstance(fonte, dict):
                continue
            tokens_extras |= tokens(fonte.get("titulo") or "")
            tokens_extras |= tokens(fonte.get("resumo") or "")
            valor_dominio = dominio(fonte.get("url"))
            if valor_dominio:
                dominios_novos.add(valor_dominio)

        if not tokens_consulta and not tokens_extras and not dominios_novos:
            return []

        candidatos = []
        for relatorio in self.listar():
            tokens_relatorio = tokens(
                relatorio.texto_busca(incluir_conteudo)
            )
            if not tokens_relatorio:
                continue

            pontuacao = 0.0
            if tokens_consulta:
                pontuacao += len(
                    tokens_consulta & tokens_relatorio
                ) / len(tokens_consulta)
            if tokens_extras:
                pontuacao += 0.2 * (
                    len(tokens_extras & tokens_relatorio) / len(tokens_extras)
                )
            if dominios_novos:
                comuns = dominios_novos & relatorio.dominios()
                if comuns:
                    pontuacao += 0.25 * (
                        len(comuns) / len(dominios_novos)
                    )

            pontuacao = min(1.0, pontuacao)
            if pontuacao >= limiar:
                candidatos.append((pontuacao, relatorio))

        candidatos.sort(key=lambda item: item[0], reverse=True)
        return candidatos[:limite]
