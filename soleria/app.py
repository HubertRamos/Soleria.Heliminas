"""Inicialização e coordenação da aplicação."""

import atexit
import signal
import threading
import time
from collections import deque

from config import (
    COOLDOWN_PROATIVA,
    EMOCAO_ESTADO,
    NOME,
    TEMPO_INATIVIDADE,
    TEMPO_PROATIVA,
    TIMEOUT_DIGITACAO,
    TELA_ACORDAR,
    TELA_COOLDOWN,
    TELA_INTERVALO,
    TELA_MUDANCA,
)
from soleria.core.assistant import Assistant
from soleria.core.context import montar_contexto
from soleria.core.history import HistoricoConversa
from soleria.core.screen import comentario_repetido
from soleria.llm.server import LlamaServer
from soleria.logging_utils import log_erro, log_evento
from soleria.persona.emotions import MotorEmocional
from soleria.screen import (
    ObservadorTela,
    TelaIgnorada,
    TelaIndisponivel,
    mudanca,
)
from soleria.settings import Preferencias
from soleria.ui.chat import ChatUI

__all__ = ["main", "montar_contexto"]


def main():
    preferencias = Preferencias()
    emocoes = MotorEmocional(
        caminho=EMOCAO_ESTADO,
        ativo=bool(preferencias.obter("emocoes")),
        iniciativa=bool(preferencias.obter("proativas")),
    )
    servidor = LlamaServer()
    assistente = Assistant(
        servidor,
        emocoes=emocoes,
        acoes=bool(preferencias.obter("acoes")),
    )
    historico = HistoricoConversa()

    envio_lock = threading.Lock()

    encerrando = threading.Event()

    modo_voz_ativo = threading.Event()
    conversa_voz_ref = [None]
    cancelamento_voz_ref = [None]
    voz_lock = threading.Lock()

    entrada_voz_ref = [None]
    fala_respostas_ref = [None]
    fala_respostas_indisponivel = [False]

    try:
        assistente.definir_relatorios(
            bool(preferencias.obter("relatorios"))
        )
    except Exception as erro:
        log_erro(erro)

    digitando_desde = [None]
    digitando_lock = threading.Lock()

    # Iniciativa própria: no máximo uma mensagem por turno do usuário,
    # com um intervalo mínimo entre tentativas. O ``turno`` invalida uma
    # geração que ficou pronta depois de o usuário mandar outra mensagem.
    proativa_lock = threading.Lock()
    proativa_disponivel = [False]
    ultima_proativa = [None]
    ultima_proativa_em = [0.0]
    turno_conversa = [0]

    # Olhar a tela: uma captura por vez, com intervalo e limite de
    # repetição. A imagem é descartada pelo observador; só o texto fica.
    observador_tela = ObservadorTela()
    tela_lock = threading.Lock()
    ultima_impressao = [None]
    ultima_olhada_em = [time.monotonic()]
    ultimo_comentario_em = [0.0]
    comentarios_tela = deque(maxlen=3)
    tela_avisada = [False]

    # ------------------------------------------------------------------
    # Voz: push-to-talk e fala das respostas
    # ------------------------------------------------------------------

    def obter_fala_respostas():
        if fala_respostas_ref[0] is not None:
            return fala_respostas_ref[0]
        if fala_respostas_indisponivel[0]:
            return None
        try:
            from soleria.voice.reply import FalaRespostas
        except ImportError as erro:
            log_erro(erro)
            fala_respostas_indisponivel[0] = True
            ui.adicionar_externo(
                "Sistema",
                "A fala das respostas precisa de faster-whisper, "
                "sounddevice, numpy e um motor de TTS instalados.",
            )
            return None

        fala_respostas_ref[0] = FalaRespostas(
            obter_motor=lambda: preferencias.obter("tts_motor"),
            ao_erro=lambda texto: ui.adicionar_externo("Sistema", texto),
        )
        return fala_respostas_ref[0]

    def ao_texto_voz(texto):
        auto = bool(preferencias.obter("voz_auto_enviar"))
        ui.definir_texto_entrada(texto, enviar=auto)
        if not auto:
            ui.adicionar_externo(
                "Sistema", "Texto transcrito — revise e aperte Enter."
            )

    def ao_status_voz(texto):
        ui.definir_gravacao(True, texto)

    def ao_aviso_voz(texto):
        ui.adicionar_externo("Sistema", texto)

    def ao_fim_voz():
        ui.definir_gravacao(False)

    def obter_entrada_voz():
        if entrada_voz_ref[0] is not None:
            return entrada_voz_ref[0]
        try:
            from soleria.voice.input import EntradaVoz
        except ImportError as erro:
            log_erro(erro)
            ui.adicionar_externo(
                "Sistema",
                "A gravação por voz precisa de numpy, sounddevice e "
                "faster-whisper instalados.",
            )
            return None

        entrada_voz_ref[0] = EntradaVoz(
            ao_texto=ao_texto_voz,
            ao_status=ao_status_voz,
            ao_aviso=ao_aviso_voz,
            ao_fim=ao_fim_voz,
        )
        return entrada_voz_ref[0]

    def ao_alternar_gravacao():
        if modo_voz_ativo.is_set():
            ui.adicionar_externo(
                "Sistema",
                "O modo de voz contínuo está ativo. Use /voz para "
                "desligá-lo antes de gravar com Tab.",
            )
            return

        entrada = obter_entrada_voz()
        if entrada is None:
            return

        if entrada.ativo:
            ui.definir_gravacao(True, "finalizando gravação…")
            entrada.finalizar()
        elif entrada.iniciar(manter=True):
            ui.definir_gravacao(True, "abrindo microfone…")

    def ao_cancelar_gravacao():
        entrada = entrada_voz_ref[0]
        if entrada is not None:
            entrada.cancelar()
        ui.definir_gravacao(False)

    def ao_parar_gravacao():
        entrada = entrada_voz_ref[0]
        if entrada is None or not entrada.ativo:
            return
        ui.definir_gravacao(True, "finalizando gravação…")
        entrada.finalizar()

    def ao_manter_gravacao(manter):
        entrada = entrada_voz_ref[0]
        if entrada is not None:
            entrada.manter(bool(manter))

    def ao_mudar_config(chave, valor):
        if chave == "acoes":
            assistente.definir_acoes(bool(valor))
            return (
                "Ações no sistema ligadas."
                if valor
                else "Ações no sistema desligadas."
            )

        if chave == "relatorios":
            try:
                assistente.definir_relatorios(bool(valor))
            except Exception as erro:
                log_erro(erro)
                return "Não consegui ligar os relatórios."
            return "Relatórios ligados." if valor else "Relatórios desligados."

        if chave in {"falar_respostas", "falar_streaming", "tts_motor"}:
            fala = fala_respostas_ref[0]
            if chave == "tts_motor" and fala is not None:
                fala.reconfigurar()
            if chave == "falar_respostas":
                if not valor and fala is not None:
                    fala.parar()
                return (
                    "Fala das respostas ligada."
                    if valor
                    else "Fala das respostas desligada."
                )
            return None

        if chave == "emocoes":
            emocoes.definir_ativo(bool(valor))
            ui.atualizar_preferencias()
            if valor:
                return "Estado emocional ligado."
            return "Estado emocional desligado."

        if chave == "proativas":
            emocoes.definir_iniciativa(bool(valor))
            if not valor:
                proativa_disponivel[0] = False
            return (
                "Iniciativa própria ligada."
                if valor
                else "Iniciativa própria desligada."
            )

        if chave == "tela":
            ultima_olhada_em[0] = time.monotonic()
            tela_avisada[0] = False
            if valor:
                disponivel, motivo = observador_tela.disponivel()
                if not disponivel:
                    return f"Olhar a tela ligado, mas {motivo}"
                return "Olhar a tela ligado."
            return "Olhar a tela desligado."

        if chave == "expressoes":
            ui.atualizar_preferencias()
            return None

        if chave == "retrato":
            return "O retrato muda no próximo início."

        return None

    def ao_enviar(texto, cb_stream, cb_status, cb_reset, cancelado):
        turno_conversa[0] += 1
        proativa_disponivel[0] = True
        ultima_olhada_em[0] = time.monotonic()
        with digitando_lock:
            digitando_desde[0] = None

        # Serializa envios para que a ordem do histórico não se misture
        # quando voz e teclado são usados ao mesmo tempo.
        with envio_lock:
            fala = None
            if not modo_voz_ativo.is_set() and preferencias.obter(
                "falar_respostas"
            ):
                servico = obter_fala_respostas()
                if servico is not None and servico.iniciar(
                    streaming=bool(preferencias.obter("falar_streaming"))
                ):
                    fala = servico
                    stream_ui = cb_stream
                    reset_ui = cb_reset

                    def cb_stream(trecho):
                        stream_ui(trecho)
                        fala.adicionar(trecho)

                    def cb_reset():
                        reset_ui()
                        fala.limpar()

            resposta = ""
            try:
                mensagem_usuario, mensagens, versao = (
                    historico.registrar_usuario(texto)
                )

                resposta = assistente.responder(
                    mensagens,
                    callback_stream=cb_stream,
                    callback_status=cb_status,
                    callback_reset=cb_reset,
                    cancelado=cancelado,
                )
                ui.sincronizar_emocao()

                if not resposta:
                    # Cancelado ou vazio: não deixe uma pergunta órfã no
                    # contexto da próxima mensagem.
                    historico.descartar_usuario(mensagem_usuario, versao)
                    return ""

                # Se a conversa foi limpa durante a geração, a resposta não
                # deve entrar no histórico novo.
                conteudo_historico = assistente.ultimo_contexto or resposta
                historico.registrar_assistente(conteudo_historico, versao)
                return resposta
            finally:
                if fala is not None:
                    if resposta and not cancelado.is_set():
                        fala.finalizar(resposta)
                    else:
                        fala.parar()

    def ao_limpar():
        turno_conversa[0] += 1
        proativa_disponivel[0] = False
        ultima_proativa[0] = None
        ultima_proativa_em[0] = 0.0
        ultima_olhada_em[0] = time.monotonic()
        historico.limpar()
        try:
            emocoes.reiniciar()
            emocoes.salvar()
        except Exception as erro:
            log_erro(erro)
        with voz_lock:
            cancelamento = cancelamento_voz_ref[0]
        if cancelamento is not None:
            cancelamento.set()
        entrada = entrada_voz_ref[0]
        if entrada is not None:
            entrada.cancelar()
        fala = fala_respostas_ref[0]
        if fala is not None:
            fala.parar()
        ui.definir_gravacao(False)

    def ao_digitar():
        with digitando_lock:
            if digitando_desde[0] is None:
                digitando_desde[0] = time.monotonic()

    def ao_abrir_relatorios():
        if not assistente.relatorios:
            ui.adicionar_externo(
                "Sistema",
                "Os relatórios estão desativados. Ligue em Ctrl+P › "
                "Configurações.",
            )
            return
        caminho = assistente.abrir_catalogo()
        if caminho:
            ui.adicionar_externo("Sistema", f"Relatórios em {caminho}")
        else:
            ui.adicionar_externo(
                "Sistema", "Não consegui abrir o catálogo de relatórios."
            )

    def ao_olhar_tela():
        """Olhada manual: ignora o intervalo e comenta mesmo sem mudança."""
        disponivel, motivo = observador_tela.disponivel()
        if not disponivel:
            ui.adicionar_externo("Sistema", motivo or "Captura indisponível.")
            return
        if assistente.esta_ocupado():
            ui.adicionar_externo(
                "Sistema", "Espere a resposta atual para eu olhar a tela."
            )
            return
        if not ui.pode_comentar_tela(manual=True):
            ui.adicionar_externo(
                "Sistema",
                "Termine o que está fazendo para eu olhar a tela.",
            )
            return
        if not tela_lock.acquire(blocking=False):
            ui.adicionar_externo("Sistema", "Já estou olhando a tela.")
            return

        ultima_olhada_em[0] = time.monotonic()
        ui.definir_observando(True, "olhando a tela…")
        try:
            threading.Thread(
                target=observar_tela,
                args=(True,),
                name="soleria-tela",
                daemon=True,
            ).start()
        except Exception as erro:
            tela_lock.release()
            ui.definir_observando(False)
            log_erro(erro)

    def observar_tela(manual=False):
        """Captura, lê e comenta; roda numa thread e libera o lock no fim."""
        try:
            if manual:
                ui.definir_observando(True, "olhando a tela…")

            try:
                observacao = observador_tela.observar()
            except TelaIgnorada as motivo:
                log_evento(f"Tela: {motivo}")
                if manual:
                    ui.adicionar_externo(
                        "Sistema", f"Deixei a tela em paz: {motivo}."
                    )
                return
            except TelaIndisponivel as erro:
                log_evento(f"Tela: {erro}")
                if manual or not tela_avisada[0]:
                    tela_avisada[0] = True
                    ui.adicionar_externo(
                        "Sistema", f"Não consegui olhar a tela: {erro}"
                    )
                return

            if not manual:
                anterior = ultima_impressao[0]
                if (
                    anterior is not None
                    and mudanca(anterior, observacao.impressao) < TELA_MUDANCA
                ):
                    log_evento("Tela: sem mudança suficiente")
                    return
                if not TELA_ACORDAR and not servidor.esta_pronto():
                    log_evento("Tela: modelo dormindo; observação adiada")
                    return

            texto = assistente.comentar_tela(
                observacao,
                historico.snapshot(),
                comentarios_tela,
                permitir_acordar=manual or TELA_ACORDAR,
            )
            ultima_impressao[0] = observacao.impressao
            if not texto:
                return
            if comentario_repetido(texto, comentarios_tela):
                log_evento("Tela: comentário repetido descartado")
                return
            if not ui.pode_comentar_tela(manual=manual):
                log_evento("Tela: interface ocupada; comentário descartado")
                return
            if not historico.registrar_espontanea(texto):
                return

            comentarios_tela.append(texto)
            ultimo_comentario_em[0] = time.monotonic()
            ui.adicionar_externo("Soleria", texto)
        except Exception as erro:
            log_erro(erro)
        finally:
            if manual:
                ui.definir_observando(False)
            tela_lock.release()

    def talvez_observar_tela():
        """Dispara uma olhada automática quando o intervalo venceu."""
        if not preferencias.obter("tela"):
            return
        agora = time.monotonic()
        if agora - ultima_olhada_em[0] < TELA_INTERVALO:
            return
        if agora - ultimo_comentario_em[0] < TELA_COOLDOWN:
            return
        if modo_voz_ativo.is_set():
            return
        if assistente.esta_ocupado():
            return
        if not ui.pode_comentar_tela():
            return

        with digitando_lock:
            desde = digitando_desde[0]
        if desde is not None and (agora - desde) < min(15, TIMEOUT_DIGITACAO):
            return

        disponivel, motivo = observador_tela.disponivel()
        if not disponivel:
            if not tela_avisada[0]:
                tela_avisada[0] = True
                ui.adicionar_externo("Sistema", motivo or "Captura indisponível.")
            return

        if not tela_lock.acquire(blocking=False):
            return

        ultima_olhada_em[0] = agora
        try:
            threading.Thread(
                target=observar_tela,
                name="soleria-tela",
                daemon=True,
            ).start()
        except Exception as erro:
            tela_lock.release()
            log_erro(erro)

    def parar_voz():
        modo_voz_ativo.clear()
        proativa_disponivel[0] = False
        with voz_lock:
            conversa = conversa_voz_ref[0]
            conversa_voz_ref[0] = None
            cancelamento = cancelamento_voz_ref[0]
            cancelamento_voz_ref[0] = None
        if cancelamento is not None:
            cancelamento.set()
        if conversa is not None:
            conversa.parar()
        ui.definir_indicador_voz(False)

    def ao_alternar_voz():
        if modo_voz_ativo.is_set():
            parar_voz()
            return

        # O modo contínuo e o push-to-talk não podem disputar o microfone.
        entrada = entrada_voz_ref[0]
        if entrada is not None:
            entrada.cancelar()
        ui.definir_gravacao(False)

        # No modo de voz a própria conversa fala as respostas; evita a
        # fala duplicada do chat.
        fala = fala_respostas_ref[0]
        if fala is not None:
            fala.parar()

        try:
            from soleria.voice import ConversaVoz
        except ImportError as erro:
            log_erro(erro)
            ui.adicionar_externo(
                "Sistema",
                "Módulo de voz indisponível. Instale faster-whisper, "
                "sounddevice, numpy e edge-tts (ou piper-tts, pyttsx3).",
            )
            return

        def ao_transcrever(texto):
            ui.adicionar_externo("Você (voz)", texto)

        def ao_responder(resposta):
            if resposta:
                ui.adicionar_externo("Soleria (voz)", resposta)

        def ao_status(texto):
            ui.definir_indicador_voz(True, texto)

        referencia = [None]
        cancelamento = threading.Event()

        def ao_encerrar(motivo=None):
            with voz_lock:
                # Ignora o encerramento de uma conversa antiga quando o
                # usuário já iniciou outra.
                if conversa_voz_ref[0] is not referencia[0]:
                    return
                conversa_voz_ref[0] = None
                cancelamento_voz_ref[0] = None
            modo_voz_ativo.clear()
            proativa_disponivel[0] = False
            cancelamento.set()
            ui.definir_indicador_voz(False)
            if motivo:
                ui.adicionar_externo("Sistema", motivo)

        def processar_voz(texto, ao_trecho=None, ao_reset=None):
            # Uma nova fala começa "limpa"; /limpar ou a parada do modo
            # de voz cancelam a geração em andamento.
            if not modo_voz_ativo.is_set():
                return ""
            cancelamento.clear()
            return ao_enviar(
                texto,
                cb_stream=ao_trecho,
                cb_status=ao_status,
                cb_reset=ao_reset,
                cancelado=cancelamento,
            )

        try:
            conversa = ConversaVoz(
                processar_voz,
                ao_transcrever=ao_transcrever,
                ao_responder=ao_responder,
                ao_status=ao_status,
                ao_encerrar=ao_encerrar,
            )
        except Exception as erro:
            log_erro(erro)
            ui.adicionar_externo(
                "Sistema", "Não consegui iniciar o modo de voz."
            )
            return

        with voz_lock:
            referencia[0] = conversa
            conversa_voz_ref[0] = conversa
            cancelamento_voz_ref[0] = cancelamento
        modo_voz_ativo.set()
        ui.definir_indicador_voz(True, "iniciando voz...")

        try:
            conversa.iniciar()
        except Exception as erro:
            log_erro(erro)
            ao_encerrar("Não consegui iniciar o modo de voz.")

    ui = ChatUI(
        ao_enviar,
        ao_limpar,
        ao_digitar,
        ao_alternar_voz=ao_alternar_voz,
        ao_abrir_relatorios=ao_abrir_relatorios,
        ao_olhar_tela=ao_olhar_tela,
        ao_gravar_voz=ao_alternar_gravacao,
        ao_cancelar_gravacao=ao_cancelar_gravacao,
        ao_parar_gravacao=ao_parar_gravacao,
        ao_manter_gravacao=ao_manter_gravacao,
        ao_mudar_config=ao_mudar_config,
        preferencias=preferencias,
        retrato=preferencias.obter("retrato"),
        emocoes=emocoes,
    )

    def tentar_iniciativa(ocioso):
        """Dispara uma tentativa de puxar assunto, sem bloquear o monitor."""
        if not preferencias.obter("proativas"):
            return
        if not proativa_disponivel[0]:
            return
        if ocioso < TEMPO_PROATIVA:
            return
        if ocioso >= TEMPO_INATIVIDADE:
            return

        agora = time.monotonic()
        if (
            ultima_proativa_em[0]
            and (agora - ultima_proativa_em[0]) < COOLDOWN_PROATIVA
        ):
            return
        if not ui.pode_receber_proativa():
            return

        # Não vale a pena subir o modelo só para puxar assunto. Se ele já
        # foi encerrado, o silêncio também faz parte da conversa.
        esta_pronto = getattr(servidor, "esta_pronto", None)
        if callable(esta_pronto) and not esta_pronto():
            return
        if not proativa_lock.acquire(blocking=False):
            return

        turno = turno_conversa[0]
        ultima = ultima_proativa[0]

        def gerar():
            try:
                mensagens = historico.snapshot()
                texto = assistente.iniciativa(
                    mensagens, ultima_proativa=ultima
                )
                if not texto or encerrando.is_set():
                    return
                if turno_conversa[0] != turno:
                    return
                if not proativa_disponivel[0]:
                    return
                if not ui.pode_receber_proativa():
                    return
                if not historico.registrar_iniciativa(texto):
                    return

                proativa_disponivel[0] = False
                ultima_proativa[0] = texto
                ultima_proativa_em[0] = time.monotonic()
                ui.adicionar_externo("Soleria", texto)
            except Exception as erro:
                log_erro(erro)
            finally:
                # Mesmo quando o modelo escolhe silêncio, espere antes de
                # tentar de novo: não transforme a iniciativa em ruído.
                ultima_proativa_em[0] = time.monotonic()
                proativa_lock.release()

        try:
            threading.Thread(
                target=gerar,
                name="soleria-iniciativa",
                daemon=True,
            ).start()
        except Exception as erro:
            log_erro(erro)
            ultima_proativa_em[0] = time.monotonic()
            proativa_lock.release()

    def monitorar_tela():
        while not encerrando.wait(5):
            try:
                talvez_observar_tela()
            except Exception as erro:
                log_erro(erro)

    def monitorar_inatividade():
        while not encerrando.wait(3):
            ui.atualizar_ocio()
            if modo_voz_ativo.is_set():
                continue

            with digitando_lock:
                desde = digitando_desde[0]

            digitando_ativo = (
                desde is not None
                and (time.monotonic() - desde) < TIMEOUT_DIGITACAO
            )

            if assistente.esta_ocupado() or digitando_ativo:
                continue

            ocioso = assistente.tempo_ocioso()
            if ocioso >= TEMPO_INATIVIDADE:
                if not proativa_lock.locked():
                    servidor.encerrar()
                continue

            tentar_iniciativa(ocioso)

    def handle_sigterm(signum, frame):
        # Handlers de sinal devem apenas sinalizar; a limpeza acontece no
        # fluxo principal (final do main).
        encerrando.set()
        ui.parar()

    try:
        signal.signal(signal.SIGTERM, handle_sigterm)
    except (ValueError, OSError):
        pass

    atexit.register(servidor.encerrar)
    atexit.register(assistente.fechar)
    atexit.register(emocoes.salvar)

    monitor = threading.Thread(
        target=monitorar_inatividade,
        name="soleria-inatividade",
        daemon=True,
    )
    monitor.start()

    monitor_tela = threading.Thread(
        target=monitorar_tela,
        name="soleria-tela-agenda",
        daemon=True,
    )
    monitor_tela.start()

    try:
        if not encerrando.is_set():
            ui.run()
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        encerrando.set()
        parar_voz()
        entrada = entrada_voz_ref[0]
        if entrada is not None:
            entrada.fechar()
        fala = fala_respostas_ref[0]
        if fala is not None:
            fala.fechar()
        servidor.encerrar()
        assistente.fechar()
        emocoes.salvar()
        log_evento("Soleria encerrada")
        print(f"\n[{NOME}] Até logo!")
