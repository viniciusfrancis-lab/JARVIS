"""
app_alunos_hud_mw4.py — Saúde da Base de Alunos com tema HUD inspirado na série Call of Duty: Modern Warfare (MW4).

Não altera o app_alunos.py: importa o módulo, troca paleta + CSS, injeta um "palco" logo após o banner
(bússola, minimapa com varredura, contador no estilo de munição, barras segmentadas, nível de ameaça
e linha de objetivo — tudo calculado do resumo.parquet) e chama render().
Rodar:  streamlit run app_alunos_hud_mw4.py   (ou pelo app_alunos_temas.py, que tem o botão de troca)
"""

import base64
import html
import math
import random
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import streamlit as st

# Impede o app_alunos de se auto-executar no import (ele checa esse atributo).
st._is_running_with_vitrine = True

import app_alunos as base  # noqa: E402

# ── Chaves liga/desliga ───────────────────────────────────────────────────────
SANKEY_ESCURO = True   # inverte as cores do iframe do Sankey (fundo branco → escuro). Se as cores ficarem estranhas: False
AMEACA_BORDA  = True   # borda vermelha pulsando (efeito de "vida baixa") quando há categoria de ALTA prioridade com ocorrência
CARROSSEL     = True   # cards da "visão geral" rolando em loop (pausa ao passar o mouse)
PERSEGUICAO   = True   # helicóptero com holofote perseguindo um veículo, embaixo do carrossel (só com CARROSSEL = True)

# ── Paleta militar: grafite, verde-visão-noturna, âmbar ───────────────────────
BG, SOLID, PANEL, PANEL2, LINE = "#0a0d0b", "#151a16", "rgba(18,24,20,.88)", "#1d241e", "#38423a"
TEXT, MUTED = "#e9eee6", "#8fa08f"
AMBER, RED, GREEN, SAND = "#ffb000", "#ff4a3d", "#6fd16a", "#b7a77a"

# Constantes do app_alunos lidas em tempo de execução dentro do render(). São aplicadas só
# durante render() e restauradas depois, para não contaminar outros painéis no vitrine.
_OVERRIDES = {
    "TEAL_DARK": TEXT, "TEAL_LIGHT": LINE, "MUTED": MUTED, "TEXT": TEXT,
    "PRIO_HIGH": RED, "PRIO_MED": AMBER, "PRIO_LOW": GREEN,
}

fmt = base.fmt
OUT = "text-shadow: 1px 1px 0 #000, -1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000;"
MONO = "'Share Tech Mono', 'Consolas', monospace"
CONDENSED = "'Rajdhani', 'Bahnschrift', 'Arial Narrow', sans-serif"


