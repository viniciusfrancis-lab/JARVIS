"""
app_frequencia.py — Saúde da Base de Frequência
Pode rodar standalone:  streamlit run app_frequencia.py
Ou ser chamado pelo vitrine.py via render()

TODO: substitua os blocos marcados com  # <<<  pelos dados reais
      quando o pipeline de frequência estiver pronto.
"""

import base64
from datetime import datetime
from pathlib import Path
import polars as pl

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── Paleta SEDU (mesma do app_alunos) ────────────────────────────────────────
TEAL_DARK  = "#1a6b7a"
TEAL       = "#1e8fa5"
TEAL_MID   = "#2aabc4"
TEAL_LIGHT = "#c8eaf0"
TEAL_PALE  = "#eaf6f9"
GREEN      = "#1D9E75"
GREEN_DARK = "#0F6E56"
GREEN_MID  = "#2aba8a"
GREEN_PALE = "#e8f8f2"
MUTED      = "#718096"
TEXT       = "#2d3748"
PRIO_HIGH    = "#e05a6d"
PRIO_HIGH_BG = "#fdeef0"
PRIO_MED     = "#9f9f1a"
PRIO_MED_BG  = "#e6f4f8"
PRIO_LOW     = "#1D9E75"
PRIO_LOW_BG  = "#e3f5ee"

# ── Ícones por tipo de alerta de frequência ───────────────────────────────────
ALERTA_ICON_FREQ = {
    "Frequência Negativa":                                "📉",
    "Frequência Maior que 100%":                          "⚠️",
    "Frequência Io-iô":                                    "🔁",
    "Faltas Decrescentes no Tempo":                       "📊",
    "Carga Horária Vazia":                                "⏱️",
    "Turma sem Carga Horária":                            "⏱️",
    "Turma sem Carga Horária Registrada":                 "❌",
    "Aluno sem CPF":                                       "👤",
    "Mudança de ID":                                       "🆔",
    "Nome Alterado":                                       "✏️",
    "Mudança de Modalidade/Etapa (Integrado ↔ Regular)":  "🔄",
    "Distorção Idade Série":                              "📐",
    "Última Aparição":                                     "👋",
    "Sem Autodeclaração Racial":                          "📋",
}

# ── Metadados dos alertas (chave = nome no parquet -> (rótulo, prioridade)) ──
ALERTA_META_FREQ = {
    "Frequência Negativa":                                 ("Frequência Negativa", "alta"),
    "Frequência Maior que 100%":                           ("Frequência Maior que 100%", "alta"),
    "Frequência Io-iô":                                     ("Frequência Io-iô", "baixa"),
    "Faltas Decrescentes no Tempo":                         ("Faltas Decrescentes no Tempo", "média"),
    "Carga Horária Vazia":                                  ("Carga Horária Vazia", "alta"),
    "Turma sem Carga Horária":                              ("Turma sem Carga Horária", "alta"),
    "Turma sem Carga Horária Registrada":                   ("Turma sem Carga Horária Registrada", "alta"),
    "Aluno sem CPF":                                         ("Aluno sem CPF", "baixa"),
    "Mudança de ID":                                         ("Mudança de ID", "alta"),
    "Nome Alterado":                                         ("Nome Alterado", "média"),
    "Mudança de Modalidade/Etapa (Integrado ↔ Regular)":     ("Mudança de Modalidade/Etapa (Integrado ↔ Regular)", "baixa"),
    "Distorção Idade Série":                                ("Distorção Idade Série", "baixa"),
    "Última Aparição":                                       ("Última Aparição", "média"),
    "Sem Autodeclaração Racial":                             ("Sem Autodeclaração Racial", "baixa"),
}

