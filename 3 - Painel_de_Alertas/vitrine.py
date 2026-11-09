"""
vitrine.py — Painel TV rotativo (monitor vertical 24")
Alterna automaticamente a cada 10 minutos entre:
  • app_alunos.py     → Saúde da Base de Alunos
  • app_frequencia_hud.py → Saúde da Base de Frequência
  • app_turma.py      → Saúde da Base de Turmas

Dependência extra:
    pip install streamlit-autorefresh

Como rodar:
    streamlit run vitrine.py --server.port 8502
"""
import sys
import threading
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

# ── Popup de erro ─────────────────────────────────────────────────────────────
CAMINHO_ERRO_PNG = Path(__file__).parent / "erro.png"

@st.dialog("Erro no painel", width="large")
def mostrar_erro(mensagem):
    st.image(str(CAMINHO_ERRO_PNG), use_container_width=True)
    st.error("Ocorreu um erro ao carregar o painel.")
    with st.expander("Detalhes técnicos"):
        st.code(mensagem)
    if st.button("Fechar"):
        st.rerun()
        
        


# ── Importa os painéis ────────────────────────────────────────────────────────
st._is_running_with_vitrine = True

sys.path.insert(0, str(Path(r"N:\05 - Arquivos Pessoais\Vinicius\4 - Painel_Alerta_Frequencia")))
# append (e não insert) para a pasta do painel 4 manter prioridade em nomes repetidos
# (as duas pastas têm processar.py e validacoes/; aqui só o app_turma é importado).
sys.path.append(str(Path(r"N:\05 - Arquivos Pessoais\Vinicius\5 - Painel_Alerta_Turma")))

import app_alunos_temas
import app_frequencia_hud
import app_turma_hud

# ── Configuração ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Painel TV — SEDU",
    page_icon="📺",
    layout="wide",
)

# ── Trava de renderização (corrige painéis duplicados) ────────────────────────
# Os HUDs trocam st.markdown / st.plotly_chart / components.html e constantes dos módulos base
# DURANTE render(). Isso é global do processo, não da sessão: duas sessões renderizando ao
# mesmo tempo (TV + outra aba, ou o autorefresh coincidindo com um clique) capturam o wrapper
# uma da outra, injetam banner/palco de um painel no outro e podem deixar um wrapper instalado
# para sempre. A trava serializa os renders e _restaurar_originais() descarta qualquer vazamento.
@st.cache_resource
def _estado_global():
    # Executa uma única vez, antes de qualquer render(): guarda as funções ORIGINAIS do Streamlit.
    return {
        "lock": threading.RLock(),
        "orig": {
            "markdown":    st.markdown,
            "plotly_chart": st.plotly_chart,
            "html":        components.html,
        },
    }

_TRAVA = _estado_global()["lock"]
_ORIG  = _estado_global()["orig"]

def _restaurar_originais():
    st.markdown     = _ORIG["markdown"]
    st.plotly_chart = _ORIG["plotly_chart"]
    components.html = _ORIG["html"]

with _TRAVA:
    _restaurar_originais()


# ── Constantes ────────────────────────────────────────────────────────────────
DURACAO_SEG = 10 * 60
REFRESH_MS  = 30 * 1000