# ── Fundo da PÁGINA: imagem sua (opcional) ou cena noturna gerada em SVG ──────
PAGE_BG = None       # ex.: "fundo.png"  (imagem SEM texto, na mesma pasta do app)
PAGE_BG_DIM = 0.35   # 0 = imagem pura · 1 = tudo escuro
_PAGE_CANDIDATOS = ["page_bg.png", "page_bg.jpg", "fundo.png", "fundo.jpg", "fundo.webp",
                    "background.png", "background.jpg", "bg.png", "bg.jpg", "bg.webp"]
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def _uri_svg(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def _cume(W, base_y, amp, fill, seed):
    """Linha de cume de montanha (silhueta)."""
    rnd = random.Random(seed)
    f1, f2 = rnd.random() * 6.28, rnd.random() * 6.28
    pts = []
    for x in range(0, W + 41, 40):
        y = base_y - amp * (0.55 * math.sin(x / 230 + f1) + 0.30 * math.sin(x / 90 + f2) + 0.15 * rnd.random())
        pts.append(f"{x},{y:.0f}")
    return f'<polygon points="{" ".join(pts)} {W + 40},1080 0,1080" fill="{fill}"/>'


@lru_cache(maxsize=1)
def _cena_svg() -> str:
    """Noite em terreno montanhoso: lua, três cristas, holofotes e luzes de cidade lá embaixo."""
    W, H = 1920, 1080
    rnd = random.Random(33)
    p = [
        '<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#050807"/><stop offset=".55" stop-color="#0f1812"/>'
        '<stop offset="1" stop-color="#22331f"/></linearGradient>'
        '<radialGradient id="halo"><stop offset="0" stop-color="#cfe6cf" stop-opacity=".35"/>'
        '<stop offset="1" stop-color="#cfe6cf" stop-opacity="0"/></radialGradient></defs>',
        f'<rect width="{W}" height="{H}" fill="url(#sky)"/>',
    ]
    for _ in range(90):
        p.append(f'<circle cx="{rnd.randint(0, W)}" cy="{rnd.randint(0, 520)}" r="{rnd.choice([0.8, 1.1, 1.5])}" '
                 f'fill="#e9eee6" fill-opacity="{rnd.choice([0.3, 0.5, 0.7])}"/>')
    p.append('<circle cx="1500" cy="170" r="150" fill="url(#halo)"/><circle cx="1500" cy="170" r="44" fill="#d7ead7" fill-opacity=".88"/>')
    p.append(_cume(W, 640, 170, "#16231a", 1))
    p.append(_cume(W, 740, 150, "#101a13", 2))
    p.append('<polygon points="380,1080 440,1080 760,0 600,0" fill="#dfffe0" fill-opacity=".05"/>')
    p.append('<polygon points="1480,1080 1540,1080 1260,0 1100,0" fill="#dfffe0" fill-opacity=".05"/>')
    p.append(_cume(W, 840, 120, "#0a110c", 3))
    x = -20   # luzes da cidade ao pé da serra
    while x < W:
        w, h = rnd.randint(30, 90), rnd.randint(50, 220)
        y = H - h
        p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#070a08"/>')
        for cx in range(x + 6, x + w - 8, 12):
            for cy in range(y + 10, H - 6, 18):
                if rnd.random() < 0.11:
                    p.append(f'<rect x="{cx}" y="{cy}" width="4" height="7" fill="{rnd.choice([AMBER, "#e9eee6"])}" fill-opacity="{rnd.choice([0.4, 0.6])}"/>')
        x += w + rnd.randint(-4, 8)
    return _uri_svg(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid slice">'
                    + "".join(p) + "</svg>")


@lru_cache(maxsize=1)
def _page_bg_uri() -> str:
    nomes = [PAGE_BG] if PAGE_BG else _PAGE_CANDIDATOS
    for nome in nomes:
        for pasta in (base._BASE, Path.cwd()):
            p = pasta / nome
            if p.is_file() and p.suffix.lower() in _MIME:
                return f"data:{_MIME[p.suffix.lower()]};base64," + base64.b64encode(p.read_bytes()).decode()
    return _cena_svg()


def _page_bg_layers() -> str:
    dim = f"rgba(8,12,9,{PAGE_BG_DIM})"
    return (f"linear-gradient({dim}, {dim}), "
            f"url({_page_bg_uri()}) center / cover no-repeat fixed, "
            f"{BG}")


# ── Minimapa: anel de prioridades + varredura ─────────────────────────────────
def _radar_svg(qa, qm, ql, total):
    tot = max(total, 1)
    a, m, l = qa / tot * 100, qm / tot * 100, ql / tot * 100

    def arc(r, w, color, start, size):
        return (f'<circle cx="150" cy="150" r="{r}" fill="none" stroke="{color}" stroke-width="{w}" '
                f'pathLength="100" stroke-dasharray="{size:.2f} {100 - size:.2f}" '
                f'stroke-dashoffset="{-start:.2f}" transform="rotate(-90 150 150)"/>')

    ticks = "".join(
        f'<line x1="150" y1="34" x2="150" y2="{42 if i % 3 == 0 else 38}" stroke="{MUTED}" stroke-opacity=".75" '
        f'transform="rotate({i * 10} 150 150)"/>' for i in range(36))
    return "".join([
        '<svg viewBox="0 0 300 300" class="mw-radar" xmlns="http://www.w3.org/2000/svg">',
        f'<circle cx="150" cy="150" r="146" fill="#000" fill-opacity=".55" stroke="{LINE}" stroke-width="2"/>',
        '<circle cx="150" cy="150" r="124" fill="none" stroke="#1b221d" stroke-width="10"/>',
        arc(124, 10, RED, 0, a), arc(124, 10, AMBER, a, m), arc(124, 10, GREEN, a + m, l),
        '<circle cx="150" cy="150" r="106" fill="#0a100c" stroke="#000" stroke-width="2"/>',
        ticks,
        '<g stroke="#26382a" stroke-width="1" fill="none"><circle cx="150" cy="150" r="80"/>'
        '<circle cx="150" cy="150" r="53"/><circle cx="150" cy="150" r="27"/>'
        '<line x1="44" y1="150" x2="256" y2="150"/><line x1="150" y1="44" x2="150" y2="256"/></g>',
        f'<polygon points="150,150 118,66 182,66" fill="#fff" fill-opacity=".07"/>',
        f'<g class="mw-sweep"><path d="M150 150 L150 44 A106 106 0 0 1 242 97 Z" fill="{GREEN}" fill-opacity=".18"/>'
        f'<line x1="150" y1="150" x2="242" y2="97" stroke="{GREEN}" stroke-opacity=".85" stroke-width="1.5"/></g>',
        f'<polygon points="150,138 158,160 150,155 142,160" fill="{AMBER}" stroke="#000" stroke-width="1.5"/>',
        '<text x="150" y="62" text-anchor="middle" class="r-n">N</text>',
        f'<rect x="98" y="186" width="104" height="40" fill="#000" fill-opacity=".88" stroke="{AMBER}" stroke-width="1"/>',
        f'<text x="150" y="208" text-anchor="middle" class="r-num">{fmt(total)}</text>',
        '<text x="150" y="220" text-anchor="middle" class="r-lbl">ALERTAS</text>',
        '</svg>',
    ])


def _tile(label, value, tone, bar=None, sub=None):
    barh = (f'<div class="mw-bar"><i class="{tone}" style="width:{min(max(bar, 0), 100):.0f}%"></i></div>'
            if bar is not None else "")
    subh = f'<span class="mw-tile-s">{html.escape(str(sub))}</span>' if sub else ""
    return (f'<div class="mw-tile {tone}"><span class="mw-tile-l">{label}</span>'
            f'<span class="mw-tile-v">{value}</span>{subh}{barh}</div>')


def _compass_html(agora):
    """Faixa de bússola no topo (decorativa: desliza devagar). O quadro central mostra hora e data reais."""
    rotulos = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    ciclo = "".join(f'<span class="{"n" if r == "N" else ""}">{r}</span>' for r in rotulos)
    metade = ciclo * 3
    return ('<div class="mw-compass"><div class="mw-tape">'
            f'<div class="mw-half">{metade}</div><div class="mw-half">{metade}</div></div>'
            f'<div class="mw-head"><b>{agora:%H:%M}</b><i>{agora:%d/%m/%Y}</i></div></div>')


def _stage_html():
    df = base._carregar_resumo()
    if df.empty:
        return ""
    total = int(df["qtd"].sum())
    pr = df.groupby("prioridade")["qtd"].sum()
    qa, qm, ql = int(pr.get("alta", 0)), int(pr.get("média", 0)), int(pr.get("baixa", 0))
    share = lambda q: (q / total * 100) if total else 0.0

    n_cat = int((df["qtd"] > 0).sum())
    top = df.iloc[0]  # _carregar_resumo já ordena por qtd desc

    # Saúde da base = categorias do ALERTA_META SEM ocorrência / total de categorias
    total_cats = len({lbl for lbl, _ in base.ALERTA_META.values()})
    limpas = max(total_cats - n_cat, 0)

    # Nível de ameaça = categorias de ALTA prioridade com ocorrência / total de categorias de alta
    alta_total = sum(1 for _, p in base.ALERTA_META.values() if p == "alta")
    alta_ativas = int(((df["prioridade"] == "alta") & (df["qtd"] > 0)).sum())
    pips = "".join(f'<span class="{"on" if i < alta_ativas else ""}">◆</span>' for i in range(alta_total))

    agora = datetime.now()
    left = "".join([
        _tile("Alta prioridade", fmt(qa), "alta", share(qa)),
        _tile("Média prioridade", fmt(qm), "media", share(qm)),
        _tile("Baixa prioridade", fmt(ql), "baixa", share(ql)),
    ])
    right = "".join([
        f'<div class="mw-ammo"><span class="mw-tile-l">Total de alertas</span>'
        f'<span class="mw-ammo-n">{fmt(total)}<em>/ {n_cat} cat.</em></span></div>',
        _tile("Saúde da base", f"{limpas}/{total_cats}", "baixa",
              (limpas / total_cats * 100) if total_cats else None, sub="categorias sem ocorrência"),
        (f'<div class="mw-threat" title="Losangos acesos = categorias de alta prioridade com ocorrência">'
         f'<span class="mw-tile-l">Nível de ameaça</span><span class="mw-pips">{pips}</span></div>'
         if alta_total else ""),
    ])
    legenda = (f'<div class="mw-legend"><span><b style="background:{RED}"></b>Alta</span>'
               f'<span><b style="background:{AMBER}"></b>Média</span>'
               f'<span><b style="background:{GREEN}"></b>Baixa</span></div>')
    objetivo = (f'<div class="mw-objective"><span class="k">◆ Maior ocorrência</span> '
                f'{html.escape(str(top["alerta"]))} — {fmt(int(top["qtd"]))} alertas '
                f'({share(int(top["qtd"])):.1f}% do total)</div>')
    ameaca = '<div class="mw-hurt"></div>' if (AMEACA_BORDA and alta_ativas > 0) else ""

    return (f'{ameaca}<p class="sedu-section-title" style="margin-top:1.25rem;">painel de controle</p>'
            f'{_compass_html(agora)}'
            f'<div class="mw-stage"><div class="mw-side">{left}</div>'
            f'<div class="mw-core">{_radar_svg(qa, qm, ql, total)}{legenda}</div>'
            f'<div class="mw-side">{right}</div></div>{objetivo}')


# ── Cena do carrossel: helicóptero com holofote perseguindo um veículo ────────
def _roda(cx):
    return (f'<g class="mw-wheel"><circle cx="{cx}" cy="34" r="8" fill="#0a0d0b"/>'
            f'<circle cx="{cx}" cy="34" r="3.2" fill="#9aa59a"/>'
            f'<line x1="{cx}" y1="30.5" x2="{cx}" y2="37.5" stroke="#555" stroke-width="1.4"/></g>')


def _heli_svg():
    """Helicóptero de lado, nariz (cabine) à direita, cauda à esquerda."""
    cor, borda = "#3a4a3c", "#0b0f0c"
    return ('<svg class="mw-car" viewBox="0 0 150 56" width="100" height="37" xmlns="http://www.w3.org/2000/svg">'
            f'<g class="mw-rotor"><line x1="38" y1="9" x2="150" y2="9" stroke="{borda}" stroke-width="2.5" stroke-linecap="round"/></g>'
            f'<rect x="94" y="9" width="3" height="8" fill="{borda}"/>'
            f'<path d="M62 27 L14 24 L14 30 L62 34Z" fill="{cor}" stroke="{borda}"/>'
            f'<path d="M14 24 L5 10 L22 12Z" fill="{cor}" stroke="{borda}"/>'
            f'<circle class="mw-tail" cx="10" cy="17" r="6" fill="none" stroke="{MUTED}" stroke-width="1" stroke-dasharray="2 2"/>'
            f'<path d="M60 30 Q66 16 96 16 Q124 16 132 30 Q124 42 96 42 Q66 42 60 30Z" fill="{cor}" stroke="{borda}"/>'
            '<path d="M104 20 Q122 22 130 30 L104 30Z" fill="#9fd8e0" fill-opacity=".55"/>'
            f'<path d="M70 50 L126 50 M80 42 L78 50 M114 42 L116 50" stroke="{borda}" stroke-width="2" fill="none"/>'
            '<circle cx="126" cy="36" r="3" fill="#fff3c4"/></svg>')


def _suv_svg():
    """SUV militar de lado, frente (capô curto) à direita."""
    return ('<svg class="mw-car" viewBox="0 0 120 44" width="100" height="37" xmlns="http://www.w3.org/2000/svg">'
            '<rect x="20" y="12" width="44" height="3" fill="#0b0f0c"/>'
            '<path d="M8 31 L8 15 L72 15 L92 22 L112 23 L115 31 Q115 34 111 34 L12 34 Q8 34 8 31Z" fill="#2f3d31"/>'
            '<path d="M14 18 L69 18 L84 23 L14 23Z" fill="#0f1511"/>'
            f'<rect x="8" y="26" width="107" height="2" fill="{SAND}" fill-opacity=".7"/>'
            '<rect x="112" y="24" width="4" height="4" fill="#ffe55c"/><rect x="7" y="22" width="3" height="5" fill="#ff2a2a"/>'
            + _roda(32) + _roda(94) + '</svg>')


def _cena_html():
    return ('<div class="mw-scene"><div class="mw-pair">'
            '<svg class="mw-beam" width="300" height="92" viewBox="0 0 300 92" xmlns="http://www.w3.org/2000/svg">'
            '<polygon points="84,28 160,62 215,62" fill="#fff3c4" fill-opacity=".30"/></svg>'
            f'<div class="mw-heli">{_heli_svg()}</div><div class="mw-suv">{_suv_svg()}</div></div></div>')


def _carrossel_html(body):
    """Transforma a grade de cards do app_alunos num carrossel infinito (conjunto duplicado + translateX(-50%))."""
    pre, pos = '<div class="sedu-cards-grid">', '</div>'
    inner = body[len(pre):-len(pos)]
    n = inner.count('<div class="sedu-card ')
    dur = max(n * 6, 30)   # ~6 s por card → dá para ler
    html_ = (f'<div class="mw-carousel"><div class="mw-track" style="animation-duration:{dur}s">'
             f'<div class="mw-set">{inner}</div><div class="mw-set" aria-hidden="true">{inner}</div></div></div>')
    return html_ + (_cena_html() if PERSEGUICAO else "")


# ── Injeções no st.markdown / st.plotly_chart durante o render() ──────────────
def _make_md(orig):
    def _md(body, *args, **kwargs):
        if (CARROSSEL and isinstance(body, str) and body.startswith('<div class="sedu-cards-grid">')
                and body.endswith('</div>')):
            body = _carrossel_html(body)
        orig(body, *args, **kwargs)
        if isinstance(body, str) and 'class="sedu-banner"' in body:
            palco = _stage_html()
            if palco:
                orig(palco, unsafe_allow_html=True)
    return _md


def _make_pc(orig):
    """Os gráficos do app_alunos têm fundo branco e fontes pretas fixos; aqui eles são re-tematizados."""
    def _pc(fig, *args, **kwargs):
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(color=TEXT),
                          legend=dict(font=dict(color=TEXT), bgcolor="rgba(18,24,20,.92)", bordercolor=LINE))
        for upd in (fig.update_xaxes, fig.update_yaxes):
            upd(gridcolor="#2a322c", linecolor=LINE, tickfont=dict(color=TEXT), title_font=dict(color=MUTED))
        fig.update_shapes(line=dict(color=LINE))
        return orig(fig, *args, **kwargs)
    return _pc


