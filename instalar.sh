#!/usr/bin/env bash
#
# Instala (ou atualiza) a Soleria em um PC novo.
#
# Uso:
#   ./instalar.sh                          # instala tudo no diretório atual
#   ./instalar.sh --dir ~/.soleria         # escolhe o diretório do projeto
#   ./instalar.sh --backup ~/soleria-backup-2026-10-30.tar.zst
#   ./instalar.sh --backup ... --somente-restaurar   # só recupera os dados
#   ./instalar.sh --sem-modelo             # não baixa o GGUF de 3,8 GB
#   ./instalar.sh --sem-llama              # não compila o llama.cpp
#   ./instalar.sh --sem-voz                # não baixa a voz do Piper
#   ./instalar.sh --sem-sistema            # não instala pacotes do sistema
#   ./instalar.sh --sem-testes             # não roda a suíte de testes
#   ./instalar.sh --recompilar             # força recompilar o llama.cpp
#   ./instalar.sh --cuda | --cpu           # força build com/sem CUDA
#   ./instalar.sh --sem-atualizar          # não faz git pull
#
# Testado em Arch/CachyOS; tem suporte básico a Debian/Ubuntu e Fedora.
# Pode ser executado várias vezes: o que já existe é reaproveitado.

set -Eeuo pipefail

REPO_URL="https://github.com/HubertRamos/Soleria.Heliminas.git"
LLAMA_URL="https://github.com/ggml-org/llama.cpp.git"
MODELO_URL="https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q3_k_m.gguf"
PIPER_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium"

# ----------------------------------------------------------------------
# Saída
# ----------------------------------------------------------------------

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_OK=$'\033[1;32m'; C_AV=$'\033[1;33m'; C_ER=$'\033[1;31m'
    C_TI=$'\033[1;36m'; C_FM=$'\033[0m'
else
    C_OK=""; C_AV=""; C_ER=""; C_TI=""; C_FM=""
fi

titulo() { printf '\n%s==> %s%s\n' "$C_TI" "$*" "$C_FM"; }
ok()     { printf '%s  ok%s %s\n' "$C_OK" "$C_FM" "$*"; }
aviso()  { printf '%s  !!%s %s\n' "$C_AV" "$C_FM" "$*" >&2; }
erro()   { printf '%s erro%s %s\n' "$C_ER" "$C_FM" "$*" >&2; }
morrer() { erro "$*"; exit 1; }

trap 'erro "falhou na linha $LINENO (comando: $BASH_COMMAND)"' ERR

# ----------------------------------------------------------------------
# Argumentos e caminhos
# ----------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DIR="${SOLERIA_DIR:-}"
[ -n "$DIR" ] || {
    if [ -f "$SCRIPT_DIR/main.py" ] && [ -d "$SCRIPT_DIR/.git" ]; then
        DIR="$SCRIPT_DIR"
    else
        DIR="$HOME/.soleria"
    fi
}
DIR="${DIR/#\~/$HOME}"

MODELO="${SOLERIA_MODEL_PATH:-$HOME/Modelos/qwen2.5-7b-instruct-q3_k_m.gguf}"
LLAMA_DIR="${SOLERIA_LLAMA_DIR:-$HOME/llama.cpp}"
PIPER_DIR="$HOME/Modelos/piper"

BACKUP=""
BAIXAR_MODELO=1
COMPILAR_LLAMA=1
BAIXAR_VOZ=1
INSTALAR_SISTEMA=1
RODAR_TESTES=1
RECOMPILAR=0
ATUALIZAR=1
GPU="auto"
SOMENTE_RESTAURAR=0

