"""
app_alunos_temas.py — Painel de Alunos com troca de HUD por botão no fim da página.

Temas: J.A.R.V.I.S. (padrão, igual aos painéis de frequência e turmas), GTA VI e MW4.
A escolha fica na sessão (st.session_state), então o st_autorefresh do vitrine não volta ao tema padrão.
O botão avança para o próximo tema da lista a cada clique.

No vitrine.py:
    import app_alunos_temas
    ...
    app_alunos_temas.render()
"""

import streamlit as st

# Impede os módulos de se auto-executarem no import (eles checam esse atributo).
st._is_running_with_vitrine = True

import app_alunos_hud         # noqa: E402  (GTA VI)
import app_alunos_hud_jarvis  # noqa: E402  (J.A.R.V.I.S.)
import app_alunos_hud_mw4     # noqa: E402  (MW4)

# A ordem aqui é a ordem em que o botão percorre os temas.
TEMAS = {
    "jarvis": ("J.A.R.V.I.S.", app_alunos_hud_jarvis),
    "gtavi":  ("GTA VI",       app_alunos_hud),
    "mw4":    ("MW4",          app_alunos_hud_mw4),
}
PADRAO = "jarvis"
CHAVE  = "alunos_tema"


def render():
    tema = st.session_state.get(CHAVE, PADRAO)
    if tema not in TEMAS:
        tema = PADRAO

    TEMAS[tema][1].render()

    # Botão no fim da página (o estilo vem do CSS do tema ativo)
    chaves = list(TEMAS)
    proximo = chaves[(chaves.index(tema) + 1) % len(chaves)]
    if st.button(f"🎮 Alterar HUD  ·  atual: {TEMAS[tema][0]}  →  {TEMAS[proximo][0]}", key="btn_alterar_hud"):
        st.session_state[CHAVE] = proximo
        st.rerun()


# ── Execução standalone ───────────────────────────────────────────────────────
if __name__ == "__main__":
    st.set_page_config(page_title="Saúde da Base de Alunos — SEDU", page_icon="📊", layout="wide")
    render()