# ── CSS ───────────────────────────────────────────────────────────────────────
_SANKEY_CSS = ".stApp iframe { filter: invert(1) hue-rotate(180deg); }" if SANKEY_ESCURO else ""
_CUT = "clip-path: polygon(0 0, calc(100% - 14px) 0, 100% 14px, 100% 100%, 14px 100%, 0 calc(100% - 14px));"
_CUT_S = "clip-path: polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 0 100%);"
_SEG = "repeating-linear-gradient(90deg, #000 0 6px, transparent 6px 8px)"

HUD_CSS = f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=Share+Tech+Mono&display=swap');

  .stApp {{
    background: {_page_bg_layers()} !important;
    font-family: {CONDENSED};
    color: {TEXT};
  }}
  /* vinheta + tom de visão noturna + linhas de varredura (estáticos) */
  .stApp::after {{
    content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 9999;
    background:
      radial-gradient(ellipse at center, transparent 58%, rgba(0,0,0,.6) 100%),
      repeating-linear-gradient(0deg, rgba(0,0,0,.10) 0 1px, transparent 1px 3px),
      linear-gradient(rgba(40,80,40,.05), rgba(40,80,40,.05));
  }}
  .stApp p, .stApp label, .stApp span, .stApp li {{ color: {TEXT}; }}
  code {{ color: {AMBER} !important; background: {SOLID} !important; }}

  /* Borda vermelha pulsando (vida baixa) */
  .mw-hurt {{ position: fixed; inset: 0; z-index: 9997; pointer-events: none;
    box-shadow: inset 0 0 140px 30px rgba(255,40,30,.5); animation: mwhurt 2.4s ease-in-out infinite; }}
  @keyframes mwhurt {{ 0%, 100% {{ opacity: .12; }} 50% {{ opacity: .75; }} }}

  /* Header */
  .sedu-header {{
    background: linear-gradient(90deg, #171d18 0%, #0f1410 100%) !important;
    border: 1px solid {LINE}; border-left: 5px solid {AMBER}; border-radius: 0 !important;
    clip-path: polygon(0 0, calc(100% - 20px) 0, 100% 20px, 100% 100%, 0 100%);
  }}
  .sedu-header-divider {{ background: {LINE} !important; }}
  .sedu-header .sedu-header-title {{
    font-family: {CONDENSED} !important; font-weight: 700 !important; font-size: 28px !important;
    letter-spacing: .16em; text-transform: uppercase; color: #fff !important;
  }}
  .sedu-header .sedu-header-sub {{ font-family: {MONO}; color: {MUTED} !important; letter-spacing: .14em; text-transform: uppercase; }}
  .sedu-badge {{ background: #000 !important; border: 1px solid {LINE}; border-radius: 0 !important; color: {TEXT} !important; font-family: {MONO}; }}
  .sedu-dot {{ background: {GREEN} !important; border-radius: 0 !important; box-shadow: 0 0 6px {GREEN}; }}

  /* Banner */
  .sedu-banner {{
    background: linear-gradient(90deg, #1a211b 0%, #232c24 100%) !important;
    border: 1px solid {LINE}; border-left: 5px solid {AMBER}; border-radius: 0 !important; margin-top: 10px;
  }}
  .sedu-banner .sedu-banner-num {{ font-family: {MONO} !important; font-weight: 400 !important; font-size: 40px !important; color: {AMBER} !important; text-shadow: 0 0 12px {AMBER}88; }}
  .sedu-banner .sedu-banner-label {{ color: {MUTED} !important; letter-spacing: .16em; text-transform: uppercase; }}
  .sedu-chip {{ background: #000 !important; border: 1px solid {LINE}; border-radius: 0 !important; }}
  .sedu-chip .sedu-chip-num {{ color: #fff !important; font-family: {MONO}; }}
  .sedu-chip .sedu-chip-label {{ color: {MUTED} !important; }}
  .sedu-chip:nth-child(1) .sedu-chip-dot {{ background: {RED} !important; }}
  .sedu-chip:nth-child(2) .sedu-chip-dot {{ background: {AMBER} !important; }}
  .sedu-chip:nth-child(3) .sedu-chip-dot {{ background: {GREEN} !important; }}
  .sedu-chip .sedu-chip-dot {{ border-radius: 0 !important; }}

  /* Títulos de seção */
  .sedu-section-title {{
    color: #fff !important; border-bottom: 1px solid {LINE} !important;
    font-family: {CONDENSED}; font-weight: 700 !important; font-size: 16px !important; letter-spacing: .22em;
  }}
  .sedu-section-title::before {{ content: "▌"; color: {AMBER}; margin-right: 8px; }}

  /* ── Bússola ── */
  .mw-compass {{
    position: relative; height: 38px; margin: 6px 0 14px; overflow: hidden;
    background: rgba(8,12,9,.8); border: 1px solid {LINE};
    -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 12%, #000 88%, transparent 100%);
    mask-image: linear-gradient(90deg, transparent 0, #000 12%, #000 88%, transparent 100%);
  }}
  .mw-tape {{
    display: flex; width: max-content; height: 100%; animation: mwtape 180s linear infinite;
    background:
      repeating-linear-gradient(90deg, {MUTED} 0 1px, transparent 1px 14px) bottom / 100% 7px no-repeat,
      repeating-linear-gradient(90deg, #d8e6d8 0 2px, transparent 2px 70px) bottom / 100% 12px no-repeat;
  }}
  @keyframes mwtape {{ to {{ transform: translateX(-50%); }} }}
  .mw-half {{ display: flex; }}
  .mw-half span {{ flex: 0 0 140px; width: 140px; text-align: center; line-height: 22px; font-weight: 700; font-size: 15px; letter-spacing: .12em; color: {TEXT}; }}
  .mw-half span.n {{ color: {AMBER}; }}
  .mw-compass .mw-head {{
    position: absolute; left: 50%; top: 0; transform: translateX(-50%); display: flex; align-items: baseline; gap: 10px;
    padding: 2px 14px; background: #000; border: 1px solid {AMBER}; border-top: 0;
  }}
  .mw-compass .mw-head b {{ font-family: {MONO}; font-weight: 400; font-size: 17px; color: {AMBER}; }}
  .mw-compass .mw-head i {{ font-style: normal; font-size: 11px; letter-spacing: .12em; color: {MUTED}; }}

  /* ── Palco ── */
  .mw-stage {{ display: grid; grid-template-columns: 1fr 340px 1fr; gap: 22px; align-items: center; margin: 8px 0 10px; }}
  .mw-side {{ display: flex; flex-direction: column; gap: 10px; }}
  .mw-core {{ display: flex; flex-direction: column; align-items: center; gap: 8px; }}
  .mw-radar {{ width: 100%; max-width: 320px; filter: drop-shadow(0 6px 14px rgba(0,0,0,.7)); }}
  .mw-radar .mw-sweep {{ transform-box: view-box; transform-origin: 150px 150px; animation: mwsweep 4s linear infinite; }}
  @keyframes mwsweep {{ to {{ transform: rotate(360deg); }} }}
  .mw-radar .r-num {{ font-family: {MONO}; font-size: 22px; fill: {AMBER}; }}
  .mw-radar .r-lbl {{ font-family: {CONDENSED}; font-weight: 700; font-size: 9px; letter-spacing: .26em; fill: {MUTED}; }}
  .mw-radar .r-n {{ font-family: {CONDENSED}; font-weight: 700; font-size: 13px; fill: #fff; stroke: #000; stroke-width: 3px; paint-order: stroke; }}
  .mw-stage .mw-legend {{ display: flex; gap: 16px; font-size: 13px; font-weight: 600; letter-spacing: .12em; text-transform: uppercase; }}
  .mw-stage .mw-legend span {{ display: flex; align-items: center; gap: 6px; color: {TEXT}; }}
  .mw-stage .mw-legend b {{ width: 10px; height: 10px; display: inline-block; }}

  .mw-tile {{
    background: {PANEL}; {_CUT_S}
    border: 1px solid {LINE}; border-left: 4px solid {SAND}; padding: 10px 14px;
    display: grid; grid-template-columns: 1fr auto; row-gap: 6px; align-items: baseline;
  }}
  .mw-tile.alta  {{ border-left-color: {RED}; }}
  .mw-tile.media {{ border-left-color: {AMBER}; }}
  .mw-tile.baixa {{ border-left-color: {GREEN}; }}
  .mw-stage .mw-tile-l {{ font-size: 12px; font-weight: 600; letter-spacing: .16em; text-transform: uppercase; color: {MUTED}; }}
  .mw-stage .mw-tile-v {{ font-family: {MONO}; font-size: 28px; color: #fff; }}
  .mw-stage .mw-tile.alta  .mw-tile-v {{ color: {RED}; }}
  .mw-stage .mw-tile.media .mw-tile-v {{ color: {AMBER}; }}
  .mw-stage .mw-tile.baixa .mw-tile-v {{ color: {GREEN}; }}
  .mw-stage .mw-tile-s {{ grid-column: 1 / -1; font-size: 12px; color: {TEXT}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  /* barras segmentadas, como pentes de munição */
  .mw-bar {{ grid-column: 1 / -1; height: 10px; background: repeating-linear-gradient(90deg, #1c231e 0 6px, transparent 6px 8px); }}
  .mw-bar i {{ display: block; height: 100%; background: {SAND}; -webkit-mask: {_SEG}; mask: {_SEG}; }}
  .mw-bar i.alta {{ background: {RED}; }} .mw-bar i.media {{ background: {AMBER}; }} .mw-bar i.baixa {{ background: {GREEN}; }}

  /* Contador no estilo de munição */
  .mw-ammo {{ display: flex; flex-direction: column; align-items: flex-end; gap: 2px; padding: 8px 4px 4px; }}
  .mw-stage .mw-ammo-n {{ font-family: {MONO}; font-size: 54px; line-height: 1; color: #fff; {OUT} }}
  .mw-stage .mw-ammo-n em {{ font-style: normal; font-size: 22px; color: {AMBER}; margin-left: 10px; }}
  .mw-threat {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; background: #000; border: 1px solid {LINE}; padding: 6px 14px; }}
  .mw-stage .mw-pips span {{ font-size: 20px; color: #2b332d; margin: 0 2px; }}
  .mw-stage .mw-pips span.on {{ color: {RED}; text-shadow: 0 0 8px {RED}aa; animation: mwpip 1.2s steps(1) infinite; }}
  @keyframes mwpip {{ 50% {{ color: #a3261c; }} }}

  /* Linha de objetivo */
  .mw-objective {{
    margin: 6px 0 18px; padding: 9px 16px; background: rgba(0,0,0,.6); border-left: 3px solid {AMBER};
    font-weight: 600; font-size: 16px; letter-spacing: .04em; color: #fff; {OUT}
  }}
  .mw-objective .k {{ color: {AMBER}; text-transform: uppercase; letter-spacing: .14em; margin-right: 8px; }}

  /* Cards — placas táticas */
  .sedu-card {{
    background: {PANEL} !important; {_CUT}
    border: 1px solid {LINE} !important; border-top: 3px solid {AMBER} !important; border-radius: 0 !important;
  }}
  .sedu-card::after {{ background: {AMBER}1a !important; opacity: 1 !important; }}
  .sedu-card.warn {{ border-top-color: {RED} !important; }}
  .sedu-card.warn::after {{ background: {RED}1f !important; }}
  .sedu-card.ok   {{ border-top-color: {GREEN} !important; }}
  .sedu-card.ok::after {{ background: {GREEN}1f !important; }}
  .sedu-card:hover {{ border-color: {AMBER} !important; box-shadow: none !important; }}
  .sedu-card .sedu-card-label {{ color: {MUTED} !important; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; }}
  .sedu-card .sedu-card-value {{ font-family: {MONO}; font-weight: 400 !important; font-size: 30px !important; color: {AMBER} !important; text-shadow: 0 0 8px {AMBER}55; }}
  .sedu-card .sedu-card-value.warn {{ color: {RED} !important; text-shadow: 0 0 8px {RED}55; }}
  .sedu-card .sedu-card-value.ok   {{ color: {GREEN} !important; text-shadow: 0 0 8px {GREEN}55; }}
  .sedu-card-badge.high, .pill.high {{ background: {RED}2e !important; color: #ff8d83 !important; border: 1px solid {RED}99; border-radius: 0; }}
  .sedu-card-badge.med,  .pill.med  {{ background: {AMBER}2a !important; color: {AMBER} !important; border: 1px solid {AMBER}99; border-radius: 0; }}
  .sedu-card-badge.low,  .pill.low  {{ background: {GREEN}2a !important; color: #9be698 !important; border: 1px solid {GREEN}99; border-radius: 0; }}

  /* Carrossel */
  .mw-carousel {{
    overflow: hidden; padding: 12px 0 14px;
    -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 5%, #000 95%, transparent 100%);
    mask-image: linear-gradient(90deg, transparent 0, #000 5%, #000 95%, transparent 100%);
  }}
  .mw-track {{ display: flex; width: max-content; animation: mwscroll linear infinite; will-change: transform; }}
  .mw-set {{ display: flex; gap: 12px; padding-right: 12px; }}
  @keyframes mwscroll {{ to {{ transform: translateX(-50%); }} }}
  .mw-carousel:hover .mw-track, .mw-carousel:hover .sedu-card {{ animation-play-state: paused; }}
  .mw-track .sedu-card {{ flex: 0 0 200px; width: 200px; animation: mwbob 4s ease-in-out infinite alternate; }}
  .mw-set .sedu-card:nth-child(3n+2) {{ animation-delay: -1.3s; }}
  .mw-set .sedu-card:nth-child(3n)   {{ animation-delay: -2.6s; }}
  @keyframes mwbob {{ from {{ transform: translateY(0); }} to {{ transform: translateY(-6px); }} }}

  /* Cena: helicóptero com holofote perseguindo um veículo */
  .mw-scene {{
    position: relative; height: 92px; margin: 10px 0 6px; overflow: hidden; border: 1px solid {LINE};
    background: linear-gradient(180deg, #0e1510 0%, #1a2a1d 58%, #121812 58%, #0b0f0c 100%);
  }}
  .mw-scene::before {{
    content: ""; position: absolute; left: 0; right: 0; top: 86px; height: 3px;
    background: repeating-linear-gradient(90deg, rgba(233,238,230,.6) 0 28px, transparent 28px 64px);
    animation: mwline .5s linear infinite;
  }}
  @keyframes mwline {{ to {{ background-position: -64px 0; }} }}
  .mw-pair {{ position: absolute; left: 0; top: 0; width: 300px; height: 92px; animation: mwchase 9s linear infinite; will-change: transform; }}
  @keyframes mwchase {{
    0%   {{ transform: translateX(-320px); }}
    78%  {{ transform: translateX(100vw); }}
    100% {{ transform: translateX(100vw); }}
  }}
  .mw-beam {{ position: absolute; left: 0; top: 0; animation: mwbeam 1.1s ease-in-out infinite alternate; }}
  @keyframes mwbeam {{ from {{ opacity: .65; }} to {{ opacity: 1; }} }}
  .mw-heli {{ position: absolute; left: 0; top: 4px; animation: mwhover 1.8s ease-in-out infinite alternate; }}
  @keyframes mwhover {{ from {{ transform: translateY(0) rotate(0deg); }} to {{ transform: translateY(5px) rotate(1.5deg); }} }}
  .mw-suv {{ position: absolute; left: 150px; bottom: 8px; animation: mwweave 1.4s ease-in-out infinite alternate; }}
  @keyframes mwweave {{ from {{ transform: translateY(0) rotate(0deg); }} to {{ transform: translateY(-3px) rotate(-1deg); }} }}
  .mw-car {{ display: block; filter: drop-shadow(0 4px 6px rgba(0,0,0,.6)); }}
  .mw-wheel {{ transform-box: fill-box; transform-origin: center; animation: mwspin .3s linear infinite; }}
  @keyframes mwspin {{ to {{ transform: rotate(360deg); }} }}
  .mw-rotor {{ transform-box: fill-box; transform-origin: center; animation: mwrotor .1s linear infinite alternate; }}
  @keyframes mwrotor {{ from {{ transform: scaleX(1); }} to {{ transform: scaleX(.3); }} }}
  .mw-tail {{ transform-box: fill-box; transform-origin: center; animation: mwspin .25s linear infinite; }}
  @media (prefers-reduced-motion: reduce) {{
    .mw-track, .mw-track .sedu-card, .mw-pair, .mw-beam, .mw-heli, .mw-suv, .mw-wheel, .mw-rotor, .mw-tail, .mw-tape,
    .mw-sweep, .mw-hurt, .mw-scene::before {{ animation: none !important; }}
  }}

  /* Caixa da legenda do gráfico de barras (fundo branco inline) */
  div[style*="padding:14px 18px"] {{ background: {PANEL} !important; border: 1px solid {LINE} !important; border-radius: 0 !important; }}

  /* Gráficos */
  div[data-testid="stPlotlyChart"] {{ background: {PANEL} !important; border: 1px solid {LINE}; border-radius: 0 !important; padding: 8px; }}

  /* Tabela (estilos inline brancos → !important) */
  div[data-testid="stMarkdownContainer"] table td {{ background: {SOLID} !important; color: {TEXT} !important; border-bottom: 1px solid {LINE} !important; }}
  div[data-testid="stMarkdownContainer"] table tr:hover td {{ background: {PANEL2} !important; }}
  div[data-testid="stMarkdownContainer"] table th {{ background: #0a0d0b !important; color: {AMBER} !important; border-bottom: 2px solid {AMBER} !important; letter-spacing: .1em; text-transform: uppercase; }}
  div[style*="overflow:auto"] {{ background: {SOLID} !important; border: 1px solid {LINE} !important; border-radius: 0 !important; }}

  /* Widgets */
  div[data-baseweb="select"] > div, div[data-baseweb="input"] > div {{ background: {SOLID} !important; border-color: {LINE} !important; border-radius: 0 !important; color: {TEXT} !important; }}
  div[data-baseweb="select"] * {{ color: {TEXT} !important; }}
  ul[role="listbox"] {{ background: {SOLID} !important; }}
  .stDownloadButton button, .stButton button {{
    background: transparent !important; color: {AMBER} !important; border: 1px solid {AMBER} !important; border-radius: 0 !important;
    font-family: {CONDENSED}; font-weight: 700; letter-spacing: .14em; text-transform: uppercase;
  }}
  .stDownloadButton button:hover, .stButton button:hover {{ background: {AMBER} !important; color: #000 !important; }}
  div[data-testid="stCaptionContainer"] * {{ color: {MUTED} !important; }}
  a[href*="shinyapps"] {{ background: transparent !important; color: {AMBER} !important; border: 1px solid {AMBER} !important; border-radius: 0 !important; text-transform: uppercase; letter-spacing: .14em; font-weight: 700; }}

  {_SANKEY_CSS}
</style>
"""


# ── render() — mesmo contrato do app_alunos.render(), para uso no vitrine ─────
def render():
    orig_md, orig_pc, orig_css = st.markdown, st.plotly_chart, base.CSS
    orig_consts = {k: getattr(base, k) for k in _OVERRIDES}
    try:
        for k, v in _OVERRIDES.items():
            setattr(base, k, v)
        base.CSS = orig_css + HUD_CSS
        st.markdown = _make_md(orig_md)
        st.plotly_chart = _make_pc(orig_pc)
        base.render()
    finally:
        st.markdown, st.plotly_chart = orig_md, orig_pc
        base.CSS = orig_css
        for k, v in orig_consts.items():
            setattr(base, k, v)


# ── Execução standalone ───────────────────────────────────────────────────────
if __name__ == "__main__":
    st.set_page_config(page_title="Saúde da Base de Alunos — SEDU", page_icon="📊", layout="wide")
    render()
