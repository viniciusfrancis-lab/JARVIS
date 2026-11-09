"""
app_alunos_hud.py — Saúde da Base de Alunos com tema HUD inspirado em GTA VI (Vice City ao pôr do sol).

Não altera o app_alunos.py: importa o módulo, troca paleta + CSS, injeta um "palco" logo após
o banner (medidor com sol retrô, relógio, total, barra de saúde, estrelas de procura e legenda,
tudo calculado do resumo.parquet) e chama render().
Rodar:  streamlit run app_alunos_hud.py
"""

import base64
import html
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
SIRENE        = True   # faixa vermelho/azul piscando no topo quando há categoria de ALTA prioridade com ocorrência
CARROSSEL     = True   # cards da "visão geral" rolando em loop (pausa ao passar o mouse)
PERSEGUICAO   = True   # carro sendo perseguido por viatura numa estrada embaixo do carrossel (só com CARROSSEL = True)

# ── Paleta Vice City: pôr do sol neon ─────────────────────────────────────────
BG, SOLID, PANEL, PANEL2, LINE = "#0f0626", "#1a0f33", "rgba(26,14,52,.84)", "#251546", "#4a2b6b"
TEXT, MUTED = "#fff5fb", "#c9a9d9"
PINK, ORANGE, TEAL, VIOLET, SUN = "#ff2e7e", "#ffa530", "#1fe0c4", "#9b5cff", "#ffd23f"
RED, BLUE = "#ff2a2a", "#2a6bff"   # só para a sirene

# Constantes do app_alunos lidas em tempo de execução dentro do render(). São aplicadas só
# durante render() e restauradas depois, para não contaminar outros painéis no vitrine.
_OVERRIDES = {
    "TEAL_DARK": TEXT, "TEAL_LIGHT": LINE, "MUTED": MUTED, "TEXT": TEXT,
    "PRIO_HIGH": PINK, "PRIO_MED": ORANGE, "PRIO_LOW": TEAL,
}

fmt = base.fmt
OUT = "text-shadow: 2px 2px 0 rgba(0,0,0,.75), -1px -1px 0 rgba(0,0,0,.75), 1px -1px 0 rgba(0,0,0,.75), -1px 1px 0 rgba(0,0,0,.75);"


def GRAD(c1: str, c2: str) -> str:
    """Texto com degradê (números grandes)."""
    return (f"background: linear-gradient(180deg, {c1} 0%, {c2} 100%); -webkit-background-clip: text; "
            f"background-clip: text; -webkit-text-fill-color: transparent; color: transparent; "
            f"filter: drop-shadow(0 2px 0 rgba(0,0,0,.6));")