while [ $# -gt 0 ]; do
    case "$1" in
        --dir) DIR="$2"; shift 2 ;;
        --modelo) MODELO="$2"; shift 2 ;;
        --llama-dir) LLAMA_DIR="$2"; shift 2 ;;
        --backup) BACKUP="$2"; shift 2 ;;
        --somente-restaurar) SOMENTE_RESTAURAR=1; shift ;;
        --sem-modelo) BAIXAR_MODELO=0; shift ;;
        --sem-llama) COMPILAR_LLAMA=0; shift ;;
        --sem-voz) BAIXAR_VOZ=0; shift ;;
        --sem-sistema) INSTALAR_SISTEMA=0; shift ;;
        --sem-testes) RODAR_TESTES=0; shift ;;
        --recompilar) RECOMPILAR=1; shift ;;
        --sem-atualizar) ATUALIZAR=0; shift ;;
        --cuda) GPU="cuda"; shift ;;
        --cpu) GPU="cpu"; shift ;;
        -h|--help)
            sed -n '2,21p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) morrer "opção desconhecida: $1 (use --help)" ;;
    esac
done

DIR="${DIR/#\~/$HOME}"
MODELO="${MODELO/#\~/$HOME}"
LLAMA_DIR="${LLAMA_DIR/#\~/$HOME}"
[ -n "$BACKUP" ] && BACKUP="${BACKUP/#\~/$HOME}"

if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
else
    command -v sudo >/dev/null 2>&1 || morrer "preciso de sudo para instalar pacotes (ou use --sem-sistema)"
    SUDO="sudo"
fi

# ----------------------------------------------------------------------
# Sistema
# ----------------------------------------------------------------------

detectar_gerenciador() {
    if command -v pacman >/dev/null 2>&1; then echo pacman
    elif command -v apt-get >/dev/null 2>&1; then echo apt
    elif command -v dnf >/dev/null 2>&1; then echo dnf
    else echo nenhum
    fi
}

instalar_pacotes() {
    local gerenciador="$1"
    case "$gerenciador" in
        pacman)
            $SUDO pacman -S --needed --noconfirm --color never \
                base-devel git cmake python curl zstd \
                tesseract tesseract-data-por tesseract-data-eng tesseract-data-osd \
                portaudio ffmpeg espeak-ng xdg-utils
            $SUDO pacman -S --needed --noconfirm --color never uv \
                || aviso "pacote uv indisponível; vou usar venv + pip"
            ;;
        apt)
            $SUDO env DEBIAN_FRONTEND=noninteractive apt-get update -qq
            $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
                build-essential git cmake python3 python3-venv python3-pip curl zstd \
                tesseract-ocr tesseract-ocr-por tesseract-ocr-eng \
                portaudio19-dev ffmpeg espeak-ng xdg-utils
            $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq uv \
                || aviso "pacote uv indisponível; vou usar venv + pip"
            ;;
        dnf)
            $SUDO dnf install -y \
                gcc gcc-c++ make git cmake python3 python3-pip curl zstd \
                tesseract tesseract-langpack-por tesseract-langpack-eng \
                portaudio-devel ffmpeg-free espeak-ng xdg-utils
            $SUDO dnf install -y uv || aviso "pacote uv indisponível; vou usar venv + pip"
            ;;
        *)
            aviso "gerenciador de pacotes não reconhecido."
            aviso "Instale manualmente: git, cmake, python3, tesseract (+ idiomas por/eng),"
            aviso "portaudio, ffmpeg, espeak-ng, curl e zstd. Continuando em 5s..."
            sleep 5
            ;;
    esac
}

verificar_python() {
    local py="$1"
    "$py" - <<'PY' || morrer "Python 3.10+ é necessário."
import sys
sys.exit(0 if sys.version_info >= (3, 10) else 1)
PY
}

# ----------------------------------------------------------------------
# Backup (restauração)
# ----------------------------------------------------------------------

extrair_backup() {
    local arquivo="$1" destino="$2"
    case "$arquivo" in
        *.tar.zst|*.tzst) tar --zstd -xf "$arquivo" -C "$destino" ;;
        *.tar.gz|*.tgz)   tar -xzf "$arquivo" -C "$destino" ;;
        *.tar.xz|*.txz)   tar -xJf "$arquivo" -C "$destino" ;;
        *.tar)            tar -xf "$arquivo" -C "$destino" ;;
        *) morrer "formato de backup não reconhecido: $arquivo" ;;
    esac
}

