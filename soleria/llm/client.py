"""Cliente OpenAI para o llama-server local."""

import threading

from openai import OpenAI

from config import BASE_URL, MODELO, TEMPERATURA, TIMEOUT_REQUISICAO
from soleria.logging_utils import log_erro


class LocalModelClient:
    """Encapsula o acesso ao llama-server via API compatível com OpenAI."""

    def __init__(self):
        self._cliente = OpenAI(
            base_url=BASE_URL,
            api_key="local",
            timeout=TIMEOUT_REQUISICAO,
            max_retries=1,
        )
        self._modelo_id = None
        self._lock = threading.Lock()

    def _id_modelo(self):
        """Descobre o identificador do modelo carregado.

        O llama-server aceita qualquer nome, mas usar o id real evita
        surpresas quando há mais de um modelo carregado.
        """
        with self._lock:
            if self._modelo_id is not None:
                return self._modelo_id

        try:
            modelos = self._cliente.models.list()
            if modelos.data:
                identificador = modelos.data[0].id
                with self._lock:
                    self._modelo_id = identificador
                return identificador
        except Exception as erro:
            log_erro(erro)

        with self._lock:
            if self._modelo_id is None:
                self._modelo_id = MODELO.stem
            return self._modelo_id

    def completar(self, mensagens, max_tokens):
        """Chamada sem streaming, útil para tarefas auxiliares curtas."""
        try:
            resposta = self._cliente.chat.completions.create(
                model=self._id_modelo(),
                messages=mensagens,
                temperature=TEMPERATURA,
                max_tokens=max_tokens,
                stream=False,
            )
            return (resposta.choices[0].message.content or "").strip()
        except Exception as erro:
            log_erro(erro)
            return ""

    def stream(self, mensagens, max_tokens, callback=None, cancelado=None):
        """Chamada com streaming real, disparando ``callback`` por trecho.

        Retorna ``(texto, ok)``. ``ok=False`` indica erro de transporte/rede;
        nesse caso o texto parcial recebido é preservado. Se ``cancelado`` for
        acionado, o streaming é interrompido e ``ok`` continua verdadeiro: o
        chamador deve checar o evento para saber que houve cancelamento.
        """
        partes = []
        callback_funciona = True
        try:
            with self._cliente.chat.completions.create(
                model=self._id_modelo(),
                messages=mensagens,
                temperature=TEMPERATURA,
                max_tokens=max_tokens,
                stream=True,
            ) as fluxo:
                for evento in fluxo:
                    if cancelado is not None and cancelado.is_set():
                        break

                    if not evento.choices:
                        continue

                    trecho = evento.choices[0].delta.content
                    if not trecho:
                        continue

                    partes.append(trecho)
                    if callback and callback_funciona:
                        try:
                            callback(trecho)
                        except Exception as erro:
                            # Um erro de desenho da UI não deve matar a
                            # resposta que já está sendo gerada. Depois da
                            # primeira falha, paramos de chamar o callback
                            # para não inundar o log.
                            callback_funciona = False
                            log_erro(erro)
        except Exception as erro:
            log_erro(erro)
            return "".join(partes).strip(), False

        return "".join(partes).strip(), True

    def fechar(self):
        try:
            self._cliente.close()
        except Exception:
            pass
