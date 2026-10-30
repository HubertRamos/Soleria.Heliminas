"""Configuração central da Soleria.

Todos os valores podem ser sobrescritos por variáveis de ambiente, sem
precisar editar este arquivo. Os caminhos aceitam ``~`` e variáveis de shell.
"""

import os
from pathlib import Path


def _env_int(nome: str, padrao: int) -> int:
    try:
        return int(os.getenv(nome, str(padrao)))
    except (TypeError, ValueError):
        return padrao


def _env_float(nome: str, padrao: float) -> float:
    try:
        return float(os.getenv(nome, str(padrao)))
    except (TypeError, ValueError):
        return padrao


def _env_path(nome: str, padrao: Path) -> Path:
    valor = os.getenv(nome)
    if not valor:
        return padrao
    # O docstring do módulo promete ``~`` e variáveis de shell.
    return Path(os.path.expandvars(valor)).expanduser()


def _env_bool(nome: str, padrao: bool) -> bool:
    valor = os.getenv(nome)
    if valor is None:
        return padrao
    return valor.strip().casefold() in {"1", "true", "sim", "yes", "on"}


NOME = "Soleria"

# ----------------------------------------------------------------------
# Modelo local
# ----------------------------------------------------------------------

LLAMA_DIR = _env_path("SOLERIA_LLAMA_DIR", Path.home() / "llama.cpp")
LLAMA_SERVER = LLAMA_DIR / "build" / "bin" / "llama-server"

MODELO = _env_path(
    "SOLERIA_MODEL_PATH",
    Path.home() / "Modelos" / "qwen2.5-7b-instruct-q3_k_m.gguf",
)

HOST = os.getenv("SOLERIA_HOST", "127.0.0.1")
PORTA = _env_int("SOLERIA_PORT", 8080)
BASE_URL = f"http://{HOST}:{PORTA}/v1"

TEMPO_INATIVIDADE = _env_int("SOLERIA_IDLE_SECONDS", 120)
TEMPO_INICIALIZACAO = _env_int("SOLERIA_STARTUP_TIMEOUT", 90)
CONTEXTO = _env_int("SOLERIA_CONTEXT_SIZE", 8192)
CAMADAS_GPU = _env_int("SOLERIA_GPU_LAYERS", 99)
TEMPERATURA = _env_float("SOLERIA_TEMPERATURE", 0.2)

# Tempo máximo de uma requisição ao llama-server. Respostas longas em CPU
# podem demorar, por isso o padrão é generoso.
TIMEOUT_REQUISICAO = _env_float("SOLERIA_REQUEST_TIMEOUT", 300.0)

LOG = _env_path("SOLERIA_LOG", Path.home() / "soleria-llama-server.log")

# ----------------------------------------------------------------------
# Histórico e geração
# ----------------------------------------------------------------------

# Número máximo de mensagens (usuário + assistente) enviadas ao modelo.
MAX_HISTORICO = _env_int("SOLERIA_MAX_HISTORY", 12)

MAX_TOKENS_DECISAO = _env_int("SOLERIA_MAX_TOKENS_DECISAO", 400)
MAX_TOKENS_RESPOSTA = _env_int("SOLERIA_MAX_TOKENS_RESPOSTA", 400)

# ----------------------------------------------------------------------
# Pesquisa web
# ----------------------------------------------------------------------

MAX_RESULTADOS_BUSCA = _env_int("SOLERIA_MAX_SEARCH_RESULTS", 5)
TIMEOUT_PESQUISA = _env_float("SOLERIA_SEARCH_TIMEOUT", 15.0)
MAX_CARACTERES_RESUMO = _env_int("SOLERIA_MAX_SNIPPET_CHARS", 700)
MAX_CARACTERES_CONSULTA = _env_int("SOLERIA_MAX_QUERY_CHARS", 300)
MAX_CARACTERES_PERGUNTA = _env_int("SOLERIA_MAX_QUESTION_CHARS", 500)

# Quantas consultas o modelo pode encadear na mesma resposta (a primeira
# mais eventuais refinamentos).
MAX_RODADAS_PESQUISA = _env_int("SOLERIA_MAX_SEARCH_ROUNDS", 2)