restaurar_backup() {
    local arquivo="$1"
    [ -f "$arquivo" ] || morrer "backup não encontrado: $arquivo"

    titulo "Restaurando backup"
    local tmp
    tmp="$(mktemp -d)"
    # shellcheck disable=SC2064
    trap "rm -rf '$tmp'" EXIT

    extrair_backup "$arquivo" "$tmp"
    [ -d "$tmp/repo" ] || morrer "backup sem a pasta repo/ (arquivo inválido?)"

    # Código: só restaura se ainda não houver projeto no destino.
    if [ ! -f "$DIR/main.py" ]; then
        mkdir -p "$DIR"
        cp -a "$tmp/repo/." "$DIR/"
        ok "código restaurado em $DIR"
    else
        aviso "projeto já existe em $DIR; mantendo o código atual (só dados serão restaurados)"
    fi

    local -a pares=(
        ".config/soleria:$HOME/.config/soleria"
        ".local/state/soleria:$HOME/.local/state/soleria"
        "soleria-relatorios:$HOME/soleria-relatorios"
        "Modelos:$HOME/Modelos"
    )
    local par origem destino
    for par in "${pares[@]}"; do
        origem="$tmp/${par%%:*}"
        destino="${par#*:}"
        if [ -d "$origem" ]; then
            mkdir -p "$destino"
            cp -an "$origem/." "$destino/" 2>/dev/null || true
            ok "dados restaurados em $destino"
        fi
    done

    if [ -s "$tmp/env-soleria.txt" ]; then
        cp -a "$tmp/env-soleria.txt" "$HOME/soleria-env-backup.txt"
        aviso "variáveis SOLERIA_* antigas salvas em ~/soleria-env-backup.txt"
    fi

    rm -rf "$tmp"
    trap - EXIT
    trap 'erro "falhou na linha $LINENO (comando: $BASH_COMMAND)"' ERR
}

# ----------------------------------------------------------------------
# Projeto
# ----------------------------------------------------------------------

obter_projeto() {
    if [ -d "$DIR/.git" ]; then
        ok "projeto já existe em $DIR"
        if [ "$ATUALIZAR" = 1 ]; then
            git -C "$DIR" pull --ff-only --quiet \
                && ok "código atualizado (git pull)" \
                || aviso "não foi possível atualizar (há mudanças locais?); seguindo com o código atual"
        fi
    else
        mkdir -p "$(dirname "$DIR")"
        git clone --depth 1 "$REPO_URL" "$DIR"
        ok "projeto clonado em $DIR"
    fi
    [ -f "$DIR/requirements.txt" ] || morrer "$DIR/requirements.txt não encontrado"
}

# ----------------------------------------------------------------------
# Python
# ----------------------------------------------------------------------

criar_ambiente_python() {
    local py="$DIR/.venv/bin/python"

    if [ -x "$py" ]; then
        ok "ambiente virtual existente reaproveitado"
    else
        if command -v uv >/dev/null 2>&1; then
            rm -rf "$DIR/.venv"
            uv venv --python 3.12 "$DIR/.venv"
            ok "ambiente virtual criado com uv (Python 3.12)"
        else
            verificar_python python3
            python3 -m venv "$DIR/.venv"
            ok "ambiente virtual criado com python3 ($(python3 -V 2>&1))"
        fi
        py="$DIR/.venv/bin/python"
    fi

    titulo "Instalando dependências Python"
    if command -v uv >/dev/null 2>&1; then
        uv pip install --python "$py" -r "$DIR/requirements.txt"
    else
        "$py" -m pip install --upgrade pip
        "$py" -m pip install -r "$DIR/requirements.txt"
    fi

    "$py" - <<'PY' || morrer "as dependências Python não importaram corretamente"
import openai, prompt_toolkit, PIL, ddgs, dbus_next  # noqa: F401
PY
    ok "dependências Python instaladas"
}

# ----------------------------------------------------------------------
# llama.cpp
# ----------------------------------------------------------------------