# ── CSS ───────────────────────────────────────────────────────────────────────
CSS = f"""
<style>
  .block-container {{ padding-top: 1.25rem !important; padding-left: 3rem !important; padding-right: 3rem !important; max-width: 100% !important; }}
  section[data-testid="stSidebar"] {{ display: none; }}
  header[data-testid="stHeader"]   {{ display: none; }}
  footer {{ display: none; }}

  /* Header — verde para diferenciar visualmente do painel de alunos */
  .freq-header {{
    background: {GREEN_DARK};
    padding: 14px 22px;
    display: flex; align-items: center; justify-content: space-between;
    min-height: 60px; border-radius: 10px;
  }}
  .freq-header-left {{ display: flex; align-items: center; gap: 14px; }}
  .freq-header-divider {{ width: 1px; height: 32px; background: rgba(255,255,255,0.25); }}
  .freq-header-title {{ font-size: 18px; font-weight: 600; color: #fff; margin: 0; }}
  .freq-header-sub   {{ font-size: 11px; color: rgba(255,255,255,0.6); margin: 2px 0 0 0; }}
  .freq-badge {{
    font-size: 11px; color: rgba(255,255,255,0.75);
    background: rgba(255,255,255,0.12); border-radius: 20px;
    padding: 4px 12px; display: flex; align-items: center; gap: 6px;
  }}
  .freq-dot {{ width: 7px; height: 7px; border-radius: 50%; background: #5DCAA5; display: inline-block; }}

  /* Banner */
  .freq-banner {{
    background: linear-gradient(135deg, {GREEN_DARK} 0%, {GREEN} 100%);
    padding: 16px 22px; display: flex; align-items: center; gap: 14px; border-radius: 10px;
  }}
  .freq-banner-num   {{ font-size: 26px !important; font-weight: 600 !important; color: #fff !important; margin: 0 !important; line-height: 1.1 !important; }}
  .freq-banner-label {{ font-size: 11px !important; color: rgba(255,255,255,0.8) !important; margin: 2px 0 0 0 !important; }}
  .freq-banner-chips {{ margin-left: auto; display: flex; gap: 10px; align-items: center; }}
  .freq-chip {{
    display: flex; flex-direction: column; align-items: center;
    background: rgba(255,255,255,0.14); border-radius: 10px; padding: 7px 16px; min-width: 78px;
  }}
  .freq-chip-num   {{ font-size: 17px; font-weight: 700; color: #fff; line-height: 1.1; }}
  .freq-chip-label {{ font-size: 9px; letter-spacing: 0.05em; text-transform: uppercase; color: rgba(255,255,255,0.75); margin-top: 2px; }}
  .freq-chip-dot   {{ display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }}

  /* Corpo */
  .freq-body {{ padding: 1.25rem 0 2rem; }}
  .freq-section-title {{
    font-size: 10px; font-weight: 600; letter-spacing: 0.07em; color: {GREEN_DARK};
    text-transform: uppercase; margin: 1.25rem 0 0.75rem 0;
    padding-bottom: 6px; border-bottom: 2px solid #b2e5d0;
  }}

  /* Cards */
  .freq-cards-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 12px; margin-top: 0.25rem; }}
  .freq-card {{
    position: relative; background: #fff; border: 0.5px solid #b2e5d0;
    border-radius: 10px; border-top: 3px solid {GREEN};
    padding: 12px 14px 14px; overflow: hidden; cursor: default;
    transition: transform .16s ease, box-shadow .16s ease;
  }}
  .freq-card::after {{
    content: ""; position: absolute; right: -28px; bottom: -28px;
    width: 78px; height: 78px; border-radius: 50%; background: {GREEN_PALE}; opacity: .55;
  }}
  .freq-card:hover {{ transform: translateY(-3px); box-shadow: 0 8px 22px rgba(15,110,86,0.16); }}
  .freq-card.warn {{ border-top-color: {PRIO_HIGH}; }}
  .freq-card.warn::after {{ background: {PRIO_HIGH_BG}; }}
  .freq-card.ok   {{ border-top-color: {PRIO_LOW}; }}
  .freq-card.ok::after {{ background: {PRIO_LOW_BG}; }}
  .freq-card-top {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; position: relative; z-index: 1; }}
  .freq-card-icon  {{ font-size: 16px; line-height: 1; flex-shrink: 0; }}
  .freq-card-badge {{ font-size: 9px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; padding: 2px 7px; border-radius: 20px; white-space: nowrap; }}
  .freq-card-badge.high {{ background: {PRIO_HIGH_BG}; color: {PRIO_HIGH}; }}
  .freq-card-badge.med  {{ background: {PRIO_MED_BG};  color: {PRIO_MED}; }}
  .freq-card-badge.low  {{ background: {PRIO_LOW_BG};  color: {PRIO_LOW}; }}
  .freq-card-label {{
    position: relative; z-index: 1; font-size: 11px; color: {MUTED};
    margin: 8px 0 4px 0; line-height: 1.3;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden; min-height: 2.6em;
  }}
  .freq-card-value {{ position: relative; z-index: 1; font-size: 26px; font-weight: 700; color: {GREEN_DARK}; margin: 0; line-height: 1.1; }}
  .freq-card-value.warn {{ color: {PRIO_HIGH}; }}

  /* Placeholder */
  .freq-placeholder {{
    background: linear-gradient(135deg, {GREEN_DARK}12 0%, {GREEN}08 100%);
    border: 1.5px dashed {GREEN}; border-radius: 12px;
    padding: 40px 32px; text-align: center; color: {GREEN_DARK}; margin: 16px 0;
  }}
  .freq-placeholder h2 {{ font-size: 20px; margin: 0 0 10px; font-weight: 700; }}
  .freq-placeholder p  {{ font-size: 13px; color: {MUTED}; margin: 0; line-height: 1.6; }}

  /* Pill */
  .pill {{ font-size: 10px; padding: 2px 8px; border-radius: 20px; font-weight: 600; margin-left: 6px; vertical-align: middle; }}
  .pill.high {{ background: {PRIO_HIGH_BG}; color: {PRIO_HIGH}; }}
  .pill.med  {{ background: {PRIO_MED_BG};  color: {PRIO_MED}; }}
  .pill.low  {{ background: {PRIO_LOW_BG};  color: {PRIO_LOW}; }}
    
    /* Arredonda o gráfico HTML (iframe) de faltas por SRE */
  div[data-testid="stIFrame"] iframe,
  iframe[title="st.iframe"] {{
    border-radius: 14px;
    overflow: hidden;
  }}
  
  div[data-testid="stPlotlyChart"] {{
    background: #fff;
    border-radius: 14px;
    padding: 0px;
  }}
</style>
"""