# Leitura do conteúdo dos links encontrados. Zero desliga a leitura.
MAX_PAGINAS = _env_int("SOLERIA_MAX_PAGES", 3)
TIMEOUT_PAGINA = _env_float("SOLERIA_PAGE_TIMEOUT", 8.0)
MAX_CARACTERES_PAGINA = _env_int("SOLERIA_MAX_PAGE_CHARS", 900)
MAX_BYTES_PAGINA = _env_int("SOLERIA_MAX_PAGE_BYTES", 2_000_000)
# Orçamento total das fontes no prompt, para não estourar o contexto.
MAX_CARACTERES_FONTES = _env_int("SOLERIA_MAX_SOURCES_CHARS", 4000)

# ----------------------------------------------------------------------
# Relatórios em HTML
# ----------------------------------------------------------------------

# Quando ligado, toda pesquisa gera ou atualiza um relatório em HTML e o
# chat recebe apenas o caminho do arquivo.
RELATORIOS_ATIVOS = _env_bool("SOLERIA_REPORTS", True)
PASTA_RELATORIOS = _env_path("SOLERIA_REPORTS_DIR", Path.home() / "soleria-relatorios")

# Quantos relatórios existentes são enviados ao modelo para ele decidir se
# a pesquisa nova encaixa em algum deles.
MAX_CANDIDATOS_RELATORIO = _env_int("SOLERIA_REPORT_CANDIDATES", 3)

# O relatório precisa de mais espaço de geração que uma resposta curta.
MAX_TOKENS_RELATORIO = _env_int("SOLERIA_MAX_TOKENS_REPORT", 600)

# Orçamento total (instruções + pedido) do prompt do relatório. A conta usa
# 2,5 caracteres por token como estimativa conservadora para o português e
# desconta o espaço reservado para a geração, para o pedido não estourar o
# contexto do modelo.
MAX_CARACTERES_PROMPT_RELATORIO = _env_int(
    "SOLERIA_MAX_REPORT_PROMPT_CHARS",
    max(1800, int((CONTEXTO - MAX_TOKENS_RELATORIO) * 2.5)),
)

# Orçamento de fontes específico do relatório. É menor que o da resposta
# normal porque o prompt do relatório também carrega o resumo dos arquivos
# existentes. O valor efetivo é recalculado a partir do orçamento acima.
MAX_CARACTERES_FONTES_RELATORIO = _env_int("SOLERIA_MAX_REPORT_SOURCES_CHARS", 1600)
MAX_CARACTERES_RESUMO_RELATORIO = _env_int("SOLERIA_REPORT_SUMMARY_CHARS", 600)

# Similaridade mínima (0 a 1) para um relatório existente ser considerado
# candidato. Abaixo disso, a pesquisa cria um relatório novo.
LIMIAR_RELATORIO = _env_float("SOLERIA_REPORT_MATCH_THRESHOLD", 0.25)

# ----------------------------------------------------------------------
# Ações locais
# ----------------------------------------------------------------------

# Permite pedidos como "abre o Firefox no YouTube". Somente aplicativos e
# sites conhecidos são aceitos: a detecção de linguagem natural não vira um
# executor de comandos arbitrários.
ACOES_ATIVAS = _env_bool("SOLERIA_ACTIONS", True)

# Aplicativos extras no formato "alias=comando", separados por ";" ou ",".
# Exemplo: SOLERIA_APPS="lapce=lapce, code=flatpak run com.visualstudio.code"
APLICATIVOS_PERSONALIZADOS = os.getenv("SOLERIA_APPS", "")

# ----------------------------------------------------------------------
# Interface
# ----------------------------------------------------------------------

INTERVALO_INVALIDATE = 0.03

# Como o retrato é desenhado: "auto" usa o protocolo gráfico do Kitty
# quando disponível e cai nos blocos Unicode no restante. "kitty" força o
# protocolo (com passthrough quando dentro do tmux) e "blocos" desliga.
IMAGEM_RETRATO = os.getenv("SOLERIA_IMAGEM", "auto").strip().casefold()

# Tempo em que "usuário digitando" conta como atividade, sem reter o modelo
# para sempre se o usuário abandonar o terminal aberto.
TIMEOUT_DIGITACAO = _env_int("SOLERIA_TYPING_TIMEOUT", 300)

# ----------------------------------------------------------------------
# Emoções
# ----------------------------------------------------------------------

# O estado emocional é local e persistente: valência, energia, paciência,
# curiosidade e afinidade sobrevivem entre execuções.
EMOCOES_ATIVAS = _env_bool("SOLERIA_EMOTIONS", True)
EMOCAO_ESTADO = _env_path(
    "SOLERIA_EMOTION_STATE",
    Path.home() / ".local" / "state" / "soleria" / "emocao.json",
)