compilar_llama() {
    local bin="$LLAMA_DIR/build/bin/llama-server"

    if [ -x "$bin" ] && [ "$RECOMPILAR" = 0 ]; then
        ok "llama-server já compilado em $bin"
        return
    fi

    if [ ! -d "$LLAMA_DIR/.git" ]; then
        mkdir -p "$(dirname "$LLAMA_DIR")"
        git clone --depth 1 "$LLAMA_URL" "$LLAMA_DIR"
        ok "llama.cpp clonado em $LLAMA_DIR"
    elif [ "$ATUALIZAR" = 1 ] && [ "$RECOMPILAR" = 0 ]; then
        git -C "$LLAMA_DIR" pull --ff-only --quiet || aviso "não foi possível atualizar o llama.cpp"
    fi

    local cuda=0
    case "$GPU" in
        cuda)
            command -v nvcc >/dev/null 2>&1 || aviso "nvcc não encontrado; o build CUDA provavelmente vai falhar"
            cuda=1 ;;
        auto)
            if command -v nvcc >/dev/null 2>&1 && command -v nvidia-smi >/dev/null 2>&1; then
                cuda=1
            fi ;;
    esac

    local -a opcoes=(
        -S "$LLAMA_DIR" -B "$LLAMA_DIR/build"
        -DCMAKE_BUILD_TYPE=Release
        -DGGML_NATIVE=ON
        -DLLAMA_BUILD_TESTS=OFF
        -DLLAMA_BUILD_EXAMPLES=OFF
        -DLLAMA_BUILD_SERVER=ON
    )
    if [ "$cuda" = 1 ]; then
        opcoes+=(-DGGML_CUDA=ON)
        ok "compilando llama.cpp com CUDA"
    else
        opcoes+=(-DGGML_CUDA=OFF)
        ok "compilando llama.cpp para CPU"
    fi

    cmake "${opcoes[@]}"
    cmake --build "$LLAMA_DIR/build" --target llama-server -j "$(nproc)"
    [ -x "$bin" ] || morrer "compilação terminou sem gerar $bin"
    ok "llama-server pronto"
}

# ----------------------------------------------------------------------
# Downloads
# ----------------------------------------------------------------------

baixar() {
    local url="$1" destino="$2" temporario="$2.part"
    [ -f "$destino" ] && { ok "já existe: $destino"; return; }
    mkdir -p "$(dirname "$destino")"

    if [ -f "$temporario" ]; then
        aviso "retomando download de $(basename "$destino")"
        curl -fL --retry 5 --retry-delay 2 -C - -o "$temporario" "$url" \
            || { rm -f "$temporario"; curl -fL --retry 5 --retry-delay 2 -o "$temporario" "$url"; }
    else
        curl -fL --retry 5 --retry-delay 2 -o "$temporario" "$url"
    fi

    [ -s "$temporario" ] || morrer "download vazio: $url"
    mv "$temporario" "$destino"
    ok "baixado: $destino"
}

baixar_modelo() {
    baixar "$MODELO_URL" "$MODELO"
    local tamanho
    tamanho="$(stat -c %s "$MODELO" 2>/dev/null || echo 0)"
    [ "$tamanho" -gt 1000000000 ] || morrer "o modelo baixado parece incompleto ($tamanho bytes)"
    ok "modelo GGUF pronto ($(du -h "$MODELO" | cut -f1))"
}

baixar_voz() {
    [ -f "$PIPER_DIR/pt_BR-faber-medium.onnx" ] \
        || baixar "$PIPER_BASE.onnx" "$PIPER_DIR/pt_BR-faber-medium.onnx"
    [ -f "$PIPER_DIR/pt_BR-faber-medium.onnx.json" ] \
        || baixar "$PIPER_BASE.onnx.json" "$PIPER_DIR/pt_BR-faber-medium.onnx.json"
}

# ----------------------------------------------------------------------
# Atalhos
# ----------------------------------------------------------------------

