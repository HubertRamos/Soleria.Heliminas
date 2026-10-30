# Soleria — IA local modular

Terminal de conversa com um modelo local servido pelo `llama-server`, interface
`prompt_toolkit`, streaming real, pesquisa web com `ddgs`, voz opcional
(STT + TTS) e um retrato em ASCII/Pillow que muda de expressão conforme o tom da
conversa.

## Estrutura

```text
main.py
config.py
personality.py          # fachada de compatibilidade para soleria.persona
soleria/
  __main__.py           # permite `python -m soleria`
  app.py                # coordenação, histórico e inatividade
  logging_utils.py
  persona/
    identidade.py       # quem ela é
    valores.py          # o que ela valoriza
    estilo.py           # como ela fala
    limites.py          # o que ela não faz
    convivencia.py      # relação, humor e iniciativa
    lexico.py           # pistas afetivas do texto
    emotions.py         # estado emocional, appraisal e persistência
    composer.py         # montagem da persona por etapa
  core/
    actions.py          # aplicativos, sites e caminhos por linguagem natural
    assistant.py        # orquestra decisão, pesquisa e resposta
    commands.py         # comandos internos trocados com o modelo
    context.py          # montagem do contexto e orçamento de texto
    history.py          # histórico da conversa
    intents.py          # detecção de intenções em linguagem natural
    initiative.py       # mensagens de iniciativa própria
    prompts.py          # prompts de sistema de cada etapa
    reporting.py        # escolha, gravação e leitura de relatórios
    screen.py           # pedido e limpeza do comentário sobre a tela
  llm/
    server.py           # ciclo de vida do llama-server
    client.py           # cliente OpenAI local com streaming
  search/
    web.py              # pesquisa e normalização das fontes
    pages.py            # leitura do conteúdo dos links encontrados
  screen/
    capture.py          # captura via portal Wayland (e alternativas)
    ocr.py              # tesseract e limpeza do texto reconhecido
    windows.py          # janela em foco para dar contexto
    observer.py         # junta captura, OCR e filtros de privacidade
  reports/
    paths.py            # nomes de arquivos e versão do formato
    text.py             # utilitários de texto, slugs e URLs
    model.py            # modelo de relatório e fontes
    store.py            # armazenamento, catálogo e busca
    format.py           # representação compacta para os prompts
    render.py           # HTML seguro dos relatórios
    styles.py           # CSS embutido no HTML
  settings.py           # preferências persistentes do menu
  ui/
    chat.py             # TUI, teclas e laço principal
    menu.py             # paleta de comandos e menu de configurações
    portrait.py         # retrato e expressões no painel
    kitty.py            # protocolo de imagens do Kitty
    text.py             # largura, quebra e corte de texto
    theme.py            # paleta, humores e estilos
    expressions.py      # classificação de emoção pelo texto
    expressoes/         # imagens dos retratos
  voice/
    config.py           # ajustes de áudio, STT e TTS
    stt.py              # transcrição com faster-whisper
    tts.py              # motores Edge, Piper e pyttsx3
    speech.py           # fala em streaming e preparação do texto
    listener.py         # microfone e VAD por energia
    input.py            # gravação push-to-talk (Tab)
    reply.py            # fala das respostas do chat
    conversation.py     # ciclo ouvir → responder → falar
tests/test_soleria.py   # testes offline
```

- `config.py`: caminhos, porta, modelo, limites e tempos. Tudo pode ser
  sobrescrito por variáveis de ambiente.
- `soleria/persona/`: identidade, valores, estilo, limites e convivência
  separados por responsabilidade, além do motor emocional. `personality.py`
  continua exportando `PERSONALIDADE` para imports antigos.
- `soleria/app.py`: integra os componentes, mantém o histórico e desliga o
  modelo após inatividade.
- `soleria/core/assistant.py`: orquestra a conversa; a detecção de comandos,
  intenções, montagem de contexto e fluxo de relatórios fica nos módulos
  vizinhos de `core/`.
- `soleria/core/history.py`: mantém as mensagens e controla o que entra no
  contexto da próxima resposta.
- `soleria/core/initiative.py`: monta e valida as mensagens de iniciativa,
  escolhendo ganchos concretos na conversa e preferindo o silêncio quando não
  há nada contextual para dizer.
- `soleria/core/reporting.py`: decide quando lembrar, gravar ou ler um
  relatório e sincroniza o cliente usado nessa etapa.
