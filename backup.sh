#!/usr/bin/env bash
#
# Empacota tudo que a Soleria precisa para sobreviver a uma formatação.
#
# Uso:
#   ./backup.sh                          # salva em ~/soleria-backup-<data>.tar.zst
#   ./backup.sh --dest /run/media/hubert/pendrive
#   ./backup.sh --sem-modelos            # não inclui o GGUF de 3,7 GB
#   ./backup.sh --com-llama              # inclui o build do llama.cpp (833 MB)
#   ./backup.sh --sem-compressao         # gera .tar puro (mais rápido)
#   ./backup.sh --dir ~/.soleria
#
# O arquivo contém:
#   repo/                      código + .git + mudanças locais
#   .config/soleria/           preferências do menu (F2)
#   .local/state/soleria/      estado emocional
#   soleria-relatorios/        relatórios em HTML
#   Modelos/                   modelo GGUF e vozes do Piper
#
# Depois de formatar, no PC novo:
#   git clone https://github.com/HubertRamos/Soleria.Heliminas.git ~/.soleria
#   ~/.soleria/instalar.sh --backup /caminho/soleria-backup-....tar.zst
#
# Ou extraia o arquivo e rode ./restaurar.sh de dentro dele.

set -Eeuo pipefail

REPO_URL="https://github.com/HubertRamos/Soleria.Heliminas.git"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_OK=$'\033[1;32m'; C_AV=$'\033[1;33m'; C_ER=$'\033[1;31m'
    C_TI=$'\033[1;36m'; C_FM=$'\033[0m'
else
    C_OK=""; C_AV=""; C_ER=""; C_TI=""; C_FM=""
fi

titulo() { printf '\n%s==> %s%s\n' "$C_TI" "$*" "$C_FM"; }
ok()     { printf '%s  ok%s %s\n' "$C_OK" "$C_FM" "$*"; }
aviso()  { printf '%s  !!%s %s\n' "$C_AV" "$C_FM" "$*" >&2; }
morrer() { printf '%s erro%s %s\n' "$C_ER" "$C_FM" "$*" >&2; exit 1; }

trap 'echo "erro na linha $LINENO (comando: $BASH_COMMAND)" >&2; exit 1' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DIR="${SOLERIA_DIR:-}"
[ -n "$DIR" ] || {
    if [ -f "$SCRIPT_DIR/main.py" ] && [ -d "$SCRIPT_DIR/.git" ]; then
        DIR="$SCRIPT_DIR"
    else
        DIR="$HOME/.soleria"
    fi
}

DEST="$HOME"
COM_MODELOS=1
COM_LLAMA=0
COMPRIMIR=1
FORCAR=0

while [ $# -gt 0 ]; do
    case "$1" in
        --dir) DIR="$2"; shift 2 ;;
        --dest) DEST="$2"; shift 2 ;;
        --sem-modelos) COM_MODELOS=0; shift ;;
        --com-llama) COM_LLAMA=1; shift ;;
        --sem-compressao) COMPRIMIR=0; shift ;;
        --forcar) FORCAR=1; shift ;;
        -h|--help)
            sed -n '2,28p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) morrer "opção desconhecida: $1 (use --help)" ;;
    esac
done

DIR="${DIR/#\~/$HOME}"
DEST="${DEST/#\~/$HOME}"
DEST="${DEST%/}"
mkdir -p "$DEST" || morrer "não consegui criar o destino: $DEST"

[ -f "$DIR/main.py" ] && [ -d "$DIR/.git" ] || morrer "não encontrei um projeto Soleria em $DIR"

DATA="$(date +%Y-%m-%d_%H%M)"
if [ "$COMPRIMIR" = 1 ] && command -v zstd >/dev/null 2>&1; then
    OUT="$DEST/soleria-backup-$DATA.tar.zst"
    COMPRESSOR="zstd"
elif [ "$COMPRIMIR" = 1 ]; then
    OUT="$DEST/soleria-backup-$DATA.tar.gz"
    COMPRESSOR="gzip"