criar_atalhos() {
    local bin="$HOME/.local/bin/soleria"
    mkdir -p "$HOME/.local/bin"

    cat > "$bin" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$DIR" || exit 1
# A voz "dii" é treinada localmente e só existe se veio no backup.
# Sem ela, usa a voz faber baixada pelo instalador.
if [ -z "\${SOLERIA_PIPER_VOICE:-}" ] \\
   && [ ! -f "\$HOME/Modelos/piper/dii_pt-BR.onnx" ] \\
   && [ -f "\$HOME/Modelos/piper/pt_BR-faber-medium.onnx" ]; then
    export SOLERIA_PIPER_VOICE="\$HOME/Modelos/piper/pt_BR-faber-medium.onnx"
fi
exec "$DIR/.venv/bin/python" "$DIR/main.py" "\$@"
EOF
    chmod +x "$bin"
    ok "comando criado: $bin"

    local desktop="$HOME/.local/share/applications/soleria.desktop"
    mkdir -p "$(dirname "$desktop")"
    cat > "$desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Soleria
Comment=IA local modular no terminal
Exec="$bin"
Icon=utilities-terminal
Terminal=true
Categories=Utility;Development;
Keywords=IA;LLM;chat;terminal;
EOF
    ok "atalho de aplicativo criado: $desktop"

    case ":$PATH:" in
        *":$HOME/.local/bin:"*) ;;
        *) aviso "~/.local/bin não está no PATH; adicione ao seu shell para usar o comando 'soleria'" ;;
    esac
}

# ----------------------------------------------------------------------
# Testes
# ----------------------------------------------------------------------

rodar_testes() {
    [ "$RODAR_TESTES" = 1 ] || return 0
    titulo "Testes offline"
    if ( cd "$DIR" && "$DIR/.venv/bin/python" -m unittest discover -s tests -q ); then
        ok "todos os testes passaram"
    else
        aviso "alguns testes falharam; a instalação continua, mas verifique acima"
    fi
}

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

printf '%s\n' "${C_TI}Soleria — instalador${C_FM}"
printf '  projeto : %s\n' "$DIR"
printf '  modelo  : %s\n' "$MODELO"
printf '  llama   : %s\n' "$LLAMA_DIR"

if [ -n "$BACKUP" ]; then
    restaurar_backup "$BACKUP"
    if [ "$SOMENTE_RESTAURAR" = 1 ]; then
        titulo "Restauração concluída"
        printf '  Código : %s\n' "$DIR"
        printf '  Modelo : %s\n' "$MODELO"
        printf '  Depois, rode ./instalar.sh sem --backup para instalar as dependências.\n'
        exit 0
    fi
elif [ "$SOMENTE_RESTAURAR" = 1 ]; then
    morrer "--somente-restaurar precisa de --backup ARQUIVO"
fi

gerenciador="$(detectar_gerenciador)"
if [ "$INSTALAR_SISTEMA" = 1 ]; then
    titulo "Pacotes do sistema ($gerenciador)"
    instalar_pacotes "$gerenciador"
else
    aviso "instalação de pacotes do sistema ignorada (--sem-sistema)"
fi

titulo "Projeto"
obter_projeto

titulo "Ambiente Python"
criar_ambiente_python

if [ "$COMPILAR_LLAMA" = 1 ]; then
    titulo "llama.cpp"
    compilar_llama
else
    aviso "compilação do llama.cpp ignorada (--sem-llama)"
fi

if [ "$BAIXAR_MODELO" = 1 ]; then
    titulo "Modelo GGUF"
    baixar_modelo
else
    aviso "download do modelo ignorado (--sem-modelo)"
fi

if [ "$BAIXAR_VOZ" = 1 ]; then
    titulo "Voz do Piper"
    baixar_voz
else
    aviso "download da voz ignorado (--sem-voz)"
fi

titulo "Atalhos"
criar_atalhos

rodar_testes

titulo "Pronto"
cat <<EOF
  Inicie com:  soleria
  Ou:          cd "$DIR" && .venv/bin/python main.py
  Configure:   F2 dentro do chat

  O modelo é iniciado sob demanda e desligado após 120 s sem uso.
  Para habilitar a voz 100% local, use SOLERIA_TTS_ENGINE=piper.
EOF