# ── Helpers ───────────────────────────────────────────────────────────────────
fmt  = lambda v: f"{v:,}".replace(",", ".")
_BASE = Path(__file__).resolve().parent


def _get_logo() -> str:
    p = _BASE / "logo.png"
    if not p.exists():
        return ""
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode()

# ── Carregamento de dados ─────────────────────────────────────────────────────
# <<< Quando o pipeline estiver pronto, implemente esta função com os dados reais
@st.cache_data(ttl=300)
def _carregar_resumo_freq():
    df_raw = pd.read_parquet(_BASE / "Resultados" / "resumo.parquet")
    df_raw.columns = df_raw.columns.str.strip()

    chave = df_raw["alerta"].astype(str).str.strip()

    nao_mapeados = set(chave.unique()) - set(ALERTA_META_FREQ.keys())
    if nao_mapeados:
        st.warning(f"Alertas sem mapeamento em ALERTA_META_FREQ: {nao_mapeados}")

    df_raw["prioridade"] = chave.map(lambda x: ALERTA_META_FREQ.get(x, (x, "baixa"))[1])
    df_raw["alerta"]     = chave.map(lambda x: ALERTA_META_FREQ.get(x, (x, "baixa"))[0])

    df_agg = (
        df_raw.groupby(["alerta", "prioridade"], as_index=False)
        .agg(qtd=("id_aluno", "nunique"))
    )

    total_qtd = df_agg["qtd"].sum()
    df_agg["pct"] = (df_agg["qtd"] / total_qtd * 100).round(1) if total_qtd > 0 else 0.0

    return df_agg[["alerta", "qtd", "pct", "prioridade"]].sort_values("qtd", ascending=False).reset_index(drop=True)


@st.cache_data(ttl=300)
def _carregar_resultados_freq():
    """
    Lê o mesmo parquet (linha a linha) usado para o detalhamento.
    Mapeia 'alerta' para o rótulo amigável e deriva 'prioridade' (para as pills),
    de forma consistente com os cards de visão geral.
    """
    df = pd.read_parquet(_BASE / "Resultados" / "resumo.parquet")
    df.columns = df.columns.str.strip()

    if "alerta" in df.columns:
        chave = df["alerta"].astype(str).str.strip()
        df["prioridade"] = chave.map(lambda x: ALERTA_META_FREQ.get(x, (x, "baixa"))[1])
        df["alerta"]     = chave.map(lambda x: ALERTA_META_FREQ.get(x, (x, "baixa"))[0])
    else:
        df["prioridade"] = "baixa"

    # Datas para exibição amigável (dd/mm/aaaa), se a coluna existir.
    if "Data_Retorno" in df.columns:
        df["Data_Retorno"] = pd.to_datetime(df["Data_Retorno"], errors="coerce").dt.strftime("%d/%m/%Y")

    return df

### inicio do calculo de total dos alunos da base
# Mesmos filtros usados na exploração da BASE_EMPILHADA (6 de 11 valores de num_ano_letivo;
# a mesma lista do ANOS_LETIVOS_VALIDOS de validacoes/professores_excedentes.py).
ANOS_LETIVOS_VALIDOS = [
    "2026",
    "2026 - IASES",
    "2026/2S",
    "2026/2S - UP",
    "2026/2S - IASES",
    "2026/2S CEEJA/NEEJA",
]