# Iniciativa própria: depois de um tempo sem conversa, a Soleria pode puxar
# um assunto ligado ao que já foi falado. O silêncio continua sendo a
# resposta padrão quando não há nada que valha a pena dizer.
PROATIVAS_ATIVAS = _env_bool("SOLERIA_PROACTIVE", True)
TEMPO_PROATIVA = min(
    _env_int("SOLERIA_PROACTIVE_SECONDS", 75),
    max(5, TEMPO_INATIVIDADE - 15),
)
COOLDOWN_PROATIVA = _env_int("SOLERIA_PROACTIVE_COOLDOWN", 180)
MAX_TOKENS_PROATIVA = _env_int("SOLERIA_MAX_TOKENS_PROACTIVE", 160)
MAX_CARACTERES_PROATIVA = _env_int("SOLERIA_PROACTIVE_MAX_CHARS", 320)

# ----------------------------------------------------------------------
# Olhar a tela (captura + OCR)
# ----------------------------------------------------------------------

# A Soleria captura a tela de tempos em tempos, extrai o texto com OCR e
# comenta o que o Hubert está fazendo. A imagem não é guardada nem enviada
# para fora: só o texto reconhecido entra no prompt do modelo local.
TELA_ATIVA = _env_bool("SOLERIA_SCREEN", True)

# Intervalo entre capturas automáticas (segundos). O comentário só acontece
# se o texto da tela tiver mudado o suficiente desde a última olhada.
# No modelo de 7B em CPU cada olhada custa cerca de um minuto; 15 minutos
# deixam o recurso utilizável sem ocupar a máquina o tempo todo.
TELA_INTERVALO = max(30, _env_int("SOLERIA_SCREEN_SECONDS", 900))

# Fração do texto que precisa mudar para valer um comentário novo (0 a 1).
# Relógio, porcentagem de bateria e barras de progresso ficam abaixo disso.
TELA_MUDANCA = min(0.9, max(0.02, _env_float("SOLERIA_SCREEN_CHANGE", 0.20)))

# Teto de texto reconhecido enviado ao modelo e de caracteres do comentário.
TELA_MAX_CARACTERES = _env_int("SOLERIA_SCREEN_OCR_CHARS", 1000)
TELA_MAX_RESPOSTA = _env_int("SOLERIA_SCREEN_MAX_CHARS", 300)
MAX_TOKENS_TELA = _env_int("SOLERIA_MAX_TOKENS_SCREEN", 80)

# Espera mínima entre dois comentários, mesmo que a tela mude rápido.
TELA_COOLDOWN = _env_int("SOLERIA_SCREEN_COOLDOWN", 300)

# Subir o modelo para olhar a tela custa CPU e memória. Com False, a
# Soleria só comenta quando o modelo já estiver no ar por outro motivo.
TELA_ACORDAR = _env_bool("SOLERIA_SCREEN_WAKE", True)

# Aplicativos que nunca devem ser olhados (ids do umbriel/wayland, separados
# por vírgula). Útil para gerenciadores de senha e janelas privadas.
TELA_APPS_OCULTOS = tuple(
    item.strip().casefold()
    for item in os.getenv("SOLERIA_SCREEN_IGNORE", "").split(",")
    if item.strip()
)

OCR_IDIOMAS = os.getenv("SOLERIA_OCR_LANGS", "por+eng")
OCR_TIMEOUT = _env_float("SOLERIA_OCR_TIMEOUT", 25.0)
CAPTURA_TIMEOUT = _env_float("SOLERIA_SCREEN_TIMEOUT", 20.0)

# ----------------------------------------------------------------------
# Voz
# ----------------------------------------------------------------------

MODELO_STT = os.getenv("SOLERIA_STT_MODEL", "small")
IDIOMA_STT = os.getenv("SOLERIA_STT_LANGUAGE", "pt")
MOTOR_TTS = os.getenv("SOLERIA_TTS_ENGINE", "edge")
PIPER_VOZ = _env_path(
    "SOLERIA_PIPER_VOICE",
    Path.home() / "Modelos" / "piper" / "dii_pt-BR.onnx",
)

# Fala em streaming: a Soleria começa a falar enquanto o modelo ainda está
# gerando a resposta. Este é o tamanho máximo de um trecho falado sem
# pontuação final (para não ficar esperando o fim de um parágrafo longo).
FALA_TRECHO_MAX = _env_int("SOLERIA_TTS_CHUNK_CHARS", 220)
