"""Histórico enviado ao modelo.

A UI conversa com :class:`HistoricoConversa` em vez de manipular listas e
locks diretamente. A classe mantém a ordem das mensagens, poda o excesso e
expõe uma versão que permite saber se a conversa foi limpa durante uma
geração.
"""

import threading

from config import MAX_HISTORICO
from soleria.core.context import montar_contexto


class HistoricoConversa:
    """Lista thread-safe de mensagens no formato aceito pelo modelo."""

    def __init__(self, maximo=MAX_HISTORICO):
        self.maximo = max(1, int(maximo))
        self._mensagens = []
        self._versao = 0
        self._lock = threading.RLock()

    @property
    def versao(self):
        with self._lock:
            return self._versao

    def snapshot(self):
        with self._lock:
            return list(self._mensagens)

    def contexto(self):
        with self._lock:
            return montar_contexto(self._mensagens, self.maximo)

    def registrar_usuario(self, texto):
        """Adiciona a mensagem do usuário e devolve o contexto resultante.

        Retorna ``(mensagem, mensagens_para_o_modelo, versao)``. A versão
        deve ser passada de volta ao registrar a resposta para detectar uma
        conversa limpa no meio da geração.
        """
        with self._lock:
            mensagem = {"role": "user", "content": texto}
            self._mensagens.append(mensagem)
            self._podar()
            contexto = montar_contexto(self._mensagens, self.maximo)
            return mensagem, contexto, self._versao

    def descartar_usuario(self, mensagem, versao):
        """Remove uma pergunta órfã se a conversa não mudou desde então."""
        with self._lock:
            if versao != self._versao:
                return False
            if self._mensagens and self._mensagens[-1] is mensagem:
                self._mensagens.pop()
                return True
            return False

    def registrar_assistente(self, conteudo, versao):
        """Adiciona a resposta se a conversa ainda for a mesma.

        Retorna ``False`` quando a conversa foi limpa (ou outra mensagem
        assumiu) durante a geração.
        """
        with self._lock:
            if versao != self._versao:
                return False
            self._mensagens.append(
                {"role": "assistant", "content": conteudo}
            )
            self._podar()
            return True

    def registrar_iniciativa(self, conteudo):
        """Adiciona uma mensagem que a Soleria puxou por conta própria.

        Só entra se a última mensagem ainda for dela. Assim uma iniciativa
        gerada em segundo plano nunca "responde" uma pergunta nova que o
        usuário mandou enquanto o modelo pensava.
        """
        return self._registrar_espontanea(conteudo, exigir_historico=True)

    def registrar_espontanea(self, conteudo):
        """Adiciona um comentário espontâneo, como o da tela observada.

        Pode ser a primeira mensagem da conversa — ela comenta a tela mesmo
        sem histórico —, mas nunca entra por cima de uma mensagem do
        usuário que ainda está sem resposta.
        """
        return self._registrar_espontanea(conteudo, exigir_historico=False)

    def _registrar_espontanea(self, conteudo, exigir_historico):
        texto = str(conteudo or "").strip()
        if not texto:
            return False
        with self._lock:
            if exigir_historico and not self._mensagens:
                return False
            if self._mensagens and self._mensagens[-1].get("role") != "assistant":
                return False
            self._mensagens.append(
                {"role": "assistant", "content": texto}
            )
            self._podar()
            return True

    def limpar(self):
        with self._lock:
            self._mensagens.clear()
            self._versao += 1
            return self._versao

    def _podar(self):
        """Chame com ``self._lock`` adquirido."""
        limite = max(2, self.maximo)
        if len(self._mensagens) > limite:
            del self._mensagens[:-limite]
        while self._mensagens and self._mensagens[0].get("role") != "user":
            self._mensagens.pop(0)