else
    OUT="$DEST/soleria-backup-$DATA.tar"
    COMPRESSOR="nenhum"
fi

[ -e "$OUT" ] && morrer "o arquivo já existe: $OUT"

# ----------------------------------------------------------------------
# Tamanho e espaço
# ----------------------------------------------------------------------

soma_bytes() {
    local total=0 caminho n
    for caminho in "$@"; do
        [ -e "$caminho" ] || continue
        # -L segue symlinks: o tar usa -h, então o backup terá o conteúdo real.
        n="$(du -sbL "$caminho" 2>/dev/null | cut -f1 || true)"
        case "$n" in ''|*[!0-9]*) n=0 ;; esac
        total=$(( total + n ))
    done
    echo "$total"
}

humanos() {
    numfmt --to=iec --suffix=B "$1" 2>/dev/null || echo "$1 bytes"
}

declare -a FONTES=()
[ -d "$HOME/.config/soleria" ]      && FONTES+=("$HOME/.config/soleria")
[ -d "$HOME/.local/state/soleria" ] && FONTES+=("$HOME/.local/state/soleria")
[ -d "$HOME/soleria-relatorios" ]   && FONTES+=("$HOME/soleria-relatorios")
[ "$COM_MODELOS" = 1 ] && [ -d "$HOME/Modelos" ] && FONTES+=("$HOME/Modelos")
[ "$COM_LLAMA" = 1 ] && [ -d "$HOME/llama.cpp" ] && FONTES+=("$HOME/llama.cpp")

tamanho_repo="$(du -sb --exclude=.venv --exclude=__pycache__ "$DIR" 2>/dev/null | cut -f1 || true)"
case "$tamanho_repo" in ''|*[!0-9]*) tamanho_repo=0 ;; esac
tamanho_dados="$(soma_bytes "${FONTES[@]}")"
tamanho_total=$(( tamanho_repo + tamanho_dados ))
disponivel="$(df -B1 --output=avail "$DEST" | tail -1 | tr -d ' ')"

titulo "Planejando backup"
printf '  projeto : %s (%s)\n' "$DIR" "$(humanos "$tamanho_repo")"
printf '  dados   : %s (%s)\n' "${#FONTES[@]} pasta(s)" "$(humanos "$tamanho_dados")"
printf '  destino : %s (%s livres)\n' "$DEST" "$(humanos "$disponivel")"
printf '  arquivo : %s\n' "$OUT"

if [ "$tamanho_total" -gt "$disponivel" ]; then
    if [ "$FORCAR" = 1 ]; then
        aviso "espaço insuficiente, mas seguindo por causa de --forcar"
    else
        morrer "espaço insuficiente: faltam $(humanos $(( tamanho_total - disponivel ))) (use --dest em outro disco ou --forcar)"
    fi
fi

# ----------------------------------------------------------------------
# Preparação
# ----------------------------------------------------------------------

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/soleria-backup.XXXXXX")"
# shellcheck disable=SC2064
trap "rm -rf '$STAGE'" EXIT

titulo "Copiando o projeto"
mkdir -p "$STAGE/repo"
tar -C "$DIR" \
    --exclude=.venv \
    --exclude=__pycache__ \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    -cf - . | tar -C "$STAGE/repo" -xf -
ok "código copiado (sem .venv e __pycache__)"

titulo "Coletando metadados"