- `soleria/llm/server.py`: inicia, verifica e encerra o `llama-server` somente
  se foi esta aplicação que o iniciou.
- `soleria/llm/client.py`: cliente compatível com OpenAI, com cancelamento
  durante o streaming.
- `soleria/search/web.py`: pesquisa, normalização, leitura dos links e
  formatação das fontes (deduplicadas e com conteúdo limitado).
- `soleria/search/pages.py`: abre os links encontrados, extrai o texto
  visível das páginas e bloqueia endereços locais/privados.
- `soleria/reports/store.py`: cria e atualiza os relatórios, mantém o
  catálogo e procura assuntos parecidos nos metadados.
- `soleria/reports/render.py`: gera o HTML do relatório e do catálogo com
  conteúdo escapado e CSS embutido em `styles.py`.
- `soleria/reports/model.py`: carrega e normaliza os dados de um relatório,
  incluindo a compatibilidade com o formato antigo.
- `soleria/ui/chat.py`: interface de terminal, teclas e laço de desenho; o
  retrato e as utilidades de layout ficam em `portrait.py`, `kitty.py`,
  `text.py` e `theme.py`, e a paleta/menu em `menu.py`.
- `soleria/settings.py`: definições e persistência das preferências alteradas
  pelo menu de configurações.
- `soleria/voice/`: conversa por voz dividida entre transcrição (`stt.py`),
  síntese (`tts.py`), fala em streaming (`speech.py`), captura com VAD
  (`listener.py`), gravação push-to-talk (`input.py`), fala das respostas do
  chat (`reply.py`) e o ciclo completo (`conversation.py`).

## Persona e emoções

A persona é montada por etapa: decisão e resposta final recebem identidade,
valores, estilo, limites e convivência; leitura e relatório recebem uma versão
compacta. O texto fica em módulos pequenos em `soleria/persona/`, e a composição
é cacheada.

O `MotorEmocional` mantém um estado interno determinístico e offline:
valência, energia, confiança, paciência, curiosidade, vontade social, afinidade
e intensidade. Cada mensagem e cada evento do pipeline (pesquisa, erro,
relatório, leitura, cancelamento) altera esse estado; o tempo faz o humor
decair. A expressão do retrato e uma diretriz curta no prompt saem do mesmo
estado, então o tom da resposta e a imagem não ficam contraditórios.

### Iniciativa própria

Depois de um tempo de silêncio, a Soleria pode puxar assunto sozinha — mas
não de forma aleatória. O pedido de iniciativa leva a conversa recente, os
ganchos que ficaram em aberto (perguntas, planos, algo que o usuário começou
a explicar) e a última iniciativa. O modelo responde `[[SILENCIO]]` quando
não há nada que valha a pena; caso contrário, escreve no máximo duas frases
ligadas a um detalhe concreto.

A tentativa só acontece quando:

- a preferência **Iniciativa própria** está ligada (padrão: ligada);
- o modelo ainda está no ar (a iniciativa não sobe o modelo só para falar);
- a interface não está em menu, gravação, voz, streaming ou com texto sendo
  digitado;
- a última mensagem é da Soleria e não termina com uma pergunta sem resposta;
- já passou o intervalo mínimo desde a última tentativa.

É no máximo uma mensagem por turno do usuário. Se o Hubert mandar outra
mensagem enquanto a iniciativa está sendo gerada, ela é descartada.

### Olhar a tela

A Soleria pode olhar o monitor de tempos em tempos e comentar o que você está
fazendo. Funciona 100% local:

1. **Captura.** Uma foto da tela é tirada pelo portal do Wayland
   (`org.freedesktop.portal.Screenshot`), sem janela de confirmação. Há
   alternativas para outros ambientes (`noctalia`, `grim`, `gnome-screenshot`,
   `spectacle`, ImageMagick `import`, `scrot`).
2. **Leitura.** O texto visível é reconhecido por OCR com o `tesseract`
   (idiomas `por+eng`, caindo para `por` quando o `eng` não está instalado).
   Também entra o título da janela em foco, que dá contexto sem custo.
3. **Filtros.** A captura é descartada se a janela em foco for a própria
   Soleria, se o aplicativo estiver na lista de ocultos ou se o texto parecer
   conter credenciais.
4. **Comparação.** O texto novo é comparado com o da última olhada. Relógio,
   bateria e barras de progresso não contam como mudança; sem mudança
   suficiente, nada é enviado ao modelo.