@st.cache_data(show_spinner=False, ttl=36000)
def _carregar_total_ativos() -> int:
    """
    Alunos DISTINTOS com matrícula ATIVA, em turma ATIVA, nos anos letivos válidos,
    no snapshot mais recente (dt_referencia máxima) do BASE_EMPILHADA.
    Usado como denominador do medidor do HUD e como teto fixo do eixo X no gráfico
    de alertas por categoria.
    """
    df = pl.scan_parquet(_BASE / "BDados" / "BASE_EMPILHADA.parquet")

    data_ref = (
        df.select(pl.col("dt_referencia").max())
          .collect()
          .item()
    )

    total = (
        df.filter(
            (pl.col("dt_referencia") == data_ref)
            & (pl.col("num_ano_letivo").is_in(ANOS_LETIVOS_VALIDOS))
            & (pl.col("status_turma") == "ATIVA")
            & (pl.col("situacao_matricula") == "ATIVA")
        )
        .select(pl.col("id_aluno").n_unique())
        .collect()
        .item()
    )
    return total

### fim do calculo de total dos alunos da base


### inicio do calculo de saidas/voltas mensais (Io-iô) ───────────────────────
@st.cache_data(show_spinner=False, ttl=300)
def _carregar_saidas_voltas_ioio():
    """
    Lê o frequencia.parquet (saída própria do módulo io-iô, com as colunas
    Episodio_N_Ida / Episodio_N_Volta) e agrega por mês:
      - 'saidas' = contagem de Episodio_*_Ida caindo naquele mês
      - 'voltas' = contagem de Episodio_*_Volta caindo naquele mês
    Cada mês mostra o total daquele mês (não é soma acumulada entre meses).
    """
    caminho = _BASE / "Resultados" / "frequencia.parquet"
    if not caminho.exists():
        return pd.DataFrame(columns=["mes_label", "mes_ord", "saidas", "voltas"])

    df = pl.read_parquet(caminho)

    colunas_ida   = [c for c in df.columns if c.startswith("Episodio_") and c.endswith("_Ida")]
    colunas_volta = [c for c in df.columns if c.startswith("Episodio_") and c.endswith("_Volta")]

    if not colunas_ida or not colunas_volta:
        return pd.DataFrame(columns=["mes_label", "mes_ord", "saidas", "voltas"])

    idas = pl.concat(
        [df.select(pl.col(c).alias("data")) for c in colunas_ida]
    ).drop_nulls()
    voltas = pl.concat(
        [df.select(pl.col(c).alias("data")) for c in colunas_volta]
    ).drop_nulls()

    if idas.height == 0 and voltas.height == 0:
        return pd.DataFrame(columns=["mes_label", "mes_ord", "saidas", "voltas"])

    saidas_mes = (
        idas.with_columns(pl.col("data").dt.strftime("%Y-%m").alias("mes"))
            .group_by("mes").agg(pl.len().alias("saidas")).sort("mes")
    )
    voltas_mes = (
        voltas.with_columns(pl.col("data").dt.strftime("%Y-%m").alias("mes"))
              .group_by("mes").agg(pl.len().alias("voltas")).sort("mes")
    )

    todos_meses = sorted(
        set(saidas_mes["mes"].to_list()) | set(voltas_mes["mes"].to_list())
    )
    s_map = dict(zip(saidas_mes["mes"].to_list(), saidas_mes["saidas"].to_list()))
    v_map = dict(zip(voltas_mes["mes"].to_list(), voltas_mes["voltas"].to_list()))

    meses_pt = {"01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
                "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
                "09": "Set", "10": "Out", "11": "Nov", "12": "Dez"}

    linhas = []
    for m in todos_meses:
        ano, mes_num = m.split("-")
        linhas.append({
            "mes_label": f"{meses_pt[mes_num]}/{ano}",
            "mes_ord":   m,
            "saidas":    int(s_map.get(m, 0)),
            "voltas":    int(v_map.get(m, 0)),
        })

    return pd.DataFrame(linhas)

### fim do calculo de saidas/voltas mensais (Io-iô)