# ── Fundo da PÁGINA: imagem sua (opcional) ou cena gerada em SVG ──────────────
PAGE_BG = None       # ex.: "fundo.png"  (imagem SEM texto, na mesma pasta do app)
PAGE_BG_DIM = 0.30   # 0 = imagem pura · 1 = tudo escuro
_PAGE_CANDIDATOS = ["page_bg.png", "page_bg.jpg", "fundo.png", "fundo.jpg", "fundo.webp",
                    "background.png", "background.jpg", "bg.png", "bg.jpg", "bg.webp"]
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def _uri_svg(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def _palma(x, base_y, h, lean, esc):
    """Palmeira em silhueta: tronco curvo + folhas."""
    tx, ty = x + lean * h, base_y - h
    cor = "#08020f"
    p = [f'<path d="M{x} {base_y} Q{x + lean * h * 0.15} {base_y - h * 0.55} {tx} {ty}" '
         f'stroke="{cor}" stroke-width="{14 * esc:.1f}" fill="none" stroke-linecap="round"/>']
    for ang in (-178, -150, -122, -92, -62, -32, -2, 28, 150):
        L = 210 * esc
        p.append(f'<path d="M0 0 Q{L * .5:.0f} {-L * .30:.0f} {L:.0f} {L * .16:.0f} Q{L * .5:.0f} {-L * .04:.0f} 0 0" '
                 f'fill="{cor}" transform="translate({tx:.0f} {ty:.0f}) rotate({ang})"/>')
    return "".join(p)


@lru_cache(maxsize=1)
def _cena_svg() -> str:
    """Pôr do sol retrô: céu em degradê, sol listrado, mar com reflexo, skyline e palmeiras."""
    W, H, hy = 1920, 1080, 700
    rnd = random.Random(21)
    p = [
        '<defs>'
        f'<linearGradient id="sky" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="{hy}">'
        '<stop offset="0" stop-color="#0f0626"/><stop offset=".30" stop-color="#2c0d5a"/>'
        '<stop offset=".52" stop-color="#8f1f7a"/><stop offset=".66" stop-color="#ff3d8a"/>'
        '<stop offset=".80" stop-color="#ff8a3d"/><stop offset="1" stop-color="#ffd23f"/></linearGradient>'
        f'<linearGradient id="sea" gradientUnits="userSpaceOnUse" x1="0" y1="{hy}" x2="0" y2="{H}">'
        '<stop offset="0" stop-color="#2a0b4f"/><stop offset="1" stop-color="#0b0420"/></linearGradient>'
        f'<linearGradient id="sunG" gradientUnits="userSpaceOnUse" x1="0" y1="{hy - 290}" x2="0" y2="{hy}">'
        '<stop offset="0" stop-color="#ffe55c"/><stop offset=".55" stop-color="#ff6a3d"/>'
        '<stop offset="1" stop-color="#ff1f8e"/></linearGradient>'
        f'<clipPath id="above"><rect x="0" y="0" width="{W}" height="{hy}"/></clipPath>'
        '<mask id="stripes"><rect width="1920" height="1080" fill="#fff"/>'
        + "".join(f'<rect x="0" y="{hy - 150 + i * 28}" width="1920" height="{3 + i * 3}" fill="#000"/>' for i in range(6))
        + '</mask></defs>',
        f'<rect x="0" y="0" width="{W}" height="{hy}" fill="url(#sky)"/>',
        f'<g clip-path="url(#above)"><circle cx="960" cy="{hy - 60}" r="230" fill="url(#sunG)" mask="url(#stripes)"/></g>',
        f'<rect x="0" y="{hy}" width="{W}" height="{H - hy}" fill="url(#sea)"/>',
    ]
    for i in range(14):   # reflexo do sol
        w = 380 - i * 22 + rnd.randint(-20, 20)
        p.append(f'<rect x="{960 - w // 2}" y="{hy + 12 + i * 22}" width="{w}" height="4" fill="#ff3d9a" fill-opacity="{0.42 - i * 0.025:.2f}"/>')

    def skyline(hmin, hmax, fill, op_janela):
        x = -30
        while x < W:
            w, h = rnd.randint(36, 110), rnd.randint(hmin, hmax)
            y = hy - h
            p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"/>')
            if rnd.random() < 0.5:   # topo escalonado (art déco)
                p.append(f'<rect x="{x + w // 4}" y="{y - 22}" width="{w // 2}" height="22" fill="{fill}"/>')
            for cx in range(x + 6, x + w - 8, 12):
                for cy in range(y + 10, hy - 6, 18):
                    if rnd.random() < 0.10:
                        p.append(f'<rect x="{cx}" y="{cy}" width="4" height="7" fill="{rnd.choice(["#ff5fa2", "#2ee6e6", "#ffd23f"])}" fill-opacity="{op_janela}"/>')
            x += w + rnd.randint(-4, 8)

    skyline(50, 170, "#2a0f4f", 0.5)
    skyline(30, 110, "#12062a", 0.7)
    for args in ((150, H + 30, 860, 0.16, 1.0), (360, H + 20, 520, -0.12, 0.7),
                 (1770, H + 30, 880, -0.18, 1.0), (1560, H + 20, 500, 0.10, 0.7)):
        p.append(_palma(*args))
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
    dim = f"rgba(10,4,24,{PAGE_BG_DIM})"
    return (f"linear-gradient({dim}, {dim}), "
            f"url({_page_bg_uri()}) center / cover no-repeat fixed, "
            f"{BG}")


# ── Medidor: anel de prioridades + sol retrô ──────────────────────────────────
def _gauge_svg(qa, qm, ql, total):
    tot = max(total, 1)
    a, m, l = qa / tot * 100, qm / tot * 100, ql / tot * 100

    def arc(r, w, color, start, size):
        return (f'<circle cx="150" cy="150" r="{r}" fill="none" stroke="{color}" stroke-width="{w}" '
                f'pathLength="100" stroke-dasharray="{size:.2f} {100 - size:.2f}" '
                f'stroke-dashoffset="{-start:.2f}" transform="rotate(-90 150 150)"/>')

    stripes = "".join(
        f'<rect x="50" y="{166 + i * 11}" width="200" height="{2 + i * 1.6:.1f}" fill="#1a0d33"/>' for i in range(6)
    )
    return "".join([
        '<svg viewBox="0 0 300 300" class="gta-radar" xmlns="http://www.w3.org/2000/svg">',
        '<defs><linearGradient id="sunv" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#ffe55c"/><stop offset=".55" stop-color="#ff6a3d"/>'
        '<stop offset="1" stop-color="#ff1f8e"/></linearGradient>'
        '<clipPath id="sunclip"><circle cx="150" cy="150" r="88"/></clipPath></defs>',
        f'<circle cx="150" cy="150" r="146" fill="none" stroke="{PINK}" stroke-opacity=".45" stroke-width="1.5"/>',
        f'<circle cx="150" cy="150" r="139" fill="none" stroke="#2ee6e6" stroke-opacity=".35" stroke-width="1" stroke-dasharray="2 7"/>',
        '<circle cx="150" cy="150" r="124" fill="none" stroke="#2a1a47" stroke-width="12"/>',
        arc(124, 12, PINK, 0, a), arc(124, 12, ORANGE, a, m), arc(124, 12, TEAL, a + m, l),
        '<circle cx="150" cy="150" r="104" fill="#1a0d33" stroke="#000" stroke-opacity=".5" stroke-width="2"/>',
        '<circle cx="150" cy="150" r="88" fill="url(#sunv)"/>',
        f'<g clip-path="url(#sunclip)">{stripes}</g>',
        f'<text x="150" y="150" text-anchor="middle" class="r-num">{fmt(total)}</text>',
        '<text x="150" y="170" text-anchor="middle" class="r-lbl">ALERTAS</text>',
        '</svg>',
    ])


def _tile(label, value, tone, bar=None, sub=None):
    barh = (f'<div class="gta-bar"><i class="{tone}" style="width:{min(max(bar, 0), 100):.0f}%"></i></div>'
            if bar is not None else "")
    subh = f'<span class="gta-tile-s">{html.escape(str(sub))}</span>' if sub else ""
    return (f'<div class="gta-tile {tone}"><span class="gta-tile-l">{label}</span>'
            f'<span class="gta-tile-v">{value}</span>{subh}{barh}</div>')


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

    # Nível de procura = categorias de ALTA prioridade com ocorrência / total de categorias de alta
    alta_total = sum(1 for _, p in base.ALERTA_META.values() if p == "alta")
    alta_ativas = int(((df["prioridade"] == "alta") & (df["qtd"] > 0)).sum())
    estrelas = "".join(f'<span class="{"on" if i < alta_ativas else ""}">★</span>' for i in range(alta_total))

    agora = datetime.now()
    left = "".join([
        _tile("Alta prioridade", fmt(qa), "alta", share(qa)),
        _tile("Média prioridade", fmt(qm), "media", share(qm)),
        _tile("Baixa prioridade", fmt(ql), "baixa", share(ql)),
    ])
    right = "".join([
        f'<div class="gta-clock"><span class="gta-clock-t">{agora:%H:%M}</span>'
        f'<span class="gta-clock-d">{agora:%d/%m/%Y}</span></div>',
        f'<div class="gta-tile money"><span class="gta-tile-l">Total de alertas</span>'
        f'<span class="gta-tile-v">{fmt(total)}</span></div>',
        _tile("Saúde da base", f"{limpas}/{total_cats}", "baixa",
              (limpas / total_cats * 100) if total_cats else None, sub="categorias sem ocorrência"),
        (f'<div class="gta-wanted" title="Estrelas acesas = categorias de alta prioridade com ocorrência">'
         f'<span class="gta-wanted-l">Nível de procura</span><span class="gta-stars">{estrelas}</span></div>'
         if alta_total else ""),
    ])
    legenda = (f'<div class="gta-legend"><span><b style="background:{PINK}"></b>Alta</span>'
               f'<span><b style="background:{ORANGE}"></b>Média</span>'
               f'<span><b style="background:{TEAL}"></b>Baixa</span></div>')
    legenda_jogo = (f'<div class="gta-subtitle"><span class="k">Maior ocorrência:</span> '
                    f'{html.escape(str(top["alerta"]))} — {fmt(int(top["qtd"]))} alertas '
                    f'({share(int(top["qtd"])):.1f}% do total)</div>')
    sirene = '<div class="gta-siren"></div>' if (SIRENE and alta_ativas > 0) else ""

    return (f'{sirene}<p class="sedu-section-title" style="margin-top:1.25rem;">painel de controle</p>'
            f'<div class="gta-stage"><div class="gta-side">{left}</div>'
            f'<div class="gta-core">{_gauge_svg(qa, qm, ql, total)}{legenda}</div>'
            f'<div class="gta-side">{right}</div></div>{legenda_jogo}')


# ── Injeções no st.markdown / st.plotly_chart durante o render() ──────────────
def _roda(cx):
    return (f'<g class="vc-wheel"><circle cx="{cx}" cy="33" r="8" fill="#0a0318"/>'
            f'<circle cx="{cx}" cy="33" r="3.2" fill="#bbb"/>'
            f'<line x1="{cx}" y1="29.5" x2="{cx}" y2="36.5" stroke="#555" stroke-width="1.4"/></g>')


def _carro_lider_svg():
    """Esportivo rosa com neon turquesa embaixo, virado para a direita."""
    return ('<svg class="vc-car" viewBox="0 0 120 44" width="112" height="41" xmlns="http://www.w3.org/2000/svg">'
            f'<ellipse cx="62" cy="40" rx="50" ry="3.5" fill="{TEAL}" fill-opacity=".55"/>'
            '<g transform="translate(120 0) scale(-1 1)">'   # silhueta espelhada: capô comprido na frente (direita)
            f'<path d="M6 30 L11 21 Q15 15 31 13 L52 11 Q62 5 78 9 L97 13 Q112 15 116 25 L116 30 Q116 33 112 33 L10 33 Q6 33 6 30Z" fill="{PINK}"/>'
            '<path d="M55 13 Q62 7 77 10 L89 14 L55 14Z" fill="#1a0d33"/>'
            '</g>'
            '<rect x="5" y="23" width="5" height="4" fill="#ff2a2a"/><rect x="112" y="23" width="5" height="4" fill="#ffe55c"/>'
            + _roda(30) + _roda(92) + '</svg>')


def _viatura_svg():
    """Viatura preta e branca com barra de luz vermelha/azul."""
    return ('<svg class="vc-car" viewBox="0 0 120 44" width="112" height="41" xmlns="http://www.w3.org/2000/svg">'
            '<g transform="translate(120 0) scale(-1 1)">'   # silhueta espelhada: capô comprido na frente (direita)
            '<path d="M4 30 L8 21 Q12 15 26 14 L44 13 Q52 6 70 7 L86 8 Q98 12 107 18 L113 22 Q117 26 117 30 Q117 33 113 33 L8 33 Q4 33 4 30Z" fill="#f4f4f4"/>'
            '<path d="M4 27 L117 27 L117 30 Q117 33 113 33 L8 33 Q4 33 4 30Z" fill="#111"/>'
            '<path d="M50 14 Q54 8 70 9 L84 10 L96 16 L50 16Z" fill="#1a0d33"/>'
            '<rect class="vc-lb r" x="58" y="3" width="10" height="4" rx="1"/><rect class="vc-lb b" x="70" y="3" width="10" height="4" rx="1"/>'
            '</g>'
            '<rect x="3" y="22" width="5" height="4" fill="#ff2a2a"/><rect x="112" y="22" width="5" height="4" fill="#ffe55c"/>'
            + _roda(28) + _roda(92) + '</svg>')


def _estrada_html():
    return ('<div class="vc-road"><div class="vc-pair">'
            f'<div class="vc-police">{_viatura_svg()}<div class="vc-glow"></div></div>'
            f'<div class="vc-lead">{_carro_lider_svg()}</div></div></div>')


def _carrossel_html(body):
    """Transforma a grade de cards do app_alunos num carrossel infinito (conjunto duplicado + translateX(-50%))."""
    pre, pos = '<div class="sedu-cards-grid">', '</div>'
    inner = body[len(pre):-len(pos)]
    n = inner.count('<div class="sedu-card ')
    dur = max(n * 6, 30)   # ~6 s por card → dá para ler
    html_ = (f'<div class="vc-carousel"><div class="vc-track" style="animation-duration:{dur}s">'
             f'<div class="vc-set">{inner}</div><div class="vc-set" aria-hidden="true">{inner}</div></div></div>')
    return html_ + (_estrada_html() if PERSEGUICAO else "")


_CARROSSEL_CSS = f"""
  .vc-carousel {{
    overflow: hidden; padding: 12px 0 14px;
    -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 5%, #000 95%, transparent 100%);
    mask-image: linear-gradient(90deg, transparent 0, #000 5%, #000 95%, transparent 100%);
  }}
  .vc-track {{ display: flex; width: max-content; animation: vcscroll linear infinite; will-change: transform; }}
  .vc-set {{ display: flex; gap: 12px; padding-right: 12px; }}
  @keyframes vcscroll {{ to {{ transform: translateX(-50%); }} }}
  .vc-carousel:hover .vc-track, .vc-carousel:hover .sedu-card {{ animation-play-state: paused; }}
  .vc-track .sedu-card {{ flex: 0 0 200px; width: 200px; animation: vcbob 4s ease-in-out infinite alternate; }}
  .vc-set .sedu-card:nth-child(3n+2) {{ animation-delay: -1.3s; }}
  .vc-set .sedu-card:nth-child(3n)   {{ animation-delay: -2.6s; }}
  @keyframes vcbob {{ from {{ transform: translateY(0); }} to {{ transform: translateY(-6px); }} }}

  /* Estrada + perseguição */
  .vc-road {{
    position: relative; height: 66px; margin: 10px 0 6px; overflow: hidden; border-radius: 12px;
    background: linear-gradient(180deg, #1b1033 0%, #0c0620 100%);
    border-top: 2px solid {PINK}; border-bottom: 2px solid {TEAL}; box-shadow: 0 0 18px {PINK}4d;
  }}
  .vc-road::before {{
    content: ""; position: absolute; left: 0; right: 0; top: 58px; height: 3px;
    background: repeating-linear-gradient(90deg, rgba(255,245,251,.75) 0 28px, transparent 28px 64px);
    animation: vcline .5s linear infinite;
  }}
  @keyframes vcline {{ to {{ background-position: -64px 0; }} }}
  .vc-pair {{ position: absolute; bottom: 8px; left: 0; width: 300px; height: 41px; animation: vcchase 8s linear infinite; will-change: transform; }}
  @keyframes vcchase {{
    0%   {{ transform: translateX(-320px); }}
    78%  {{ transform: translateX(100vw); }}
    100% {{ transform: translateX(100vw); }}
  }}
  .vc-police {{ position: absolute; left: 0; bottom: 0; animation: vcgap 2.4s ease-in-out infinite alternate; }}
  @keyframes vcgap {{ from {{ transform: translateX(0); }} to {{ transform: translateX(26px); }} }}
  .vc-lead {{ position: absolute; left: 150px; bottom: 0; animation: vcweave 1.4s ease-in-out infinite alternate; }}
  @keyframes vcweave {{ from {{ transform: translateY(0) rotate(0deg); }} to {{ transform: translateY(-5px) rotate(-1.5deg); }} }}
  .vc-car {{ display: block; filter: drop-shadow(0 4px 6px rgba(0,0,0,.6)); }}
  .vc-wheel {{ transform-box: fill-box; transform-origin: center; animation: vcspin .3s linear infinite; }}
  @keyframes vcspin {{ to {{ transform: rotate(360deg); }} }}
  .vc-lb {{ animation: vclb .5s steps(1) infinite; }}
  .vc-lb.r {{ fill: #ff2a2a; }}
  .vc-lb.b {{ fill: #2a6bff; animation-delay: .25s; }}
  @keyframes vclb {{ 0% {{ opacity: 1; }} 50% {{ opacity: .15; }} }}
  .vc-glow {{ position: absolute; left: 38px; top: -16px; width: 64px; height: 44px; border-radius: 50%; pointer-events: none; animation: vcpol .5s steps(1) infinite; }}
  @keyframes vcpol {{
    0%   {{ background: radial-gradient(circle, rgba(255,42,42,.55), transparent 65%); }}
    50%  {{ background: radial-gradient(circle, rgba(42,107,255,.55), transparent 65%); }}
  }}
  @media (prefers-reduced-motion: reduce) {{
    .vc-track, .vc-track .sedu-card, .vc-pair, .vc-police, .vc-lead, .vc-wheel, .vc-lb, .vc-glow, .vc-road::before {{ animation: none !important; }}
  }}
"""


def _make_md(orig):
    def _md(body, *args, **kwargs):
        if (CARROSSEL and isinstance(body, str) and body.startswith('<div class="sedu-cards-grid">')
                and body.endswith('</div>')):
            body = _carrossel_html(body)
        orig(body, *args, **kwargs)
        if isinstance(body, str) and 'class="sedu-banner"' in body:
            # Identidade visual cinematográfica inspirada em Vice City.
            intro = (
                '<div class="gta-intro">'
                '<div class="gta-intro-kicker"><span class="gta-live-dot"></span> SEDU DATA SYSTEMS '
                '<span class="gta-intro-sep">///</span> VICE CITY DISTRICT</div>'
                '<div class="gta-intro-title">BASE <span>EM</span><br><em>CONTROLE</em></div>'
                '<div class="gta-intro-bottom"><span>INTELLIGENCE • ALERT MONITORING</span>'
                '<span class="gta-intro-code">VC-26 // LIVE FEED</span></div>'
                '</div>'
            )
            orig(intro, unsafe_allow_html=True)
            palco = _stage_html()
            if palco:
                orig(palco, unsafe_allow_html=True)
    return _md


def _make_pc(orig):
    """Os gráficos do app_alunos têm fundo branco e fontes pretas fixos; aqui eles são re-tematizados."""
    def _pc(fig, *args, **kwargs):
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(color=TEXT),
                          legend=dict(font=dict(color=TEXT), bgcolor="rgba(26,15,51,.9)", bordercolor=LINE))
        for upd in (fig.update_xaxes, fig.update_yaxes):
            upd(gridcolor="#3a2557", linecolor=LINE, tickfont=dict(color=TEXT), title_font=dict(color=MUTED))
        fig.update_shapes(line=dict(color=LINE))
        return orig(fig, *args, **kwargs)
    return _pc