{
    echo "Soleria — backup"
    echo "data:      $(date -Is)"
    echo "host:      $(hostname)"
    echo "sistema:   $(uname -srm)"
    echo "projeto:   $DIR"
    echo "commit:    $(git -C "$DIR" rev-parse HEAD 2>/dev/null || echo desconhecido)"
    echo "sujo:      $({ git -C "$DIR" status --porcelain 2>/dev/null || true; } | wc -l) arquivo(s) modificado(s)"
    echo "python:    $("$DIR/.venv/bin/python" -V 2>/dev/null || python3 -V 2>/dev/null || echo desconhecido)"
    echo "git:       $(git --version 2>/dev/null || echo desconhecido)"
    echo "cmake:     $(cmake --version 2>/dev/null | head -1 || echo desconhecido)"
    echo
    echo "tamanhos:"
    echo "  projeto: $(humanos "$tamanho_repo")"
    echo "  dados:   $(humanos "$tamanho_dados")"
    echo
    echo "conteúdo:"
    for fonte in "${FONTES[@]}"; do
        echo "  $fonte -> $(humanos "$(soma_bytes "$fonte")")"
    done
    echo
    echo "pacotes relevantes:"
    if command -v pacman >/dev/null 2>&1; then
        pacman -Q tesseract tesseract-data-por tesseract-data-eng portaudio ffmpeg espeak-ng 2>/dev/null | sed 's/^/  /' || true
    elif command -v dpkg-query >/dev/null 2>&1; then
        dpkg-query -W -f='  ${Package} ${Version}\n' \
            tesseract-ocr tesseract-ocr-por tesseract-ocr-eng libportaudio2 ffmpeg espeak-ng 2>/dev/null || true
    fi
} > "$STAGE/MANIFEST.txt"

{
    echo "# Variáveis SOLERIA_* do ambiente atual"
    env | grep -E '^SOLERIA_' | sort || true
    echo
    echo "# Linhas SOLERIA_* encontradas nos arquivos de shell"
    for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile" "$HOME/.config/fish/config.fish"; do
        [ -f "$rc" ] || continue
        grep -H 'SOLERIA_' "$rc" 2>/dev/null || true
    done
} > "$STAGE/env-soleria.txt"
ok "manifesto e variáveis de ambiente salvos"

cat > "$STAGE/restaurar.sh" <<'RESTAURAR'
#!/usr/bin/env bash
# Restaura os dados deste backup sem precisar do instalar.sh.
set -Eeuo pipefail
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR="${SOLERIA_DIR:-$HOME/.soleria}"

restaurar() {
    local origem="$1" destino="$2"
    [ -d "$origem" ] || return 0
    mkdir -p "$destino"
    # -n: nunca sobrescreve o que já existe no PC novo
    cp -an "$origem/." "$destino/" 2>/dev/null || true
    echo "  restaurado: $destino"
}

echo "Restaurando Soleria..."
if [ ! -f "$DIR/main.py" ]; then
    restaurar "$BASE/repo" "$DIR"
else
    echo "  projeto já existe em $DIR; mantendo o código atual"
fi
restaurar "$BASE/.config/soleria" "$HOME/.config/soleria"
restaurar "$BASE/.local/state/soleria" "$HOME/.local/state/soleria"
restaurar "$BASE/soleria-relatorios" "$HOME/soleria-relatorios"
restaurar "$BASE/Modelos" "$HOME/Modelos"

if [ -s "$BASE/env-soleria.txt" ]; then
    cp -a "$BASE/env-soleria.txt" "$HOME/soleria-env-backup.txt"
    echo "  variáveis SOLERIA_* antigas: ~/soleria-env-backup.txt"
fi

echo "Pronto. Agora rode ~/.soleria/instalar.sh para instalar as dependências."
RESTAURAR
chmod +x "$STAGE/restaurar.sh"

cat > "$STAGE/RESTAURAR.md" <<'GUIA'
# Como restaurar depois de formatar

## Opção 1 — instalador (recomendado)

```bash
git clone https://github.com/HubertRamos/Soleria.Heliminas.git ~/.soleria
~/.soleria/instalar.sh --backup /caminho/para/este-arquivo.tar.zst
```

O instalador restaura os dados **sem sobrescrever** nada que já exista, instala
pacotes do sistema, dependências Python, recompila o llama.cpp e reaproveita o
modelo que veio no backup.

## Opção 2 — só os dados

```bash
mkdir -p /tmp/soleria-restore
tar --zstd -xf /caminho/para/este-arquivo.tar.zst -C /tmp/soleria-restore
/tmp/soleria-restore/restaurar.sh
```

Depois instale as dependências com `~/.soleria/instalar.sh`.

## Conteúdo