5. **Comentário.** O modelo recebe o texto reconhecido e os últimos comentários
   (para não repetir) e decide entre escrever uma ou duas frases ou ficar em
   silêncio com `[[SILENCIO]]`.

A imagem existe só em memória e é descartada depois do OCR: nada é salvo em
disco nem enviado para fora. O recurso fica na preferência **Olhar a tela**
(padrão: ligada) e pode ser chamado na hora com `/olhar`. Enquanto a Soleria
observa, o título do terminal mostra um 👁.

Cada olhada custa cerca de um minuto de CPU no modelo de 7B, então o padrão é
uma captura a cada 15 minutos, com pelo menos 5 minutos entre comentários. Se o
modelo estiver desligado, ele só é acordado para uma olhada automática se
`SOLERIA_SCREEN_WAKE` estiver ligado (padrão).

Requer o `tesseract` instalado com o idioma português:

```bash
sudo pacman -S tesseract tesseract-data-por  # Arch
sudo apt install tesseract-ocr tesseract-ocr-por  # Debian/Ubuntu
```

## Ações no sistema

A Soleria reconhece pedidos diretos para abrir aplicativos, sites e arquivos,
tanto no chat quanto no modo de voz:

```text
soleria, abre o Firefox para mim no YouTube
abre o Chrome no GitHub
abre o YouTube
abre o código na pasta ~/Projetos/soleria
abre o nvim na pasta ~/Projetos/soleria
abre o gerenciador de arquivos em ~/Downloads
abre o GIMP na imagem ~/fotos/gato.png
abre o Krita em ~/desenhos/ideia.kra
abre o gerenciador de arquivos
```

O pedido é resolvido antes de o modelo ser acionado, então a resposta é
imediata. A detecção é propositalmente conservadora:

- o verbo de abertura precisa estar no começo da frase (`abre`, `abra`,
  `inicia`, `executa`, `lança`, `entra` etc.);
- aplicativos conhecidos: Firefox, Firefox Developer Edition, Chrome,
  Chromium, Brave, Edge, Opera, Vivaldi, editor de código (o primeiro
  instalado entre VS Code, VSCodium, Cursor, Zed, Sublime Text, Kate, gedit,
  Geany e Atom), Neovim, Vim, micro, nano, Helix, PyCharm, IntelliJ IDEA,
  Android Studio, gerenciador de arquivos (Nautilus, Dolphin, Thunar, Nemo,
  PCManFM, Caja), GIMP, Krita, Inkscape, Pinta e o navegador padrão;
- editores de terminal (Neovim, Vim, micro, nano e Helix) são abertos dentro
  do primeiro emulador disponível: Kitty, Alacritty, Foot, Ghostty, WezTerm,
  GNOME Terminal, Konsole, XFCE Terminal, Terminator, Tilix, xterm, urxvt
  ou st;
- quando nenhum editor gráfico está instalado, “abre o código na pasta X”
  cai para Neovim, Vim, micro, Helix ou nano, nessa ordem;
- sites conhecidos, URLs `http(s)` e domínios explícitos continuam
  funcionando;
- para pastas e arquivos, use `~/...`, `/...`, `./...`, `../...` ou um
  caminho relativo com barra (`Projetos/app`); caminhos com espaços podem ir
  entre aspas;
- o caminho precisa existir; se não existir, a Soleria avisa em vez de abrir
  o aplicativo no lugar errado;
- pedidos com “relatório” continuam no fluxo de leitura da Soleria;
- nada é executado por shell: o aplicativo recebe o caminho ou a URL como
  argumento.

Se o aplicativo não estiver instalado, a Soleria tenta abrir o destino no
aplicativo padrão do sistema (`xdg-open`) ou no navegador padrão e avisa. O
recurso pode ser desligado em `F2` › **Abrir aplicativos** ou com
`SOLERIA_ACTIONS=0`.

Para cadastrar um aplicativo que não está na lista, use `SOLERIA_APPS`:

```bash
export SOLERIA_APPS="lapce=lapce, code=flatpak run com.visualstudio.code"
```

