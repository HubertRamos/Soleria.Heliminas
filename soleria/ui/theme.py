"""Tema visual da Soleria: paleta, expressões e estilos do prompt_toolkit."""

from pathlib import Path

from soleria.persona.emotions import EMOCOES

PASTA_EXPRESSOES = Path(__file__).resolve().parent / "expressoes"

# O catálogo emocional é a única fonte de verdade: a TUI não mantém uma
# segunda lista de imagens, cores ou rótulos.
EXPRESSOES = {
    emocao.chave: (emocao.arquivo, emocao.cor) for emocao in EMOCOES
}

HUMORES = {emocao.chave: emocao.rotulo for emocao in EMOCOES}

# Paleta da Soleria. O ciano é a assinatura dela; o rosa aparece nos
# detalhes e nas falas, sem poluir a leitura.
COR_FUNDO = "#0b0e13"
COR_PAINEL = "#0d1219"
COR_ENTRADA = "#101722"
COR_BORDA = "#243444"
COR_TEXTO = "#d7e2ec"
COR_FRACO = "#61758a"
COR_CIANO = "#55f5ee"
COR_ROSA = "#ff55cf"
COR_AMARELO = "#ffd34e"

FRAMES_STATUS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def classe_expressao(nome):
    return f"expr_{nome.lower()}"


def construir_estilos():
    """Estilos nomeados usados pela TUI."""
    estilos = {
        "": f"bg:{COR_FUNDO} {COR_TEXTO}",
        "raiz": f"bg:{COR_FUNDO} {COR_TEXTO}",
        "barra_titulo": f"bg:{COR_PAINEL} {COR_TEXTO}",
        "marca": f"bg:{COR_PAINEL} {COR_CIANO} bold",
        "marca_nome": f"bg:{COR_PAINEL} #f2fbff bold",
        "marca_sub": f"bg:{COR_PAINEL} {COR_FRACO}",
        "barra_dica": f"bg:{COR_PAINEL} {COR_FRACO}",
        "barra_dica_forte": f"bg:{COR_PAINEL} {COR_CIANO}",
        "divisor": f"bg:{COR_FUNDO} #1c2a38",
        "regua": f"bg:{COR_FUNDO} {COR_BORDA}",
        "painel": f"bg:{COR_PAINEL} {COR_TEXTO}",
        "area_chat": f"bg:{COR_FUNDO} {COR_TEXTO}",
        "historico": f"bg:{COR_FUNDO} {COR_TEXTO}",
        "status": f"bg:{COR_FUNDO} {COR_FRACO}",
        "status_ativo": f"bg:{COR_FUNDO} {COR_CIANO}",
        "status_aviso": f"bg:{COR_FUNDO} {COR_AMARELO}",
        "status_ocio": f"bg:{COR_FUNDO} {COR_FRACO}",
        "entrada": f"bg:{COR_ENTRADA} #e8f2fc",
        "prompt_entrada": f"bg:{COR_ENTRADA} {COR_CIANO} bold",
        "borda": f"bg:{COR_PAINEL} {COR_BORDA}",
        "borda_acento": f"bg:{COR_PAINEL} {COR_CIANO} bold",
        "titulo_painel": f"bg:{COR_PAINEL} #f2fbff bold",
        "rotulo": f"bg:{COR_FUNDO} {COR_FRACO} bold",
        "rotulo_voce": f"bg:{COR_FUNDO} {COR_CIANO} bold",
        "rotulo_soleria": f"bg:{COR_FUNDO} {COR_ROSA} bold",
        "rotulo_sistema": f"bg:{COR_FUNDO} {COR_AMARELO} bold",
        "barra_voce": f"bg:{COR_FUNDO} #2e7f83",
        "barra_soleria": f"bg:{COR_FUNDO} #7a3466",
        "barra_sistema": f"bg:{COR_FUNDO} #6b5b2a",
        "corpo_voce": f"bg:{COR_FUNDO} {COR_TEXTO}",
        "corpo_soleria": f"bg:{COR_FUNDO} {COR_TEXTO}",
        "corpo_sistema": f"bg:{COR_FUNDO} #b9c7d6 italic",
        "texto_fraco": f"bg:{COR_FUNDO} {COR_FRACO}",
        "fala_atual": f"bg:{COR_PAINEL} #9fb3c7 italic",
        "rotulo_painel": f"bg:{COR_PAINEL} {COR_FRACO} bold",
        "cursor_ia": f"bg:{COR_FUNDO} {COR_ROSA} bold",
        "msg_sistema": f"{COR_AMARELO} italic",
        "gravando": f"bg:{COR_FUNDO} {COR_ROSA} bold",
        # Paleta de comandos / configurações
        "menu": f"bg:{COR_PAINEL} {COR_TEXTO}",
        "menu_corpo": f"bg:{COR_PAINEL} {COR_TEXTO}",
        "menu_filtro": f"bg:{COR_ENTRADA} #e8f2fc",
        "menu_regua": f"bg:{COR_PAINEL} {COR_BORDA}",
        "menu_lista": f"bg:{COR_PAINEL} {COR_TEXTO}",
        "menu_item": f"bg:{COR_PAINEL} #b9c7d6",
        "menu_item_ativo": f"bg:{COR_ENTRADA} {COR_CIANO} bold",
        "menu_titulo": f"bg:{COR_PAINEL} {COR_CIANO} bold",
        "menu_ajuda": f"bg:{COR_PAINEL} {COR_FRACO}",
        "menu_dica": f"bg:{COR_PAINEL} #9fb3c7 italic",
        "menu_aviso": f"bg:{COR_PAINEL} {COR_AMARELO}",
        "menu_vazio": f"bg:{COR_PAINEL} {COR_FRACO} italic",
        "frame.border": f"bg:{COR_PAINEL} {COR_BORDA}",
        "frame.label": f"bg:{COR_PAINEL} {COR_CIANO} bold",
    }
    for nome, (_arquivo, cor) in EXPRESSOES.items():
        estilos[classe_expressao(nome)] = f"bold {cor}"
        estilos[f"humor_{nome.lower()}"] = cor
    return estilos


# Alias privado usado por código/testes antigos.
_classe_expressao = classe_expressao
_FRAMES_STATUS = FRAMES_STATUS