- `repo/` — código, histórico `.git` e mudanças locais
- `.config/soleria/` — preferências do menu (F2)
- `.local/state/soleria/` — estado emocional
- `soleria-relatorios/` — relatórios em HTML
- `Modelos/` — modelo GGUF e vozes do Piper (se incluído)
- `MANIFEST.txt` — versões e tamanhos no momento do backup
- `env-soleria.txt` — variáveis `SOLERIA_*` que você usava
GUIA

# ----------------------------------------------------------------------
# Empacotamento
# ----------------------------------------------------------------------

titulo "Gerando o arquivo"

# Caminhos relativos ao HOME, para o restore cair no lugar certo.
declare -a RELATIVOS=()
for fonte in "${FONTES[@]}"; do
    case "$fonte" in
        "$HOME"/*) RELATIVOS+=("${fonte#"$HOME"/}") ;;
        *) aviso "ignorando $fonte (fora de $HOME); copie manualmente" ;;
    esac
done

TAR_EXTRA=()
if [ "$COM_MODELOS" = 1 ] && [ -d "$HOME/Modelos" ]; then
    if find "$HOME/Modelos" -xtype l -print -quit 2>/dev/null | grep -q .; then
        aviso "há symlinks quebrados em ~/Modelos; eles serão ignorados"
        while IFS= read -r -d '' link; do
            TAR_EXTRA+=(--exclude="${link#"$HOME"/}")
        done < <(find "$HOME/Modelos" -xtype l -print0 2>/dev/null)
    elif find "$HOME/Modelos" -type l -print -quit 2>/dev/null | grep -q .; then
        aviso "há symlinks em ~/Modelos; o conteúdo real deles será copiado (não o link)"
    fi
fi

# Um único tar: o staging (repo pequeno + docs) e depois as pastas do HOME.
# -h grava o conteúdo real dos symlinks (ex.: modelos apontando para o cache
# do Hugging Face), para o backup funcionar em outro computador.
if [ "$COMPRESSOR" = "zstd" ]; then
    tar -h "${TAR_EXTRA[@]}" -C "$STAGE" -cf - repo MANIFEST.txt env-soleria.txt restaurar.sh RESTAURAR.md \
        -C "$HOME" "${RELATIVOS[@]}" | zstd -3 -T0 -q -o "$OUT"
elif [ "$COMPRESSOR" = "gzip" ]; then
    tar -h "${TAR_EXTRA[@]}" -C "$STAGE" -cf - repo MANIFEST.txt env-soleria.txt restaurar.sh RESTAURAR.md \
        -C "$HOME" "${RELATIVOS[@]}" | gzip -6 > "$OUT"
else
    tar -h "${TAR_EXTRA[@]}" -C "$STAGE" -cf "$OUT" repo MANIFEST.txt env-soleria.txt restaurar.sh RESTAURAR.md \
        -C "$HOME" "${RELATIVOS[@]}"
fi

rm -rf "$STAGE"
trap - EXIT

# ----------------------------------------------------------------------
# Verificação
# ----------------------------------------------------------------------

titulo "Verificando"
[ -s "$OUT" ] || morrer "arquivo vazio: $OUT"

case "$OUT" in
    *.tar.zst) tar --zstd -tf "$OUT" >/dev/null ;;
    *.tar.gz)  tar -tzf "$OUT" >/dev/null ;;
    *)         tar -tf "$OUT" >/dev/null ;;
esac || morrer "o arquivo gerado está corrompido"

sha256sum "$OUT" | tee "$OUT.sha256"
tamanho_final="$(stat -c %s "$OUT" 2>/dev/null || echo 0)"

titulo "Backup pronto"
cat <<EOF
  Arquivo : $OUT
  Tamanho : $(humanos "$tamanho_final")
  Checksum: $OUT.sha256

  Copie o .tar.zst E o .sha256 para um pendrive/HD externo ou nuvem.
  Para conferir depois:  sha256sum -c "$(basename "$OUT").sha256"

  No PC novo:
    git clone $REPO_URL ~/.soleria
    ~/.soleria/instalar.sh --backup "$OUT"
EOF