PAINEIS = ["alunos", "freq", "turma"]
LABELS  = {
    "alunos": "📊 Saúde da Base de Alunos",
    "freq":   "📅 Saúde da Base de Frequência",
    "turma":  "🏫 Saúde da Base de Turmas",
}
CORES_BARRA = {
    "alunos": "#1e8fa5",
    "freq":   "#0F6E56",
    "turma":  "#0F6E56",   # mesmo verde do header do app_turma
}
MUTED = "#718096"

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
  header[data-testid="stHeader"] {{ display: none; }}
  footer {{ display: none; }}
  section[data-testid="stSidebar"] {{ display: none; }}
  .block-container {{
    padding: 0.75rem 1.5rem 0 !important;
    max-width: 100% !important;
  }}

  /* Remove estilo padrão dos botões Streamlit dentro da barra */
  div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] > button {{
    width: 100%;
    padding: 10px 0;
    font-size: 13px;
    font-weight: 600;
    border-radius: 8px;
    border: none;
    letter-spacing: 0.02em;
    cursor: pointer;
    transition: opacity 0.2s;
  }}
  div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] > button:hover {{
    opacity: 0.88;
    border: none;
  }}

  /* Botão ATIVO — alunos */
  div[data-testid="stHorizontalBlock"] div[data-testid="stButton"].btn-ativo-alunos > button {{
    background: linear-gradient(135deg, #1e8fa5 0%, #2aabc4 100%) !important;
    color: #fff !important;
    box-shadow: 0 2px 6px rgba(30,143,165,0.35);
  }}

  /* Botão ATIVO — freq */
  div[data-testid="stHorizontalBlock"] div[data-testid="stButton"].btn-ativo-freq > button {{
    background: linear-gradient(135deg, #0F6E56 0%, #1D9E75 100%) !important;
    color: #fff !important;
    box-shadow: 0 2px 6px rgba(15,110,86,0.35);
  }}

  /* Botão ATIVO — turma */
  div[data-testid="stHorizontalBlock"] div[data-testid="stButton"].btn-ativo-turma > button {{
    background: linear-gradient(135deg, #0F6E56 0%, #1D9E75 100%) !important;
    color: #fff !important;
    box-shadow: 0 2px 6px rgba(15,110,86,0.35);
  }}

  /* Botão INATIVO */
  div[data-testid="stHorizontalBlock"] div[data-testid="stButton"].btn-inativo > button {{
    background: #f0f4f5 !important;
    color: {MUTED} !important;
    box-shadow: none;
  }}

  .vitrine-timer {{
    font-size: 11px;
    color: {MUTED};
    text-align: right;
    margin-bottom: 6px;
  }}
  .vitrine-progress-wrap {{
    background: #e8eff1;
    border-radius: 20px;
    height: 4px;
    margin-bottom: 6px;
    overflow: hidden;
  }}
  .vitrine-progress-bar {{
    height: 100%;
    border-radius: 20px;
  }}
</style>
""", unsafe_allow_html=True)

# ── Autorefresh ───────────────────────────────────────────────────────────────
st_autorefresh(interval=REFRESH_MS, key="vitrine_refresh")

# ── Controle de estado ────────────────────────────────────────────────────────
agora = time.time()

if "vitrine_inicio" not in st.session_state:
    st.session_state.vitrine_inicio = agora
    st.session_state.vitrine_painel = "alunos"

elapsed = agora - st.session_state.vitrine_inicio

if elapsed >= DURACAO_SEG:
    idx_atual = PAINEIS.index(st.session_state.vitrine_painel)
    proximo   = PAINEIS[(idx_atual + 1) % len(PAINEIS)]
    st.session_state.vitrine_painel = proximo
    st.session_state.vitrine_inicio = agora
    elapsed = 0

painel_ativo  = st.session_state.vitrine_painel
progresso_pct = min(int((elapsed / DURACAO_SEG) * 100), 100)
restante_seg  = max(0, int(DURACAO_SEG - elapsed))
minutos       = restante_seg // 60
segundos      = restante_seg % 60

idx_ativo     = PAINEIS.index(painel_ativo)
proximo_key   = PAINEIS[(idx_ativo + 1) % len(PAINEIS)]
proximo_label = LABELS[proximo_key]
cor_barra     = CORES_BARRA[painel_ativo]

# ── Barra de botões clicáveis ─────────────────────────────────────────────────
cols = st.columns(len(PAINEIS))

for col, key in zip(cols, PAINEIS):
    css_class = f"btn-ativo-{key}" if key == painel_ativo else "btn-inativo"

    # Injeta a classe CSS no container do botão via JavaScript
    col.markdown(
        f'<style>div[data-testid="stHorizontalBlock"] '
        f'div[data-testid="stButton"]:nth-child({PAINEIS.index(key)+1})'
        f'{{ /* placeholder */ }}</style>',
        unsafe_allow_html=True,
    )

    with col:
        # Marca o container com a classe correta usando um div wrapper
        st.markdown(
            f'<div class="{css_class}" style="display:contents"></div>',
            unsafe_allow_html=True,
        )
        if st.button(LABELS[key], key=f"btn_{key}", use_container_width=True):
            st.session_state.vitrine_painel = key
            st.session_state.vitrine_inicio = agora
            st.rerun()

# ── Barra de progresso e timer ────────────────────────────────────────────────
st.markdown(f"""
<div class="vitrine-progress-wrap">
  <div class="vitrine-progress-bar"
       style="width:{progresso_pct}%; background:{cor_barra};"></div>
</div>
<div class="vitrine-timer">
  🔄 Próximo: <b>{proximo_label}</b> em <b>{minutos:02d}:{segundos:02d}</b>
</div>
""", unsafe_allow_html=True)

# # ── Renderiza o painel ativo ──────────────────────────────────────────────────
# if painel_ativo == "alunos":
#     app_alunos.render()
# else:
#     app_frequencia_hud.render()
# ── Renderiza o painel ativo ──────────────────────────────────────────────────
# Sob a trava e com os originais restaurados antes e depois: só uma sessão por vez mexe nos patches.
try:
    with _TRAVA:
        _restaurar_originais()
        try:
            if painel_ativo == "alunos":
                app_alunos_temas.render()
            elif painel_ativo == "freq":
                app_frequencia_hud.render()
            else:
                app_turma_hud.render()
        finally:
            _restaurar_originais()
except Exception as e:
    mostrar_erro(str(e))