# ── render() ─────────────────────────────────────────────────────────────────
def render():
    st.markdown(CSS, unsafe_allow_html=True)

    df       = _carregar_resumo_freq()
    total    = int(df["qtd"].sum()) if not df.empty else 0
    logo_b64 = _get_logo()

    _qtd_prio = df.groupby("prioridade")["qtd"].sum() if not df.empty else {}
    qtd_alta  = int(_qtd_prio.get("alta",  0))
    qtd_media = int(_qtd_prio.get("média", 0))
    qtd_baixa = int(_qtd_prio.get("baixa", 0))

    ultima_data = datetime.now().strftime("%d/%m/%Y")
    ultima_hora = datetime.now().strftime("%H:%M")

    logo_img = (
        f'<img src="data:image/png;base64,{logo_b64}" '
        f'style="width:130px;height:70px;object-fit:contain;" alt="SEDU"/>'
        if logo_b64 else ""
    )

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="freq-header">
      <div class="freq-header-left">
        {logo_img}
        <div class="freq-header-divider"></div>
        <div>
          <p class="freq-header-title">Saúde da Base de Frequência — SEDU</p>
          <p class="freq-header-sub">Secretaria da Educação · ES</p>
        </div>
      </div>
      <div class="freq-badge">
        <span class="freq-dot"></span>
        {ultima_data} · {ultima_hora}
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Banner ────────────────────────────────────────────────────────────────
    total_str = fmt(total) if total > 0 else "—"
    st.markdown(f"""
    <div class="freq-banner">
      <div style="font-size:22px; color:rgba(255,255,255,0.85);">📅</div>
      <div>
        <div class="freq-banner-num">{total_str}</div>
        <div class="freq-banner-label">alertas de frequência nesta atualização</div>
      </div>
      <div class="freq-banner-chips">
        <div class="freq-chip">
          <span class="freq-chip-num"><span class="freq-chip-dot" style="background:{PRIO_HIGH};"></span>{fmt(qtd_alta) if total > 0 else "—"}</span>
          <span class="freq-chip-label">Alta</span>
        </div>
        <div class="freq-chip">
          <span class="freq-chip-num"><span class="freq-chip-dot" style="background:#bdeaf2;"></span>{fmt(qtd_media) if total > 0 else "—"}</span>
          <span class="freq-chip-label">Média</span>
        </div>
        <div class="freq-chip">
          <span class="freq-chip-num"><span class="freq-chip-dot" style="background:#8fe3c4;"></span>{fmt(qtd_baixa) if total > 0 else "—"}</span>
          <span class="freq-chip-label">Baixa</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="freq-body">', unsafe_allow_html=True)

    # ── Dados reais (quando existirem) ou placeholder ─────────────────────────
    if not df.empty:
        # ── Cards ─────────────────────────────────────────────────────────────
        st.markdown('<p class="freq-section-title">visão geral</p>', unsafe_allow_html=True)

        CARD_CLS  = {"alta": "warn", "média": "", "baixa": "ok"}
        VAL_CLS   = {"alta": "warn", "média": "", "baixa": ""}
        BADGE_CLS = {"alta": "high", "média": "med", "baixa": "low"}
        BADGE_TXT = {"alta": "Alta", "média": "Média", "baixa": "Baixa"}

        cards_html = ['<div class="freq-cards-grid">']
        for row in df.itertuples():
            ccls = CARD_CLS[row.prioridade]
            vcls = VAL_CLS[row.prioridade]
            bcls = BADGE_CLS[row.prioridade]
            btxt = BADGE_TXT[row.prioridade]
            icon = ALERTA_ICON_FREQ.get(row.alerta, "•")
            cards_html.append(
                f'<div class="freq-card {ccls}">'
                f'<div class="freq-card-top">'
                f'<span class="freq-card-icon">{icon}</span>'
                f'<span class="freq-card-badge {bcls}">{btxt}</span>'
                f'</div>'
                f'<p class="freq-card-label" title="{row.alerta}">{row.alerta}</p>'
                f'<p class="freq-card-value {vcls}">{fmt(row.qtd)}</p>'
                f'</div>'
            )
        cards_html.append('</div>')
        st.markdown("".join(cards_html), unsafe_allow_html=True)



        # ── Gráfico de barras ─────────────────────────────────────────────────
        st.markdown('<p class="freq-section-title" style="margin-top:1.5rem;">total de alertas por categoria</p>', unsafe_allow_html=True)

        bar_colors = [
            PRIO_HIGH if p == "alta" else (PRIO_MED if p == "média" else PRIO_LOW)
            for p in df["prioridade"]
        ]
        fig_bar = go.Figure(go.Bar(
            x=df["qtd"], y=df["alerta"], orientation="h",
            marker=dict(color=bar_colors, line=dict(width=0), cornerradius=4),
            text=[fmt(v) for v in df["qtd"]],
            textposition="outside", textfont=dict(size=12, color=TEXT),
            customdata=df["pct"],
            hovertemplate="<b>%{y}</b><br>%{x:,} alertas · %{customdata:.1f}% do total<extra></extra>",
        ))
        
        total_ativos = _carregar_total_ativos()
        
        fig_bar.update_layout(
            height=280, margin=dict(l=0, r=80, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="sans-serif", size=12, color=MUTED),
            xaxis=dict(
                gridcolor="#f0f4f5", showline=False, zeroline=False,
                tickfont=dict(color=TEXT, size=12),
                range=[0, total_ativos],
            ),
            yaxis=dict(autorange="reversed", showgrid=False, showline=False,
                       tickfont=dict(color=TEXT, size=13)),
            showlegend=False,
        )
        st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})

        # ── Gráfico: saídas x voltas mensais (Io-iô) ────────────────────────────
        st.markdown('<p class="freq-section-title" style="margin-top:1.5rem;">saídas e voltas mensais — frequência io-iô</p>', unsafe_allow_html=True)

        df_sv = _carregar_saidas_voltas_ioio()
        if not df_sv.empty:
            fig_sv = go.Figure()
            fig_sv.add_trace(go.Scatter(
                x=df_sv["mes_label"], y=df_sv["saidas"],
                mode="lines+markers", name="Saídas",
                line=dict(color=PRIO_HIGH, width=3),
                marker=dict(size=8, color=PRIO_HIGH, line=dict(color="white", width=1.5)),
                hovertemplate="Saídas: %{y:,}<extra></extra>",
            ))
            fig_sv.add_trace(go.Scatter(
                x=df_sv["mes_label"], y=df_sv["voltas"],
                mode="lines+markers", name="Voltas",
                line=dict(color=GREEN, width=3),
                marker=dict(size=8, color=GREEN, line=dict(color="white", width=1.5)),
                hovertemplate="Voltas: %{y:,}<extra></extra>",
            ))
            fig_sv.update_layout(
                height=320, margin=dict(l=0, r=20, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="sans-serif", size=12, color=MUTED),
                hovermode="x unified",
                xaxis=dict(showgrid=False, showline=True, linecolor="#ddd",
                           tickfont=dict(color=TEXT, size=12)),
                yaxis=dict(gridcolor="#f0f4f5", showline=False, zeroline=False,
                           tickfont=dict(color=TEXT, size=12)),
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            xanchor="right", x=1, font=dict(size=12, color=TEXT)),
            )
            st.plotly_chart(fig_sv, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Sem dados de episódios io-iô (Episodio_N_Ida/Volta) disponíveis para o gráfico.")
        # ── fim gráfico saídas x voltas ──────────────────────────────────────────



        ### gráfico HTML de faltas retroativas por SRE ###
        st.markdown('<p class="freq-section-title" style="margin-top:1.5rem;">Alunos com faltas reduzidas</p>', unsafe_allow_html=True)
        _html_faltas = _BASE / "Grafico_faltas_SRE" / "Faltas Retroativas por SRE.dc.html"
        if _html_faltas.exists():
            with open(_html_faltas, "r", encoding="utf-8") as f:
                html = f.read()
            st.components.v1.html(html, height=800, scrolling=True)
        else:
            st.info("Gráfico de faltas retroativas indisponível (arquivo HTML não encontrado).")
        ### fim do gráfico ###
        
        
        st.markdown(
    '<a href="https://esleycaminhasferreira.shinyapps.io/painel-frequencia-v2" target="_blank" '
    'style="display:inline-block;background-color:white;color:black;padding:8px 20px;border-radius:20px;'
    'border:1px solid #ccc;text-decoration:none;font-size:14px;font-weight:500;">Ver mais</a>',
    unsafe_allow_html=True,
)
        
        import webbrowser

        st.markdown(
            '<a href="#" onclick="window.open(\'/painel_faltas_decrescentes.html\')" target="_blank" '
            'style="display:inline-block;background-color:white;color:black;padding:8px 20px;border-radius:20px;'
            'border:1px solid #ccc;text-decoration:none;font-size:14px;font-weight:500;">Ver mais</a>',
            unsafe_allow_html=True,
        )
        
                
        

    #     # ── Detalhamento ──────────────────────────────────────────────────────
    #     st.markdown('<p class="freq-section-title" style="margin-top:1.5rem;">detalhamento</p>', unsafe_allow_html=True)

    #     COLUNAS_EXIBIR_FREQ = [
    #         "alerta", "Status_Frequencia", "Detalhe_Frequencia",
    #         "nm_regional", "nm_municipio", "nm_escola",
    #         "nome_ano_escolaridade", "dc_turno",
    #         "nm_aluno", "id_aluno", "nasc_str", "Data_Retorno",
    #     ]
    #     LABELS_COLUNAS_FREQ = {
    #         "alerta": "Alerta", "Status_Frequencia": "Status", "Detalhe_Frequencia": "Detalhe",
    #         "nm_regional": "Regional", "nm_municipio": "Município", "nm_escola": "Escola",
    #         "nome_ano_escolaridade": "Ano/Série", "dc_turno": "Turno",
    #         "nm_aluno": "Aluno", "id_aluno": "ID Aluno", "nasc_str": "Nascimento",
    #         "Data_Retorno": "Data",
    #     }
    #     PRIO_PILL = {"alta": ("alta", "high"), "média": ("média", "med"), "baixa": ("baixa", "low")}

    #     df_res = _carregar_resultados_freq()

    #     # Filtros adaptativos: Regional/Escola só aparecem se existirem no parquet.
    #     tem_regional = "nm_regional" in df_res.columns
    #     tem_escola   = "nm_escola"   in df_res.columns

    #     filtros  = ["alerta"] + (["regional"] if tem_regional else []) + (["escola"] if tem_escola else [])
    #     larguras = {"alerta": 2, "regional": 2, "escola": 3}
    #     colunas_st = st.columns([larguras[f] for f in filtros] + [1])
    #     col_map = dict(zip(filtros, colunas_st))
    #     col_dl  = colunas_st[-1]

    #     alertas_disp = sorted(df_res["alerta"].dropna().unique().tolist()) if "alerta" in df_res.columns else []
    #     with col_map["alerta"]:
    #         filtro_alerta = st.selectbox("Tipo de alerta", ["Todos"] + alertas_disp)

    #     df_filtrado = df_res.copy()
    #     if filtro_alerta != "Todos" and "alerta" in df_filtrado.columns:
    #         df_filtrado = df_filtrado[df_filtrado["alerta"] == filtro_alerta]

    #     if tem_regional:
    #         regionais_disp = sorted(df_filtrado["nm_regional"].dropna().unique().tolist())
    #         with col_map["regional"]:
    #             filtro_regional = st.selectbox("Regional", ["Todas"] + regionais_disp)
    #         if filtro_regional != "Todas":
    #             df_filtrado = df_filtrado[df_filtrado["nm_regional"] == filtro_regional]

    #     if tem_escola:
    #         escolas_disp = sorted(df_filtrado["nm_escola"].dropna().unique().tolist())
    #         with col_map["escola"]:
    #             filtro_escola = st.selectbox("Escola", ["Todas"] + escolas_disp)
    #         if filtro_escola != "Todas":
    #             df_filtrado = df_filtrado[df_filtrado["nm_escola"] == filtro_escola]

    #     csv = df_filtrado.to_csv(index=False, sep=";", encoding="utf-8-sig")
    #     with col_dl:
    #         st.markdown("<div style='margin-top:1.6rem;'>", unsafe_allow_html=True)
    #         st.download_button("⬇ CSV", data=csv, file_name="alertas_frequencia_detalhamento.csv",
    #                            mime="text/csv", use_container_width=True)
    #         st.markdown("</div>", unsafe_allow_html=True)

    #     n = len(df_filtrado)
    #     st.markdown(f'<p style="font-size:12px;color:{MUTED};margin:4px 0 10px;">{fmt(n)} registro(s) encontrado(s)</p>', unsafe_allow_html=True)

    #     cols_presentes = [c for c in COLUNAS_EXIBIR_FREQ if c in df_filtrado.columns and df_filtrado[c].notna().any()]
    #     df_exibir = df_filtrado[cols_presentes].rename(columns=LABELS_COLUNAS_FREQ).reset_index(drop=True)

    #     thead = "".join(
    #         f'<th style="font-size:11px;font-weight:600;color:#fff;background:{GREEN_DARK};'
    #         f'padding:9px 14px;text-align:left;white-space:nowrap;position:sticky;top:0;z-index:2;">{c}</th>'
    #         for c in df_exibir.columns
    #     )
    #     tbody = ""
    #     df_head        = df_filtrado.head(500).reset_index(drop=True)
    #     df_exibir_head = df_exibir.head(500).reset_index(drop=True)
    #     for i, row in df_exibir_head.iterrows():
    #         cells = ""
    #         for col_name, val in row.items():
    #             val_str = "" if pd.isna(val) else str(val)
    #             td_base = ("padding:9px 14px;white-space:nowrap;vertical-align:middle;"
    #                        "border-bottom:0.5px solid #e8f4f7;color:#2d3748;background:#ffffff;")
    #             if col_name == "Alerta":
    #                 prio = df_head.at[i, "prioridade"] if "prioridade" in df_head.columns else "baixa"
    #                 ptxt, pcls = PRIO_PILL.get(prio, ("baixa", "low"))
    #                 cells += (f'<td style="{td_base}"><span style="white-space:nowrap;">'
    #                           f'{val_str} <span class="pill {pcls}">{ptxt}</span></span></td>')
    #             else:
    #                 cells += f'<td style="{td_base}">{val_str}</td>'
    #         tbody += f"<tr>{cells}</tr>"

    #     st.markdown(f"""
    #     <div style="border:0.5px solid #b2e5d0;border-radius:10px;overflow:auto;max-height:500px;background:#fff;">
    #       <table style="border-collapse:collapse;font-size:13px;min-width:100%;">
    #         <thead><tr>{thead}</tr></thead>
    #         <tbody>{tbody}</tbody>
    #       </table>
    #     </div>
    #     """, unsafe_allow_html=True)

    #     if len(df_filtrado) > 500:
    #         st.caption(f"Exibindo 500 de {fmt(len(df_filtrado))} registros. Use o CSV para ver todos.")

    # else:
    #     # Placeholder visual enquanto o pipeline não existe
    #     st.markdown(f"""
    #     <div class="freq-placeholder">
    #       <h2>📅 Saúde da Base de Frequência</h2>
    #       <p>
    #         Painel em construção.<br><br>
    #         Para ativar este painel, implemente a função
    #         <code>_carregar_resumo_freq()</code> em <b>app_frequencia.py</b>
    #         apontando para o parquet gerado pelo pipeline de frequência.
    #       </p>
    #     </div>
    #     """, unsafe_allow_html=True)

        # Preview dos cards que virão (opacidade reduzida)
        st.markdown('<p class="freq-section-title" style="margin-top:1rem;">tipos de alerta previstos</p>', unsafe_allow_html=True)

        previstos = [
            ("📉", "Frequência abaixo de 75%",     "alta"),
            ("📆", "Faltas consecutivas > 5 dias",  "alta"),
            ("🔁", "Oscilação de frequência",       "média"),
            ("📋", "Frequência não registrada",     "média"),
            ("✅", "Frequência regular",            "baixa"),
            ("📊", "Faltas decrescentes",           "média"),
            ("👤", "Alunos sem CPF",                "alta"),
            ("⚠️", "Frequência maior que 100%",     "alta"),
           
        ]
        BADGE_CLS = {"alta": "high", "média": "med", "baixa": "low"}
        BADGE_TXT = {"alta": "Alta", "média": "Média", "baixa": "Baixa"}
        CARD_CLS  = {"alta": "warn", "média": "", "baixa": "ok"}

        cards_prev = ['<div class="freq-cards-grid">']
        for icon, label, prio in previstos:
            cards_prev.append(
                f'<div class="freq-card {CARD_CLS[prio]}" style="opacity:0.5;">'
                f'<div class="freq-card-top">'
                f'<span class="freq-card-icon">{icon}</span>'
                f'<span class="freq-card-badge {BADGE_CLS[prio]}">{BADGE_TXT[prio]}</span>'
                f'</div>'
                f'<p class="freq-card-label">{label}</p>'
                f'<p class="freq-card-value" style="color:{MUTED};font-size:18px;">em breve</p>'
                f'</div>'
            )
        cards_prev.append('</div>')
        st.markdown("".join(cards_prev), unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)  # fecha freq-body



# ── Popup de erro ─────────────────────────────────────────────────────────────
CAMINHO_ERRO_PNG = Path(__file__).parent / "erro.png"

@st.dialog("Erro no painel")
def mostrar_erro(mensagem):
    st.image(str(CAMINHO_ERRO_PNG), use_container_width=True)
    st.error("Ocorreu um erro ao carregar o painel.")
    with st.expander("Detalhes técnicos"):
        st.code(mensagem)
    if st.button("Fechar"):
        st.rerun()

# # ── Execução standalone ───────────────────────────────────────────────────────

if __name__ == "__main__" or not hasattr(st, "_is_running_with_vitrine"):
    st.set_page_config(
        page_title="Saúde da Base de Frequência — SEDU",
        page_icon="📅",
        layout="wide",
    )
    try:
        render()
    except Exception as e:
        mostrar_erro(str(e))



# if __name__ == "__main__" or not hasattr(st, "_is_running_with_vitrine"):
#     st.set_page_config(
#         page_title="Saúde da Base de Frequência — SEDU",
#         page_icon="📅",
#         layout="wide",
#     )
#     render()