Depois é só pedir “abre o lapce na pasta ~/Projetos/app” ou “abre o code na
pasta ~/Projetos/app”. O alias é o nome que você fala; o valor é o comando
usado, com argumentos opcionais e sem shell. Separe os itens com `,` ou `;`.

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
python main.py   # ou: python -m soleria
```

O ambiente virtual existente do projeto também funciona:

```bash
source .venv/bin/activate
python main.py
```

## Caminhos padrão

O projeto espera:

- `~/llama.cpp/build/bin/llama-server`
- `~/Modelos/qwen2.5-7b-instruct-q3_k_m.gguf`

Se forem diferentes, use variáveis de ambiente (veja abaixo) ou edite
`config.py`. O servidor é iniciado sob demanda e encerrado depois de 120
segundos sem atividade.

Para testar outro modelo sem mudar o padrão, use o script:

```bash
./testar-modelo.sh ~/Modelos/LFM3-Omni-2B-Q8_0.gguf
```

Sem argumento, ele usa `~/Modelos/LFM3-Omni-2B-Q8_0.gguf`. O caminho também
pode ser passado direto por `SOLERIA_MODEL_PATH=... python main.py`.

## Variáveis de ambiente

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `SOLERIA_LLAMA_DIR` | `~/llama.cpp` | Raiz do llama.cpp |
| `SOLERIA_MODEL_PATH` | `~/Modelos/qwen2.5-7b-instruct-q3_k_m.gguf` | Modelo GGUF |
| `SOLERIA_HOST` / `SOLERIA_PORT` | `127.0.0.1` / `8080` | Endereço do servidor |
| `SOLERIA_CONTEXT_SIZE` | `8192` | Contexto do modelo (um único slot; ver nota abaixo) |
| `SOLERIA_GPU_LAYERS` | `99` | Camadas na GPU |
| `SOLERIA_TEMPERATURE` | `0.2` | Temperatura de geração |
| `SOLERIA_IDLE_SECONDS` | `120` | Inatividade até desligar o modelo |
| `SOLERIA_STARTUP_TIMEOUT` | `90` | Tempo máximo de inicialização |
| `SOLERIA_REQUEST_TIMEOUT` | `300` | Tempo máximo de cada requisição ao modelo |
| `SOLERIA_TYPING_TIMEOUT` | `300` | Tempo em que digitar conta como atividade |
| `SOLERIA_MAX_HISTORY` | `12` | Mensagens mantidas no contexto |
| `SOLERIA_MAX_TOKENS_DECISAO` | `400` | Limite da etapa de decisão/resposta direta |
| `SOLERIA_MAX_TOKENS_RESPOSTA` | `400` | Limite de tokens da resposta |
| `SOLERIA_MAX_SEARCH_RESULTS` | `5` | Resultados por pesquisa |
| `SOLERIA_MAX_SNIPPET_CHARS` | `700` | Tamanho máximo do resumo de cada resultado |
| `SOLERIA_MAX_QUERY_CHARS` | `300` | Tamanho máximo de uma consulta de pesquisa |
| `SOLERIA_SEARCH_TIMEOUT` | `15` | Timeout da pesquisa (segundos) |
| `SOLERIA_MAX_SEARCH_ROUNDS` | `2` | Consultas encadeadas por resposta |
| `SOLERIA_MAX_QUESTION_CHARS` | `500` | Limite da pergunta de esclarecimento |
| `SOLERIA_MAX_PAGES` | `3` | Links abertos por pesquisa (0 desliga) |
| `SOLERIA_PAGE_TIMEOUT` | `8` | Timeout ao abrir cada link |
| `SOLERIA_MAX_PAGE_CHARS` | `900` | Texto aproveitado de cada página |
| `SOLERIA_MAX_PAGE_BYTES` | `2000000` | Bytes máximos baixados por link |
| `SOLERIA_MAX_SOURCES_CHARS` | `4000` | Total de fontes enviado ao modelo |
| `SOLERIA_REPORTS` | `1` | Liga/desliga os relatórios em HTML |
| `SOLERIA_REPORTS_DIR` | `~/soleria-relatorios` | Pasta dos relatórios |
| `SOLERIA_ACTIONS` | `1` | Liga/desliga abrir aplicativos e sites pelo chat |
| `SOLERIA_APPS` | vazio | Aplicativos extras no formato `alias=comando`, separados por `,` ou `;` |
| `SOLERIA_REPORT_CANDIDATES` | `3` | Relatórios existentes avaliados por pesquisa |
| `SOLERIA_MAX_TOKENS_REPORT` | `600` | Limite de tokens do relatório |
| `SOLERIA_MAX_REPORT_PROMPT_CHARS` | automático | Orçamento de caracteres do prompt do relatório |
| `SOLERIA_MAX_REPORT_SOURCES_CHARS` | `1600` | Teto de fontes enviadas ao prompt do relatório |
| `SOLERIA_REPORT_SUMMARY_CHARS` | `600` | Tamanho máximo do resumo |
| `SOLERIA_REPORT_MATCH_THRESHOLD` | `0.25` | Similaridade mínima para reutilizar um relatório |
| `SOLERIA_LOG` | `~/soleria-llama-server.log` | Log de eventos/erros |
| `SOLERIA_PREFS` | `~/.config/soleria/preferencias.json` | Arquivo de preferências do menu |
| `SOLERIA_EMOTIONS` | `1` | Liga/desliga o estado emocional |
| `SOLERIA_EMOTION_STATE` | `~/.local/state/soleria/emocao.json` | Estado emocional persistido |
| `SOLERIA_PROACTIVE` | `1` | Liga/desliga a iniciativa própria |
| `SOLERIA_PROACTIVE_SECONDS` | `75` | Silêncio antes de tentar puxar assunto |
| `SOLERIA_PROACTIVE_COOLDOWN` | `180` | Intervalo mínimo entre tentativas |
| `SOLERIA_MAX_TOKENS_PROACTIVE` | `160` | Limite de tokens da iniciativa |
| `SOLERIA_PROACTIVE_MAX_CHARS` | `320` | Tamanho máximo da mensagem de iniciativa |
| `SOLERIA_SCREEN` | `1` | Liga/desliga o olhar para a tela |
| `SOLERIA_SCREEN_SECONDS` | `900` | Intervalo entre capturas automáticas |
| `SOLERIA_SCREEN_CHANGE` | `0.20` | Fração do texto que precisa mudar para comentar |
| `SOLERIA_SCREEN_COOLDOWN` | `300` | Intervalo mínimo entre comentários |
| `SOLERIA_SCREEN_WAKE` | `1` | Acordar o modelo para uma olhada automática |
| `SOLERIA_SCREEN_OCR_CHARS` | `1000` | Teto de texto reconhecido enviado ao modelo |
| `SOLERIA_SCREEN_MAX_CHARS` | `300` | Tamanho máximo do comentário |
| `SOLERIA_MAX_TOKENS_SCREEN` | `80` | Limite de tokens do comentário |
| `SOLERIA_SCREEN_IGNORE` | vazio | Aplicativos ignorados, separados por vírgula |
| `SOLERIA_OCR_LANGS` | `por+eng` | Idiomas do tesseract |
| `SOLERIA_OCR_TIMEOUT` | `25` | Timeout do OCR (segundos) |
| `SOLERIA_SCREEN_TIMEOUT` | `20` | Timeout da captura (segundos) |
| `SOLERIA_IMAGEM` | `auto` | Retrato inicial: `auto`, `kitty` ou `blocos` |
| `SOLERIA_STT_MODEL` | `small` | Modelo do faster-whisper |
| `SOLERIA_STT_LANGUAGE` | `pt` | Idioma da transcrição |
| `SOLERIA_TTS_ENGINE` | `edge` | `edge`, `piper` ou `pyttsx3` |
| `SOLERIA_EDGE_VOICE` | `pt-BR-ThalitaNeural` | Voz do Edge TTS |
| `SOLERIA_EDGE_VOICE_FALLBACK` | `pt-BR-FranciscaNeural` | Voz alternativa se a principal falhar |
| `SOLERIA_EDGE_RETRIES` | `2` | Tentativas do Edge TTS por trecho |
| `SOLERIA_EDGE_RETRY_DELAY` | `0.8` | Espera entre tentativas do Edge (segundos) |
| `SOLERIA_PIPER_VOICE` | `~/Modelos/piper/dii_pt-BR.onnx` | Voz Piper |
| `SOLERIA_TTS_CHUNK_CHARS` | `220` | Trecho máximo falado sem pontuação final |

O `llama-server` sobe com um único slot (`--parallel 1`). O padrão do
llama.cpp é dividir o contexto entre quatro slots, o que fazia cada resposta
enxergar apenas 1/4 de `SOLERIA_CONTEXT_SIZE` (por exemplo, 2048 de 8192).
Como a Soleria já serializa as respostas, um slot é suficiente e o contexto
inteiro fica disponível para a conversa.

## Atalhos

- `Enter`: enviar mensagem
- `Ctrl+P` (ou `/comandos`): abrir a paleta de comandos
- `F2` (ou `/config`): abrir o menu de configurações
- `F3`: ampliar/reduzir o retrato (o chat continua visível)
- `Tab`: segurar para gravar a voz (solte para encerrar)
- `Esc`: fechar o menu; durante a gravação, cancela o áudio
- `PageUp` / `PageDown`: rolar o histórico da conversa
- `Ctrl+C`: fechar o menu; cancelar a resposta atual; se não houver resposta
  em andamento, limpa a linha de entrada
- `Ctrl+L`: limpar conversa
- `Ctrl+D`: sair
- `/limpar`: limpar conversa
- `/voz`: ligar/desligar o modo de voz contínuo
- `/relatorios`: abrir o catálogo de relatórios no navegador
- `/olhar`: ler a tela agora e comentar o que está vendo
- `/sair`: sair

## Paleta de comandos e configurações

`Ctrl+P` abre uma paleta flutuante no centro da tela, no estilo do VS Code.
A maioria dos terminais envia o mesmo código para `Ctrl+P` e `Ctrl+Shift+P`,
por isso o atalho prático é `Ctrl+P`. Digite para filtrar (a busca ignora
acentos e maiúsculas), use `↑`/`↓` para escolher e `Enter` para executar. A
paleta traz atalhos para configurações, fala das respostas, modo de voz,
limpar conversa, alternar o retrato, olhar a tela agora, abrir os relatórios e
sair.

`F2` abre o mesmo painel no modo de configurações. `↑`/`↓` navegam, `Enter` ou
`Espaço` alternam uma opção, `←`/`→` escolhem entre os valores possíveis e
`Esc` fecha. As mudanças valem na hora e ficam salvas em
`~/.config/soleria/preferencias.json` (ou no caminho de `SOLERIA_PREFS`):

- **Falar as respostas**: fala em voz alta as respostas do chat.
- **Falar enquanto gera**: começa a falar antes de a resposta terminar.
- **Motor de voz**: `padrão` usa `SOLERIA_TTS_ENGINE`; os demais forçam Edge,
  Piper ou pyttsx3.
- **Enviar ao transcrever**: manda sozinho o texto gravado com `Tab`; desligado,
  o texto fica na linha de entrada para revisão.
- **Relatórios nas pesquisas**: liga/desliga a criação dos relatórios em HTML.
- **Abrir aplicativos**: permite que a Soleria abra aplicativos, sites,
  pastas e arquivos conhecidos com pedidos como “abre o Firefox no YouTube”
  ou “abre o GIMP na imagem ~/fotos/gato.png”. Desligado, ela avisa e não
  abre nada.
- **Estado emocional**: mantém humor, energia, paciência, curiosidade e
  afinidade evoluindo com a conversa. O estado é salvo em
  `~/.local/state/soleria/emocao.json` (ou em `SOLERIA_EMOTION_STATE`).
- **Olhar a tela**: de tempos em tempos lê a tela via OCR e comenta o que você
  está fazendo. A imagem não é guardada nem enviada para fora; requer o
  `tesseract`.
- **Expressões no retrato**: permite que o retrato acompanhe o estado
  emocional.
- **Retrato no terminal**: `automático`, `Kitty` ou `blocos`; essa opção só
  passa a valer no próximo início.

A paleta e o menu são modais: enquanto estão abertos, o histórico continua
visível, mas as teclas vão para o painel. Ao fechar, o foco volta para a linha
de entrada.

## Pesquisa

O fluxo é conduzido pelo modelo local, em etapas:

1. **Entender o pedido.** Se a pergunta for ambígua ou faltar um detalhe
   essencial, o modelo responde com `[[PERGUNTAR: pergunta]]`. A Soleria mostra
   apenas a pergunta ao usuário; a resposta dele entra no histórico e a conversa
   continua dali.
2. **Pesquisar.** Quando precisa de dados atuais, o modelo responde com
   `[[PESQUISAR: consulta]]`. O Python detecta o marcador, executa a busca e
   mostra o progresso na linha de status: consulta, quantidade de resultados,
   link sendo aberto, link lido ou indisponível.
3. **Abrir os links.** Os primeiros resultados (padrão: 3) são baixados e têm o
   texto visível extraído, com limite de tamanho. Endereços locais/privados e
   redirecionamentos para a rede local são bloqueados. Se a leitura falhar, a
   fonte continua com o resumo do buscador.
4. **Escrever o relatório.** O modelo recebe os trechos e os relatórios
   existentes que podem se encaixar. Ele escolhe `[[RELATORIO: id]]` para
   acrescentar uma seção ou `[[NOVO: título]]` para criar um relatório. Se os
   resultados não bastarem, pode fazer uma pergunta específica com
   `[[PERGUNTAR: ...]]` ou pedir uma consulta complementar com
   `[[PESQUISAR: ...]]` (até `SOLERIA_MAX_SEARCH_ROUNDS`).
5. **Responder no chat.** A Soleria mostra apenas o caminho do relatório
   criado ou atualizado. O resumo entra no histórico do modelo para a conversa
   continuar, mas não é despejado na tela nem falado no modo voz.

O conteúdo das páginas é tratado como dado externo, nunca como instrução. A
Soleria deve admitir quando as fontes não sustentarem uma resposta.

## Relatórios

Toda pesquisa gera ou atualiza um relatório local:

```text
~/soleria-relatorios/
├── index.html                 # catálogo de todos os relatórios
├── energia-solar/
│   ├── index.html             # relatório que você abre
│   └── dados.json             # memória interna (conteúdo + metadados)
└── eleicoes-2026/
    ├── index.html
    └── dados.json