# ── CSS ───────────────────────────────────────────────────────────────────────
_SANKEY_CSS = ".stApp iframe { filter: invert(1) hue-rotate(180deg); border-radius: 12px; }" if SANKEY_ESCURO else ""
_GLASS = "backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px);"

HUD_CSS = f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Montserrat:wght@500;600;700&display=swap');

  .stApp {{
    background: {_page_bg_layers()} !important;
    font-family: 'Montserrat', 'Segoe UI', Arial, sans-serif;
    color: {TEXT};
  }}
  /* vinheta suave */
  .stApp::after {{
    content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 9999;
    background: radial-gradient(ellipse at center, transparent 60%, rgba(10,4,24,.5) 100%);
  }}
  .stApp p, .stApp label, .stApp span, .stApp li {{ color: {TEXT}; }}
  code {{ color: {SUN} !important; background: {SOLID} !important; }}

  /* Sirene (faixa vermelho/azul no topo) */
  .gta-siren {{ position: fixed; top: 0; left: 0; right: 0; height: 4px; z-index: 10000; pointer-events: none;
    background: linear-gradient(90deg, {RED} 0 50%, {BLUE} 50% 100%); animation: vcsiren 1.2s steps(1) infinite; }}
  @keyframes vcsiren {{
    0%   {{ background: linear-gradient(90deg, {RED} 0 50%, {BLUE} 50% 100%); }}
    50%  {{ background: linear-gradient(90deg, {BLUE} 0 50%, {RED} 50% 100%); }}
  }}

  /* Header — vidro roxo com brilho rosa */
  .sedu-header {{
    background: {PANEL} !important; {_GLASS}
    border: 1px solid {PINK}88; border-radius: 16px !important;
    box-shadow: 0 0 26px {PINK}40, inset 0 0 30px {VIOLET}22;
  }}
  .sedu-header-divider {{ background: {PINK}66 !important; }}
  .sedu-header .sedu-header-title {{
    font-family: 'Bebas Neue', Impact, 'Arial Narrow', sans-serif !important; font-weight: 400 !important;
    font-size: 34px !important; letter-spacing: .08em; text-transform: uppercase; color: #fff !important;
    text-shadow: 0 0 18px {PINK}bb, 2px 2px 0 rgba(0,0,0,.6);
  }}
  .sedu-header .sedu-header-sub {{ color: {MUTED} !important; letter-spacing: .16em; text-transform: uppercase; }}
  .sedu-badge {{ background: rgba(0,0,0,.35) !important; border: 1px solid {PINK}66; border-radius: 20px !important; color: {TEXT} !important; }}
  .sedu-dot {{ background: {TEAL} !important; box-shadow: 0 0 8px {TEAL}; }}

  /* Banner — pôr do sol */
  .sedu-banner {{
    background: linear-gradient(90deg, #3b1a6b 0%, {PINK} 62%, {ORANGE} 100%) !important;
    border-radius: 16px !important; margin-top: 10px; box-shadow: 0 6px 24px {PINK}55;
  }}
  .sedu-banner .sedu-banner-num {{ font-family: 'Bebas Neue', Impact, sans-serif !important; font-weight: 400 !important; font-size: 44px !important; color: #fff !important; {OUT} }}
  .sedu-banner .sedu-banner-label {{ color: #fff !important; opacity: .9; letter-spacing: .14em; text-transform: uppercase; }}
  .sedu-chip {{ background: rgba(15,6,38,.45) !important; border: 1px solid rgba(255,255,255,.25); border-radius: 12px !important; }}
  .sedu-chip .sedu-chip-num {{ color: #fff !important; font-family: 'Bebas Neue', Impact, sans-serif; font-weight: 400; letter-spacing: .04em; font-size: 20px; }}
  .sedu-chip .sedu-chip-label {{ color: #f3d9ec !important; }}
  .sedu-chip:nth-child(1) .sedu-chip-dot {{ background: {PINK} !important; box-shadow: 0 0 6px {PINK}; }}
  .sedu-chip:nth-child(2) .sedu-chip-dot {{ background: {ORANGE} !important; box-shadow: 0 0 6px {ORANGE}; }}
  .sedu-chip:nth-child(3) .sedu-chip-dot {{ background: {TEAL} !important; box-shadow: 0 0 6px {TEAL}; }}

  /* Títulos de seção */
  .sedu-section-title {{
    color: #fff !important; border-bottom: 2px solid transparent !important;
    border-image: linear-gradient(90deg, {PINK}, {ORANGE}, transparent) 1 !important;
    font-family: 'Bebas Neue', Impact, sans-serif; font-weight: 400 !important; font-size: 18px !important;
    letter-spacing: .14em; {OUT}
  }}
  .sedu-section-title::before {{ content: "✦"; color: {SUN}; margin-right: 8px; }}

  /* ── Palco ── */
  .gta-stage {{ display: grid; grid-template-columns: 1fr 340px 1fr; gap: 22px; align-items: center; margin: 8px 0 10px; }}
  .gta-side {{ display: flex; flex-direction: column; gap: 10px; }}
  .gta-core {{ display: flex; flex-direction: column; align-items: center; gap: 8px; }}
  .gta-radar {{ width: 100%; max-width: 320px; animation: vcglow 3.5s ease-in-out infinite alternate; }}
  @keyframes vcglow {{
    from {{ filter: drop-shadow(0 0 12px {PINK}77); }}
    to   {{ filter: drop-shadow(0 0 26px {ORANGE}aa); }}
  }}
  .gta-radar .r-num {{ font-family: 'Bebas Neue', Impact, sans-serif; font-size: 44px; fill: #fff; stroke: #1a0d33; stroke-width: 5px; paint-order: stroke; }}
  .gta-radar .r-lbl {{ font-family: 'Montserrat', sans-serif; font-weight: 700; font-size: 10px; letter-spacing: .26em; fill: #fff; stroke: #1a0d33; stroke-width: 3px; paint-order: stroke; }}
  .gta-stage .gta-legend {{ display: flex; gap: 16px; font-size: 12px; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; }}
  .gta-stage .gta-legend span {{ display: flex; align-items: center; gap: 6px; color: {TEXT}; {OUT} }}
  .gta-stage .gta-legend b {{ width: 11px; height: 11px; display: inline-block; border-radius: 50%; }}

  /* Coluna direita: relógio, total, saúde, estrelas */
  .gta-stage .gta-clock {{ display: flex; justify-content: flex-end; align-items: baseline; gap: 10px; }}
  .gta-stage .gta-clock-t {{ font-family: 'Bebas Neue', Impact, sans-serif; font-size: 46px; {GRAD('#ffffff', '#ffb3d9')} }}
  .gta-stage .gta-clock-d {{ font-size: 12px; font-weight: 600; letter-spacing: .14em; color: {TEXT}; {OUT} }}
  .gta-stage .gta-wanted {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; background: {PANEL}; {_GLASS} border: 1px solid {LINE}; border-radius: 12px; padding: 6px 14px; }}
  .gta-stage .gta-wanted-l {{ font-size: 11px; font-weight: 600; letter-spacing: .16em; text-transform: uppercase; color: {MUTED}; }}
  .gta-stage .gta-stars span {{ font-size: 24px; color: #3a2557; margin: 0 1px; }}
  .gta-stage .gta-stars span.on {{ color: {SUN}; text-shadow: 0 0 10px {SUN}aa, 1px 1px 0 rgba(0,0,0,.6); animation: vcstar 1.2s steps(1) infinite; }}
  @keyframes vcstar {{ 50% {{ color: #c79a1f; }} }}

  .gta-tile {{
    background: {PANEL}; {_GLASS}
    border: 1px solid {LINE}; border-left: 5px solid {VIOLET}; border-radius: 12px; padding: 10px 14px;
    display: grid; grid-template-columns: 1fr auto; row-gap: 6px; align-items: baseline;
    box-shadow: 0 4px 16px rgba(0,0,0,.35);
  }}
  .gta-tile.alta  {{ border-left-color: {PINK}; }}
  .gta-tile.media {{ border-left-color: {ORANGE}; }}
  .gta-tile.baixa {{ border-left-color: {TEAL}; }}
  .gta-tile.money {{ border-left-color: {SUN}; background: linear-gradient(90deg, rgba(255,46,126,.28) 0%, {PANEL} 100%); }}
  .gta-stage .gta-tile-l {{ font-size: 11px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; color: {MUTED}; }}
  .gta-stage .gta-tile-v {{ font-family: 'Bebas Neue', Impact, sans-serif; font-size: 30px; {GRAD('#ffffff', '#ffc2e0')} }}
  .gta-stage .gta-tile.alta  .gta-tile-v {{ {GRAD('#ffb3d1', PINK)} }}
  .gta-stage .gta-tile.media .gta-tile-v {{ {GRAD('#ffe08a', ORANGE)} }}
  .gta-stage .gta-tile.baixa .gta-tile-v {{ {GRAD('#a5fff0', TEAL)} }}
  .gta-stage .gta-tile.money .gta-tile-v {{ font-size: 40px; {GRAD(SUN, PINK)} }}
  .gta-stage .gta-tile-s {{ grid-column: 1 / -1; font-size: 12px; color: {TEXT}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .gta-bar {{ grid-column: 1 / -1; height: 8px; background: rgba(0,0,0,.4); border-radius: 6px; overflow: hidden; }}
  .gta-bar i {{ display: block; height: 100%; border-radius: 6px; background: {VIOLET}; }}
  .gta-bar i.alta {{ background: linear-gradient(90deg, {PINK}, #ff7ab0); box-shadow: 0 0 8px {PINK}; }}
  .gta-bar i.media {{ background: linear-gradient(90deg, {ORANGE}, {SUN}); box-shadow: 0 0 8px {ORANGE}; }}
  .gta-bar i.baixa {{ background: linear-gradient(90deg, {TEAL}, #7dfff0); box-shadow: 0 0 8px {TEAL}; }}

  /* Legenda no estilo de legenda de jogo */
  .gta-subtitle {{
    text-align: center; margin: 6px 0 18px; padding: 9px 16px; background: rgba(15,6,38,.55); border-radius: 12px;
    font-weight: 600; font-size: 16px; letter-spacing: .02em; color: #fff; {OUT}
  }}
  .gta-subtitle .k {{ color: {SUN}; text-transform: uppercase; letter-spacing: .1em; }}

  /* Cards */
  .sedu-card {{
    background: {PANEL} !important; {_GLASS}
    border: 1px solid {LINE} !important; border-top: 4px solid {ORANGE} !important;
    border-radius: 14px !important; box-shadow: 0 4px 16px rgba(0,0,0,.35);
  }}
  .sedu-card::after {{ background: {ORANGE}22 !important; opacity: 1 !important; }}
  .sedu-card.warn {{ border-top-color: {PINK} !important; }}
  .sedu-card.warn::after {{ background: {PINK}22 !important; }}
  .sedu-card.ok   {{ border-top-color: {TEAL} !important; }}
  .sedu-card.ok::after {{ background: {TEAL}22 !important; }}
  .sedu-card:hover {{ border-color: {PINK} !important; box-shadow: 0 8px 28px {PINK}55 !important; }}
  .sedu-card .sedu-card-label {{ color: {MUTED} !important; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }}
  .sedu-card .sedu-card-value {{ font-family: 'Bebas Neue', Impact, sans-serif; font-weight: 400 !important; font-size: 32px !important; {GRAD('#ffe08a', ORANGE)} }}
  .sedu-card .sedu-card-value.warn {{ {GRAD('#ffb3d1', PINK)} }}
  .sedu-card .sedu-card-value.ok   {{ {GRAD('#a5fff0', TEAL)} }}
  .sedu-card-badge.high, .pill.high {{ background: {PINK}2e !important; color: #ff9cc4 !important; border: 1px solid {PINK}99; }}
  .sedu-card-badge.med,  .pill.med  {{ background: {ORANGE}2e !important; color: #ffc766 !important; border: 1px solid {ORANGE}99; }}
  .sedu-card-badge.low,  .pill.low  {{ background: {TEAL}2e !important; color: #7ff0de !important; border: 1px solid {TEAL}99; }}

  /* Caixa da legenda do gráfico de barras (fundo branco inline) */
  div[style*="padding:14px 18px"] {{ background: {PANEL} !important; border: 1px solid {LINE} !important; border-radius: 14px !important; }}

  /* Gráficos */
  div[data-testid="stPlotlyChart"] {{ background: {PANEL} !important; {_GLASS} border: 1px solid {LINE}; border-radius: 14px !important; padding: 8px; }}

  /* Tabela (estilos inline brancos → !important) */
  div[data-testid="stMarkdownContainer"] table td {{ background: {SOLID} !important; color: {TEXT} !important; border-bottom: 1px solid {LINE} !important; }}
  div[data-testid="stMarkdownContainer"] table tr:hover td {{ background: {PANEL2} !important; }}
  div[data-testid="stMarkdownContainer"] table th {{ background: linear-gradient(90deg, #3b1a6b, {PINK}) !important; color: #fff !important; letter-spacing: .06em; text-transform: uppercase; }}
  div[style*="overflow:auto"] {{ background: {SOLID} !important; border: 1px solid {LINE} !important; border-radius: 14px !important; }}

  /* Widgets */
  div[data-baseweb="select"] > div, div[data-baseweb="input"] > div {{ background: {SOLID} !important; border-color: {LINE} !important; border-radius: 10px !important; color: {TEXT} !important; }}
  div[data-baseweb="select"] * {{ color: {TEXT} !important; }}
  ul[role="listbox"] {{ background: {SOLID} !important; }}
  .stDownloadButton button, .stButton button {{
    background: linear-gradient(90deg, {PINK}, {ORANGE}) !important; color: #fff !important; border: 0 !important;
    border-radius: 20px !important; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
  }}
  .stDownloadButton button:hover, .stButton button:hover {{ box-shadow: 0 0 18px {PINK}aa; filter: brightness(1.1); }}
  div[data-testid="stCaptionContainer"] * {{ color: {MUTED} !important; }}
  a[href*="shinyapps"] {{ background: linear-gradient(90deg, {PINK}, {ORANGE}) !important; color: #fff !important; border: 0 !important; border-radius: 20px !important; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }}

  {_CARROSSEL_CSS}
  {_SANKEY_CSS}

  /* ── GTA VI / Vice City: camada de impacto cinematográfico ── */
  .stApp {{
    background-image:
      linear-gradient(180deg, rgba(9,3,23,.35), rgba(9,3,23,.72)),
      {_page_bg_layers()} !important;
    background-attachment: fixed !important;
  }}
  .stApp::before {{
    content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 1;
    opacity: .12;
    background: repeating-linear-gradient(0deg, transparent 0 3px, rgba(255,255,255,.08) 4px, transparent 5px);
    mix-blend-mode: screen;
  }}
  .stApp [data-testid="stAppViewContainer"] {{ position: relative; z-index: 2; }}
  .gta-intro {{
    position: relative; overflow: hidden; margin: 18px 0 20px; padding: 26px 30px 20px;
    border: 1px solid rgba(255,46,126,.65); border-radius: 18px;
    background: linear-gradient(112deg, rgba(15,6,38,.97) 0%, rgba(52,13,76,.88) 48%, rgba(255,46,126,.20) 100%);
    box-shadow: 0 12px 40px rgba(0,0,0,.42), 0 0 26px rgba(255,46,126,.18), inset 0 0 35px rgba(155,92,255,.10);
  }}
  .gta-intro::before {{
    content: ""; position: absolute; right: -70px; top: -180px; width: 430px; height: 430px;
    border: 1px solid rgba(255,210,63,.45); border-radius: 50%;
    box-shadow: 0 0 0 18px rgba(255,210,63,.035), 0 0 0 42px rgba(255,46,126,.04), 0 0 70px rgba(255,46,126,.18);
  }}
  .gta-intro::after {{
    content: "VI"; position: absolute; right: 36px; top: -45px;
    font: 400 230px/.95 'Bebas Neue', Impact, sans-serif; letter-spacing: -.08em;
    color: rgba(255,255,255,.035); transform: skew(-8deg); pointer-events: none;
  }}
  .gta-intro-kicker {{
    position: relative; z-index: 1; display: flex; align-items: center; gap: 9px;
    color: #ffd23f; font: 700 10px/1.4 'Montserrat', sans-serif; letter-spacing: .24em;
  }}
  .gta-live-dot {{ width: 7px; height: 7px; border-radius: 50%; background: #1fe0c4; box-shadow: 0 0 12px #1fe0c4; }}
  .gta-intro-sep {{ color: #ff2e7e; }}
  .gta-intro-title {{
    position: relative; z-index: 1; margin: 10px 0 4px; color: #fff;
    font: 400 clamp(46px, 7vw, 86px)/.83 'Bebas Neue', Impact, sans-serif;
    letter-spacing: .015em; text-shadow: 0 5px 0 rgba(0,0,0,.22), 0 0 24px rgba(255,46,126,.24);
  }}
  .gta-intro-title span {{ color: #ff9cc4; font-size: .48em; letter-spacing: .12em; vertical-align: middle; }}
  .gta-intro-title em {{
    font-style: normal; background: linear-gradient(90deg, #ff2e7e 0%, #ffa530 55%, #ffd23f 100%);
    -webkit-background-clip: text; background-clip: text; color: transparent;
    filter: drop-shadow(0 3px 0 rgba(0,0,0,.45));
  }}
  .gta-intro-bottom {{
    position: relative; z-index: 1; display: flex; justify-content: space-between; gap: 12px;
    margin-top: 20px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.16);
    color: #c9a9d9; font: 600 9px/1.4 'Montserrat', sans-serif; letter-spacing: .17em;
  }}
  .gta-intro-code {{ color: #1fe0c4; }}
  .sedu-header {{ border-color: rgba(255,46,126,.75) !important; }}
  .sedu-banner {{ position: relative; overflow: hidden; }}
  .sedu-banner::after {{
    content: ""; position: absolute; inset: 0; pointer-events: none;
    background: linear-gradient(110deg, transparent 0 35%, rgba(255,255,255,.16) 48%, transparent 60%);
    transform: translateX(-100%); animation: gta-sheen 7s ease-in-out infinite;
  }}
  @keyframes gta-sheen {{ 0%, 65% {{ transform: translateX(-100%); }} 90%, 100% {{ transform: translateX(100%); }} }}
  .gta-tile, .sedu-card, div[data-testid="stPlotlyChart"] {{
    transition: transform .22s ease, border-color .22s ease, box-shadow .22s ease;
  }}
  .gta-tile:hover {{ transform: translateY(-3px); border-color: {PINK} !important; box-shadow: 0 8px 24px rgba(255,46,126,.18); }}
  .gta-subtitle {{ border: 1px solid rgba(255,210,63,.22); box-shadow: inset 3px 0 0 {SUN}, 0 6px 20px rgba(0,0,0,.2); }}
  @media (max-width: 900px) {{
    .gta-intro {{ padding: 20px 18px 16px; }}
    .gta-intro::after {{ right: -8px; font-size: 150px; }}
    .gta-intro-bottom {{ flex-wrap: wrap; }}
    .gta-stage {{ grid-template-columns: 1fr; }}
    .gta-core {{ order: -1; }}
    .gta-radar {{ max-width: 250px; }}
  }}
  @media (prefers-reduced-motion: reduce) {{
    .gta-intro *, .sedu-banner::after {{ animation: none !important; }}
  }}
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
    st.set_page_config(page_title="VICE CITY // SEDU HUD", page_icon="🌴", layout="wide")
    render()
