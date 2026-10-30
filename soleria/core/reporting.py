"""Fluxo de relatórios: escolher, gravar e ler a memória local.

O :class:`Assistant` cuida da conversa e da pesquisa; esta classe cuida
apenas do que acontece quando um relatório entra em jogo. Ela recebe o
repositório e o cliente do modelo e devolve texto pronto para a UI, sem
conhecer a interface.
"""

from config import LIMIAR_RELATORIO, MAX_TOKENS_RESPOSTA
from soleria.core.commands import extrair_novo, extrair_relatorio, limpar_comandos
from soleria.core.context import (
    caminho_amigavel,
    extrair_conteudo_relatorio,
    montar_pedido_leitura,
    relatorio_de_fontes,
    resumo_do_relatorio,
)
from soleria.core.intents import assunto_da_lembranca
from soleria.core.prompts import PROMPT_LEITURA
from soleria.logging_utils import log_erro, log_evento
from soleria.reports.format import formatar_relatorio
from soleria.reports.text import slugificar


class ReportCoordinator:
    """Operações de relatório usadas pelo orquestrador."""

    def __init__(self, repositorio, cliente):
        self.repositorio = repositorio
        self.cliente = cliente

    def encontrar(self, assunto):
        """Relatório que combina com o assunto e a lista de disponíveis."""
        if not self.repositorio:
            return None, []

        disponiveis = self.repositorio.listar()
        if not disponiveis:
            return None, []

        assunto = (assunto or "").strip()
        if not assunto:
            # Sem tema, só dá para ler automaticamente se houver um único
            # relatório; com vários, é melhor perguntar qual.
            if len(disponiveis) == 1:
                return disponiveis[0], disponiveis
            return None, disponiveis

        chave = slugificar(assunto, limite=200).replace("-", " ").strip()
        if chave:
            for relatorio in disponiveis:
                if chave == relatorio.id:
                    return relatorio, disponiveis
                titulo = slugificar(
                    relatorio.titulo, limite=200
                ).replace("-", " ").strip()
                if chave == titulo:
                    return relatorio, disponiveis

            for relatorio in disponiveis:
                titulo = slugificar(
                    relatorio.titulo, limite=200
                ).replace("-", " ").strip()
                if len(chave) >= 4 and len(titulo) >= 4 and (
                    chave in titulo or titulo in chave
                ):
                    return relatorio, disponiveis

        candidatos = self.repositorio.candidatos(
            assunto, limite=1, incluir_conteudo=True
        )
        if candidatos:
            return candidatos[0][1], disponiveis
        return None, disponiveis

    @staticmethod
    def mensagem_sem_relatorio(assunto, disponiveis):
        """Resposta quando a lembrança não encontra um relatório salvo."""
        if not disponiveis:
            if not assunto:
                return (
                    "Ainda não há nenhum relatório salvo. Quando eu "
                    "pesquisar algo, o relatório fica guardado aqui."
                )
            return (
                "Não encontrei nenhum relatório salvo. Pelo que está "
                "aqui, nunca conversamos sobre esse assunto."
            )

        titulos = "; ".join(r.titulo for r in disponiveis[:8])
        if not assunto:
            return (
                f"Tenho estes relatórios salvos: {titulos}. "
                "Qual deles você quer que eu leia?"
            )
        return (
            "Não encontrei nenhum relatório sobre isso. Pelo que "
            "está salvo aqui, nunca conversamos sobre esse assunto. "
            f"Os relatórios que tenho são: {titulos}."
        )

    def escolher(self, resposta, consulta, fontes):
        """Decide entre atualizar um relatório existente e criar outro."""
        identificador = extrair_relatorio(resposta)
        if identificador:
            relatorio = self.repositorio.carregar(identificador)
            if relatorio is not None:
                return ("atualizar", relatorio)

        titulo = extrair_novo(resposta)
        if titulo:
            chave = slugificar(titulo)
            for relatorio in self.repositorio.listar():
                if slugificar(relatorio.titulo) == chave:
                    return ("atualizar", relatorio)
            return ("criar", titulo)

        # O modelo não escolheu explicitamente. Se houver um candidato
        # muito forte, atualizamos; caso contrário, criamos um novo.
        candidatos = self.repositorio.candidatos(consulta, fontes)
        if candidatos and candidatos[0][0] >= LIMIAR_RELATORIO + 0.1:
            return ("atualizar", candidatos[0][1])
        return ("criar", consulta or "Relatório")

    def responder_leitura(
        self,
        mensagens,
        texto,
        emitir,
        status,
        resetar,
        foi_cancelado,
        cancelado,
        relatorio=None,
        prompt_sistema=None,
    ):
        """Responde a partir de um relatório salvo, sem pesquisar na web.

        Retorna ``(resposta, contexto)``. ``contexto`` é o texto que deve
        entrar no histórico do modelo; ``None`` significa que nada deve ser
        guardado. ``relatorio`` pode vir pronto de uma consulta anterior.
        ``prompt_sistema`` permite que o orquestrador acrescente a diretriz
        emocional sem quebrar o orçamento do pedido.
        """
        prompt_sistema = prompt_sistema or PROMPT_LEITURA
        assunto = assunto_da_lembranca(texto)
        if relatorio is None:
            relatorio, disponiveis = self.encontrar(assunto)
            if relatorio is None:
                resposta = self.mensagem_sem_relatorio(
                    assunto, disponiveis
                )
                emitir(resposta)
                return resposta, resposta

        status("lendo o relatório…")
        pedido = montar_pedido_leitura(
            mensagens,
            relatorio,
            texto,
            prompt_len=len(prompt_sistema),
        )
        resposta, ok = self.cliente.stream(
            [
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": pedido},
            ],
            MAX_TOKENS_RESPOSTA,
            callback=emitir,
            cancelado=cancelado,
        )
        status(None)
        if foi_cancelado():
            return "", None

        resposta = limpar_comandos(resposta or "").strip()
        if not ok or not resposta:
            # Se o modelo falhou ou devolveu só comandos, ainda entregue o
            # essencial do relatório em vez de perder a consulta.
            resetar()
            resposta = resumo_do_relatorio(relatorio)
            emitir(resposta)

        trecho = formatar_relatorio(relatorio, limite=700)
        contexto = (
            f"Relatório consultado ({relatorio.id}):\n{trecho}\n\n"
            f"Resposta dada ao usuário:\n{resposta}"
        )
        log_evento(f"Relatório lido: {relatorio.id}")
        return resposta, contexto

    def gravar(self, resposta, consultas, fontes, emitir):
        """Cria ou atualiza um relatório e devolve ``(mensagem, contexto)``."""
        consulta = " ; ".join(consultas)
        resumo, secao_titulo, conteudo = extrair_conteudo_relatorio(
            resposta, consulta
        )
        if not conteudo and not resumo:
            # O modelo pode ter devolvido só comandos internos (por exemplo,
            # [[PESQUISAR: ...]] na última rodada). A pesquisa já existe; não
            # jogue o trabalho fora: monte um relatório mínimo com as fontes.
            resumo, secao_titulo, conteudo = relatorio_de_fontes(
                consulta, fontes
            )
            log_evento(
                "Relatório montado a partir das fontes: o modelo não "
                f"devolveu conteúdo para a consulta {consulta!r}."
            )

        escolha = self.escolher(resposta, consulta, fontes)
        log_evento(
            f"Relatório: escolha={escolha[0]!r} "
            f"alvo={getattr(escolha[1], 'id', escolha[1])!r}"
        )
        try:
            if escolha[0] == "atualizar":
                relatorio = self.repositorio.atualizar(
                    escolha[1],
                    resumo=resumo,
                    consulta=consulta,
                    secao_titulo=secao_titulo,
                    conteudo=conteudo,
                    fontes=fontes,
                )
                acao = "Atualizei"
            else:
                relatorio = self.repositorio.criar(
                    titulo=escolha[1],
                    resumo=resumo,
                    consulta=consulta,
                    secao_titulo=secao_titulo,
                    conteudo=conteudo,
                    fontes=fontes,
                )
                acao = "Montei"
        except Exception as erro:
            log_erro(erro)
            mensagem = (
                "Não consegui salvar o relatório em "
                f"{self.repositorio.base_dir}. O conteúdo ficou assim:\n\n"
                f"{conteudo[:1200]}"
            )
            emitir(mensagem)
            return mensagem, None

        caminho = caminho_amigavel(relatorio.caminho_html())
        mensagem = (
            f'{acao} o relatório "{relatorio.titulo}" em {caminho}. '
            "Dá uma olhada."
        )
        contexto = (
            f"Resumo do relatório: {relatorio.resumo}\n\n{mensagem}"
        )
        emitir(mensagem)
        return mensagem, contexto

    def abrir_catalogo(self):
        """Gera o catálogo e tenta abri-lo no navegador."""
        try:
            caminho = self.repositorio.garantir_catalogo()
        except Exception as erro:
            log_erro(erro)
            return None

        try:
            import webbrowser

            webbrowser.open(caminho.resolve().as_uri())
        except Exception as erro:
            log_erro(erro)
        return caminho