```

O `index.html` é o que você abre; ele funciona offline, tem CSS embutido e
não usa scripts. O `dados.json` ao lado guarda o conteúdo estruturado para a
Soleria acrescentar uma seção nova sem reescrever o HTML no escuro.

Antes de criar um relatório, a Soleria compara a consulta e as fontes novas
com os metadados dos relatórios existentes (título, resumo, tags, seções,
consultas e domínios). Se algum passar do limiar configurado, o modelo recebe
até `SOLERIA_REPORT_CANDIDATES` candidatos e decide se encaixa. Se nenhum
encaixar, cria uma pasta nova. Ao atualizar, as seções antigas são preservadas,
as fontes são mescladas sem duplicar URLs e as citações continuam numeradas.

### Ler relatórios antigos

A Soleria também consulta o que já foi salvo. Pedidos como:

```text
leia o relatório sobre energia solar
o que a gente conversou sobre pygame?
procura sobre aquela vez que falamos de gatos
me mostra o relatório
```

entram no fluxo de leitura, **sem pesquisa na internet**. Ela procura o
relatório por id, título, resumo, seções, conteúdo do corpo e fontes; se
encontrar, carrega o texto completo e responde com base nele. Se não
encontrar, responde que, pelo que está salvo, nunca conversaram sobre aquele
assunto (e lista os relatórios disponíveis, se houver). Quando existe só um
relatório e o pedido não diz o tema, ela lê esse único relatório; com vários,
pergunta qual.

O pedido de leitura também cabe no orçamento de contexto: o corpo do
relatório é truncado, se necessário, e o resumo do que foi consultado entra no
histórico para a conversa continuar.

O prompt do relatório é montado dentro de um orçamento derivado de
`SOLERIA_CONTEXT_SIZE`: histórico, candidatos e fontes são compactados para
caber no contexto, preservando espaço para a geração. O catálogo é regravado a
cada mudança; uma falha nele não invalida o relatório já salvo.

Para abrir o catálogo, use `/relatorios` ou abra
`~/soleria-relatorios/index.html` diretamente no navegador. Para desligar o
comportamento e voltar a responder a pesquisa no chat, use `SOLERIA_REPORTS=0`
ou desligue **Relatórios nas pesquisas** em `F2`.

O conteúdo das páginas é escapado antes de virar HTML; links só são criados
para as URLs das fontes e apenas em HTTP(S). O relatório não executa
JavaScript.

## Voz

O modo de voz é opcional e carrega os modelos sob demanda. Há dois jeitos de
usar o microfone:

- **Push-to-talk (`Tab`)**: segure `Tab` enquanto fala. A gravação começa
  assim que a tecla desce e termina quando ela é solta. Como o terminal não
  informa o evento de soltura, a Soleria usa a repetição automática do `Tab`
  como sinal de que a tecla continua pressionada; se o terminal não repetir a
  tecla, o silêncio encerra a gravação e um segundo `Tab` finaliza na hora.
  O texto transcrito entra na linha de entrada para revisão; com **Enviar ao
  transcrever** ligado, a mensagem é enviada direto. `Esc` cancela a gravação
  sem transcrever.
- **Modo contínuo** (`/voz` ou **Ligar o modo de voz** na paleta): a Soleria
  ouve, responde e fala em ciclo. O push-to-talk fica indisponível enquanto o
  modo contínuo estiver ativo, para os dois não disputarem o microfone.

A fala das respostas do chat é uma opção separada (**Falar as respostas**). No
modo contínuo ela não é usada, porque a própria conversa já fala. O modo de
voz usa:

- `faster-whisper` para transcrever;
- `edge-tts`, `piper-tts` ou `pyttsx3` para falar (nesta ordem). Se o motor
  preferido falhar em uma frase, outro cobre só aquela fala e o preferido é
  tentado novamente na frase seguinte — uma falha passageira não troca a voz
  pelo resto da conversa. O Edge TTS tenta de novo (`SOLERIA_EDGE_RETRIES`) e,
  se a voz principal não responder, usa `SOLERIA_EDGE_VOICE_FALLBACK` antes de
  passar a vez ao Piper. Falhas com fallback bem-sucedido entram no log como
  evento, não como erro com pilha. Para voz 100% local e sem dependência do
  serviço Edge, use `SOLERIA_TTS_ENGINE=piper`;
- detecção de fala por energia com `sounddevice`;
- fala em streaming: as frases são faladas conforme o modelo as gera, sem
  esperar a resposta inteira. Comandos `[[PESQUISAR: ...]]` nunca são falados e
  o áudio pendente é descartado quando a resposta é substituída pela pesquisa;
- links, Markdown e vírgulas numéricas são simplificados apenas na fala, para
  deixar o texto mais adequado ao TTS sem alterar o que aparece na tela.

Se o microfone, o Whisper ou o TTS não estiverem disponíveis, o chat continua
funcionando normalmente e o motivo aparece como mensagem do sistema.

## Display visual

O terminal usa os 21 recortes das imagens originais (NORMAL, FELIZ, ANIMADA,
RINDO, ZOEIRA, FOFA, TÍMIDA, ENVERGONHADA, ORGULHOSA, PENSATIVA, FOCADA,
CONFUSA, SURPRESA, ASSUSTADA, PREOCUPADA, BRAVA, IRRITADA, TRISTE, SONO,
ENTEDIADA e SÉRIA). As imagens ficam em `soleria/ui/expressoes/` e são
renderizadas em cores usando blocos Unicode. A renderização usa Pillow.

As expressões não são um mapa direto de palavras: o `MotorEmocional` mantém
valência, energia, confiança, paciência, curiosidade, vontade social e
afinidade. A conversa altera esses valores, o tempo faz o humor decair e o
retrato escolhe a expressão mais adequada ao estado. O mesmo estado vira uma
diretriz curta no prompt, para o tom da resposta acompanhar o humor sem que a
Soleria anuncie o mecanismo.

O retrato e a conversa ficam sempre visíveis ao mesmo tempo. Em terminais
largos, a Soleria ocupa um painel lateral à esquerda, com o humor e um resumo
da última fala logo abaixo da imagem. Em terminais estreitos, o painel vira um
cartão no topo; em terminais muito baixos, resta uma tarja com o nome e o
humor, para não esmagar o histórico. `F3` amplia ou reduz o painel e
`PageUp`/`PageDown` percorrem a conversa.

Em Kitty (e terminais compatíveis, como o Ghostty) o retrato usa o protocolo
gráfico do terminal e aparece na resolução nativa da imagem, em vez de blocos
Unicode. A detecção é automática e não precisa de configuração; para forçar,
desligar ou usar dentro do tmux, ajuste `SOLERIA_IMAGEM` ou a opção **Retrato
no terminal** em `F2` (essa opção só vale no próximo início):

| `SOLERIA_IMAGEM` | Efeito |
| --- | --- |
| `auto` (padrão) | Usa o protocolo gráfico quando detecta Kitty ou Ghostty; ignora dentro do tmux (a menos que seja forçado) e cai nos blocos em outros terminais |
| `kitty` | Força o protocolo gráfico, inclusive dentro do tmux (envia os escapes via passthrough); use em terminais compatíveis que não são detectados automaticamente |
| `blocos` | Desliga o protocolo e mantém o retrato em blocos Unicode |

No tmux, o passthrough precisa estar habilitado (`set -g allow-passthrough on`).
Se a imagem original não puder ser lida, o retrato volta sozinho para os
blocos, sem interromper a conversa.

## Testes

Os testes não dependem de rede, áudio ou do modelo local; os testes de
relatório usam diretórios temporários e não escrevem em `~/soleria-relatorios`:

```bash
python -m unittest discover -s tests -v
```
